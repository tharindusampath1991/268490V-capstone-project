"""Tests for the config loader. They use no network and no data files."""

import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from entsoe.entsoe import QUARTER_MTU_SDAC_GOLIVE
from entsoe.mappings import lookup_area

from epf.config import REPO_ROOT, load_config, ordered_zones
from epf.data.clean import ENTSOE_NAMES
from epf.data.market_time import split_starts
from epf.data.validate import HOURLY, QUARTER_HOUR, WEATHER_TABLE, load_approved_gaps
from epf.evaluation.backtest import build_model
from epf.evaluation.cutoff import cut_columns
from epf.evaluation.quantiles import quantile_model
from epf.features.holiday_calendar import holiday_dates


def zone_entry(key: str, group: str) -> dict:
    """One zone entry shaped like those in config/config.yaml."""
    return {"key": key, "holiday_country": "XX", "group": group}


def test_ordered_zones_puts_core_zones_before_extra_zones():
    config = {"zones": [zone_entry("A", "extra"), zone_entry("B", "core"),
                        zone_entry("C", "extra"), zone_entry("D", "core")]}

    keys = [zone.key for zone in ordered_zones(config)]

    assert keys == ["B", "D", "A", "C"]


def test_ordered_zones_rejects_an_unknown_group():
    config = {"zones": [zone_entry("A", "core"), zone_entry("B", "optional")]}

    with pytest.raises(ValueError, match="B.*optional"):
        ordered_zones(config)


def test_project_config_zone_keys_are_entsoe_area_names():
    zones = ordered_zones(load_config())

    assert zones
    for zone in zones:
        assert lookup_area(zone.key).name == zone.key


def test_project_config_switch_instant_matches_the_entsoe_client():
    market = load_config()["market"]

    switch = pd.Timestamp(market["quarter_hour_start"], tz=market["timezone"])

    assert switch == QUARTER_MTU_SDAC_GOLIVE


def test_project_config_gives_every_zone_a_weather_point_on_the_globe():
    for zone in ordered_zones(load_config()):
        point = zone.weather_point

        assert point["place"]
        assert -90 <= point["latitude"] <= 90
        assert -180 <= point["longitude"] <= 180


def test_project_config_split_dates_follow_from_the_last_delivery_day():
    config = load_config()
    last_day, splits = config["data"]["end"], config["splits"]

    if last_day is None:
        assert splits["validation_start"] is None
        assert splits["test_start"] is None
        return
    validation_start, test_start = split_starts(
        date.fromisoformat(last_day), splits["test_days"], splits["validation_days"])
    assert splits["validation_start"] == validation_start.isoformat()
    assert splits["test_start"] == test_start.isoformat()


def test_project_config_drops_only_columns_of_configured_zones_that_are_not_kept():
    config = load_config()
    gate = config["coverage_gate"]
    zone_keys = {zone.key for zone in ordered_zones(config)}
    kept = {(mark["zone"], mark["column"]) for mark in gate["keep_columns"]}

    assert gate["drop_columns"]
    for mark in gate["drop_columns"]:
        assert mark["zone"] in zone_keys
        assert (mark["zone"], mark["column"]) not in kept


def test_project_approved_gaps_cover_every_zone_and_allow_no_empty_price():
    config = load_config()
    approved = load_approved_gaps(REPO_ROOT / config["paths"]["approved_gaps"])
    drops = {(mark["zone"], ENTSOE_NAMES[mark["column"]])
             for mark in config["coverage_gate"]["drop_columns"]}

    assert list(approved) == [zone.key for zone in ordered_zones(config)]
    for zone_key, tables in approved.items():
        assert list(tables) == [HOURLY, QUARTER_HOUR, WEATHER_TABLE]
        for name in (HOURLY, QUARTER_HOUR):
            assert tables[name]["price"] == 0
            assert not any((zone_key, column) in drops for column in tables[name])


def test_project_config_gives_every_zone_holiday_categories_the_package_supports():
    for zone in ordered_zones(load_config()):
        days = holiday_dates(zone.holiday_country, zone.holiday_categories, [2026])

        assert "public" in zone.holiday_categories
        assert days


def test_ordered_zones_uses_public_holidays_when_a_zone_names_no_category():
    zones = ordered_zones({"zones": [zone_entry("A", "core")]})

    assert zones[0].holiday_categories == ("public",)


def test_project_config_holds_the_backtest_defaults_of_the_forecast_protocol():
    config = load_config()

    assert config["backtest"]["refit_every_days"] == 7
    assert config["backtest"]["history_days"] is None
    assert build_model(config, "naive").params == {"lag_days": 7}


def test_project_config_opens_the_test_days_to_naive_and_the_frozen_models_only():
    backtest = load_config()["backtest"]

    assert backtest["test_models"] == ["naive", backtest["statistical_baseline"],
                                       backtest["lightgbm_model"]]


def test_project_config_keeps_the_forecasts_under_the_folder_that_git_ignores():
    paths = load_config()["paths"]

    assert Path(paths["forecasts"]).parts[0] == "data"
    assert Path(paths["results"]).parts[0] == "reports"


def test_project_config_places_every_approved_column_under_exactly_one_cut():
    config = load_config()
    columns = cut_columns(config)
    listed = [columns.price, *columns.day_ahead, *columns.delayed]
    approved = load_approved_gaps(REPO_ROOT / config["paths"]["approved_gaps"])

    assert len(listed) == len(set(listed))
    for tables in approved.values():
        for name in (HOURLY, QUARTER_HOUR):
            assert set(tables[name]) <= set(listed)


def test_project_config_builds_every_model_entry_under_its_own_name():
    config = load_config()

    for name in config["models"]:
        assert build_model(config, name).name == name


def test_project_config_holds_candidates_of_every_model_family():
    entries = load_config()["models"].values()

    families = {entry["family"] for entry in entries if "family" in entry}

    assert families == {"arima", "ets", "mstl", "lgbm", "chronos2", "timesfm25"}


PRICE_GROUPS = ["price", "calendar"]
FORECAST_GROUPS = [*PRICE_GROUPS, "load_forecast", "wind_forecast", "solar_forecast"]
LOAD_GROUPS = [*FORECAST_GROUPS, "actual_load"]
ALL_GROUPS = [*LOAD_GROUPS, "weather"]


def lgbm_entry(groups: list[str], history_days: int | None = None, objective: str = "regression",
               trees: int = 100, params: dict | None = None) -> dict:
    """One approved LightGBM entry as config/config.yaml holds it.

    Without history_days the entry has no such key and the model receives
    every day. Without params the entry holds an empty dictionary.
    """
    entry = {"family": "lgbm", "groups": groups, "objective": objective, "trees": trees,
             "params": params or {}}
    if history_days is not None:
        entry["history_days"] = history_days
    return entry


# The approved LightGBM candidates.
LGBM_CANDIDATES = {
    "lgbm_price": lgbm_entry(PRICE_GROUPS),
    "lgbm_fcst": lgbm_entry(FORECAST_GROUPS),
    "lgbm_load": lgbm_entry(LOAD_GROUPS),
    "lgbm_all": lgbm_entry(ALL_GROUPS),
    "lgbm_load_826": lgbm_entry(LOAD_GROUPS, 826),
    "lgbm_all_826": lgbm_entry(ALL_GROUPS, 826),
    "lgbm_load_364": lgbm_entry(LOAD_GROUPS, 364),
    "lgbm_all_364": lgbm_entry(ALL_GROUPS, 364),
    "lgbm_load_826_l1": lgbm_entry(LOAD_GROUPS, 826, objective="regression_l1"),
    "lgbm_load_826_slow": lgbm_entry(LOAD_GROUPS, 826, trees=400,
                                     params={"learning_rate": 0.025}),
    "lgbm_load_826_leaves15": lgbm_entry(LOAD_GROUPS, 826, params={"num_leaves": 15}),
}


def test_project_config_holds_the_approved_lightgbm_candidates():
    models = load_config()["models"]

    found = {name: entry for name, entry in models.items() if entry.get("family") == "lgbm"}

    assert found == LGBM_CANDIDATES


def test_project_config_names_a_frozen_statistical_baseline_that_is_a_model_entry():
    config = load_config()

    name = config["backtest"]["statistical_baseline"]

    assert "family" in config["models"][name]
    assert build_model(config, name).name == name


def test_project_config_names_a_frozen_lightgbm_model_that_is_a_model_entry():
    config = load_config()

    name = config["backtest"]["lightgbm_model"]

    assert name == "lgbm_load_826_slow"
    assert config["models"][name]["family"] == "lgbm"
    assert build_model(config, name).name == name


# The features section as it stood when the LightGBM model was frozen. A results row holds
# the entry of the model, with its groups, but not these settings.
FROZEN_FEATURES = {
    "groups": ALL_GROUPS,
    "price_lag_days": [1, 2, 3, 4, 5, 6, 7],
    "price_day_stats": ["mean", "min", "max", "last"],
    "forecasts": {"load_forecast": ["load_forecast"],
                  "wind_forecast": ["wind_onshore_forecast", "wind_offshore_forecast"],
                  "solar_forecast": ["solar_forecast"]},
    "forecast_lag_days": [1, 7],
    "actual_load_lag_days": [2],
    "weather_hour_before": ["shortwave_radiation"],
}


def test_project_config_holds_the_feature_settings_that_the_frozen_lightgbm_model_reads():
    assert load_config()["features"] == FROZEN_FEATURES


def test_project_config_holds_the_five_quantile_levels():
    backtest = load_config()["backtest"]

    assert backtest["quantile_levels"] == [0.05, 0.25, 0.5, 0.75, 0.95]


def test_project_config_builds_a_quantile_model_from_the_frozen_lightgbm_entry():
    config = load_config()
    name = config["backtest"]["lightgbm_model"]

    model = quantile_model(config)

    assert model.name == f"{name}_quantiles"
    assert model.name not in config["backtest"]["test_models"]
    assert model.name not in config["models"]
    assert model.settings == config["models"][name]
    assert model.levels == (0.05, 0.25, 0.5, 0.75, 0.95)
    assert model.features == build_model(config, name).features
    assert model.seed == config["seed"]


ZERO_SHOT_FAMILIES = ("chronos2", "timesfm25")

# The zero-shot candidates: the same four context lengths for both models.
ZERO_SHOT_CANDIDATES = {
    "chronos2_14": {"family": "chronos2", "context_days": 14},
    "chronos2_28": {"family": "chronos2", "context_days": 28},
    "chronos2_56": {"family": "chronos2", "context_days": 56},
    "chronos2_84": {"family": "chronos2", "context_days": 84},
    "timesfm25_14": {"family": "timesfm25", "context_days": 14},
    "timesfm25_28": {"family": "timesfm25", "context_days": 28},
    "timesfm25_56": {"family": "timesfm25", "context_days": 56},
    "timesfm25_84": {"family": "timesfm25", "context_days": 84},
}


def test_project_config_holds_the_zero_shot_candidates():
    models = load_config()["models"]

    found = {name: entry for name, entry in models.items()
             if entry.get("family") in ZERO_SHOT_FAMILIES}

    assert found == ZERO_SHOT_CANDIDATES


def test_project_config_pins_each_foundation_model_to_a_full_commit_hash():
    sections = load_config()["foundation_models"]

    assert set(sections) == set(ZERO_SHOT_FAMILIES)
    for section in sections.values():
        # A branch name such as main can move. A full commit hash cannot.
        assert re.fullmatch(r"[0-9a-f]{40}", section["revision"])


def test_every_zero_shot_candidate_fits_its_model_on_the_15_minute_table():
    config = load_config()
    max_horizon = config["foundation_models"]["timesfm25"]["max_horizon"]
    # Read from the loaded models on 2026-11-27: Chronos-2 takes a context of 8192 steps,
    # and TimesFM 2.5 takes 16384 steps for the context and the horizon together.
    for entry in config["models"].values():
        steps = entry.get("context_days", 0) * 96
        if entry.get("family") == "chronos2":
            assert steps <= 8192
        if entry.get("family") == "timesfm25":
            assert steps + max_horizon <= 16384


def test_project_config_forbids_timesfm_to_cut_a_forecast_at_zero():
    assert load_config()["foundation_models"]["timesfm25"]["infer_is_positive"] is False


@pytest.mark.parametrize("key, family, name", [("chronos2_model", "chronos2", "chronos2_84"),
                                               ("timesfm25_model", "timesfm25", "timesfm25_84")])
def test_project_config_names_the_frozen_setting_of_each_zero_shot_model(key, family, name):
    config = load_config()

    assert config["backtest"][key] == name
    assert config["models"][name]["family"] == family
    assert build_model(config, name).name == name


def test_project_config_opens_the_test_days_to_no_zero_shot_setting():
    test_models = load_config()["backtest"]["test_models"]

    assert not set(test_models) & set(ZERO_SHOT_CANDIDATES)
