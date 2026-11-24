"""Seasonal naive forecast: the price of the same local market time unit some days before.

For delivery day D the forecast of a market time unit is the price at the
same wall-clock time in market time lag_days calendar days earlier (7 in the
config). A clock-change day has 23 or 25 hours, so a wall-clock time can be
missing or double on the earlier day. The forecast is then the price exactly
lag_days times 24 hours before the target.

Prices are in EUR/MWh with a UTC index.
"""

from datetime import timedelta

import pandas as pd


def seasonal_naive(prices: pd.Series, target_index: pd.DatetimeIndex, market_tz: str,
                   lag_days: int) -> pd.Series:
    """Return the seasonal naive forecast for the market time units of one delivery day.

    Input: past prices with a UTC index, the market time units to forecast in
        UTC, the market time zone and the lag in calendar days.
    Output: one value per market time unit of target_index. A value is empty
        when the history holds no price at the source time.
    """
    sources = source_times(target_index, market_tz, lag_days)
    return pd.Series(prices.reindex(sources).to_numpy(), index=target_index, name="forecast")


def source_times(target_index: pd.DatetimeIndex, market_tz: str,
                 lag_days: int) -> pd.DatetimeIndex:
    """Return for each target time the time whose price the forecast takes.

    Input: target times in UTC, the market time zone and the lag in days.
    Output: UTC times, one per target. Each is the same wall-clock time in
        market time lag_days earlier. Where that wall-clock time does not
        exist or exists twice, it is lag_days times 24 hours before the target.
    """
    lag = timedelta(days=lag_days)
    wall_clock = target_index.tz_convert(market_tz).tz_localize(None)
    same_wall_clock = (wall_clock - lag).tz_localize(market_tz, ambiguous="NaT",
                                                     nonexistent="NaT").tz_convert("UTC")
    return same_wall_clock.where(same_wall_clock.notna(), target_index - lag)
