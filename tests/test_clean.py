"""Tests for the cleaning step. They use small synthetic frames, a temporary folder and no network."""

from datetime import timedelta

import pandas as pd
import pytest

from epf.config import Zone
from epf.data.clean import (
    ENTSOE_NAMES,
    CleaningError,
    Period,
    clean_frame,
    clean_zone,
    dropped_columns,
    frozen_period,
    read_raw,
    require_complete,
    weather_names,
)
from epf.data.entsoe_cache import cached_fetch
from epf.data.market_time import (
    expected_price_index,
    hourly_index,
    quarter_hour_index,
    year_ranges,
)

MARKET_TZ = "Europe/Berlin"
SWITCH = pd.Timestamp("2025-10-01", tz=MARKET_TZ)
WEATHER_NAMES = {"temperature_2m": "temperature_2m", "run": "run"}
ES = Zone("ES", "ES", "core", weather_point={"place": "Madrid", "latitude": 40.42, "longitude": -3.70})


def market_time(text: str) -> pd.Timestamp:
    """A timestamp in market time. A date alone means 00:00 on that day."""
    return pd.Timestamp(text, tz=MARKET_TZ)


def period(first_day: str, day_after_last: str) -> Period:
    """A data period [first_day, day_after_last) whose weather starts on the first day."""
    start = market_time(first_day)
    return Period(start, market_time(day_after_last), SWITCH, weather_start=start)


def raw_prices(first_day: str, day_after_last: str) -> pd.DataFrame:
    """Raw prices for [first_day, day_after_last): the values 0.0, 1.0, 2.0 and so on."""
    index = expected_price_index(market_time(first_day), market_time(day_after_last), SWITCH)
    return pd.DataFrame({"price": range(len(index))}, index=index, dtype="float64")


def price_grid(first_day: str, day_after_last: str) -> pd.DatetimeIndex:
    """The market time units of [first_day, day_after_last)."""
    return expected_price_index(market_time(first_day), market_time(day_after_last), SWITCH)


def quarter_hour_frame(first_day: str, day_after_last: str, columns: list[str]) -> pd.DataFrame:
    """One value per quarter-hour and column: 0.0, 1.0, 2.0 and so on."""
    index = quarter_hour_index(market_time(first_day), market_time(day_after_last))
    return pd.DataFrame({column: range(len(index)) for column in columns}, index=index,
                        dtype="float64")


def weather_frame(first_day: str, day_after_last: str) -> pd.DataFrame:
    """One temperature per hour, with the run time of the day before the first day."""
    index = hourly_index(market_time(first_day), market_time(day_after_last))
    run = pd.Timestamp(first_day, tz="UTC") - timedelta(hours=24)
    return pd.DataFrame({"temperature_2m": 10.0, "run": run}, index=index)


def save(cache_dir, dataset: str, zone_key: str, frame: pd.DataFrame,
         first_day: str, day_after_last: str) -> None:
    """Save a frame in a cache folder, one file per year, as the downloaders do."""
    for year, start, end in year_ranges(market_time(first_day), market_time(day_after_last)):
        piece = frame[(frame.index >= start) & (frame.index < end)]
        cached_fetch(lambda query_start, query_end: piece, cache_dir, dataset, zone_key,
                     year, start, end)


def test_frozen_period_ends_at_midnight_after_the_last_delivery_day():
    config = {"market": {"timezone": MARKET_TZ, "quarter_hour_start": "2025-10-01"},
              "data": {"start": "2019-01-01", "end": "2026-11-19"},
              "open_meteo": {"first_run": "2024-03-14"}}

    found = frozen_period(config)

    assert found.start == market_time("2019-01-01")
    assert found.end == market_time("2026-11-20")
    assert found.quarter_hour_start == SWITCH
    assert found.weather_start == market_time("2024-03-15")


def test_frozen_period_refuses_a_config_without_a_last_delivery_day():
    config = {"market": {"timezone": MARKET_TZ, "quarter_hour_start": "2025-10-01"},
              "data": {"start": "2019-01-01", "end": None},
              "open_meteo": {"first_run": "2024-03-14"}}

    with pytest.raises(ValueError, match="data.end"):
        frozen_period(config)


def test_dropped_columns_lists_the_columns_of_one_zone():
    config = {"coverage_gate": {"drop_columns": [{"zone": "FR", "column": "Wind Offshore"},
                                                 {"zone": "SE_1", "column": "Solar"}]}}

    assert dropped_columns(config, "FR") == ["Wind Offshore"]
    assert dropped_columns(config, "ES") == []


def test_weather_names_keeps_the_configured_variables_and_the_run_time():
    config = {"open_meteo": {"variables": ["temperature_2m", "wind_speed_10m"]}}

    assert weather_names(config) == {"temperature_2m": "temperature_2m",
                                     "wind_speed_10m": "wind_speed_10m", "run": "run"}


def test_clean_frame_removes_every_value_after_the_last_delivery_day():
    raw = raw_prices("2026-11-18", "2026-11-22")
    start, end = market_time("2026-11-18"), market_time("2026-11-20")

    cleaned, counts = clean_frame(raw, start, end, price_grid("2026-11-18", "2026-11-20"),
                                  ENTSOE_NAMES)

    assert len(cleaned) == 2 * 96
    assert cleaned.index.max() == pd.Timestamp("2026-11-19 22:45", tz="UTC")
    assert counts == {"raw_values": 4 * 96, "outside_period": 2 * 96,
                      "dropped_columns": 0, "kept_values": 2 * 96}


@pytest.mark.parametrize("day, next_day, count", [
    ("2025-03-30", "2025-03-31", 23),    # clocks go forward, hourly
    ("2026-03-29", "2026-03-30", 92),    # clocks go forward, 15-minute
    ("2026-10-25", "2026-10-26", 100),   # clocks go back, 15-minute
    ("2025-10-01", "2025-10-02", 96),    # first 15-minute day
])
def test_clean_frame_keeps_every_price_of_a_special_day(day, next_day, count):
    raw = raw_prices(day, next_day)

    cleaned, _ = clean_frame(raw, market_time(day), market_time(next_day),
                             price_grid(day, next_day), ENTSOE_NAMES)

    assert len(cleaned) == count
    assert cleaned["price"].tolist() == raw["price"].tolist()


def test_clean_frame_keeps_hourly_prices_before_the_switch_and_quarter_hours_from_it():
    raw = raw_prices("2025-09-30", "2025-10-02")

    cleaned, _ = clean_frame(raw, market_time("2025-09-30"), market_time("2025-10-02"),
                             price_grid("2025-09-30", "2025-10-02"), ENTSOE_NAMES)

    assert len(cleaned) == 24 + 96


def test_clean_frame_refuses_a_repeated_timestamp():
    raw = raw_prices("2026-10-25", "2026-10-26")
    repeated = pd.concat([raw, raw.iloc[-1:]])

    with pytest.raises(CleaningError, match="repeated"):
        clean_frame(repeated, market_time("2026-10-25"), market_time("2026-10-26"),
                    price_grid("2026-10-25", "2026-10-26"), ENTSOE_NAMES)


def test_clean_frame_refuses_a_value_at_a_time_that_is_not_on_the_grid():
    raw = raw_prices("2025-01-15", "2025-01-16")
    off_grid = pd.DataFrame({"price": [1.0]}, index=[pd.Timestamp("2025-01-15 10:15", tz="UTC")])

    with pytest.raises(CleaningError, match="off the expected time grid: 1"):
        clean_frame(pd.concat([raw, off_grid]).sort_index(), market_time("2025-01-15"),
                    market_time("2025-01-16"), price_grid("2025-01-15", "2025-01-16"),
                    ENTSOE_NAMES)


def test_clean_frame_refuses_a_column_it_has_no_name_for():
    raw = quarter_hour_frame("2026-10-25", "2026-10-26", ["Wind Onshore", "Biomass"])
    start, end = market_time("2026-10-25"), market_time("2026-10-26")

    with pytest.raises(CleaningError, match="Biomass"):
        clean_frame(raw, start, end, quarter_hour_index(start, end), ENTSOE_NAMES)


def test_clean_frame_leaves_out_a_dropped_column_and_renames_the_others():
    raw = quarter_hour_frame("2026-10-25", "2026-10-26", ["Solar", "Wind Onshore", "Wind Offshore"])
    start, end = market_time("2026-10-25"), market_time("2026-10-26")

    cleaned, counts = clean_frame(raw, start, end, quarter_hour_index(start, end), ENTSOE_NAMES,
                                  dropped=["Wind Offshore"])

    assert list(cleaned.columns) == ["solar_forecast", "wind_onshore_forecast"]
    assert counts == {"raw_values": 300, "outside_period": 0,
                      "dropped_columns": 100, "kept_values": 200}


def test_clean_frame_leaves_a_gap_as_it_is():
    raw = quarter_hour_frame("2026-10-25", "2026-10-26", ["Forecasted Load"])
    raw.iloc[5] = float("nan")
    raw = raw.drop(raw.index[40])
    start, end = market_time("2026-10-25"), market_time("2026-10-26")

    cleaned, counts = clean_frame(raw, start, end, quarter_hour_index(start, end), ENTSOE_NAMES)

    assert len(cleaned) == 99
    assert cleaned["load_forecast"].isna().sum() == 1
    assert counts["kept_values"] == 98


def test_require_complete_accepts_one_price_per_market_time_unit():
    prices = raw_prices("2026-10-25", "2026-10-26")

    require_complete(prices["price"], price_grid("2026-10-25", "2026-10-26"))


def test_require_complete_refuses_a_missing_and_an_empty_price():
    prices = raw_prices("2026-10-25", "2026-10-26")
    prices.iloc[3] = float("nan")
    prices = prices.drop(prices.index[50])

    with pytest.raises(CleaningError, match="without a price: 2"):
        require_complete(prices["price"], price_grid("2026-10-25", "2026-10-26"))


def test_read_raw_joins_the_saved_years(tmp_path):
    save(tmp_path, "prices", "ES", raw_prices("2025-12-30", "2026-01-03"), "2025-12-30", "2026-01-03")

    raw = read_raw(tmp_path, "prices", "ES", market_time("2025-12-30"), market_time("2026-01-03"))

    assert len(raw) == 4 * 96
    assert raw.index.is_monotonic_increasing


def test_read_raw_refuses_a_saved_file_that_ends_before_the_period(tmp_path):
    save(tmp_path, "prices", "ES", raw_prices("2026-11-01", "2026-11-19"), "2026-11-01", "2026-11-19")

    with pytest.raises(CleaningError, match="download it again"):
        read_raw(tmp_path, "prices", "ES", market_time("2026-11-01"), market_time("2026-11-20"))


def test_clean_zone_cleans_the_five_datasets_and_counts_each_rule(tmp_path):
    first, last, after = "2026-10-24", "2026-10-26", "2026-10-28"
    save(tmp_path / "entsoe", "prices", "ES", raw_prices(first, after), first, after)
    save(tmp_path / "entsoe", "load_forecast", "ES",
         quarter_hour_frame(first, after, ["Forecasted Load"]), first, after)
    save(tmp_path / "entsoe", "wind_solar_forecast", "ES",
         quarter_hour_frame(first, after, ["Solar", "Wind Onshore"]), first, after)
    save(tmp_path / "entsoe", "actual_load", "ES",
         quarter_hour_frame(first, after, ["Actual Load"]), first, after)
    save(tmp_path / "open_meteo", "weather_forecast", "ES", weather_frame(first, after), first, after)

    cleaned, counts = clean_zone(tmp_path, ES, period(first, last), ["Solar"], WEATHER_NAMES)

    # 24 October has 96 quarter-hours and 25 October, when the clocks go back, has 100.
    assert len(cleaned["prices"]) == 196
    assert list(cleaned["wind_solar_forecast"].columns) == ["wind_onshore_forecast"]
    assert list(cleaned["weather_forecast"].columns) == ["temperature_2m", "run"]
    assert len(cleaned["weather_forecast"]) == 49
    assert counts["dataset"].tolist() == ["prices", "load_forecast", "wind_solar_forecast",
                                          "actual_load", "weather_forecast"]
    wind_solar = counts.set_index("dataset").loc["wind_solar_forecast"]
    assert wind_solar["outside_period"] == 2 * 2 * 96
    assert wind_solar["dropped_columns"] == 196
    assert wind_solar["kept_values"] == 196
    assert (counts["zone"] == "ES").all()


def test_clean_zone_names_the_zone_and_dataset_of_a_missing_price(tmp_path):
    first, after = "2026-10-24", "2026-10-26"
    prices = raw_prices(first, after)
    save(tmp_path / "entsoe", "prices", "ES", prices.drop(prices.index[7]), first, after)

    with pytest.raises(CleaningError, match="ES prices: .*without a price: 1"):
        clean_zone(tmp_path, ES, period(first, after), [], WEATHER_NAMES)


def test_clean_zone_skips_the_weather_of_a_zone_without_a_weather_point(tmp_path):
    first, after = "2026-10-24", "2026-10-26"
    save(tmp_path / "entsoe", "prices", "ES", raw_prices(first, after), first, after)
    for dataset, column in [("load_forecast", "Forecasted Load"),
                            ("wind_solar_forecast", "Wind Onshore"), ("actual_load", "Actual Load")]:
        save(tmp_path / "entsoe", dataset, "ES", quarter_hour_frame(first, after, [column]),
             first, after)

    cleaned, _ = clean_zone(tmp_path, Zone("ES", "ES", "core"), period(first, after), [],
                            WEATHER_NAMES)

    assert "weather_forecast" not in cleaned
