"""Tests for the price spreads inside an hour and between two zones.

They use small synthetic series and no data files. 2025-03-30 is a 23-hour
day and 2025-10-26 a 25-hour day in market time.
"""

import numpy as np
import pandas as pd

from epf.data.market_time import hourly_index, quarter_hour_index
from epf.eda.price_stats import hour_profile
from epf.eda.spread_stats import (
    difference_before_and_from,
    equal_share_by_year,
    hour_spread,
    quarter_differences,
    quarter_profile,
    spread_summary,
    yearly_means,
)

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


# ---- the four prices of an hour ----

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


# ---- prices of two zones ----

def test_yearly_means_counts_the_year_in_market_time():
    index = hours("2024-12-31", "2025-01-02")              # one day in each year
    price = pd.Series([10.0] * 24 + [30.0] * 24, index=index)

    result = yearly_means(price, MARKET_TZ)

    assert index[24].year == 2024                          # 23:00 UTC on 31 December
    assert result.to_dict() == {2024: 10.0, 2025: 30.0}


def test_equal_share_by_year_counts_the_hours_with_exactly_the_same_price():
    index = hours("2024-12-31", "2025-01-02")
    one = pd.Series(50.0, index=index)
    other = one.copy()
    other.iloc[24:36] += 0.01                              # twelve hours of 2025 differ by a cent

    result = equal_share_by_year(one, other, MARKET_TZ)

    assert result.loc[2024].to_dict() == {"hours": 24, "identical": 24, "share_percent": 100.0}
    assert result.loc[2025].to_dict() == {"hours": 24, "identical": 12, "share_percent": 50.0}


def test_equal_share_by_year_leaves_out_an_hour_with_an_empty_price():
    index = hours("2025-06-02", "2025-06-03")
    one = pd.Series(50.0, index=index)
    other = one.copy()
    other.iloc[0] = np.nan

    result = equal_share_by_year(one, other, MARKET_TZ)

    assert result.loc[2025, "hours"] == 23
    assert result.loc[2025, "share_percent"] == 100.0


def test_difference_before_and_from_splits_the_hours_at_the_start():
    index = hours("2025-06-02", "2025-06-04")
    one = pd.Series(50.0, index=index)
    other = one.copy()
    other.iloc[24:] += np.tile([1.0, 3.0], 12)             # the second day differs by 1 or 3

    result = difference_before_and_from(one, other, market_time("2025-06-03"))

    assert list(result.index) == ["before", "from"]
    assert result.loc["before"].to_dict() == {
        "hours": 24, "identical_percent": 100.0, "median_abs_difference": 0.0,
        "q95_abs_difference": 0.0}
    assert result.loc["from", "hours"] == 24
    assert result.loc["from", "identical_percent"] == 0.0
    assert result.loc["from", "median_abs_difference"] == 2.0
    assert result.loc["from", "q95_abs_difference"] == 3.0
