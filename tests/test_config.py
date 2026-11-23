"""Tests for the config loader. They use no network and no data files."""

from datetime import date

import pandas as pd
import pytest
from entsoe.entsoe import QUARTER_MTU_SDAC_GOLIVE
from entsoe.mappings import lookup_area

from epf.config import load_config, ordered_zones
from epf.data.market_time import split_starts


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
