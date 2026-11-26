"""Features for the LightGBM model, built from the cut inputs of one delivery day.

The builder reads a DayInputs object (epf.evaluation.cutoff) and nothing else.
build_features gets it from day_inputs for every delivery day, so the cuts of
the leakage rule are applied there and are not repeated here.

One row per market time unit of the delivery day D, with a UTC index. The
price of D is never in the frame. The groups, switched on in features.groups
of the config:

    price        the price at the same wall-clock time some days before, and
                 statistics of the prices of D-1
    calendar     hour, quarter of the hour on the 15-minute grid, weekday and
                 a holiday mark, all in market time
    forecasts    one group per entry of features.forecasts, for example the
                 wind forecast as the sum of onshore and offshore: its value
                 at the target time and at the same time some days before
    actual_load  the delayed columns at the same time some days before
    weather      the weather forecast of the hour

A lag is lined up with source_times of epf.models.naive: the same wall-clock
time in market time, or a whole number of 24 hours back where that time is
missing or double on a clock-change day.

Nothing is filled. A feature is empty when its source value is empty, lies
before the start of the table or behind a cut, or when the zone does not have
the column. No row is dropped. Every zone gets the same columns.
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from epf.evaluation.cutoff import Columns, DayInputs, WeatherRule, day_inputs
from epf.models.naive import source_times

PRICE = "price"
CALENDAR = "calendar"
ACTUAL_LOAD = "actual_load"
WEATHER = "weather"
ONE_HOUR = timedelta(hours=1)

# Statistics of the prices of D-1. Mean, min and max are empty when one of those prices is.
DAY_STATS: dict[str, Callable[[pd.Series], float]] = {
    "mean": lambda prices: prices.mean(skipna=False),
    "min": lambda prices: prices.min(skipna=False),
    "max": lambda prices: prices.max(skipna=False),
    "last": lambda prices: prices.iloc[-1],
}

Day = tuple[pd.Timestamp, pd.Timestamp]   # 00:00 market time on D and on D+1
MakeIndex = Callable[[pd.Timestamp, pd.Timestamp], pd.DatetimeIndex]


@dataclass(frozen=True)
class FeatureSettings:
    """What the builder makes. Lags are in days."""

    groups: tuple[str, ...]                 # the groups that are built
    price_lag_days: tuple[int, ...]
    price_day_stats: tuple[str, ...]        # keys of DAY_STATS
    forecasts: dict[str, tuple[str, ...]]   # group name to the day-ahead columns summed into it
    forecast_lag_days: tuple[int, ...]      # besides the value at the target time
    delayed: tuple[str, ...]                # the columns under the D-2 cut
    delayed_lag_days: tuple[int, ...]
    weather: tuple[str, ...]                # the weather columns
    weather_hour_before: tuple[str, ...]    # weather columns that hold the mean of the hour
                                            # before their timestamp


def feature_settings(config: dict) -> FeatureSettings:
    """Return the feature settings of the config.

    Input: the config dictionary. The groups, lags and forecast groups come
        from features, the delayed columns from backtest.delayed_columns and
        the weather columns from open_meteo.variables.
    Raises ValueError for settings that check_settings refuses.
    """
    features = config["features"]
    settings = FeatureSettings(
        groups=tuple(features["groups"]),
        price_lag_days=tuple(features["price_lag_days"]),
        price_day_stats=tuple(features["price_day_stats"]),
        forecasts={name: tuple(columns) for name, columns in features["forecasts"].items()},
        forecast_lag_days=tuple(features["forecast_lag_days"]),
        delayed=tuple(config["backtest"]["delayed_columns"]),
        delayed_lag_days=tuple(features["actual_load_lag_days"]),
        weather=tuple(config["open_meteo"]["variables"]),
        weather_hour_before=tuple(features["weather_hour_before"]),
    )
    check_settings(settings, config["backtest"]["day_ahead_columns"])
    return settings


def check_settings(settings: FeatureSettings, day_ahead_columns: Collection[str]) -> None:
    """Refuse settings that the builder cannot serve.

    Input: the settings and the columns under the day-ahead cut.
    Raises ValueError for a group or a statistic that does not exist, for a
        lag below one day, for a forecast column that is not under the
        day-ahead cut, and for an hour-before column that is not a weather column.
    """
    known_groups = {PRICE, CALENDAR, ACTUAL_LOAD, WEATHER, *settings.forecasts}
    problems = [f"unknown group '{group}'" for group in settings.groups
                if group not in known_groups]
    problems += [f"unknown statistic '{name}'" for name in settings.price_day_stats
                 if name not in DAY_STATS]
    lag_lists = {"price_lag_days": settings.price_lag_days,
                 "forecast_lag_days": settings.forecast_lag_days,
                 "actual_load_lag_days": settings.delayed_lag_days}
    problems += [f"{name} holds a lag below 1 day" for name, lags in lag_lists.items()
                 if any(lag < 1 for lag in lags)]
    problems += [f"forecast column '{column}' is not under the day-ahead cut"
                 for columns in settings.forecasts.values() for column in columns
                 if column not in day_ahead_columns]
    problems += [f"'{column}' is not a weather column" for column in settings.weather_hour_before
                 if column not in settings.weather]
    if problems:
        raise ValueError("Feature settings: " + "; ".join(problems) + ".")


def history_days(settings: FeatureSettings) -> int:
    """Return the days before D that the features read.

    Output: the longest lag of the settings, and at least 1, because the
        statistics of the day before read D-1.
    """
    lags = [*settings.price_lag_days, *settings.forecast_lag_days, *settings.delayed_lag_days]
    return max([1, *lags])


def build_features(table: pd.DataFrame, days: list[Day], make_index: MakeIndex,
                   columns: Columns, settings: FeatureSettings, holidays: Collection[date],
                   weather: pd.DataFrame | None = None,
                   rule: WeatherRule | None = None) -> pd.DataFrame:
    """Return the features of a list of delivery days.

    Input: a table with a UTC index, the delivery days as (day start, next
        day start) in market time, the function that gives the market time
        units of a day (hourly_index or quarter_hour_index), the columns
        under each cut, the settings, the holiday dates of the zone, and
        optionally the weather table with a UTC index, and its rule.
    Output: one row per market time unit of the days, in UTC. Each day is
        built from day_inputs, so from what is known when it is forecast.
    Raises ValueError when day_inputs refuses a table.
    """
    history = history_days(settings)
    frames = []
    for day_start, day_end in days:
        inputs = day_inputs(table, day_start, day_end, make_index(day_start, day_end), columns,
                            history, weather, rule)
        frames.append(day_features(inputs, settings, holidays))
    return pd.concat(frames)


def day_features(inputs: DayInputs, settings: FeatureSettings,
                 holidays: Collection[date]) -> pd.DataFrame:
    """Return the features of one delivery day from its cut inputs.

    Input: the inputs of the day, the settings and the holiday dates of the zone.
    Output: one row per market time unit of the day, on inputs.target_index.
    """
    features: dict[str, np.ndarray] = {}
    if PRICE in settings.groups:
        features.update(price_features(inputs, settings))
    if CALENDAR in settings.groups:
        features.update(calendar_features(inputs, holidays))
    for name, columns in settings.forecasts.items():
        if name in settings.groups:
            features.update(forecast_features(inputs, name, columns, settings.forecast_lag_days))
    if ACTUAL_LOAD in settings.groups:
        features.update(delayed_features(inputs, settings))
    if WEATHER in settings.groups:
        features.update(weather_features(inputs, settings))
    return pd.DataFrame(features, index=inputs.target_index)


def lagged(values: pd.Series, inputs: DayInputs, lag_days: int) -> np.ndarray:
    """Return a series at the same wall-clock time some days before each market time unit of D.

    Output: one value per market time unit. Empty where the series has no
        value at that time.
    """
    sources = source_times(inputs.target_index, inputs.market_tz, lag_days)
    return values.reindex(sources).to_numpy(dtype=float)


def price_features(inputs: DayInputs, settings: FeatureSettings) -> dict[str, np.ndarray]:
    """Return the price lags and the statistics of the prices of D-1.

    A statistic is one number per delivery day, repeated on its rows. It
    covers every market time unit of D-1: 23, 24 or 25 hours.
    """
    features = {f"price_lag_{lag}": lagged(inputs.prices, inputs, lag)
                for lag in settings.price_lag_days}
    day_before = pd.Timestamp(inputs.delivery_day - timedelta(days=1), tz=inputs.market_tz)
    prices = inputs.prices[inputs.prices.index >= day_before]
    for name in settings.price_day_stats:
        value = DAY_STATS[name](prices) if len(prices) else np.nan
        features[f"price_d1_{name}"] = np.full(len(inputs.target_index), value, dtype=float)
    return features


def calendar_features(inputs: DayInputs, holidays: Collection[date]) -> dict[str, np.ndarray]:
    """Return hour, quarter of the hour, weekday and the holiday mark, in market time.

    quarter_hour exists only when the market time units are shorter than one
    hour. Weekday 0 is Monday. holiday is 1 when D is among the holiday dates.
    """
    local = inputs.target_index.tz_convert(inputs.market_tz)
    rows = len(local)
    features = {"hour": local.hour.to_numpy()}
    step = local[1] - local[0]
    if step < ONE_HOUR:
        features["quarter_hour"] = local.minute.to_numpy() // (step.seconds // 60)
    features["weekday"] = np.full(rows, inputs.delivery_day.weekday())
    features["holiday"] = np.full(rows, int(inputs.delivery_day in holidays))
    return features


def forecast_features(inputs: DayInputs, name: str, columns: tuple[str, ...],
                      lag_days: tuple[int, ...]) -> dict[str, np.ndarray]:
    """Return one day-ahead forecast at the target time and at its lags.

    Input: the inputs, the feature name and the day-ahead columns that are
        summed into it. A column the zone does not have is left out of the sum.
    Output: empty where one of the summed columns is empty, and everywhere
        when the zone has none of the columns.
    """
    present = [column for column in columns if column in inputs.day_ahead.columns]
    if present:
        total = inputs.day_ahead[present].sum(axis=1, skipna=False)
    else:
        total = pd.Series(np.nan, index=inputs.day_ahead.index)
    features = {name: total.reindex(inputs.target_index).to_numpy(dtype=float)}
    for lag in lag_days:
        features[f"{name}_lag_{lag}"] = lagged(total, inputs, lag)
    return features


def delayed_features(inputs: DayInputs, settings: FeatureSettings) -> dict[str, np.ndarray]:
    """Return the delayed columns at their lags.

    The inputs hold these columns through the end of D-2 only, so a lag of
    one day is always empty.
    """
    features = {}
    for column in settings.delayed:
        values = _column(inputs.delayed, column)
        for lag in settings.delayed_lag_days:
            features[f"{column}_lag_{lag}"] = lagged(values, inputs, lag)
    return features


def weather_features(inputs: DayInputs, settings: FeatureSettings) -> dict[str, np.ndarray]:
    """Return the weather forecast of the hour of each market time unit.

    The weather table is hourly, so on the 15-minute grid a value stands on
    the four quarter-hours of its hour. A column in weather_hour_before holds
    the mean of the hour before its timestamp, so the hour that starts at t
    takes the value stamped t plus one hour. For the last hour of D that
    value lies behind the weather cut and the feature is empty.
    """
    hours = inputs.target_index.floor("h")
    features = {}
    for column in settings.weather:
        moments = hours + ONE_HOUR if column in settings.weather_hour_before else hours
        features[column] = _column(inputs.weather, column).reindex(moments).to_numpy(dtype=float)
    return features


def _column(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a column of a frame, or an empty series when the frame does not have it."""
    if column in frame.columns:
        return frame[column]
    return pd.Series(np.nan, index=pd.DatetimeIndex([], tz="UTC"))
