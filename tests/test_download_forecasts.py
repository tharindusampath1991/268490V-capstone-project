"""Tests for the forecast fetch functions. They use a fake client and no network."""

import pandas as pd
from entsoe.exceptions import NoMatchingDataError

from epf.data.download_forecasts import fetch_load_forecast, fetch_wind_solar_forecast

MARKET_TZ = "Europe/Berlin"
DAY_START = pd.Timestamp("2025-01-15", tz=MARKET_TZ)
DAY_END = pd.Timestamp("2025-01-16", tz=MARKET_TZ)


class FakeClient:
    """Stands in for EntsoePandasClient.

    Like the real client it answers in local time, includes the end timestamp
    and raises NoMatchingDataError when nothing is left.
    """

    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls = []

    def _answer(self, query: str, country_code: str, start: pd.Timestamp,
                end: pd.Timestamp) -> pd.DataFrame:
        self.calls.append((query, country_code, start, end))
        answer = self.frame.truncate(before=start, after=end)
        if len(answer) == 0:
            raise NoMatchingDataError
        return answer

    def query_load_forecast(self, country_code: str, start: pd.Timestamp,
                            end: pd.Timestamp) -> pd.DataFrame:
        return self._answer("load_forecast", country_code, start, end)

    def query_wind_and_solar_forecast(self, country_code: str, start: pd.Timestamp,
                                      end: pd.Timestamp) -> pd.DataFrame:
        return self._answer("wind_solar_forecast", country_code, start, end)


def hourly_frame(first: str, last: str, columns: list[str]) -> pd.DataFrame:
    """One value per hour and column from first to last, both included, in market time."""
    index = pd.date_range(first, last, freq="h", tz=MARKET_TZ)
    return pd.DataFrame({column: 1000.0 for column in columns}, index=index)


def test_fetch_load_forecast_returns_utc_values_without_the_end_timestamp():
    client = FakeClient(hourly_frame("2025-01-15", "2025-01-16", ["Forecasted Load"]))

    data = fetch_load_forecast(client, "FR", DAY_START, DAY_END)

    assert list(data.columns) == ["Forecasted Load"]
    assert str(data.index.tz) == "UTC"
    assert len(data) == 24
    assert data.index[0] == pd.Timestamp("2025-01-14 23:00", tz="UTC")
    assert data.index[-1] == pd.Timestamp("2025-01-15 22:00", tz="UTC")
    assert client.calls == [("load_forecast", "FR", DAY_START, DAY_END)]


def test_fetch_wind_solar_forecast_keeps_one_column_per_production_type():
    client = FakeClient(hourly_frame("2025-01-15", "2025-01-16", ["Solar", "Wind Onshore"]))

    data = fetch_wind_solar_forecast(client, "ES", DAY_START, DAY_END)

    assert list(data.columns) == ["Solar", "Wind Onshore"]
    assert len(data) == 24
    assert client.calls == [("wind_solar_forecast", "ES", DAY_START, DAY_END)]


def test_fetch_load_forecast_returns_an_empty_frame_when_entsoe_has_no_data():
    client = FakeClient(hourly_frame("2024-01-01", "2024-01-02", ["Forecasted Load"]))

    data = fetch_load_forecast(client, "FR", DAY_START, DAY_END)

    assert data.empty
    assert str(data.index.tz) == "UTC"
