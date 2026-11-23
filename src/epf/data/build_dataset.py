"""Build the modelling tables from the raw cache, then validate them.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.data.build_dataset

For every configured zone, core zones first, the command cleans the raw
downloads (epf.data.clean) and writes three Parquet tables under
paths.processed:
    hourly/{ZONE}.parquet        experiment H. One row per hour from data.start.
                                 From the first 15-minute delivery day the price
                                 is the mean of the four quarter-hour prices.
    quarter_hour/{ZONE}.parquet  experiment Q. One row per quarter-hour from the
                                 first 15-minute delivery day.
    weather/{ZONE}.parquet       one row per hour from the first delivery day
                                 with a weather forecast, with the run time.
Every table ends with the last delivery day, data.end, and has a row for
every time step, also where a value is empty. It then runs the checks of
epf.data.validate and ends with an error when one fails.

The index is in UTC. The load, wind and solar columns are in MW, at the
time they apply to. actual_load is not shifted: a forecast for delivery day
D may use it through day D-2 only, and the feature builder applies that cut.
"""

import sys
from pathlib import Path

import pandas as pd

from epf.config import REPO_ROOT, load_config, ordered_zones
from epf.data.clean import (
    COVARIATES,
    ENTSOE_NAMES,
    PRICES,
    WEATHER,
    CleaningError,
    Period,
    clean_zone,
    dropped_columns,
    frozen_period,
    weather_names,
)
from epf.data.resolution import (
    align_to_hours,
    align_to_quarter_hours,
    hourly_prices,
    quarter_hour_prices,
)
from epf.data.validate import (
    HOURLY,
    QUARTER_HOUR,
    WEATHER_TABLE,
    load_approved_gaps,
    report,
    table_index,
    table_path,
    table_start,
    validate_processed,
)

COLUMN_ORDER = list(ENTSOE_NAMES.values())


def build_hourly(cleaned: dict[str, pd.DataFrame], period: Period) -> pd.DataFrame:
    """Return the experiment H table of one zone.

    Input: the cleaned frames from clean_zone and the data period.
    Output: one row per UTC hour of the period. The price comes from
        hourly_prices and the other columns from align_to_hours. An hour
        without data has a row with empty values.
    """
    grid = table_index(HOURLY, period)
    price = hourly_prices(cleaned[PRICES]["price"], period.quarter_hour_start)
    parts = [price] + [align_to_hours(cleaned[dataset]) for dataset in COVARIATES]
    return _join_on_grid(parts, grid)


def build_quarter_hour(cleaned: dict[str, pd.DataFrame], period: Period) -> pd.DataFrame:
    """Return the experiment Q table of one zone.

    Input: the cleaned frames from clean_zone and the data period.
    Output: one row per UTC quarter-hour from the first 15-minute delivery
        day. The price comes from quarter_hour_prices and the other columns
        from align_to_quarter_hours, which repeats an hourly value on its
        four quarter-hours.
    """
    grid = table_index(QUARTER_HOUR, period)
    start = table_start(QUARTER_HOUR, period)
    price = quarter_hour_prices(cleaned[PRICES]["price"], period.quarter_hour_start)
    parts = [price] + [align_to_quarter_hours(cleaned[dataset][cleaned[dataset].index >= start])
                       for dataset in COVARIATES]
    return _join_on_grid(parts, grid)


def build_weather(cleaned: dict[str, pd.DataFrame], period: Period) -> pd.DataFrame:
    """Return the weather table of one zone.

    Input: the cleaned frames from clean_zone and the data period.
    Output: one row per UTC hour from the first delivery day with a weather
        forecast. The values are as downloaded, with the run time of the
        model run in the column run.
    """
    return cleaned[WEATHER].reindex(table_index(WEATHER_TABLE, period))


def build_tables(cleaned: dict[str, pd.DataFrame], period: Period) -> dict[str, pd.DataFrame]:
    """Return the tables of one zone by table name. No weather table without weather data."""
    tables = {HOURLY: build_hourly(cleaned, period),
              QUARTER_HOUR: build_quarter_hour(cleaned, period)}
    if WEATHER in cleaned:
        tables[WEATHER_TABLE] = build_weather(cleaned, period)
    return tables


def write_tables(tables: dict[str, pd.DataFrame], processed_dir: Path, zone_key: str) -> None:
    """Write the tables of one zone as Parquet files, replacing earlier ones."""
    for name, table in tables.items():
        path = table_path(processed_dir, name, zone_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(path)


def run(config: dict) -> None:
    """Build and validate the tables of every zone named by a config.

    Input: the config dictionary.
    Output: nothing. Prints the cleaning counts and the validation summary.
        Ends with an error message when data.end is not set, a raw file is
        missing, a cleaning rule is broken or a validation check fails.
    """
    try:
        period = frozen_period(config)
        approved = load_approved_gaps(REPO_ROOT / config["paths"]["approved_gaps"])
    except (ValueError, FileNotFoundError) as error:
        sys.exit(str(error))
    raw_dir = REPO_ROOT / config["paths"]["raw"]
    processed_dir = REPO_ROOT / config["paths"]["processed"]
    zones = ordered_zones(config)

    counts = []
    for zone in zones:
        print(f"{zone.key:6s} build", flush=True)
        try:
            cleaned, zone_counts = clean_zone(raw_dir, zone, period,
                                              dropped_columns(config, zone.key),
                                              weather_names(config))
        except (CleaningError, FileNotFoundError) as error:
            sys.exit(str(error))
        write_tables(build_tables(cleaned, period), processed_dir, zone.key)
        counts.append(zone_counts)
    print(pd.concat(counts).to_string(index=False))
    report(*validate_processed(processed_dir, zones, period, approved))


def main() -> None:
    """Build and validate the tables of the project config."""
    run(load_config())


def _join_on_grid(parts: list[pd.Series | pd.DataFrame], grid: pd.DatetimeIndex) -> pd.DataFrame:
    """Put the parts side by side on one time grid, with the columns in COLUMN_ORDER."""
    table = pd.concat([part.reindex(grid) for part in parts], axis=1)
    return table[[column for column in COLUMN_ORDER if column in table.columns]]


if __name__ == "__main__":
    main()
