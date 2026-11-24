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
from epf.eda import spread_stats
from epf.eda.driver_plots import (
    plot_group_profiles,
    plot_price_vs_inputs,
    plot_quarter_hours,
    plot_regime,
    plot_shares_by_bin,
    plot_sweden,
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
    panels = np.array(figure.axes[:8]).reshape(2, 4)       # two zones, four inputs
    assert panels[0][0].get_ylabel().startswith("AA")
    assert panels[1][0].get_ylabel().startswith("BB")
    assert panels[0][2].axison                             # AA has a solar forecast
    assert not panels[1][2].axison                         # BB has none


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
    panels = np.array(figure.axes).reshape(2, 2)           # two zones, two kinds of flag
    assert [ax.get_ylabel() for ax in panels[:, 0]] == ["AA", "BB"]
    assert [ax.get_title() for ax in panels[0]] == ["Low", "High"]


def test_plot_quarter_hours_writes_a_png(tmp_path):
    index = quarter_hour_index(START, END)
    step = np.arange(len(index))
    price = pd.Series(50.0 + 20.0 * np.sin(step * 2 * np.pi / 96) + 5.0 * (step % 4), index=index)
    spreads = {"AA": hour_profile(spread_stats.hour_spread(price), MARKET_TZ)}
    differences = spread_stats.quarter_differences(price)
    quarters = {"AA": spread_stats.quarter_profile(differences, MARKET_TZ)}
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
    panels = np.array(figure.axes).reshape(2, 2)           # two zones, two kinds of panel
    assert [ax.get_ylabel() for ax in panels[:, 0]] == ["AA", "BB"]
    assert len(panels[0][0].get_lines()) == 3
    assert len(panels[1][1].get_lines()) == 3


def test_plot_group_profiles_wraps_after_four_zones(drivers):
    table = drivers["AA"]
    groups = pd.Series(np.where(table[stats.WIND] > 1500.0, "high", "low"), index=table.index)
    profile = stats.hour_profile_by_group(table["price"], groups, MARKET_TZ, ["low", "high"])
    profiles = {f"Z{number}": profile for number in range(1, 8)}

    figure = plot_group_profiles(profiles, {"low": "Little wind", "high": "Much wind"},
                                 "Title", "Price")

    assert len(figure.axes) == 7
    assert figure.get_size_inches()[0] == pytest.approx(4 * 4.2)


def test_plot_sweden_writes_a_png_with_three_panels(tmp_path):
    years = [2023, 2024, 2025]
    yearly = pd.DataFrame({"N1": [10.0, 12.0, 8.0], "S1": [30.0, 40.0, 50.0]}, index=years)
    equal = pd.DataFrame({"N1 = S1": [90.0, 60.0, 3.0]}, index=years)
    index = hourly_index(START, END)
    price = pd.Series(1.0 + 0.3 * np.sin(np.arange(len(index)) * 2 * np.pi / 24), index=index)
    profiles = pd.DataFrame({"N1": hour_profile(price, MARKET_TZ)["median"],
                             "S1": hour_profile(price * 1.1, MARKET_TZ)["median"]})
    path = tmp_path / "sweden.png"

    figure = plot_sweden(yearly, equal, profiles, 2024.8, "From 2024-10-30", "Title", path)

    assert_png(path)
    assert len(figure.axes) == 3
    assert len(figure.axes[0].get_lines()) == 2
