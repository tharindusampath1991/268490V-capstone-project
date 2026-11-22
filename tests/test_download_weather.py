"""Tests for the weather forecast download. They use a fake HTTP call and no network."""

import pandas as pd
import pytest

from epf.config import Zone
from epf.data.download_weather import (
    OpenMeteoError,
    download_weather,
    fetch_delivery_day,
    fetch_weather,
    parse_forecast_response,
    run_time,
)

MARKET_TZ = "Europe/Berlin"
SETTINGS = {
    "url": "https://example.invalid/v1/forecast",
    "model": "ecmwf_ifs",
    "run_hour_utc": 0,
    "forecast_hours": 48,
    "variables": ["temperature_2m", "shortwave_radiation"],
    "wind_speed_unit": "ms",
    "pause_seconds": 1.0,
}
KASSEL = {"place": "Kassel", "latitude": 51.32, "longitude": 9.50}
DE_LU = Zone("DE_LU", "DE", "core", weather_point=KASSEL)
SE_1 = Zone("SE_1", "SE", "extra", weather_point={"place": "Lulea", "latitude": 65.58,
                                                  "longitude": 22.15})


def market_time(text: str) -> pd.Timestamp:
    """A timestamp in market time. A date alone means 00:00 on that day."""
    return pd.Timestamp(text, tz=MARKET_TZ)


def run_body(run: str, hours: int = 48) -> dict:
    """An answer shaped like a real one: `hours` hourly steps in UTC from the run time."""
    times = pd.date_range(run, periods=hours, freq="h")
    return {
        "latitude": 51.35325,
        "longitude": 9.422382,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "hourly_units": {"time": "iso8601", "temperature_2m": "°C",
                         "shortwave_radiation": "W/m²"},
        "hourly": {
            "time": [moment.strftime("%Y-%m-%dT%H:%M") for moment in times],
            "temperature_2m": [float(step) for step in range(hours)],
            # Like the real API, the radiation of the first step is empty.
            "shortwave_radiation": [None] + [100.0] * (hours - 1),
        },
    }


class FakeResponse:
    """Stands in for requests.Response."""

    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self.body = body

    def json(self) -> dict:
        return self.body


class FakeApi:
    """Stands in for requests.get. It answers every run except those listed as unavailable."""

    def __init__(self, unavailable: tuple[str, ...] = ()) -> None:
        self.unavailable = unavailable
        self.calls = []

    def __call__(self, url: str, params: dict) -> FakeResponse:
        self.calls.append((url, params))
        if params["run"] in self.unavailable:
            return FakeResponse(400, {"error": True,
                                      "reason": "The requested model run is not available."})
        return FakeResponse(200, run_body(params["run"], params["forecast_hours"]))


def no_sleep(seconds: float) -> None:
    """Replaces time.sleep in tests."""


def test_parse_forecast_response_gives_a_utc_index_and_one_column_per_variable():
    data = parse_forecast_response(run_body("2025-01-14T00:00", hours=3))

    assert list(data.columns) == ["temperature_2m", "shortwave_radiation"]
    assert str(data.index.tz) == "UTC"
    assert data.index[0] == pd.Timestamp("2025-01-14 00:00", tz="UTC")
    assert data["temperature_2m"].tolist() == [0.0, 1.0, 2.0]
    assert pd.isna(data["shortwave_radiation"].iloc[0])


def test_parse_forecast_response_rejects_an_answer_that_is_not_in_utc():
    body = run_body("2025-01-14T00:00", hours=3)
    body["utc_offset_seconds"] = 3600

    with pytest.raises(OpenMeteoError, match="UTC"):
        parse_forecast_response(body)


@pytest.mark.parametrize("day, run", [
    ("2025-01-15", "2025-01-14 00:00"),
    ("2026-03-29", "2026-03-28 00:00"),    # clocks go forward on the delivery day
    ("2026-10-26", "2026-10-25 00:00"),    # clocks went back the day before
])
def test_run_time_is_midnight_utc_on_the_day_before_delivery(day, run):
    assert run_time(market_time(day), run_hour_utc=0) == pd.Timestamp(run, tz="UTC")


def test_fetch_delivery_day_asks_for_the_run_of_the_day_before():
    api = FakeApi()

    fetch_delivery_day(api, SETTINGS, KASSEL, market_time("2025-01-15"), market_time("2025-01-16"))

    assert api.calls == [("https://example.invalid/v1/forecast", {
        "latitude": 51.32,
        "longitude": 9.50,
        "run": "2025-01-14T00:00",
        "hourly": "temperature_2m,shortwave_radiation",
        "models": "ecmwf_ifs",
        "forecast_hours": 48,
        "wind_speed_unit": "ms",
    })]


def test_fetch_delivery_day_keeps_the_hours_of_the_delivery_day_and_records_the_run():
    data = fetch_delivery_day(FakeApi(), SETTINGS, KASSEL,
                              market_time("2025-01-15"), market_time("2025-01-16"))

    assert list(data.columns) == ["temperature_2m", "shortwave_radiation", "run"]
    assert len(data) == 24
    assert data.index[0] == pd.Timestamp("2025-01-14 23:00", tz="UTC")
    assert data.index[-1] == pd.Timestamp("2025-01-15 22:00", tz="UTC")
    # The run starts at 14 Jan 00:00 UTC, so the first hour of the delivery day is step 23.
    assert data["temperature_2m"].iloc[0] == 23.0
    assert (data["run"] == pd.Timestamp("2025-01-14 00:00", tz="UTC")).all()


@pytest.mark.parametrize("day, next_day, hours", [
    ("2026-03-29", "2026-03-30", 23),
    ("2026-10-25", "2026-10-26", 25),
])
def test_fetch_delivery_day_covers_every_hour_of_a_clock_change_day(day, next_day, hours):
    data = fetch_delivery_day(FakeApi(), SETTINGS, KASSEL, market_time(day), market_time(next_day))

    assert len(data) == hours
    assert data.index[0] == market_time(day)
    assert data["temperature_2m"].notna().all()


def test_fetch_delivery_day_returns_no_rows_when_the_run_is_not_archived():
    api = FakeApi(unavailable=("2025-01-14T00:00",))

    data = fetch_delivery_day(api, SETTINGS, KASSEL,
                              market_time("2025-01-15"), market_time("2025-01-16"))

    assert data.empty


def test_fetch_delivery_day_raises_for_any_other_error_answer():
    def get(url: str, params: dict) -> FakeResponse:
        return FakeResponse(429, {"error": True, "reason": "Minutely API request limit exceeded."})

    with pytest.raises(OpenMeteoError, match="429.*limit exceeded"):
        fetch_delivery_day(get, SETTINGS, KASSEL,
                           market_time("2025-01-15"), market_time("2025-01-16"))


def test_fetch_weather_asks_one_run_per_delivery_day_and_pauses_before_each():
    api = FakeApi()
    pauses = []

    data = fetch_weather(api, SETTINGS, KASSEL, market_time("2026-10-24"),
                         market_time("2026-10-27"), sleep=pauses.append)

    assert [params["run"] for _, params in api.calls] == [
        "2026-10-23T00:00", "2026-10-24T00:00", "2026-10-25T00:00"]
    assert pauses == [1.0, 1.0, 1.0]
    assert len(data) == 24 + 25 + 24
    assert data.index.is_monotonic_increasing
    assert data.index.is_unique


def test_fetch_weather_leaves_out_a_day_whose_run_is_not_archived():
    api = FakeApi(unavailable=("2025-01-15T00:00",))

    data = fetch_weather(api, SETTINGS, KASSEL, market_time("2025-01-15"),
                         market_time("2025-01-18"), sleep=no_sleep)

    assert len(data) == 48
    assert data["run"].nunique() == 2


def test_fetch_weather_returns_no_rows_when_no_run_is_archived():
    api = FakeApi(unavailable=("2025-01-14T00:00",))

    data = fetch_weather(api, SETTINGS, KASSEL, market_time("2025-01-15"),
                         market_time("2025-01-16"), sleep=no_sleep)

    assert data.empty
    assert str(data.index.tz) == "UTC"


def test_download_weather_reports_each_zone_year_and_variable_in_the_given_order(tmp_path):
    ranges = [(2025, market_time("2025-01-15"), market_time("2025-01-17"))]

    summary = download_weather(FakeApi(), SETTINGS, [DE_LU, SE_1], ranges, tmp_path,
                               sleep=no_sleep)

    assert summary.to_dict("records")[0] == {
        "zone": "DE_LU", "year": 2025, "column": "temperature_2m", "rows": 48, "runs": 2,
        "expected_hours": 48, "missing_hours": 0, "repeated": 0,
    }
    assert summary["zone"].tolist() == ["DE_LU", "DE_LU", "SE_1", "SE_1"]
    assert summary["column"].tolist() == ["temperature_2m", "shortwave_radiation"] * 2
    assert (tmp_path / "weather_forecast" / "DE_LU_2025.parquet").exists()


def test_download_weather_uses_the_point_of_each_zone(tmp_path):
    api = FakeApi()
    ranges = [(2025, market_time("2025-01-15"), market_time("2025-01-16"))]

    download_weather(api, SETTINGS, [DE_LU, SE_1], ranges, tmp_path, sleep=no_sleep)

    assert [(params["latitude"], params["longitude"]) for _, params in api.calls] == [
        (51.32, 9.50), (65.58, 22.15)]


def test_download_weather_counts_the_hours_of_a_missing_run(tmp_path):
    api = FakeApi(unavailable=("2025-01-15T00:00",))
    ranges = [(2025, market_time("2025-01-15"), market_time("2025-01-17"))]

    summary = download_weather(api, SETTINGS, [DE_LU], ranges, tmp_path, sleep=no_sleep)

    assert summary["missing_hours"].tolist() == [24, 24]
    assert summary["runs"].tolist() == [1, 1]


def test_download_weather_uses_the_saved_files_on_a_second_run(tmp_path):
    api = FakeApi()
    ranges = [(2025, market_time("2025-01-15"), market_time("2025-01-17"))]
    download_weather(api, SETTINGS, [DE_LU], ranges, tmp_path, sleep=no_sleep)

    summary = download_weather(api, SETTINGS, [DE_LU], ranges, tmp_path, sleep=no_sleep)

    assert len(api.calls) == 2
    assert summary["rows"].tolist() == [48, 48]


def test_download_weather_leaves_out_a_zone_without_a_weather_point(tmp_path):
    api = FakeApi()
    ranges = [(2025, market_time("2025-01-15"), market_time("2025-01-16"))]

    summary = download_weather(api, SETTINGS, [Zone("FR", "FR", "core"), DE_LU], ranges, tmp_path,
                               sleep=no_sleep)

    assert summary["zone"].unique().tolist() == ["DE_LU"]
    assert len(api.calls) == 1
