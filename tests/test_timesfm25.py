"""Tests for the TimesFM 2.5 wrapper, run through the backtest loop.

A stub stands in for the loaded model, so the tests use no network and no
model download. The forecast options are the real timesfm.ForecastConfig, so
the tests import timesfm and torch. Each price table is a running number per
market time unit, starting at 0, so a context value names the position of its
price.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.evaluation.backtest import build_model, run, run_days
from epf.evaluation.cutoff import Columns, day_inputs
from epf.models.timesfm25 import TimesFm25Model

MARKET_TZ = "Europe/Berlin"
COLUMNS = Columns(price="price", day_ahead=("load_forecast",), delayed=("actual_load",))
# normalize_inputs and force_flip_invariance are the opposite of the timesfm defaults here,
# so an option that does not reach the model shows.
SOURCE = {"model_id": "google/timesfm-2.5-200m-pytorch", "revision": "abc123",
          "torch_compile": False, "max_horizon": 128, "normalize_inputs": True,
          "force_flip_invariance": False, "infer_is_positive": False}
ENTRY = {"family": "timesfm25", "context_days": 7}


class StubTimesFm:
    """Stands in for the loaded TimesFM model and keeps every call.

    The point forecast of step k is the last context value plus k, counted
    from 1. The second answer is 100 higher, so a wrapper that reads it gives
    another forecast.
    """

    def __init__(self):
        self.compiled: list = []
        self.calls: list[dict] = []

    def compile(self, forecast_config) -> None:
        self.compiled.append(forecast_config)

    def forecast(self, horizon, inputs):
        self.calls.append({"horizon": horizon, "inputs": inputs})
        point = inputs[0][-1] + np.arange(1, horizon + 1, dtype=np.float32)
        # The real model answers with (series, steps) and (series, steps, mean and 9 quantiles).
        return point[None, :], np.repeat(point[None, :, None], 10, axis=2) + 100


class Loader:
    """Stands in for the function that loads the model and keeps its calls."""

    def __init__(self, model: StubTimesFm):
        self.model = model
        self.calls: list[tuple[dict, int]] = []

    def __call__(self, source: dict, seed: int) -> StubTimesFm:
        self.calls.append((source, seed))
        return self.model


def market_time(day: str | date) -> pd.Timestamp:
    """00:00 in market time on a day."""
    return pd.Timestamp(day, tz=MARKET_TZ)


def day_after(day: str, days: int = 1) -> date:
    """The calendar day some days after a day. A negative number goes back."""
    return date.fromisoformat(day) + timedelta(days=days)


def running_table(first_day: str, end_day: str, make_index=hourly_index) -> pd.DataFrame:
    """A table from first_day up to the start of end_day. The price is 0, 1, 2, ..."""
    index = make_index(market_time(first_day), market_time(end_day))
    numbers = pd.Series(range(len(index)), index=index, dtype=float)
    return pd.DataFrame({"price": numbers, "load_forecast": numbers + 0.1,
                         "actual_load": numbers + 0.3})


def model_and_stub(source: dict = SOURCE) -> tuple[TimesFm25Model, StubTimesFm, Loader]:
    """A model whose loader hands back a stub."""
    stub = StubTimesFm()
    loader = Loader(stub)
    return TimesFm25Model("candidate", ENTRY, source, 42, load=loader), stub, loader


def forecasts(model: TimesFm25Model, table: pd.DataFrame, first_day: str, count: int = 1,
              make_index=hourly_index) -> pd.Series:
    """The forecasts of count delivery days through the backtest loop."""
    days = delivery_days(market_time(first_day), market_time(day_after(first_day, count)))
    scored, _ = run_days(table, days, make_index, model, COLUMNS, refit_every_days=7)
    return scored["forecast"]


@pytest.mark.parametrize("make_index, day, units", [
    (hourly_index, "2026-07-01", 24), (hourly_index, "2026-03-29", 23),
    (hourly_index, "2026-10-25", 25), (quarter_hour_index, "2026-07-01", 96),
    (quarter_hour_index, "2026-03-29", 92), (quarter_hour_index, "2026-10-25", 100)])
def test_the_horizon_is_the_number_of_market_time_units_of_the_delivery_day(make_index, day,
                                                                             units):
    model, stub, _ = model_and_stub()
    table = running_table(str(day_after(day, -10)), str(day_after(day, 2)), make_index)

    forecast = forecasts(model, table, day, make_index=make_index)

    assert stub.calls[0]["horizon"] == units
    assert len(forecast) == units
    assert forecast.index.equals(make_index(market_time(day), market_time(day_after(day))))


def test_infer_is_positive_false_reaches_timesfm():
    model, stub, _ = model_and_stub()

    forecasts(model, running_table("2026-06-01", "2026-07-03"), "2026-07-01")

    assert stub.compiled[0].infer_is_positive is False


def test_a_model_section_that_would_cut_the_forecast_at_zero_is_refused():
    with pytest.raises(ValueError, match="infer_is_positive.*negative"):
        TimesFm25Model("candidate", ENTRY, {**SOURCE, "infer_is_positive": True}, 42)


def test_the_options_of_the_model_section_reach_timesfm():
    model, stub, _ = model_and_stub()

    forecasts(model, running_table("2026-06-01", "2026-07-03"), "2026-07-01")

    options = stub.compiled[0]
    assert options.max_horizon == 128
    assert options.normalize_inputs is True
    assert options.force_flip_invariance is False


@pytest.mark.parametrize("make_index, steps", [(hourly_index, 168), (quarter_hour_index, 672)])
def test_the_longest_context_of_timesfm_is_the_context_days_of_the_table(make_index, steps):
    model, stub, _ = model_and_stub()
    table = running_table("2026-06-01", "2026-07-03", make_index)

    forecasts(model, table, "2026-07-01", make_index=make_index)

    assert stub.compiled[0].max_context == steps


def test_one_model_is_set_up_again_for_the_table_of_each_run():
    model, stub, loader = model_and_stub()

    forecasts(model, running_table("2026-06-01", "2026-07-03"), "2026-07-01")
    forecasts(model, running_table("2026-06-01", "2026-07-03", quarter_hour_index), "2026-07-01",
              make_index=quarter_hour_index)

    assert [options.max_context for options in stub.compiled] == [168, 672]
    assert len(loader.calls) == 1


def test_timesfm_receives_the_last_context_days_of_prices():
    model, stub, _ = model_and_stub()

    forecasts(model, running_table("2026-06-01", "2026-07-03"), "2026-07-01")

    # 30 days of history are the hours 0 to 719. The context of 7 days is the last 168.
    assert len(stub.calls[0]["inputs"]) == 1
    assert stub.calls[0]["inputs"][0].tolist() == list(range(552, 720))


def test_the_forecast_is_the_point_forecast_of_timesfm():
    model, _, _ = model_and_stub()

    forecast = forecasts(model, running_table("2026-06-01", "2026-07-03"), "2026-07-01")

    # The last price before the delivery day is 719.
    assert forecast.tolist() == list(range(720, 744))


# The second forecast day is 2026-10-25 with 25 hours.
def test_no_price_of_the_delivery_day_or_later_reaches_timesfm():
    model, stub, _ = model_and_stub()
    table = running_table("2026-10-10", "2026-11-01")

    forecasts(model, table, "2026-10-24", count=3)

    # 14, 15 and 16 days of history end with the hours 335, 359 and 384.
    assert [call["inputs"][0][-1] for call in stub.calls] == [335, 359, 384]
    assert [call["inputs"][0].max() for call in stub.calls] == [335, 359, 384]


def test_changing_every_value_after_the_price_cut_leaves_the_forecast_unchanged():
    table = running_table("2026-06-01", "2026-07-03")
    changed = table.copy()
    changed.loc[changed.index >= market_time("2026-07-01"), "price"] += 1000

    before = forecasts(model_and_stub()[0], table, "2026-07-01")
    after = forecasts(model_and_stub()[0], changed, "2026-07-01")

    pd.testing.assert_series_equal(before, after)


def test_the_wrapper_reads_the_price_and_no_other_column():
    table = running_table("2026-06-01", "2026-07-03")
    changed = table.copy()
    changed["load_forecast"] += 1000
    changed["actual_load"] += 1000

    before = forecasts(model_and_stub()[0], table, "2026-07-01")
    after = forecasts(model_and_stub()[0], changed, "2026-07-01")

    pd.testing.assert_series_equal(before, after)


def test_building_the_model_loads_nothing():
    _, stub, loader = model_and_stub()

    assert loader.calls == []
    assert stub.compiled == []


def test_the_model_is_loaded_once_with_the_model_section_and_the_seed():
    model, stub, loader = model_and_stub()
    table = running_table("2026-06-01", "2026-07-12")

    # 9 days: fit is called on the first and on the eighth day.
    forecasts(model, table, "2026-07-01", count=9)

    assert loader.calls == [(SOURCE, 42)]
    assert len(stub.calls) == 9


def test_a_forecast_before_the_model_is_loaded_is_refused():
    model, _, _ = model_and_stub()
    table = running_table("2026-06-01", "2026-07-03")
    day_start, day_end = market_time("2026-07-01"), market_time("2026-07-02")
    inputs = day_inputs(table, day_start, day_end, hourly_index(day_start, day_end), COLUMNS)

    with pytest.raises(ValueError, match="candidate.*not been loaded"):
        model.predict(inputs)


def test_the_params_for_the_results_hold_the_entry_and_the_model_section():
    model, _, _ = model_and_stub()

    assert model.name == "candidate"
    assert model.params == {**ENTRY, **SOURCE}
    assert model.params["context_days"] == 7
    assert model.params["revision"] == "abc123"


@pytest.mark.parametrize("entry, source, message", [
    ({"family": "timesfm25"}, SOURCE, "context_days.*missing"),
    ({**ENTRY, "context_days": 0}, SOURCE, "context_days"),
    ({**ENTRY, "family": "chronos2"}, SOURCE, "chronos2"),
    (ENTRY, {key: value for key, value in SOURCE.items() if key != "revision"},
     "revision.*missing"),
    (ENTRY, {key: value for key, value in SOURCE.items() if key != "infer_is_positive"},
     "infer_is_positive.*missing"),
])
def test_a_wrong_entry_or_model_section_is_refused_when_the_model_is_built(entry, source,
                                                                          message):
    with pytest.raises(ValueError, match=message):
        TimesFm25Model("candidate", entry, source, 42)


def project_config(entry: dict) -> dict:
    """The parts of a config that build_model reads for a TimesFM entry."""
    return {"seed": 42, "models": {"naive": {"lag_days": 7}, "timesfm25_7": entry},
            "foundation_models": {"timesfm25": SOURCE}}


def test_the_backtest_builds_the_model_from_its_entry_and_the_model_section():
    model = build_model(project_config(ENTRY), "timesfm25_7")

    assert isinstance(model, TimesFm25Model)
    assert model.name == "timesfm25_7"
    assert model.params == {**ENTRY, **SOURCE}
    assert model.seed == 42


def test_the_backtest_refuses_a_timesfm25_entry_in_a_config_without_its_section():
    config = project_config(ENTRY)
    del config["foundation_models"]

    with pytest.raises(ValueError, match="foundation_models.timesfm25"):
        build_model(config, "timesfm25_7")


def test_the_command_ends_with_one_line_for_a_wrong_entry():
    config = project_config({"family": "timesfm25", "context_days": 2.5})

    with pytest.raises(SystemExit) as ended:
        run(config, "timesfm25_7", "validation")

    message = str(ended.value)
    assert "timesfm25" in message and "context_days" in message
    assert "\n" not in message
