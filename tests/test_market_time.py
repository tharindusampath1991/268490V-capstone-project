"""Tests for the market time helpers: delivery days, clock changes and the 15-minute switch."""

import pandas as pd
import pytest

from epf.data.market_time import (
    data_range,
    expected_price_index,
    hourly_index,
    native_resolution,
    quarter_hour_index,
    year_ranges,
)

MARKET_TZ = "Europe/Berlin"
SWITCH = pd.Timestamp("2025-10-01", tz=MARKET_TZ)


def market_time(text: str) -> pd.Timestamp:
    """A timestamp in market time. A date alone means 00:00 on that day."""
    return pd.Timestamp(text, tz=MARKET_TZ)


@pytest.mark.parametrize("day, next_day, count", [
    ("2025-01-15", "2025-01-16", 24),    # ordinary hourly day
    ("2025-03-30", "2025-03-31", 23),    # clocks go forward
    ("2024-10-27", "2024-10-28", 25),    # clocks go back
    ("2025-10-01", "2025-10-02", 96),    # first 15-minute day
    ("2026-03-29", "2026-03-30", 92),    # clocks go forward, 15-minute
    ("2026-10-25", "2026-10-26", 100),   # clocks go back, 15-minute
])
def test_expected_price_index_counts_the_market_time_units_of_a_delivery_day(day, next_day, count):
    index = expected_price_index(market_time(day), market_time(next_day), SWITCH)

    assert len(index) == count


def test_expected_price_index_changes_from_hourly_to_quarter_hourly_at_the_switch():
    index = expected_price_index(market_time("2025-09-30"), market_time("2025-10-02"), SWITCH)

    assert len(index) == 24 + 96
    assert index[23] == pd.Timestamp("2025-09-30 21:00", tz="UTC")
    assert index[24] == pd.Timestamp("2025-09-30 22:00", tz="UTC")
    assert index[25] == pd.Timestamp("2025-09-30 22:15", tz="UTC")


def test_expected_price_index_is_in_utc():
    index = expected_price_index(market_time("2025-01-15"), market_time("2025-01-16"), SWITCH)

    assert str(index.tz) == "UTC"
    assert index[0] == pd.Timestamp("2025-01-14 23:00", tz="UTC")


def test_year_ranges_splits_a_period_at_each_new_year():
    ranges = year_ranges(market_time("2019-06-01"), market_time("2021-03-10"))

    assert ranges == [
        (2019, market_time("2019-06-01"), market_time("2020-01-01")),
        (2020, market_time("2020-01-01"), market_time("2021-01-01")),
        (2021, market_time("2021-01-01"), market_time("2021-03-10")),
    ]


def test_year_ranges_adds_no_empty_piece_when_the_period_ends_at_new_year():
    ranges = year_ranges(market_time("2019-01-01"), market_time("2020-01-01"))

    assert ranges == [(2019, market_time("2019-01-01"), market_time("2020-01-01"))]


def test_data_range_ends_today_while_data_end_is_not_frozen():
    config = {"market": {"timezone": MARKET_TZ}, "data": {"start": "2019-01-01", "end": None}}

    start, end = data_range(config, today=market_time("2026-11-20"))

    assert start == market_time("2019-01-01")
    assert end == market_time("2026-11-20")


def test_data_range_includes_the_last_delivery_day_when_data_end_is_set():
    config = {"market": {"timezone": MARKET_TZ}, "data": {"start": "2019-01-01", "end": "2026-10-25"}}

    start, end = data_range(config, today=market_time("2026-11-20"))

    assert end == market_time("2026-10-26")


def test_hourly_index_has_one_utc_step_per_hour_of_a_clock_change_day():
    index = hourly_index(market_time("2026-10-25"), market_time("2026-10-26"))

    assert len(index) == 25
    assert str(index.tz) == "UTC"
    assert index[0] == pd.Timestamp("2026-10-24 22:00", tz="UTC")


@pytest.mark.parametrize("day, next_day, count", [
    ("2025-10-01", "2025-10-02", 96),    # ordinary day
    ("2026-03-29", "2026-03-30", 92),    # clocks go forward
    ("2026-10-25", "2026-10-26", 100),   # clocks go back
])
def test_quarter_hour_index_counts_the_quarter_hours_of_a_delivery_day(day, next_day, count):
    index = quarter_hour_index(market_time(day), market_time(next_day))

    assert len(index) == count
    assert str(index.tz) == "UTC"


def test_quarter_hour_index_starts_at_midnight_in_market_time():
    index = quarter_hour_index(market_time("2026-10-25"), market_time("2026-10-26"))

    assert index[0] == pd.Timestamp("2026-10-24 22:00", tz="UTC")
    assert index[1] == pd.Timestamp("2026-10-24 22:15", tz="UTC")
    assert index[-1] == pd.Timestamp("2026-10-25 22:45", tz="UTC")


@pytest.mark.parametrize("freq, expected", [("h", "60min"), ("15min", "15min")])
def test_native_resolution_names_the_most_common_step(freq, expected):
    index = pd.date_range("2025-01-01", periods=8, freq=freq, tz="UTC")

    assert native_resolution(index) == expected


def test_native_resolution_is_not_changed_by_one_gap():
    index = pd.date_range("2025-01-01", periods=8, freq="h", tz="UTC").delete(3)

    assert native_resolution(index) == "60min"


def test_native_resolution_is_a_dash_for_fewer_than_two_timestamps():
    index = pd.date_range("2025-01-01", periods=1, freq="h", tz="UTC")

    assert native_resolution(index) == "-"
