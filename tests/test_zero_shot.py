"""Tests for what the two zero-shot wrappers share: the context and the checks of an entry.

Each price history is a running number per market time unit, starting at 0. A
context value therefore names the position of the price it was taken from.
They use no network, no data files and no model.
"""

import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import hourly_index, quarter_hour_index
from epf.evaluation.cutoff import Columns, day_inputs
from epf.models.zero_shot import check_entry, context_steps, price_context, source_settings

MARKET_TZ = "Europe/Berlin"
COLUMNS = Columns(price="price", day_ahead=("load_forecast",), delayed=("actual_load",))
ENTRY = {"family": "chronos2", "context_days": 28}
SOURCE = {"model_id": "some/model", "revision": "abc123"}
SOURCE_KEYS = ("model_id", "revision")


def market_time(day: str) -> pd.Timestamp:
    """00:00 in market time on a day."""
    return pd.Timestamp(day, tz=MARKET_TZ)


def inputs_of(first_day: str, delivery_day: str, next_day: str, make_index=hourly_index):
    """The inputs of a delivery day from a table that starts on first_day and runs past the day.

    The price is 0, 1, 2, ... from the first market time unit on.
    """
    index = make_index(market_time(first_day), market_time(next_day))
    numbers = pd.Series(range(len(index)), index=index, dtype=float)
    table = pd.DataFrame({"price": numbers, "load_forecast": -1.0, "actual_load": -2.0})
    day_start, day_end = market_time(delivery_day), market_time(next_day)
    return day_inputs(table, day_start, day_end, make_index(day_start, day_end), COLUMNS)


@pytest.mark.parametrize("make_index, steps", [(hourly_index, 672), (quarter_hour_index, 2688)])
def test_context_steps_are_the_context_days_in_market_time_units(make_index, steps):
    target = make_index(market_time("2026-07-01"), market_time("2026-07-02"))

    assert context_steps(28, target) == steps


def test_context_steps_do_not_change_on_a_day_with_23_hours():
    target = hourly_index(market_time("2026-03-29"), market_time("2026-03-30"))

    assert len(target) == 23
    assert context_steps(28, target) == 672


def test_the_context_is_the_last_hourly_prices_before_the_delivery_day_in_their_order():
    inputs = inputs_of("2026-06-01", "2026-07-01", "2026-07-02")

    context = price_context(inputs, context_days=7)

    # 30 days of history are the hours 0 to 719. The last 7 days are 168 hours.
    assert context.tolist() == list(range(552, 720))


def test_the_context_is_the_last_quarter_hour_prices_before_the_delivery_day():
    inputs = inputs_of("2026-06-01", "2026-07-01", "2026-07-02", quarter_hour_index)

    context = price_context(inputs, context_days=7)

    # 30 days of history are the quarter-hours 0 to 2879. The last 7 days are 672 of them.
    assert context.tolist() == list(range(2208, 2880))


def test_the_context_counts_steps_across_the_day_with_25_hours():
    inputs = inputs_of("2026-10-20", "2026-10-27", "2026-10-28")

    context = price_context(inputs, context_days=2)

    # 7 days with the 25-hour day of 2026-10-25 are the hours 0 to 168.
    assert context.tolist() == list(range(121, 169))


def test_a_history_shorter_than_the_context_is_handed_over_whole():
    inputs = inputs_of("2026-06-28", "2026-07-01", "2026-07-02")

    context = price_context(inputs, context_days=7)

    assert context.tolist() == list(range(72))


def test_an_empty_price_inside_the_context_is_refused():
    inputs = inputs_of("2026-06-01", "2026-07-01", "2026-07-02")
    inputs.prices.iloc[-10] = np.nan

    with pytest.raises(ValueError, match="2026-07-01.*empty"):
        price_context(inputs, context_days=7)


def test_an_empty_price_before_the_context_is_not_read():
    inputs = inputs_of("2026-06-01", "2026-07-01", "2026-07-02")
    inputs.prices.iloc[0] = np.nan

    context = price_context(inputs, context_days=7)

    assert len(context) == 168


def test_a_delivery_day_without_any_price_before_it_is_refused():
    inputs = inputs_of("2026-07-01", "2026-07-01", "2026-07-02")

    with pytest.raises(ValueError, match="2026-07-01.*no price"):
        price_context(inputs, context_days=7)


def test_a_complete_entry_passes_the_check():
    check_entry(ENTRY, "chronos2", SOURCE, SOURCE_KEYS)


@pytest.mark.parametrize("entry, message", [
    ({"family": "chronos2"}, "context_days.*missing"),
    ({"context_days": 28}, "family.*missing"),
    ({**ENTRY, "history_days": 28}, "history_days.*unknown"),
    ({**ENTRY, "family": "timesfm25"}, "timesfm25.*chronos2"),
    ({**ENTRY, "context_days": 0}, "context_days"),
    ({**ENTRY, "context_days": -7}, "context_days"),
    ({**ENTRY, "context_days": 2.5}, "context_days"),
    ({**ENTRY, "context_days": "28"}, "context_days"),
    ({**ENTRY, "context_days": True}, "context_days"),
])
def test_an_entry_the_model_cannot_run_is_refused(entry, message):
    with pytest.raises(ValueError, match=message):
        check_entry(entry, "chronos2", SOURCE, SOURCE_KEYS)


@pytest.mark.parametrize("source, message", [
    ({"model_id": "some/model"}, "revision.*missing"),
    ({**SOURCE, "context_length": 512}, "context_length.*unknown"),
])
def test_a_model_section_with_a_missing_or_an_unknown_key_is_refused(source, message):
    with pytest.raises(ValueError, match=message):
        check_entry(ENTRY, "chronos2", source, SOURCE_KEYS)


def test_the_message_of_a_refused_entry_names_its_family_and_is_one_line():
    with pytest.raises(ValueError) as refused:
        check_entry({"family": "chronos2", "days": 28}, "chronos2", SOURCE, SOURCE_KEYS)

    message = str(refused.value)
    assert "chronos2" in message
    assert "context_days" in message and "days" in message
    assert "\n" not in message


def test_source_settings_are_the_section_of_the_family():
    config = {"foundation_models": {"chronos2": SOURCE, "timesfm25": {"model_id": "other"}}}

    assert source_settings(config, "chronos2") == SOURCE


@pytest.mark.parametrize("config", [{}, {"foundation_models": {"timesfm25": SOURCE}}])
def test_a_config_without_the_section_of_the_family_is_refused(config):
    with pytest.raises(ValueError, match="foundation_models.chronos2"):
        source_settings(config, "chronos2")
