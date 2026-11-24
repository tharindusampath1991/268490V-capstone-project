"""Tests for the metrics. Every expected value is worked out by hand in a comment.

They use small synthetic series, no network and no data files.
"""

import pandas as pd
import pytest

from epf.data.market_time import hourly_index
from epf.evaluation.metrics import (
    coverage,
    daily_losses,
    mae,
    mean_pinball_loss,
    pinball_loss,
    relative_mae,
    rmse,
)

MARKET_TZ = "Europe/Berlin"


def series(values: list[float]) -> pd.Series:
    """Hourly values from 2026-07-01 00:00 UTC."""
    index = pd.date_range("2026-07-01", periods=len(values), freq="h", tz="UTC")
    return pd.Series(values, index=index, dtype=float)


# Prices with a negative value and a zero. Errors, actual minus forecast: -2, -5, 4, 6.
ACTUAL = series([10, -20, 0, 50])
FORECAST = series([12, -15, -4, 44])
# Errors of the reference: -4, 10, -8, 17.
REFERENCE = series([14, -30, 8, 33])


def test_mae_is_the_mean_of_the_absolute_errors():
    # (2 + 5 + 4 + 6) / 4 = 17 / 4
    assert mae(ACTUAL, FORECAST) == pytest.approx(4.25)


def test_rmse_is_the_root_of_the_mean_squared_error():
    # (4 + 25 + 16 + 36) / 4 = 20.25, and its root is 4.5
    assert rmse(ACTUAL, FORECAST) == pytest.approx(4.5)


def test_relative_mae_divides_by_the_mae_of_the_reference():
    # reference: (4 + 10 + 8 + 17) / 4 = 9.75, so 4.25 / 9.75 = 17 / 39
    assert relative_mae(ACTUAL, FORECAST, REFERENCE) == pytest.approx(17 / 39)


def test_relative_mae_of_the_reference_itself_is_one():
    assert relative_mae(ACTUAL, REFERENCE, REFERENCE) == 1.0


def test_relative_mae_refuses_a_reference_without_error():
    with pytest.raises(ValueError, match="reference"):
        relative_mae(ACTUAL, FORECAST, ACTUAL)


def test_pinball_loss_weighs_a_forecast_that_is_too_high_by_one_minus_the_level():
    actual = series([10, -20])
    # level 0.1, errors -4 and 10: max(-0.4, 3.6) = 3.6 and max(1.0, -9.0) = 1.0, mean 2.3
    assert pinball_loss(actual, series([14, -30]), 0.1) == pytest.approx(2.3)
    # level 0.9, errors 2 and -10: max(1.8, -0.2) = 1.8 and max(-9.0, 1.0) = 1.0, mean 1.4
    assert pinball_loss(actual, series([8, -10]), 0.9) == pytest.approx(1.4)


def test_pinball_loss_at_the_median_is_half_the_mae():
    # 4.25 / 2
    assert pinball_loss(ACTUAL, FORECAST, 0.5) == pytest.approx(2.125)


@pytest.mark.parametrize("level", [0.0, 1.0, -0.1, 1.5])
def test_pinball_loss_refuses_a_level_outside_zero_to_one(level):
    with pytest.raises(ValueError, match="level"):
        pinball_loss(ACTUAL, FORECAST, level)


def test_mean_pinball_loss_is_the_mean_over_the_levels():
    actual = series([10, -20])
    forecasts = {0.1: series([14, -30]), 0.9: series([8, -10])}

    # (2.3 + 1.4) / 2
    assert mean_pinball_loss(actual, forecasts) == pytest.approx(1.85)


def test_coverage_counts_values_inside_the_interval_with_the_bounds_included():
    low = series([5, -20, 1, 40])
    high = series([15, -10, 9, 49])

    # 10 is inside, -20 is on the lower bound, 0 is below 1, 50 is above 49: 2 of 4
    assert coverage(ACTUAL, low, high) == pytest.approx(0.5)


def test_daily_losses_group_by_delivery_day_in_market_time():
    # 2026-10-25 has 25 hours in market time, 2026-10-26 has 24.
    index = hourly_index(pd.Timestamp("2026-10-25", tz=MARKET_TZ),
                         pd.Timestamp("2026-10-27", tz=MARKET_TZ))
    actual = pd.Series([-30.0] * 25 + [40.0] * 24, index=index)
    forecast = pd.Series([-32.0] * 25 + [44.0] * 24, index=index)   # errors 2 and -4

    daily = daily_losses(actual, forecast, MARKET_TZ)

    assert [str(day) for day in daily.index] == ["2026-10-25", "2026-10-26"]
    assert daily["mtus"].tolist() == [25, 24]
    assert daily["mae"].tolist() == pytest.approx([2.0, 4.0])
    assert daily["mse"].tolist() == pytest.approx([4.0, 16.0])


def test_pooled_mae_follows_from_the_daily_losses_and_is_not_the_mean_of_days():
    index = hourly_index(pd.Timestamp("2026-10-25", tz=MARKET_TZ),
                         pd.Timestamp("2026-10-27", tz=MARKET_TZ))
    actual = pd.Series([-30.0] * 25 + [40.0] * 24, index=index)
    forecast = pd.Series([-32.0] * 25 + [44.0] * 24, index=index)

    daily = daily_losses(actual, forecast, MARKET_TZ)
    from_days = (daily["mae"] * daily["mtus"]).sum() / daily["mtus"].sum()

    # (25 * 2 + 24 * 4) / 49 = 146 / 49, while the mean of the two days is 3
    assert mae(actual, forecast) == pytest.approx(146 / 49)
    assert from_days == pytest.approx(146 / 49)
    assert daily["mae"].mean() == pytest.approx(3.0)


@pytest.mark.parametrize("metric", [mae, rmse])
def test_point_metrics_refuse_an_empty_value(metric):
    with pytest.raises(ValueError, match="empty"):
        metric(ACTUAL, series([12, float("nan"), -4, 44]))


@pytest.mark.parametrize("metric", [mae, rmse])
def test_point_metrics_refuse_a_forecast_on_other_timestamps(metric):
    with pytest.raises(ValueError, match="index"):
        metric(ACTUAL, FORECAST.iloc[:3])


def test_metrics_refuse_a_series_without_values():
    with pytest.raises(ValueError, match="no value"):
        mae(ACTUAL.iloc[:0], FORECAST.iloc[:0])
