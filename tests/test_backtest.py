"""Tests for the backtest loop and command, with the leakage tests of PROJECT_CONTEXT section 5.

They use small synthetic tables, a temporary folder, no network and no data files.
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.data.splits import split_range
from epf.data.validate import HOURLY, QUARTER_HOUR, table_path
from epf.evaluation.backtest import (
    lag_check_days,
    matches_price_before,
    read_table,
    run,
    run_days,
)
from epf.evaluation.cutoff import Columns, DayInputs
from epf.models.naive import SeasonalNaive

MARKET_TZ = "Europe/Berlin"
COLUMNS = Columns(price="price",
                  day_ahead=("load_forecast", "wind_onshore_forecast", "solar_forecast"),
                  delayed=("actual_load",))


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


def days_from(first_day: str, count: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """The delivery days from first_day on, as (day start, next day start)."""
    return delivery_days(market_time(first_day), market_time(day_after(first_day, count)))


class Recorder:
    """A model that keeps every input it is given and forecasts zero."""

    def __init__(self):
        self.fits: list[DayInputs] = []
        self.predicts: list[DayInputs] = []

    def fit(self, inputs: DayInputs) -> None:
        self.fits.append(inputs)

    def predict(self, inputs: DayInputs) -> pd.Series:
        self.predicts.append(inputs)
        return pd.Series(0.0, index=inputs.target_index)


class UsesEverything:
    """A model whose forecast is the sum of every value it is given."""

    def fit(self, inputs: DayInputs) -> None:
        pass

    def predict(self, inputs: DayInputs) -> pd.Series:
        total = (inputs.prices.sum() + inputs.day_ahead.to_numpy().sum()
                 + inputs.delayed.to_numpy().sum())
        return pd.Series(total, index=inputs.target_index)


class Vandal:
    """A model that overwrites everything it is given."""

    def fit(self, inputs: DayInputs) -> None:
        pass

    def predict(self, inputs: DayInputs) -> pd.Series:
        inputs.prices.iloc[:] = -999.0
        inputs.day_ahead.iloc[:, :] = -999.0
        inputs.delayed.iloc[:, :] = -999.0
        return pd.Series(1.0, index=inputs.target_index)


class WrongIndex:
    """A model that answers for the hours one hour later."""

    def fit(self, inputs: DayInputs) -> None:
        pass

    def predict(self, inputs: DayInputs) -> pd.Series:
        return pd.Series(1.0, index=inputs.target_index + timedelta(hours=1))


def change_after_the_cuts(table: pd.DataFrame, day: str) -> pd.DataFrame:
    """Return a copy with every value changed that a model may not see for a delivery day."""
    changed = table.copy()
    changed.loc[changed.index >= market_time(day), "price"] += 1000
    for column in ("load_forecast", "wind_onshore_forecast"):
        changed.loc[changed.index >= market_time(day_after(day)), column] += 1000
    changed.loc[changed.index >= market_time(day_after(day, -1)), "actual_load"] += 1000
    return changed


def forecast_of(model, table: pd.DataFrame, day: str, make_index=hourly_index) -> pd.Series:
    """The forecast of one delivery day through the backtest loop."""
    scored, _ = run_days(table, days_from(day, 1), make_index, model, COLUMNS,
                         refit_every_days=7)
    return scored["forecast"]


# The days hold 2026-10-25 with 25 hours, as D, as D-1 and as D-2.
@pytest.mark.parametrize("make_index", [hourly_index, quarter_hour_index])
def test_a_model_never_receives_a_value_after_its_cut(make_index):
    table = make_table("2026-10-10", "2026-11-05", make_index)
    model = Recorder()

    run_days(table, days_from("2026-10-20", 14), make_index, model, COLUMNS, refit_every_days=7)

    assert len(model.predicts) == 14
    assert len(model.fits) == 2
    for inputs in model.fits + model.predicts:
        day = inputs.delivery_day
        assert inputs.prices.index.max() < market_time(day)
        assert inputs.day_ahead.index.max() < market_time(day + timedelta(days=1))
        assert inputs.delayed.index.max() < market_time(day - timedelta(days=1))


def test_changing_every_value_after_the_cuts_leaves_the_forecast_unchanged():
    table = make_table("2026-06-20", "2026-07-05")

    before = forecast_of(UsesEverything(), table, "2026-07-01")
    after = forecast_of(UsesEverything(), change_after_the_cuts(table, "2026-07-01"),
                        "2026-07-01")

    pd.testing.assert_series_equal(before, after)


@pytest.mark.parametrize("column, last_seen", [
    ("price", "2026-06-30 23:00"),
    ("load_forecast", "2026-07-01 23:00"),
    ("wind_onshore_forecast", "2026-07-01 23:00"),
    ("actual_load", "2026-06-29 23:00"),
])
def test_changing_the_last_value_before_a_cut_changes_the_forecast(column, last_seen):
    table = make_table("2026-06-20", "2026-07-05")
    changed = table.copy()
    changed.loc[pd.Timestamp(last_seen, tz=MARKET_TZ), column] += 1000

    before = forecast_of(UsesEverything(), table, "2026-07-01")
    after = forecast_of(UsesEverything(), changed, "2026-07-01")

    assert (after - before).tolist() == pytest.approx([1000.0] * 24)


@pytest.mark.parametrize("day", ["2026-07-01", "2026-10-25", "2026-11-01"])
def test_the_naive_forecast_ignores_every_value_after_the_cuts(day):
    table = make_table(str(day_after(day, -10)), str(day_after(day, 3)))
    model = SeasonalNaive(lag_days=7)

    before = forecast_of(model, table, day)
    after = forecast_of(model, change_after_the_cuts(table, day), day)

    assert before.notna().all()
    pd.testing.assert_series_equal(before, after)


def test_the_naive_forecast_follows_the_price_seven_days_before():
    table = make_table("2026-06-20", "2026-07-05")
    changed = table.copy()
    changed.loc[market_time("2026-06-24"), "price"] += 1000

    before = forecast_of(SeasonalNaive(lag_days=7), table, "2026-07-01")
    after = forecast_of(SeasonalNaive(lag_days=7), changed, "2026-07-01")

    assert (after - before).tolist() == [1000.0] + [0.0] * 23


def test_a_model_that_overwrites_its_inputs_changes_neither_the_table_nor_the_actuals():
    table = make_table("2026-06-20", "2026-07-05")
    original = table.copy()

    scored, _ = run_days(table, days_from("2026-07-01", 3), hourly_index, Vandal(), COLUMNS,
                         refit_every_days=7)

    pd.testing.assert_frame_equal(table, original)
    assert scored["actual"].tolist() == original.loc[scored.index, "price"].tolist()


def test_a_forecast_on_other_timestamps_is_refused():
    table = make_table("2026-06-20", "2026-07-05")

    with pytest.raises(ValueError, match="index"):
        forecast_of(WrongIndex(), table, "2026-07-01")


def test_fit_is_called_on_the_first_day_and_then_every_refit_every_days():
    table = make_table("2026-06-01", "2026-07-05")
    model = Recorder()

    run_days(table, days_from("2026-06-15", 15), hourly_index, model, COLUMNS,
             refit_every_days=7)

    assert [inputs.delivery_day for inputs in model.fits] == [
        date(2026, 6, 15), date(2026, 6, 22), date(2026, 6, 29)]


def test_history_days_limits_what_the_model_receives():
    table = make_table("2026-06-01", "2026-07-05")
    model = Recorder()

    run_days(table, days_from("2026-07-01", 1), hourly_index, model, COLUMNS,
             refit_every_days=7, history_days=5)

    assert model.predicts[0].prices.index.min() == market_time("2026-06-26")


def test_scored_frame_holds_forecast_and_actual_for_every_market_time_unit():
    table = make_table("2026-10-10", "2026-11-05")

    scored, seconds = run_days(table, days_from("2026-10-24", 3), hourly_index,
                               SeasonalNaive(lag_days=7), COLUMNS, refit_every_days=7)

    expected = hourly_index(market_time("2026-10-24"), market_time("2026-10-27"))
    assert len(expected) == 24 + 25 + 24
    assert scored.index.equals(expected)
    assert list(scored.columns) == ["forecast", "actual"]
    assert scored["actual"].tolist() == table.loc[expected, "price"].tolist()
    assert seconds >= 0


def test_a_table_column_under_no_cut_stops_the_run():
    table = make_table("2026-06-20", "2026-07-05").assign(temperature_2m=1.0)

    with pytest.raises(ValueError, match="temperature_2m"):
        forecast_of(Recorder(), table, "2026-07-01")


# The command. A small project in a temporary folder: zone A is core, zone B is extra.
# The price of a delivery day is its number, so the naive forecast is always 7 too low.

def project_config(tmp_path, data_start: str = "2026-10-05") -> dict:
    """A config with 5 validation days and 10 test days, the 25-hour day among them."""
    return {
        "seed": 42,
        "market": {"timezone": MARKET_TZ},
        "paths": {"processed": str(tmp_path / "processed"),
                  "results": str(tmp_path / "results"),
                  "forecasts": str(tmp_path / "forecasts")},
        "data": {"start": data_start, "end": "2026-11-03"},
        "splits": {"validation_days": 5, "test_days": 10,
                   "validation_start": "2026-10-20", "test_start": "2026-10-25"},
        "backtest": {"refit_every_days": 7, "history_days": None, "test_models": ["naive"],
                     "price_column": "price", "day_ahead_columns": ["load_forecast"],
                     "delayed_columns": ["actual_load"]},
        "models": {"naive": {"lag_days": 7}},
        "zones": [{"key": "B", "holiday_country": "XX", "group": "extra"},
                  {"key": "A", "holiday_country": "XX", "group": "core"}],
    }


def save_tables(config: dict, zone_keys=("A", "B")) -> None:
    """Write the hourly and the 15-minute table of each zone."""
    start = market_time(config["data"]["start"])
    end = market_time(day_after(config["data"]["end"]))
    for name, make_index in ((HOURLY, hourly_index), (QUARTER_HOUR, quarter_hour_index)):
        index = make_index(start, end)
        local_day = index.tz_convert(MARKET_TZ).tz_localize(None).normalize()
        day_number = (local_day - start.tz_localize(None)).days.astype(float)
        table = pd.DataFrame({"price": day_number, "load_forecast": 1.0, "actual_load": 2.0},
                             index=index)
        for zone_key in zone_keys:
            path = table_path(Path(config["paths"]["processed"]), name, zone_key)
            path.parent.mkdir(parents=True, exist_ok=True)
            table.to_parquet(path)


def saved(config: dict, name: str) -> pd.DataFrame:
    """Read one results file of the temporary project."""
    return pd.read_csv(Path(config["paths"]["results"]) / name)


def test_run_scores_the_validation_days_of_core_and_extra_zones_in_their_own_files(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "naive", "validation")

    core, extra = saved(config, "backtest_core.csv"), saved(config, "backtest_extra.csv")
    assert core["zone"].tolist() == ["A", "A"]
    assert extra["zone"].tolist() == ["B", "B"]
    assert core["experiment"].tolist() == ["H", "Q"]
    assert core["days"].tolist() == [5, 5]
    assert core["mtus"].tolist() == [120, 480]
    assert core["first_day"].tolist() == ["2026-10-20"] * 2
    assert core["last_day"].tolist() == ["2026-10-24"] * 2
    # Every forecast is the price of 7 days before, which is 7 lower.
    assert core["mae"].tolist() == [7.0, 7.0]
    assert core["rmse"].tolist() == [7.0, 7.0]
    assert core["relative_mae"].tolist() == [1.0, 1.0]
    assert core["empty_forecasts"].tolist() == [0, 0]
    assert core["seed"].tolist() == [42, 42]
    assert core["split"].tolist() == ["validation"] * 2
    assert (core["wall_seconds"] >= 0).all()
    assert core["hardware"].str.contains("GB RAM").all()


def test_run_writes_the_daily_losses_and_the_forecasts(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "naive", "validation")

    daily = saved(config, "daily_core.csv")
    hourly_days = daily[daily["experiment"] == "H"]
    assert hourly_days["delivery_day"].tolist() == [f"2026-10-{day}" for day in range(20, 25)]
    assert hourly_days["mtus"].tolist() == [24] * 5
    assert hourly_days["mae"].tolist() == [7.0] * 5
    assert hourly_days["mse"].tolist() == [49.0] * 5
    forecasts = pd.read_parquet(
        Path(config["paths"]["forecasts"]) / "naive" / "Q" / "validation" / "B.parquet")
    assert len(forecasts) == 480
    assert (forecasts["actual"] - forecasts["forecast"]).tolist() == [7.0] * 480


def test_run_on_the_test_days_counts_the_25_hours_of_the_clock_change_day(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "naive", "test")

    core = saved(config, "backtest_core.csv")
    assert core["days"].tolist() == [10, 10]
    assert core["mtus"].tolist() == [241, 964]
    assert core["mae"].tolist() == [7.0, 7.0]
    daily = saved(config, "daily_core.csv")
    assert daily.loc[daily["delivery_day"] == "2026-10-25", "mtus"].tolist() == [25, 100]


def test_a_second_run_adds_rows_to_the_log_and_replaces_the_daily_losses(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    run(config, "naive", "validation")
    run(config, "naive", "validation")

    assert len(saved(config, "backtest_core.csv")) == 4
    assert len(saved(config, "daily_core.csv")) == 10


def test_run_refuses_the_test_days_for_a_model_that_is_not_listed(tmp_path):
    config = project_config(tmp_path)
    config["backtest"]["test_models"] = []
    save_tables(config)

    with pytest.raises(SystemExit, match="test"):
        run(config, "naive", "test")

    assert not Path(config["paths"]["results"]).exists()


def test_run_refuses_an_unknown_model(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)

    with pytest.raises(SystemExit, match="sarima"):
        run(config, "sarima", "validation")


def test_run_with_an_empty_forecast_fails_and_writes_nothing(tmp_path):
    # The tables start 3 days before the first validation day, so no price of D-7 exists.
    config = project_config(tmp_path, data_start="2026-10-17")
    save_tables(config)

    with pytest.raises(SystemExit, match="empty"):
        run(config, "naive", "validation")

    assert not Path(config["paths"]["results"]).exists()
    assert not Path(config["paths"]["forecasts"]).exists()


def test_core_results_are_written_before_an_extra_zone_fails(tmp_path):
    config = project_config(tmp_path)
    save_tables(config, zone_keys=("A",))

    with pytest.raises(SystemExit, match="B"):
        run(config, "naive", "validation")

    assert len(saved(config, "backtest_core.csv")) == 2
    assert not (Path(config["paths"]["results"]) / "backtest_extra.csv").exists()


def test_a_validation_run_reads_no_row_of_the_test_days(tmp_path):
    config = project_config(tmp_path)
    save_tables(config)
    _, validation_end = split_range(config, "validation")

    table = read_table(config, HOURLY, "A", validation_end)

    assert table.index.max() == market_time("2026-10-25") - timedelta(hours=1)


def test_lag_check_days_are_the_first_middle_and_last_day_with_no_clock_change_before():
    days = days_from("2026-10-20", 15)   # 2026-10-20 to 2026-11-03

    chosen = lag_check_days(days, lag_days=7)

    # The clock changes on 2026-10-25. It lies between D-7 and the end of D for the days
    # 25 Oct to 1 Nov. Seven days are left: 20 to 24 Oct, 2 Nov and 3 Nov.
    assert [str(day_start.date()) for day_start, _ in chosen] == [
        "2026-10-20", "2026-10-23", "2026-11-03"]


def test_matches_price_before_compares_the_forecast_with_the_price_168_hours_earlier():
    table = make_table("2026-06-20", "2026-07-05")
    day = days_from("2026-07-01", 1)[0]
    scored, _ = run_days(table, [day], hourly_index, SeasonalNaive(lag_days=7), COLUMNS,
                         refit_every_days=7)
    wrong = scored.assign(forecast=scored["forecast"] + 1)

    assert matches_price_before(scored, table["price"], day, lag_days=7)
    assert not matches_price_before(wrong, table["price"], day, lag_days=7)
