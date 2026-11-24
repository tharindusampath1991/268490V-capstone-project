"""The numbers behind the figures of EDA 2: the price against its day-ahead inputs.

Every function takes series or tables with a UTC index and changes nothing.
Prices are in EUR/MWh, forecasts in MW. Hours, delivery days, months and
years are counted in market time. On a 23-hour day local hour 2 does not
exist. On a 25-hour day it exists twice, and both hours count under hour 2.

No gap is filled. An hour with an empty input is left out of a comparison,
and the functions return how many hours they left out.

The caller passes train data only (epf.data.splits.load_train).
"""

from datetime import date

import numpy as np
import pandas as pd

from epf.eda.price_stats import HOURS_OF_DAY

PRICE = "price"
LOAD = "load_forecast"
WIND = "wind_forecast"
SOLAR = "solar_forecast"
RESIDUAL = "residual_load"
WIND_COLUMNS = ("wind_onshore_forecast", "wind_offshore_forecast")
INPUTS = (LOAD, WIND, SOLAR, RESIDUAL)

BEFORE, DURING, AFTER = "Before", "High-price period", "After"
PERIODS = [BEFORE, DURING, AFTER]

WORKING, HOLIDAY, SATURDAY, SUNDAY = "Working day", "Holiday, Mon to Fri", "Saturday", "Sunday"
DAY_TYPES = [WORKING, HOLIDAY, SATURDAY, SUNDAY]

QUARTERS = [1, 2, 3, 4]
MONTH_FORMAT = "%Y-%m"


# ---- residual load and rank correlation ----

def driver_table(table: pd.DataFrame) -> pd.DataFrame:
    """Return the price beside the day-ahead forecasts and the residual load.

    Input: a processed table with price, load_forecast, the wind forecast
        columns the zone has and, where the zone has one, solar_forecast.
    Output: the columns price, load_forecast, wind_forecast, solar_forecast
        (only when the table has it) and residual_load. wind_forecast is
        onshore plus offshore. residual_load is the load forecast minus wind
        and solar. Both are empty in an hour in which one of their inputs is
        empty. actual_load is not used.
    """
    wind_columns = [column for column in WIND_COLUMNS if column in table.columns]
    drivers = pd.DataFrame({PRICE: table[PRICE], LOAD: table[LOAD],
                            WIND: table[wind_columns].sum(axis=1, skipna=False)})
    residual = drivers[LOAD] - drivers[WIND]
    if SOLAR in table.columns:
        drivers[SOLAR] = table[SOLAR]
        residual = residual - drivers[SOLAR]
    drivers[RESIDUAL] = residual
    return drivers


def rank_correlation(x: pd.Series, y: pd.Series) -> dict[str, float]:
    """Return the rank correlation of two series over the hours in which both have a value.

    Output: rank_correlation is the Pearson correlation of the ranks, between
        -1 and 1. hours_used and hours_left_out count the hours.
    """
    both = x.notna() & y.notna()
    value = x[both].rank().corr(y[both].rank())
    used = int(both.sum())
    return {"rank_correlation": value, "hours_used": used, "hours_left_out": len(x) - used}


def correlation_table(drivers: pd.DataFrame) -> pd.DataFrame:
    """Return the rank correlation of the price with every input of driver_table.

    Output: one row per input the zone has, with the columns of rank_correlation.
    """
    rows = {name: rank_correlation(drivers[name], drivers[PRICE])
            for name in INPUTS if name in drivers.columns}
    table = pd.DataFrame.from_dict(rows, orient="index")
    return table.astype({"hours_used": int, "hours_left_out": int})


def correlation_by_year(drivers: pd.DataFrame, market_tz: str) -> pd.DataFrame:
    """Return the rank correlation of the price with every input, per year in market time.

    Output: one row per year, one column per input the zone has.
    """
    years = drivers.index.tz_convert(market_tz).year
    names = [name for name in INPUTS if name in drivers.columns]
    rows = {year: {name: rank_correlation(part[name], part[PRICE])["rank_correlation"]
                   for name in names}
            for year, part in drivers.groupby(np.asarray(years))}
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("year")


# ---- bins ----

def bin_numbers(values: pd.Series, bins: int) -> pd.Series:
    """Return the number of the bin of every value, 1 for the lowest values.

    Input: a series and the number of bins asked for.
    Output: the bin edges are quantiles of the values, so every bin holds
        about the same number of values. Equal edges are merged. A series
        with many equal values, such as a solar forecast of zero at night,
        therefore gives fewer bins. An empty value has no bin.
    """
    edges = np.unique(values.quantile(np.linspace(0, 1, bins + 1)).to_numpy())
    if len(edges) < 2:
        return values.where(values.isna(), 1.0)
    return pd.cut(values, edges, labels=False, include_lowest=True) + 1


def binned_median(x: pd.Series, y: pd.Series, bins: int) -> pd.DataFrame:
    """Return the median of y in bins of x, over the hours in which both have a value.

    Output: one row per bin of bin_numbers with x_low, x_high and x_median of
        the bin, the number of hours and the median of y as median_price.
    """
    both = x.notna() & y.notna()
    return _bin_table(x[both], y[both], bin_numbers(x[both], bins))


def binned_median_by_group(x: pd.Series, y: pd.Series, groups: pd.Series, bins: int,
                           order: list[str]) -> dict[str, pd.DataFrame]:
    """Return binned_median once per group, with one set of bins for all groups.

    Input: x, y and a group name per hour on the same index, the number of
        bins and the groups in the order wanted.
    Output: per group the table of binned_median. The bin edges come from all
        hours with x and y, so the groups are compared on the same bins.
    """
    both = x.notna() & y.notna()
    numbers = bin_numbers(x[both], bins)
    tables = {}
    for name in order:
        part = both & (groups == name)
        tables[name] = _bin_table(x[part], y[part], numbers[part[both]])
    return tables


def share_by_bin(x: pd.Series, flags: pd.Series, bins: int) -> pd.DataFrame:
    """Return per bin of x how many hours are flagged.

    Input: an input series, a True/False series on the same index and the
        number of bins. An hour without x is left out.
    Output: one row per bin with hours, flagged and share_percent.
    """
    known = x.notna()
    numbers = bin_numbers(x[known], bins).astype(int)
    groups = flags[known].groupby(numbers)
    table = pd.DataFrame({"hours": groups.size(), "flagged": groups.sum().astype(int)})
    table["share_percent"] = 100.0 * table["flagged"] / table["hours"]
    return table.rename_axis("bin")


def median_shares(drivers: pd.DataFrame, flags: pd.Series) -> dict[str, float]:
    """Return how large wind, solar and the residual load are in the flagged hours.

    Input: the table of driver_table and a True/False series on its index.
    Output: hours is the number of flagged hours with a residual load. The
        other values are medians over those hours: the load forecast in MW,
        and wind, solar and the residual load as a percentage of the load
        forecast of the same hour.
    """
    part = drivers[flags & drivers[RESIDUAL].notna()]
    row = {"hours": len(part), "load_forecast_median": part[LOAD].median()}
    names = {WIND: "wind_share_percent", SOLAR: "solar_share_percent",
             RESIDUAL: "residual_share_percent"}
    for column, name in names.items():
        if column in part.columns:
            row[name] = (100.0 * part[column] / part[LOAD]).median()
    return row


# ---- delivery days ----

def delivery_day(index: pd.DatetimeIndex, market_tz: str) -> pd.DatetimeIndex:
    """Return the delivery day of every time step, as a date without a time zone."""
    return index.tz_convert(market_tz).normalize().tz_localize(None)


def daily_mean(values: pd.Series, market_tz: str) -> pd.Series:
    """Return the mean of the values of each delivery day. Empty values are skipped."""
    return values.groupby(delivery_day(values.index, market_tz)).mean()


def daily_sum(values: pd.Series, market_tz: str) -> pd.Series:
    """Return the sum of the values of each delivery day.

    Output: one value per delivery day, empty for a day with an empty value.
    """
    day = delivery_day(values.index, market_tz)
    complete = values.notna().groupby(day).all()
    return values.groupby(day).sum().where(complete)


def minus_day_mean(price: pd.Series, market_tz: str) -> pd.Series:
    """Return every price minus the mean price of its delivery day."""
    day = delivery_day(price.index, market_tz)
    return price - price.groupby(day).transform("mean")


def to_time_steps(by_day: pd.Series, index: pd.DatetimeIndex, market_tz: str) -> pd.Series:
    """Return for every time step the value of its delivery day.

    Input: one value per delivery day, a UTC index and the market time zone.
    Output: a series on the index, empty where the delivery day has no value.
    """
    values = by_day.reindex(delivery_day(index, market_tz)).to_numpy()
    return pd.Series(values, index=index)


def hour_profile_by_group(values: pd.Series, groups: pd.Series, market_tz: str,
                          order: list) -> pd.DataFrame:
    """Return the median of the values per hour of day in market time and per group.

    Input: values and a group per time step on the same UTC index, and the
        groups in the order wanted. A time step without a value or without a
        group is left out.
    Output: one row per hour 0 to 23, one column per group.
    """
    keep = (values.notna() & groups.notna()).to_numpy()
    hour = values.index.tz_convert(market_tz).hour[keep]
    medians = values[keep].groupby([np.asarray(hour), groups[keep].to_numpy()]).median()
    return medians.unstack().reindex(index=HOURS_OF_DAY, columns=order).rename_axis("hour")


# ---- high-price period ----

def monthly_means(price: pd.Series, market_tz: str) -> pd.Series:
    """Return the mean price per month in market time, with the month named as YYYY-MM."""
    month = price.index.tz_convert(market_tz).strftime(MONTH_FORMAT)
    return price.groupby(np.asarray(month)).mean().sort_index()


def high_price_period(prices: dict[str, pd.Series], factor: float,
                      market_tz: str) -> tuple[dict, pd.Series]:
    """Find the months in which the zones together are far above their usual level.

    Input: prices by zone, the factor and the market time zone.
    Output: a summary and the pooled series. The pooled series is the mean
        over the zones of their monthly mean prices. A month is above when its
        pooled mean is above factor times the median of the pooled series.
        The period runs from the first to the last such month, so
        months_in_period can be larger than months_above.
    Raises ValueError when no month is above the threshold.
    """
    by_zone = pd.DataFrame({zone: monthly_means(price, market_tz)
                            for zone, price in prices.items()})
    pooled = by_zone.mean(axis=1)
    median = float(pooled.median())
    above = pooled.index[pooled > factor * median]
    if len(above) == 0:
        raise ValueError(f"No month is above {factor:g} times the median monthly mean.")
    summary = {"median_of_monthly_means": median, "threshold": factor * median,
               "first_month": above[0], "last_month": above[-1], "months_above": len(above),
               "months_in_period": len(pooled.loc[above[0]:above[-1]])}
    return summary, pooled


def period_labels(index: pd.DatetimeIndex, first_month: str, last_month: str,
                  market_tz: str) -> pd.Series:
    """Return for every time step whether it lies before, in or after a period of months.

    Input: a UTC index and the first and the last month of the period as YYYY-MM.
    Output: BEFORE, DURING or AFTER per time step. Months are cut in market time.
    """
    month = index.tz_convert(market_tz).strftime(MONTH_FORMAT)
    labels = np.where(month < first_month, BEFORE, np.where(month > last_month, AFTER, DURING))
    return pd.Series(labels, index=index)


# ---- holidays ----

def day_types(days: pd.DatetimeIndex, holidays: set[date]) -> pd.Series:
    """Return the type of every delivery day.

    Input: delivery days as dates without a time zone, and the holiday dates.
    Output: SATURDAY, SUNDAY, HOLIDAY for a holiday on Monday to Friday, and
        WORKING for the rest. A holiday on a Saturday or Sunday counts as that
        weekend day.
    """
    is_holiday = np.array([day in holidays for day in days.date], dtype=bool)
    types = np.select([days.dayofweek == 5, days.dayofweek == 6, is_holiday],
                      [SATURDAY, SUNDAY, HOLIDAY], WORKING)
    return pd.Series(types, index=days)


def weekend_holidays(days: pd.DatetimeIndex, holidays: set[date]) -> int:
    """Return how many of the delivery days are a holiday on a Saturday or Sunday."""
    return sum(day in holidays for day in days[days.dayofweek >= 5].date)


def matched_difference(daily: pd.Series, days: pd.DatetimeIndex,
                       reference: pd.DatetimeIndex, window_days: int) -> pd.Series:
    """Compare each day with the reference days close to it.

    Input: one value per delivery day, the days to judge, the reference days
        and the window in days.
    Output: per judged day its value minus the median value of the reference
        days at most window_days before or after it. Empty when no reference
        day lies in the window.
    """
    window = pd.Timedelta(window_days, unit="D")
    near_values = daily[daily.index.isin(reference)]
    differences = {}
    for day in days:
        near = near_values[(near_values.index >= day - window)
                           & (near_values.index <= day + window)]
        differences[day] = daily[day] - near.median()
    return pd.Series(differences, dtype=float)


def difference_summary(differences: pd.Series) -> dict[str, float]:
    """Return the count, the median, the quartiles and the share below zero of differences.

    Output: days counts the values that are not empty, days_left_out the empty ones.
    """
    known = differences.dropna()
    return {"days": len(known), "days_left_out": len(differences) - len(known),
            "median": known.median(), "q25": known.quantile(0.25),
            "q75": known.quantile(0.75),
            "below_zero_percent": 100.0 * (known < 0).mean() if len(known) else np.nan}


def share_groups(shares: pd.Series, edges: list[float]) -> tuple[pd.Series, list[str]]:
    """Sort shares between 0 and 1 into named groups.

    Input: the shares and the inner edges in rising order, for example [0.25, 0.5].
    Output: the group of every share and the group names in rising order. A
        share equal to an edge belongs to the group below it.
    """
    bounds = [0.0, *edges, 1.0]
    names = [f"up to {edges[0]:.0%}"]
    names += [f"{low:.0%} to {high:.0%}" for low, high in zip(edges[:-1], edges[1:])]
    names += [f"above {edges[-1]:.0%}"]
    labels = pd.cut(shares, bounds, labels=names, include_lowest=True)
    return labels.astype(object), names


# ---- quarter-hours ----

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


def _bin_table(x: pd.Series, y: pd.Series, numbers: pd.Series) -> pd.DataFrame:
    """Return per bin number the range and median of x, the hours and the median of y."""
    numbers = numbers.astype(int)
    by_x, by_y = x.groupby(numbers), y.groupby(numbers)
    table = pd.DataFrame({"x_low": by_x.min(), "x_high": by_x.max(), "x_median": by_x.median(),
                          "hours": by_y.size(), "median_price": by_y.median()})
    return table.rename_axis("bin")
