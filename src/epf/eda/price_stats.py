"""The numbers behind the price figures of EDA 1.

Every function takes prices in EUR/MWh with a UTC index, one value per hour,
and changes nothing. Hours, weekdays, months and years are counted in market
time. On a 23-hour day local hour 2 does not exist. On a 25-hour day it
exists twice, and both hours count under hour 2.

The caller passes train data only (epf.data.splits.load_train).
"""

import numpy as np
import pandas as pd

HOURS_OF_DAY = list(range(24))
WEEKDAYS = list(range(7))          # Monday is 0
MONTHS = list(range(1, 13))
TIME_FORMAT = "%Y-%m-%d %H:%M"


def price_summary(price: pd.Series) -> dict[str, float]:
    """Return the count, centre, spread, quantiles and skewness of the prices.

    Output: hours is the number of prices that are not empty. q01 to q99 are
        quantiles. skew is the sample skewness, 0 for a symmetric distribution.
    """
    quantiles = {"q01": 0.01, "q05": 0.05, "q25": 0.25, "median": 0.5,
                 "q75": 0.75, "q95": 0.95, "q99": 0.99}
    summary = {"hours": int(price.count()), "mean": price.mean(), "std": price.std(),
               "min": price.min()}
    summary.update({name: price.quantile(share) for name, share in quantiles.items()})
    summary.update({"max": price.max(), "skew": price.skew()})
    return summary


def extremes(price: pd.Series, market_tz: str) -> dict[str, float | str]:
    """Return the lowest and the highest price, each with its hour in market time."""
    low, high = price.idxmin(), price.idxmax()
    return {
        "min": price[low], "min_time": low.tz_convert(market_tz).strftime(TIME_FORMAT),
        "max": price[high], "max_time": high.tz_convert(market_tz).strftime(TIME_FORMAT),
    }


def pooled_range(prices: dict[str, pd.Series], low_share: float,
                 high_share: float) -> tuple[float, float]:
    """Return two quantiles of the prices of all zones taken together.

    Input: prices by zone, and two shares such as 0.001 and 0.999.
    Output: (low, high) in EUR/MWh. The histograms share this range.
    """
    pooled = pd.concat(list(prices.values()))
    return float(pooled.quantile(low_share)), float(pooled.quantile(high_share))


def count_outside(price: pd.Series, low: float, high: float) -> tuple[int, int]:
    """Return how many prices lie below low and how many above high."""
    return int((price < low).sum()), int((price > high).sum())


def hour_profile(price: pd.Series, market_tz: str) -> pd.DataFrame:
    """Return count, q25, median and q75 of the price per hour of day in market time.

    Output: one row per hour 0 to 23. An hour without a price has count 0.
    """
    return _profile(price, price.index.tz_convert(market_tz).hour, HOURS_OF_DAY)


def weekday_profile(price: pd.Series, market_tz: str) -> pd.DataFrame:
    """Return count, q25, median and q75 of the price per weekday in market time.

    Output: one row per weekday, 0 for Monday to 6 for Sunday.
    """
    return _profile(price, price.index.tz_convert(market_tz).dayofweek, WEEKDAYS)


def month_year_means(price: pd.Series, market_tz: str) -> pd.DataFrame:
    """Return the mean price per year and month in market time.

    Output: one row per year, one column per month 1 to 12. A month without
        a price is empty.
    """
    local = price.index.tz_convert(market_tz)
    means = price.groupby([local.year.to_numpy(), local.month.to_numpy()]).mean().unstack()
    return means.reindex(columns=MONTHS)


def spike_threshold(price: pd.Series, window_hours: int, sd: float) -> pd.Series:
    """Return for every hour the price above which it counts as a spike.

    Input: hourly prices, the window length in hours and the number of
        standard deviations.
    Output: the mean of the window_hours prices before the hour, plus sd
        times their sample standard deviation. The hour itself is not in its
        window. Empty for the first window_hours hours and while the window
        holds an empty price.
    """
    before = price.shift(1).rolling(window_hours, min_periods=window_hours)
    return before.mean() + sd * before.std()


def spike_flags(price: pd.Series, window_hours: int, sd: float) -> pd.Series:
    """Return True for every hour whose price is above its spike threshold.

    Output: False where the hour has no threshold. Only upward spikes count.
    """
    return price > spike_threshold(price, window_hours, sd)


def negative_flags(price: pd.Series) -> pd.Series:
    """Return True for every hour with a price below zero. A price of zero is not negative."""
    return price < 0


def count_zero(price: pd.Series) -> int:
    """Return the number of hours with a price of exactly zero."""
    return int((price == 0).sum())


def flag_counts(flags: pd.Series, market_tz: str) -> dict[str, pd.Series]:
    """Count the flagged hours per year, per month and per hour of day in market time.

    Input: a True/False series with a UTC index.
    Output: three series under the keys year, month and hour. year has the
        years of the index, month the months 1 to 12 and hour the hours 0 to
        23, each with 0 where nothing is flagged.
    """
    local = flags.index.tz_convert(market_tz)
    years = sorted(set(local.year))
    keys = {"year": (local.year, years), "month": (local.month, MONTHS),
            "hour": (local.hour, HOURS_OF_DAY)}
    return {name: flags.groupby(np.asarray(values)).sum().reindex(order, fill_value=0).astype(int)
            for name, (values, order) in keys.items()}


def flag_summary(flags: pd.Series, judged_hours: int, market_tz: str) -> dict[str, float]:
    """Return how many hours are flagged, their share and the delivery days they fall on.

    Input: a True/False series with a UTC index, and the number of hours
        that could have been flagged.
    Output: hours_judged, hours_flagged, share_percent and days_flagged, the
        number of delivery days with at least one flagged hour.
    """
    flagged = int(flags.sum())
    days = flags.index[flags.to_numpy()].tz_convert(market_tz).normalize()
    return {"hours_judged": judged_hours, "hours_flagged": flagged,
            "share_percent": 100.0 * flagged / judged_hours, "days_flagged": days.nunique()}


def _profile(price: pd.Series, keys: pd.Index, order: list[int]) -> pd.DataFrame:
    """Return count, q25, median and q75 of the price per key, in the given order."""
    groups = price.groupby(np.asarray(keys))
    table = pd.DataFrame({"count": groups.count(), "q25": groups.quantile(0.25),
                          "median": groups.median(), "q75": groups.quantile(0.75)})
    table = table.reindex(order)
    table["count"] = table["count"].fillna(0).astype(int)
    return table
