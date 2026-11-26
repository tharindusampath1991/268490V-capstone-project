"""Tests for the command that builds the features of every zone and experiment.

They use small synthetic tables in a temporary folder, no network and no data files.
"""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epf.config import ordered_zones
from epf.data.market_time import hourly_index, quarter_hour_index
from epf.data.validate import HOURLY, QUARTER_HOUR, WEATHER_TABLE, table_path
from epf.features.build import empty_counts, features_path, run, zone_features

MARKET_TZ = "Europe/Berlin"
POINT = {"place": "X", "latitude": 0.0, "longitude": 0.0}


def market_time(day: str | date) -> pd.Timestamp:
    """00:00 in market time on a day."""
    return pd.Timestamp(day, tz=MARKET_TZ)


def project_config(tmp_path) -> dict:
    """A config with 12 delivery days. Zone A has every column and weather, zone B has less."""
    return {
        "market": {"timezone": MARKET_TZ},
        "paths": {"processed": str(tmp_path / "processed"),
                  "features": str(tmp_path / "features")},
        "data": {"start": "2026-09-28", "end": "2026-10-09"},
        "splits": {"validation_days": 2, "test_days": 2,
                   "validation_start": "2026-10-06", "test_start": "2026-10-08"},
        "backtest": {"price_column": "price",
                     "day_ahead_columns": ["load_forecast", "wind_onshore_forecast",
                                           "solar_forecast"],
                     "delayed_columns": ["actual_load"], "weather_run_column": "run"},
        "open_meteo": {"variables": ["temperature_2m"], "run_hour_utc": 0},
        "features": {"groups": ["price", "calendar", "load_forecast", "wind_forecast",
                                "solar_forecast", "actual_load", "weather"],
                     "price_lag_days": [1, 7], "price_day_stats": ["mean"],
                     "forecasts": {"load_forecast": ["load_forecast"],
                                   "wind_forecast": ["wind_onshore_forecast"],
                                   "solar_forecast": ["solar_forecast"]},
                     "forecast_lag_days": [1], "actual_load_lag_days": [2],
                     "weather_hour_before": []},
        "zones": [{"key": "B", "holiday_country": "SE", "holiday_categories": ["public"],
                   "group": "core"},
                  {"key": "A", "holiday_country": "DE", "holiday_categories": ["public"],
                   "group": "core", "weather_point": POINT}],
    }


def save_tables(config: dict, zone_keys=("A", "B")) -> None:
    """Write the hourly and the 15-minute table of each zone, and the weather table of zone A.

    Zone B has no solar forecast. Every value of a table is its row number.
    """
    start = market_time(config["data"]["start"])
    end = market_time(date.fromisoformat(config["data"]["end"]) + timedelta(days=1))
    processed = Path(config["paths"]["processed"])
    for name, make_index in ((HOURLY, hourly_index), (QUARTER_HOUR, quarter_hour_index)):
        index = make_index(start, end)
        numbers = np.arange(len(index), dtype=float)
        table = pd.DataFrame({"price": numbers, "load_forecast": numbers,
                              "wind_onshore_forecast": numbers, "solar_forecast": numbers,
                              "actual_load": numbers}, index=index)
        for zone_key in zone_keys:
            path = table_path(processed, name, zone_key)
            path.parent.mkdir(parents=True, exist_ok=True)
            columns = table.columns if zone_key == "A" else table.columns.drop("solar_forecast")
            table[columns].to_parquet(path)
    index = hourly_index(start, end)
    delivery_day = index.tz_convert(MARKET_TZ).normalize().tz_localize(None)
    weather = pd.DataFrame({"temperature_2m": np.arange(len(index), dtype=float),
                            "run": (delivery_day - timedelta(days=1)).tz_localize("UTC")},
                           index=index)
    path = table_path(processed, WEATHER_TABLE, "A")
    path.parent.mkdir(parents=True, exist_ok=True)
    weather.to_parquet(path)


def zone(config: dict, key: str):
    """The zone of the config with a key."""
    return [zone for zone in ordered_zones(config) if zone.key == key][0]


def test_zone_features_cover_every_market_time_unit_of_the_table(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    hourly = zone_features(config, zone(config, "A"), "H")
    quarter_hourly = zone_features(config, zone(config, "A"), "Q")

    start, end = market_time("2026-09-28"), market_time("2026-10-10")
    assert hourly.index.equals(hourly_index(start, end))
    assert quarter_hourly.index.equals(quarter_hour_index(start, end))
    assert len(hourly) == 12 * 24


def test_zone_features_mark_the_holidays_of_the_country_of_the_zone(tmp_path):
    # 3 October is a public holiday in Germany and not in Sweden.
    config = project_config(tmp_path)
    save_tables(config)

    german = zone_features(config, zone(config, "A"), "H")
    swedish = zone_features(config, zone(config, "B"), "H")

    days = german.index.tz_convert(MARKET_TZ).date
    assert set(days[german["holiday"] == 1]) == {date(2026, 10, 3)}
    assert swedish["holiday"].sum() == 0


def test_zone_features_read_the_weather_table_of_a_zone_with_a_weather_point(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    with_point = zone_features(config, zone(config, "A"), "H")
    without_point = zone_features(config, zone(config, "B"), "H")

    assert with_point["temperature_2m"].tolist() == [float(row) for row in range(12 * 24)]
    assert without_point["temperature_2m"].isna().all()
    assert list(with_point.columns) == list(without_point.columns)


def test_empty_counts_give_the_empty_cells_per_feature_and_zone(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)
    frames = {key: zone_features(config, zone(config, key), "H") for key in ("A", "B")}

    counts = empty_counts(frames)

    assert list(counts.columns) == ["A", "B"]
    assert counts.loc["price_lag_1"].tolist() == [24, 24]        # the first day of the table
    assert counts.loc["price_lag_7"].tolist() == [7 * 24, 7 * 24]
    assert counts.loc["actual_load_lag_2"].tolist() == [48, 48]
    assert counts.loc["solar_forecast"].tolist() == [0, 12 * 24]  # zone B has no solar forecast
    assert counts.loc["temperature_2m"].tolist() == [0, 12 * 24]
    assert counts.loc["hour"].tolist() == [0, 0]


def test_run_saves_one_frame_per_zone_and_experiment_and_prints_the_counts(tmp_path, capsys):
    config = project_config(tmp_path)
    save_tables(config)

    run(config)

    folder = Path(config["paths"]["features"])
    saved = sorted(str(path.relative_to(folder).as_posix()) for path in folder.rglob("*.parquet"))
    assert saved == ["H/A.parquet", "H/B.parquet", "Q/A.parquet", "Q/B.parquet"]
    frame = pd.read_parquet(features_path(folder, "Q", "A"))
    pd.testing.assert_frame_equal(frame, zone_features(config, zone(config, "A"), "Q"),
                                  check_freq=False)
    printed = capsys.readouterr().out
    assert "experiment H" in printed and "experiment Q" in printed
    assert "288" in printed and "1152" in printed
    assert "solar_forecast" in printed


def test_run_ends_with_an_error_and_saves_nothing_when_a_table_is_missing(tmp_path):
    config = project_config(tmp_path)
    save_tables(config, zone_keys=("A",))

    with pytest.raises(SystemExit, match="B"):
        run(config)

    assert not Path(config["paths"]["features"]).exists()


def test_run_ends_with_an_error_when_a_table_column_stands_under_no_cut(tmp_path):
    config = project_config(tmp_path)
    config["backtest"]["day_ahead_columns"] = ["load_forecast", "wind_onshore_forecast"]
    config["features"]["forecasts"].pop("solar_forecast")
    config["features"]["groups"].remove("solar_forecast")
    save_tables(config)

    with pytest.raises(SystemExit, match="solar_forecast"):
        run(config)
