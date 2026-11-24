"""Write the price figures of EDA 1 and print the numbers behind them.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.eda.price_figures

The command reads the hourly table (experiment H) of every core zone, keeps
the train delivery days and writes one PNG per entry of FIGURES to
paths.figures. No validation or test day is read into a figure or a number.

Each figure function takes the train prices by zone and the config. It
returns the tables behind the figure and the figure, and writes a PNG when a
path is given. The notebook notebooks/01_eda_prices.ipynb calls the same
functions without a path.

Prices are in EUR/MWh. The index is UTC. Hours, weekdays, months and years
are counted in market time.
"""

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure

from epf.config import REPO_ROOT, load_config, ordered_zones
from epf.data.splits import load_train
from epf.data.validate import HOURLY
from epf.eda import price_plots as plots
from epf.eda import price_stats as stats

CORE = "core"
HISTOGRAM_SHARES = (0.001, 0.999)   # quantiles of all core zones together
HOURS_PER_DAY = 24
DAY_FORMAT = "%Y-%m-%d"
MONTH_NOTE = " The month panels divide by the years in which the month occurs."

Tables = dict[str, pd.DataFrame]


def load_core_prices(config: dict) -> dict[str, pd.Series]:
    """Return the hourly train prices of every core zone, in the order of the config.

    Input: the config dictionary.
    Output: prices in EUR/MWh by zone key, with a UTC index that ends before
        00:00 market time on splits.validation_start.
    """
    zones = [zone for zone in ordered_zones(config) if zone.group == CORE]
    return {zone.key: load_train(config, HOURLY, zone.key)["price"] for zone in zones}


def train_period(prices: dict[str, pd.Series], config: dict) -> pd.DataFrame:
    """Return per zone the number of hours and the first and last hour in market time."""
    market_tz = config["market"]["timezone"]
    rows = {zone: {"hours": len(price),
                   "first_hour": price.index[0].tz_convert(market_tz).strftime(stats.TIME_FORMAT),
                   "last_hour": price.index[-1].tz_convert(market_tz).strftime(stats.TIME_FORMAT),
                   "empty_prices": int(price.isna().sum())}
            for zone, price in prices.items()}
    return pd.DataFrame.from_dict(rows, orient="index")


def distribution(prices: dict[str, pd.Series], config: dict,
                 path: Path | None = None) -> tuple[Tables, Figure]:
    """Histogram of the hourly price per zone, on one price range shared by the zones."""
    market_tz = config["market"]["timezone"]
    low, high = stats.pooled_range(prices, *HISTOGRAM_SHARES)
    outside = {zone: stats.count_outside(price, low, high) for zone, price in prices.items()}
    tables = {
        "Summary": _by_zone({zone: stats.price_summary(price) for zone, price in prices.items()}),
        "Lowest and highest price, with the hour in market time":
            _by_zone({zone: stats.extremes(price, market_tz) for zone, price in prices.items()}),
        "Price range of the histogram, and the hours outside it":
            _by_zone({zone: {"range_low": low, "range_high": high, "hours_below": below,
                             "hours_above": above} for zone, (below, above) in outside.items()}),
    }
    return tables, plots.plot_distribution(prices, low, high, path)


def by_hour(prices: dict[str, pd.Series], config: dict,
            path: Path | None = None) -> tuple[Tables, Figure]:
    """Median price per hour of day in market time, with the band from q25 to q75."""
    market_tz = config["market"]["timezone"]
    profiles = {zone: stats.hour_profile(price, market_tz) for zone, price in prices.items()}
    return _profile_tables(profiles, "hour"), plots.plot_hour_profile(profiles, path)


def by_weekday(prices: dict[str, pd.Series], config: dict,
               path: Path | None = None) -> tuple[Tables, Figure]:
    """Median price per weekday in market time, with the range from q25 to q75."""
    market_tz = config["market"]["timezone"]
    profiles = {zone: stats.weekday_profile(price, market_tz) for zone, price in prices.items()}
    tables = _profile_tables(profiles, "weekday")
    for table in tables.values():
        table.index = pd.Index(plots.WEEKDAY_NAMES, name="weekday")
    return tables, plots.plot_weekday_profile(profiles, path)


def by_month_year(prices: dict[str, pd.Series], config: dict,
                  path: Path | None = None) -> tuple[Tables, Figure]:
    """Mean price per year and month in market time, as a heatmap."""
    market_tz = config["market"]["timezone"]
    means = {zone: stats.month_year_means(price, market_tz) for zone, price in prices.items()}
    tables = {f"Mean price per year (rows) and month (columns), {zone}": table
              for zone, table in means.items()}
    return tables, plots.plot_month_year(means, _period_note(prices, market_tz), path)


def spikes(prices: dict[str, pd.Series], config: dict,
           path: Path | None = None) -> tuple[Tables, Figure]:
    """Spike hours per year, month and hour of day.

    A spike is a price above the mean plus eda.spike_sd standard deviations
    of the eda.spike_window_days days before it. The hours of the first
    window are not judged.
    """
    market_tz = config["market"]["timezone"]
    days, sd = config["eda"]["spike_window_days"], config["eda"]["spike_sd"]
    window = days * HOURS_PER_DAY
    flags = {zone: stats.spike_flags(price, window, sd) for zone, price in prices.items()}
    judged = {zone: stats.spike_threshold(price, window, sd).notna()
              for zone, price in prices.items()}
    note = (f"Spike: a price above the mean plus {sd:g} standard deviations of the {days} days "
            f"before it. {_period_note(prices, market_tz)}")
    return _flag_tables_and_figure(flags, judged, {}, market_tz, "Spike hours, train period",
                                   note, path)


def negative_prices(prices: dict[str, pd.Series], config: dict,
                    path: Path | None = None) -> tuple[Tables, Figure]:
    """Hours with a price below zero per year, month and hour of day."""
    market_tz = config["market"]["timezone"]
    flags = {zone: stats.negative_flags(price) for zone, price in prices.items()}
    judged = {zone: price.notna() for zone, price in prices.items()}
    zero = {zone: {"hours_at_zero": stats.count_zero(price)} for zone, price in prices.items()}
    return _flag_tables_and_figure(flags, judged, zero, market_tz,
                                   "Hours with a negative price, train period",
                                   _period_note(prices, market_tz), path)


FIGURES = {
    "eda1_price_distribution": distribution,
    "eda1_price_by_hour": by_hour,
    "eda1_price_by_weekday": by_weekday,
    "eda1_price_by_month_year": by_month_year,
    "eda1_spikes": spikes,
    "eda1_negative_prices": negative_prices,
}


def print_tables(tables: Tables) -> None:
    """Print every table under its name, with two decimals for numbers that are not whole."""
    for name, table in tables.items():
        print(f"\n{name}")
        print(table.to_string(float_format=lambda value: f"{value:.2f}", na_rep="-"))


def run(config: dict) -> None:
    """Write every figure of FIGURES and print the tables behind it.

    Input: the config dictionary.
    Output: nothing. Writes the PNG files to paths.figures.
    """
    folder = REPO_ROOT / config["paths"]["figures"]
    folder.mkdir(parents=True, exist_ok=True)
    prices = load_core_prices(config)
    print_tables({"Train data, hourly table": train_period(prices, config)})
    for name, make in FIGURES.items():
        path = folder / f"{name}.png"
        print(f"\n===== {name} =====")
        tables, figure = make(prices, config, path)
        print_tables(tables)
        plt.close(figure)
        print(f"\nWrote {path}")


def main() -> None:
    """Write the price figures of the project config."""
    matplotlib.use("Agg")   # draws to files, so no window opens
    run(load_config())


def _by_zone(rows: dict[str, dict]) -> pd.DataFrame:
    """Return a table with one row per zone from one dictionary of values per zone."""
    return pd.DataFrame.from_dict(rows, orient="index")


def _profile_tables(profiles: dict[str, pd.DataFrame], index_name: str) -> Tables:
    """Return one table per statistic of a profile, with one column per zone."""
    names = {"median": "Median price", "q25": "25% quantile of the price",
             "q75": "75% quantile of the price", "count": "Number of hours with a price"}
    tables = {}
    for statistic, name in names.items():
        table = pd.DataFrame({zone: profile[statistic] for zone, profile in profiles.items()})
        tables[name] = table.rename_axis(index_name)
    return tables


def _flag_tables_and_figure(flags: dict[str, pd.Series], judged: dict[str, pd.Series],
                            extra: dict[str, dict], market_tz: str, title: str, note: str,
                            path: Path | None) -> tuple[Tables, Figure]:
    """Count flagged hours per zone and draw them per year, month and hour of day.

    Input: per zone a True/False series of the flagged hours and one of the
        hours that could have been flagged, and extra columns for the summary.
    The month panel shows the mean per year, because the last year of the
    train set is a part year and its months would count once more than the rest.
    """
    counts = {zone: stats.flag_counts(flag, market_tz) for zone, flag in flags.items()}
    months = {zone: stats.month_means(flag, judged[zone], market_tz)
              for zone, flag in flags.items()}
    summary = {zone: {**stats.flag_summary(flag, int(judged[zone].sum()), market_tz),
                      **extra.get(zone, {})} for zone, flag in flags.items()}
    panels = {zone: {"year": counts[zone]["year"], "month": months[zone]["mean_per_year"],
                     "hour": counts[zone]["hour"]} for zone in flags}
    tables = {"Summary": _by_zone(summary)}
    for key, label in plots.COUNT_ROWS.items():
        if key == "month":
            tables["Hours per month"] = _by_month(months, "hours")
            tables["Years in which the month has a judged hour"] = _by_month(months, "years")
        table = pd.DataFrame({zone: panel[key] for zone, panel in panels.items()})
        tables[label] = table.rename_axis(key)
    return tables, plots.plot_flag_counts(panels, title, note + MONTH_NOTE, path)


def _by_month(months: dict[str, pd.DataFrame], column: str) -> pd.DataFrame:
    """Return one column of the month_means tables, with one column per zone."""
    table = pd.DataFrame({zone: by_month[column] for zone, by_month in months.items()})
    return table.rename_axis("month")


def _period_note(prices: dict[str, pd.Series], market_tz: str) -> str:
    """Return a sentence with the first and the last delivery day of the prices."""
    first = min(price.index[0] for price in prices.values()).tz_convert(market_tz)
    last = max(price.index[-1] for price in prices.values()).tz_convert(market_tz)
    return f"Train period {first.strftime(DAY_FORMAT)} to {last.strftime(DAY_FORMAT)}."


if __name__ == "__main__":
    main()
