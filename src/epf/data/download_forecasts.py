"""Download the day-ahead load forecast and the wind and solar forecast from ENTSO-E.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.data.download_forecasts

Zones, dates and folders come from config/config.yaml. Core zones run first.
Downloads go through the raw cache, so a finished year is read from disk. The
command prints counts per zone, dataset, year and column and changes no value.
The token is read from ENTSOE_API_TOKEN or the .env file and is never printed.
"""

import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

import pandas as pd
from entsoe import EntsoePandasClient

from epf.config import REPO_ROOT, Zone, load_config, ordered_zones
from epf.data.entsoe_api import (
    EntsoeNoDataError,
    EntsoeRequestError,
    MissingTokenError,
    call_entsoe,
    load_token,
)
from epf.data.entsoe_cache import cached_fetch
from epf.data.market_time import data_range, hourly_index, native_resolution, year_ranges

NO_DATA = "(no data)"
FrameFetch = Callable[[EntsoePandasClient, str, pd.Timestamp, pd.Timestamp], pd.DataFrame]
YearRange = tuple[int, pd.Timestamp, pd.Timestamp]


def fetch_load_forecast(client: EntsoePandasClient, zone_key: str,
                        start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Download the day-ahead load forecast of one zone for [start, end).

    Input: an entsoe-py client, the ENTSO-E area key of the zone, and a time
        zone aware start and end.
    Output: the client's columns with a UTC index. The end timestamp is left
        out. The frame is empty when ENTSO-E has no data.
    """
    return fetch_frame(client.query_load_forecast, zone_key, start, end)


def fetch_wind_solar_forecast(client: EntsoePandasClient, zone_key: str,
                              start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Download the day-ahead wind and solar forecast of one zone for [start, end).

    Input: an entsoe-py client, the ENTSO-E area key of the zone, and a time
        zone aware start and end.
    Output: one column per production type with a UTC index. The end timestamp
        is left out. The frame is empty when ENTSO-E has no data.
    """
    return fetch_frame(client.query_wind_and_solar_forecast, zone_key, start, end)


def hourly_coverage(data: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    """Return one coverage row per column: the share of hours in [start, end) with a value.

    Input: a forecast frame with a UTC index, start and end in market time.
    Output: an hour counts as present when it holds at least one value, so
        hourly and 15-minute series are measured the same way. An empty frame
        gives one row named "(no data)" with share 0.
    """
    expected = hourly_index(start, end)
    shared = {
        "resolution": native_resolution(data.index),
        "expected": len(expected),
        "days_with_gaps": None,
        "unexpected": None,
        "duplicates": int(data.index.duplicated().sum()),
    }
    if data.empty:
        return [{"column": NO_DATA, "present": 0, "share": 0.0, **shared}]
    hourly = data.resample("h").mean().reindex(expected)
    rows = []
    for column in hourly.columns:
        present = int(hourly[column].notna().sum())
        rows.append({"column": str(column), "present": present,
                     "share": present / len(expected), **shared})
    return rows


def download_datasets(client: EntsoePandasClient, fetchers: dict[str, FrameFetch],
                      zones: list[Zone], ranges: list[YearRange], cache_dir: Path) -> pd.DataFrame:
    """Download each dataset for every zone and year, or read it from the cache.

    Input: fetchers maps a dataset name to its fetch function. zones are in
        the order they should run. ranges are year pieces from year_ranges, in
        market time. cache_dir is the folder of the ENTSO-E cache.
    Output: one row per zone, dataset, year and column.
        rows            rows in the saved file
        resolution      most common step between its timestamps
        expected_hours  hours in the year piece
        missing_hours   hours in which the column has no value
        repeated        timestamps that repeat an earlier one
    """
    rows = []
    for zone in zones:
        for dataset, fetch in fetchers.items():
            for year, start, end in ranges:
                print(f"{zone.key:6s} {dataset:20s} {year}", flush=True)
                data = cached_fetch(partial(fetch, client, zone.key),
                                    cache_dir, dataset, zone.key, year, start, end)
                for found in hourly_coverage(data, start, end):
                    rows.append({
                        "zone": zone.key, "dataset": dataset, "year": year,
                        "column": found["column"], "rows": len(data),
                        "resolution": found["resolution"],
                        "expected_hours": found["expected"],
                        "missing_hours": found["expected"] - found["present"],
                        "repeated": found["duplicates"],
                    })
    return pd.DataFrame(rows)


def run_downloads(fetchers: dict[str, FrameFetch]) -> None:
    """Download the given datasets for all configured zones and print the counts.

    Input: fetchers maps a dataset name to its fetch function. Zones, dates
        and folders come from config/config.yaml. The data period ends at
        00:00 today in market time while data.end is not set.
    """
    config = load_config()
    market_tz = config["market"]["timezone"]
    today = pd.Timestamp.now(tz=market_tz).normalize()
    start, end = data_range(config, today)
    cache_dir = REPO_ROOT / config["paths"]["raw"] / "entsoe"

    try:
        token = load_token()
    except MissingTokenError as error:
        sys.exit(str(error))
    client = EntsoePandasClient(api_key=token, timeout=config["entsoe"]["timeout_seconds"])
    try:
        summary = download_datasets(client, fetchers, ordered_zones(config),
                                    year_ranges(start, end), cache_dir)
    except EntsoeRequestError as error:
        sys.exit(f"{error} HTTP status 401 means the token was rejected. "
                 "Finished years are saved, so run the command again to resume.")
    print(summary.to_string(index=False))


def main() -> None:
    """Download the load forecast and the wind and solar forecast of all configured zones."""
    run_downloads({"load_forecast": fetch_load_forecast,
                   "wind_solar_forecast": fetch_wind_solar_forecast})


def fetch_frame(query: Callable[..., pd.DataFrame], zone_key: str,
                start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Run one entsoe-py frame query and return it in UTC, cut to [start, end).

    Input: a client method that takes a zone key, start and end and returns a
        frame. start and end are time zone aware.
    Output: the client's columns with a UTC index. The end timestamp is left
        out. The frame is empty when ENTSO-E has no data.
    """
    try:
        data = call_entsoe(query, zone_key, start=start, end=end)
    except EntsoeNoDataError:
        return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"))
    data = data.tz_convert("UTC")
    return data[(data.index >= start) & (data.index < end)]


if __name__ == "__main__":
    main()
