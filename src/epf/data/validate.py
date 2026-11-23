"""Validate the processed tables against the data period and the approved gaps.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.data.validate

For every zone and table the command checks:
    index     exactly the time steps of the period, in UTC, each once
    days      every delivery day has 24, 23 or 25 hours (96, 92 or 100
              quarter-hours), as its date requires
    end       no timestamp after the last delivery day
    columns   the columns approved for the zone, no more and no fewer
    gaps      per column as many empty values as were approved, no more and
              no fewer

The approved columns and gaps are read from the file named in
paths.approved_gaps. A failed check ends the command with an error.
All times are UTC. Delivery days are defined in market time.
"""

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import yaml

from epf.config import REPO_ROOT, Zone, load_config, ordered_zones
from epf.data.clean import Period, frozen_period
from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.data.resolution import QUARTER_HOUR as QUARTER_HOUR_STEP

HOURLY = "hourly"              # experiment H
QUARTER_HOUR = "quarter_hour"  # experiment Q
WEATHER_TABLE = "weather"
HOUR = timedelta(hours=1)
STEP = {HOURLY: HOUR, QUARTER_HOUR: QUARTER_HOUR_STEP, WEATHER_TABLE: HOUR}
ALLOWED_DAY_HOURS = (23, 24, 25)
NOT_UTC = "The index is not a time index in UTC."


def table_path(processed_dir: Path, table_name: str, zone_key: str) -> Path:
    """Return the Parquet file of one processed table."""
    return processed_dir / table_name / f"{zone_key}.parquet"


def table_start(table_name: str, period: Period) -> pd.Timestamp:
    """Return 00:00 in market time on the first delivery day of a table."""
    starts = {HOURLY: period.start,
              QUARTER_HOUR: max(period.start, period.quarter_hour_start),
              WEATHER_TABLE: period.weather_start}
    return min(starts[table_name], period.end)


def table_index(table_name: str, period: Period) -> pd.DatetimeIndex:
    """Return every time step a table must have, as a UTC index."""
    start = table_start(table_name, period)
    if table_name == QUARTER_HOUR:
        return quarter_hour_index(start, period.end)
    return hourly_index(start, period.end)


def check_index(index: pd.Index, expected: pd.DatetimeIndex) -> list[str]:
    """Compare the index of a table with the time steps it must have.

    Output: one message per kind of difference. Empty when the index is in
        UTC and holds each expected time step once and nothing else.
    """
    if not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC":
        return [NOT_UTC]
    counts = {
        "missing": len(expected.difference(index)),
        "unexpected": len(index.difference(expected)),
        "repeated": int(index.duplicated().sum()),
    }
    problems = [f"Time steps {kind}: {count}." for kind, count in counts.items() if count]
    if not index.is_monotonic_increasing:
        problems.append("The index is not sorted from old to new.")
    return problems


def check_day_lengths(index: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp,
                      step: timedelta) -> list[str]:
    """Check that every delivery day in [start, end) has the time steps of its date.

    Input: a UTC index, start and end at 00:00 in market time, and the step
        of the table.
    Output: at most one message, with the number of wrong days and the first
        of them. A delivery day is 24 hours long, or 23 or 25 on a
        clock-change day.
    """
    found = pd.Series(1, index=index.tz_convert(start.tz).normalize()).groupby(level=0).sum()
    wrong = []
    for day_start, next_day_start in delivery_days(start, end):
        hours = (next_day_start - day_start) // HOUR
        expected = (next_day_start - day_start) // step
        count = int(found.get(day_start, 0))
        if count != expected or hours not in ALLOWED_DAY_HOURS:
            wrong.append(f"{day_start.date()} has {count}, expected {expected}")
    if not wrong:
        return []
    return [f"Delivery days with a wrong number of time steps: {len(wrong)}. First: {wrong[0]}."]


def check_no_timestamp_after(index: pd.DatetimeIndex, end: pd.Timestamp) -> list[str]:
    """Check that no time step lies at or after end, the day after the last delivery day."""
    late = int((index >= end).sum())
    return [f"Time steps after the last delivery day: {late}."] if late else []


def check_columns(table: pd.DataFrame, expected: list[str]) -> list[str]:
    """Compare the columns of a table with the approved columns."""
    missing = [column for column in expected if column not in table.columns]
    unexpected = [column for column in table.columns if column not in expected]
    problems = []
    if missing:
        problems.append(f"Missing columns: {missing}.")
    if unexpected:
        problems.append(f"Unexpected columns: {unexpected}.")
    return problems


def check_empty_counts(table: pd.DataFrame, approved: dict[str, int]) -> list[str]:
    """Compare the empty values per column with the approved number.

    Input: a table, and the approved number of empty values per column.
    Output: one message per column whose count differs. A column that is
        not in the table is left to check_columns.
    """
    problems = []
    for column, allowed in approved.items():
        if column in table.columns:
            found = int(table[column].isna().sum())
            if found != allowed:
                problems.append(f"{column}: empty values {found}, approved {allowed}.")
    return problems


def validate_table(table: pd.DataFrame, table_name: str, period: Period,
                   approved: dict[str, int]) -> list[str]:
    """Run every check on one processed table.

    Input: the table, its name (HOURLY, QUARTER_HOUR or WEATHER_TABLE), the
        data period and the approved number of empty values per column.
    Output: the messages of all failed checks. Empty when the table passes.
    """
    problems = check_index(table.index, table_index(table_name, period))
    if problems == [NOT_UTC]:
        return problems
    problems += check_day_lengths(table.index, table_start(table_name, period), period.end,
                                  STEP[table_name])
    problems += check_no_timestamp_after(table.index, period.end)
    problems += check_columns(table, list(approved))
    problems += check_empty_counts(table, approved)
    return problems


def validate_processed(processed_dir: Path, zones: list[Zone], period: Period,
                       approved: dict) -> tuple[pd.DataFrame, list[str]]:
    """Validate the saved tables of every zone.

    Input: the folder of the processed tables, the zones in the order they
        should run, the data period, and the approved gaps as
        {zone: {table: {column: empty values}}}.
    Output: one summary row per zone and table, then the messages of all
        failed checks with the zone and table in front. A zone without a
        weather point has no weather table.
    """
    rows, problems = [], []
    for zone in zones:
        names = [HOURLY, QUARTER_HOUR] + ([WEATHER_TABLE] if zone.weather_point else [])
        for name in names:
            path = table_path(processed_dir, name, zone.key)
            columns = approved.get(zone.key, {}).get(name)
            if columns is None:
                problems.append(f"{zone.key} {name}: no approved columns and gaps.")
                continue
            if not path.exists():
                problems.append(f"{zone.key} {name}: no file at {path}.")
                continue
            table = pd.read_parquet(path)
            found = validate_table(table, name, period, columns)
            problems += [f"{zone.key} {name}: {problem}" for problem in found]
            rows.append({"zone": zone.key, "table": name, "rows": len(table),
                         "columns": len(table.columns),
                         "empty_values": int(table.isna().to_numpy().sum()),
                         "failed_checks": len(found)})
    return pd.DataFrame(rows), problems


def load_approved_gaps(path: Path) -> dict:
    """Read the approved columns and gaps as {zone: {table: {column: empty values}}}.

    Raises FileNotFoundError when the file does not exist.
    """
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def run(config: dict) -> None:
    """Validate the processed tables named by a config and print the summary.

    Input: the config dictionary.
    Output: nothing. Ends with an error message when data.end is not set,
        the approved gaps file is missing or a check fails.
    """
    try:
        period = frozen_period(config)
        approved = load_approved_gaps(REPO_ROOT / config["paths"]["approved_gaps"])
    except (ValueError, FileNotFoundError) as error:
        sys.exit(str(error))
    summary, problems = validate_processed(REPO_ROOT / config["paths"]["processed"],
                                           ordered_zones(config), period, approved)
    if not summary.empty:
        print(summary.to_string(index=False))
    if problems:
        sys.exit("Validation failed:\n" + "\n".join(problems))
    print("Validation passed.")


def main() -> None:
    """Validate the processed tables of the project config."""
    run(load_config())


if __name__ == "__main__":
    main()
