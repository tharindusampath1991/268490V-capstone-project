"""Tests for the quantile loop, its scores and its command.

They use small synthetic tables, a temporary folder, no network and no data files.
The price is in EUR/MWh with a UTC index. Delivery days are in market time.
"""

import json
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epf.config import REPO_ROOT, load_config, ordered_zones
from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.data.validate import HOURLY, QUARTER_HOUR, WEATHER_TABLE, table_path
from epf.evaluation import backtest, quantiles
from epf.evaluation.cutoff import Columns, DayInputs, cut_columns, weather_rule
from epf.evaluation.quantiles import (
    intervals,
    quantile_model,
    quantile_zone,
    run,
    run_quantile_days,
    score,
    sort_quantiles,
)
from epf.features.builder import feature_settings
from epf.models import lgbm

MARKET_TZ = "Europe/Berlin"
COLUMNS = Columns(price="price",
                  day_ahead=("load_forecast", "wind_onshore_forecast", "solar_forecast"),
                  delayed=("actual_load",))
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]


def market_time(day: str | date) -> pd.Timestamp:
    """00:00 in market time on a day."""
    return pd.Timestamp(day, tz=MARKET_TZ)


def day_after(day: str, days: int = 1) -> date:
    """The calendar day some days after a day. A negative number goes back."""
    return date.fromisoformat(day) + timedelta(days=days)


def days_from(first_day: str, count: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """The delivery days from first_day on, as (day start, next day start)."""
    return delivery_days(market_time(first_day), market_time(day_after(first_day, count)))


def make_table(first_day: str, end_day: str, make_index=hourly_index,
               seed: int = 0) -> pd.DataFrame:
    """A table from first_day up to the start of end_day.

    Every input column is random between 0 and 100. The price is twice the load forecast
    plus normal noise with a standard deviation of 10.
    """
    index = make_index(market_time(first_day), market_time(end_day))
    random = np.random.default_rng(seed)
    table = pd.DataFrame({column: random.uniform(0, 100, len(index))
                          for column in (*COLUMNS.day_ahead, *COLUMNS.delayed)}, index=index)
    table.insert(0, "price", 2 * table["load_forecast"] + random.normal(0, 10, len(index)))
    return table


def make_weather(first_day: str, end_day: str) -> pd.DataFrame:
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


class Recorder:
    """A quantile model that keeps every input it is given and forecasts the same three values."""

    name = "recorder"
    levels = (0.25, 0.5, 0.75)
    values = (1.0, 2.0, 3.0)
    params = {"quantile_levels": [0.25, 0.5, 0.75]}
    seed = 42

    def __init__(self):
        self.fits: list[DayInputs] = []
        self.predicts: list[DayInputs] = []

    def fit(self, inputs: DayInputs) -> None:
        self.fits.append(inputs)

    def predict_quantiles(self, inputs: DayInputs) -> pd.DataFrame:
        self.predicts.append(inputs)
        return pd.DataFrame(dict(zip(self.levels, self.values)), index=inputs.target_index)


class Crossing(Recorder):
    """A quantile model whose lowest level stands above its median."""

    values = (2.5, 2.0, 3.0)


class OneEmpty(Recorder):
    """A quantile model with an empty value at its highest level."""

    values = (1.0, 2.0, np.nan)


class OneInfinite(Recorder):
    """A quantile model with an infinite value at its highest level."""

    values = (1.0, 2.0, np.inf)


class WrongIndex(Recorder):
    """A quantile model that answers for the hours one hour later."""

    def predict_quantiles(self, inputs: DayInputs) -> pd.DataFrame:
        return super().predict_quantiles(inputs).shift(freq="1h")


class WrongLevels(Recorder):
    """A quantile model that answers with the columns of other levels."""

    def predict_quantiles(self, inputs: DayInputs) -> pd.DataFrame:
        return super().predict_quantiles(inputs).rename(columns={0.25: 0.1})


class PointRecorder:
    """A point model of the backtest that keeps every input it is given and forecasts zero."""

    def __init__(self, name: str):
        self.name = name
        self.params = {}
        self.fits: list[DayInputs] = []
        self.predicts: list[DayInputs] = []

    def fit(self, inputs: DayInputs) -> None:
        self.fits.append(inputs)

    def predict(self, inputs: DayInputs) -> pd.Series:
        self.predicts.append(inputs)
        return pd.Series(0.0, index=inputs.target_index)


# The day loop.

# The days hold 2026-10-25 with 25 hours, as D, as D-1 and as D-2.
@pytest.mark.parametrize("make_index", [hourly_index, quarter_hour_index])
def test_a_model_never_receives_a_value_after_its_cut(make_index):
    table = make_table("2026-10-10", "2026-11-05", make_index)
    model = Recorder()

    run_quantile_days(table, days_from("2026-10-20", 14), make_index, model, COLUMNS,
                      refit_every_days=7)

    assert len(model.predicts) == 14
    for inputs in model.fits + model.predicts:
        day = inputs.delivery_day
        assert inputs.prices.index.max() < market_time(day)
        assert inputs.day_ahead.index.max() < market_time(day + timedelta(days=1))
        assert inputs.delayed.index.max() < market_time(day - timedelta(days=1))


def test_fit_is_called_on_the_first_day_and_then_every_refit_every_days():
    table = make_table("2026-06-01", "2026-07-05")
    model = Recorder()

    run_quantile_days(table, days_from("2026-06-15", 15), hourly_index, model, COLUMNS,
                      refit_every_days=7)

    assert [inputs.delivery_day for inputs in model.fits] == [
        date(2026, 6, 15), date(2026, 6, 22), date(2026, 6, 29)]


def test_history_days_limits_what_the_model_receives():
    table = make_table("2026-06-01", "2026-07-05")
    model = Recorder()

    run_quantile_days(table, days_from("2026-07-01", 1), hourly_index, model, COLUMNS,
                      refit_every_days=7, history_days=5)

    assert model.predicts[0].prices.index.min() == market_time("2026-06-26")


def test_the_loop_returns_one_row_per_market_time_unit_and_one_column_per_level():
    table = make_table("2026-10-10", "2026-11-05")

    frame, seconds = run_quantile_days(table, days_from("2026-10-24", 3), hourly_index,
                                       Recorder(), COLUMNS, refit_every_days=7)

    expected = hourly_index(market_time("2026-10-24"), market_time("2026-10-27"))
    assert len(expected) == 24 + 25 + 24
    assert frame.index.equals(expected)
    assert list(frame.columns) == [0.25, 0.5, 0.75]
    assert frame.iloc[0].tolist() == [1.0, 2.0, 3.0]
    assert seconds >= 0


def test_the_loop_does_not_sort_the_values_of_a_market_time_unit():
    table = make_table("2026-06-20", "2026-07-05")

    frame, _ = run_quantile_days(table, days_from("2026-07-01", 1), hourly_index, Crossing(),
                                 COLUMNS, refit_every_days=7)

    assert frame.iloc[0].tolist() == [2.5, 2.0, 3.0]


@pytest.mark.parametrize("model, message", [(WrongIndex(), "index"), (WrongLevels(), "levels")])
def test_quantile_forecasts_on_other_timestamps_or_levels_are_refused(model, message):
    table = make_table("2026-06-20", "2026-07-05")

    with pytest.raises(ValueError, match=message):
        run_quantile_days(table, days_from("2026-07-01", 1), hourly_index, model, COLUMNS,
                          refit_every_days=7)


def test_a_table_column_under_no_cut_stops_the_loop():
    table = make_table("2026-06-20", "2026-07-05").assign(temperature_2m=1.0)

    with pytest.raises(ValueError, match="temperature_2m"):
        run_quantile_days(table, days_from("2026-07-01", 1), hourly_index, Recorder(), COLUMNS,
                          refit_every_days=7)


# Sorting. Hand values.

def hours(count: int) -> pd.DatetimeIndex:
    """The first hours of 2026-07-01 in UTC."""
    return pd.date_range("2026-07-01", periods=count, freq="1h", tz="UTC")


def test_sorting_puts_the_values_of_each_row_in_ascending_order_and_marks_the_changed_rows():
    frame = pd.DataFrame({0.25: [1.0, 5.0, 2.0, 2.0], 0.5: [2.0, 4.0, 2.0, 2.0],
                          0.75: [3.0, 6.0, 1.0, 3.0]}, index=hours(4))

    ordered, changed = sort_quantiles(frame)

    assert ordered.to_numpy().tolist() == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [1.0, 2.0, 2.0],
                                           [2.0, 2.0, 3.0]]
    assert list(ordered.columns) == [0.25, 0.5, 0.75]
    assert ordered.index.equals(frame.index)
    # The first row ascends and the last one holds two equal values: neither is changed.
    assert changed.tolist() == [False, True, True, False]
    assert changed.index.equals(frame.index)
    assert changed.mean() == 0.5


def test_sorting_does_not_change_the_frame_it_is_given():
    frame = pd.DataFrame({0.25: [5.0], 0.75: [4.0]}, index=hours(1))

    sort_quantiles(frame)

    assert frame.to_numpy().tolist() == [[5.0, 4.0]]


# The intervals and the scores. Hand values.

def test_the_intervals_pair_each_level_with_its_mirror_the_narrowest_first():
    assert intervals(LEVELS) == [(0.25, 0.75), (0.05, 0.95)]
    assert intervals([0.25, 0.75]) == [(0.25, 0.75)]
    assert intervals([0.025, 0.5, 0.975]) == [(0.025, 0.975)]


def test_the_scores_are_the_pinball_losses_the_coverage_and_the_width_of_hand_values():
    actual = pd.Series(10.0, index=hours(4))
    # Row 1 lies in both intervals, row 2 in none, row 3 in the 90% interval only, and
    # row 4 stands on the bounds of both, which counts as inside.
    frame = pd.DataFrame([[0.0, 5.0, 10.0, 15.0, 20.0],
                          [11.0, 12.0, 13.0, 14.0, 30.0],
                          [2.0, 11.0, 12.0, 13.0, 14.0],
                          [0.0, 10.0, 10.0, 10.0, 10.0]], index=hours(4), columns=LEVELS)

    scores = score(actual, frame)

    assert list(scores) == ["pinball_0.05", "pinball_0.25", "pinball_0.5", "pinball_0.75",
                            "pinball_0.95", "mean_pinball", "coverage_50", "width_50",
                            "coverage_90", "width_90"]
    # Level 0.05: the errors 10, -1, 8 and 10 cost 0.5, 0.95, 0.4 and 0.5.
    assert scores["pinball_0.05"] == pytest.approx(0.5875)
    assert scores["pinball_0.25"] == pytest.approx(0.875)
    assert scores["pinball_0.5"] == pytest.approx(0.625)
    assert scores["pinball_0.75"] == pytest.approx(0.75)
    assert scores["pinball_0.95"] == pytest.approx(0.425)
    assert scores["mean_pinball"] == pytest.approx(0.6525)
    assert scores["coverage_50"] == 0.5
    assert scores["coverage_90"] == 0.75
    assert scores["width_50"] == pytest.approx(3.5)
    assert scores["width_90"] == pytest.approx(15.25)


def test_the_scores_of_two_levels_hold_one_interval():
    actual = pd.Series([10.0, 20.0], index=hours(2))
    frame = pd.DataFrame({0.1: [8.0, 21.0], 0.9: [12.0, 23.0]}, index=hours(2))

    scores = score(actual, frame)

    assert list(scores) == ["pinball_0.1", "pinball_0.9", "mean_pinball", "coverage_80",
                            "width_80"]
    assert scores["coverage_80"] == 0.5
    assert scores["width_80"] == pytest.approx(3.0)


# The command. A small project in a temporary folder: zone A is core and has weather,
# zone B is extra and has none. One model object runs both zones and both experiments.

SMALL = {"family": "lgbm", "groups": ["price", "calendar", "load_forecast", "weather"],
         "history_days": 12, "objective": "regression", "trees": 10,
         "params": {"learning_rate": 0.3, "min_data_in_leaf": 5}}
NAME = "lgbm_small_quantiles"
ROW_COLUMNS = [
    "run_started_utc", "model", "model_params", "split", "hardware", "seed", "refit_every_days",
    "history_days", "data_start", "data_end", "validation_start", "test_start", "experiment",
    "zone", "group", "first_day", "last_day", "days", "mtus", "pinball_0.05", "pinball_0.25",
    "pinball_0.5", "pinball_0.75", "pinball_0.95", "mean_pinball", "coverage_50", "width_50",
    "coverage_90", "width_90", "crossing_share", "wall_seconds", "peak_memory_mb",
]
FORECAST_COLUMNS = ["quantile_0.05", "quantile_0.25", "quantile_0.5", "quantile_0.75",
                    "quantile_0.95", "actual"]


def project_config(tmp_path) -> dict:
    """A config with 5 validation days, the frozen entry lgbm_small and the five levels."""
    return {
        "seed": 42,
        "market": {"timezone": MARKET_TZ},
        "paths": {"processed": str(tmp_path / "processed"),
                  "results": str(tmp_path / "results"),
                  "forecasts": str(tmp_path / "forecasts")},
        "data": {"start": "2026-10-05", "end": "2026-11-03"},
        "splits": {"validation_days": 5, "test_days": 10,
                   "validation_start": "2026-10-20", "test_start": "2026-10-25"},
        "backtest": {"refit_every_days": 7, "history_days": None,
                     "lightgbm_model": "lgbm_small", "quantile_levels": list(LEVELS),
                     "test_models": ["naive", "lgbm_small"],
                     "price_column": COLUMNS.price, "day_ahead_columns": list(COLUMNS.day_ahead),
                     "delayed_columns": list(COLUMNS.delayed), "weather_run_column": "run"},
        "open_meteo": {"variables": ["temperature_2m", "shortwave_radiation"],
                       "run_hour_utc": 0},
        "features": {"groups": ["price", "calendar", "load_forecast", "wind_forecast",
                                "solar_forecast", "actual_load", "weather"],
                     "price_lag_days": [1, 2, 7],
                     "price_day_stats": ["mean", "min", "max", "last"],
                     "forecasts": {"load_forecast": ["load_forecast"],
                                   "wind_forecast": ["wind_onshore_forecast"],
                                   "solar_forecast": ["solar_forecast"]},
                     "forecast_lag_days": [1, 7], "actual_load_lag_days": [2],
                     "weather_hour_before": ["shortwave_radiation"]},
        "models": {"naive": {"lag_days": 7}, "lgbm_small": SMALL},
        "zones": [{"key": "B", "holiday_country": "PL", "group": "extra"},
                  {"key": "A", "holiday_country": "DE", "group": "core",
                   "weather_point": {"place": "X", "latitude": 10.0, "longitude": 20.0}}],
    }


def save_tables(config: dict, zone_keys: str = "AB") -> None:
    """Write the hourly and the 15-minute table of the zones and the weather table of zone A."""
    first, end = config["data"]["start"], str(day_after(config["data"]["end"]))
    folder = Path(config["paths"]["processed"])
    tables = {(HOURLY, zone_key): make_table(first, end, hourly_index) for zone_key in zone_keys}
    tables.update({(QUARTER_HOUR, zone_key): make_table(first, end, quarter_hour_index)
                   for zone_key in zone_keys})
    tables[(WEATHER_TABLE, "A")] = make_weather(first, end)
    for (name, zone_key), table in tables.items():
        path = table_path(folder, name, zone_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(path)


def saved(config: dict, name: str) -> pd.DataFrame:
    """Read one results file of the temporary project."""
    return pd.read_csv(Path(config["paths"]["results"]) / name)


def forecasts_file(config: dict, experiment: str, zone_key: str, model: str = NAME) -> Path:
    """The forecasts file of one zone and experiment on the validation days."""
    return (Path(config["paths"]["forecasts"]) / model / experiment / "validation"
            / f"{zone_key}.parquet")


def files_under(folder: Path) -> dict[Path, bytes]:
    """Every file under a folder with its content."""
    return {path: path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def test_the_quantile_model_is_the_frozen_entry_with_the_levels_of_the_config(tmp_path):
    config = project_config(tmp_path)

    model = quantile_model(config)

    assert isinstance(model, lgbm.LgbmQuantileModel)
    assert model.name == NAME
    assert model.settings == SMALL
    assert model.levels == tuple(LEVELS)
    assert model.features == lgbm.model_features(feature_settings(config), SMALL["groups"],
                                                 COLUMNS.day_ahead)
    assert model.columns == cut_columns(config)
    assert model.rule == weather_rule(config)
    assert model.seed == 42


def test_a_frozen_name_without_a_model_entry_is_refused(tmp_path):
    config = project_config(tmp_path)
    config["backtest"]["lightgbm_model"] = "lgbm_gone"

    with pytest.raises(ValueError, match="lgbm_gone"):
        quantile_model(config)


def test_a_config_without_the_quantile_levels_is_refused(tmp_path):
    config = project_config(tmp_path)
    del config["backtest"]["quantile_levels"]

    with pytest.raises(ValueError, match="backtest.quantile_levels"):
        quantile_model(config)


def test_run_ends_with_one_line_for_a_config_without_the_quantile_levels(tmp_path):
    config = project_config(tmp_path)
    del config["backtest"]["quantile_levels"]
    save_tables(config)

    with pytest.raises(SystemExit) as refused:
        run(config, "validation")

    assert refused.value.code == ("The config has no backtest.quantile_levels, the levels of "
                                  "the quantile forecasts.")
    assert not Path(config["paths"]["results"]).exists()
    assert not Path(config["paths"]["forecasts"]).exists()


def test_a_config_without_the_frozen_name_is_refused(tmp_path):
    config = project_config(tmp_path)
    del config["backtest"]["lightgbm_model"]

    with pytest.raises(ValueError, match="backtest.lightgbm_model"):
        quantile_model(config)


def test_run_ends_with_one_line_for_a_config_without_the_frozen_name(tmp_path):
    config = project_config(tmp_path)
    del config["backtest"]["lightgbm_model"]
    save_tables(config)

    with pytest.raises(SystemExit) as refused:
        run(config, "validation")

    assert refused.value.code == ("The config has no backtest.lightgbm_model, the name of the "
                                  "frozen LightGBM entry.")
    assert not Path(config["paths"]["results"]).exists()
    assert not Path(config["paths"]["forecasts"]).exists()


def test_run_writes_one_row_per_zone_and_experiment_with_the_scores(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "validation")

    core, extra = saved(config, "quantile_core.csv"), saved(config, "quantile_extra.csv")
    assert core["zone"].tolist() == ["A", "A"]
    assert extra["zone"].tolist() == ["B", "B"]
    for rows in (core, extra):
        assert list(rows.columns) == ROW_COLUMNS
        assert rows["model"].tolist() == [NAME] * 2
        assert [json.loads(text) for text in rows["model_params"]] == [
            {**SMALL, "objective": "quantile", "quantile_levels": LEVELS}] * 2
        assert rows["seed"].tolist() == [42, 42]
        assert rows["split"].tolist() == ["validation"] * 2
        assert rows["refit_every_days"].tolist() == [7, 7]
        assert rows["history_days"].tolist() == [12, 12]
        assert rows["experiment"].tolist() == ["H", "Q"]
        assert rows["first_day"].tolist() == ["2026-10-20"] * 2
        assert rows["last_day"].tolist() == ["2026-10-24"] * 2
        assert rows["days"].tolist() == [5, 5]
        assert rows["mtus"].tolist() == [120, 480]
        assert rows["hardware"].str.contains("GB RAM").all()
        assert (rows["wall_seconds"] >= 0).all()
        pinball = rows[[f"pinball_{level:g}" for level in LEVELS]]
        assert (pinball > 0).all().all()
        assert rows["mean_pinball"].tolist() == pytest.approx(pinball.mean(axis=1).tolist())
        assert rows[["coverage_50", "coverage_90", "crossing_share"]].ge(0).all().all()
        assert rows[["coverage_50", "coverage_90", "crossing_share"]].le(1).all().all()
        assert (rows["coverage_90"] >= rows["coverage_50"]).all()
        assert (rows["width_90"] > rows["width_50"]).all()
        assert (rows["width_50"] > 0).all()


def test_run_saves_the_sorted_quantiles_with_the_actual_price(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "validation")

    frame = pd.read_parquet(forecasts_file(config, "H", "A"))
    table = pd.read_parquet(table_path(Path(config["paths"]["processed"]), HOURLY, "A"))
    assert list(frame.columns) == FORECAST_COLUMNS
    assert frame.index.equals(hourly_index(market_time("2026-10-20"), market_time("2026-10-25")))
    assert frame["actual"].tolist() == table.loc[frame.index, "price"].tolist()
    assert (np.diff(frame[FORECAST_COLUMNS[:-1]].to_numpy(), axis=1) >= 0).all()
    assert len(pd.read_parquet(forecasts_file(config, "Q", "B"))) == 480


def test_the_saved_row_holds_the_scores_of_the_saved_forecasts(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "validation", ["H"])

    row = saved(config, "quantile_core.csv").iloc[0]
    frame = pd.read_parquet(forecasts_file(config, "H", "A"))
    actual, low, high = frame["actual"], frame["quantile_0.05"], frame["quantile_0.95"]
    errors = actual - frame["quantile_0.25"]
    assert row["coverage_90"] == pytest.approx(((actual >= low) & (actual <= high)).mean())
    assert row["width_50"] == pytest.approx(
        (frame["quantile_0.75"] - frame["quantile_0.25"]).mean())
    assert row["pinball_0.25"] == pytest.approx(
        np.maximum(0.25 * errors, -0.75 * errors).mean())


def test_run_refuses_the_test_days_with_one_line_and_writes_nothing(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    with pytest.raises(SystemExit) as refused:
        run(config, "test")

    assert refused.value.code == (
        "Model 'lgbm_small_quantiles' may not be scored on the test days. "
        "backtest.test_models lists ['naive', 'lgbm_small'].")
    assert not Path(config["paths"]["results"]).exists()
    assert not Path(config["paths"]["forecasts"]).exists()


def test_a_second_run_adds_rows_with_the_same_scores_and_writes_the_forecasts_again(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "validation")
    first_forecasts = files_under(Path(config["paths"]["forecasts"]))
    run(config, "validation")

    rows = saved(config, "quantile_core.csv")
    scores = ROW_COLUMNS[ROW_COLUMNS.index("pinball_0.05"):ROW_COLUMNS.index("wall_seconds")]
    assert rows["experiment"].tolist() == ["H", "Q", "H", "Q"]
    assert rows.loc[[0, 1], scores].to_numpy().tolist() \
        == rows.loc[[2, 3], scores].to_numpy().tolist()
    assert files_under(Path(config["paths"]["forecasts"])) == first_forecasts
    assert len(first_forecasts) == 4


def test_run_leaves_the_point_results_and_the_point_forecasts_byte_for_byte_unchanged(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)
    backtest.run(config, "lgbm_small", "validation")
    before = files_under(tmp_path)

    run(config, "validation")

    after = files_under(tmp_path)
    results_folder, forecasts_folder = (Path(config["paths"][key])
                                        for key in ("results", "forecasts"))
    assert {path.name for path in before if path.parent == results_folder} == {
        "backtest_core.csv", "backtest_extra.csv", "daily_core.csv", "daily_extra.csv"}
    assert {path: after[path] for path in before} == before
    new = set(after) - set(before)
    assert {path for path in new if path.parent == results_folder} == {
        results_folder / "quantile_core.csv", results_folder / "quantile_extra.csv"}
    assert all(path.is_relative_to(forecasts_folder / NAME)
               for path in new if path.parent != results_folder)
    assert len(new) == 6


def test_run_with_one_experiment_scores_that_table_only(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "validation", ["Q"])

    assert saved(config, "quantile_core.csv")["experiment"].tolist() == ["Q"]
    assert not forecasts_file(config, "H", "A").exists()


def test_run_refuses_an_unknown_experiment(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    with pytest.raises(SystemExit, match="D"):
        run(config, "validation", ["D"])

    assert not Path(config["paths"]["results"]).exists()


@pytest.mark.parametrize("change, message", [
    ({"quantile_levels": [0.1, 0.5, 0.95]}, "Quantile levels.*mirror"),
    ({"lightgbm_model": "naive"}, "LightGBM entry"),
])
def test_run_ends_with_one_line_for_levels_or_an_entry_that_the_model_refuses(
        change, message, tmp_path):
    config = project_config(tmp_path)
    config["backtest"].update(change)
    save_tables(config)

    with pytest.raises(SystemExit, match=message):
        run(config, "validation")

    assert not Path(config["paths"]["results"]).exists()


def test_run_ends_with_one_line_for_a_parameter_value_that_lightgbm_refuses(tmp_path):
    config = project_config(tmp_path)
    config["models"]["lgbm_small"] = {**SMALL, "params": {"num_leaves": 1}}
    save_tables(config)

    with pytest.raises(SystemExit, match=f"A H: .*'{NAME}'.*num_leaves"):
        run(config, "validation")

    assert not Path(config["paths"]["results"]).exists()


@pytest.mark.parametrize("model, check", [(OneEmpty(), "no empty quantile"),
                                          (OneInfinite(), "every quantile is finite")])
def test_run_with_a_failed_check_ends_with_an_error_and_writes_nothing(
        model, check, tmp_path, monkeypatch, capsys):
    config = project_config(tmp_path)
    save_tables(config)
    monkeypatch.setattr(quantiles, "quantile_model", lambda config: model)

    with pytest.raises(SystemExit, match=f"A H: failed checks: .*{check}"):
        run(config, "validation")

    assert f"FAIL: {check}" in capsys.readouterr().out
    assert not Path(config["paths"]["results"]).exists()
    assert not Path(config["paths"]["forecasts"]).exists()


def test_core_results_are_written_before_an_extra_zone_fails(tmp_path):
    config = project_config(tmp_path)
    save_tables(config, zone_keys="A")

    with pytest.raises(SystemExit, match="B"):
        run(config, "validation")

    assert len(saved(config, "quantile_core.csv")) == 2
    assert not (Path(config["paths"]["results"]) / "quantile_extra.csv").exists()


def test_run_prints_the_numbers_and_the_checks_of_every_zone_and_experiment(tmp_path, capsys):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "validation", ["H"])

    printed = capsys.readouterr().out
    assert "core zones, validation days, model lgbm_small_quantiles" in printed
    for check in ("5 scored days", "120 market time units", "no empty quantile",
                  "every quantile is finite", "every row ascends after sorting"):
        assert printed.count(f"pass: {check}") == 2
    assert "FAIL" not in printed
    assert "Wrote 1 rows to" in printed


def test_a_crossing_row_is_sorted_before_it_is_scored_and_counted_in_the_share(
        tmp_path, monkeypatch):
    config = project_config(tmp_path)
    save_tables(config)
    monkeypatch.setattr(quantiles, "quantile_model", lambda config: Crossing())

    run(config, "validation", ["H"])

    row = saved(config, "quantile_core.csv").iloc[0]
    frame = pd.read_parquet(Path(config["paths"]["forecasts"]) / "recorder" / "H" / "validation"
                            / "A.parquet")
    assert row["crossing_share"] == 1.0
    assert frame.iloc[0, :3].tolist() == [2.0, 2.5, 3.0]
    assert row["width_50"] == pytest.approx(1.0)


# What the loop hands to the model is what the backtest hands to a point model.

def assert_same_inputs(first: DayInputs, second: DayInputs) -> None:
    """Two inputs of a delivery day must hold the same values in every part."""
    assert first.delivery_day == second.delivery_day
    assert first.market_tz == second.market_tz
    assert first.holidays == second.holidays
    assert first.target_index.equals(second.target_index)
    pd.testing.assert_series_equal(first.prices, second.prices, check_exact=True)
    pd.testing.assert_frame_equal(first.day_ahead, second.day_ahead, check_exact=True)
    pd.testing.assert_frame_equal(first.delayed, second.delayed, check_exact=True)
    pd.testing.assert_frame_equal(first.weather, second.weather, check_exact=True)


@pytest.mark.parametrize("experiment", ["H", "Q"])
def test_a_zone_gets_the_days_cuts_weather_holidays_and_history_of_the_backtest(
        experiment, tmp_path):
    config = project_config(tmp_path)
    config["backtest"]["refit_every_days"] = 2
    save_tables(config)
    run_info = {"model": "lgbm_small", "split": "validation"}

    for zone in ordered_zones(config):
        point, quantile = PointRecorder("lgbm_small"), Recorder()
        backtest.backtest_zone(config, zone, experiment, "validation", point, run_info)
        quantile_zone(config, zone, experiment, "validation", quantile, run_info)

        assert [inputs.delivery_day.day for inputs in quantile.fits] == [20, 22, 24]
        assert len(quantile.fits) == len(point.fits)
        assert len(quantile.predicts) == len(point.predicts) == 5
        for ours, theirs in zip(quantile.fits + quantile.predicts, point.fits + point.predicts):
            assert_same_inputs(ours, theirs)
        # The entry has a history of 12 days. Zone A has a weather table and zone B has none.
        assert quantile.predicts[0].prices.index.min() == market_time("2026-10-08")
        assert bool(len(quantile.predicts[0].weather.columns)) == (zone.key == "A")


def test_a_validation_run_hands_the_model_no_row_of_the_test_days(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)
    model = Recorder()

    quantile_zone(config, ordered_zones(config)[0], "H", "validation", model, {})

    newest = max(inputs.day_ahead.index.max() for inputs in model.predicts)
    assert newest == market_time("2026-10-25") - timedelta(hours=1)


# The command line.

def test_the_command_reads_the_split_and_the_experiment_from_the_command_line(
        tmp_path, monkeypatch):
    config = project_config(tmp_path)
    save_tables(config)
    monkeypatch.setattr(quantiles, "load_config", lambda: config)
    monkeypatch.setattr("sys.argv", ["quantiles", "--split", "validation", "--experiment", "Q"])

    quantiles.main()

    assert saved(config, "quantile_core.csv")["experiment"].tolist() == ["Q"]
    assert saved(config, "quantile_extra.csv")["split"].tolist() == ["validation"]


def test_the_command_refuses_the_test_days_from_the_command_line(tmp_path, monkeypatch):
    config = project_config(tmp_path)
    save_tables(config)
    monkeypatch.setattr(quantiles, "load_config", lambda: config)
    monkeypatch.setattr("sys.argv", ["quantiles", "--split", "test"])

    with pytest.raises(SystemExit, match="may not be scored on the test days"):
        quantiles.main()

    assert not Path(config["paths"]["results"]).exists()


@pytest.mark.parametrize("arguments", [
    [],
    ["--split", "train"],
    ["--split", "validation", "--experiment", "D"],
    ["--split", "validation", "--model", "naive"],
])
def test_the_command_refuses_a_missing_or_unknown_argument(arguments, tmp_path, monkeypatch):
    monkeypatch.setattr(quantiles, "load_config", lambda: project_config(tmp_path))
    monkeypatch.setattr("sys.argv", ["quantiles", *arguments])

    with pytest.raises(SystemExit) as error:
        quantiles.main()

    assert error.value.code == 2


# The code.

def test_the_quantile_code_names_no_zone():
    config = load_config()
    names = [str(zone[key]) for zone in config["zones"] for key in ("key", "energy_charts")]
    names += [zone["weather_point"]["place"] for zone in config["zones"]]

    text = (REPO_ROOT / "src" / "epf" / "evaluation" / "quantiles.py").read_text(encoding="utf-8")

    found = [name for name in names if re.search(rf"\b{re.escape(name)}\b", text)]
    assert found == []
