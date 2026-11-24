"""Tests for the command that writes the EDA 2 figures.

They use small synthetic tables, a temporary folder and no data files. The
holiday tests call the `holidays` package for Germany and France in 2025.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")   # draws to memory, so no window opens

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import hourly_index, quarter_hour_index
from epf.data.validate import HOURLY, QUARTER_HOUR, table_path
from epf.eda import driver_stats as stats
from epf.eda.driver_figures import (
    CORE,
    EXTRA,
    FIGURES,
    holidays,
    load_tables,
    negative_spike_by_residual,
    price_vs_drivers,
    quarter_hour_spread,
    regime,
    run,
    solar_midday,
    sweden,
)

MARKET_TZ = "Europe/Berlin"
TRAIN_START = "2025-01-01"
VALIDATION_START = "2025-06-11"
TABLE_END = "2025-06-21"
TRAIN_DAYS = 161
VALIDATION_VALUE = 9999.0


@pytest.fixture(autouse=True)
def close_figures():
    """Close the figures a test opened."""
    yield
    plt.close("all")


def market_time(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz=MARKET_TZ)


def project_config(tmp_path) -> dict:
    """A config with two core zones, two extra zones and validation from 2025-06-11."""
    return {
        "market": {"timezone": MARKET_TZ},
        "splits": {"validation_start": VALIDATION_START},
        "paths": {"processed": str(tmp_path / "processed"), "figures": str(tmp_path / "figures")},
        "eda": {"spike_window_days": 28, "spike_sd": 3, "median_bins": 10, "share_bins": 5,
                "solar_day_groups": 3, "regime_factor": 2, "holiday_window_days": 7,
                "regional_share_edges": [0.25, 0.5], "nordic_flow_based_start": "2025-04-01"},
        "zones": [{"key": "XX", "holiday_country": "SE", "group": "extra",
                   "holiday_categories": ["public", "de_facto"]},
                  {"key": "YY", "holiday_country": "SE", "group": "extra",
                   "holiday_categories": ["public", "de_facto"]},
                  {"key": "AA", "holiday_country": "DE", "group": "core"},
                  {"key": "BB", "holiday_country": "FR", "group": "core"}],
    }


def hourly_table() -> pd.DataFrame:
    """A price that follows the residual load, is 400 higher in March and dips below zero.

    The load forecast is empty in one hour and the solar forecast in another.
    From the validation start every value is VALIDATION_VALUE.
    """
    index = hourly_index(market_time(TRAIN_START), market_time(TABLE_END))
    step = np.arange(len(index))
    load = 5000.0 + 1000.0 * np.sin(step * 2 * np.pi / 24)
    wind = 1500.0 + 1000.0 * np.sin(step * 2 * np.pi / 170)
    daylight = np.clip(2000.0 * np.sin(step * 2 * np.pi / 24 - 2.0), 0.0, None)
    solar = daylight * (1 + step / len(step))
    price = (load - wind - solar) / 50.0 - 30.0
    price[index.tz_convert(MARKET_TZ).month == 3] += 400.0
    table = pd.DataFrame({"price": price, "load_forecast": load, "wind_onshore_forecast": wind,
                          "solar_forecast": solar}, index=index)
    table.iloc[5, table.columns.get_loc("load_forecast")] = np.nan
    table.iloc[100, table.columns.get_loc("solar_forecast")] = np.nan
    table[index >= market_time(VALIDATION_START)] = VALIDATION_VALUE
    return table


def quarter_hour_table() -> pd.DataFrame:
    """A 15-minute price that rises by 5 with every quarter-hour of its hour."""
    index = quarter_hour_index(market_time(TRAIN_START), market_time(TABLE_END))
    step = np.arange(len(index))
    price = 50.0 + 20.0 * np.sin(step * 2 * np.pi / 96) + 5.0 * (step % 4)
    table = pd.DataFrame({"price": price}, index=index)
    table[index >= market_time(VALIDATION_START)] = VALIDATION_VALUE
    return table


def save_table(config: dict, name: str, zone_key: str, table: pd.DataFrame) -> None:
    """Write one processed table of one zone."""
    path = table_path(Path(config["paths"]["processed"]), name, zone_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(path)


def save_tables(config: dict, zone_keys: list[str]) -> None:
    """Write the hourly and the 15-minute table of every given zone."""
    for name, table in ((HOURLY, hourly_table()), (QUARTER_HOUR, quarter_hour_table())):
        for zone_key in zone_keys:
            save_table(config, name, zone_key, table)


def save_extra_tables(config: dict) -> None:
    """Write the hourly tables of the extra zones XX and YY, which have no solar forecast.

    YY has the price of XX until 2025-03-31 and a price 2 higher from 2025-04-01.
    """
    table = hourly_table().drop(columns="solar_forecast")
    save_table(config, HOURLY, "XX", table)
    other = table.copy()
    train_from_april = ((other.index >= market_time("2025-04-01"))
                        & (other.index < market_time(VALIDATION_START)))
    other.loc[train_from_april, "price"] += 2.0
    save_table(config, HOURLY, "YY", other)


@pytest.fixture
def config(tmp_path) -> dict:
    """The test config with the tables of the two core zones saved."""
    made = project_config(tmp_path)
    save_tables(made, ["AA", "BB"])                # no file for the extra zones
    return made


def test_load_tables_reads_the_zones_of_one_group_and_train_days_only(config):
    tables = load_tables(config, HOURLY, CORE)

    assert list(tables) == ["AA", "BB"]
    assert len(tables["AA"]) == TRAIN_DAYS * 24 - 1        # 2025-03-30 has 23 hours
    assert tables["AA"].max().max() < VALIDATION_VALUE


def test_run_writes_every_figure_and_prints_no_validation_value(config, tmp_path, capsys):
    save_extra_tables(config)

    run(config)

    written = sorted(path.name for path in (tmp_path / "figures").iterdir())
    assert written == sorted(f"{name}.png" for name in FIGURES)
    assert len(written) == 7
    assert all(name.startswith("eda2_") for name in written)
    printed = capsys.readouterr().out
    assert "9999" not in printed
    assert printed.index("AA") < printed.index("XX")       # core zones come first


def test_the_extra_zones_are_the_last_figure():
    groups = [group for _, _, group in FIGURES.values()]

    assert groups == [CORE] * 6 + [EXTRA]


def test_price_vs_drivers_counts_the_hours_left_out_per_input(config):
    tables, _ = price_vs_drivers(load_tables(config, HOURLY, CORE), config)

    left_out = tables["Hours left out because the input or the price is empty"]
    correlation = tables["Rank correlation of the price with each input"]
    assert left_out.loc["AA"].to_dict() == {stats.LOAD: 1, stats.WIND: 0, stats.SOLAR: 1,
                                            stats.RESIDUAL: 2}
    assert correlation.loc["AA", stats.RESIDUAL] > 0.5
    assert len(tables["Median price per bin of the residual load (bin 1 = lowest, x in MW)"]) == 10


def test_solar_midday_groups_the_days_and_leaves_out_a_day_with_an_empty_hour(config):
    tables, figure = solar_midday(load_tables(config, HOURLY, CORE), config)

    days = tables["Delivery days per group of the daily solar forecast (group 1 = least solar)"]
    counted = days.loc["AA", ["days_group_1", "days_group_2", "days_group_3"]].sum()
    assert days.loc["AA", "days_left_out"] == 1
    assert counted == TRAIN_DAYS - 1
    assert len(figure.axes[0].get_lines()) == 4            # three groups and the zero line


def test_negative_spike_by_residual_reads_the_bins_from_the_config(config):
    tables, _ = negative_spike_by_residual(load_tables(config, HOURLY, CORE), config)

    negative = tables["Hours with a negative price per bin of the residual load (bin 1 = lowest)"]
    left_out = tables["Hours left out because the residual load is empty"]
    assert list(negative.index) == [1, 2, 3, 4, 5]
    assert negative.loc[1, "AA"] > 0
    assert negative.loc[5, "AA"] == 0
    assert left_out.loc["AA", "hours"] == 2


def test_quarter_hour_spread_measures_the_spread_of_every_train_hour(config):
    tables, _ = quarter_hour_spread(load_tables(config, QUARTER_HOUR, CORE), config)

    summary = tables["Spread inside the hour: highest minus lowest quarter-hour price"]
    assert summary.loc["AA", "hours"] == TRAIN_DAYS * 24 - 1
    assert summary.loc["AA", "hours_left_out"] == 0
    assert 10.0 < summary.loc["AA", "median"] < 20.0       # three steps of 5 plus the daily wave


def test_regime_finds_the_month_with_the_raised_price(config):
    tables, _ = regime(load_tables(config, HOURLY, CORE), config)

    period = tables["High-price period, one for all zones"]
    by_period = tables["Price per period, AA"]
    assert period.loc["all zones", "first_month"] == "2025-03"
    assert period.loc["all zones", "last_month"] == "2025-03"
    assert by_period.loc[stats.DURING, "hours"] == 31 * 24 - 1
    assert by_period.loc[stats.DURING, "median"] > by_period.loc[stats.BEFORE, "median"] + 300


def test_holidays_counts_the_day_types_from_the_calendar_of_each_zone(config):
    tables, _ = holidays(load_tables(config, HOURLY, CORE), config)

    days = tables["Delivery days per day type"]
    # DE in the train period: 1 Jan, 18 and 21 Apr, 1 and 29 May and 9 Jun 2025, all Mon to Fri.
    assert days.loc["AA", stats.HOLIDAY] == 6
    # FR has 8 May too, and no Good Friday outside Alsace-Moselle.
    assert days.loc["BB", stats.HOLIDAY] == 6
    assert days.loc["AA", stats.DAY_TYPES].sum() == TRAIN_DAYS
    assert days.loc["AA", "holidays_on_a_weekend"] == 0


def test_holidays_lists_the_regional_days_the_calendar_leaves_out(config):
    tables, _ = holidays(load_tables(config, HOURLY, CORE), config)

    regional = tables["Regional holidays on Monday to Friday that count as working days"]
    # DE in the train period: 6 Jan, 8 Mar is a Saturday, 8 May (Berlin 2025) and others.
    assert regional.loc["AA", "days"] > 0
    assert regional.loc["AA", "days"] < 20
    assert 0 < regional.loc["AA", "percent_of_working_days"] < 20


def test_sweden_compares_neighbouring_zones_before_and_from_the_flow_based_start(config):
    save_extra_tables(config)

    tables, figure = sweden(load_tables(config, HOURLY, EXTRA), config)

    split = tables["Prices of XX and YY before and from 2025-04-01"]
    by_year = tables["Hours with exactly the same price in neighbouring zones, percent"]
    relative = tables["Mean price per year divided by the mean of the zones"]
    assert split.loc["before", "identical_percent"] == 100.0
    assert split.loc["from", "identical_percent"] == 0.0
    assert split.loc["from", "median_abs_difference"] == pytest.approx(2.0)
    assert list(by_year.columns) == ["XX = YY"]
    assert 0.0 < by_year.loc[2025, "XX = YY"] < 100.0
    assert relative.loc[2025, "XX"] < 1.0 < relative.loc[2025, "YY"]
    assert len(figure.axes) == 3


def test_sweden_leaves_out_the_solar_forecast_the_zones_do_not_have(config):
    save_extra_tables(config)

    tables, _ = sweden(load_tables(config, HOURLY, EXTRA), config)

    correlation = tables["Rank correlation of the price with each input"]
    assert list(correlation.columns) == [stats.LOAD, stats.WIND, stats.RESIDUAL]
    assert correlation.loc["XX", stats.RESIDUAL] > 0.5
