"""The figures of EDA 2, one function per kind of figure.

Every function takes numbers that epf.eda.driver_stats computed, by zone, and
draws one column of panels per zone. It returns the figure and writes a PNG
when a path is given. Prices are in EUR/MWh, forecasts are drawn in GW.
Hours are in market time.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.figure import Figure

from epf.eda.driver_stats import INPUTS, LOAD, PRICE, RESIDUAL, SOLAR, WIND
from epf.eda.price_plots import (
    BLUE,
    BLUE_LIGHT,
    BLUE_RAMP,
    INK,
    INK_SOFT,
    UNIT,
    _finish,
    _panels,
)

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # groups without an order, fixed order
ORDERED = ["#86b6ef", "#2a78d6", "#0d366b"]             # groups from low to high
CELLS = 50                                              # cells per axis of a 2D histogram
MW_PER_GW = 1000.0
PANEL_WIDTH = 4.2
INPUT_LABELS = {LOAD: "Load forecast", WIND: "Wind forecast", SOLAR: "Solar forecast",
                RESIDUAL: "Residual load"}
QUARTER_LABELS = {1: "First quarter-hour", 2: "Second", 3: "Third", 4: "Fourth"}
HOUR_LABEL = "Hour of day, market time"


def plot_price_vs_inputs(drivers: dict[str, pd.DataFrame],
                         medians: dict[str, dict[str, pd.DataFrame]], low: float, high: float,
                         path: Path | None = None) -> Figure:
    """Draw the price against every input as a 2D histogram with the median price per bin.

    Input: the table of driver_table by zone, per zone and input the table of
        binned_median, and the price range [low, high] of the panels. Every
        hour with a price and the input is counted. Hours with a price outside
        the range are not drawn. A zone without an input gets an empty panel.
    """
    names = [name for name in INPUTS if any(name in table.columns for table in drivers.values())]
    figure, axes = _panels(len(names), len(drivers), (PANEL_WIDTH * len(drivers), 2.9 * len(names)),
                           grid=False, sharey=True)
    cells = {(zone, name): _cell_counts(table[name], table[PRICE], low, high)
             for zone, table in drivers.items() for name in names if name in table.columns}
    scale = LogNorm(1, max(counts.max() for counts, _, _ in cells.values()))
    colours = LinearSegmentedColormap.from_list("blue_ramp", BLUE_RAMP)
    for row, name in enumerate(names):
        for column, zone in enumerate(drivers):
            ax = axes[row][column]
            if (zone, name) not in cells:
                ax.set_axis_off()
                ax.text(0.5, 0.5, f"No {INPUT_LABELS[name].lower()} in this zone",
                        transform=ax.transAxes, ha="center", va="center", fontsize=8,
                        color=INK_SOFT)
                continue
            counts, x_edges, y_edges = cells[zone, name]
            mesh = ax.pcolormesh(x_edges, y_edges, np.ma.masked_equal(counts.T, 0), cmap=colours,
                                 norm=scale)
            median = medians[zone][name]
            ax.plot(median["x_median"] / MW_PER_GW, median["median_price"], color=INK,
                    linewidth=1.8, label="Median price per bin")
            ax.set_ylim(low, high)
            ax.set_xlabel(f"{INPUT_LABELS[name]}, GW")
        axes[row][0].set_ylabel(f"Price, {UNIT}")
    for column, zone in enumerate(drivers):
        axes[0][column].set_title(zone)
    axes[0][0].legend(frameon=False, fontsize=8, loc="upper left")
    bar = figure.colorbar(mesh, ax=axes.ravel().tolist(), shrink=0.35, pad=0.01)
    bar.set_label("Hours per cell, log scale", color=INK_SOFT)
    bar.outline.set_visible(False)
    return _finish(figure, "Price against the day-ahead forecasts, train period", path)


def plot_group_profiles(profiles: dict[str, pd.DataFrame], labels: dict, title: str, ylabel: str,
                        path: Path | None = None, note: str = "", ordered: bool = False,
                        zero_line: bool = False) -> Figure:
    """Draw one line per group over the hour of day, one panel per zone.

    Input: per zone a table with one row per hour and one column per group,
        and the legend label of each group, in the order drawn. ordered picks
        the colours from light to dark for groups that run from low to high.
    """
    figure, axes = _panels(1, len(profiles), (PANEL_WIDTH * len(profiles), 3.8), sharey=True)
    colours = ORDERED if ordered else SERIES
    for ax, (zone, profile) in zip(axes[0], profiles.items()):
        if zero_line:
            ax.axhline(0, color=INK_SOFT, linewidth=0.8)
        _group_lines(ax, profile.index, profile, labels, colours)
        ax.set_xticks(range(0, 24, 3))
        ax.set_title(zone)
        ax.set_xlabel(HOUR_LABEL)
    axes[0][0].set_ylabel(ylabel)
    axes[0][0].legend(frameon=False, fontsize=8, loc="best")
    return _finish(figure, title, path, note)


def plot_shares_by_bin(shares: dict[str, dict[str, pd.DataFrame]], title: str, xlabel: str,
                       path: Path | None = None, note: str = "") -> Figure:
    """Draw the share of flagged hours per bin as bars, one row of panels per kind of flag.

    Input: per zone and per row label the table of share_by_bin. Each row of
        panels shares one y-axis.
    """
    rows = list(next(iter(shares.values())))
    figure, axes = _panels(len(rows), len(shares), (PANEL_WIDTH * len(shares), 2.9 * len(rows)),
                           sharey="row")
    for column, (zone, by_row) in enumerate(shares.items()):
        for row, label in enumerate(rows):
            ax, table = axes[row][column], by_row[label]
            ax.bar(table.index, table["share_percent"], width=0.7, color=BLUE)
            ax.set_xticks(table.index)
        axes[0][column].set_title(zone)
        axes[-1][column].set_xlabel(xlabel)
    for row, label in enumerate(rows):
        axes[row][0].set_ylabel(label)
    return _finish(figure, title, path, note)


def plot_quarter_hours(spreads: dict[str, pd.DataFrame], quarters: dict[str, pd.DataFrame],
                       path: Path | None = None, note: str = "") -> Figure:
    """Draw the spread inside the hour and the place of each quarter-hour in its hour.

    Input: per zone the hour profile of hour_spread (median, q25 and q75 per
        hour of day) and the table of quarter_profile.
    """
    figure, axes = _panels(2, len(spreads), (PANEL_WIDTH * len(spreads), 6.6), sharey="row")
    for column, zone in enumerate(spreads):
        top, bottom, spread = axes[0][column], axes[1][column], spreads[zone]
        top.fill_between(spread.index, spread["q25"], spread["q75"], color=BLUE_LIGHT,
                         linewidth=0, label="25% to 75%")
        top.plot(spread.index, spread["median"], color=BLUE, linewidth=2, label="Median")
        top.set_title(zone)
        bottom.axhline(0, color=INK_SOFT, linewidth=0.8)
        _group_lines(bottom, quarters[zone].index, quarters[zone], QUARTER_LABELS, SERIES)
        bottom.set_xlabel(HOUR_LABEL)
        for ax in (top, bottom):
            ax.set_xticks(range(0, 24, 3))
    axes[0][0].set_ylabel(f"Highest minus lowest price\nin the hour, {UNIT}")
    axes[1][0].set_ylabel(f"Median difference from\nthe hourly mean, {UNIT}")
    axes[0][0].legend(frameon=False, fontsize=8, loc="upper left")
    axes[1][0].legend(frameon=False, fontsize=8, loc="best", ncols=2)
    return _finish(figure, "15-minute prices inside the hour, train period", path, note)


def plot_regime(profiles: dict[str, pd.DataFrame], medians: dict[str, dict[str, pd.DataFrame]],
                labels: dict[str, str], path: Path | None = None, note: str = "") -> Figure:
    """Draw the price per hour of day and against the residual load, one line per period.

    Input: per zone the table of hour_profile_by_group over the periods, per
        zone and period the table of binned_median_by_group, and the legend
        label of each period.
    """
    figure, axes = _panels(2, len(profiles), (PANEL_WIDTH * len(profiles), 6.6), sharey="row")
    for column, zone in enumerate(profiles):
        top, bottom = axes[0][column], axes[1][column]
        _group_lines(top, profiles[zone].index, profiles[zone], labels, SERIES)
        top.set_xticks(range(0, 24, 3))
        top.set_xlabel(HOUR_LABEL)
        top.set_title(zone)
        for colour, (period, label) in zip(SERIES, labels.items()):
            table = medians[zone][period]
            bottom.plot(table["x_median"] / MW_PER_GW, table["median_price"], color=colour,
                        linewidth=2, label=label)
        bottom.set_xlabel(f"{INPUT_LABELS[RESIDUAL]}, GW")
    axes[0][0].set_ylabel(f"Median price, {UNIT}")
    axes[1][0].set_ylabel(f"Median price per bin, {UNIT}")
    axes[0][0].legend(frameon=False, fontsize=8, loc="upper left")
    return _finish(figure, "Price before, in and after the high-price period, train period",
                   path, note)


def _cell_counts(x: pd.Series, price: pd.Series, low: float,
                 high: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Count the hours per cell of input (in GW) and price, with the edges of the cells."""
    both = x.notna() & price.notna()
    x_gw = x[both] / MW_PER_GW
    return np.histogram2d(x_gw, price[both], bins=CELLS,
                          range=[[x_gw.min(), x_gw.max()], [low, high]])


def _group_lines(ax: plt.Axes, x: pd.Index, table: pd.DataFrame, labels: dict,
                 colours: list[str]) -> None:
    """Draw one line per column named in labels, in the given colours."""
    for colour, (column, label) in zip(colours, labels.items()):
        ax.plot(x, table[column], color=colour, linewidth=2, label=label)
