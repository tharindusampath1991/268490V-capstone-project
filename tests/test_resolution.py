"""Tests for the index check, the price resolution split and the covariate alignment."""

import pandas as pd
import pytest

from epf.data.market_time import expected_price_index, hourly_index, quarter_hour_index
from epf.data.resolution import check_utc_index, hourly_prices, quarter_hour_prices

MARKET_TZ = "Europe/Berlin"
SWITCH = pd.Timestamp("2025-10-01", tz=MARKET_TZ)
HOURS = pd.date_range("2025-01-14 23:00", periods=4, freq="h", tz="UTC")


def market_time(text: str) -> pd.Timestamp:
    """A timestamp in market time. A date alone means 00:00 on that day."""
    return pd.Timestamp(text, tz=MARKET_TZ)


def raw_prices(first_day: str, day_after_last: str) -> pd.Series:
    """Raw prices for [first_day, day_after_last): the values 0.0, 1.0, 2.0 and so on."""
    index = expected_price_index(market_time(first_day), market_time(day_after_last), SWITCH)
    return pd.Series(range(len(index)), index=index, dtype="float64", name="price")


def test_check_utc_index_accepts_a_sorted_utc_index_without_repeats():
    check_utc_index(pd.Series(1.0, index=HOURS))
    check_utc_index(pd.DataFrame({"price": 1.0}, index=HOURS))


def test_check_utc_index_rejects_an_index_without_a_time_zone():
    naive = pd.Series(1.0, index=HOURS.tz_localize(None))

    with pytest.raises(ValueError, match="UTC"):
        check_utc_index(naive)


def test_check_utc_index_rejects_an_index_in_local_time():
    local = pd.Series(1.0, index=HOURS.tz_convert("Europe/Berlin"))

    with pytest.raises(ValueError, match="UTC"):
        check_utc_index(local)


def test_check_utc_index_rejects_an_index_that_is_not_a_time_index():
    with pytest.raises(ValueError, match="UTC"):
        check_utc_index(pd.Series([1.0, 2.0]))


def test_check_utc_index_rejects_an_unsorted_index():
    unsorted = pd.Series(1.0, index=HOURS[::-1])

    with pytest.raises(ValueError, match="sorted"):
        check_utc_index(unsorted)


def test_check_utc_index_rejects_a_repeated_timestamp():
    repeated = pd.Series(1.0, index=HOURS.append(HOURS[-1:]))

    with pytest.raises(ValueError, match="1 repeated"):
        check_utc_index(repeated)


def test_hourly_prices_keeps_hourly_values_before_the_switch():
    prices = raw_prices("2025-09-29", "2025-10-01")

    hourly = hourly_prices(prices, SWITCH)

    assert hourly.index.equals(prices.index)
    assert hourly.tolist() == prices.tolist()


def test_hourly_prices_takes_the_mean_of_four_quarter_hours_from_the_switch_day():
    prices = raw_prices("2025-09-30", "2025-10-02")

    hourly = hourly_prices(prices, SWITCH)

    assert hourly.index.equals(hourly_index(market_time("2025-09-30"), market_time("2025-10-02")))
    assert hourly.iloc[:24].tolist() == prices.iloc[:24].tolist()
    # The first hour of 1 Oct holds the raw values 24, 25, 26 and 27.
    assert hourly.loc[pd.Timestamp("2025-09-30 22:00", tz="UTC")] == 25.5
    assert hourly.iloc[-1] == prices.iloc[-4:].mean()


@pytest.mark.parametrize("day, next_day, hours", [
    ("2026-03-29", "2026-03-30", 23),    # clocks go forward: 92 quarter-hours
    ("2026-10-25", "2026-10-26", 25),    # clocks go back: 100 quarter-hours
])
def test_hourly_prices_gives_one_mean_per_hour_of_a_clock_change_day(day, next_day, hours):
    prices = raw_prices(day, next_day)

    hourly = hourly_prices(prices, SWITCH)

    assert len(prices) == 4 * hours
    assert hourly.index.equals(hourly_index(market_time(day), market_time(next_day)))
    # Hour k holds the raw values 4k, 4k+1, 4k+2 and 4k+3.
    assert hourly.tolist() == [4 * hour + 1.5 for hour in range(hours)]


def test_hourly_prices_leaves_an_hour_empty_when_a_quarter_hour_is_absent():
    prices = raw_prices("2026-10-25", "2026-10-26").drop(
        pd.Timestamp("2026-10-25 10:30", tz="UTC"))

    hourly = hourly_prices(prices, SWITCH)

    assert len(hourly) == 25
    assert hourly.isna().sum() == 1
    assert pd.isna(hourly.loc[pd.Timestamp("2026-10-25 10:00", tz="UTC")])


def test_hourly_prices_leaves_an_hour_empty_when_a_quarter_hour_has_no_value():
    prices = raw_prices("2026-10-25", "2026-10-26")
    prices.loc[pd.Timestamp("2026-10-25 10:30", tz="UTC")] = float("nan")

    hourly = hourly_prices(prices, SWITCH)

    assert hourly.isna().sum() == 1
    assert pd.isna(hourly.loc[pd.Timestamp("2026-10-25 10:00", tz="UTC")])


def test_hourly_prices_does_not_invent_a_value_for_an_empty_hourly_price():
    prices = raw_prices("2025-09-30", "2025-10-01")
    prices.iloc[5] = float("nan")

    hourly = hourly_prices(prices, SWITCH)

    assert len(hourly) == 24
    assert pd.isna(hourly.iloc[5])


def test_hourly_prices_rejects_an_index_in_local_time():
    prices = raw_prices("2025-09-30", "2025-10-01").tz_convert(MARKET_TZ)

    with pytest.raises(ValueError, match="UTC"):
        hourly_prices(prices, SWITCH)


def test_quarter_hour_prices_keeps_only_the_values_from_the_switch_day():
    prices = raw_prices("2025-09-30", "2025-10-02")

    quarter_hourly = quarter_hour_prices(prices, SWITCH)

    assert quarter_hourly.index.equals(
        quarter_hour_index(market_time("2025-10-01"), market_time("2025-10-02")))
    assert quarter_hourly.tolist() == prices.iloc[24:].tolist()


@pytest.mark.parametrize("day, next_day, count", [
    ("2026-03-29", "2026-03-30", 92),
    ("2026-10-25", "2026-10-26", 100),
])
def test_quarter_hour_prices_keeps_every_value_of_a_clock_change_day(day, next_day, count):
    prices = raw_prices(day, next_day)

    quarter_hourly = quarter_hour_prices(prices, SWITCH)

    assert len(quarter_hourly) == count
    assert quarter_hourly.tolist() == prices.tolist()


def test_quarter_hour_prices_is_empty_before_the_switch():
    prices = raw_prices("2025-09-29", "2025-10-01")

    quarter_hourly = quarter_hour_prices(prices, SWITCH)

    assert quarter_hourly.empty
    assert str(quarter_hourly.index.tz) == "UTC"


def test_quarter_hour_prices_rejects_a_repeated_timestamp():
    prices = raw_prices("2025-10-01", "2025-10-02")
    repeated = pd.concat([prices, prices.iloc[-1:]])

    with pytest.raises(ValueError, match="repeated"):
        quarter_hour_prices(repeated, SWITCH)
