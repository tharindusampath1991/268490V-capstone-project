"""Tests for the cuts that decide what a model may see for a delivery day.

They use small synthetic tables, no network and no data files.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from epf.data.market_time import hourly_index, quarter_hour_index
from epf.evaluation.cutoff import Columns, WeatherRule, cut_columns, day_inputs, weather_rule

MARKET_TZ = "Europe/Berlin"
STEPS = {hourly_index: timedelta(hours=1), quarter_hour_index: timedelta(minutes=15)}
# solar_forecast is listed but not in the table, as for a zone without that column.
COLUMNS = Columns(price="price",
                  day_ahead=("load_forecast", "wind_onshore_forecast", "solar_forecast"),
                  delayed=("actual_load",))
WEATHER = WeatherRule(columns=("temperature_2m", "shortwave_radiation"), run_column="run",
                      run_hour_utc=0)


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


def run_time(day: str | date, hour: int = 0) -> pd.Timestamp:
    """The start of the model run of a calendar day at an hour, in UTC."""
    return pd.Timestamp(day, tz="UTC") + timedelta(hours=hour)


def make_weather(first_day: str, end_day: str) -> pd.DataFrame:
    """Hourly weather. The hours of each delivery day come from the 00:00 UTC run of the day before."""
    index = hourly_index(market_time(first_day), market_time(end_day))
    numbers = pd.Series(range(len(index)), index=index, dtype=float)
    delivery_day = index.tz_convert(MARKET_TZ).normalize().tz_localize(None)
    run = (delivery_day - timedelta(days=1)).tz_localize("UTC")
    return pd.DataFrame({"temperature_2m": numbers, "shortwave_radiation": numbers + 0.5,
                         "run": run}, index=index)


def weather_inputs_for(weather: pd.DataFrame, day: str, rule: WeatherRule = WEATHER,
                       history_days=None):
    """The inputs of one delivery day with a weather table."""
    table = make_table(str(day_after(day, -12)), str(day_after(day, 3)))
    day_start, day_end = market_time(day), market_time(day_after(day))
    return day_inputs(table, day_start, day_end, hourly_index(day_start, day_end), COLUMNS,
                      history_days, weather, rule)


def hours_of(weather: pd.DataFrame, day: str) -> pd.Series:
    """True for the rows of one delivery day."""
    return pd.Series((weather.index >= market_time(day))
                     & (weather.index < market_time(day_after(day))), index=weather.index)


def test_weather_ends_with_the_last_hour_of_the_delivery_day():
    inputs = weather_inputs_for(make_weather("2026-06-20", "2026-07-05"), "2026-07-01")

    assert inputs.weather.index.max() == market_time("2026-07-02") - timedelta(hours=1)
    assert inputs.weather.index.min() == market_time("2026-06-20")
    assert list(inputs.weather.columns) == ["temperature_2m", "shortwave_radiation", "run"]


def test_the_newest_weather_run_is_the_one_of_the_day_before_the_delivery_day():
    inputs = weather_inputs_for(make_weather("2026-06-20", "2026-07-05"), "2026-07-01")

    assert inputs.weather["run"].max() == run_time("2026-06-30")


def test_weather_from_a_later_run_is_cut_although_it_stands_on_the_delivery_day():
    weather = make_weather("2026-06-20", "2026-07-05")
    weather.loc[hours_of(weather, "2026-07-01"), "run"] = run_time("2026-07-01")

    inputs = weather_inputs_for(weather, "2026-07-01")

    assert inputs.weather.index.max() == market_time("2026-07-01") - timedelta(hours=1)


def test_weather_from_a_run_one_hour_after_the_run_hour_is_cut():
    weather = make_weather("2026-06-20", "2026-07-05")
    weather.loc[hours_of(weather, "2026-07-01"), "run"] = run_time("2026-06-30", hour=1)

    inputs = weather_inputs_for(weather, "2026-07-01")

    assert inputs.weather.index.max() == market_time("2026-07-01") - timedelta(hours=1)


def test_weather_after_the_delivery_day_is_cut_although_its_run_is_old():
    weather = make_weather("2026-06-20", "2026-07-05")
    weather.loc[hours_of(weather, "2026-07-02"), "run"] = run_time("2026-06-30")

    inputs = weather_inputs_for(weather, "2026-07-01")

    assert inputs.weather.index.max() == market_time("2026-07-02") - timedelta(hours=1)


def test_the_run_hour_of_the_rule_sets_the_newest_run():
    weather = make_weather("2026-06-20", "2026-07-05")
    weather.loc[hours_of(weather, "2026-07-01"), "run"] = run_time("2026-06-30", hour=6)
    at_six = WeatherRule(WEATHER.columns, WEATHER.run_column, run_hour_utc=6)

    assert weather_inputs_for(weather, "2026-07-01").weather.index.max()         == market_time("2026-07-01") - timedelta(hours=1)
    assert weather_inputs_for(weather, "2026-07-01", at_six).weather.index.max()         == market_time("2026-07-02") - timedelta(hours=1)


# 2026-10-25 has 25 hours and 2026-03-29 has 23. Each is taken as D and as D-1.
@pytest.mark.parametrize("day", ["2026-10-25", "2026-10-26", "2026-03-29", "2026-03-30"])
def test_the_weather_cut_is_a_midnight_in_market_time_around_a_clock_change(day):
    weather = make_weather(str(day_after(day, -10)), str(day_after(day, 3)))

    inputs = weather_inputs_for(weather, day)

    assert inputs.weather.index.max() == market_time(day_after(day)) - timedelta(hours=1)
    assert inputs.weather["run"].max() == run_time(day_after(day, -1))


def test_history_days_also_limits_the_weather():
    inputs = weather_inputs_for(make_weather("2026-06-20", "2026-07-05"), "2026-07-01",
                                history_days=3)

    assert inputs.weather.index.min() == market_time("2026-06-28")


def test_inputs_without_a_weather_table_hold_an_empty_weather_frame():
    inputs = inputs_for(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    assert inputs.weather.empty
    assert list(inputs.weather.columns) == []


def test_a_weather_column_that_the_rule_does_not_list_is_refused():
    weather = make_weather("2026-06-20", "2026-07-05").assign(wind_speed_10m=1.0)

    with pytest.raises(ValueError, match="wind_speed_10m"):
        weather_inputs_for(weather, "2026-07-01")


def test_a_weather_table_without_the_run_column_is_refused():
    weather = make_weather("2026-06-20", "2026-07-05").drop(columns="run")

    with pytest.raises(ValueError, match="run"):
        weather_inputs_for(weather, "2026-07-01")


def test_a_weather_table_without_a_rule_is_refused():
    table = make_table("2026-06-20", "2026-07-05")
    day_start, day_end = market_time("2026-07-01"), market_time("2026-07-02")

    with pytest.raises(ValueError, match="rule"):
        day_inputs(table, day_start, day_end, hourly_index(day_start, day_end), COLUMNS,
                   weather=make_weather("2026-06-20", "2026-07-05"))


def test_writing_into_the_weather_inputs_does_not_change_the_weather_table():
    weather = make_weather("2026-06-20", "2026-07-05")
    before = weather.copy()
    inputs = weather_inputs_for(weather, "2026-07-01")

    inputs.weather.loc[:, "temperature_2m"] = -999.0

    pd.testing.assert_frame_equal(weather, before)


def test_weather_rule_reads_the_columns_and_the_run_hour_from_the_config():
    config = {"open_meteo": {"variables": ["temperature_2m", "shortwave_radiation"],
                             "run_hour_utc": 0},
              "backtest": {"weather_run_column": "run"}}

    assert weather_rule(config) == WEATHER


# One date lies before the first row of the table, one is the delivery day, one is months later.
HOLIDAYS = frozenset({date(2026, 6, 1), date(2026, 7, 1), date(2026, 12, 25)})


def holiday_inputs_for(holidays: frozenset[date] | set[date], day: str, history_days=None):
    """The inputs of one delivery day with holiday dates."""
    table = make_table(str(day_after(day, -12)), str(day_after(day, 3)))
    day_start, day_end = market_time(day), market_time(day_after(day))
    return day_inputs(table, day_start, day_end, hourly_index(day_start, day_end), COLUMNS,
                      history_days, holidays=holidays)


def test_inputs_hold_the_holiday_dates_they_were_given():
    inputs = holiday_inputs_for(HOLIDAYS, "2026-07-01")

    assert inputs.holidays == HOLIDAYS


def test_holiday_dates_are_cut_neither_by_the_delivery_day_nor_by_the_history():
    inputs = holiday_inputs_for(HOLIDAYS, "2026-07-01", history_days=3)

    assert inputs.prices.index.min() == market_time("2026-06-28")
    assert inputs.holidays == HOLIDAYS


def test_inputs_without_holiday_dates_hold_an_empty_set():
    inputs = inputs_for(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    assert inputs.holidays == frozenset()


def test_a_plain_set_of_holiday_dates_comes_back_as_a_frozenset_with_the_same_dates():
    inputs = holiday_inputs_for(set(HOLIDAYS), "2026-07-01")

    assert isinstance(inputs.holidays, frozenset)
    assert inputs.holidays == HOLIDAYS


def test_changing_the_set_of_the_caller_afterwards_does_not_change_the_inputs():
    of_the_caller = set(HOLIDAYS)
    inputs = holiday_inputs_for(of_the_caller, "2026-07-01")

    of_the_caller.add(date(2027, 1, 1))

    assert inputs.holidays == HOLIDAYS
