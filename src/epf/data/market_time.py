"""Market time helpers: which market time units exist in a period.

A delivery day runs from 00:00 to 24:00 in the market time zone. Results are
in UTC, where a clock-change day is simply 23 or 25 hours long.
"""

from datetime import date, timedelta

import pandas as pd


def data_range(config: dict, today: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the configured data period as [start, end) in market time.

    Input: the config dictionary, and 00:00 of today in market time.
    Output: start is 00:00 on data.start. end is 00:00 on the day after
        data.end, so data.end is the last delivery day included. While
        data.end is not set, end is today.
    """
    market_tz = config["market"]["timezone"]
    start = pd.Timestamp(config["data"]["start"], tz=market_tz)
    last_day = config["data"]["end"]
    if last_day is None:
        return start, today
    next_day = date.fromisoformat(last_day) + timedelta(days=1)
    return start, pd.Timestamp(next_day, tz=market_tz)


def year_ranges(start: pd.Timestamp,
                end: pd.Timestamp) -> list[tuple[int, pd.Timestamp, pd.Timestamp]]:
    """Split [start, end) into one piece per calendar year.

    Input: start and end in market time.
    Output: tuples of (year, piece start, piece end). Years begin at 00:00
        on 1 January in the time zone of start.
    """
    ranges = []
    for year in range(start.year, end.year + 1):
        piece_start = max(start, pd.Timestamp(f"{year}-01-01", tz=start.tz))
        piece_end = min(end, pd.Timestamp(f"{year + 1}-01-01", tz=start.tz))
        if piece_start < piece_end:
            ranges.append((year, piece_start, piece_end))
    return ranges


def expected_price_index(start: pd.Timestamp, end: pd.Timestamp,
                         quarter_hour_start: pd.Timestamp) -> pd.DatetimeIndex:
    """Return every market time unit in [start, end).

    Input: start and end are time zone aware. quarter_hour_start is 00:00 in
        market time on the first delivery day with 15-minute prices.
    Output: a UTC index. Hourly steps before quarter_hour_start, 15-minute
        steps from it.
    """
    switch = min(max(quarter_hour_start, start), end)
    start_utc, switch_utc, end_utc = (moment.tz_convert("UTC") for moment in (start, switch, end))
    return _steps(start_utc, switch_utc, "h").append(_steps(switch_utc, end_utc, "15min"))


def hourly_index(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Return every hour in [start, end) as a UTC index.

    Input: start and end are time zone aware.
    """
    return _steps(start.tz_convert("UTC"), end.tz_convert("UTC"), "h")


def quarter_hour_index(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Return every quarter-hour in [start, end) as a UTC index.

    Input: start and end are time zone aware.
    """
    return _steps(start.tz_convert("UTC"), end.tz_convert("UTC"), "15min")


def native_resolution(index: pd.DatetimeIndex) -> str:
    """Return the most common step between timestamps, for example "15min".

    Output: "-" when the index has fewer than two timestamps.
    """
    if len(index) < 2:
        return "-"
    step = index.to_series().diff().mode().iloc[0]
    return f"{int(step.total_seconds() // 60)}min"


def _steps(start: pd.Timestamp, end: pd.Timestamp, freq: str) -> pd.DatetimeIndex:
    """Return the time steps in [start, end). Empty when start equals end."""
    index = pd.date_range(start, end, freq=freq)
    return index[index < end]
