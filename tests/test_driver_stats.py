"""Tests for the numbers behind the figures of EDA 2.

They use small synthetic series and no data files. 2025-03-30 is a 23-hour
day and 2025-10-26 a 25-hour day in market time.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import hourly_index, quarter_hour_index
from epf.eda.driver_stats import (
    AFTER,
    BEFORE,
    DURING,
    HOLIDAY,
    LOAD,
    RESIDUAL,
    SATURDAY,
    SOLAR,
    SUNDAY,
    WIND,
    WORKING,
    bin_numbers,
    binned_median,
    binned_median_by_group,
    correlation_by_year,
    correlation_table,
    daily_mean,
    daily_sum,
    day_types,
    delivery_day,
    difference_summary,
    driver_table,
    high_price_period,
    hour_profile_by_group,
    hour_spread,
    matched_difference,
    median_shares,
    minus_day_mean,
    monthly_means,
    period_labels,
    quarter_differences,
    quarter_profile,
    rank_correlation,
    share_by_bin,
    share_groups,
    spread_summary,
    to_time_steps,
    weekend_holidays,
)
from epf.eda.price_stats import hour_profile

MARKET_TZ = "Europe/Berlin"


def market_time(text: str) -> pd.Timestamp:
    """A timestamp in market time. A date alone means 00:00 on that day."""
    return pd.Timestamp(text, tz=MARKET_TZ)


def hours(first_day: str, day_after_last: str) -> pd.DatetimeIndex:
    """Every hour of the delivery days [first_day, day_after_last), as a UTC index."""
    return hourly_index(market_time(first_day), market_time(day_after_last))


def quarter_hours(first_day: str, day_after_last: str) -> pd.DatetimeIndex:
    """Every quarter-hour of the delivery days [first_day, day_after_last), as a UTC index."""
    return quarter_hour_index(market_time(first_day), market_time(day_after_last))


def days(first: str, count: int) -> pd.DatetimeIndex:
    """A run of delivery days as dates without a time zone."""
    return pd.date_range(first, periods=count, freq="D")


def table(**columns: list[float]) -> pd.DataFrame:
    """A table with the given columns on the first hours of 2025-06-02."""
    length = len(next(iter(columns.values())))
    return pd.DataFrame(columns, index=hours("2025-06-02", "2025-06-03")[:length])


# ---- residual load ----

def test_driver_table_adds_the_wind_columns_and_subtracts_wind_and_solar_from_the_load():
    hourly = table(price=[50.0, 60.0], load_forecast=[100.0, 110.0],
                   wind_onshore_forecast=[20.0, 25.0], wind_offshore_forecast=[5.0, 10.0],
                   solar_forecast=[10.0, 0.0], actual_load=[999.0, 999.0])

    drivers = driver_table(hourly)

    assert list(drivers.columns) == ["price", LOAD, WIND, SOLAR, RESIDUAL]
    assert drivers[WIND].tolist() == [25.0, 35.0]
    assert drivers[RESIDUAL].tolist() == [65.0, 75.0]


def test_driver_table_works_without_an_offshore_and_without_a_solar_column():
    hourly = table(price=[50.0], load_forecast=[100.0], wind_onshore_forecast=[20.0])

    drivers = driver_table(hourly)

    assert SOLAR not in drivers.columns
    assert drivers[WIND].tolist() == [20.0]
    assert drivers[RESIDUAL].tolist() == [80.0]


def test_driver_table_leaves_the_residual_load_empty_when_one_input_is_empty():
    hourly = table(price=[50.0, 50.0, 50.0, 50.0], load_forecast=[100.0, np.nan, 100.0, 100.0],
                   wind_onshore_forecast=[20.0, 20.0, 20.0, 20.0],
                   wind_offshore_forecast=[5.0, 5.0, np.nan, 5.0],
                   solar_forecast=[10.0, 10.0, 10.0, np.nan])

    drivers = driver_table(hourly)

    assert drivers[RESIDUAL].isna().tolist() == [False, True, True, True]
    assert drivers[WIND].isna().tolist() == [False, False, True, False]


# ---- rank correlation ----

def test_rank_correlation_is_one_for_a_rising_curve_and_minus_one_for_a_falling_one():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    assert rank_correlation(x, x ** 3)["rank_correlation"] == pytest.approx(1.0)
    assert rank_correlation(x, -np.exp(x))["rank_correlation"] == pytest.approx(-1.0)


def test_rank_correlation_leaves_out_an_hour_with_an_empty_value_and_counts_it():
    x = pd.Series([1.0, 2.0, np.nan, 4.0, 5.0])
    y = pd.Series([10.0, 20.0, -500.0, np.nan, 50.0])

    result = rank_correlation(x, y)

    assert result == {"rank_correlation": pytest.approx(1.0), "hours_used": 3,
                      "hours_left_out": 2}


def test_correlation_table_has_one_row_per_input_of_the_zone():
    hourly = table(price=[10.0, 20.0, 30.0, 40.0], load_forecast=[1.0, 2.0, 3.0, 4.0],
                   wind_onshore_forecast=[4.0, 3.0, np.nan, 1.0])

    result = correlation_table(driver_table(hourly))

    assert list(result.index) == [LOAD, WIND, RESIDUAL]
    assert result.loc[LOAD, "rank_correlation"] == pytest.approx(1.0)
    assert result.loc[WIND, "rank_correlation"] == pytest.approx(-1.0)
    assert result.loc[WIND, "hours_left_out"] == 1
    assert result.loc[RESIDUAL, "hours_used"] == 3


def test_correlation_by_year_counts_the_year_in_market_time():
    index = hours("2024-12-30", "2025-01-03")              # two days in each year
    falling = np.arange(48, dtype=float)[::-1]
    hourly = pd.DataFrame({"price": np.arange(96, dtype=float),
                           "load_forecast": np.concatenate([np.arange(48.0), falling]),
                           "wind_onshore_forecast": np.tile([1.0, 2.0], 48)}, index=index)

    result = correlation_by_year(driver_table(hourly), MARKET_TZ)

    assert list(result.index) == [2024, 2025]
    assert result.loc[2024, LOAD] == pytest.approx(1.0)
    assert result.loc[2025, LOAD] == pytest.approx(-1.0)


# ---- bins ----

def test_bin_numbers_gives_bins_of_equal_count_with_one_for_the_lowest_values():
    values = pd.Series(np.arange(1.0, 101.0))

    numbers = bin_numbers(values, 10)

    assert numbers.value_counts().tolist() == [10] * 10
    assert numbers.iloc[0] == 1
    assert numbers.iloc[-1] == 10


def test_bin_numbers_merges_equal_edges_and_gives_an_empty_value_no_bin():
    values = pd.Series([0.0] * 6 + [1.0, 2.0, 3.0, 4.0] + [np.nan])

    numbers = bin_numbers(values, 5)

    assert numbers.iloc[:6].tolist() == [1] * 6            # the zeros share one bin
    assert numbers.max() < 5
    assert np.isnan(numbers.iloc[-1])


def test_bin_numbers_puts_values_that_are_all_equal_into_one_bin():
    assert bin_numbers(pd.Series([7.0, 7.0, np.nan]), 4).tolist()[:2] == [1, 1]


def test_binned_median_gives_the_median_price_per_bin_and_leaves_out_empty_hours():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, np.nan])
    y = pd.Series([10.0, 30.0, 50.0, 70.0, np.nan, 999.0])

    result = binned_median(x, y, 2)

    assert result["hours"].tolist() == [2, 2]
    assert result["median_price"].tolist() == [20.0, 60.0]
    assert result["x_median"].tolist() == [1.5, 3.5]
    assert result["x_low"].tolist() == [1.0, 3.0]
    assert result["x_high"].tolist() == [2.0, 4.0]


def test_binned_median_by_group_uses_one_set_of_bins_for_all_groups():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0])
    y = pd.Series([10.0, 10.0, 20.0, 20.0, 100.0, 100.0, 200.0, 200.0])
    groups = pd.Series(["a"] * 4 + ["b"] * 4)

    result = binned_median_by_group(x, y, groups, 2, ["a", "b"])

    assert list(result) == ["a", "b"]
    assert result["a"]["median_price"].tolist() == [10.0, 20.0]
    assert result["b"]["median_price"].tolist() == [100.0, 200.0]
    assert result["a"]["hours"].tolist() == [2, 2]


def test_share_by_bin_counts_the_flagged_hours_per_bin_and_skips_an_empty_input():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, np.nan])
    flags = pd.Series([True, False, False, False, True])

    result = share_by_bin(x, flags, 2)

    assert result["hours"].tolist() == [2, 2]
    assert result["flagged"].tolist() == [1, 0]
    assert result["share_percent"].tolist() == [50.0, 0.0]


def test_median_shares_gives_the_inputs_as_a_share_of_the_load_for_the_flagged_hours():
    hourly = table(price=[-5.0, -1.0, 80.0, -3.0], load_forecast=[100.0, 200.0, 100.0, np.nan],
                   wind_onshore_forecast=[30.0, 20.0, 5.0, 10.0],
                   solar_forecast=[50.0, 120.0, 5.0, 10.0])
    drivers = driver_table(hourly)

    result = median_shares(drivers, drivers["price"] < 0)

    assert result["hours"] == 2                            # the fourth hour has no load forecast
    assert result["load_forecast_median"] == 150.0
    assert result["wind_share_percent"] == pytest.approx(20.0)       # median of 30% and 10%
    assert result["solar_share_percent"] == pytest.approx(55.0)      # median of 50% and 60%
    assert result["residual_share_percent"] == pytest.approx(25.0)   # median of 20% and 30%


# ---- delivery days ----

def test_delivery_day_follows_market_time():
    index = hours("2025-06-02", "2025-06-04")

    found = delivery_day(index, MARKET_TZ)

    assert index[0].hour == 22                             # 22:00 UTC on 1 June
    assert found[0] == pd.Timestamp("2025-06-02")
    assert found[-1] == pd.Timestamp("2025-06-03")
    assert found.tz is None


def test_daily_sum_counts_23_and_25_hours_on_the_clock_change_days():
    spring = pd.Series(1.0, index=hours("2025-03-29", "2025-03-31"))
    autumn = pd.Series(1.0, index=hours("2025-10-26", "2025-10-27"))

    assert daily_sum(spring, MARKET_TZ).tolist() == [24.0, 23.0]
    assert daily_sum(autumn, MARKET_TZ).tolist() == [25.0]


def test_daily_sum_is_empty_for_a_day_with_an_empty_hour():
    values = pd.Series(1.0, index=hours("2025-06-02", "2025-06-04"))
    values.iloc[30] = np.nan

    result = daily_sum(values, MARKET_TZ)

    assert result.index.tolist() == days("2025-06-02", 2).tolist()
    assert result.iloc[0] == 24.0
    assert np.isnan(result.iloc[1])


def test_daily_mean_and_minus_day_mean_use_the_hours_of_the_delivery_day():
    index = hours("2025-06-02", "2025-06-04")
    price = pd.Series([10.0] * 12 + [30.0] * 12 + [100.0] * 24, index=index)

    assert daily_mean(price, MARKET_TZ).tolist() == [20.0, 100.0]
    difference = minus_day_mean(price, MARKET_TZ)
    assert difference.iloc[0] == -10.0
    assert difference.iloc[12] == 10.0
    assert difference.iloc[24:].eq(0.0).all()


def test_to_time_steps_gives_every_hour_the_value_of_its_delivery_day():
    index = hours("2025-06-02", "2025-06-05")
    by_day = pd.Series(["low", "high"], index=days("2025-06-02", 2))

    result = to_time_steps(by_day, index, MARKET_TZ)

    assert result.index.equals(index)
    assert result.iloc[:24].eq("low").all()
    assert result.iloc[24:48].eq("high").all()
    assert result.iloc[48:].isna().all()                   # the third day has no value


# ---- profiles ----

def test_hour_profile_by_group_gives_the_median_per_hour_and_group():
    index = hours("2025-06-02", "2025-06-06")              # four days
    values = pd.Series(np.repeat([1.0, 3.0, 100.0, 200.0], 24), index=index)
    groups = pd.Series(np.repeat(["a", "a", "b", "b"], 24), index=index)

    result = hour_profile_by_group(values, groups, MARKET_TZ, ["a", "b"])

    assert list(result.index) == list(range(24))
    assert result["a"].eq(2.0).all()
    assert result["b"].eq(150.0).all()


def test_hour_profile_by_group_counts_both_hours_two_of_a_25_hour_day_under_hour_two():
    index = hours("2025-10-26", "2025-10-27")
    values = pd.Series(0.0, index=index)
    values.iloc[2], values.iloc[3] = 10.0, 30.0            # 02:00 summer time, 02:00 winter time
    groups = pd.Series("a", index=index)

    result = hour_profile_by_group(values, groups, MARKET_TZ, ["a"])

    assert len(index) == 25
    assert result.loc[2, "a"] == 20.0
    assert result.loc[3, "a"] == 0.0


def test_hour_profile_by_group_has_no_hour_two_on_a_23_hour_day():
    index = hours("2025-03-30", "2025-03-31")
    values = pd.Series(5.0, index=index)

    result = hour_profile_by_group(values, pd.Series("a", index=index), MARKET_TZ, ["a"])

    assert len(index) == 23
    assert np.isnan(result.loc[2, "a"])
    assert result["a"].count() == 23


def test_hour_profile_by_group_leaves_out_hours_without_a_group_or_a_value():
    index = hours("2025-06-02", "2025-06-04")
    values = pd.Series([1.0] * 24 + [9.0] * 24, index=index)
    groups = pd.Series(["a"] * 24 + [None] * 24, index=index)
    values.iloc[0] = np.nan

    result = hour_profile_by_group(values, groups, MARKET_TZ, ["a"])

    assert np.isnan(result.loc[0, "a"])
    assert result.loc[1:, "a"].eq(1.0).all()


# ---- high-price period ----

def monthly_prices(means: dict[str, float]) -> pd.Series:
    """Hourly prices that have the given mean in each month, named as YYYY-MM."""
    parts = []
    for month, mean in means.items():
        start = market_time(f"{month}-01")
        index = hourly_index(start, start + pd.offsets.MonthBegin(1))
        parts.append(pd.Series(mean, index=index))
    return pd.concat(parts)


def test_monthly_means_names_the_month_in_market_time():
    price = monthly_prices({"2025-01": 10.0, "2025-02": 30.0})

    result = monthly_means(price, MARKET_TZ)

    assert price.index[0].month == 12                      # 23:00 UTC on 31 December
    assert result.to_dict() == {"2025-01": 10.0, "2025-02": 30.0}


def test_high_price_period_runs_from_the_first_to_the_last_month_above_the_threshold():
    quiet = {"2025-01": 10.0, "2025-02": 10.0, "2025-06": 10.0, "2025-07": 10.0}
    one = monthly_prices({**quiet, "2025-03": 50.0, "2025-04": 10.0, "2025-05": 50.0})
    two = monthly_prices({**quiet, "2025-03": 30.0, "2025-04": 10.0, "2025-05": 30.0})

    summary, pooled = high_price_period({"AA": one, "BB": two}, 2, MARKET_TZ)

    assert pooled["2025-03"] == 40.0                       # the mean of the two zones
    assert summary["median_of_monthly_means"] == 10.0
    assert summary["threshold"] == 20.0
    assert summary["first_month"] == "2025-03"
    assert summary["last_month"] == "2025-05"
    assert summary["months_above"] == 2
    assert summary["months_in_period"] == 3                # April lies inside and is not above


def test_high_price_period_refuses_prices_without_a_month_above_the_threshold():
    flat = monthly_prices({"2025-01": 10.0, "2025-02": 10.0})

    with pytest.raises(ValueError, match="No month"):
        high_price_period({"AA": flat}, 2, MARKET_TZ)


def test_period_labels_cut_at_midnight_market_time():
    index = hours("2025-02-28", "2025-05-02")

    labels = period_labels(index, "2025-03", "2025-04", MARKET_TZ)

    assert labels[market_time("2025-02-28 23:00")] == BEFORE
    assert labels[market_time("2025-03-01 00:00")] == DURING
    assert labels[market_time("2025-04-30 23:00")] == DURING
    assert labels[market_time("2025-05-01 00:00")] == AFTER


# ---- holidays ----

def test_day_types_counts_a_holiday_on_a_weekend_as_that_weekend_day():
    week = days("2025-06-02", 7)                           # Monday to Sunday
    holidays = {date(2025, 6, 4), date(2025, 6, 7)}        # a Wednesday and a Saturday

    types = day_types(week, holidays)

    assert types.tolist() == [WORKING, WORKING, HOLIDAY, WORKING, WORKING, SATURDAY, SUNDAY]
    assert weekend_holidays(week, holidays) == 1


def test_matched_difference_compares_a_day_with_the_reference_days_around_it():
    daily = pd.Series([50.0, 60.0, 20.0, 70.0, 80.0, 500.0], index=days("2025-06-02", 6))
    holiday = daily.index[[2]]
    reference = daily.index[[0, 1, 3, 4, 5]]

    near = matched_difference(daily, holiday, reference, 2)
    wide = matched_difference(daily, holiday, reference, 3)

    assert near.tolist() == [20.0 - 65.0]                  # median of 50, 60, 70 and 80
    assert wide.tolist() == [20.0 - 70.0]                  # 500 is three days away


def test_matched_difference_is_empty_without_a_reference_day_in_the_window():
    daily = pd.Series([50.0, 20.0, 30.0], index=days("2025-06-02", 3))

    result = matched_difference(daily, daily.index[[2]], daily.index[[0]], 1)

    assert result.isna().tolist() == [True]


def test_difference_summary_counts_the_days_and_the_share_below_zero():
    differences = pd.Series([-30.0, -10.0, 10.0, np.nan])

    summary = difference_summary(differences)

    assert summary["days"] == 3
    assert summary["days_left_out"] == 1
    assert summary["median"] == -10.0
    assert summary["q25"] == -20.0
    assert summary["q75"] == 0.0
    assert summary["below_zero_percent"] == pytest.approx(200 / 3)


def test_share_groups_names_the_group_of_every_share():
    shares = pd.Series([0.05, 0.25, 0.3, 0.5, 0.9])

    labels, order = share_groups(shares, [0.25, 0.5])

    assert order == ["up to 25%", "25% to 50%", "above 50%"]
    assert labels.tolist() == ["up to 25%", "up to 25%", "25% to 50%", "25% to 50%", "above 50%"]


# ---- quarter-hours ----

def test_hour_spread_is_the_highest_minus_the_lowest_quarter_hour_price():
    index = quarter_hours("2025-06-02", "2025-06-03")[:8]
    price = pd.Series([10.0, 12.0, 8.0, 15.0, -5.0, -5.0, -5.0, -5.0], index=index)

    spread = hour_spread(price)

    assert spread.tolist() == [7.0, 0.0]
    assert spread.index.tolist() == [index[0], index[4]]


def test_hour_spread_is_empty_for_an_hour_with_fewer_than_four_prices():
    index = quarter_hours("2025-06-02", "2025-06-03")[:8]
    price = pd.Series([10.0, 12.0, np.nan, 15.0, 1.0, 2.0, 3.0, 4.0], index=index)

    spread = hour_spread(price)
    differences = quarter_differences(price)

    assert np.isnan(spread.iloc[0])
    assert spread.iloc[1] == 3.0
    assert differences.iloc[:4].isna().all()
    assert differences.iloc[4:].tolist() == [-1.5, -0.5, 0.5, 1.5]


def test_spread_profile_counts_two_hours_two_on_a_25_hour_day_and_none_on_a_23_hour_day():
    autumn = pd.Series(1.0, index=quarter_hours("2025-10-26", "2025-10-27"))
    spring = pd.Series(1.0, index=quarter_hours("2025-03-30", "2025-03-31"))

    long_day = hour_profile(hour_spread(autumn), MARKET_TZ)
    short_day = hour_profile(hour_spread(spring), MARKET_TZ)

    assert len(autumn) == 100
    assert long_day.loc[2, "count"] == 2
    assert long_day.loc[3, "count"] == 1
    assert len(spring) == 92
    assert short_day.loc[2, "count"] == 0


def test_quarter_profile_gives_the_median_difference_per_hour_and_quarter():
    index = quarter_hours("2025-06-02", "2025-06-04")      # two days
    one_hour = [3.0, 1.0, -1.0, -3.0]
    price = pd.Series(one_hour * 24 + [2 * value for value in one_hour] * 24, index=index)

    profile = quarter_profile(quarter_differences(price), MARKET_TZ)

    assert list(profile.columns) == [1, 2, 3, 4]
    assert list(profile.index) == list(range(24))
    assert profile.loc[8].tolist() == [4.5, 1.5, -1.5, -4.5]   # the median of the two days


def test_quarter_profile_has_no_hour_two_on_a_23_hour_day():
    price = pd.Series(1.0, index=quarter_hours("2025-03-30", "2025-03-31"))

    profile = quarter_profile(quarter_differences(price), MARKET_TZ)

    assert profile.loc[2].isna().all()
    assert profile.loc[3].notna().all()


def test_spread_summary_counts_the_hours_and_the_hours_without_a_spread():
    spread = pd.Series([0.0, 2.0, 4.0, 10.0, np.nan])

    summary = spread_summary(spread)

    assert summary["hours"] == 4
    assert summary["hours_left_out"] == 1
    assert summary["median"] == 3.0
    assert summary["max"] == 10.0
    assert summary["zero_percent"] == 25.0
