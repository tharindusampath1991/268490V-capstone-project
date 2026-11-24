"""The backtest loop: one forecast per delivery day, from inputs cut to that day.

For every delivery day the loop cuts the table with day_inputs (see
epf.evaluation.cutoff), hands the result to the model and takes back one
forecast per market time unit. The actual prices of the day stay here and are
set beside the forecast only after the model has answered.

A model has two methods:
    fit(inputs)      called on the first scored day and then every
                     refit_every_days delivery days
    predict(inputs)  returns a price series on inputs.target_index

Tables have a UTC index. Delivery days are defined in market time.
"""

import time
from collections.abc import Callable
from typing import Protocol

import pandas as pd

from epf.evaluation.cutoff import Columns, DayInputs, check_columns, day_inputs

FORECAST = "forecast"
ACTUAL = "actual"

Day = tuple[pd.Timestamp, pd.Timestamp]   # 00:00 market time on D and on D+1
MakeIndex = Callable[[pd.Timestamp, pd.Timestamp], pd.DatetimeIndex]


class Model(Protocol):
    """What the backtest loop asks of a model."""

    def fit(self, inputs: DayInputs) -> None: ...

    def predict(self, inputs: DayInputs) -> pd.Series: ...


def run_days(table: pd.DataFrame, days: list[Day], make_index: MakeIndex, model: Model,
             columns: Columns, refit_every_days: int,
             history_days: int | None = None) -> tuple[pd.DataFrame, float]:
    """Forecast every delivery day of a list and set the actual prices beside the forecasts.

    Input: a table with a UTC index, the delivery days as (day start, next
        day start) in market time, the function that gives the market time
        units of a day (hourly_index or quarter_hour_index), the model, the
        columns under each cut, the number of days between two fits, and the
        days of history a model receives (None for all).
    Output: a frame with a UTC index and the columns forecast and actual,
        one row per market time unit of the days, then the seconds the loop
        took. The time covers the cuts, fit and predict.
    Raises ValueError when a table column stands under no cut or a forecast
        is not on the market time units of its day.
    """
    check_columns(table, columns)
    forecasts = []
    started = time.perf_counter()
    for number, (day_start, day_end) in enumerate(days):
        inputs = day_inputs(table, day_start, day_end, make_index(day_start, day_end), columns,
                            history_days)
        if number % refit_every_days == 0:
            model.fit(inputs)
        forecasts.append(checked_forecast(model.predict(inputs), inputs.target_index))
    seconds = time.perf_counter() - started

    forecast = pd.concat(forecasts)
    actual = table.loc[forecast.index, columns.price]
    return pd.DataFrame({FORECAST: forecast, ACTUAL: actual}), seconds


def checked_forecast(forecast: pd.Series, target_index: pd.DatetimeIndex) -> pd.Series:
    """Return a forecast as numbers after checking that it answers the right market time units.

    Raises ValueError when the forecast is not a series on exactly target_index.
    """
    if not isinstance(forecast, pd.Series) or not forecast.index.equals(target_index):
        raise ValueError("The forecast does not have the index of the market time units "
                         f"of the delivery day that starts at {target_index[0]}.")
    return forecast.astype(float).rename(FORECAST)
