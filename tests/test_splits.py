"""Tests for the train loader and the split ranges.

They use small synthetic tables, a temporary folder and no network.
"""

from pathlib import Path

import pandas as pd
import pytest

from epf.config import load_config
from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.data.splits import keep_train, load_train, split_range, train_cut
from epf.data.validate import HOURLY, QUARTER_HOUR, table_path

MARKET_TZ = "Europe/Berlin"


def market_time(text: str) -> pd.Timestamp:
    """A timestamp in market time. A date alone means 00:00 on that day."""
    return pd.Timestamp(text, tz=MARKET_TZ)


def project_config(tmp_path, validation_start: str) -> dict:
    """A config with the processed folder under tmp_path."""
    return {
        "market": {"timezone": MARKET_TZ},
        "splits": {"validation_start": validation_start},
        "paths": {"processed": str(tmp_path / "processed")},
    }


def save_table(config: dict, table_name: str, index: pd.DatetimeIndex) -> None:
    """Write a table with a running number as its price."""
    path = table_path(Path(config["paths"]["processed"]), table_name, "ES")
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"price": range(len(index))}, index=index).to_parquet(path)


def test_train_cut_is_midnight_in_market_time_on_the_first_validation_day(tmp_path):
    cut = train_cut(project_config(tmp_path, "2026-06-23"))

    assert cut == pd.Timestamp("2026-06-22 22:00", tz="UTC")


@pytest.mark.parametrize("table_name, make_index, rows, last", [
    (HOURLY, hourly_index, 48, "2026-06-22 23:00"),
    (QUARTER_HOUR, quarter_hour_index, 192, "2026-06-22 23:45"),
])
def test_load_train_has_no_row_at_or_after_midnight_market_time_on_validation_start(
        tmp_path, table_name, make_index, rows, last):
    config = project_config(tmp_path, "2026-06-23")
    save_table(config, table_name, make_index(market_time("2026-06-21"), market_time("2026-06-25")))

    train = load_train(config, table_name, "ES")

    assert len(train) == rows
    assert train.index.max() == market_time(last)
    assert (train.index < market_time("2026-06-23")).all()
    assert str(train.index.tz) == "UTC"


def test_keep_train_keeps_all_25_hours_of_a_clock_change_day_before_the_cut():
    index = hourly_index(market_time("2026-10-25"), market_time("2026-10-27"))
    table = pd.DataFrame({"price": 1.0}, index=index)

    train = keep_train(table, market_time("2026-10-26"))

    assert len(train) == 25


def test_keep_train_refuses_a_table_whose_index_is_not_utc():
    index = hourly_index(market_time("2026-06-22"), market_time("2026-06-24"))
    table = pd.DataFrame({"price": 1.0}, index=index.tz_convert(MARKET_TZ))

    with pytest.raises(ValueError):
        keep_train(table, market_time("2026-06-23"))


def split_config() -> dict:
    """A config with the dates that split_range reads."""
    return {
        "market": {"timezone": MARKET_TZ},
        "data": {"end": "2026-11-19"},
        "splits": {"validation_start": "2026-06-23", "test_start": "2026-08-22"},
    }


def test_split_range_of_validation_runs_from_validation_start_to_test_start():
    start, end = split_range(split_config(), "validation")

    assert start == market_time("2026-06-23")
    assert end == market_time("2026-08-22")


def test_split_range_of_test_ends_at_midnight_after_the_last_delivery_day():
    start, end = split_range(split_config(), "test")

    assert start == market_time("2026-08-22")
    assert end == market_time("2026-11-20")


@pytest.mark.parametrize("split", ["train", "all", ""])
def test_split_range_refuses_any_other_split(split):
    with pytest.raises(ValueError, match="split"):
        split_range(split_config(), split)


def test_project_config_splits_hold_the_configured_number_of_delivery_days():
    config = load_config()

    for split, length in (("validation", "validation_days"), ("test", "test_days")):
        days = delivery_days(*split_range(config, split))

        assert len(days) == config["splits"][length]
