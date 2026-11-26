"""Tests for the LightGBM model, run through the backtest loop, with its leakage tests.

They use small synthetic tables, a temporary folder, no network and no data files.
The price is in EUR/MWh with a UTC index. Delivery days are in market time.

LightGBM stores the target as a 32-bit float, so no test expects an exact price
from a fit. Two forecasts are compared exactly, a learned relation with a margin.
"""

import json
import re
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epf.config import REPO_ROOT, load_config
from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.data.resolution import check_utc_index
from epf.data.validate import HOURLY, QUARTER_HOUR, WEATHER_TABLE, table_path
from epf.evaluation.backtest import build_model, run, run_days
from epf.evaluation.cutoff import (
    Columns,
    DayInputs,
    WeatherRule,
    check_columns,
    cut_columns,
    day_inputs,
    weather_rule,
)
from epf.features.builder import FeatureSettings, build_features
from epf.models import lgbm
from epf.models.stats import StatsModel

MARKET_TZ = "Europe/Berlin"
COLUMNS = Columns(price="price",
                  day_ahead=("load_forecast", "wind_onshore_forecast", "solar_forecast"),
                  delayed=("actual_load",))
RULE = WeatherRule(columns=("temperature_2m", "shortwave_radiation"), run_column="run",
                   run_hour_utc=0)
FEATURES = FeatureSettings(
    groups=("price", "calendar", "load_forecast", "wind_forecast", "solar_forecast",
            "actual_load", "weather"),
    price_lag_days=(1, 2, 7),
    price_day_stats=("mean", "min", "max", "last"),
    forecasts={"load_forecast": ("load_forecast",),
               "wind_forecast": ("wind_onshore_forecast",),
               "solar_forecast": ("solar_forecast",)},
    forecast_lag_days=(1, 7),
    delayed=("actual_load",),
    delayed_lag_days=(2,),
    weather=("temperature_2m", "shortwave_radiation"),
    weather_hour_before=("shortwave_radiation",),
)
PRICE_FEATURES = ["price_lag_1", "price_lag_2", "price_lag_7", "price_d1_mean", "price_d1_min",
                  "price_d1_max", "price_d1_last"]
LONGEST_LAG = 7
ENTRY = {"family": "lgbm", "groups": list(FEATURES.groups), "history_days": None,
         "objective": "regression", "trees": 20,
         "params": {"learning_rate": 0.3, "num_leaves": 8, "min_data_in_leaf": 5}}
# With these keys a tree sees a random part of the rows and of the features, so the seed matters.
SAMPLED = {**ENTRY, "params": {**ENTRY["params"], "feature_fraction": 0.7,
                               "bagging_fraction": 0.7, "bagging_freq": 1}}
SEED = 42

# The delivery day of most tests, with the first day of its table and the end of the table.
# The training days are 2026-06-17 to 2026-06-30.
DAY, FIRST, END = "2026-07-01", "2026-06-10", "2026-07-04"


def market_time(day: str | date) -> pd.Timestamp:
    """00:00 in market time on a day."""
    return pd.Timestamp(day, tz=MARKET_TZ)


def day_after(day: str, days: int = 1) -> date:
    """The calendar day some days after a day. A negative number goes back."""
    return date.fromisoformat(day) + timedelta(days=days)


def days_from(first_day: str, count: int = 1) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """The delivery days from first_day on, as (day start, next day start)."""
    return delivery_days(market_time(first_day), market_time(day_after(first_day, count)))


def make_table(first_day: str = FIRST, end_day: str = END, make_index=hourly_index,
               seed: int = 0) -> pd.DataFrame:
    """A table from first_day up to the start of end_day.

    Every input column is random between 0 and 100. The price is twice the load forecast.
    """
    index = make_index(market_time(first_day), market_time(end_day))
    random = np.random.default_rng(seed)
    table = pd.DataFrame({column: random.uniform(0, 100, len(index))
                          for column in (*COLUMNS.day_ahead, *COLUMNS.delayed)}, index=index)
    table.insert(0, "price", 2 * table["load_forecast"])
    return table


def make_weather(first_day: str = FIRST, end_day: str = END) -> pd.DataFrame:
    """Hourly weather, random between 0 and 100.

    The hours of each delivery day come from the 00:00 UTC run of the day before.
    """
    index = hourly_index(market_time(first_day), market_time(end_day))
    delivery_day = index.tz_convert(MARKET_TZ).normalize().tz_localize(None)
    random = np.random.default_rng(1)
    return pd.DataFrame({"temperature_2m": random.uniform(0, 100, len(index)),
                         "shortwave_radiation": random.uniform(0, 100, len(index)),
                         "run": (delivery_day - timedelta(days=1)).tz_localize("UTC")},
                        index=index)


def announced_prices(index: pd.DatetimeIndex) -> np.ndarray:
    """Prices that follow the last price of the day before.

    Every hour of a day but the last holds the price of the last hour of the day before. The
    last hour holds a new random price between 0 and 100.
    """
    local = index.tz_convert(MARKET_TZ)
    day_number = np.asarray((local.normalize() - local[0].normalize()).days)
    levels = np.random.default_rng(2).uniform(0, 100, day_number.max() + 2)
    return np.where(local.hour == 23, levels[day_number + 1], levels[day_number])


def table_following(source: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A table and its weather for the days around DAY, whose price follows one source.

    The price of a market time unit is the value that a feature of that source reads for it:
    the last price of the day before, the load forecast or the temperature of the same hour,
    or the actual load two days before.
    """
    table, weather = make_table(), make_weather()
    if source == "price":
        table["price"] = announced_prices(table.index)
    elif source == "load_forecast":
        table["price"] = table["load_forecast"]
    elif source == "actual_load":
        table["price"] = table["actual_load"].shift(48)
    elif source == "temperature_2m":
        table["price"] = weather["temperature_2m"]
    return table, weather


def model_with(entry: dict = ENTRY, features: FeatureSettings = FEATURES,
               seed: int = SEED) -> lgbm.LgbmModel:
    """A model set up from an entry, with the columns and the weather rule of these tests."""
    return lgbm.LgbmModel("candidate", entry, features, COLUMNS, RULE, seed)


def forecasts(model, table: pd.DataFrame, first_day: str = DAY, count: int = 1,
              make_index=hourly_index, weather: pd.DataFrame | None = None,
              holidays: frozenset[date] = frozenset()) -> pd.Series:
    """The forecasts of count delivery days through the backtest loop, with one fit."""
    rule = None if weather is None else RULE
    scored, _ = run_days(table, days_from(first_day, count), make_index, model, COLUMNS,
                         refit_every_days=7, history_days=model.params.get("history_days"),
                         weather=weather, rule=rule, holidays=holidays)
    return scored["forecast"]


def inputs_of(table: pd.DataFrame, day: str = DAY, make_index=hourly_index,
              weather: pd.DataFrame | None = None, holidays: frozenset[date] = frozenset(),
              history_days: int | None = None) -> DayInputs:
    """The cut inputs of one delivery day."""
    day_start, day_end = market_time(day), market_time(day_after(day))
    rule = None if weather is None else RULE
    return day_inputs(table, day_start, day_end, make_index(day_start, day_end), COLUMNS,
                      history_days, weather, rule, holidays)


def assert_identical(first: pd.Series, second: pd.Series) -> None:
    """Two forecasts must be equal to the last bit."""
    pd.testing.assert_series_equal(first, second, check_exact=True)


# The shape of a forecast.

# 2026-03-29 has 23 hours and 2026-10-25 has 25. For 2026-11-01 the 25-hour day is a
# training day and the day that the lag of 7 days reads.
@pytest.mark.parametrize("day, make_index, units", [
    ("2026-07-01", hourly_index, 24), ("2026-03-29", hourly_index, 23),
    ("2026-10-25", hourly_index, 25), ("2026-11-01", hourly_index, 24),
    ("2026-03-29", quarter_hour_index, 92), ("2026-10-25", quarter_hour_index, 100)])
def test_the_forecast_has_one_finite_value_per_market_time_unit(day, make_index, units):
    first, end = str(day_after(day, -21)), str(day_after(day, 2))

    forecast = forecasts(model_with(), make_table(first, end, make_index), day,
                         make_index=make_index, weather=make_weather(first, end))

    assert len(forecast) == units
    assert forecast.index.equals(make_index(market_time(day), market_time(day_after(day))))
    assert forecast.name == "forecast"
    assert np.isfinite(forecast).all()


def test_the_model_learns_that_the_price_is_twice_the_load_forecast():
    table = make_table()

    forecast = forecasts(model_with(), table, weather=make_weather())

    # The price runs from 0 to 200. A forecast of its mean would be about 50 off.
    assert np.abs(forecast - table.loc[forecast.index, "price"]).mean() < 10


def test_a_table_without_a_solar_column_and_without_weather_trains_and_forecasts():
    table = make_table().drop(columns="solar_forecast")

    forecast = forecasts(model_with(), table)

    assert len(forecast) == 24
    assert np.isfinite(forecast).all()
    assert np.abs(forecast - table.loc[forecast.index, "price"]).mean() < 10


def test_the_model_grows_the_number_of_trees_of_its_entry():
    model = model_with({**ENTRY, "trees": 13})

    forecasts(model, make_table())

    assert model.booster.num_trees() == 13


def test_a_fit_and_a_forecast_print_nothing(capfd):
    forecasts(model_with(), make_table(), weather=make_weather())

    printed = capfd.readouterr()
    assert printed.out == ""
    assert printed.err == ""


# The same seed, the same forecast. Measured on these tables and this machine.

def test_two_fits_with_the_same_seed_give_the_same_forecast():
    table, weather = make_table(), make_weather()

    first = forecasts(model_with(SAMPLED), table, weather=weather)
    second = forecasts(model_with(SAMPLED), table, weather=weather)

    assert_identical(first, second)


def test_another_seed_gives_another_forecast_when_rows_and_features_are_sampled():
    table, weather = make_table(), make_weather()

    first = forecasts(model_with(SAMPLED, seed=42), table, weather=weather)
    second = forecasts(model_with(SAMPLED, seed=43), table, weather=weather)

    assert not first.equals(second)


def test_a_model_fitted_on_another_table_before_forecasts_like_a_fresh_one():
    # The other table is on the 15-minute grid, has no solar column and no weather, so its
    # features have another column, quarter_hour, and other rows.
    other = make_table(make_index=quarter_hour_index, seed=5).drop(columns="solar_forecast")
    table, weather = make_table(), make_weather()
    reused = model_with(SAMPLED)

    forecasts(reused, other, make_index=quarter_hour_index)
    again = forecasts(reused, table, weather=weather)

    assert_identical(again, forecasts(model_with(SAMPLED), table, weather=weather))


def test_the_model_hands_lightgbm_the_seed_and_its_own_fixed_keys():
    assert lgbm.train_params(ENTRY, seed=7) == {
        "learning_rate": 0.3, "num_leaves": 8, "min_data_in_leaf": 5,
        "objective": "regression", "seed": 7, "deterministic": True, "force_col_wise": True,
        "verbosity": -1}


# The leakage rule (PROJECT_CONTEXT section 5).

def change_after_the_cuts(table: pd.DataFrame, weather: pd.DataFrame,
                          day: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return copies with every value changed that a forecast for a delivery day may not use."""
    table, weather = table.copy(), weather.copy()
    table.loc[table.index >= market_time(day), "price"] += 1000
    for column in COLUMNS.day_ahead:
        table.loc[table.index >= market_time(day_after(day)), column] += 1000
    table.loc[table.index >= market_time(day_after(day, -1)), "actual_load"] += 1000
    weather.loc[weather.index >= market_time(day_after(day)),
                ["temperature_2m", "shortwave_radiation"]] += 1000
    return table, weather


SOURCES = ["price", "load_forecast", "actual_load", "temperature_2m"]


@pytest.mark.parametrize("source", SOURCES)
def test_changing_every_value_after_the_cuts_leaves_the_forecast_unchanged(source):
    table, weather = table_following(source)
    changed_table, changed_weather = change_after_the_cuts(table, weather, DAY)

    before = forecasts(model_with(), table, weather=weather)
    after = forecasts(model_with(), changed_table, weather=changed_weather)

    assert_identical(before, after)


# 2026-10-25 has 25 hours. It is taken as D and as D-1.
@pytest.mark.parametrize("day, make_index", [("2026-10-25", hourly_index),
                                             ("2026-10-26", quarter_hour_index)])
def test_the_forecast_ignores_every_value_after_the_cuts_around_a_clock_change(day, make_index):
    first, end = str(day_after(day, -21)), str(day_after(day, 3))
    table, weather = make_table(first, end, make_index), make_weather(first, end)
    changed_table, changed_weather = change_after_the_cuts(table, weather, day)

    before = forecasts(model_with(), table, day, make_index=make_index, weather=weather)
    after = forecasts(model_with(), changed_table, day, make_index=make_index,
                      weather=changed_weather)

    assert_identical(before, after)


# The model is fitted for 2026-07-01 only. The forecast of 2026-07-02 lies between two fits.
def test_a_forecast_between_two_fits_ignores_every_value_after_its_cuts():
    table, weather = make_table(), make_weather()
    changed_table, changed_weather = change_after_the_cuts(table, weather, "2026-07-02")

    before = forecasts(model_with(), table, count=2, weather=weather)
    after = forecasts(model_with(), changed_table, count=2, weather=changed_weather)

    assert len(before) == 48
    assert_identical(before, after)


# The last moment before each cut for the delivery day 2026-07-01, and the feature group
# that reads it. The price of each table follows that source, so the trees split on it.
LAST_SEEN = [
    ("price", "price", "2026-06-30 23:00"),
    ("load_forecast", "load_forecast", "2026-07-01 23:00"),
    ("actual_load", "actual_load", "2026-06-29 23:00"),
    ("temperature_2m", "weather", "2026-07-01 23:00"),
]


def forecast_with_last_value(source: str, group: str, last_seen: str, value: float) -> pd.Series:
    """The forecast of DAY from one feature group, with the last value of a source set."""
    table, weather = table_following(source)
    frame = weather if source in weather.columns else table
    frame.loc[pd.Timestamp(last_seen, tz=MARKET_TZ), source] = value
    return forecasts(model_with({**ENTRY, "groups": [group]}), table, weather=weather)


@pytest.mark.parametrize("source, group, last_seen", LAST_SEEN)
def test_changing_the_last_value_before_a_cut_changes_the_forecast(source, group, last_seen):
    low = forecast_with_last_value(source, group, last_seen, 10.0)
    high = forecast_with_last_value(source, group, last_seen, 90.0)

    # The price follows the source, so the forecast that reads it moves by about 80.
    assert (high - low).max() > 40


def test_weather_from_a_later_run_does_not_reach_the_forecast():
    table, weather = table_following("temperature_2m")
    late = weather.copy()
    on_the_day = late.index >= market_time(DAY)
    late.loc[on_the_day, "run"] = pd.Timestamp(DAY, tz="UTC")
    late_and_changed = late.copy()
    late_and_changed.loc[on_the_day, "temperature_2m"] += 1000
    model = {**ENTRY, "groups": ["weather"]}

    in_time = forecasts(model_with(model), table, weather=weather)
    too_late = forecasts(model_with(model), table, weather=late)
    changed = forecasts(model_with(model), table, weather=late_and_changed)

    assert_identical(too_late, changed)
    assert not in_time.equals(too_late)


# The model is fitted for 2026-07-01 only. The forecast of 2026-07-02 lies between two fits.
def test_between_two_fits_the_forecast_follows_the_newest_price_before_its_cut():
    low, weather = table_following("price")
    high = low.copy()
    newest = pd.Timestamp("2026-07-01 23:00", tz=MARKET_TZ)
    low.loc[newest, "price"], high.loc[newest, "price"] = 10.0, 90.0
    price_only = {**ENTRY, "groups": ["price"]}

    before = forecasts(model_with(price_only), low, count=2, weather=weather)
    after = forecasts(model_with(price_only), high, count=2, weather=weather)

    second_day = before.index >= market_time("2026-07-02")
    assert_identical(before[~second_day], after[~second_day])
    assert (after[second_day] - before[second_day]).max() > 40


# The training rows.

def test_the_training_rows_run_from_the_first_day_plus_the_longest_lag_to_the_day_before():
    table = make_table()

    rows, target = lgbm.training_rows(inputs_of(table), FEATURES, COLUMNS, RULE)

    expected = hourly_index(market_time(day_after(FIRST, LONGEST_LAG)), market_time(DAY))
    assert len(expected) == 14 * 24
    assert rows.index.equals(expected)
    assert target.index.equals(expected)
    assert rows.index.max() == market_time(DAY) - timedelta(hours=1)


def test_the_target_of_a_training_row_is_the_table_price_of_its_market_time_unit():
    table = make_table()

    rows, target = lgbm.training_rows(inputs_of(table), FEATURES, COLUMNS, RULE)

    assert target.tolist() == table.loc[rows.index, "price"].tolist()
    assert "price" not in rows.columns


def test_every_training_day_is_cut_as_if_it_were_forecast_on_its_own_day():
    table, weather = make_table(), make_weather()
    holidays = frozenset({date(2026, 6, 20)})
    days = delivery_days(market_time(day_after(FIRST, LONGEST_LAG)), market_time(DAY))

    rows, _ = lgbm.training_rows(inputs_of(table, weather=weather, holidays=holidays),
                                 FEATURES, COLUMNS, RULE)

    from_the_whole_table = build_features(table, days, hourly_index, COLUMNS, FEATURES,
                                          holidays, weather, RULE)
    pd.testing.assert_frame_equal(rows, from_the_whole_table, check_exact=True)
    assert rows[["temperature_2m", "actual_load_lag_2"]].notna().all().all()


def test_the_training_rows_end_before_the_delivery_day_when_the_prices_reach_further():
    table = make_table()
    # Inputs that a wrong price cut would give: the prices run to the end of the table.
    inputs = replace(inputs_of(table), prices=table["price"])
    assert inputs.prices.index.max() > market_time(day_after(DAY))

    days = lgbm.training_days(inputs, LONGEST_LAG)
    rows, target = lgbm.training_rows(inputs, FEATURES, COLUMNS, RULE)

    assert days[-1] == (market_time(day_after(DAY, -1)), market_time(DAY))
    assert rows.index.max() == market_time(DAY) - timedelta(hours=1)
    assert target.index.max() == market_time(DAY) - timedelta(hours=1)


def test_the_first_training_day_follows_the_history_that_the_inputs_hold():
    inputs = inputs_of(make_table(), history_days=10)

    days = lgbm.training_days(inputs, LONGEST_LAG)

    # The prices start 10 days before 2026-07-01, on 2026-06-21, and the longest lag is 7 days.
    assert [str(day_start.date()) for day_start, _ in days] == [
        "2026-06-28", "2026-06-29", "2026-06-30"]


def test_the_training_days_of_the_15_minute_table_have_96_rows_each():
    table = make_table(make_index=quarter_hour_index)

    rows, target = lgbm.training_rows(inputs_of(table, make_index=quarter_hour_index),
                                      FEATURES, COLUMNS, RULE)

    assert rows.index.equals(quarter_hour_index(market_time(day_after(FIRST, LONGEST_LAG)),
                                                market_time(DAY)))
    assert len(rows) == 14 * 96
    assert "quarter_hour" in rows.columns


@pytest.mark.parametrize("first_day", ["2026-06-24", "2026-07-01"])
def test_inputs_without_a_training_day_are_refused(first_day):
    # A table from 2026-06-24 holds the 7 days that the lags of 2026-07-01 read and no day more.
    inputs = inputs_of(make_table(first_day))

    with pytest.raises(ValueError, match="training day"):
        lgbm.training_days(inputs, LONGEST_LAG)


def test_a_row_with_an_empty_feature_stays_and_a_row_with_an_empty_price_is_dropped():
    table = make_table().drop(columns="solar_forecast")
    empty_feature = pd.Timestamp("2026-06-20 05:00", tz=MARKET_TZ)
    empty_price = pd.Timestamp("2026-06-22 05:00", tz=MARKET_TZ)
    table.loc[empty_feature, "load_forecast"] = np.nan
    table.loc[empty_price, "price"] = np.nan

    rows, target = lgbm.training_rows(inputs_of(table), FEATURES, COLUMNS, RULE)

    assert len(rows) == 14 * 24 - 1
    assert empty_price not in rows.index
    assert target.notna().all()
    assert np.isnan(rows.loc[empty_feature, "load_forecast"])
    assert rows["solar_forecast"].isna().all()
    assert rows["temperature_2m"].isna().all()
    # The day after the empty price reads it as its lag of one day. Nothing is filled.
    assert np.isnan(rows.loc[empty_price + timedelta(days=1), "price_lag_1"])


def test_the_holiday_mark_reaches_the_training_rows():
    holidays = frozenset({date(2026, 6, 20), date(2026, 7, 1)})

    rows, _ = lgbm.training_rows(inputs_of(make_table(), holidays=holidays), FEATURES, COLUMNS,
                                 RULE)

    marked = rows.index[rows["holiday"] == 1]
    assert marked.equals(hourly_index(market_time("2026-06-20"), market_time("2026-06-21")))


def test_the_forecast_of_a_holiday_follows_the_holidays_among_the_training_days():
    # The price is 80 on a holiday and 20 on every other day. 2026-07-01 is a holiday.
    holidays = frozenset({date(2026, 6, 18), date(2026, 6, 23), date(2026, 6, 27),
                          date(2026, 7, 1)})
    table = make_table()
    table["price"] = [80.0 if day in holidays else 20.0
                      for day in table.index.tz_convert(MARKET_TZ).date]
    calendar_only = {**ENTRY, "groups": ["calendar"]}

    marked = forecasts(model_with(calendar_only), table, holidays=holidays)
    not_marked = forecasts(model_with(calendar_only), table,
                           holidays=holidays - {date(2026, 7, 1)})

    assert (np.abs(marked - 80) < 5).all()
    assert (np.abs(not_marked - 20) < 5).all()


# The known table.

def test_the_known_table_holds_the_three_parts_and_nothing_after_their_cuts():
    inputs = inputs_of(make_table())

    known = lgbm.known_table(inputs, COLUMNS)

    check_utc_index(known)
    check_columns(known, COLUMNS)
    assert known.index.equals(inputs.day_ahead.index)
    assert sorted(known.columns) == sorted(make_table().columns)
    assert known.loc[known.index >= market_time(DAY), "price"].isna().all()
    assert known.loc[known.index >= market_time(day_after(DAY, -1)), "actual_load"].isna().all()
    assert known["price"].notna().sum() == len(inputs.prices)
    assert known["actual_load"].notna().sum() == len(inputs.delayed)
    assert known[list(COLUMNS.day_ahead)].notna().all().all()


def test_cutting_the_known_table_again_gives_the_parts_of_the_inputs_back():
    inputs = inputs_of(make_table())

    again = day_inputs(lgbm.known_table(inputs, COLUMNS), market_time(DAY),
                       market_time(day_after(DAY)), inputs.target_index, COLUMNS)

    pd.testing.assert_series_equal(again.prices, inputs.prices, check_exact=True)
    pd.testing.assert_frame_equal(again.day_ahead, inputs.day_ahead, check_exact=True)
    pd.testing.assert_frame_equal(again.delayed, inputs.delayed, check_exact=True)


def test_the_known_table_does_not_change_the_inputs():
    inputs = inputs_of(make_table())
    day_ahead = inputs.day_ahead.copy()

    lgbm.known_table(inputs, COLUMNS)

    pd.testing.assert_frame_equal(inputs.day_ahead, day_ahead)


# The market time units and the features of a model.

def test_the_index_maker_follows_the_step_of_the_market_time_units():
    start, end = market_time(DAY), market_time(day_after(DAY))

    assert lgbm.index_maker(hourly_index(start, end)) is hourly_index
    assert lgbm.index_maker(quarter_hour_index(start, end)) is quarter_hour_index
    with pytest.raises(ValueError, match="30"):
        lgbm.index_maker(pd.date_range(start, end, freq="30min", inclusive="left"))


def test_the_features_of_a_model_are_the_feature_settings_with_the_groups_of_its_entry():
    chosen = lgbm.model_features(FEATURES, ["price", "calendar"], COLUMNS.day_ahead)

    assert chosen == replace(FEATURES, groups=("price", "calendar"))
    assert len(FEATURES.groups) == 7


def test_feature_settings_that_the_builder_refuses_are_refused_for_a_model_too():
    wrong = replace(FEATURES, price_day_stats=("median",))

    with pytest.raises(ValueError, match="median"):
        model_with(features=wrong)


def test_a_model_trains_on_the_features_of_its_groups_only():
    model = model_with({**ENTRY, "groups": ["price"]})

    forecasts(model, make_table(), weather=make_weather())

    assert model.feature_names == PRICE_FEATURES


def test_a_forecast_from_other_features_than_those_of_the_fit_is_refused():
    model = model_with()
    model.fit(inputs_of(make_table()))

    with pytest.raises(ValueError, match="quarter_hour"):
        model.predict(inputs_of(make_table(make_index=quarter_hour_index),
                                make_index=quarter_hour_index))


# The settings of an entry.

def test_the_settings_of_the_entry_are_the_params_for_the_results():
    model = model_with()

    assert model.name == "candidate"
    assert model.params == ENTRY
    assert json.loads(json.dumps(model.params)) == ENTRY


@pytest.mark.parametrize("history_days", [None, 8, 500])
def test_a_history_longer_than_the_longest_lag_is_accepted(history_days):
    assert model_with({**ENTRY, "history_days": history_days}).params["history_days"] \
        == history_days


def test_an_entry_without_a_history_length_is_accepted():
    entry = {key: value for key, value in ENTRY.items() if key != "history_days"}

    assert model_with(entry).params == entry


@pytest.mark.parametrize("objective", ["regression", "regression_l1"])
def test_the_two_objectives_for_the_squared_and_the_absolute_error_train(objective):
    table = make_table()

    forecast = forecasts(model_with({**ENTRY, "objective": objective}), table)

    assert np.abs(forecast - table.loc[forecast.index, "price"]).mean() < 10


@pytest.mark.parametrize("key", ["family", "groups", "objective", "trees", "params"])
def test_an_entry_without_one_of_its_keys_is_refused(key):
    entry = {name: value for name, value in ENTRY.items() if name != key}

    with pytest.raises(ValueError, match=key):
        model_with(entry)


@pytest.mark.parametrize("change, message", [
    ({"family": "ets"}, "'ets'"),
    ({"history_day": 30}, "'history_day'"),       # a misspelt key of the entry
    ({"groups": []}, "group"),
    ({"groups": ["price", "tide"]}, "tide"),
    ({"objective": "quantile"}, "quantile"),
    ({"objective": "mse"}, "mse"),                # another name of regression
    ({"trees": 0}, "trees"),
    ({"trees": 2.5}, "trees"),
    ({"history_days": 7}, "history_days"),        # the longest lag itself leaves no training day
    ({"history_days": 3}, "history_days"),
])
def test_wrong_settings_of_an_entry_are_refused(change, message):
    with pytest.raises(ValueError, match=message):
        model_with({**ENTRY, **change})


def test_a_group_that_the_feature_settings_do_not_build_is_refused():
    built = replace(FEATURES, groups=("price", "calendar"))

    with pytest.raises(ValueError, match="weather"):
        model_with({**ENTRY, "groups": ["price", "weather"]}, features=built)


# LightGBM ignores a key it does not know without an error, and a round count among the
# parameters would replace the number of trees of the entry.
@pytest.mark.parametrize("key", [
    "num_leafs",                                   # misspelt
    "num_leaf", "eta", "min_child_samples", "colsample_bytree", "subsample", "reg_lambda",
    "max_bins",                                    # other names of allowed keys
    "num_iterations", "n_estimators", "num_boost_round", "num_trees",   # a round count
    "seed", "random_state", "deterministic", "force_col_wise", "verbosity", "verbose",
    "objective", "num_threads", "n_jobs",          # set by the model, or left to the library
    "alpha", "early_stopping_round", "force_row_wise",
])
def test_a_parameter_key_outside_the_allowed_list_is_refused(key):
    with pytest.raises(ValueError, match=key):
        model_with({**ENTRY, "params": {**ENTRY["params"], key: 1}})


def test_every_allowed_parameter_key_is_accepted_and_reaches_lightgbm():
    params = {"learning_rate": 0.2, "num_leaves": 6, "max_depth": 4, "min_data_in_leaf": 5,
              "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
              "lambda_l1": 0.1, "lambda_l2": 0.1, "max_bin": 63}
    entry = {**ENTRY, "params": params}

    forecast = forecasts(model_with(entry), make_table())

    assert sorted(params) == sorted(lgbm.ALLOWED_PARAMS)
    assert set(params) <= set(lgbm.train_params(entry, SEED))
    assert np.isfinite(forecast).all()


# The command. A small project in a temporary folder: zone A is core and has weather,
# zone B is extra and has none. One model object runs both zones and both experiments.

SMALL = {"family": "lgbm", "groups": ["price", "calendar", "load_forecast", "weather"],
         "history_days": 12, "objective": "regression_l1", "trees": 10,
         "params": {"learning_rate": 0.3, "min_data_in_leaf": 5}}
ETS = {"family": "ets", "form": "ANN", "season_days": [1], "history_days": 5}


def project_config(tmp_path) -> dict:
    """A config with 5 validation days, the feature settings of these tests and two entries."""
    return {
        "seed": 42,
        "market": {"timezone": MARKET_TZ},
        "paths": {"processed": str(tmp_path / "processed"),
                  "results": str(tmp_path / "results"),
                  "forecasts": str(tmp_path / "forecasts")},
        "data": {"start": "2026-10-05", "end": "2026-11-03"},
        "splits": {"validation_days": 5, "test_days": 10,
                   "validation_start": "2026-10-20", "test_start": "2026-10-25"},
        "backtest": {"refit_every_days": 7, "history_days": None, "test_models": ["naive"],
                     "price_column": COLUMNS.price, "day_ahead_columns": list(COLUMNS.day_ahead),
                     "delayed_columns": list(COLUMNS.delayed), "weather_run_column": "run"},
        "open_meteo": {"variables": list(RULE.columns), "run_hour_utc": 0},
        "features": {"groups": list(FEATURES.groups), "price_lag_days": [1, 2, 7],
                     "price_day_stats": ["mean", "min", "max", "last"],
                     "forecasts": {"load_forecast": ["load_forecast"],
                                   "wind_forecast": ["wind_onshore_forecast"],
                                   "solar_forecast": ["solar_forecast"]},
                     "forecast_lag_days": [1, 7], "actual_load_lag_days": [2],
                     "weather_hour_before": ["shortwave_radiation"]},
        "models": {"naive": {"lag_days": 7}, "lgbm_small": SMALL, "ets_short": ETS},
        "zones": [{"key": "B", "holiday_country": "PL", "group": "extra"},
                  {"key": "A", "holiday_country": "DE", "group": "core",
                   "weather_point": {"place": "X", "latitude": 10.0, "longitude": 20.0}}],
    }


def save_tables(config: dict) -> None:
    """Write the hourly and the 15-minute table of both zones and the weather table of zone A."""
    first, end = config["data"]["start"], str(day_after(config["data"]["end"]))
    folder = Path(config["paths"]["processed"])
    tables = {(HOURLY, zone_key): make_table(first, end, hourly_index) for zone_key in "AB"}
    tables.update({(QUARTER_HOUR, zone_key): make_table(first, end, quarter_hour_index)
                   for zone_key in "AB"})
    tables[(WEATHER_TABLE, "A")] = make_weather(first, end)
    for (name, zone_key), table in tables.items():
        path = table_path(folder, name, zone_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(path)


def saved(config: dict, name: str) -> pd.DataFrame:
    """Read one results file of the temporary project."""
    return pd.read_csv(Path(config["paths"]["results"]) / name)


def test_build_model_sets_a_lightgbm_entry_up_from_the_config(tmp_path):
    config = project_config(tmp_path)

    model = build_model(config, "lgbm_small")

    assert isinstance(model, lgbm.LgbmModel)
    assert model.name == "lgbm_small"
    assert model.params == SMALL
    assert model.features == replace(FEATURES, groups=tuple(SMALL["groups"]))
    assert model.columns == cut_columns(config)
    assert model.rule == weather_rule(config)
    assert model.seed == 42


def test_build_model_keeps_every_other_family_a_statistical_model(tmp_path):
    config = project_config(tmp_path)

    assert isinstance(build_model(config, "ets_short"), StatsModel)


def test_the_project_config_gives_feature_settings_that_a_lightgbm_entry_can_use():
    config = load_config()
    config["models"]["candidate"] = {**ENTRY, "groups": list(config["features"]["groups"])}

    model = build_model(config, "candidate")

    assert isinstance(model, lgbm.LgbmModel)
    assert model.seed == config["seed"]


def test_run_scores_a_lightgbm_entry_and_writes_its_settings_and_the_seed(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "lgbm_small", "validation")

    core, extra = saved(config, "backtest_core.csv"), saved(config, "backtest_extra.csv")
    assert core["zone"].tolist() == ["A", "A"]
    assert extra["zone"].tolist() == ["B", "B"]
    for rows in (core, extra):
        assert rows["model"].tolist() == ["lgbm_small"] * 2
        assert [json.loads(text) for text in rows["model_params"]] == [SMALL] * 2
        assert rows["seed"].tolist() == [42, 42]
        assert rows["history_days"].tolist() == [12, 12]
        assert rows["experiment"].tolist() == ["H", "Q"]
        assert rows["days"].tolist() == [5, 5]
        assert rows["mtus"].tolist() == [120, 480]
        assert rows["empty_forecasts"].tolist() == [0, 0]
        # The price is twice the load forecast, which the naive forecast cannot know.
        assert (rows["relative_mae"] < 0.5).all()
    forecasts_file = Path(config["paths"]["forecasts"]) / "lgbm_small" / "H" / "validation" \
        / "A.parquet"
    assert len(pd.read_parquet(forecasts_file)) == 120


def test_run_refuses_a_lightgbm_entry_with_a_misspelt_parameter(tmp_path):
    config = project_config(tmp_path)
    config["models"]["lgbm_small"] = {**SMALL, "params": {"num_leafs": 8}}
    save_tables(config)

    with pytest.raises(SystemExit, match="num_leafs"):
        run(config, "lgbm_small", "validation")

    assert not Path(config["paths"]["results"]).exists()


# The code.

def test_the_model_code_names_no_zone():
    config = load_config()
    names = [str(zone[key]) for zone in config["zones"] for key in ("key", "energy_charts")]
    names += [zone["weather_point"]["place"] for zone in config["zones"]]

    text = (REPO_ROOT / "src" / "epf" / "models" / "lgbm.py").read_text(encoding="utf-8")

    found = [name for name in names if re.search(rf"\b{re.escape(name)}\b", text)]
    assert found == []
