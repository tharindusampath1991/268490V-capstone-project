"""Tests for the Chronos-2 wrapper, run through the backtest loop.

A stub stands in for the loaded pipeline, so the tests use no network, no
model download and no torch. Each price table is a running number per market
time unit, starting at 0, so a context value names the position of its price.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.evaluation.backtest import build_model, run, run_days
from epf.evaluation.cutoff import Columns, day_inputs
from epf.models.chronos2 import Chronos2Model

MARKET_TZ = "Europe/Berlin"
COLUMNS = Columns(price="price", day_ahead=("load_forecast",), delayed=("actual_load",))
SOURCE = {"model_id": "amazon/chronos-2", "revision": "abc123", "device": "cpu"}
ENTRY = {"family": "chronos2", "context_days": 7}


class StubPipeline:
    """Stands in for the loaded Chronos2Pipeline and keeps every call.

    The 0.5 quantile of step k is the last context value plus k, counted from
    1. Another level moves the answer, and the mean is 100 higher, so a
    wrapper that reads another output gives another forecast.
    """

    model_context_length = 8192

    def __init__(self):
        self.calls: list[dict] = []

    def predict_quantiles(self, inputs, prediction_length, quantile_levels, context_length):
        self.calls.append({"inputs": inputs, "prediction_length": prediction_length,
                           "quantile_levels": quantile_levels, "context_length": context_length})
        median = inputs[0][-1] + np.arange(1, prediction_length + 1, dtype=np.float32)
        levels = np.array(quantile_levels, dtype=np.float32)
        # Per series the real pipeline answers with (variates, steps, levels) and (variates, steps).
        quantiles = median[None, :, None] + 10 * (levels[None, None, :] - 0.5)
        return [quantiles], [median[None, :] + 100]


class Loader:
    """Stands in for the function that loads the pipeline and keeps its calls."""

    def __init__(self, pipeline: StubPipeline):
        self.pipeline = pipeline
        self.calls: list[tuple[dict, int]] = []

    def __call__(self, source: dict, seed: int) -> StubPipeline:
        self.calls.append((source, seed))
        return self.pipeline


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


def model_and_stub(entry: dict = ENTRY) -> tuple[Chronos2Model, StubPipeline, Loader]:
    """A model whose loader hands back a stub pipeline."""
    stub = StubPipeline()
    loader = Loader(stub)
    return Chronos2Model("candidate", entry, SOURCE, 42, load=loader), stub, loader


def forecasts(model: Chronos2Model, table: pd.DataFrame, first_day: str, count: int = 1,
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

    assert stub.calls[0]["prediction_length"] == units
    assert len(forecast) == units
    assert forecast.index.equals(make_index(market_time(day), market_time(day_after(day))))


def test_the_pipeline_receives_the_last_context_days_of_prices_and_their_length():
    model, stub, _ = model_and_stub()
    table = running_table("2026-06-01", "2026-07-03")

    forecasts(model, table, "2026-07-01")

    # 30 days of history are the hours 0 to 719. The context of 7 days is the last 168.
    assert len(stub.calls[0]["inputs"]) == 1
    assert stub.calls[0]["inputs"][0].tolist() == list(range(552, 720))
    assert stub.calls[0]["context_length"] == 168


def test_the_context_of_the_quarter_hour_table_covers_the_same_days():
    model, stub, _ = model_and_stub()
    table = running_table("2026-06-01", "2026-07-03", quarter_hour_index)

    forecasts(model, table, "2026-07-01", make_index=quarter_hour_index)

    assert stub.calls[0]["inputs"][0].tolist() == list(range(2208, 2880))
    assert stub.calls[0]["context_length"] == 672


def test_the_forecast_is_the_half_quantile_of_the_pipeline():
    model, stub, _ = model_and_stub()
    table = running_table("2026-06-01", "2026-07-03")

    forecast = forecasts(model, table, "2026-07-01")

    # The last price before the delivery day is 719.
    assert stub.calls[0]["quantile_levels"] == [0.5]
    assert forecast.tolist() == list(range(720, 744))


# The second forecast day is 2026-10-25 with 25 hours, so it is D, and D-1 for no day.
def test_no_price_of_the_delivery_day_or_later_reaches_the_pipeline():
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
    _, _, loader = model_and_stub()

    assert loader.calls == []


def test_the_pipeline_is_loaded_once_with_the_model_section_and_the_seed():
    model, stub, loader = model_and_stub()
    table = running_table("2026-06-01", "2026-07-12")

    # 9 days: fit is called on the first and on the eighth day.
    forecasts(model, table, "2026-07-01", count=9)

    assert loader.calls == [(SOURCE, 42)]
    assert len(stub.calls) == 9


def test_a_forecast_before_the_pipeline_is_loaded_is_refused():
    model, _, _ = model_and_stub()
    table = running_table("2026-06-01", "2026-07-03")
    day_start, day_end = market_time("2026-07-01"), market_time("2026-07-02")
    inputs = day_inputs(table, day_start, day_end, hourly_index(day_start, day_end), COLUMNS)

    with pytest.raises(ValueError, match="candidate.*not been loaded"):
        model.predict(inputs)


def test_a_context_above_the_limit_of_the_model_is_refused():
    model, stub, _ = model_and_stub()
    stub.model_context_length = 100
    table = running_table("2026-06-01", "2026-07-03")

    with pytest.raises(ValueError, match="168.*100"):
        forecasts(model, table, "2026-07-01")


def test_the_params_for_the_results_hold_the_entry_and_the_model_section():
    model, _, _ = model_and_stub()

    assert model.name == "candidate"
    assert model.params == {"family": "chronos2", "context_days": 7,
                            "model_id": "amazon/chronos-2", "revision": "abc123",
                            "device": "cpu"}


@pytest.mark.parametrize("entry, source, message", [
    ({"family": "chronos2"}, SOURCE, "context_days.*missing"),
    ({**ENTRY, "context_days": 0}, SOURCE, "context_days"),
    ({**ENTRY, "family": "timesfm25"}, SOURCE, "timesfm25"),
    (ENTRY, {"model_id": "amazon/chronos-2", "device": "cpu"}, "revision.*missing"),
])
def test_a_wrong_entry_or_model_section_is_refused_when_the_model_is_built(entry, source,
                                                                          message):
    with pytest.raises(ValueError, match=message):
        Chronos2Model("candidate", entry, source, 42)


def project_config(entry: dict) -> dict:
    """The parts of a config that build_model reads for a Chronos-2 entry."""
    return {"seed": 42, "models": {"naive": {"lag_days": 7}, "chronos2_7": entry},
            "foundation_models": {"chronos2": SOURCE}}


def test_the_backtest_builds_the_model_from_its_entry_and_the_model_section():
    model = build_model(project_config(ENTRY), "chronos2_7")

    assert isinstance(model, Chronos2Model)
    assert model.name == "chronos2_7"
    assert model.params == {**ENTRY, **SOURCE}
    assert model.seed == 42


def test_the_backtest_refuses_a_chronos2_entry_in_a_config_without_its_section():
    config = project_config(ENTRY)
    del config["foundation_models"]

    with pytest.raises(ValueError, match="foundation_models.chronos2"):
        build_model(config, "chronos2_7")


def test_the_command_ends_with_one_line_for_a_wrong_entry():
    config = project_config({"family": "chronos2", "context_days": 0})

    with pytest.raises(SystemExit) as ended:
        run(config, "chronos2_7", "validation")

    message = str(ended.value)
    assert "chronos2" in message and "context_days" in message
    assert "\n" not in message
