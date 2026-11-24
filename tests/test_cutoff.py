"""Tests for the cuts that decide what a model may see for a delivery day.

They use small synthetic tables, no network and no data files.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from epf.data.market_time import hourly_index, quarter_hour_index
from epf.evaluation.cutoff import Columns, cut_columns, day_inputs

MARKET_TZ = "Europe/Berlin"
STEPS = {hourly_index: timedelta(hours=1), quarter_hour_index: timedelta(minutes=15)}
# solar_forecast is listed but not in the table, as for a zone without that column.
COLUMNS = Columns(price="price",
                  day_ahead=("load_forecast", "wind_onshore_forecast", "solar_forecast"),
                  delayed=("actual_load",))


def market_time(day: str | date) -> pd.Timestamp:
    """00:00 in market time on a day."""
    return pd.Timestamp(day, tz=MARKET_TZ)


def day_after(day: str, days: int = 1) -> date:
    """The calendar day some days after a day. A negative number goes back."""
    return date.fromisoformat(day) + timedelta(days=days)


def make_table(first_day: str, end_day: str, make_index=hourly_index) -> pd.DataFrame:
    """A table from first_day up to the start of end_day, every value different."""
    index = make_index(market_time(first_day), market_time(end_day))
    numbers = pd.Series(range(len(index)), index=index, dtype=float)
    return pd.DataFrame({"price": numbers, "load_forecast": numbers + 0.1,
                         "wind_onshore_forecast": numbers + 0.2, "actual_load": numbers + 0.3})


def inputs_for(table: pd.DataFrame, day: str, make_index=hourly_index, history_days=None):
    """The inputs of one delivery day."""
    day_start, day_end = market_time(day), market_time(day_after(day))
    return day_inputs(table, day_start, day_end, make_index(day_start, day_end), COLUMNS,
                      history_days)


def test_prices_end_with_the_last_hour_of_the_day_before():
    inputs = inputs_for(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    assert inputs.prices.index.max() == market_time("2026-07-01") - timedelta(hours=1)
    assert inputs.prices.index.min() == market_time("2026-06-20")


def test_day_ahead_columns_end_with_the_last_hour_of_the_delivery_day():
    inputs = inputs_for(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    assert inputs.day_ahead.index.max() == market_time("2026-07-02") - timedelta(hours=1)
    assert inputs.target_index.isin(inputs.day_ahead.index).all()
    assert list(inputs.day_ahead.columns) == ["load_forecast", "wind_onshore_forecast"]


def test_delayed_columns_end_with_the_last_hour_two_days_before():
    inputs = inputs_for(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    assert inputs.delayed.index.max() == market_time("2026-06-30") - timedelta(hours=1)
    assert list(inputs.delayed.columns) == ["actual_load"]


def test_inputs_name_the_delivery_day_its_market_time_units_and_the_time_zone():
    inputs = inputs_for(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    assert inputs.delivery_day == date(2026, 7, 1)
    assert inputs.target_index.equals(hourly_index(market_time("2026-07-01"),
                                                   market_time("2026-07-02")))
    assert inputs.market_tz == MARKET_TZ


# 2026-10-25 has 25 hours and 2026-03-29 has 23. Each is taken as D, as D-1 and as D-2.
@pytest.mark.parametrize("make_index", [hourly_index, quarter_hour_index])
@pytest.mark.parametrize("day", ["2026-10-25", "2026-10-26", "2026-10-27",
                                 "2026-03-29", "2026-03-30", "2026-03-31"])
def test_cuts_are_midnights_in_market_time_around_a_clock_change(day, make_index):
    table = make_table(str(day_after(day, -10)), str(day_after(day, 3)), make_index)
    step = STEPS[make_index]

    inputs = inputs_for(table, day, make_index)

    assert inputs.prices.index.max() == market_time(day) - step
    assert inputs.day_ahead.index.max() == market_time(day_after(day)) - step
    assert inputs.delayed.index.max() == market_time(day_after(day, -1)) - step


def test_history_days_keeps_only_that_many_days_before_the_delivery_day():
    inputs = inputs_for(make_table("2026-06-20", "2026-07-05"), "2026-07-01", history_days=3)

    assert inputs.prices.index.min() == market_time("2026-06-28")
    assert inputs.day_ahead.index.min() == market_time("2026-06-28")
    assert inputs.delayed.index.min() == market_time("2026-06-28")
    assert inputs.prices.index.max() == market_time("2026-07-01") - timedelta(hours=1)


def test_a_table_column_that_is_in_no_list_is_refused():
    table = make_table("2026-06-20", "2026-07-05").assign(temperature_2m=1.0)

    with pytest.raises(ValueError, match="temperature_2m"):
        inputs_for(table, "2026-07-01")


def test_a_table_without_the_price_column_is_refused():
    table = make_table("2026-06-20", "2026-07-05").drop(columns="price")

    with pytest.raises(ValueError, match="price"):
        inputs_for(table, "2026-07-01")


def test_writing_into_the_inputs_does_not_change_the_table():
    table = make_table("2026-06-20", "2026-07-05")
    before = table.copy()
    inputs = inputs_for(table, "2026-07-01")

    inputs.prices.iloc[:] = -999.0
    inputs.day_ahead.iloc[:, :] = -999.0
    inputs.delayed.iloc[:, :] = -999.0

    pd.testing.assert_frame_equal(table, before)


def test_cut_columns_reads_the_three_groups_from_the_config():
    config = {"backtest": {"price_column": "price", "day_ahead_columns": ["load_forecast"],
                           "delayed_columns": ["actual_load"]}}

    assert cut_columns(config) == Columns(price="price", day_ahead=("load_forecast",),
                                          delayed=("actual_load",))
