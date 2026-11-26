"""The leakage rule: what a model may see when it forecasts delivery day D.

The forecast is made on day D-1 before the 12:00 gate closure (PROJECT_CONTEXT
section 5). Three kinds of columns are known up to three different moments:

    price               through the end of D-1
    day-ahead columns   through the end of D, because a day-ahead forecast of
                        load, wind or solar for D is published on D-1
    delayed columns     through the end of D-2, the actual load

Each moment is 00:00 of a calendar day in market time. The weather forecast
is its own table with a fourth cut: through the end of D, and only from a
model run that started at or before the run hour on D-1 in UTC.

A model receives a DayInputs object and nothing else. The rows after a cut
are not in it. Tables have a UTC index.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from epf.data.resolution import check_utc_index


@dataclass(frozen=True)
class Columns:
    """The table columns under each cut. A zone need not have every listed column."""

    price: str
    day_ahead: tuple[str, ...]
    delayed: tuple[str, ...]


@dataclass(frozen=True)
class WeatherRule:
    """The columns of the weather table and the newest model run a forecast may use."""

    columns: tuple[str, ...]   # the weather variables
    run_column: str            # holds the start of the model run of each row, in UTC
    run_hour_utc: int          # the run of this hour on D-1 is the newest one known for D


@dataclass(frozen=True)
class DayInputs:
    """Everything a model may use for one delivery day."""

    delivery_day: date                # day D
    target_index: pd.DatetimeIndex    # the market time units of D, in UTC
    prices: pd.Series                 # before 00:00 market time on D
    day_ahead: pd.DataFrame           # before 00:00 market time on D+1
    delayed: pd.DataFrame             # before 00:00 market time on D-1
    market_tz: str
    # Hourly, before 00:00 market time on D+1, from runs up to the run hour on D-1.
    # Without columns when no weather table was given.
    weather: pd.DataFrame = field(default_factory=pd.DataFrame)


def cut_columns(config: dict) -> Columns:
    """Return the columns under each cut, as listed in the backtest section of the config."""
    backtest = config["backtest"]
    return Columns(price=backtest["price_column"],
                   day_ahead=tuple(backtest["day_ahead_columns"]),
                   delayed=tuple(backtest["delayed_columns"]))


def weather_rule(config: dict) -> WeatherRule:
    """Return the weather columns, the run column and the run hour from the config.

    The run hour is the one the download asks for (open_meteo.run_hour_utc).
    """
    return WeatherRule(columns=tuple(config["open_meteo"]["variables"]),
                       run_column=config["backtest"]["weather_run_column"],
                       run_hour_utc=config["open_meteo"]["run_hour_utc"])


def check_columns(table: pd.DataFrame, columns: Columns) -> None:
    """Refuse a table whose columns are not all placed under a cut.

    Raises ValueError when the price column is missing, or when the table has
        a column that the config lists under no cut. Such a column is never
        handed to a model by default.
    """
    if columns.price not in table.columns:
        raise ValueError(f"The table has no column '{columns.price}'.")
    known = {columns.price, *columns.day_ahead, *columns.delayed}
    unknown = [column for column in table.columns if column not in known]
    if unknown:
        raise ValueError(f"Columns that the config lists under no cut: {unknown}.")


def day_inputs(table: pd.DataFrame, day_start: pd.Timestamp, day_end: pd.Timestamp,
               target_index: pd.DatetimeIndex, columns: Columns,
               history_days: int | None = None, weather: pd.DataFrame | None = None,
               rule: WeatherRule | None = None) -> DayInputs:
    """Cut a table to what is known when delivery day D is forecast.

    Input: a table with a UTC index, 00:00 in market time on D and on D+1,
        the market time units of D in UTC, the columns under each cut, and
        the number of days of history to keep. None keeps every row from the
        first one. Optionally the weather table with a UTC index, and its rule.
    Output: the inputs of the day. Each part is a copy, so writing into it
        does not change the table.
    Raises ValueError when an index is not UTC, sorted and free of repeats,
        when check_columns or check_weather refuses a table.
    """
    check_utc_index(table)
    check_columns(table, columns)
    day = day_start.date()
    previous_day_start = pd.Timestamp(day - timedelta(days=1), tz=day_start.tz)
    first = None
    if history_days is not None:
        first = pd.Timestamp(day - timedelta(days=history_days), tz=day_start.tz)
        table = table[table.index >= first]
    known_weather = pd.DataFrame()
    if weather is not None:
        known_weather = cut_weather(weather, day, day_end, rule, first)
    return DayInputs(
        delivery_day=day,
        target_index=target_index,
        prices=table.loc[table.index < day_start, columns.price],
        day_ahead=table.loc[table.index < day_end, _present(table, columns.day_ahead)],
        delayed=table.loc[table.index < previous_day_start, _present(table, columns.delayed)],
        market_tz=str(day_start.tz),
        weather=known_weather,
    )


def check_weather(weather: pd.DataFrame, rule: WeatherRule | None) -> None:
    """Refuse a weather table that the rule does not describe.

    Raises ValueError when there is no rule, when the table lacks the run
        column, or when it has a column that the rule does not list.
    """
    if rule is None:
        raise ValueError("A weather table needs a weather rule.")
    if rule.run_column not in weather.columns:
        raise ValueError(f"The weather table has no column '{rule.run_column}'.")
    known = {*rule.columns, rule.run_column}
    unknown = [column for column in weather.columns if column not in known]
    if unknown:
        raise ValueError(f"Weather columns that the rule does not list: {unknown}.")


def cut_weather(weather: pd.DataFrame, day: date, day_end: pd.Timestamp,
                rule: WeatherRule | None, first: pd.Timestamp | None) -> pd.DataFrame:
    """Cut the weather table to what is known when delivery day D is forecast.

    Input: the weather table with a UTC index, the date of D, 00:00 in market
        time on D+1, the rule, and the first moment to keep (None for all).
    Output: a copy of the rows before 00:00 on D+1 whose model run started
        at or before the run hour on D-1 in UTC. The run column stays, so
        the run of every value can be read.
    Raises ValueError when the index is not UTC, sorted and free of repeats,
        or when check_weather refuses the table.
    """
    check_utc_index(weather)
    check_weather(weather, rule)
    newest_run = (pd.Timestamp(day - timedelta(days=1), tz="UTC")
                  + timedelta(hours=rule.run_hour_utc))
    known = (weather.index < day_end) & (weather[rule.run_column] <= newest_run)
    if first is not None:
        known &= weather.index >= first
    return weather.loc[known].copy()


def _present(table: pd.DataFrame, names: tuple[str, ...]) -> list[str]:
    """Return the columns of a table that are among names, in the order of the table."""
    return [column for column in table.columns if column in names]
