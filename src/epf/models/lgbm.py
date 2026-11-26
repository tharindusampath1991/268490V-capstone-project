"""LightGBM as a model of the backtest: boosted trees on the features of epf.features.builder.

A fit receives the inputs cut for delivery day D (epf.evaluation.cutoff) and
nothing else. It reads no file. It sets the three table parts of the inputs
side by side again and builds one training row per market time unit of every
delivery day before D. build_features cuts that table again for each of those
days, so a training row holds what was known when its own day was forecast.
The target of a row is the price of its market time unit.

The model never sees a price of D or later, a day-ahead value after D, an
actual load after D-2 or a weather value from a run that started after the
run hour on D-1. These values are not in the inputs. The last training day is
D-1 by the calendar. It is read from the delivery day of the inputs and not
from the last price.

Between two fits the trees stay as they are. The forecast of a day applies
them to the features of that day, which are built from its own inputs.

A row without a price is dropped, because LightGBM would store its target as
0. An empty feature stays empty, and LightGBM handles it as a missing value.
Nothing is filled and nothing is scaled.

Two fits on the same rows with the same seed gave the same forecast in the
tests. LightGBM states this for one machine and one version of the library
only, with deterministic and force_col_wise set, as they are here.

Prices are in EUR/MWh. Tables have a UTC index. Delivery days are in market time.
"""

from collections.abc import Collection
from dataclasses import replace
from datetime import timedelta

import lightgbm
import pandas as pd

from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.evaluation.cutoff import Columns, DayInputs, WeatherRule
from epf.features import builder
from epf.features.builder import Day, FeatureSettings, MakeIndex, build_features, day_features

FAMILY = "lgbm"
FORECAST = "forecast"
HISTORY = "history_days"
REQUIRED_KEYS = ("family", "groups", "objective", "trees", "params")
# The names under which LightGBM stores the squared and the absolute error.
OBJECTIVES = ("regression", "regression_l1")
ALLOWED_PARAMS = ("learning_rate", "num_leaves", "max_depth", "min_data_in_leaf",
                  "feature_fraction", "bagging_fraction", "bagging_freq", "lambda_l1",
                  "lambda_l2", "max_bin")


class LgbmModel:
    """LightGBM as a model of the backtest, set up from its config entry."""

    def __init__(self, name: str, settings: dict, features: FeatureSettings, columns: Columns,
                 rule: WeatherRule, seed: int):
        """Keep the name and the settings of a config entry and what the features are built with.

        Input: the name of the entry and its settings. family is lgbm. groups
            holds the feature groups the model uses, objective is regression
            for the squared error or regression_l1 for the absolute error,
            trees is the number of boosting rounds and params holds LightGBM
            parameters, keys of ALLOWED_PARAMS only. history_days may be there
            too. The backtest reads it. Then the feature settings of the
            config, the columns under each cut, the weather rule and the seed.
        Raises ValueError for settings that check_settings or the feature
            builder refuses.
        """
        check_settings(settings, features)
        self.name = name
        self.settings = settings
        self.features = model_features(features, settings["groups"], columns.day_ahead)
        self.columns = columns
        self.rule = rule
        self.seed = seed
        self.booster = None
        self.feature_names = None

    @property
    def params(self) -> dict:
        """The settings of the model, for the results."""
        return dict(self.settings)

    def fit(self, inputs: DayInputs) -> None:
        """Grow the trees on the training rows of the inputs.

        The trees and the feature names of an earlier fit are replaced, so a
        model can be fitted on one table after another.
        """
        rows, target = training_rows(inputs, self.features, self.columns, self.rule)
        self.booster = lightgbm.train(train_params(self.settings, self.seed),
                                      lightgbm.Dataset(rows, label=target),
                                      num_boost_round=self.settings["trees"])
        self.feature_names = list(rows.columns)

    def predict(self, inputs: DayInputs) -> pd.Series:
        """Return the forecast for the market time units of the delivery day.

        The trees of the last fit are applied to the features of this day,
        which are built from its inputs. Nothing is fitted again.
        Raises ValueError when the features are not those of the fit, in
            name or in order.
        """
        rows = day_features(inputs, self.features, inputs.holidays)
        # LightGBM takes the columns by their position and does not compare the names.
        if list(rows.columns) != self.feature_names:
            raise ValueError(f"The features of {inputs.delivery_day} are {list(rows.columns)}. "
                             f"The model was fitted on {self.feature_names}.")
        return pd.Series(self.booster.predict(rows), index=inputs.target_index, name=FORECAST)


def check_settings(settings: dict, features: FeatureSettings) -> None:
    """Refuse an entry that the model cannot run as it is written.

    Input: the settings of a config entry and the feature settings of the config.
    Raises ValueError for a missing or an unknown key, another family, no
        group, a group that the feature settings do not build, an objective
        outside OBJECTIVES, a number of trees that is not a whole number
        above 0, a parameter key outside ALLOWED_PARAMS and a history that is
        not longer than the longest lag of the features.
    """
    check_keys(settings)
    problems = []
    if settings["family"] != FAMILY:
        problems.append(f"the family is '{settings['family']}', not '{FAMILY}'")
    if not settings["groups"]:
        problems.append("it names no feature group")
    problems += [f"the feature settings do not build the group '{group}'"
                 for group in settings["groups"] if group not in features.groups]
    if settings["objective"] not in OBJECTIVES:
        problems.append(f"the objective '{settings['objective']}' is not among {OBJECTIVES}")
    trees = settings["trees"]
    if not isinstance(trees, int) or trees < 1:
        problems.append(f"trees must be a whole number above 0, not {trees}")
    # LightGBM ignores a key it does not know without an error, and a round count among
    # the parameters would replace the number of trees of the entry.
    refused = [key for key in settings["params"] if key not in ALLOWED_PARAMS]
    if refused:
        problems.append(f"the parameters {refused} are not among {ALLOWED_PARAMS}")
    history, longest_lag = settings.get(HISTORY), builder.history_days(features)
    if history is not None and history <= longest_lag:
        problems.append(f"{HISTORY} is {history} and the longest lag of the features is "
                        f"{longest_lag} days, so no training day is left")
    if problems:
        raise ValueError("LightGBM entry: " + "; ".join(problems) + ".")


def check_keys(settings: dict) -> None:
    """Refuse an entry that lacks one of REQUIRED_KEYS or holds a key the model does not know."""
    problems = [f"the key '{key}' is missing" for key in REQUIRED_KEYS if key not in settings]
    problems += [f"the key '{key}' is unknown" for key in settings
                 if key not in (*REQUIRED_KEYS, HISTORY)]
    if problems:
        raise ValueError("LightGBM entry: " + "; ".join(problems) + ".")


def model_features(features: FeatureSettings, groups: list[str],
                   day_ahead_columns: Collection[str]) -> FeatureSettings:
    """Return the feature settings with the groups of a model entry in place of their own.

    Input: the feature settings of the config, the groups of the entry and the
        columns under the day-ahead cut.
    Raises ValueError for settings that the feature builder refuses.
    """
    chosen = replace(features, groups=tuple(groups))
    builder.check_settings(chosen, day_ahead_columns)
    return chosen


def index_maker(target_index: pd.DatetimeIndex) -> MakeIndex:
    """Return the function that gives the market time units of a day on the grid of the inputs.

    Input: the market time units of a delivery day in UTC. Their step is one
        hour or 15 minutes.
    Output: hourly_index or quarter_hour_index.
    Raises ValueError for any other step.
    """
    step = target_index[1] - target_index[0]
    if step == timedelta(hours=1):
        return hourly_index
    if step == timedelta(minutes=15):
        return quarter_hour_index
    raise ValueError(f"The market time units have a step of {step}, which is neither one "
                     "hour nor 15 minutes.")


def known_table(inputs: DayInputs, columns: Columns) -> pd.DataFrame:
    """Set the three table parts of the inputs side by side as one table again.

    Input: the inputs of delivery day D and the columns under each cut.
    Output: a table with a UTC index that runs to the end of D, as the
        day-ahead part does. The price is empty from 00:00 market time on D
        and a delayed column from 00:00 on D-1, because the inputs hold
        nothing later. A price at a time that the day-ahead part does not
        have is left out.
    """
    table = inputs.day_ahead.copy()
    table[columns.price] = inputs.prices
    for column in inputs.delayed.columns:
        table[column] = inputs.delayed[column]
    return table


def training_days(inputs: DayInputs, skip_days: int) -> list[Day]:
    """Return the delivery days that a fit for delivery day D trains on.

    Input: the inputs of D, and the days at the start of the prices that are
        left out because the lags of the features read them.
    Output: the days from the first day with a price plus skip_days to D-1,
        as (day start, next day start) in market time. D-1 is the day before
        the delivery day of the inputs, wherever the prices end.
    Raises ValueError when no day is left.
    """
    days = []
    if len(inputs.prices):
        first_day = inputs.prices.index[0].tz_convert(inputs.market_tz).date()
        days = delivery_days(
            pd.Timestamp(first_day + timedelta(days=skip_days), tz=inputs.market_tz),
            pd.Timestamp(inputs.delivery_day, tz=inputs.market_tz))
    if not days:
        raise ValueError(f"No training day before {inputs.delivery_day}: the prices of the "
                         f"inputs must start more than {skip_days} days before it.")
    return days


def training_rows(inputs: DayInputs, features: FeatureSettings, columns: Columns,
                  rule: WeatherRule) -> tuple[pd.DataFrame, pd.Series]:
    """Return the features and the target of every training row of a fit.

    Input: the inputs of delivery day D, the feature settings of the model,
        the columns under each cut and the weather rule.
    Output: the features with a UTC index, one row per market time unit of
        the training days, and the price of each row. Every day is built from
        day_inputs on the known table, so from what was known when that day
        was forecast. A row without a price is left out. An empty feature
        stays empty.
    Raises ValueError when there is no training day.
    """
    table = known_table(inputs, columns)
    days = training_days(inputs, builder.history_days(features))
    # Without a weather table the inputs hold a weather frame without columns.
    weather, weather_rule = None, None
    if len(inputs.weather.columns):
        weather, weather_rule = inputs.weather, rule
    rows = build_features(table, days, index_maker(inputs.target_index), columns, features,
                          inputs.holidays, weather, weather_rule)
    target = table[columns.price].reindex(rows.index)
    has_price = target.notna()
    return rows[has_price], target[has_price]


def train_params(settings: dict, seed: int) -> dict:
    """Return the LightGBM parameters of a fit.

    Input: the settings of a config entry and the seed of the project.
    Output: the parameters of the entry, its objective and the keys that the
        model always sets itself. The number of trees is not among them. It
        is handed over as the number of boosting rounds.
    """
    # The LightGBM documentation names deterministic for the same result from the same rows
    # and parameters, and asks for force_col_wise or force_row_wise with it. A fit without
    # verbosity keeps the level of the fit before it.
    return {**settings["params"], "objective": settings["objective"], "seed": seed,
            "deterministic": True, "force_col_wise": True, "verbosity": -1}
