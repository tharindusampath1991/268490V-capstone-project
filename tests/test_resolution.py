"""Tests for the index check, the price resolution split and the covariate alignment."""

import pandas as pd
import pytest

from epf.data.market_time import expected_price_index, hourly_index, quarter_hour_index
from epf.data.resolution import (
    align_to_hours,
    align_to_quarter_hours,
    check_utc_index,
    hourly_prices,
    quarter_hour_prices,
)

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


def hourly_frame(day: str, next_day: str, column: str = "Forecasted Load") -> pd.DataFrame:
    """One value per hour of [day, next_day): 0.0, 4.0, 8.0 and so on."""
    index = hourly_index(market_time(day), market_time(next_day))
    return pd.DataFrame({column: [4.0 * step for step in range(len(index))]}, index=index)


def quarter_hour_frame(day: str, next_day: str, column: str = "Forecasted Load") -> pd.DataFrame:
    """One value per quarter-hour of [day, next_day): 0.0, 1.0, 2.0 and so on."""
    index = quarter_hour_index(market_time(day), market_time(next_day))
    return pd.DataFrame({column: range(len(index))}, index=index, dtype="float64")


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


@pytest.mark.parametrize("day, next_day, hours", [
    ("2025-03-30", "2025-03-31", 23),
    ("2024-10-27", "2024-10-28", 25),
    ("2026-10-25", "2026-10-26", 25),
])
def test_align_to_hours_keeps_hourly_values_on_a_clock_change_day(day, next_day, hours):
    data = hourly_frame(day, next_day)

    aligned = align_to_hours(data)

    assert len(aligned) == hours
    assert aligned.index.equals(data.index)
    assert aligned["Forecasted Load"].tolist() == data["Forecasted Load"].tolist()


@pytest.mark.parametrize("day, next_day, hours", [
    ("2026-03-29", "2026-03-30", 23),    # 92 quarter-hours
    ("2026-10-25", "2026-10-26", 25),    # 100 quarter-hours
])
def test_align_to_hours_takes_the_mean_of_four_quarter_hour_values(day, next_day, hours):
    data = quarter_hour_frame(day, next_day)

    aligned = align_to_hours(data)

    assert len(data) == 4 * hours
    assert aligned.index.equals(hourly_index(market_time(day), market_time(next_day)))
    assert aligned["Forecasted Load"].tolist() == [4 * hour + 1.5 for hour in range(hours)]


def test_align_to_hours_handles_a_series_that_changes_resolution():
    data = pd.concat([hourly_frame("2025-09-30", "2025-10-01"),
                      quarter_hour_frame("2025-10-01", "2025-10-02")])

    aligned = align_to_hours(data)

    assert aligned.index.equals(hourly_index(market_time("2025-09-30"), market_time("2025-10-02")))
    assert aligned["Forecasted Load"].iloc[:24].tolist() == [4.0 * step for step in range(24)]
    assert aligned["Forecasted Load"].iloc[24:].tolist() == [4 * hour + 1.5 for hour in range(24)]


def test_align_to_hours_treats_each_column_by_its_own_resolution():
    wind = quarter_hour_frame("2026-10-25", "2026-10-26", "Wind Onshore")
    solar = hourly_frame("2026-10-25", "2026-10-26", "Solar")
    data = wind.join(solar)

    aligned = align_to_hours(data)

    assert aligned["Wind Onshore"].tolist() == [4 * hour + 1.5 for hour in range(25)]
    assert aligned["Solar"].tolist() == solar["Solar"].tolist()


def test_align_to_hours_leaves_an_hour_with_three_values_empty():
    data = quarter_hour_frame("2026-10-25", "2026-10-26").drop(
        pd.Timestamp("2026-10-25 10:30", tz="UTC"))

    aligned = align_to_hours(data)

    assert len(aligned) == 25
    assert aligned["Forecasted Load"].isna().sum() == 1
    assert pd.isna(aligned.loc[pd.Timestamp("2026-10-25 10:00", tz="UTC"), "Forecasted Load"])


def test_align_to_hours_leaves_an_hour_empty_when_its_only_value_is_not_on_the_hour():
    data = pd.DataFrame({"Forecasted Load": [7.0]},
                        index=pd.DatetimeIndex([pd.Timestamp("2026-10-25 10:15", tz="UTC")]))

    aligned = align_to_hours(data)

    assert aligned.index.tolist() == [pd.Timestamp("2026-10-25 10:00", tz="UTC")]
    assert aligned["Forecasted Load"].isna().all()


def test_align_to_hours_reads_a_lone_value_on_the_hour_as_an_hourly_value():
    hour = pd.Timestamp("2026-10-25 10:00", tz="UTC")
    data = quarter_hour_frame("2026-10-25", "2026-10-26")
    data[(data.index.floor("h") == hour) & (data.index != hour)] = float("nan")

    aligned = align_to_hours(data)

    assert aligned.loc[hour, "Forecasted Load"] == data.loc[hour, "Forecasted Load"]
    assert aligned["Forecasted Load"].notna().all()


def test_align_to_hours_rejects_an_unsorted_index():
    data = hourly_frame("2026-10-25", "2026-10-26").iloc[::-1]

    with pytest.raises(ValueError, match="sorted"):
        align_to_hours(data)


@pytest.mark.parametrize("day, next_day, quarter_hours", [
    ("2026-03-29", "2026-03-30", 92),
    ("2026-10-25", "2026-10-26", 100),
])
def test_align_to_quarter_hours_repeats_an_hourly_value_on_its_four_quarter_hours(
        day, next_day, quarter_hours):
    data = hourly_frame(day, next_day)

    aligned = align_to_quarter_hours(data)

    assert aligned.index.equals(quarter_hour_index(market_time(day), market_time(next_day)))
    assert len(aligned) == quarter_hours
    # Hour k has the value 4k. It is repeated, not interpolated towards 4k + 4.
    assert aligned["Forecasted Load"].tolist() == [4.0 * (step // 4) for step in range(quarter_hours)]


@pytest.mark.parametrize("day, next_day, quarter_hours", [
    ("2026-03-29", "2026-03-30", 92),
    ("2026-10-25", "2026-10-26", 100),
])
def test_align_to_quarter_hours_keeps_quarter_hour_values(day, next_day, quarter_hours):
    data = quarter_hour_frame(day, next_day)

    aligned = align_to_quarter_hours(data)

    assert len(aligned) == quarter_hours
    assert aligned.index.equals(data.index)
    assert aligned["Forecasted Load"].tolist() == data["Forecasted Load"].tolist()


def test_align_to_quarter_hours_treats_each_column_by_its_own_resolution():
    wind = quarter_hour_frame("2026-10-25", "2026-10-26", "Wind Onshore")
    solar = hourly_frame("2026-10-25", "2026-10-26", "Solar")
    data = wind.join(solar)

    aligned = align_to_quarter_hours(data)

    assert aligned["Wind Onshore"].tolist() == wind["Wind Onshore"].tolist()
    assert aligned["Solar"].tolist() == [4.0 * (step // 4) for step in range(100)]


def test_align_to_quarter_hours_handles_a_series_that_changes_resolution():
    data = pd.concat([hourly_frame("2025-09-30", "2025-10-01"),
                      quarter_hour_frame("2025-10-01", "2025-10-02")])

    aligned = align_to_quarter_hours(data)

    assert aligned.index.equals(
        quarter_hour_index(market_time("2025-09-30"), market_time("2025-10-02")))
    assert aligned["Forecasted Load"].iloc[:96].tolist() == [4.0 * (step // 4) for step in range(96)]
    assert aligned["Forecasted Load"].iloc[96:].tolist() == [float(step) for step in range(96)]


def test_align_to_quarter_hours_leaves_a_missing_quarter_hour_empty():
    gap = pd.Timestamp("2026-10-25 10:30", tz="UTC")
    data = quarter_hour_frame("2026-10-25", "2026-10-26").drop(gap)

    aligned = align_to_quarter_hours(data)

    assert len(aligned) == 100
    assert aligned["Forecasted Load"].isna().sum() == 1
    assert pd.isna(aligned.loc[gap, "Forecasted Load"])


def test_align_to_quarter_hours_does_not_repeat_a_value_that_is_not_on_the_hour():
    data = pd.DataFrame({"Forecasted Load": [7.0]},
                        index=pd.DatetimeIndex([pd.Timestamp("2026-10-25 10:15", tz="UTC")]))

    aligned = align_to_quarter_hours(data)

    assert len(aligned) == 4
    assert aligned["Forecasted Load"].notna().sum() == 1
    assert aligned.loc[pd.Timestamp("2026-10-25 10:15", tz="UTC"), "Forecasted Load"] == 7.0


def test_align_to_quarter_hours_repeats_a_lone_value_on_the_hour_over_empty_rows():
    hour = pd.Timestamp("2026-10-25 10:00", tz="UTC")
    data = quarter_hour_frame("2026-10-25", "2026-10-26")
    in_hour = data.index.floor("h") == hour
    data[in_hour & (data.index != hour)] = float("nan")

    aligned = align_to_quarter_hours(data)

    assert aligned.loc[in_hour, "Forecasted Load"].tolist() == [data.loc[hour, "Forecasted Load"]] * 4


def test_align_to_quarter_hours_rejects_a_repeated_timestamp():
    data = hourly_frame("2026-10-25", "2026-10-26")
    repeated = pd.concat([data, data.iloc[-1:]])

    with pytest.raises(ValueError, match="repeated"):
        align_to_quarter_hours(repeated)


def test_alignment_returns_no_rows_for_a_download_without_data():
    no_data = pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"))

    assert align_to_hours(no_data).empty
    assert align_to_quarter_hours(no_data).empty
