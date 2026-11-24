"""Price spreads for EDA 2: inside an hour, and between two zones.

Every function takes prices in EUR/MWh with a UTC index and changes nothing.
Hours of the day and years are counted in market time. On a 23-hour day local
hour 2 does not exist. On a 25-hour day it exists twice, and both hours count
under hour 2.

The caller passes train data only (epf.data.splits.load_train).
"""

import numpy as np
import pandas as pd

from epf.eda.price_stats import HOURS_OF_DAY

QUARTERS = [1, 2, 3, 4]


# ---- the four prices of an hour ----

def hour_spread(price: pd.Series) -> pd.Series:
    """Return per hour the highest minus the lowest of its four quarter-hour prices.

    Input: 15-minute prices with a UTC index.
    Output: one value per hour, at the start of the hour. Empty for an hour
        with fewer than four prices.
    """
    groups = price.groupby(price.index.floor("h"))
    return (groups.max() - groups.min()).where(groups.count() == len(QUARTERS))


def quarter_differences(price: pd.Series) -> pd.Series:
    """Return every quarter-hour price minus the mean of the four prices of its hour.

    Output: on the index of the prices. Empty for an hour with fewer than four prices.
    """
    groups = price.groupby(price.index.floor("h"))
    complete = groups.transform("count") == len(QUARTERS)
    return (price - groups.transform("mean")).where(complete)


def quarter_profile(differences: pd.Series, market_tz: str) -> pd.DataFrame:
    """Return the median of quarter_differences per hour of day and quarter-hour.

    Output: one row per hour 0 to 23 in market time, one column per
        quarter-hour 1 to 4 of the hour.
    """
    known = differences.dropna()
    local = known.index.tz_convert(market_tz)
    quarter = local.minute // 15 + 1
    medians = known.groupby([np.asarray(local.hour), np.asarray(quarter)]).median()
    return medians.unstack().reindex(index=HOURS_OF_DAY, columns=QUARTERS).rename_axis("hour")


def spread_summary(spread: pd.Series) -> dict[str, float]:
    """Return the count and the quantiles of hour_spread, and how often it is zero."""
    known = spread.dropna()
    return {"hours": len(known), "hours_left_out": len(spread) - len(known),
            "median": known.median(), "q75": known.quantile(0.75),
            "q95": known.quantile(0.95), "max": known.max(),
            "zero_percent": 100.0 * (known == 0).mean()}


# ---- prices of two zones ----

def yearly_means(price: pd.Series, market_tz: str) -> pd.Series:
    """Return the mean price per year in market time."""
    years = price.index.tz_convert(market_tz).year
    return price.groupby(np.asarray(years)).mean().rename_axis("year")


def equal_share_by_year(one: pd.Series, other: pd.Series, market_tz: str) -> pd.DataFrame:
    """Return per year how often two zones have exactly the same price.

    Input: the prices of two zones on the same UTC index. An hour in which
        one of them is empty is left out.
    Output: one row per year in market time with hours, identical and share_percent.
    """
    both = one.notna() & other.notna()
    same = one[both] == other[both]
    groups = same.groupby(np.asarray(same.index.tz_convert(market_tz).year))
    table = pd.DataFrame({"hours": groups.size(), "identical": groups.sum().astype(int)})
    table["share_percent"] = 100.0 * table["identical"] / table["hours"]
    return table.rename_axis("year")


def difference_before_and_from(one: pd.Series, other: pd.Series,
                               start: pd.Timestamp) -> pd.DataFrame:
    """Compare the prices of two zones before a moment and from it on.

    Input: the prices of two zones on the same UTC index and the moment.
    Output: the rows before and from, each with the hours, the percentage of
        hours with exactly the same price, and the median and the 95%
        quantile of the absolute price difference.
    """
    difference = (one - other).abs().dropna()
    parts = {"before": difference[difference.index < start],
             "from": difference[difference.index >= start]}
    rows = {name: {"hours": len(part), "identical_percent": 100.0 * (part == 0).mean(),
                   "median_abs_difference": part.median(),
                   "q95_abs_difference": part.quantile(0.95)}
            for name, part in parts.items()}
    return pd.DataFrame.from_dict(rows, orient="index")
