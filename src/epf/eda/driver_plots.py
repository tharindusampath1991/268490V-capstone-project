"""The figures of EDA 2, one function per kind of figure.

Every function takes numbers that epf.eda.driver_stats computed, by zone. A
figure with one panel per zone starts a new row after four zones. A figure
with several panels per zone has one row per zone. Each function returns the
figure and writes a PNG when a path is given. Prices are in EUR/MWh, forecasts
are drawn in GW. Hours are in market time.
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
    PANEL_WIDTH,
    ROW_HEIGHT,
    UNIT,
    _finish,
    _label_rows,
    _panels,
    _zone_label,
    _zone_panels,
)

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # groups without an order, fixed order
ORDERED = ["#86b6ef", "#2a78d6", "#0d366b"]             # groups from low to high
CELLS = 50                                              # cells per axis of a 2D histogram
MW_PER_GW = 1000.0
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
        One row of panels per zone and one column per input.
    """
    names = [name for name in INPUTS if any(name in table.columns for table in drivers.values())]
    figure, axes = _panels(len(drivers), len(names),
                           (PANEL_WIDTH * len(names), ROW_HEIGHT * len(drivers)), grid=False,
                           sharey=True)
    cells = {(zone, name): _cell_counts(table[name], table[PRICE], low, high)
             for zone, table in drivers.items() for name in names if name in table.columns}
    scale = LogNorm(1, max(counts.max() for counts, _, _ in cells.values()))
    colours = LinearSegmentedColormap.from_list("blue_ramp", BLUE_RAMP)
    for row, zone in enumerate(drivers):
        for column, name in enumerate(names):
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
        _zone_label(axes[row][0], f"{zone}\nPrice, {UNIT}")
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
    figure, panels = _zone_panels(len(profiles), sharey=True)
    colours = ORDERED if ordered else SERIES
    for ax, (zone, profile) in zip(panels, profiles.items()):
        if zero_line:
            ax.axhline(0, color=INK_SOFT, linewidth=0.8)
        _group_lines(ax, profile.index, profile, labels, colours)
        ax.set_xticks(range(0, 24, 3))
        ax.set_title(zone)
        ax.set_xlabel(HOUR_LABEL)
    _label_rows(panels, ylabel)
    panels[0].legend(frameon=False, fontsize=8, loc="best")
    return _finish(figure, title, path, note)


def plot_shares_by_bin(shares: dict[str, dict[str, pd.DataFrame]], title: str, xlabel: str,
                       path: Path | None = None, note: str = "") -> Figure:
    """Draw the share of flagged hours per bin as bars, one row per zone and one column per flag.

    Input: per zone and per kind of flag the table of share_by_bin. Each
        column of panels shares one y-axis.
    """
    kinds = list(next(iter(shares.values())))
    figure, axes = _panels(len(shares), len(kinds),
                           (PANEL_WIDTH * len(kinds), ROW_HEIGHT * len(shares)), sharey="col")
    for row, (zone, by_kind) in enumerate(shares.items()):
        for column, label in enumerate(kinds):
            ax, table = axes[row][column], by_kind[label]
            ax.bar(table.index, table["share_percent"], width=0.7, color=BLUE)
            ax.set_xticks(table.index)
        _zone_label(axes[row][0], zone)
    for column, label in enumerate(kinds):
        axes[0][column].set_title(label)
        axes[-1][column].set_xlabel(xlabel)
    return _finish(figure, title, path, note)


def plot_quarter_hours(spreads: dict[str, pd.DataFrame], quarters: dict[str, pd.DataFrame],
                       path: Path | None = None, note: str = "") -> Figure:
    """Draw the spread inside the hour and the place of each quarter-hour in its hour.

    Input: per zone the hour profile of hour_spread (median, q25 and q75 per
        hour of day) and the table of quarter_profile. One row of panels per
        zone: the spread on the left, the quarter-hours on the right.
    """
    figure, axes = _panels(len(spreads), 2, (PANEL_WIDTH * 2, ROW_HEIGHT * len(spreads)),
                           sharey="col")
    for row, zone in enumerate(spreads):
        left, right, spread = axes[row][0], axes[row][1], spreads[zone]
        left.fill_between(spread.index, spread["q25"], spread["q75"], color=BLUE_LIGHT,
                          linewidth=0, label="25% to 75%")
        left.plot(spread.index, spread["median"], color=BLUE, linewidth=2, label="Median")
        right.axhline(0, color=INK_SOFT, linewidth=0.8)
        _group_lines(right, quarters[zone].index, quarters[zone], QUARTER_LABELS, SERIES)
        for ax in (left, right):
            ax.set_xticks(range(0, 24, 3))
        _zone_label(left, zone)
    axes[0][0].set_title(f"Highest minus lowest price in the hour, {UNIT}")
    axes[0][1].set_title(f"Median difference from the hourly mean, {UNIT}")
    for ax in axes[-1]:
        ax.set_xlabel(HOUR_LABEL)
    axes[0][0].legend(frameon=False, fontsize=8, loc="upper left")
    axes[0][1].legend(frameon=False, fontsize=8, loc="upper right", ncols=2)
    return _finish(figure, "15-minute prices inside the hour, train period", path, note)


def plot_regime(profiles: dict[str, pd.DataFrame], medians: dict[str, dict[str, pd.DataFrame]],
                labels: dict[str, str], path: Path | None = None, note: str = "") -> Figure:
    """Draw the price per hour of day and against the residual load, one line per period.

    Input: per zone the table of hour_profile_by_group over the periods, per
        zone and period the table of binned_median_by_group, and the legend
        label of each period. One row of panels per zone: the hour of day on
        the left, the residual load on the right.
    """
    figure, axes = _panels(len(profiles), 2, (PANEL_WIDTH * 2, ROW_HEIGHT * len(profiles)),
                           sharey="col")
    for row, zone in enumerate(profiles):
        left, right = axes[row][0], axes[row][1]
        _group_lines(left, profiles[zone].index, profiles[zone], labels, SERIES)
        left.set_xticks(range(0, 24, 3))
        for colour, (period, label) in zip(SERIES, labels.items()):
            table = medians[zone][period]
            right.plot(table["x_median"] / MW_PER_GW, table["median_price"], color=colour,
                       linewidth=2, label=label)
        _zone_label(left, zone)
    axes[0][0].set_title(f"Median price by hour of day, {UNIT}")
    axes[0][1].set_title(f"Median price per bin of the residual load, {UNIT}")
    axes[-1][0].set_xlabel(HOUR_LABEL)
    axes[-1][1].set_xlabel(f"{INPUT_LABELS[RESIDUAL]}, GW")
    axes[0][1].legend(frameon=False, fontsize=8, loc="upper left")
    return _finish(figure, "Price before, in and after the high-price period, train period",
                   path, note)


def plot_sweden(relative: pd.DataFrame, equal: pd.DataFrame, profiles: pd.DataFrame,
                mark: float, mark_label: str, title: str, path: Path | None = None,
                note: str = "") -> Figure:
    """Draw neighbouring zones in one figure: level, identical prices and daily shape.

    Input: the mean price per year divided by the mean of the zones (one
        column per zone), the percentage of hours with the same price per year
        (one column per pair of zones), the median price per hour of day
        divided by the mean price of the zone (one column per zone), and a
        position on the year axis to mark with a dashed line and a label.
    """
    figure, axes = _panels(1, 3, (PANEL_WIDTH * 3, 3.8))
    left, middle, right = axes[0]
    for colour, zone in zip(SERIES, relative.columns):
        left.plot(relative.index, relative[zone], color=colour, linewidth=2, marker="o",
                  markersize=4, label=zone)
        right.plot(profiles.index, profiles[zone], color=colour, linewidth=2, label=zone)
    for colour, pair in zip(SERIES, equal.columns):
        middle.plot(equal.index, equal[pair], color=colour, linewidth=2, marker="o",
                    markersize=4, label=pair)
    middle.axvline(mark, color=INK_SOFT, linewidth=0.8, linestyle="--")
    middle.text(mark, 0.97, f" {mark_label}", transform=middle.get_xaxis_transform(), ha="left",
                va="top", fontsize=8, color=INK_SOFT)
    for ax in (left, middle):
        ax.set_xticks(relative.index)
        ax.set_xlabel("Year")
    right.set_xticks(range(0, 24, 3))
    right.set_xlabel(HOUR_LABEL)
    left.set_ylabel("Mean price of the year divided by\nthe mean of the zones")
    middle.set_ylabel("Hours with exactly the same price, %")
    right.set_ylabel("Median price divided by\nthe mean price of the zone")
    for ax in (left, middle, right):
        ax.legend(frameon=False, fontsize=8, loc="best")
    return _finish(figure, title, path, note)


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
