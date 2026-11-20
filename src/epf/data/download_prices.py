"""Download day-ahead prices from ENTSO-E into the raw cache.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.data.download_prices

Zones, dates and folders come from config/config.yaml. Core zones run first.
The token is read from ENTSOE_API_TOKEN or the .env file and is never printed.
"""

import sys
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
from epf.data.market_time import data_range, expected_price_index, year_ranges

YearRange = tuple[int, pd.Timestamp, pd.Timestamp]


def fetch_prices(client: EntsoePandasClient, zone_key: str,
                 start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Download the day-ahead prices of one zone for [start, end).

    Input: an entsoe-py client, the ENTSO-E area key of the zone, and a time
        zone aware start and end.
    Output: one column "price" with a UTC index. The end timestamp is left
        out. The frame is empty when ENTSO-E has no data.
    """
    try:
        series = call_entsoe(client.query_day_ahead_prices, zone_key, start=start, end=end)
    except EntsoeNoDataError:
        return pd.DataFrame(columns=["price"], index=pd.DatetimeIndex([], tz="UTC"), dtype="float64")
    data = series.to_frame("price").tz_convert("UTC")
    return data[(data.index >= start) & (data.index < end)]


def check_prices(data: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                 quarter_hour_start: pd.Timestamp) -> dict:
    """Compare downloaded prices with the market time units of [start, end).

    Input: a frame from fetch_prices, start and end in market time, and the
        first 15-minute delivery day.
    Output: counts.
        expected        market time units in the period
        missing         market time units with no price
        days_with_gaps  delivery days, in the time zone of start, with a missing price
        unexpected      prices at a time that is not a market time unit
        duplicates      timestamps that repeat an earlier one
    """
    expected = expected_price_index(start, end, quarter_hour_start)
    priced = data.index[data["price"].notna().to_numpy()]
    missing = expected.difference(priced)
    gap_days = missing.tz_convert(start.tz).normalize().unique()
    return {
        "expected": len(expected),
        "missing": len(missing),
        "days_with_gaps": len(gap_days),
        "unexpected": len(priced.difference(expected)),
        "duplicates": int(data.index.duplicated().sum()),
    }


def download_prices(client: EntsoePandasClient, zones: list[Zone], ranges: list[YearRange],
                    cache_dir: Path, quarter_hour_start: pd.Timestamp) -> pd.DataFrame:
    """Download the prices of every zone and year, or read them from the cache.

    Input: zones in the order they should run, year pieces from year_ranges,
        the folder of the ENTSO-E cache and the first 15-minute delivery day.
    Output: one row per zone and year with the row count and the counts
        from check_prices.
    """
    rows = []
    for zone in zones:
        for year, start, end in ranges:
            print(f"{zone.key:6s} prices {year}", flush=True)
            data = cached_fetch(partial(fetch_prices, client, zone.key),
                                cache_dir, "prices", zone.key, year, start, end)
            counts = check_prices(data, start, end, quarter_hour_start)
            rows.append({"zone": zone.key, "year": year, "rows": len(data), **counts})
    return pd.DataFrame(rows)


def main() -> None:
    """Download the prices of all configured zones and print the check counts."""
    config = load_config()
    market_tz = config["market"]["timezone"]
    today = pd.Timestamp.now(tz=market_tz).normalize()
    start, end = data_range(config, today)
    quarter_hour_start = pd.Timestamp(config["market"]["quarter_hour_start"], tz=market_tz)
    cache_dir = REPO_ROOT / config["paths"]["raw"] / "entsoe"

    try:
        token = load_token()
    except MissingTokenError as error:
        sys.exit(str(error))
    client = EntsoePandasClient(api_key=token, timeout=config["entsoe"]["timeout_seconds"])
    try:
        summary = download_prices(client, ordered_zones(config), year_ranges(start, end),
                                  cache_dir, quarter_hour_start)
    except EntsoeRequestError as error:
        sys.exit(f"{error} HTTP status 401 means the token was rejected. "
                 "Finished years are saved, so run the command again to resume.")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
