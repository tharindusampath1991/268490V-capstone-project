"""Tests for the quantile forecasts of a LightGBM entry, with their leakage tests.

They use small synthetic tables, no network and no data files. The price is in
EUR/MWh with a UTC index. Delivery days are in market time.

Every forecast here comes from inputs that day_inputs has cut for its delivery
day. LightGBM stores the target as a 32-bit float, so two frames are compared
exactly and a learned relation with a margin.
"""

import json
from datetime import date, timedelta

import lightgbm
import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import hourly_index, quarter_hour_index
from epf.evaluation.cutoff import Columns, DayInputs, WeatherRule, day_inputs
from epf.features.builder import FeatureSettings, day_features
from epf.models import lgbm

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
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
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


def announced_table() -> pd.DataFrame:
    """A table whose price follows the last price of the day before.

    Every hour of a day but the last holds the price of the last hour of the day before. The
    last hour holds a new random price between 0 and 100.
    """
    table = make_table()
    local = table.index.tz_convert(MARKET_TZ)
    day_number = np.asarray((local.normalize() - local[0].normalize()).days)
    levels = np.random.default_rng(2).uniform(0, 100, day_number.max() + 2)
    table["price"] = np.where(local.hour == 23, levels[day_number + 1], levels[day_number])
    return table


def model_with(entry: dict = ENTRY, levels: list[float] = LEVELS,
               features: FeatureSettings = FEATURES, seed: int = SEED) -> lgbm.LgbmQuantileModel:
    """A quantile model of an entry, with the columns and the weather rule of these tests."""
    return lgbm.LgbmQuantileModel("candidate", entry, levels, features, COLUMNS, RULE, seed)


def inputs_of(table: pd.DataFrame, day: str = DAY, make_index=hourly_index,
              weather: pd.DataFrame | None = None) -> DayInputs:
    """The cut inputs of one delivery day."""
    day_start, day_end = market_time(day), market_time(day_after(day))
    rule = None if weather is None else RULE
    return day_inputs(table, day_start, day_end, make_index(day_start, day_end), COLUMNS,
                      None, weather, rule)


def quantiles(model: lgbm.LgbmQuantileModel, table: pd.DataFrame, day: str = DAY,
              make_index=hourly_index, weather: pd.DataFrame | None = None) -> pd.DataFrame:
    """The quantile forecasts of one delivery day, from a fit on the cut inputs of that day."""
    inputs = inputs_of(table, day, make_index, weather)
    model.fit(inputs)
    return model.predict_quantiles(inputs)


def assert_identical(first: pd.DataFrame, second: pd.DataFrame) -> None:
    """Two frames of quantile forecasts must be equal to the last bit."""
    pd.testing.assert_frame_equal(first, second, check_exact=True)


# The shape of the forecasts.

# 2026-03-29 has 23 hours and 2026-10-25 has 25.
@pytest.mark.parametrize("day, make_index, units", [
    ("2026-07-01", hourly_index, 24), ("2026-03-29", hourly_index, 23),
    ("2026-10-25", hourly_index, 25), ("2026-07-01", quarter_hour_index, 96)])
def test_every_market_time_unit_has_one_finite_value_per_level(day, make_index, units):
    first, end = str(day_after(day, -21)), str(day_after(day, 2))

    frame = quantiles(model_with(), make_table(first, end, make_index), day, make_index,
                      make_weather(first, end))

    assert frame.shape == (units, 5)
    assert list(frame.columns) == LEVELS
    assert frame.index.equals(make_index(market_time(day), market_time(day_after(day))))
    assert np.isfinite(frame).all().all()


def test_a_fit_grows_one_set_of_trees_per_level_with_the_level_as_alpha():
    model = model_with({**ENTRY, "trees": 13})

    quantiles(model, make_table())

    assert list(model.boosters) == LEVELS
    for level, booster in model.boosters.items():
        assert booster.params["objective"] == "quantile"
        assert booster.params["alpha"] == level
        assert booster.num_trees() == 13


def test_the_values_of_a_level_are_those_of_its_trees_and_are_not_sorted():
    model, inputs = model_with(), inputs_of(make_table())
    model.fit(inputs)

    frame = model.predict_quantiles(inputs)

    rows = day_features(inputs, model.features, inputs.holidays)
    for level in LEVELS:
        assert frame[level].tolist() == model.boosters[level].predict(rows).tolist()


def test_the_parameters_of_a_level_are_those_of_the_entry_with_the_quantile_objective():
    assert lgbm.quantile_params(ENTRY, seed=7, level=0.25) == {
        "learning_rate": 0.3, "num_leaves": 8, "min_data_in_leaf": 5,
        "objective": "quantile", "alpha": 0.25, "seed": 7, "deterministic": True,
        "force_col_wise": True, "verbosity": -1}


def test_the_objective_of_the_entry_is_not_used():
    table = make_table()

    squared = quantiles(model_with({**ENTRY, "objective": "regression"}), table)
    absolute = quantiles(model_with({**ENTRY, "objective": "regression_l1"}), table)

    assert_identical(squared, absolute)


def test_a_fit_and_a_forecast_print_nothing(capfd):
    quantiles(model_with(), make_table(), weather=make_weather())

    printed = capfd.readouterr()
    assert printed.out == ""
    assert printed.err == ""


# The same seed, the same frame. Measured on these tables and this machine.

def test_two_fits_with_the_same_seed_give_the_same_frame():
    table, weather = make_table(), make_weather()

    first = quantiles(model_with(SAMPLED), table, weather=weather)
    second = quantiles(model_with(SAMPLED), table, weather=weather)

    assert_identical(first, second)


def test_another_seed_gives_another_frame_when_rows_and_features_are_sampled():
    table, weather = make_table(), make_weather()

    first = quantiles(model_with(SAMPLED, seed=42), table, weather=weather)
    second = quantiles(model_with(SAMPLED, seed=43), table, weather=weather)

    assert not first.equals(second)


def test_a_model_fitted_on_another_table_before_forecasts_like_a_fresh_one():
    # The other table is on the 15-minute grid, has no solar column and no weather, so its
    # features have another column, quarter_hour, and other rows.
    other = make_table(make_index=quarter_hour_index, seed=5).drop(columns="solar_forecast")
    table, weather = make_table(), make_weather()
    reused = model_with(SAMPLED)

    quantiles(reused, other, make_index=quarter_hour_index)
    again = quantiles(reused, table, weather=weather)

    assert_identical(again, quantiles(model_with(SAMPLED), table, weather=weather))


# What the levels mean. The price is twice the load forecast plus normal noise with a
# standard deviation of 10 EUR/MWh. One fit for 2026-07-01 on 84 training days, then the
# 20 delivery days from 2026-07-01, each from its own cut inputs: 480 prices.

SPREAD = 10.0
CALIBRATION = {**ENTRY, "groups": ["load_forecast"], "trees": 100,
               "params": {"learning_rate": 0.1, "num_leaves": 8, "min_data_in_leaf": 20}}
# With 480 prices a share at the level 0.5 has a standard error of 0.023. Measured on
# 2026-11-26: the shares 0.0958, 0.3021, 0.5312, 0.7917 and 0.9333 for the five levels, so
# 0.0521 from the level at most, and 31.59 between the mean forecasts of 0.05 and 0.95.
SHARE_TOLERANCE = 0.07


def noisy_table() -> pd.DataFrame:
    """A table from 2026-04-01 whose price is twice the load forecast plus normal noise."""
    table = make_table("2026-04-01", "2026-07-22")
    noise = np.random.default_rng(3).normal(0, SPREAD, len(table))
    table["price"] = 2 * table["load_forecast"] + noise
    return table


def later_days(model: lgbm.LgbmQuantileModel, table: pd.DataFrame, count: int) -> pd.DataFrame:
    """The quantile forecasts of count delivery days from DAY on, from one fit for DAY."""
    model.fit(inputs_of(table))
    return pd.concat(model.predict_quantiles(inputs_of(table, str(day_after(DAY, number))))
                     for number in range(count))


def test_the_share_of_later_prices_below_the_forecast_of_a_level_is_near_the_level():
    table = noisy_table()

    frame = later_days(model_with(CALIBRATION), table, count=20)

    actual = table.loc[frame.index, "price"]
    shares = {level: float((actual < frame[level]).mean()) for level in LEVELS}
    assert len(actual) == 480
    for level, share in shares.items():
        assert abs(share - level) < SHARE_TOLERANCE, shares


def test_a_higher_level_never_gives_a_lower_mean_forecast():
    frame = later_days(model_with(CALIBRATION), noisy_table(), count=20)

    means = frame.mean()

    assert means.is_monotonic_increasing
    # 90% of normal noise lies within 1.645 standard deviations of its mean.
    assert means[0.95] - means[0.05] == pytest.approx(2 * 1.645 * SPREAD, rel=0.25)


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


# 2026-10-25 has 25 hours.
@pytest.mark.parametrize("day, make_index", [("2026-07-01", hourly_index),
                                             ("2026-10-25", hourly_index),
                                             ("2026-07-01", quarter_hour_index)])
def test_changing_every_value_after_the_cuts_leaves_the_frame_unchanged(day, make_index):
    first, end = str(day_after(day, -21)), str(day_after(day, 3))
    table, weather = make_table(first, end, make_index), make_weather(first, end)
    changed_table, changed_weather = change_after_the_cuts(table, weather, day)

    before = quantiles(model_with(), table, day, make_index, weather)
    after = quantiles(model_with(), changed_table, day, make_index, changed_weather)

    assert_identical(before, after)


# The model is fitted for 2026-07-01 only. The forecast of 2026-07-02 lies between two fits.
def test_a_forecast_between_two_fits_ignores_every_value_after_its_cuts():
    table, weather = make_table(), make_weather()
    changed_table, changed_weather = change_after_the_cuts(table, weather, "2026-07-02")
    model, other = model_with(), model_with()
    model.fit(inputs_of(table, weather=weather))
    other.fit(inputs_of(changed_table, weather=changed_weather))

    before = model.predict_quantiles(inputs_of(table, "2026-07-02", weather=weather))
    after = other.predict_quantiles(inputs_of(changed_table, "2026-07-02",
                                              weather=changed_weather))

    assert_identical(before, after)


def test_changing_the_last_price_before_the_cut_changes_the_frame():
    low, high = announced_table(), announced_table()
    last_seen = pd.Timestamp("2026-06-30 23:00", tz=MARKET_TZ)
    low.loc[last_seen, "price"], high.loc[last_seen, "price"] = 10.0, 90.0
    price_only = {**ENTRY, "groups": ["price"]}

    low_frame = quantiles(model_with(price_only), low)
    high_frame = quantiles(model_with(price_only), high)

    # The price follows the last price of the day before, so the median moves by about 80.
    # The outer levels of these 14 training days follow it less and are not asserted.
    assert (high_frame[0.5] - low_frame[0.5]).max() > 40
    assert not high_frame.equals(low_frame)


# What the model refuses.

def test_a_forecast_before_any_fit_is_refused():
    with pytest.raises(ValueError, match="'candidate' has not been fitted"):
        model_with().predict_quantiles(inputs_of(make_table()))


def test_a_forecast_from_other_features_than_those_of_the_fit_is_refused():
    model = model_with()
    model.fit(inputs_of(make_table()))

    with pytest.raises(ValueError, match="quarter_hour"):
        model.predict_quantiles(inputs_of(make_table(make_index=quarter_hour_index),
                                          make_index=quarter_hour_index))


@pytest.mark.parametrize("levels, message", [
    ([0.5], "at least two"),
    ([], "at least two"),
    ([0.0, 0.5, 1.0], "between 0 and 1"),
    ([-0.1, 0.5, 1.1], "between 0 and 1"),
    ([0.75, 0.5, 0.25], "ascend"),
    ([0.25, 0.25, 0.75, 0.75], "ascend"),
    ([0.1, 0.5, 0.95], "mirror"),
    ([0.05, 0.25, 0.5, 0.75], "mirror"),
])
def test_wrong_levels_are_refused(levels, message):
    with pytest.raises(ValueError, match=f"Quantile levels.*{message}"):
        model_with(levels=levels)


# An empty key in the YAML file gives None, and a quoted number is text.
@pytest.mark.parametrize("levels", [None, 0.5, "0.25, 0.75", ["0.25", "0.75"], [True, False],
                                    [0, 1]])
def test_levels_of_the_wrong_kind_are_refused(levels):
    with pytest.raises(ValueError, match="Quantile levels.*list of decimal numbers"):
        model_with(levels=levels)


@pytest.mark.parametrize("levels", [[0.25, 0.75], [0.1, 0.9], [0.025, 0.5, 0.975],
                                    (0.05, 0.25, 0.5, 0.75, 0.95)])
def test_levels_that_pair_up_around_the_median_are_accepted(levels):
    assert model_with(levels=levels).levels == tuple(levels)


@pytest.mark.parametrize("change, message", [
    ({"family": "ets"}, "'ets'"),
    ({"groups": ["price", "tide"]}, "tide"),
    ({"trees": 0}, "trees"),
    ({"params": {"alpha": 0.5}}, "alpha"),
    ({"params": {"num_leafs": 8}}, "num_leafs"),
    ({"history_days": 7}, "history_days"),
])
def test_an_entry_that_the_point_model_refuses_is_refused_for_the_quantiles_too(change, message):
    with pytest.raises(ValueError, match=f"LightGBM entry: .*{message}"):
        model_with({**ENTRY, **change})


def test_a_parameter_value_that_lightgbm_refuses_is_a_value_error_that_names_the_entry():
    model = model_with({**ENTRY, "params": {"num_leaves": 1}})

    with pytest.raises(ValueError, match="'candidate'.*num_leaves") as refused:
        model.fit(inputs_of(make_table()))

    assert isinstance(refused.value.__cause__, lightgbm.basic.LightGBMError)


# The settings for the results.

def test_the_params_are_the_entry_with_the_quantile_objective_and_the_levels():
    model = model_with()

    assert model.name == "candidate"
    assert model.params == {**ENTRY, "objective": "quantile", "quantile_levels": LEVELS}
    assert json.loads(json.dumps(model.params)) == model.params
    assert model.settings == ENTRY
