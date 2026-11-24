"""Tests that every price plot function writes a PNG file.

They use small synthetic series, a temporary folder and no data files.
"""

import matplotlib

matplotlib.use("Agg")   # draws to memory, so no window opens

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import hourly_index
from epf.eda.price_plots import (
    plot_distribution,
    plot_flag_counts,
    plot_hour_profile,
    plot_month_year,
    plot_weekday_profile,
)
from epf.eda.price_stats import (
    flag_counts,
    hour_profile,
    month_year_means,
    negative_flags,
    pooled_range,
    weekday_profile,
)

MARKET_TZ = "Europe/Berlin"
PNG_START = b"\x89PNG"


@pytest.fixture
def prices() -> dict[str, pd.Series]:
    """Two zones with 90 days of hourly prices that follow a daily wave and dip below zero."""
    index = hourly_index(pd.Timestamp("2025-01-01", tz=MARKET_TZ),
                         pd.Timestamp("2025-04-01", tz=MARKET_TZ))
    wave = 40.0 * np.sin(np.arange(len(index)) * 2 * np.pi / 24)
    return {"AA": pd.Series(30.0 + wave, index=index), "BB": pd.Series(60.0 + wave, index=index)}


@pytest.fixture(autouse=True)
def close_figures():
    """Close the figures a test opened."""
    yield
    plt.close("all")


def is_png(path) -> bool:
    """True when the file exists and starts like a PNG image."""
    return path.exists() and path.read_bytes()[:4] == PNG_START


def test_plot_distribution_writes_a_png(tmp_path, prices):
    low, high = pooled_range(prices, 0.01, 0.99)

    plot_distribution(prices, low, high, tmp_path / "distribution.png")

    assert is_png(tmp_path / "distribution.png")


def test_plot_hour_profile_writes_a_png(tmp_path, prices):
    profiles = {zone: hour_profile(price, MARKET_TZ) for zone, price in prices.items()}

    plot_hour_profile(profiles, tmp_path / "hour.png")

    assert is_png(tmp_path / "hour.png")


def test_plot_hour_profile_draws_a_day_without_hour_2(tmp_path):
    index = hourly_index(pd.Timestamp("2025-03-30", tz=MARKET_TZ),
                         pd.Timestamp("2025-03-31", tz=MARKET_TZ))
    profiles = {"AA": hour_profile(pd.Series(50.0, index=index), MARKET_TZ)}

    plot_hour_profile(profiles, tmp_path / "hour.png")

    assert is_png(tmp_path / "hour.png")


def test_plot_weekday_profile_writes_a_png(tmp_path, prices):
    profiles = {zone: weekday_profile(price, MARKET_TZ) for zone, price in prices.items()}

    plot_weekday_profile(profiles, tmp_path / "weekday.png")

    assert is_png(tmp_path / "weekday.png")


def test_plot_month_year_writes_a_png(tmp_path, prices):
    means = {zone: month_year_means(price, MARKET_TZ) for zone, price in prices.items()}

    plot_month_year(means, "2025 covers 1 Jan to 31 Mar.", tmp_path / "month_year.png")

    assert is_png(tmp_path / "month_year.png")


def test_plot_flag_counts_writes_a_png(tmp_path, prices):
    counts = {zone: flag_counts(negative_flags(price), MARKET_TZ)
              for zone, price in prices.items()}

    plot_flag_counts(counts, "Hours with a negative price", "A note.", tmp_path / "negative.png")

    assert is_png(tmp_path / "negative.png")


def seven_zones(prices: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """Seven zones with the prices of the first zone, each 5 higher than the one before."""
    first = next(iter(prices.values()))
    return {f"Z{number}": first + 5.0 * number for number in range(1, 8)}


def test_one_panel_per_zone_wraps_after_four_zones(prices):
    profiles = {zone: weekday_profile(price, MARKET_TZ)
                for zone, price in seven_zones(prices).items()}

    figure = plot_weekday_profile(profiles)

    width, height = figure.get_size_inches()
    assert len(figure.axes) == 7                           # the eighth place stays empty
    assert [ax.get_title() for ax in figure.axes] == list(profiles)
    assert width == pytest.approx(4 * 4.2)                 # four panels wide
    assert height == pytest.approx(2 * 3.8)                # two rows


def test_plot_flag_counts_draws_one_row_per_zone_and_one_column_per_count(prices):
    counts = {zone: flag_counts(negative_flags(price), MARKET_TZ)
              for zone, price in prices.items()}

    figure = plot_flag_counts(counts, "Hours with a negative price", "A note.")

    panels = np.array(figure.axes).reshape(2, 3)           # two zones, three kinds of count
    assert [ax.get_ylabel() for ax in panels[:, 0]] == ["AA", "BB"]
    assert [ax.get_title() for ax in panels[0]] == [
        "Hours per year", "Mean hours per year, by month", "Hours per hour of day"]


def test_a_plot_function_writes_no_file_without_a_path(tmp_path, prices, monkeypatch):
    monkeypatch.chdir(tmp_path)
    profiles = {zone: weekday_profile(price, MARKET_TZ) for zone, price in prices.items()}

    figure = plot_weekday_profile(profiles)

    assert len(figure.axes) == 2
    assert list(tmp_path.iterdir()) == []
