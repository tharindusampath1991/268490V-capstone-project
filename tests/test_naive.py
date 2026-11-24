"""Tests for the seasonal naive forecast.

Each history is a running number per market time unit, starting at 0 on its
first day. A forecast value therefore names the position of the price it was
taken from. They use no network and no data files.
"""

from datetime import date

import pandas as pd
import pytest

from epf.data.market_time import hourly_index, quarter_hour_index
from epf.evaluation.cutoff import DayInputs
from epf.models.naive import SeasonalNaive, seasonal_naive

MARKET_TZ = "Europe/Berlin"


def market_time(day: str) -> pd.Timestamp:
    """00:00 in market time on a day."""
    return pd.Timestamp(day, tz=MARKET_TZ)


def running_prices(first_day: str, delivery_day: str, make_index=hourly_index) -> pd.Series:
    """Prices 0, 1, 2, ... from first_day up to the start of delivery_day."""
    index = make_index(market_time(first_day), market_time(delivery_day))
    return pd.Series(range(len(index)), index=index, dtype=float)


def targets(delivery_day: str, next_day: str, make_index=hourly_index) -> pd.DatetimeIndex:
    """The market time units of one delivery day."""
    return make_index(market_time(delivery_day), market_time(next_day))


def test_normal_day_takes_each_price_of_the_same_hour_seven_days_before():
    prices = running_prices("2026-06-20", "2026-07-01")
    target = targets("2026-07-01", "2026-07-02")

    forecast = seasonal_naive(prices, target, MARKET_TZ, lag_days=7)

    # 2026-06-24 is the fifth day of the history, so its hours are 96 to 119.
    assert forecast.tolist() == list(range(96, 120))
    assert forecast.index.equals(target)


def test_day_with_25_hours_uses_the_02_price_of_d7_for_both_02_hours():
    prices = running_prices("2026-10-18", "2026-10-25")
    target = targets("2026-10-25", "2026-10-26")

    forecast = seasonal_naive(prices, target, MARKET_TZ, lag_days=7)

    # Local hours of 2026-10-25: 0, 1, 2, 2, 3, ..., 23. D-7 has hours 0 to 23.
    assert len(target) == 25
    assert forecast.tolist() == [0, 1, 2, 2] + list(range(3, 24))


def test_d7_with_25_hours_gives_02_the_second_02_price_168_hours_back():
    prices = running_prices("2026-10-25", "2026-11-01")
    target = targets("2026-11-01", "2026-11-02")

    forecast = seasonal_naive(prices, target, MARKET_TZ, lag_days=7)

    # 2026-10-25 holds 25 prices: 0 and 1, the first 02 hour at 2, the second at 3,
    # then hour 3 at 4 up to hour 23 at 24.
    assert forecast.tolist() == [0, 1] + list(range(3, 25))


def test_day_with_23_hours_leaves_the_02_price_of_d7_unused():
    prices = running_prices("2026-03-22", "2026-03-29")
    target = targets("2026-03-29", "2026-03-30")

    forecast = seasonal_naive(prices, target, MARKET_TZ, lag_days=7)

    # Local hours of 2026-03-29: 0, 1, 3, 4, ..., 23.
    assert len(target) == 23
    assert forecast.tolist() == [0, 1] + list(range(3, 24))


def test_d7_with_23_hours_gives_02_the_01_price_168_hours_back():
    prices = running_prices("2026-03-29", "2026-04-05")
    target = targets("2026-04-05", "2026-04-06")

    forecast = seasonal_naive(prices, target, MARKET_TZ, lag_days=7)

    # 2026-03-29 holds 23 prices: hours 0 and 1 at 0 and 1, hour 3 at 2 up to hour 23 at 22.
    # Hour 02 does not exist there. 168 hours before 02:00 on 2026-04-05 is 01:00.
    assert forecast.tolist() == [0, 1, 1] + list(range(2, 23))


def test_quarter_hour_day_takes_the_same_quarter_hour_seven_days_before():
    prices = running_prices("2026-06-24", "2026-07-01", quarter_hour_index)
    target = targets("2026-07-01", "2026-07-02", quarter_hour_index)

    forecast = seasonal_naive(prices, target, MARKET_TZ, lag_days=7)

    assert len(target) == 96
    assert forecast.tolist() == list(range(96))


def test_quarter_hour_day_with_25_hours_repeats_the_four_quarters_of_02():
    prices = running_prices("2026-10-18", "2026-10-25", quarter_hour_index)
    target = targets("2026-10-25", "2026-10-26", quarter_hour_index)

    forecast = seasonal_naive(prices, target, MARKET_TZ, lag_days=7)

    # Hours 0 to 2 are quarters 0 to 11. The second 02 hour takes quarters 8 to 11 again.
    assert len(target) == 100
    assert forecast.tolist() == list(range(12)) + list(range(8, 96))


def test_forecast_is_empty_when_the_history_does_not_reach_back_seven_days():
    prices = running_prices("2026-06-28", "2026-07-01")
    target = targets("2026-07-01", "2026-07-02")

    forecast = seasonal_naive(prices, target, MARKET_TZ, lag_days=7)

    assert len(forecast) == 24
    assert forecast.isna().all()


def test_lag_days_sets_how_many_days_back_the_price_is_taken():
    prices = running_prices("2026-06-29", "2026-07-01")
    target = targets("2026-07-01", "2026-07-02")

    forecast = seasonal_naive(prices, target, MARKET_TZ, lag_days=1)

    assert forecast.tolist() == list(range(24, 48))


def test_negative_prices_pass_through_unchanged():
    prices = -running_prices("2026-06-24", "2026-07-01") - 0.5
    target = targets("2026-07-01", "2026-07-02")

    forecast = seasonal_naive(prices, target, MARKET_TZ, lag_days=7)

    assert forecast.tolist() == pytest.approx([-(hour + 0.5) for hour in range(24)])


def test_model_predicts_the_seasonal_naive_forecast_from_the_day_inputs():
    prices = running_prices("2026-06-20", "2026-07-01")
    target = targets("2026-07-01", "2026-07-02")
    inputs = DayInputs(delivery_day=date(2026, 7, 1), target_index=target, prices=prices,
                       day_ahead=pd.DataFrame(index=prices.index),
                       delayed=pd.DataFrame(index=prices.index), market_tz=MARKET_TZ)
    model = SeasonalNaive(lag_days=7)

    model.fit(inputs)
    forecast = model.predict(inputs)

    assert forecast.tolist() == list(range(96, 120))
    assert model.name == "naive"
    assert model.params == {"lag_days": 7}
