"""Time resolution handling: the index check, the price split and the covariate alignment.

All series are in UTC. In UTC every hour holds four quarter-hours, also on a
clock-change day, which is simply 23 or 25 hours long. No function here fills
a gap or writes a file.
"""

import pandas as pd


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
