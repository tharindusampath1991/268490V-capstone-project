"""Forecast metrics: MAE, RMSE, relative MAE, pinball loss, coverage and daily losses.

Every metric is pooled: it is one mean over all market time units it is
given, so each market time unit has the same weight. Prices are in EUR/MWh
and may be negative, so no metric divides by a price. Series have a UTC index.

An empty value or a forecast on other timestamps raises ValueError. Nothing
is skipped.
"""

import numpy as np
import pandas as pd


def mae(actual: pd.Series, forecast: pd.Series) -> float:
    """Return the mean absolute error, in the unit of the prices."""
    return float(_errors(actual, forecast).abs().mean())


def rmse(actual: pd.Series, forecast: pd.Series) -> float:
    """Return the root of the mean squared error, in the unit of the prices."""
    return float(np.sqrt((_errors(actual, forecast) ** 2).mean()))


def relative_mae(actual: pd.Series, forecast: pd.Series, reference: pd.Series) -> float:
    """Return the MAE of a forecast divided by the MAE of a reference forecast.

    Input: three series on the same timestamps. The reference is the
        seasonal naive forecast.
    Output: below 1 when the forecast is better than the reference.
    Raises ValueError when the reference has no error, since the ratio does
        not exist then.
    """
    reference_mae = mae(actual, reference)
    if reference_mae == 0:
        raise ValueError("The reference forecast has no error, so relative MAE is not defined.")
    return mae(actual, forecast) / reference_mae


def pinball_loss(actual: pd.Series, forecast: pd.Series, level: float) -> float:
    """Return the mean pinball loss of a quantile forecast.

    Input: actual values, the forecast of the quantile, and its level
        between 0 and 1, for example 0.1 for the 10% quantile.
    Output: the mean of max(level * e, (level - 1) * e) with e = actual
        minus forecast. A forecast that is too low costs level per unit, one
        that is too high costs 1 - level.
    Raises ValueError when the level is not between 0 and 1.
    """
    if not 0 < level < 1:
        raise ValueError(f"The level must lie between 0 and 1. It is {level}.")
    errors = _errors(actual, forecast)
    return float(np.maximum(level * errors, (level - 1) * errors).mean())


def mean_pinball_loss(actual: pd.Series, forecasts: dict[float, pd.Series]) -> float:
    """Return the mean of the pinball losses of several quantile forecasts.

    Input: actual values, and the quantile forecasts by level.
    """
    losses = [pinball_loss(actual, forecast, level) for level, forecast in forecasts.items()]
    return float(np.mean(losses))


def coverage(actual: pd.Series, low: pd.Series, high: pd.Series) -> float:
    """Return the share of actual values inside the interval from low to high.

    Input: three series on the same timestamps. A value on a bound counts
        as inside.
    Output: a share between 0 and 1.
    """
    _errors(actual, low)
    _errors(actual, high)
    return float(((actual >= low) & (actual <= high)).mean())


def daily_losses(actual: pd.Series, forecast: pd.Series, market_tz: str) -> pd.DataFrame:
    """Return the losses of each delivery day, for the Diebold-Mariano test.

    Input: actual values and forecasts with a UTC index, and the market time
        zone that defines the delivery days.
    Output: one row per delivery day with
        mtus   the number of market time units of the day
        mae    the mean absolute error of the day
        mse    the mean squared error of the day
        The pooled MAE is the sum of mae * mtus divided by the sum of mtus.
    """
    errors = _errors(actual, forecast)
    days = pd.Index(errors.index.tz_convert(market_tz).date, name="delivery_day")
    return pd.DataFrame({
        "mtus": errors.groupby(days).size(),
        "mae": errors.abs().groupby(days).mean(),
        "mse": (errors ** 2).groupby(days).mean(),
    })


def _errors(actual: pd.Series, forecast: pd.Series) -> pd.Series:
    """Return actual minus forecast after checking that the two can be compared.

    Raises ValueError when the series are empty, stand on different
        timestamps or hold an empty value.
    """
    if len(actual) == 0:
        raise ValueError("The series hold no value.")
    if not actual.index.equals(forecast.index):
        raise ValueError("The forecast does not have the index of the actual values.")
    if actual.isna().any() or forecast.isna().any():
        raise ValueError("The actual values or the forecast hold an empty value.")
    return actual - forecast
