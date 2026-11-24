"""The price figures of EDA 1, one function per kind of figure.

Every function takes numbers that epf.eda.price_stats computed, by zone, and
draws one panel or one column of panels per zone. It returns the figure and
writes a PNG when a path is given. Prices are in EUR/MWh. Hours, weekdays,
months and years are in market time.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure

from epf.eda.price_stats import count_outside

DPI = 150
HISTOGRAM_BINS = 80
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e6e5e0"
BLUE = "#2a78d6"
BLUE_LIGHT = "#b7d3f6"
BLUE_RAMP = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]   # low to high
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
COUNT_ROWS = {"year": "Hours per year", "month": "Mean hours per year, by month",
              "hour": "Hours per hour of day"}
UNIT = "EUR/MWh"


def plot_distribution(prices: dict[str, pd.Series], low: float, high: float,
                      path: Path | None = None) -> Figure:
    """Draw a histogram of the hourly prices of each zone on one shared price range.

    Input: prices by zone, and the range [low, high] in EUR/MWh. Prices
        outside the range are not drawn. Their number is written in the panel.
    """
    figure, axes = _panels(1, len(prices), (4.2 * len(prices), 3.8), sharey=True)
    bins = np.linspace(low, high, HISTOGRAM_BINS + 1)
    for ax, (zone, price) in zip(axes[0], prices.items()):
        ax.hist(price.dropna(), bins=bins, color=BLUE, edgecolor=SURFACE, linewidth=0.3)
        ax.axvline(0, color=INK_SOFT, linewidth=0.8)
        below, above = count_outside(price, low, high)
        ax.text(0.97, 0.95, f"median: {price.median():.1f}\nhours below {low:.0f}: {below}\n"
                f"hours above {high:.0f}: {above}", transform=ax.transAxes, ha="right", va="top",
                fontsize=8, color=INK_SOFT)
        ax.set_title(zone)
        ax.set_xlabel(f"Price, {UNIT}")
    axes[0][0].set_ylabel("Hours")
    return _finish(figure, "Hourly day-ahead price, train period", path)


def plot_hour_profile(profiles: dict[str, pd.DataFrame], path: Path | None = None) -> Figure:
    """Draw the median price per hour of day with the band from q25 to q75.

    Input: the table of hour_profile by zone. An hour without a price leaves
        a break in the line.
    """
    figure, axes = _panels(1, len(profiles), (4.2 * len(profiles), 3.8), sharey=True)
    for ax, (zone, profile) in zip(axes[0], profiles.items()):
        ax.fill_between(profile.index, profile["q25"], profile["q75"], color=BLUE_LIGHT,
                        linewidth=0, label="25% to 75%")
        ax.plot(profile.index, profile["median"], color=BLUE, linewidth=2, label="Median")
        ax.set_xticks(range(0, 24, 3))
        ax.set_title(zone)
        ax.set_xlabel("Hour of day, market time")
    axes[0][0].set_ylabel(f"Price, {UNIT}")
    axes[0][0].legend(frameon=False, fontsize=8, loc="upper left")
    return _finish(figure, "Price by hour of day, train period", path)


def plot_weekday_profile(profiles: dict[str, pd.DataFrame], path: Path | None = None) -> Figure:
    """Draw the median price per weekday with the range from q25 to q75.

    Input: the table of weekday_profile by zone.
    """
    figure, axes = _panels(1, len(profiles), (4.2 * len(profiles), 3.8), sharey=True)
    for ax, (zone, profile) in zip(axes[0], profiles.items()):
        spread = [profile["median"] - profile["q25"], profile["q75"] - profile["median"]]
        ax.errorbar(profile.index, profile["median"], yerr=spread, fmt="o", color=BLUE,
                    markersize=6, elinewidth=2, capsize=3, label="Median, with 25% to 75%")
        ax.set_xticks(profile.index, WEEKDAY_NAMES)
        ax.set_ylim(bottom=min(0.0, ax.get_ylim()[0]))
        ax.set_title(zone)
    axes[0][0].set_ylabel(f"Price, {UNIT}")
    axes[0][0].legend(frameon=False, fontsize=8, loc="lower left")
    return _finish(figure, "Price by weekday, train period", path)


def plot_month_year(means: dict[str, pd.DataFrame], note: str,
                    path: Path | None = None) -> Figure:
    """Draw the mean price per year and month as a heatmap with the value in each cell.

    Input: the table of month_year_means by zone, and a note for the foot
        of the figure. All zones share one colour scale.
    """
    figure, axes = _panels(len(means), 1, (9.5, 3.1 * len(means)), grid=False)
    lowest = min(0.0, min(table.min().min() for table in means.values()))
    highest = max(table.max().max() for table in means.values())
    colours = LinearSegmentedColormap.from_list("blue_ramp", BLUE_RAMP)
    for ax, (zone, table) in zip(axes[:, 0], means.items()):
        sns.heatmap(table, ax=ax, cmap=colours, vmin=lowest, vmax=highest, annot=True, fmt=".0f",
                    annot_kws={"size": 8}, linewidths=1.5, linecolor=SURFACE, cbar=False,
                    xticklabels=MONTH_NAMES)
        ax.set_title(zone)
        ax.set_ylabel("")
        ax.tick_params(axis="y", rotation=0)
    bar = figure.colorbar(axes[-1, 0].collections[0], ax=axes[:, 0].tolist(), shrink=0.5, pad=0.02)
    bar.set_label(f"Mean price, {UNIT}", color=INK_SOFT)
    bar.outline.set_visible(False)
    return _finish(figure, "Mean price by year and month, train period", path, note)


def plot_flag_counts(counts: dict[str, dict[str, pd.Series]], title: str, note: str,
                     path: Path | None = None) -> Figure:
    """Draw the flagged hours per year, per month and per hour of day.

    Input: per zone one series under each key of COUNT_ROWS, the figure
        title and a note for the foot of the figure. year and hour hold the
        counts of flag_counts, month the mean per year of month_means. Each
        row of panels shares one y-axis.
    """
    figure, axes = _panels(len(COUNT_ROWS), len(counts), (4.2 * len(counts), 8.2), sharey="row")
    for column, (zone, by_key) in enumerate(counts.items()):
        for row, key in enumerate(COUNT_ROWS):
            ax, series = axes[row][column], by_key[key]
            positions = range(len(series))
            bars = ax.bar(positions, series.to_numpy(), width=0.7, color=BLUE)
            if key == "year":
                ax.set_xticks(positions, series.index)
                ax.bar_label(bars, fontsize=7, color=INK_SOFT, padding=2)
            elif key == "month":
                ax.set_xticks(positions, [name[0] for name in MONTH_NAMES])
            else:
                ax.set_xticks(range(0, 24, 3))
                ax.set_xlabel("Hour of day, market time")
        axes[0][column].set_title(zone)
    for row, label in enumerate(COUNT_ROWS.values()):
        axes[row][0].set_ylabel(label)
    return _finish(figure, title, path, note)


def _panels(rows: int, columns: int, size: tuple[float, float], grid: bool = True,
            **shared) -> tuple[Figure, np.ndarray]:
    """Return a figure with rows x columns panels in the common style, as a 2D array."""
    figure, axes = plt.subplots(rows, columns, figsize=size, squeeze=False, layout="constrained",
                                facecolor=SURFACE, **shared)
    for ax in axes.flat:
        ax.set_facecolor(SURFACE)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color(GRID)
        ax.tick_params(colors=INK_SOFT, labelsize=8)
        ax.xaxis.label.set_color(INK_SOFT)
        ax.yaxis.label.set_color(INK_SOFT)
        ax.title.set_color(INK)
        ax.set_axisbelow(True)
        if grid:
            ax.grid(axis="y", color=GRID, linewidth=0.8)
    return figure, axes


def _finish(figure: Figure, title: str, path: Path | None, note: str = "") -> Figure:
    """Add the title and the note, write the PNG when a path is given and return the figure."""
    figure.suptitle(title, x=0.01, ha="left", fontsize=12, color=INK)
    if note:
        figure.supxlabel(note, x=0.01, ha="left", fontsize=8, color=INK_SOFT)
    if path is not None:
        figure.savefig(path, dpi=DPI, facecolor=SURFACE)
    return figure
