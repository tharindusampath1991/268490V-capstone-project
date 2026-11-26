"""Tests for the dataset build. They use small synthetic frames, a temporary folder and no network."""

from datetime import timedelta

import pandas as pd
import pytest
import yaml

from epf.data.build_dataset import (
    build_hourly,
    build_quarter_hour,
    build_weather,
    run,
)
from epf.data.clean import Period
from epf.data.entsoe_cache import cached_fetch
from epf.data.market_time import (
    expected_price_index,
    hourly_index,
    quarter_hour_index,
    year_ranges,
)
from epf.data.validate import HOURLY, QUARTER_HOUR, WEATHER_TABLE, table_path

MARKET_TZ = "Europe/Berlin"
SWITCH = pd.Timestamp("2025-10-01", tz=MARKET_TZ)
MADRID = {"place": "Madrid", "latitude": 40.42, "longitude": -3.70}
MADE_UP_POINT = {"place": "X", "latitude": 10.0, "longitude": 20.0}


def market_time(text: str) -> pd.Timestamp:
    """A timestamp in market time. A date alone means 00:00 on that day."""
    return pd.Timestamp(text, tz=MARKET_TZ)


def period(first_day: str, day_after_last: str) -> Period:
    """A data period [first_day, day_after_last) whose weather starts on the first day."""
    start = market_time(first_day)
    return Period(start, market_time(day_after_last), SWITCH, weather_start=start)


def prices(first_day: str, day_after_last: str) -> pd.DataFrame:
    """One price per market time unit of [first_day, day_after_last): 0.0, 1.0, 2.0 and so on."""
    index = expected_price_index(market_time(first_day), market_time(day_after_last), SWITCH)
    return pd.DataFrame({"price": range(len(index))}, index=index, dtype="float64")


def hourly_frame(first_day: str, day_after_last: str, columns: list[str]) -> pd.DataFrame:
    """One value per hour and column: 0.0, 4.0, 8.0 and so on."""
    index = hourly_index(market_time(first_day), market_time(day_after_last))
    return pd.DataFrame({column: [4.0 * step for step in range(len(index))] for column in columns},
                        index=index)


def quarter_hour_frame(first_day: str, day_after_last: str, columns: list[str]) -> pd.DataFrame:
    """One value per quarter-hour and column: 0.0, 1.0, 2.0 and so on."""
    index = quarter_hour_index(market_time(first_day), market_time(day_after_last))
    return pd.DataFrame({column: range(len(index)) for column in columns}, index=index,
                        dtype="float64")


def weather_frame(first_day: str, day_after_last: str) -> pd.DataFrame:
    """One temperature per hour, with a run time 24 hours before the first day."""
    index = hourly_index(market_time(first_day), market_time(day_after_last))
    run_time = pd.Timestamp(first_day, tz="UTC") - timedelta(hours=24)
    return pd.DataFrame({"temperature_2m": 10.0, "run": run_time}, index=index)


def cleaned_frames(first_day: str, day_after_last: str, frame=quarter_hour_frame) -> dict:
    """Cleaned frames of one zone, named as the cleaning step names them."""
    return {
        "prices": prices(first_day, day_after_last),
        "load_forecast": frame(first_day, day_after_last, ["load_forecast"]),
        "wind_solar_forecast": frame(first_day, day_after_last,
                                     ["solar_forecast", "wind_onshore_forecast"]),
        "actual_load": frame(first_day, day_after_last, ["actual_load"]),
        "weather_forecast": weather_frame(first_day, day_after_last),
    }


@pytest.mark.parametrize("day, next_day, hours", [
    ("2026-03-29", "2026-03-30", 23),    # clocks go forward
    ("2026-10-25", "2026-10-26", 25),    # clocks go back
])
def test_build_hourly_has_one_row_per_hour_of_a_clock_change_day(day, next_day, hours):
    table = build_hourly(cleaned_frames(day, next_day), period(day, next_day))

    assert table.index.equals(hourly_index(market_time(day), market_time(next_day)))
    assert len(table) == hours
    # Hour k holds the quarter-hour values 4k to 4k + 3, so its mean is 4k + 1.5.
    assert table["price"].tolist() == [4 * hour + 1.5 for hour in range(hours)]
    assert table["load_forecast"].tolist() == [4 * hour + 1.5 for hour in range(hours)]


def test_build_hourly_keeps_hourly_prices_before_the_switch_and_takes_the_mean_from_it():
    table = build_hourly(cleaned_frames("2025-09-30", "2025-10-02"),
                         period("2025-09-30", "2025-10-02"))

    assert len(table) == 48
    assert table["price"].iloc[:24].tolist() == [float(hour) for hour in range(24)]
    # The 96 quarter-hour prices of 1 October are 24, 25, 26 and so on.
    assert table["price"].iloc[24:].tolist() == [24 + 4 * hour + 1.5 for hour in range(24)]


def test_build_hourly_puts_the_columns_in_one_fixed_order():
    table = build_hourly(cleaned_frames("2026-10-25", "2026-10-26"),
                         period("2026-10-25", "2026-10-26"))

    assert list(table.columns) == ["price", "load_forecast", "wind_onshore_forecast",
                                   "solar_forecast", "actual_load"]


def test_build_hourly_keeps_a_row_for_an_hour_without_data():
    frames = cleaned_frames("2026-10-25", "2026-10-26")
    gap = pd.Timestamp("2026-10-25 10:00", tz="UTC")
    load = frames["load_forecast"]
    frames["load_forecast"] = load[load.index.floor("h") != gap]

    table = build_hourly(frames, period("2026-10-25", "2026-10-26"))

    assert len(table) == 25
    assert pd.isna(table.loc[gap, "load_forecast"])
    assert table["load_forecast"].isna().sum() == 1
    assert table["price"].notna().all()


def test_build_hourly_ends_with_the_last_delivery_day():
    table = build_hourly(cleaned_frames("2026-11-18", "2026-11-20"),
                         period("2026-11-18", "2026-11-20"))

    assert table.index.max() == pd.Timestamp("2026-11-19 22:00", tz="UTC")


@pytest.mark.parametrize("day, next_day, quarter_hours", [
    ("2026-03-29", "2026-03-30", 92),
    ("2026-10-25", "2026-10-26", 100),
])
def test_build_quarter_hour_has_one_row_per_quarter_hour_of_a_clock_change_day(
        day, next_day, quarter_hours):
    table = build_quarter_hour(cleaned_frames(day, next_day), period(day, next_day))

    assert table.index.equals(quarter_hour_index(market_time(day), market_time(next_day)))
    assert len(table) == quarter_hours
    assert table["price"].tolist() == [float(step) for step in range(quarter_hours)]


def test_build_quarter_hour_starts_on_the_first_15_minute_delivery_day():
    table = build_quarter_hour(cleaned_frames("2025-09-30", "2025-10-02"),
                               period("2025-09-30", "2025-10-02"))

    assert len(table) == 96
    assert table.index[0] == pd.Timestamp("2025-09-30 22:00", tz="UTC")
    assert table["price"].tolist() == [24.0 + step for step in range(96)]


def test_build_quarter_hour_repeats_an_hourly_forecast_on_its_four_quarter_hours():
    frames = cleaned_frames("2026-10-25", "2026-10-26", frame=hourly_frame)

    table = build_quarter_hour(frames, period("2026-10-25", "2026-10-26"))

    assert table["load_forecast"].tolist() == [4.0 * (step // 4) for step in range(100)]


def test_build_weather_has_one_row_per_hour_and_keeps_the_run_time():
    frames = cleaned_frames("2026-10-25", "2026-10-26")
    gap = pd.Timestamp("2026-10-25 10:00", tz="UTC")
    frames["weather_forecast"] = frames["weather_forecast"].drop(gap)

    table = build_weather(frames, period("2026-10-25", "2026-10-26"))

    assert len(table) == 25
    assert list(table.columns) == ["temperature_2m", "run"]
    assert pd.isna(table.loc[gap, "temperature_2m"])
    assert table["run"].dropna().eq(pd.Timestamp("2026-10-24", tz="UTC")).all()


def save(cache_dir, dataset: str, zone_key: str, frame: pd.DataFrame,
         first_day: str, day_after_last: str) -> None:
    """Save a frame in a cache folder, one file per year, as the downloaders do."""
    for year, start, end in year_ranges(market_time(first_day), market_time(day_after_last)):
        piece = frame[(frame.index >= start) & (frame.index < end)]
        cached_fetch(lambda query_start, query_end: piece, cache_dir, dataset, zone_key,
                     year, start, end)


def save_raw_zone(raw_dir, zone_key: str, first_day: str, day_after_last: str,
                  load_rows_left_out: int = 0) -> None:
    """Save the five raw datasets of one zone, with the raw ENTSO-E column names.

    The load forecast can be saved without its first rows, to make a gap.
    """
    save(raw_dir / "entsoe", "prices", zone_key, prices(first_day, day_after_last),
         first_day, day_after_last)
    load = quarter_hour_frame(first_day, day_after_last, ["Forecasted Load"])
    save(raw_dir / "entsoe", "load_forecast", zone_key, load.iloc[load_rows_left_out:],
         first_day, day_after_last)
    for dataset, columns in [("wind_solar_forecast", ["Solar", "Wind Onshore"]),
                             ("actual_load", ["Actual Load"])]:
        save(raw_dir / "entsoe", dataset, zone_key,
             quarter_hour_frame(first_day, day_after_last, columns), first_day, day_after_last)
    save(raw_dir / "open_meteo", "weather_forecast", zone_key,
         weather_frame(first_day, day_after_last), first_day, day_after_last)


def project_config(tmp_path, last_day: str | None, approved: dict) -> dict:
    """A config that starts on 24 October 2026, with its folders under tmp_path.

    The extra zone XX is listed before the core zone ES and has its Solar column dropped.
    """
    gaps_path = tmp_path / "approved_gaps.yaml"
    gaps_path.write_text(yaml.safe_dump(approved), encoding="utf-8")
    return {
        "market": {"timezone": MARKET_TZ, "quarter_hour_start": "2025-10-01"},
        "data": {"start": "2026-10-24", "end": last_day},
        "open_meteo": {"first_run": "2024-03-14", "variables": ["temperature_2m"]},
        "paths": {"raw": str(tmp_path / "raw"), "processed": str(tmp_path / "processed"),
                  "approved_gaps": str(gaps_path)},
        "coverage_gate": {"drop_columns": [{"zone": "XX", "column": "Solar"}]},
        "zones": [
            {"key": "XX", "holiday_country": "PL", "group": "extra",
             "weather_point": MADE_UP_POINT},
            {"key": "ES", "holiday_country": "ES", "group": "core", "weather_point": MADRID},
        ],
    }


def no_gaps(columns: list[str]) -> dict:
    """Approved gaps for one zone: the given columns in both tables, with no empty value."""
    table = {column: 0 for column in columns}
    return {HOURLY: table, QUARTER_HOUR: table, WEATHER_TABLE: {"temperature_2m": 0, "run": 0}}


APPROVED = {
    "ES": no_gaps(["price", "load_forecast", "wind_onshore_forecast", "solar_forecast",
                   "actual_load"]),
    "XX": no_gaps(["price", "load_forecast", "wind_onshore_forecast", "actual_load"]),
}


def test_run_builds_and_validates_the_tables_of_every_zone_core_first(tmp_path, capsys):
    for zone_key in ["ES", "XX"]:
        save_raw_zone(tmp_path / "raw", zone_key, "2026-10-24", "2026-10-29")

    run(project_config(tmp_path, "2026-10-26", APPROVED))

    # Raw data runs to 28 October. The tables end with delivery day 26 October:
    # 24 + 25 + 24 hours, because the clocks go back on 25 October.
    solar = {}
    for zone_key in ["ES", "XX"]:
        hourly = pd.read_parquet(table_path(tmp_path / "processed", HOURLY, zone_key))
        quarter = pd.read_parquet(table_path(tmp_path / "processed", QUARTER_HOUR, zone_key))
        weather = pd.read_parquet(table_path(tmp_path / "processed", WEATHER_TABLE, zone_key))
        assert (len(hourly), len(quarter), len(weather)) == (73, 292, 73)
        assert hourly.index.max() == pd.Timestamp("2026-10-26 22:00", tz="UTC")
        solar[zone_key] = "solar_forecast" in hourly.columns
    assert solar == {"ES": True, "XX": False}
    printed = capsys.readouterr().out
    assert printed.index("ES     build") < printed.index("XX     build")
    assert "Validation passed." in printed


def test_run_exits_while_the_last_delivery_day_is_not_set(tmp_path):
    with pytest.raises(SystemExit) as stopped:
        run(project_config(tmp_path, None, APPROVED))

    assert "data.end" in str(stopped.value)
    assert not (tmp_path / "processed").exists()


def test_run_exits_with_an_error_when_a_built_table_has_a_gap_that_was_not_approved(tmp_path):
    save_raw_zone(tmp_path / "raw", "XX", "2026-10-24", "2026-10-29")
    save_raw_zone(tmp_path / "raw", "ES", "2026-10-24", "2026-10-29", load_rows_left_out=8)

    with pytest.raises(SystemExit) as stopped:
        run(project_config(tmp_path, "2026-10-26", APPROVED))

    assert "ES hourly: load_forecast: empty values 2, approved 0." in str(stopped.value)
    assert "ES quarter_hour: load_forecast: empty values 8, approved 0." in str(stopped.value)
