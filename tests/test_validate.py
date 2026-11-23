"""Tests for the validation of the processed tables.

They use small synthetic tables, a temporary folder and no network.
"""

from datetime import timedelta

import pandas as pd
import pytest
import yaml

from epf.config import Zone
from epf.data.clean import Period
from epf.data.market_time import hourly_index, quarter_hour_index
from epf.data.validate import (
    HOURLY,
    QUARTER_HOUR,
    WEATHER_TABLE,
    check_columns,
    check_day_lengths,
    check_empty_counts,
    check_index,
    check_no_timestamp_after,
    run,
    table_index,
    table_path,
    validate_processed,
    validate_table,
)

MARKET_TZ = "Europe/Berlin"
SWITCH = pd.Timestamp("2025-10-01", tz=MARKET_TZ)
HOUR = timedelta(hours=1)
ES = Zone("ES", "ES", "core", weather_point={"place": "Madrid", "latitude": 40.42, "longitude": -3.70})
NO_GAPS = {"price": 0, "load_forecast": 0}


def market_time(text: str) -> pd.Timestamp:
    """A timestamp in market time. A date alone means 00:00 on that day."""
    return pd.Timestamp(text, tz=MARKET_TZ)


def period(first_day: str, day_after_last: str) -> Period:
    """A data period [first_day, day_after_last) whose weather starts on the first day."""
    start = market_time(first_day)
    return Period(start, market_time(day_after_last), SWITCH, weather_start=start)


def table_on(index: pd.DatetimeIndex, columns: tuple[str, ...] = ("price", "load_forecast")) -> pd.DataFrame:
    """A table with the value 1.0 in every column and row."""
    return pd.DataFrame({column: 1.0 for column in columns}, index=index)


@pytest.mark.parametrize("day, next_day, hours", [
    ("2026-01-15", "2026-01-16", 24),
    ("2026-03-29", "2026-03-30", 23),    # clocks go forward
    ("2026-10-25", "2026-10-26", 25),    # clocks go back
    ("2025-10-01", "2025-10-02", 24),    # first 15-minute day
])
def test_validate_table_accepts_an_hourly_table_of_one_delivery_day(day, next_day, hours):
    table = table_on(hourly_index(market_time(day), market_time(next_day)))

    problems = validate_table(table, HOURLY, period(day, next_day), NO_GAPS)

    assert len(table) == hours
    assert problems == []


@pytest.mark.parametrize("day, next_day, quarter_hours", [
    ("2026-01-15", "2026-01-16", 96),
    ("2026-03-29", "2026-03-30", 92),
    ("2026-10-25", "2026-10-26", 100),
    ("2025-10-01", "2025-10-02", 96),
])
def test_validate_table_accepts_a_quarter_hour_table_of_one_delivery_day(day, next_day,
                                                                       quarter_hours):
    table = table_on(quarter_hour_index(market_time(day), market_time(next_day)))

    problems = validate_table(table, QUARTER_HOUR, period(day, next_day), NO_GAPS)

    assert len(table) == quarter_hours
    assert problems == []


def test_table_index_starts_the_quarter_hour_table_at_the_switch():
    index = table_index(QUARTER_HOUR, period("2025-09-29", "2025-10-02"))

    assert len(index) == 96
    assert index[0] == pd.Timestamp("2025-09-30 22:00", tz="UTC")


def test_table_index_starts_the_weather_table_at_the_first_weather_day():
    days = Period(market_time("2024-03-10"), market_time("2024-03-17"), SWITCH,
                  weather_start=market_time("2024-03-15"))

    assert len(table_index(HOURLY, days)) == 7 * 24
    assert len(table_index(WEATHER_TABLE, days)) == 2 * 24


def test_check_index_counts_missing_unexpected_and_repeated_timestamps():
    expected = hourly_index(market_time("2026-10-25"), market_time("2026-10-26"))
    late = pd.DatetimeIndex([expected[-1] + HOUR])
    index = expected[1:].append(late).append(late)

    problems = check_index(index, expected)

    assert len(problems) == 3
    assert any("missing: 1" in problem for problem in problems)
    assert any("unexpected: 1" in problem for problem in problems)
    assert any("repeated: 1" in problem for problem in problems)


def test_check_index_refuses_an_index_in_local_time():
    expected = hourly_index(market_time("2026-10-25"), market_time("2026-10-26"))

    problems = check_index(expected.tz_convert(MARKET_TZ), expected)

    assert problems == ["The index is not a time index in UTC."]


def test_check_day_lengths_names_a_day_with_a_missing_hour():
    start, end = market_time("2026-10-24"), market_time("2026-10-27")
    index = hourly_index(start, end).delete(30)

    problems = check_day_lengths(index, start, end, HOUR)

    assert len(problems) == 1
    assert "2026-10-25 has 24, expected 25" in problems[0]


def test_check_no_timestamp_after_flags_a_row_after_the_last_delivery_day():
    end = market_time("2026-11-20")
    index = hourly_index(market_time("2026-11-19"), market_time("2026-11-21"))

    problems = check_no_timestamp_after(index, end)

    assert len(problems) == 1
    assert "24" in problems[0]


def test_validate_table_reports_a_table_that_runs_past_the_last_delivery_day():
    table = table_on(hourly_index(market_time("2026-11-19"), market_time("2026-11-21")))

    problems = validate_table(table, HOURLY, period("2026-11-19", "2026-11-20"), NO_GAPS)

    assert any("after the last delivery day" in problem for problem in problems)


def test_check_columns_names_missing_and_unexpected_columns():
    table = table_on(hourly_index(market_time("2026-01-15"), market_time("2026-01-16")),
                     columns=("price", "solar_forecast"))

    problems = check_columns(table, ["price", "load_forecast"])

    assert len(problems) == 2
    assert any("load_forecast" in problem and "missing" in problem.lower() for problem in problems)
    assert any("solar_forecast" in problem and "unexpected" in problem.lower()
               for problem in problems)


def test_check_empty_counts_accepts_the_approved_gaps():
    table = table_on(hourly_index(market_time("2026-01-15"), market_time("2026-01-16")))
    table.iloc[3:5, 1] = float("nan")

    assert check_empty_counts(table, {"price": 0, "load_forecast": 2}) == []


def test_check_empty_counts_reports_a_gap_that_was_not_approved():
    table = table_on(hourly_index(market_time("2026-01-15"), market_time("2026-01-16")))
    table.iloc[3:5, 0] = float("nan")

    problems = check_empty_counts(table, NO_GAPS)

    assert problems == ["price: empty values 2, approved 0."]


def save_tables(processed_dir, zone_key: str, first_day: str, day_after_last: str) -> None:
    """Write a complete hourly, quarter-hour and weather table for one zone."""
    days = period(first_day, day_after_last)
    for name, columns in [(HOURLY, ("price", "load_forecast")),
                          (QUARTER_HOUR, ("price", "load_forecast")),
                          (WEATHER_TABLE, ("temperature_2m", "run"))]:
        path = table_path(processed_dir, name, zone_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        table_on(table_index(name, days), columns).to_parquet(path)


APPROVED = {"ES": {HOURLY: NO_GAPS, QUARTER_HOUR: NO_GAPS,
                   WEATHER_TABLE: {"temperature_2m": 0, "run": 0}}}


def test_validate_processed_passes_complete_tables(tmp_path):
    save_tables(tmp_path, "ES", "2026-10-24", "2026-10-27")

    summary, problems = validate_processed(tmp_path, [ES], period("2026-10-24", "2026-10-27"),
                                           APPROVED)

    assert problems == []
    assert summary["table"].tolist() == [HOURLY, QUARTER_HOUR, WEATHER_TABLE]
    assert summary["rows"].tolist() == [73, 292, 73]
    assert summary["empty_values"].tolist() == [0, 0, 0]


def test_validate_processed_reports_a_missing_file_and_a_zone_without_approved_gaps(tmp_path):
    save_tables(tmp_path, "ES", "2026-10-24", "2026-10-27")
    table_path(tmp_path, WEATHER_TABLE, "ES").unlink()
    france = Zone("FR", "FR", "core")

    _, problems = validate_processed(tmp_path, [ES, france], period("2026-10-24", "2026-10-27"),
                                     APPROVED)

    assert any(problem.startswith("ES weather:") and "no file" in problem for problem in problems)
    assert any(problem.startswith("FR hourly:") and "approved" in problem for problem in problems)


def test_validate_processed_expects_no_weather_table_without_a_weather_point(tmp_path):
    save_tables(tmp_path, "ES", "2026-10-24", "2026-10-27")
    table_path(tmp_path, WEATHER_TABLE, "ES").unlink()

    summary, problems = validate_processed(tmp_path, [Zone("ES", "ES", "core")],
                                           period("2026-10-24", "2026-10-27"), APPROVED)

    assert problems == []
    assert summary["table"].tolist() == [HOURLY, QUARTER_HOUR]


def project_config(tmp_path, approved: dict) -> dict:
    """A config for the days 24 to 26 October 2026 with its folders under tmp_path."""
    gaps_path = tmp_path / "approved_gaps.yaml"
    gaps_path.write_text(yaml.safe_dump(approved), encoding="utf-8")
    return {
        "market": {"timezone": MARKET_TZ, "quarter_hour_start": "2025-10-01"},
        "data": {"start": "2026-10-24", "end": "2026-10-26"},
        "open_meteo": {"first_run": "2024-03-14"},
        "paths": {"processed": str(tmp_path / "processed"), "approved_gaps": str(gaps_path)},
        "zones": [{"key": "ES", "holiday_country": "ES", "group": "core",
                   "weather_point": {"place": "Madrid", "latitude": 40.42, "longitude": -3.70}}],
    }


def test_run_passes_tables_that_match_the_approved_gaps(tmp_path, capsys):
    save_tables(tmp_path / "processed", "ES", "2026-10-24", "2026-10-27")

    run(project_config(tmp_path, APPROVED))

    assert "ES" in capsys.readouterr().out


def test_run_exits_with_an_error_when_a_table_has_a_gap_that_was_not_approved(tmp_path):
    save_tables(tmp_path / "processed", "ES", "2026-10-24", "2026-10-27")
    path = table_path(tmp_path / "processed", HOURLY, "ES")
    table = pd.read_parquet(path)
    table.iloc[10, 0] = float("nan")
    table.to_parquet(path)

    with pytest.raises(SystemExit) as stopped:
        run(project_config(tmp_path, APPROVED))

    assert "ES hourly: price: empty values 1, approved 0." in str(stopped.value)


def test_run_exits_with_an_error_when_the_approved_gaps_file_is_missing(tmp_path):
    config = project_config(tmp_path, APPROVED)
    config["paths"]["approved_gaps"] = str(tmp_path / "nowhere.yaml")

    with pytest.raises(SystemExit) as stopped:
        run(config)

    assert "nowhere.yaml" in str(stopped.value)
