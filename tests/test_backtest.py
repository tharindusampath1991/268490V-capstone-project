"""Tests for the backtest loop, with the leakage tests of PROJECT_CONTEXT section 5.

They use small synthetic tables, no network and no data files.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.evaluation.backtest import run_days
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
