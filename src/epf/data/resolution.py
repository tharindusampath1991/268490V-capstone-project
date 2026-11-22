"""Time resolution handling: the index check, the price split and the covariate alignment.

All series are in UTC. In UTC every hour holds four quarter-hours, also on a
clock-change day, which is simply 23 or 25 hours long. No function here fills
a gap or writes a file.
"""

import pandas as pd

QUARTERS_PER_HOUR = 4


def check_utc_index(data: pd.Series | pd.DataFrame) -> None:
    """Refuse data whose time index is not ready for the functions in this module.

    Input: a series or frame as stored in the raw cache.
    Output: nothing. The data is not changed and nothing is repaired.
    Raises ValueError when the index is not a time index in UTC, is not sorted
        from old to new, or holds a timestamp more than once.
    """
    index = data.index
    if not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC":
        raise ValueError("The index must be a time zone aware time index in UTC.")
    if not index.is_monotonic_increasing:
        raise ValueError("The index must be sorted from old to new.")
    repeats = int(index.duplicated().sum())
    if repeats:
        raise ValueError(f"The index must hold each timestamp once. It has {repeats} repeated.")


def hourly_prices(prices: pd.Series, quarter_hour_start: pd.Timestamp) -> pd.Series:
    """Return the hourly price series of experiment H.

    Input: raw prices with a UTC index, hourly before quarter_hour_start and
        15-minute from it. quarter_hour_start is 00:00 in market time on the
        first delivery day with 15-minute prices.
    Output: one value per UTC hour that has a price row. Before the switch it
        is the hourly price, unchanged. From the switch it is the mean of the
        four quarter-hour prices of the hour. An hour with fewer than four
        quarter-hour prices is empty.
    Raises ValueError when the index fails check_utc_index.
    """
    check_utc_index(prices)
    is_hourly = prices.index < quarter_hour_start
    return pd.concat([prices[is_hourly], _mean_of_complete_hours(prices[~is_hourly])])


def quarter_hour_prices(prices: pd.Series, quarter_hour_start: pd.Timestamp) -> pd.Series:
    """Return the 15-minute price series of experiment Q.

    Input: raw prices with a UTC index, and 00:00 in market time on the first
        delivery day with 15-minute prices.
    Output: the prices from quarter_hour_start on, unchanged.
    Raises ValueError when the index fails check_utc_index.
    """
    check_utc_index(prices)
    return prices[prices.index >= quarter_hour_start]


def _mean_of_complete_hours(values: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """Return the mean per UTC hour, empty unless the hour holds four values.

    Input: 15-minute values with a UTC index. Works per column on a frame.
    Output: one row per hour that has at least one input row.
    """
    by_hour = values.groupby(values.index.floor("h"))
    return by_hour.mean().where(by_hour.count() == QUARTERS_PER_HOUR)
