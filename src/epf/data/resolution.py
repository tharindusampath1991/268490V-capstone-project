"""Time resolution handling: the index check, the price split and the covariate alignment.

All series are in UTC. In UTC every hour holds four quarter-hours, also on a
clock-change day, which is simply 23 or 25 hours long. No function here writes
a file or fills a gap, apart from the limit stated at align_to_hours.
"""

from datetime import timedelta

import pandas as pd

QUARTERS_PER_HOUR = 4
QUARTER_HOUR = timedelta(minutes=15)


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


def align_to_hours(data: pd.DataFrame) -> pd.DataFrame:
    """Put a covariate frame on the hourly grid.

    Input: a raw forecast or load frame with a UTC index. A column may be
        hourly, 15-minute, or change between the two.
    Output: one row per UTC hour that has an input row. The rule is applied
        per column and per hour:
          one value, at minute 0       the value, unchanged
          four quarter-hour values     their mean
          anything else                empty
        Limit: values are counted, not rows. An hour whose only value is at
        minute 0 counts as hourly, also when the frame has empty rows for
        its other quarter-hours. A column that is hourly beside a 15-minute
        column looks exactly like that.
    Raises ValueError when the index fails check_utc_index.
    """
    check_utc_index(data)
    means = _mean_of_complete_hours(data)
    return means.where(means.notna(), _single_hourly_values(data))


def align_to_quarter_hours(data: pd.DataFrame) -> pd.DataFrame:
    """Put a covariate frame on the 15-minute grid.

    Input: a raw forecast or load frame with a UTC index. A column may be
        hourly, 15-minute, or change between the two.
    Output: four rows per UTC hour that has an input row. The rule is applied
        per column and per hour:
          one value, at minute 0       repeated on the four quarter-hours.
                                       An hourly value is the mean power of
                                       its hour, so nothing is interpolated.
          anything else                each value stays at its own time and
                                       a missing quarter-hour stays empty
        Limit: the same as in align_to_hours. A lone value at minute 0 is
        repeated over empty rows of its hour.
    Raises ValueError when the index fails check_utc_index.
    """
    check_utc_index(data)
    hours = data.index.floor("h").unique()
    grid = hours.append([hours + step * QUARTER_HOUR
                         for step in range(1, QUARTERS_PER_HOUR)]).sort_values()
    on_grid = data.reindex(grid)
    repeated = _single_hourly_values(data).reindex(grid.floor("h")).set_axis(grid)
    return on_grid.where(repeated.isna(), repeated)


def _single_hourly_values(data: pd.DataFrame) -> pd.DataFrame:
    """Return, per UTC hour, the value at minute 0 when it is the only value of the hour.

    Output: one row per hour that has an input row. Empty where the hour
        holds more than one value or its one value is not at minute 0.
    """
    count = data.groupby(data.index.floor("h")).count()
    at_minute_zero = data[data.index.minute == 0]
    return at_minute_zero.reindex(count.index).where(count == 1)


def _mean_of_complete_hours(values: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """Return the mean per UTC hour, empty unless the hour holds four values.

    Input: 15-minute values with a UTC index. Works per column on a frame.
    Output: one row per hour that has at least one input row.
    """
    by_hour = values.groupby(values.index.floor("h"))
    return by_hour.mean().where(by_hour.count() == QUARTERS_PER_HOUR)
