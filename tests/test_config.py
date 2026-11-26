"""Tests for the config loader. They use no network and no data files."""

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
    assert config["backtest"]["test_models"] == ["naive", config["backtest"]["statistical_baseline"]]
    assert build_model(config, "naive").params == {"lag_days": 7}


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


def test_project_config_holds_candidates_of_the_statistical_families_and_lightgbm():
    entries = load_config()["models"].values()

    families = {entry["family"] for entry in entries if "family" in entry}

    assert families == {"arima", "ets", "mstl", "lgbm"}


PRICE_GROUPS = ["price", "calendar"]
FORECAST_GROUPS = [*PRICE_GROUPS, "load_forecast", "wind_forecast", "solar_forecast"]
LOAD_GROUPS = [*FORECAST_GROUPS, "actual_load"]
ALL_GROUPS = [*LOAD_GROUPS, "weather"]
# The approved LightGBM candidates: the feature groups and the days of history of each.
# None stands for an entry without history_days, which receives every day.
LGBM_CANDIDATES = {
    "lgbm_price": (PRICE_GROUPS, None),
    "lgbm_fcst": (FORECAST_GROUPS, None),
    "lgbm_load": (LOAD_GROUPS, None),
    "lgbm_all": (ALL_GROUPS, None),
    "lgbm_load_826": (LOAD_GROUPS, 826),
    "lgbm_all_826": (ALL_GROUPS, 826),
    "lgbm_load_364": (LOAD_GROUPS, 364),
    "lgbm_all_364": (ALL_GROUPS, 364),
}


def lgbm_entry(groups: list[str], history_days: int | None) -> dict:
    """One approved LightGBM entry as config/config.yaml holds it."""
    entry = {"family": "lgbm", "groups": groups, "objective": "regression", "trees": 100,
             "params": {}}
    if history_days is not None:
        entry["history_days"] = history_days
    return entry


def test_project_config_holds_the_approved_lightgbm_candidates():
    models = load_config()["models"]

    found = {name: entry for name, entry in models.items() if entry.get("family") == "lgbm"}

    assert found == {name: lgbm_entry(groups, history_days)
                     for name, (groups, history_days) in LGBM_CANDIDATES.items()}


def test_project_config_names_a_frozen_statistical_baseline_that_is_a_model_entry():
    config = load_config()

    name = config["backtest"]["statistical_baseline"]

    assert "family" in config["models"][name]
    assert build_model(config, name).name == name
