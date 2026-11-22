"""Download the day-ahead load forecast and the wind and solar forecast from ENTSO-E."""

from collections.abc import Callable

import pandas as pd
from entsoe import EntsoePandasClient

from epf.data.entsoe_api import EntsoeNoDataError, call_entsoe
from epf.data.market_time import hourly_index, native_resolution

NO_DATA = "(no data)"


def fetch_load_forecast(client: EntsoePandasClient, zone_key: str,
                        start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Download the day-ahead load forecast of one zone for [start, end).

    Input: an entsoe-py client, the ENTSO-E area key of the zone, and a time
        zone aware start and end.
    Output: the client's columns with a UTC index. The end timestamp is left
        out. The frame is empty when ENTSO-E has no data.
    """
    return _fetch_frame(client.query_load_forecast, zone_key, start, end)


def fetch_wind_solar_forecast(client: EntsoePandasClient, zone_key: str,
                              start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Download the day-ahead wind and solar forecast of one zone for [start, end).

    Input: an entsoe-py client, the ENTSO-E area key of the zone, and a time
        zone aware start and end.
    Output: one column per production type with a UTC index. The end timestamp
        is left out. The frame is empty when ENTSO-E has no data.
    """
    return _fetch_frame(client.query_wind_and_solar_forecast, zone_key, start, end)


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


def _fetch_frame(query: Callable[..., pd.DataFrame], zone_key: str,
                 start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Run one entsoe-py frame query and return it in UTC, cut to [start, end)."""
    try:
        data = call_entsoe(query, zone_key, start=start, end=end)
    except EntsoeNoDataError:
        return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"))
    data = data.tz_convert("UTC")
    return data[(data.index >= start) & (data.index < end)]
