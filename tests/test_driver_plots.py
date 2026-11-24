"""Tests that every plot function of EDA 2 writes a PNG file.

They use small synthetic tables, a temporary folder and no data files.
"""

import matplotlib

matplotlib.use("Agg")   # draws to memory, so no window opens

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import hourly_index, quarter_hour_index
from epf.eda import driver_stats as stats
from epf.eda.driver_plots import (
    plot_group_profiles,
    plot_price_vs_inputs,
    plot_quarter_hours,
    plot_regime,
    plot_shares_by_bin,
)
from epf.eda.price_stats import hour_profile

MARKET_TZ = "Europe/Berlin"
PNG_START = b"\x89PNG"
START = pd.Timestamp("2025-01-01", tz=MARKET_TZ)
END = pd.Timestamp("2025-04-01", tz=MARKET_TZ)


def hourly_table(level: float, with_solar: bool) -> pd.DataFrame:
    """90 days of a price that follows the residual load, with a daily wave in the inputs."""
    index = hourly_index(START, END)
    step = np.arange(len(index))
    table = pd.DataFrame({
        "load_forecast": 5000.0 + 1000.0 * np.sin(step * 2 * np.pi / 24),
        "wind_onshore_forecast": 1500.0 + 1000.0 * np.sin(step * 2 * np.pi / 170),
    }, index=index)
    if with_solar:
        table["solar_forecast"] = np.clip(2000.0 * np.sin(step * 2 * np.pi / 24), 0.0, None)
    residual = table["load_forecast"] - table.drop(columns="load_forecast").sum(axis=1)
    table.insert(0, "price", level + residual / 50.0)
    return table


@pytest.fixture
def drivers() -> dict[str, pd.DataFrame]:
    """Two zones. The second has no solar forecast."""
    return {"AA": stats.driver_table(hourly_table(0.0, with_solar=True)),
            "BB": stats.driver_table(hourly_table(20.0, with_solar=False))}


@pytest.fixture(autouse=True)
def close_figures():
    """Close the figures a test opened."""
    yield
    plt.close("all")


def assert_png(path) -> None:
    assert path.read_bytes().startswith(PNG_START)


def test_plot_price_vs_inputs_writes_a_png_and_marks_a_missing_input(tmp_path, drivers):
    medians = {zone: {name: stats.binned_median(table[name], table["price"], 10)
                      for name in stats.INPUTS if name in table.columns}
               for zone, table in drivers.items()}
    path = tmp_path / "inputs.png"

    figure = plot_price_vs_inputs(drivers, medians, -50.0, 150.0, path)

    assert_png(path)
    panels = np.array(figure.axes[:8]).reshape(4, 2)       # four inputs, two zones
    assert panels[0][0].get_title() == "AA"
    assert panels[2][0].axison                             # AA has a solar forecast
    assert not panels[2][1].axison                         # BB has none


def test_plot_price_vs_inputs_writes_no_file_without_a_path(tmp_path, drivers):
    medians = {zone: {name: stats.binned_median(table[name], table["price"], 10)
                      for name in stats.INPUTS if name in table.columns}
               for zone, table in drivers.items()}

    plot_price_vs_inputs(drivers, medians, -50.0, 150.0)

    assert list(tmp_path.iterdir()) == []


def test_plot_group_profiles_writes_a_png_with_one_line_per_group(tmp_path, drivers):
    profiles = {}
    for zone, table in drivers.items():
        groups = pd.Series(np.where(table[stats.WIND] > 1500.0, "high", "low"), index=table.index)
        profiles[zone] = stats.hour_profile_by_group(table["price"], groups, MARKET_TZ,
                                                     ["low", "high"])
    path = tmp_path / "profiles.png"

    figure = plot_group_profiles(profiles, {"low": "Little wind", "high": "Much wind"},
                                 "Title", "Price", path, note="A note.")

    assert_png(path)
    assert len(figure.axes) == 2
    assert len(figure.axes[0].get_lines()) == 2


def test_plot_shares_by_bin_writes_a_png_with_one_row_per_flag(tmp_path, drivers):
    shares = {}
    for zone, table in drivers.items():
        low_price = table["price"] < table["price"].quantile(0.1)
        high_price = table["price"] > table["price"].quantile(0.9)
        shares[zone] = {"Low": stats.share_by_bin(table[stats.RESIDUAL], low_price, 10),
                        "High": stats.share_by_bin(table[stats.RESIDUAL], high_price, 10)}
    path = tmp_path / "shares.png"

    figure = plot_shares_by_bin(shares, "Title", "Tenth of the residual load", path)

    assert_png(path)
    assert len(figure.axes) == 4
    assert figure.axes[0].get_ylabel() == "Low"


def test_plot_quarter_hours_writes_a_png(tmp_path):
    index = quarter_hour_index(START, END)
    step = np.arange(len(index))
    price = pd.Series(50.0 + 20.0 * np.sin(step * 2 * np.pi / 96) + 5.0 * (step % 4), index=index)
    spreads = {"AA": hour_profile(stats.hour_spread(price), MARKET_TZ)}
    quarters = {"AA": stats.quarter_profile(stats.quarter_differences(price), MARKET_TZ)}
    path = tmp_path / "quarters.png"

    figure = plot_quarter_hours(spreads, quarters, path)

    assert_png(path)
    assert len(figure.axes) == 2
    assert len(figure.axes[1].get_lines()) == 5            # four quarter-hours and the zero line


def test_plot_regime_writes_a_png(tmp_path, drivers):
    profiles, medians = {}, {}
    for zone, table in drivers.items():
        labels = stats.period_labels(table.index, "2025-02", "2025-02", MARKET_TZ)
        profiles[zone] = stats.hour_profile_by_group(table["price"], labels, MARKET_TZ,
                                                     stats.PERIODS)
        medians[zone] = stats.binned_median_by_group(table[stats.RESIDUAL], table["price"],
                                                     labels, 10, stats.PERIODS)
    path = tmp_path / "regime.png"

    figure = plot_regime(profiles, medians, {name: name for name in stats.PERIODS}, path)

    assert_png(path)
    assert len(figure.axes) == 4
    assert len(figure.axes[0].get_lines()) == 3

