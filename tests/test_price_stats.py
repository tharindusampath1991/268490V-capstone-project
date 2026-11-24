"""Tests for the numbers behind the price figures.

They use small synthetic series and no data files.
"""

import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import hourly_index
from epf.eda.price_stats import (
    count_outside,
    count_zero,
    extremes,
    flag_counts,
    flag_summary,
    hour_profile,
    month_means,
    month_year_means,
    negative_flags,
    pooled_range,
    price_summary,
    spike_flags,
    spike_threshold,
    weekday_profile,
)

MARKET_TZ = "Europe/Berlin"
WINDOW = 672


def market_time(text: str) -> pd.Timestamp:
    """A timestamp in market time. A date alone means 00:00 on that day."""
    return pd.Timestamp(text, tz=MARKET_TZ)


def hours(first_day: str, day_after_last: str) -> pd.DatetimeIndex:
    """Every hour of the delivery days [first_day, day_after_last), as a UTC index."""
    return hourly_index(market_time(first_day), market_time(day_after_last))


def running(index: pd.DatetimeIndex) -> pd.Series:
    """Prices 0.0, 1.0, 2.0 and so on, in time order."""
    return pd.Series(np.arange(len(index), dtype=float), index=index)


def quiet_then(*last_prices: float) -> pd.Series:
    """672 hours that alternate between 10 and 20, followed by the given prices.

    The 672 hours have a mean of 15 and a standard deviation of 5.0037, so the
    spike threshold after them is 30.011 with 3 standard deviations.
    """
    values = [10.0, 20.0] * (WINDOW // 2) + list(last_prices)
    index = pd.date_range("2025-01-01", periods=len(values), freq="h", tz="UTC")
    return pd.Series(values, index=index)


def test_price_summary_gives_the_count_centre_and_ends():
    price = pd.Series([-10.0, 0.0, 10.0, 20.0, 30.0], index=hours("2025-06-02", "2025-06-03")[:5])

    summary = price_summary(price)

    assert summary["hours"] == 5
    assert summary["mean"] == 10.0
    assert summary["median"] == 10.0
    assert summary["min"] == -10.0
    assert summary["max"] == 30.0
    assert summary["q25"] == 0.0
    assert summary["skew"] == 0.0


def test_extremes_names_the_local_time_of_the_lowest_and_highest_price():
    price = running(hours("2025-06-02", "2025-06-03"))

    found = extremes(price, MARKET_TZ)

    assert found["min"] == 0.0
    assert found["min_time"] == "2025-06-02 00:00"
    assert found["max"] == 23.0
    assert found["max_time"] == "2025-06-02 23:00"


def test_pooled_range_takes_the_quantiles_over_all_zones_together():
    index = hours("2025-06-02", "2025-06-07")[:100]
    prices = {"A": pd.Series(np.arange(0.0, 100.0), index=index),
              "B": pd.Series(np.arange(100.0, 200.0), index=index)}

    low, high = pooled_range(prices, 0.1, 0.9)

    assert low == pytest.approx(19.9)
    assert high == pytest.approx(179.1)
    assert count_outside(prices["A"], low, high) == (20, 0)
    assert count_outside(prices["B"], low, high) == (0, 20)


def test_hour_profile_has_no_value_for_hour_2_on_a_23_hour_day():
    price = running(hours("2025-03-30", "2025-03-31"))

    profile = hour_profile(price, MARKET_TZ)

    assert profile.index.tolist() == list(range(24))
    assert profile.loc[2, "count"] == 0
    assert np.isnan(profile.loc[2, "median"])
    assert profile["count"].sum() == 23
    assert profile.loc[1, "median"] == 1.0
    assert profile.loc[3, "median"] == 2.0     # the hour after 01:00 is 03:00


def test_hour_profile_counts_both_hours_2_on_a_25_hour_day():
    price = running(hours("2025-10-26", "2025-10-27"))

    profile = hour_profile(price, MARKET_TZ)

    assert profile.loc[2, "count"] == 2
    assert profile.loc[2, "median"] == 2.5     # the prices 2.0 and 3.0
    assert profile["count"].sum() == 25
    assert profile.loc[3, "count"] == 1
    assert profile.loc[3, "median"] == 4.0
    assert profile.loc[23, "median"] == 24.0


def test_hour_profile_groups_by_market_time_and_not_by_utc():
    index = hours("2025-06-02", "2025-06-03")
    price = pd.Series(0.0, index=index)
    price[pd.Timestamp("2025-06-02 06:00", tz="UTC")] = 100.0   # 08:00 in market time

    profile = hour_profile(price, MARKET_TZ)

    assert profile.loc[8, "median"] == 100.0
    assert profile.loc[6, "median"] == 0.0


def test_hour_profile_gives_the_quartiles_of_each_hour():
    index = hours("2025-06-02", "2025-06-07")                   # five days
    price = pd.Series(np.repeat([0.0, 10.0, 20.0, 30.0, 40.0], 24), index=index)

    profile = hour_profile(price, MARKET_TZ)

    assert profile.loc[12, ["count", "q25", "median", "q75"]].tolist() == [5, 10.0, 20.0, 30.0]


def test_weekday_profile_groups_by_the_weekday_in_market_time():
    index = hours("2025-06-02", "2025-06-16")                   # Monday to Sunday, twice
    price = pd.Series(index.tz_convert(MARKET_TZ).dayofweek.to_numpy(dtype=float), index=index)

    profile = weekday_profile(price, MARKET_TZ)

    assert profile.index.tolist() == list(range(7))
    assert profile["count"].tolist() == [48] * 7
    assert profile["median"].tolist() == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_month_year_means_puts_the_first_local_hour_of_a_year_into_january():
    index = hours("2024-12-01", "2025-02-01")
    local = index.tz_convert(MARKET_TZ)
    price = pd.Series(np.where(local.year == 2024, 10.0, 20.0), index=index)

    means = month_year_means(price, MARKET_TZ)

    assert means.columns.tolist() == list(range(1, 13))
    assert means.index.tolist() == [2024, 2025]
    assert means.loc[2024, 12] == 10.0
    assert means.loc[2025, 1] == 20.0          # includes 2024-12-31 23:00 UTC
    assert np.isnan(means.loc[2025, 12])


def test_spike_threshold_is_the_mean_plus_three_standard_deviations_of_the_672_hours_before():
    price = quiet_then(30.0)

    threshold = spike_threshold(price, WINDOW, 3.0)

    assert threshold.iloc[:WINDOW].isna().all()
    assert threshold.iloc[WINDOW] == pytest.approx(15.0 + 3.0 * np.sqrt(25.0 * 672 / 671))


def test_spike_flags_marks_a_price_above_the_threshold_and_not_one_below():
    assert not spike_flags(quiet_then(30.0), WINDOW, 3.0).iloc[WINDOW]
    assert spike_flags(quiet_then(31.0), WINDOW, 3.0).iloc[WINDOW]


def test_spike_flags_does_not_judge_the_hours_without_a_full_window():
    price = quiet_then()
    price.iloc[100] = 5000.0

    flags = spike_flags(price, WINDOW, 3.0)

    assert not flags.any()


def test_spike_flags_judges_an_hour_only_on_the_hours_before_it():
    early = spike_flags(quiet_then(31.0, 10.0, 20.0), WINDOW, 3.0)
    late = spike_flags(quiet_then(31.0, 9000.0, -9000.0), WINDOW, 3.0)

    assert early.iloc[:WINDOW + 1].tolist() == late.iloc[:WINDOW + 1].tolist()


def test_spike_flags_marks_no_price_drop():
    assert not spike_flags(quiet_then(-500.0), WINDOW, 3.0).iloc[WINDOW]


def test_spike_threshold_is_empty_while_the_window_holds_an_empty_price():
    price = quiet_then(31.0)
    price.iloc[300] = np.nan

    assert np.isnan(spike_threshold(price, WINDOW, 3.0).iloc[WINDOW])
    assert not spike_flags(price, WINDOW, 3.0).iloc[WINDOW]


def test_negative_flags_marks_prices_below_zero_and_not_zero():
    price = pd.Series([-0.01, 0.0, 0.01, -500.0], index=hours("2025-06-02", "2025-06-03")[:4])

    assert negative_flags(price).tolist() == [True, False, False, True]


def test_count_zero_counts_prices_of_exactly_zero():
    price = pd.Series([-1.0, 0.0, 0.0, 0.01], index=hours("2025-06-02", "2025-06-03")[:4])

    assert count_zero(price) == 2


def test_flag_counts_counts_per_local_year_month_and_hour():
    index = hours("2024-12-31", "2025-01-02")
    price = pd.Series(1.0, index=index)
    price[pd.Timestamp("2024-12-31 12:00", tz="UTC")] = -1.0    # 13:00 on 31 Dec 2024
    price[pd.Timestamp("2024-12-31 23:00", tz="UTC")] = -1.0    # 00:00 on 1 Jan 2025
    price[pd.Timestamp("2025-01-01 12:00", tz="UTC")] = -1.0    # 13:00 on 1 Jan 2025

    counts = flag_counts(negative_flags(price), MARKET_TZ)

    assert counts["year"].to_dict() == {2024: 1, 2025: 2}
    assert counts["month"].index.tolist() == list(range(1, 13))
    assert counts["month"][1] == 2
    assert counts["month"][12] == 1
    assert counts["month"].sum() == 3
    assert counts["hour"].index.tolist() == list(range(24))
    assert counts["hour"][13] == 2
    assert counts["hour"][0] == 1
    assert counts["hour"].sum() == 3


def test_flag_counts_puts_both_hours_2_of_a_25_hour_day_under_hour_2():
    price = pd.Series(-1.0, index=hours("2025-10-26", "2025-10-27"))

    counts = flag_counts(negative_flags(price), MARKET_TZ)

    assert counts["hour"][2] == 2
    assert counts["hour"].sum() == 25


def test_month_means_divides_the_hours_of_a_month_by_the_years_it_occurs_in():
    index = hours("2024-12-01", "2026-02-01")       # December 2024 to January 2026
    price = pd.Series(1.0, index=index)
    price[pd.Timestamp("2025-01-10 12:00", tz="UTC")] = -1.0
    price[pd.Timestamp("2025-01-11 12:00", tz="UTC")] = -1.0
    price[pd.Timestamp("2025-01-12 12:00", tz="UTC")] = -1.0
    price[pd.Timestamp("2026-01-10 12:00", tz="UTC")] = -1.0
    price[pd.Timestamp("2025-06-10 12:00", tz="UTC")] = -1.0

    means = month_means(negative_flags(price), price.notna(), MARKET_TZ)

    assert means.index.tolist() == list(range(1, 13))
    assert means.loc[1].tolist() == [4, 2, 2.0]     # hours, years, mean_per_year
    assert means.loc[6].tolist() == [1, 1, 1.0]
    assert means.loc[12].tolist() == [0, 2, 0.0]


def test_month_means_counts_a_year_only_when_the_month_has_a_judged_hour():
    index = hours("2024-12-01", "2026-02-01")
    price = pd.Series(-1.0, index=index)
    judged = pd.Series(index >= market_time("2025-01-01"), index=index)
    flags = negative_flags(price) & judged

    means = month_means(flags, judged, MARKET_TZ)

    assert means.loc[12, "years"] == 1              # December 2024 is not judged
    assert means.loc[12, "hours"] == 31 * 24
    assert means.loc[12, "mean_per_year"] == 31 * 24
    assert means.loc[1, "years"] == 2


def test_month_means_is_empty_for_a_month_that_is_not_in_the_data():
    price = pd.Series(-1.0, index=hours("2025-01-01", "2025-03-01"))

    means = month_means(negative_flags(price), price.notna(), MARKET_TZ)

    assert means.loc[7, "years"] == 0
    assert np.isnan(means.loc[7, "mean_per_year"])
    assert means.loc[2, "mean_per_year"] == 28 * 24


def test_flag_summary_gives_the_share_and_the_delivery_days_with_a_flag():
    index = hours("2025-06-02", "2025-06-06")                   # four days, 96 hours
    price = pd.Series(1.0, index=index)
    price.iloc[[0, 1, 2, 30, 31, 95]] = -1.0                    # on days 1, 2 and 4
    flags = negative_flags(price)

    summary = flag_summary(flags, judged_hours=96, market_tz=MARKET_TZ)

    assert summary["hours_judged"] == 96
    assert summary["hours_flagged"] == 6
    assert summary["share_percent"] == pytest.approx(6.25)
    assert summary["days_flagged"] == 3
