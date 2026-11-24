"""The leakage rule: what a model may see when it forecasts delivery day D.

The forecast is made on day D-1 before the 12:00 gate closure (PROJECT_CONTEXT
section 5). Three kinds of columns are known up to three different moments:

    price               through the end of D-1
    day-ahead columns   through the end of D, because a day-ahead forecast of
                        load, wind or solar for D is published on D-1
    delayed columns     through the end of D-2, the actual load

Each moment is 00:00 of a calendar day in market time. A model receives a
DayInputs object and nothing else. The rows after a cut are not in it.
Tables have a UTC index.
"""

from dataclasses import dataclass
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
class DayInputs:
    """Everything a model may use for one delivery day."""

    delivery_day: date                # day D
    target_index: pd.DatetimeIndex    # the market time units of D, in UTC
    prices: pd.Series                 # before 00:00 market time on D
    day_ahead: pd.DataFrame           # before 00:00 market time on D+1
    delayed: pd.DataFrame             # before 00:00 market time on D-1
    market_tz: str


def cut_columns(config: dict) -> Columns:
    """Return the columns under each cut, as listed in the backtest section of the config."""
    backtest = config["backtest"]
    return Columns(price=backtest["price_column"],
                   day_ahead=tuple(backtest["day_ahead_columns"]),
                   delayed=tuple(backtest["delayed_columns"]))


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
               history_days: int | None = None) -> DayInputs:
    """Cut a table to what is known when delivery day D is forecast.

    Input: a table with a UTC index, 00:00 in market time on D and on D+1,
        the market time units of D in UTC, the columns under each cut, and
        the number of days of history to keep. None keeps every row from the
        first one.
    Output: the inputs of the day. Each part is a copy, so writing into it
        does not change the table.
    Raises ValueError when the index is not UTC, sorted and free of repeats,
        or when check_columns refuses the table.
    """
    check_utc_index(table)
    check_columns(table, columns)
    day = day_start.date()
    previous_day_start = pd.Timestamp(day - timedelta(days=1), tz=day_start.tz)
    if history_days is not None:
        first = pd.Timestamp(day - timedelta(days=history_days), tz=day_start.tz)
        table = table[table.index >= first]
    return DayInputs(
        delivery_day=day,
        target_index=target_index,
        prices=table.loc[table.index < day_start, columns.price],
        day_ahead=table.loc[table.index < day_end, _present(table, columns.day_ahead)],
        delayed=table.loc[table.index < previous_day_start, _present(table, columns.delayed)],
        market_tz=str(day_start.tz),
    )


def _present(table: pd.DataFrame, names: tuple[str, ...]) -> list[str]:
    """Return the columns of a table that are among names, in the order of the table."""
    return [column for column in table.columns if column in names]
