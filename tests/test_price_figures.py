"""Tests for the command that writes the price figures.

They use small synthetic tables, a temporary folder and no data files.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")   # draws to memory, so no window opens

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import hourly_index
from epf.data.validate import HOURLY, table_path
from epf.eda.price_figures import FIGURES, load_core_prices, negative_prices, run, spikes

MARKET_TZ = "Europe/Berlin"
VALIDATION_PRICE = 9999.0


@pytest.fixture(autouse=True)
def close_figures():
    """Close the figures a test opened."""
    yield
    plt.close("all")


def project_config(tmp_path) -> dict:
    """A config with one core zone, one extra zone and validation from 2025-03-12."""
    return {
        "market": {"timezone": MARKET_TZ},
        "splits": {"validation_start": "2025-03-12"},
        "paths": {"processed": str(tmp_path / "processed"), "figures": str(tmp_path / "figures")},
        "eda": {"spike_window_days": 28, "spike_sd": 3},
        "zones": [{"key": "XX", "holiday_country": "PL", "group": "extra"},
                  {"key": "AA", "holiday_country": "DE", "group": "core"}],
    }


def save_hourly(config: dict, zone_key: str) -> None:
    """Write 80 days of prices: a daily wave for 70 train days, then VALIDATION_PRICE."""
    index = hourly_index(pd.Timestamp("2025-01-01", tz=MARKET_TZ),
                         pd.Timestamp("2025-03-22", tz=MARKET_TZ))
    price = pd.Series(30.0 + 40.0 * np.sin(np.arange(len(index)) * 2 * np.pi / 24), index=index)
    price[index >= pd.Timestamp("2025-03-12", tz=MARKET_TZ)] = VALIDATION_PRICE
    path = table_path(Path(config["paths"]["processed"]), HOURLY, zone_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"price": price}).to_parquet(path)


def test_load_core_prices_reads_core_zones_and_train_days_only(tmp_path):
    config = project_config(tmp_path)
    save_hourly(config, "AA")           # no file for the extra zone XX

    prices = load_core_prices(config)

    assert list(prices) == ["AA"]
    assert len(prices["AA"]) == 70 * 24
    assert prices["AA"].max() < VALIDATION_PRICE


def test_run_writes_every_figure_and_prints_no_validation_price(tmp_path, capsys):
    config = project_config(tmp_path)
    save_hourly(config, "AA")

    run(config)

    written = sorted(path.name for path in (tmp_path / "figures").iterdir())
    assert written == sorted(f"{name}.png" for name in FIGURES)
    assert len(written) == 6
    printed = capsys.readouterr().out
    assert "AA" in printed
    assert "XX" not in printed
    assert "9999" not in printed


def test_spikes_reads_the_window_and_the_standard_deviations_from_the_config(tmp_path):
    config = project_config(tmp_path)
    save_hourly(config, "AA")
    prices = load_core_prices(config)

    tables, _ = spikes(prices, config)

    assert tables["Summary"].loc["AA", "hours_judged"] == 70 * 24 - 28 * 24


def test_negative_prices_gives_the_month_panel_as_the_mean_per_year(tmp_path):
    config = project_config(tmp_path)
    save_hourly(config, "AA")
    prices = load_core_prices(config)

    tables, figure = negative_prices(prices, config)

    hours = tables["Hours per month"]["AA"]
    years = tables["Years in which the month has a judged hour"]["AA"]
    means = tables["Mean hours per year, by month"]["AA"]
    assert years.tolist() == [1, 1, 1] + [0] * 9          # January to March 2025
    assert hours[1] > 0
    assert means[1] == hours[1] / 1
    assert means.iloc[3:].isna().all()
    month_panel = figure.axes[1]                            # first zone, second column
    assert month_panel.get_title() == "Mean hours per year, by month"
