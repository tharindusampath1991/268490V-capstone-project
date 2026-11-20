"""Download the day-ahead load forecast and the wind and solar forecast from ENTSO-E."""

from collections.abc import Callable

import pandas as pd
from entsoe import EntsoePandasClient

from epf.data.entsoe_api import EntsoeNoDataError, call_entsoe


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


def _fetch_frame(query: Callable[..., pd.DataFrame], zone_key: str,
                 start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Run one entsoe-py frame query and return it in UTC, cut to [start, end)."""
    try:
        data = call_entsoe(query, zone_key, start=start, end=end)
    except EntsoeNoDataError:
        return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"))
    data = data.tz_convert("UTC")
    return data[(data.index >= start) & (data.index < end)]
