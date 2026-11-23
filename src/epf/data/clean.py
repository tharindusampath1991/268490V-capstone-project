"""Clean the raw downloads: check them, cut them to the data period, name the columns.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.data.clean

The command reads the raw cache, prints per zone and dataset how many values
each rule removed, and writes nothing. build_dataset uses the same functions.

The rules (docs/DATA_NOTES.md, "Preprocessing"):
    index     UTC, sorted, each timestamp once. A file that fails is refused.
    period    values outside [data.start, DATA_END] are removed.
    grid      a value at a time that is not on the time grid is refused.
    prices    exactly one price per market time unit, or the zone is refused.
    columns   a forecast column listed under coverage_gate.drop_columns is
              left out. The other columns get the names in ENTSOE_NAMES.
    gaps      an empty or missing value stays as it is. Nothing is filled.

All times are UTC. The period is defined in market time.
"""

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from epf.config import REPO_ROOT, Zone, load_config, ordered_zones
from epf.data.download_weather import DATASET as WEATHER
from epf.data.download_weather import RUN_COLUMN
from epf.data.entsoe_cache import read_saved
from epf.data.market_time import (
    data_range,
    expected_price_index,
    hourly_index,
    quarter_hour_index,
    year_ranges,
)
from epf.data.resolution import check_utc_index

ENTSOE_FOLDER = "entsoe"
WEATHER_FOLDER = "open_meteo"
PRICES = "prices"
COVARIATES = ("load_forecast", "wind_solar_forecast", "actual_load")

# Raw ENTSO-E column name to the name in the processed tables.
ENTSOE_NAMES = {
    "price": "price",
    "Forecasted Load": "load_forecast",
    "Wind Onshore": "wind_onshore_forecast",
    "Wind Offshore": "wind_offshore_forecast",
    "Solar": "solar_forecast",
    "Actual Load": "actual_load",
}


class CleaningError(ValueError):
    """Raw data breaks a cleaning rule. The message names the rule and the count."""


@dataclass(frozen=True)
class Period:
    """The frozen data period. Every field is 00:00 of a day in market time."""

    start: pd.Timestamp               # first delivery day
    end: pd.Timestamp                 # the day after the last delivery day
    quarter_hour_start: pd.Timestamp  # first delivery day with 15-minute prices
    weather_start: pd.Timestamp       # first delivery day with a weather forecast


def frozen_period(config: dict) -> Period:
    """Return the data period of the config.

    Input: the config dictionary.
    Output: the period in market time. The weather starts on the day after
        the first archived model run, or on data.start when that is later.
    Raises ValueError when data.end is not set.
    """
    if config["data"]["end"] is None:
        raise ValueError("data.end is not set in the config. Freeze DATA_END first.")
    market_tz = config["market"]["timezone"]
    start, end = data_range(config, today=None)
    first_weather_day = date.fromisoformat(config["open_meteo"]["first_run"]) + timedelta(days=1)
    return Period(
        start=start,
        end=end,
        quarter_hour_start=pd.Timestamp(config["market"]["quarter_hour_start"], tz=market_tz),
        weather_start=max(start, pd.Timestamp(first_weather_day, tz=market_tz)),
    )


def dropped_columns(config: dict, zone_key: str) -> list[str]:
    """Return the raw forecast columns that are left out for one zone."""
    marks = config["coverage_gate"].get("drop_columns", [])
    return [mark["column"] for mark in marks if mark["zone"] == zone_key]


def weather_names(config: dict) -> dict[str, str]:
    """Return the weather columns to keep, each under its own name."""
    return {name: name for name in [*config["open_meteo"]["variables"], RUN_COLUMN]}


def read_raw(cache_dir: Path, dataset: str, zone_key: str,
             start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Return the saved downloads of one dataset and zone that cover [start, end).

    Input: the folder of a raw cache, and start and end in market time.
    Output: the yearly files joined in time order, with a UTC index.
    Raises FileNotFoundError when a year is not in the cache, and
        CleaningError when a saved file was downloaded for a shorter period.
    """
    frames = []
    for year, piece_start, piece_end in year_ranges(start, end):
        frame, query_start, query_end = read_saved(cache_dir, dataset, zone_key, year)
        if query_start > piece_start or query_end < piece_end:
            raise CleaningError(f"{zone_key} {dataset} {year}: the saved file does not cover "
                                "the data period. Run the download command to download it again.")
        frames.append(frame)
    return pd.concat(frames)


def clean_frame(raw: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                grid: pd.DatetimeIndex, names: dict[str, str],
                dropped: Sequence[str] = ()) -> tuple[pd.DataFrame, dict]:
    """Apply the index, period, grid and column rules to one raw dataset.

    Input: a raw frame with a UTC index, the period [start, end), the UTC
        times at which a value may stand, the raw column names with their new
        names, and the raw columns to leave out.
    Output: the cleaned frame, then counts of values that are not empty:
        raw_values       in the raw frame
        outside_period   removed because they lie outside [start, end)
        dropped_columns  removed with a column that is left out
        kept_values      in the cleaned frame
    Raises CleaningError when the index is not UTC, sorted and free of
        repeats, when a timestamp is not on the grid, or when a column has no
        name in names.
    """
    try:
        check_utc_index(raw)
    except ValueError as error:
        raise CleaningError(str(error)) from None
    inside = raw[(raw.index >= start) & (raw.index < end)]
    off_grid = inside.index.difference(grid)
    if len(off_grid):
        raise CleaningError(f"Timestamps off the expected time grid: {len(off_grid)}.")
    unknown = [column for column in inside.columns if column not in names]
    if unknown:
        raise CleaningError(f"Columns without a name in the cleaning step: {unknown}.")

    kept = inside.drop(columns=[column for column in dropped if column in inside.columns])
    counts = {
        "raw_values": _values(raw),
        "outside_period": _values(raw) - _values(inside),
        "dropped_columns": _values(inside) - _values(kept),
        "kept_values": _values(kept),
    }
    return kept.rename(columns=names), counts


def require_complete(prices: pd.Series, grid: pd.DatetimeIndex) -> None:
    """Refuse prices that do not have a value for every market time unit.

    Input: cleaned prices with a UTC index, and the market time units of the period.
    Raises CleaningError with the number of market time units without a price.
    """
    missing = grid.difference(prices.dropna().index)
    if len(missing):
        raise CleaningError(f"Market time units without a price: {len(missing)}.")


def clean_zone(raw_dir: Path, zone: Zone, period: Period, dropped: list[str],
               weather_columns: dict[str, str]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Clean the five raw datasets of one zone.

    Input: the folder that holds the raw caches, the zone, the data period,
        the raw forecast columns to leave out and the weather columns to keep.
    Output: the cleaned frames by dataset name, then one row of counts per
        dataset (see clean_frame). A zone without a weather point has no
        weather dataset.
    Raises CleaningError, with the zone and dataset in front of the message.
    """
    price_grid = expected_price_index(period.start, period.end, period.quarter_hour_start)
    covariate_grid = quarter_hour_index(period.start, period.end)
    plan = [(PRICES, ENTSOE_FOLDER, period.start, price_grid, ENTSOE_NAMES)]
    plan += [(dataset, ENTSOE_FOLDER, period.start, covariate_grid, ENTSOE_NAMES)
             for dataset in COVARIATES]
    if zone.weather_point is not None:
        plan.append((WEATHER, WEATHER_FOLDER, period.weather_start,
                     hourly_index(period.weather_start, period.end), weather_columns))

    cleaned, rows = {}, []
    for dataset, folder, start, grid, names in plan:
        try:
            raw = read_raw(raw_dir / folder, dataset, zone.key, start, period.end)
            frame, counts = clean_frame(raw, start, period.end, grid, names, dropped)
            if dataset == PRICES:
                require_complete(frame["price"], grid)
        except CleaningError as error:
            raise CleaningError(f"{zone.key} {dataset}: {error}") from None
        cleaned[dataset] = frame
        rows.append({"zone": zone.key, "dataset": dataset, **counts})
    return cleaned, pd.DataFrame(rows)


def main() -> None:
    """Clean the raw data of all configured zones and print the counts per rule."""
    config = load_config()
    try:
        period = frozen_period(config)
    except ValueError as error:
        sys.exit(str(error))
    raw_dir = REPO_ROOT / config["paths"]["raw"]

    tables = []
    for zone in ordered_zones(config):
        print(f"{zone.key:6s} clean", flush=True)
        try:
            _, counts = clean_zone(raw_dir, zone, period, dropped_columns(config, zone.key),
                                   weather_names(config))
        except (CleaningError, FileNotFoundError) as error:
            sys.exit(str(error))
        tables.append(counts)
    print(pd.concat(tables).to_string(index=False))


def _values(data: pd.DataFrame) -> int:
    """Return the number of values in a frame that are not empty."""
    return int(data.notna().to_numpy().sum())


if __name__ == "__main__":
    main()
