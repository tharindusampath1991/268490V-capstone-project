"""Tests for the feature builder of the LightGBM model, with its leakage tests.

They use small synthetic tables, no network and no data files. Every value of
a table is a code of its own timestamp: the hours since EPOCH plus an offset
per column. So a feature value says which timestamp it was read from.
"""

import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epf.config import REPO_ROOT, load_config
from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.evaluation.cutoff import Columns, WeatherRule, cut_columns, day_inputs, weather_rule
from epf.features import builder
from epf.features.builder import (
    FeatureSettings,
    build_features,
    day_features,
    feature_settings,
    history_days,
)
from epf.models.naive import seasonal_naive

MARKET_TZ = "Europe/Berlin"
EPOCH = pd.Timestamp("2025-01-01", tz="UTC")
OFFSET = {"price": 0.0, "load_forecast": 1e6, "wind_onshore_forecast": 2e6,
          "wind_offshore_forecast": 3e6, "solar_forecast": 4e6, "actual_load": 5e6}
RADIATION_OFFSET = 7e6
COLUMNS = Columns(price="price",
                  day_ahead=("load_forecast", "wind_onshore_forecast", "wind_offshore_forecast",
                             "solar_forecast"),
                  delayed=("actual_load",))
RULE = WeatherRule(columns=("temperature_2m", "shortwave_radiation"), run_column="run",
                   run_hour_utc=0)
SETTINGS = FeatureSettings(
    groups=("price", "calendar", "load_forecast", "wind_forecast", "solar_forecast",
            "actual_load", "weather"),
    price_lag_days=(1, 2, 7),
    price_day_stats=("mean", "min", "max", "last"),
    forecasts={"load_forecast": ("load_forecast",),
               "wind_forecast": ("wind_onshore_forecast", "wind_offshore_forecast"),
               "solar_forecast": ("solar_forecast",)},
    forecast_lag_days=(1, 7),
    delayed=("actual_load",),
    delayed_lag_days=(2,),
    weather=("temperature_2m", "shortwave_radiation"),
    weather_hour_before=("shortwave_radiation",),
)
PRICE_FEATURES = ["price_lag_1", "price_lag_2", "price_lag_7", "price_d1_mean", "price_d1_min",
                  "price_d1_max", "price_d1_last"]
FORECAST_FEATURES = ["load_forecast", "load_forecast_lag_1", "load_forecast_lag_7",
                     "wind_forecast", "wind_forecast_lag_1", "wind_forecast_lag_7",
                     "solar_forecast", "solar_forecast_lag_1", "solar_forecast_lag_7"]
WEATHER_FEATURES = ["temperature_2m", "shortwave_radiation"]


def market_time(day: str | date) -> pd.Timestamp:
    """00:00 in market time on a day."""
    return pd.Timestamp(day, tz=MARKET_TZ)


def day_after(day: str, days: int = 1) -> date:
    """The calendar day some days after a day. A negative number goes back."""
    return date.fromisoformat(day) + timedelta(days=days)


def code(moments: pd.DatetimeIndex) -> np.ndarray:
    """The hours from EPOCH to each moment."""
    return np.asarray((moments - EPOCH) / timedelta(hours=1), dtype=float)


def at(day: str, clock: str = "00:00") -> float:
    """The code of a wall-clock time in market time."""
    return (pd.Timestamp(f"{day} {clock}", tz=MARKET_TZ) - EPOCH) / timedelta(hours=1)


def make_table(first_day: str, end_day: str, make_index=hourly_index,
               columns=tuple(OFFSET)) -> pd.DataFrame:
    """A table from first_day up to the start of end_day. Each value is the code of its time."""
    index = make_index(market_time(first_day), market_time(end_day))
    return pd.DataFrame({column: code(index) + OFFSET[column] for column in columns}, index=index)


def make_weather(first_day: str, end_day: str) -> pd.DataFrame:
    """Hourly weather. The hours of each delivery day come from the 00:00 UTC run of the day before."""
    index = hourly_index(market_time(first_day), market_time(end_day))
    delivery_day = index.tz_convert(MARKET_TZ).normalize().tz_localize(None)
    return pd.DataFrame({"temperature_2m": code(index),
                         "shortwave_radiation": code(index) + RADIATION_OFFSET,
                         "run": (delivery_day - timedelta(days=1)).tz_localize("UTC")},
                        index=index)


def days_from(first_day: str, count: int = 1) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """The delivery days from first_day on, as (day start, next day start)."""
    return delivery_days(market_time(first_day), market_time(day_after(first_day, count)))


def features_of(table: pd.DataFrame, day: str, make_index=hourly_index, settings=SETTINGS,
                weather: pd.DataFrame | None = None, holidays=frozenset(),
                count: int = 1) -> pd.DataFrame:
    """The features of the delivery days from day on."""
    rule = None if weather is None else RULE
    return build_features(table, days_from(day, count), make_index, COLUMNS, settings, holidays,
                          weather, rule)


def with_settings(**changes) -> FeatureSettings:
    """SETTINGS with some fields replaced."""
    return FeatureSettings(**{**SETTINGS.__dict__, **changes})


# Shape of the frame.

def test_a_day_gives_one_row_per_market_time_unit_and_the_features_of_every_group():
    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    assert features.index.equals(hourly_index(market_time("2026-07-01"), market_time("2026-07-02")))
    assert list(features.columns) == (
        PRICE_FEATURES + ["hour", "weekday", "holiday"] + FORECAST_FEATURES
        + ["actual_load_lag_2"] + WEATHER_FEATURES)


# 2026-10-25 has 25 hours and 2026-03-29 has 23.
@pytest.mark.parametrize("day, make_index, rows", [
    ("2026-10-25", hourly_index, 25), ("2026-03-29", hourly_index, 23),
    ("2026-07-01", quarter_hour_index, 96), ("2026-10-25", quarter_hour_index, 100),
    ("2026-03-29", quarter_hour_index, 92)])
def test_a_clock_change_day_has_the_rows_of_its_own_length(day, make_index, rows):
    table = make_table(str(day_after(day, -10)), str(day_after(day, 3)), make_index)

    features = features_of(table, day, make_index)

    assert len(features) == rows
    assert features.index.equals(make_index(market_time(day), market_time(day_after(day))))


def test_several_days_follow_each_other_with_every_time_once():
    table = make_table("2026-10-10", "2026-11-05")

    features = features_of(table, "2026-10-24", count=3)

    assert features.index.equals(hourly_index(market_time("2026-10-24"), market_time("2026-10-27")))
    assert len(features) == 24 + 25 + 24


def test_the_frame_holds_numbers_only_and_never_the_price_of_the_delivery_day():
    table = make_table("2026-06-20", "2026-07-05")

    features = features_of(table, "2026-07-01", weather=make_weather("2026-06-20", "2026-07-05"))

    assert "price" not in features.columns
    assert all(pd.api.types.is_numeric_dtype(kind) for kind in features.dtypes)
    assert not (features[PRICE_FEATURES].to_numpy() >= at("2026-07-01")).any()


# Price lags.

def test_a_price_lag_is_the_price_at_the_same_time_some_days_before():
    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    hours = np.arange(24)
    assert features["price_lag_1"].tolist() == (at("2026-06-30") + hours).tolist()
    assert features["price_lag_2"].tolist() == (at("2026-06-29") + hours).tolist()
    assert features["price_lag_7"].tolist() == (at("2026-06-24") + hours).tolist()


# 2026-07-01 is a plain day. On each of the six other days, D, D-1 or D-7 is a clock-change day.
@pytest.mark.parametrize("make_index", [hourly_index, quarter_hour_index])
@pytest.mark.parametrize("day", ["2026-07-01", "2026-10-25", "2026-10-26", "2026-11-01",
                                 "2026-03-29", "2026-03-30", "2026-04-05"])
def test_the_price_lag_of_7_days_equals_the_seasonal_naive_forecast(day, make_index):
    table = make_table(str(day_after(day, -10)), str(day_after(day, 3)), make_index)
    target = make_index(market_time(day), market_time(day_after(day)))
    known = table.loc[table.index < market_time(day), "price"]

    features = features_of(table, day, make_index)

    naive = seasonal_naive(known, target, MARKET_TZ, 7)
    assert naive.notna().all()
    assert features["price_lag_7"].tolist() == naive.tolist()


def test_both_02_hours_of_a_25_hour_day_take_the_02_price_seven_days_before():
    features = features_of(make_table("2026-10-10", "2026-10-28"), "2026-10-25")

    assert features["price_lag_7"].iloc[1:5].tolist() == [
        at("2026-10-18", "01:00"), at("2026-10-18", "02:00"), at("2026-10-18", "02:00"),
        at("2026-10-18", "03:00")]


def test_after_a_25_hour_day_the_lag_of_1_day_follows_the_wall_clock():
    # 2026-10-25 01:00 is 25 hours before 2026-10-26 01:00. Its 02:00 exists twice, so the
    # 02:00 of the next day takes the price exactly 24 hours before.
    features = features_of(make_table("2026-10-10", "2026-10-28"), "2026-10-26")

    target = code(features.index)
    assert (target - features["price_lag_1"]).iloc[:4].tolist() == [25.0, 25.0, 24.0, 24.0]


def test_a_price_lag_is_empty_when_the_table_does_not_reach_back_that_far():
    features = features_of(make_table("2026-06-28", "2026-07-05"), "2026-07-01")

    assert features["price_lag_7"].isna().all()
    assert features["price_lag_2"].notna().all()


# Statistics of the prices of D-1.

@pytest.mark.parametrize("day, make_index, values", [
    ("2026-07-01", hourly_index, 24), ("2026-10-26", hourly_index, 25),
    ("2026-03-30", hourly_index, 23), ("2026-07-01", quarter_hour_index, 96),
    ("2026-10-26", quarter_hour_index, 100)])
def test_the_day_statistics_cover_every_market_time_unit_of_the_day_before(day, make_index,
                                                                           values):
    table = make_table(str(day_after(day, -10)), str(day_after(day, 3)), make_index)
    first = at(str(day_after(day, -1)))
    step = 1.0 if make_index is hourly_index else 0.25
    last = first + (values - 1) * step

    features = features_of(table, day, make_index)

    assert features["price_d1_mean"].tolist() == pytest.approx([(first + last) / 2] * len(features))
    assert set(features["price_d1_min"]) == {first}
    assert set(features["price_d1_max"]) == {last}
    assert set(features["price_d1_last"]) == {last}


def test_the_day_statistics_are_empty_on_the_first_day_of_the_table():
    features = features_of(make_table("2026-07-01", "2026-07-05"), "2026-07-01")

    assert features[["price_d1_mean", "price_d1_min", "price_d1_max", "price_d1_last"]] \
        .isna().all().all()


def test_an_empty_price_on_the_day_before_leaves_mean_minimum_and_maximum_empty():
    table = make_table("2026-06-20", "2026-07-05")
    table.loc[pd.Timestamp("2026-06-30 05:00", tz=MARKET_TZ), "price"] = np.nan

    features = features_of(table, "2026-07-01")

    assert features[["price_d1_mean", "price_d1_min", "price_d1_max"]].isna().all().all()
    assert set(features["price_d1_last"]) == {at("2026-06-30", "23:00")}


# Calendar.

def test_hour_is_the_wall_clock_hour_in_market_time():
    assert features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01")["hour"].tolist() \
        == list(range(24))


def test_a_25_hour_day_has_hour_2_twice_and_a_23_hour_day_has_none():
    long_day = features_of(make_table("2026-10-10", "2026-10-28"), "2026-10-25")
    short_day = features_of(make_table("2026-03-15", "2026-04-02"), "2026-03-29")

    assert long_day["hour"].tolist() == [0, 1, 2, 2] + list(range(3, 24))
    assert short_day["hour"].tolist() == [0, 1] + list(range(3, 24))


def test_weekday_counts_from_monday_as_0():
    table = make_table("2026-06-20", "2026-07-08")

    features = features_of(table, "2026-07-01", count=5)   # Wednesday to Sunday

    assert features["weekday"].iloc[::24].tolist() == [2, 3, 4, 5, 6]


def test_holiday_is_1_on_a_delivery_day_in_the_holiday_set_and_0_on_other_days():
    table = make_table("2026-06-20", "2026-07-08")

    features = features_of(table, "2026-07-01", count=2, holidays={date(2026, 7, 2)})

    assert features["holiday"].tolist() == [0] * 24 + [1] * 24


def test_the_15_minute_frame_also_counts_the_quarter_of_the_hour():
    table = make_table("2026-06-20", "2026-07-05", quarter_hour_index)

    features = features_of(table, "2026-07-01", quarter_hour_index)

    assert features["quarter_hour"].tolist() == [0, 1, 2, 3] * 24
    assert features["hour"].tolist() == [hour for hour in range(24) for _ in range(4)]
    assert list(features.columns)[7:11] == ["hour", "quarter_hour", "weekday", "holiday"]


def test_the_hourly_frame_has_no_quarter_column():
    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    assert "hour" in features.columns
    assert "quarter_hour" not in features.columns


# Day-ahead forecasts.

def test_a_forecast_feature_is_the_forecast_at_the_target_time_and_at_its_lags():
    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    hours = np.arange(24)
    offset = OFFSET["load_forecast"]
    assert features["load_forecast"].tolist() == (at("2026-07-01") + hours + offset).tolist()
    assert features["load_forecast_lag_1"].tolist() == (at("2026-06-30") + hours + offset).tolist()
    assert features["load_forecast_lag_7"].tolist() == (at("2026-06-24") + hours + offset).tolist()
    assert features["solar_forecast"].tolist() \
        == (at("2026-07-01") + hours + OFFSET["solar_forecast"]).tolist()


def test_the_wind_forecast_is_the_sum_of_onshore_and_offshore():
    table = make_table("2026-06-20", "2026-07-05")

    features = features_of(table, "2026-07-01")

    target = features.index
    expected = table.loc[target, "wind_onshore_forecast"] + table.loc[target, "wind_offshore_forecast"]
    assert features["wind_forecast"].tolist() == expected.tolist()
    assert features["wind_forecast"].iloc[0] == 2 * at("2026-07-01") + 5e6


def test_a_zone_without_offshore_wind_takes_the_onshore_forecast_alone():
    table = make_table("2026-06-20", "2026-07-05").drop(columns="wind_offshore_forecast")

    features = features_of(table, "2026-07-01")

    assert features["wind_forecast"].tolist() \
        == table.loc[features.index, "wind_onshore_forecast"].tolist()


def test_a_zone_without_a_solar_forecast_keeps_the_solar_columns_and_they_are_empty():
    with_solar = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01")
    table = make_table("2026-06-20", "2026-07-05").drop(columns="solar_forecast")

    features = features_of(table, "2026-07-01")

    solar = ["solar_forecast", "solar_forecast_lag_1", "solar_forecast_lag_7"]
    assert list(features.columns) == list(with_solar.columns)
    assert features[solar].isna().all().all()
    assert features.drop(columns=solar + WEATHER_FEATURES).notna().all().all()


# Gaps stay empty.

def test_an_empty_forecast_value_stays_empty_and_no_row_is_dropped():
    table = make_table("2026-06-20", "2026-07-12")
    table.loc[pd.Timestamp("2026-07-01 05:00", tz=MARKET_TZ), "load_forecast"] = np.nan

    features = features_of(table, "2026-07-01", count=8)

    assert len(features) == 8 * 24
    empty = features[["load_forecast", "load_forecast_lag_1", "load_forecast_lag_7"]].isna()
    assert empty.sum().tolist() == [1, 1, 1]
    assert empty.idxmax().tolist() == [pd.Timestamp(f"2026-07-{day} 05:00", tz=MARKET_TZ)
                                       for day in ("01", "02", "08")]
    assert features.drop(columns=[*empty.columns, *WEATHER_FEATURES]).notna().all().all()


def test_the_wind_forecast_is_empty_when_one_of_its_columns_is_empty():
    table = make_table("2026-06-20", "2026-07-05")
    table.loc[pd.Timestamp("2026-07-01 05:00", tz=MARKET_TZ), "wind_onshore_forecast"] = np.nan

    features = features_of(table, "2026-07-01")

    assert features["wind_forecast"].isna().tolist() == [hour == 5 for hour in range(24)]


def test_an_empty_actual_load_value_leaves_its_lag_empty():
    table = make_table("2026-06-20", "2026-07-05")
    table.loc[pd.Timestamp("2026-06-29 05:00", tz=MARKET_TZ), "actual_load"] = np.nan

    features = features_of(table, "2026-07-01")

    assert features["actual_load_lag_2"].isna().tolist() == [hour == 5 for hour in range(24)]


# Actual load.

def test_actual_load_is_taken_two_days_before():
    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    assert features["actual_load_lag_2"].tolist() \
        == (at("2026-06-29") + np.arange(24) + OFFSET["actual_load"]).tolist()


def test_actual_load_of_the_day_before_is_never_there_whatever_the_settings_ask():
    settings = with_settings(delayed_lag_days=(1, 2))

    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01", settings=settings)

    assert features["actual_load_lag_1"].isna().all()
    assert features["actual_load_lag_2"].notna().all()


# Weather.

def test_a_weather_value_at_the_timestamp_goes_to_the_hour_that_starts_there():
    weather = make_weather("2026-06-20", "2026-07-05")

    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01", weather=weather)

    assert features["temperature_2m"].tolist() == (at("2026-07-01") + np.arange(24)).tolist()


def test_radiation_is_taken_one_hour_later_and_the_last_hour_of_the_day_is_empty():
    weather = make_weather("2026-06-20", "2026-07-05")

    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01", weather=weather)

    radiation = features["shortwave_radiation"]
    assert radiation.iloc[:23].tolist() \
        == (at("2026-07-01", "01:00") + np.arange(23) + RADIATION_OFFSET).tolist()
    assert radiation.isna().tolist() == [False] * 23 + [True]


def test_on_the_15_minute_grid_an_hourly_weather_value_stands_on_its_four_quarter_hours():
    table = make_table("2026-06-20", "2026-07-05", quarter_hour_index)
    weather = make_weather("2026-06-20", "2026-07-05")

    features = features_of(table, "2026-07-01", quarter_hour_index, weather=weather)

    hours = np.repeat(np.arange(24), 4)
    assert features["temperature_2m"].tolist() == (at("2026-07-01") + hours).tolist()
    assert features["shortwave_radiation"].iloc[:92].tolist() \
        == (at("2026-07-01", "01:00") + hours[:92] + RADIATION_OFFSET).tolist()
    assert features["shortwave_radiation"].isna().tolist() == [False] * 92 + [True] * 4


def test_a_25_hour_day_has_weather_for_every_hour():
    table = make_table("2026-10-10", "2026-10-28")

    features = features_of(table, "2026-10-25", weather=make_weather("2026-10-10", "2026-10-28"))

    assert features["temperature_2m"].tolist() == (at("2026-10-25") + np.arange(25)).tolist()
    assert features["shortwave_radiation"].isna().tolist() == [False] * 24 + [True]


def test_without_a_weather_table_the_weather_columns_are_there_and_empty():
    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01")

    assert features[WEATHER_FEATURES].isna().all().all()


def test_weather_is_empty_on_days_before_the_weather_table_starts():
    weather = make_weather("2026-07-02", "2026-07-05")

    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01", count=2,
                           weather=weather)

    assert features["temperature_2m"].isna().tolist() == [True] * 24 + [False] * 24


# Feature groups.

def test_only_the_groups_of_the_settings_are_built():
    table = make_table("2026-06-20", "2026-07-05")

    price_only = features_of(table, "2026-07-01", settings=with_settings(groups=("price",)))
    no_solar = features_of(table, "2026-07-01", settings=with_settings(
        groups=("price", "calendar", "load_forecast", "wind_forecast", "actual_load")))

    assert list(price_only.columns) == PRICE_FEATURES
    assert list(no_solar.columns) == (
        PRICE_FEATURES + ["hour", "weekday", "holiday"] + FORECAST_FEATURES[:6]
        + ["actual_load_lag_2"])


def test_a_group_gives_the_same_values_whatever_other_groups_are_built():
    table = make_table("2026-06-20", "2026-07-05")

    everything = features_of(table, "2026-07-01")
    price_only = features_of(table, "2026-07-01", settings=with_settings(groups=("price",)))

    pd.testing.assert_frame_equal(everything[PRICE_FEATURES], price_only)


def config_with_features() -> dict:
    """The parts of a config that the feature settings are read from."""
    return {
        "backtest": {"price_column": "price",
                     "day_ahead_columns": ["load_forecast", "wind_onshore_forecast"],
                     "delayed_columns": ["actual_load"], "weather_run_column": "run"},
        "open_meteo": {"variables": ["temperature_2m", "shortwave_radiation"], "run_hour_utc": 0},
        "features": {"groups": ["price", "wind_forecast", "weather"],
                     "price_lag_days": [1, 7], "price_day_stats": ["mean"],
                     "forecasts": {"wind_forecast": ["wind_onshore_forecast"]},
                     "forecast_lag_days": [1], "actual_load_lag_days": [2],
                     "weather_hour_before": ["shortwave_radiation"]},
    }


def test_feature_settings_are_read_from_the_config():
    assert feature_settings(config_with_features()) == FeatureSettings(
        groups=("price", "wind_forecast", "weather"), price_lag_days=(1, 7),
        price_day_stats=("mean",), forecasts={"wind_forecast": ("wind_onshore_forecast",)},
        forecast_lag_days=(1,), delayed=("actual_load",), delayed_lag_days=(2,),
        weather=("temperature_2m", "shortwave_radiation"),
        weather_hour_before=("shortwave_radiation",))


@pytest.mark.parametrize("key, value, message", [
    ("groups", ["price", "tide"], "tide"),
    ("price_day_stats", ["mean", "median"], "median"),
    ("price_lag_days", [0, 1], "price_lag_days"),
    ("forecasts", {"wind_forecast": ["wind_speed"]}, "wind_speed"),
    ("weather_hour_before", ["rain"], "rain"),
])
def test_settings_that_the_builder_cannot_serve_are_refused(key, value, message):
    config = config_with_features()
    config["features"][key] = value

    with pytest.raises(ValueError, match=message):
        feature_settings(config)


def test_the_project_config_gives_settings_that_are_accepted():
    settings = feature_settings(load_config())

    assert "price" in settings.groups
    assert history_days(settings) >= 7


def test_history_days_is_the_longest_lag_of_the_settings():
    assert history_days(SETTINGS) == 7
    assert history_days(with_settings(forecast_lag_days=(1, 14))) == 14


def test_settings_without_any_lag_still_read_the_day_before_for_its_statistics():
    no_lags = with_settings(price_lag_days=(), forecast_lag_days=(), delayed_lag_days=())

    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01", settings=no_lags)

    assert history_days(no_lags) == 1
    assert set(features["price_d1_last"]) == {at("2026-06-30", "23:00")}


def test_more_history_than_the_longest_lag_does_not_change_a_feature():
    short = features_of(make_table("2026-06-24", "2026-07-05"), "2026-07-01")
    long = features_of(make_table("2026-05-01", "2026-07-05"), "2026-07-01")

    assert short[PRICE_FEATURES + FORECAST_FEATURES].notna().all().all()
    pd.testing.assert_frame_equal(short, long)


# The leakage rule (PROJECT_CONTEXT section 5). A value is the code of its timestamp, so the
# highest value of a feature is the latest timestamp it read.

def latest_read(features: pd.DataFrame, names: list[str], offset: float = 0.0,
                columns_summed: int = 1) -> float:
    """The code of the latest timestamp that the named features read."""
    return (np.nanmax(features[names].to_numpy()) - offset) / columns_summed


# 2026-10-25 has 25 hours and 2026-03-29 has 23. Each is taken as D and as D-1.
@pytest.mark.parametrize("make_index, step", [(hourly_index, 1.0), (quarter_hour_index, 0.25)])
@pytest.mark.parametrize("day", ["2026-07-01", "2026-10-25", "2026-10-26", "2026-03-29",
                                 "2026-03-30"])
def test_no_feature_reads_a_timestamp_after_its_cut(day, make_index, step):
    first, end = str(day_after(day, -10)), str(day_after(day, 3))
    day_start, day_end = at(day), at(str(day_after(day)))

    features = features_of(make_table(first, end, make_index), day, make_index,
                           weather=make_weather(first, end))

    assert latest_read(features, PRICE_FEATURES) == day_start - step
    assert latest_read(features, FORECAST_FEATURES[:3], OFFSET["load_forecast"]) == day_end - step
    assert latest_read(features, FORECAST_FEATURES[3:6], 5e6, columns_summed=2) == day_end - step
    assert latest_read(features, FORECAST_FEATURES[6:], OFFSET["solar_forecast"]) == day_end - step
    assert latest_read(features, ["actual_load_lag_2"], OFFSET["actual_load"]) \
        == at(str(day_after(day, -1))) - step
    assert latest_read(features, ["temperature_2m"]) == day_end - 1.0
    assert latest_read(features, ["shortwave_radiation"], RADIATION_OFFSET) == day_end - 1.0


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


@pytest.mark.parametrize("make_index", [hourly_index, quarter_hour_index])
@pytest.mark.parametrize("day", ["2026-07-01", "2026-10-25", "2026-10-26", "2026-03-29"])
def test_changing_every_value_after_the_cuts_leaves_the_features_unchanged(day, make_index):
    first, end = str(day_after(day, -10)), str(day_after(day, 3))
    table, weather = make_table(first, end, make_index), make_weather(first, end)
    changed_table, changed_weather = change_after_the_cuts(table, weather, day)

    before = features_of(table, day, make_index, weather=weather)
    after = features_of(changed_table, day, make_index, weather=changed_weather)

    assert before.drop(columns="shortwave_radiation").notna().all().all()
    pd.testing.assert_frame_equal(before, after)


@pytest.mark.parametrize("column, last_seen, feature", [
    ("price", "2026-06-30 23:00", "price_d1_last"),
    ("load_forecast", "2026-07-01 23:00", "load_forecast"),
    ("wind_offshore_forecast", "2026-07-01 23:00", "wind_forecast"),
    ("solar_forecast", "2026-07-01 23:00", "solar_forecast"),
    ("actual_load", "2026-06-29 23:00", "actual_load_lag_2"),
])
def test_changing_the_last_value_before_a_cut_changes_a_feature(column, last_seen, feature):
    table = make_table("2026-06-20", "2026-07-05")
    changed = table.copy()
    changed.loc[pd.Timestamp(last_seen, tz=MARKET_TZ), column] += 1000

    before = features_of(table, "2026-07-01")
    after = features_of(changed, "2026-07-01")

    assert (after[feature] - before[feature]).iloc[-1] == 1000


def test_weather_from_a_later_run_does_not_reach_the_features():
    weather = make_weather("2026-06-20", "2026-07-05")
    on_the_day = weather.index >= market_time("2026-07-01")
    weather.loc[on_the_day, "run"] = pd.Timestamp("2026-07-01", tz="UTC")

    features = features_of(make_table("2026-06-20", "2026-07-05"), "2026-07-01", weather=weather)

    assert features[WEATHER_FEATURES].isna().all().all()


@pytest.mark.parametrize("make_index", [hourly_index, quarter_hour_index])
def test_the_builder_hands_every_day_inputs_that_end_at_the_cuts(monkeypatch, make_index):
    seen = []

    def record(inputs, settings, holidays):
        seen.append(inputs)
        return pd.DataFrame(index=inputs.target_index)

    monkeypatch.setattr(builder, "day_features", record)
    table = make_table("2026-10-10", "2026-11-05", make_index)

    features_of(table, "2026-10-20", make_index, count=14,
                weather=make_weather("2026-10-10", "2026-11-05"))

    assert len(seen) == 14
    for inputs in seen:
        day = inputs.delivery_day
        assert inputs.prices.index.max() < market_time(day)
        assert inputs.day_ahead.index.max() < market_time(day + timedelta(days=1))
        assert inputs.delayed.index.max() < market_time(day - timedelta(days=1))
        assert inputs.weather.index.max() < market_time(day + timedelta(days=1))
        assert inputs.weather["run"].max() <= pd.Timestamp(day - timedelta(days=1), tz="UTC")
        assert inputs.prices.index.min() == market_time(day - timedelta(days=7))


def test_the_features_of_a_day_come_from_its_cut_inputs_alone():
    table = make_table("2026-06-20", "2026-07-05")
    weather = make_weather("2026-06-20", "2026-07-05")
    day_start, day_end = market_time("2026-07-01"), market_time("2026-07-02")
    inputs = day_inputs(table, day_start, day_end, hourly_index(day_start, day_end), COLUMNS,
                        weather=weather, rule=RULE)

    from_inputs = day_features(inputs, SETTINGS, frozenset())

    assert from_inputs.shape == (24, 22)
    pd.testing.assert_frame_equal(from_inputs, features_of(table, "2026-07-01", weather=weather))


# The resolution switch. Hourly prices end on 2025-09-30 and 15-minute prices start on
# 2025-10-01. The hourly table runs through the switch, the 15-minute table starts on it.

def test_the_hourly_frame_runs_through_the_switch_day_without_a_break():
    table = make_table("2025-09-20", "2025-10-05")

    features = features_of(table, "2025-09-30", count=3)

    assert len(features) == 3 * 24
    assert features[PRICE_FEATURES].notna().all().all()
    assert (code(features.index) - features["price_lag_1"]).tolist() == [24.0] * 72


def test_the_15_minute_frame_has_empty_lags_until_its_table_reaches_back_far_enough():
    table = make_table("2025-10-01", "2025-10-12", quarter_hour_index)

    features = features_of(table, "2025-10-01", quarter_hour_index, count=9)

    days_with_a_value = features[PRICE_FEATURES].notna().groupby(
        features.index.tz_convert(MARKET_TZ).date).all()
    assert len(features) == 9 * 96
    assert days_with_a_value["price_lag_1"].tolist() == [False] + [True] * 8
    assert days_with_a_value["price_d1_mean"].tolist() == [False] + [True] * 8
    assert days_with_a_value["price_lag_2"].tolist() == [False] * 2 + [True] * 7
    assert days_with_a_value["price_lag_7"].tolist() == [False] * 7 + [True] * 2


# The project config and the code.

def test_every_column_that_the_project_features_read_stands_under_a_cut():
    config = load_config()
    settings = feature_settings(config)

    read = {column for columns in settings.forecasts.values() for column in columns}
    assert read <= set(cut_columns(config).day_ahead)
    assert set(settings.delayed) == set(cut_columns(config).delayed)
    assert set(settings.weather) == set(weather_rule(config).columns)
    assert min(settings.delayed_lag_days) >= 2


def test_the_feature_code_names_no_zone():
    config = load_config()
    names = [str(zone[key]) for zone in config["zones"] for key in ("key", "energy_charts")]
    names += [zone["weather_point"]["place"] for zone in config["zones"]]
    sources = sorted((REPO_ROOT / "src" / "epf" / "features").glob("*.py"))
    sources.append(REPO_ROOT / "src" / "epf" / "evaluation" / "cutoff.py")

    assert len(sources) >= 3
    for source in sources:
        text = Path(source).read_text(encoding="utf-8")
        found = [name for name in names if re.search(rf"\b{re.escape(name)}\b", text)]
        assert found == [], f"{source.name} names {found}"
