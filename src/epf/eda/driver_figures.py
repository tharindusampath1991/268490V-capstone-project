"""Write the figures of EDA 2 and print the numbers behind them.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.eda.driver_figures

EDA 2 compares the price with the day-ahead load, wind and solar forecasts,
looks inside the hour at the 15-minute prices, and compares the high-price
period of 2021 and 2022, holidays and working days. The core zones come
first. The last figure is one section on the extra zones. The command reads
the tables each figure of FIGURES names, keeps the train delivery days and
writes one PNG per figure to paths.figures. No validation or test day is read
into a figure or a number.

Each figure function takes the train tables by zone and the config. It
returns the tables behind the figure and the figure, and writes a PNG when a
path is given. The notebook notebooks/01_eda_drivers.ipynb calls the same
functions without a path.

Prices are in EUR/MWh and forecasts in MW. The index is UTC. Hours, delivery
days, months and years are counted in market time. An hour with an empty
input is left out of a comparison and counted. The price of a day is never
compared with actual_load.
"""

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from epf.config import REPO_ROOT, load_config, ordered_zones
from epf.data.splits import load_train
from epf.data.validate import HOURLY, QUARTER_HOUR
from epf.eda import driver_plots as plots
from epf.eda import driver_stats as stats
from epf.eda import price_figures as base
from epf.eda import price_stats
from epf.eda.price_plots import UNIT
from epf.features.holiday_calendar import holiday_dates, regional_days, subdivisions

CORE = "core"
EXTRA = "extra"
PRICE = stats.PRICE
HOURS_PER_DAY = 24
MW_PER_GW = 1000.0
INPUT_NAMES = {stats.LOAD: "load forecast", stats.WIND: "wind forecast",
               stats.SOLAR: "solar forecast", stats.RESIDUAL: "residual load"}

Tables = dict[str, pd.DataFrame]
ZoneTables = dict[str, pd.DataFrame]


def load_tables(config: dict, table_name: str, group: str) -> ZoneTables:
    """Return the train rows of one processed table for every zone of a group.

    Input: the config dictionary, a table name (HOURLY or QUARTER_HOUR of
        epf.data.validate) and a zone group, core or extra.
    Output: tables by zone key in the order of the config, each with a UTC
        index that ends before 00:00 market time on splits.validation_start.
    """
    zones = [zone for zone in ordered_zones(config) if zone.group == group]
    return {zone.key: load_train(config, table_name, zone.key) for zone in zones}


def price_vs_drivers(tables: ZoneTables, config: dict,
                     path: Path | None = None) -> tuple[Tables, Figure]:
    """The price against the load, wind and solar forecast and the residual load."""
    market_tz, bins = config["market"]["timezone"], config["eda"]["median_bins"]
    drivers = {zone: stats.driver_table(table) for zone, table in tables.items()}
    prices = _prices(drivers)
    low, high = price_stats.pooled_range(prices, *base.HISTOGRAM_SHARES)
    medians = {zone: {name: stats.binned_median(table[name], table[PRICE], bins)
                      for name in stats.INPUTS if name in table.columns}
               for zone, table in drivers.items()}
    correlations = {zone: stats.correlation_table(table) for zone, table in drivers.items()}
    outside = {zone: price_stats.count_outside(price, low, high) for zone, price in prices.items()}
    out = {
        "Rank correlation of the price with each input":
            _by_zone({zone: table["rank_correlation"] for zone, table in correlations.items()}),
        "Hours left out because the input or the price is empty":
            _by_zone({zone: table["hours_left_out"] for zone, table in correlations.items()}),
    }
    for zone, table in drivers.items():
        out[f"Rank correlation of the price with each input per year, {zone}"] = (
            stats.correlation_by_year(table, market_tz))
    out["Price range of the panels, and the hours outside it"] = _by_zone(
        {zone: {"range_low": low, "range_high": high, "hours_below": below, "hours_above": above}
         for zone, (below, above) in outside.items()})
    for name, label in INPUT_NAMES.items():
        columns = {zone: by_input[name][["x_median", "median_price", "hours"]]
                   for zone, by_input in medians.items() if name in by_input}
        if columns:
            out[f"Median price per bin of the {label} (bin 1 = lowest, x in MW)"] = (
                pd.concat(columns, axis=1))
    return out, plots.plot_price_vs_inputs(drivers, medians, low, high, path)


def solar_midday(tables: ZoneTables, config: dict,
                 path: Path | None = None) -> tuple[Tables, Figure]:
    """The price within the day, for days with little, medium and much solar forecast.

    The delivery days of a zone are sorted into eda.solar_day_groups groups
    of equal size by the sum of their solar forecast. A day with an empty
    solar hour is left out. A zone without a solar forecast is left out.
    """
    market_tz, count = config["market"]["timezone"], config["eda"]["solar_day_groups"]
    if count > len(plots.ORDERED):
        raise ValueError(f"eda.solar_day_groups is {count}. The figure has "
                         f"{len(plots.ORDERED)} colours.")
    order = list(range(1, count + 1))
    middle = order[1:-1]
    labels = {1: "Days with the least solar",
              **{number: "Days in between" if len(middle) == 1 else f"Group {number} of {count}"
                 for number in middle},
              count: "Days with the most solar"}
    profiles, days = {}, {}
    for zone, table in tables.items():
        if stats.SOLAR not in table.columns:
            continue
        daily = stats.daily_sum(table[stats.SOLAR], market_tz)
        group = stats.bin_numbers(daily, count)
        by_step = stats.to_time_steps(group, table.index, market_tz)
        profiles[zone] = stats.hour_profile_by_group(
            stats.minus_day_mean(table[PRICE], market_tz), by_step, market_tz, order)
        sizes = group.value_counts().reindex(order, fill_value=0)
        energy = daily.groupby(group).median().reindex(order) / MW_PER_GW
        days[zone] = {**{f"days_group_{number}": int(sizes[number]) for number in order},
                      "days_left_out": int(daily.isna().sum()),
                      **{f"median_gwh_group_{number}": energy[number] for number in order}}
    out = {"Delivery days per group of the daily solar forecast (group 1 = least solar)":
           _by_zone(days)}
    for number in order:
        out[f"Median of the price minus the mean price of its day, group {number}"] = (
            pd.DataFrame({zone: profile[number] for zone, profile in profiles.items()}))
    note = ("Days are grouped per zone by the sum of the solar forecast over the delivery day. "
            + _period_note(tables, market_tz))
    figure = plots.plot_group_profiles(
        profiles, labels, "Price within the day by the solar forecast of the day, train period",
        f"Median of price minus\nthe mean price of the day, {UNIT}", path, note, ordered=True,
        zero_line=True)
    return out, figure


def negative_spike_by_residual(tables: ZoneTables, config: dict,
                               path: Path | None = None) -> tuple[Tables, Figure]:
    """Negative prices and spikes per bin of the residual load.

    The spike rule is the one of EDA 1 (eda.spike_window_days, eda.spike_sd).
    The share of a bin is taken over all its hours.
    """
    market_tz, bins = config["market"]["timezone"], config["eda"]["share_bins"]
    days, sd = config["eda"]["spike_window_days"], config["eda"]["spike_sd"]
    negative_label, spike_label = "Hours with a negative price, %", "Spike hours, %"
    shares, left_out, inputs = {}, {}, {}
    for zone, table in tables.items():
        drivers = stats.driver_table(table)
        residual = drivers[stats.RESIDUAL]
        flags = {"negative": price_stats.negative_flags(drivers[PRICE]),
                 "spike": price_stats.spike_flags(drivers[PRICE], days * HOURS_PER_DAY, sd),
                 "all": pd.Series(True, index=drivers.index)}
        shares[zone] = {negative_label: stats.share_by_bin(residual, flags["negative"], bins),
                        spike_label: stats.share_by_bin(residual, flags["spike"], bins)}
        empty = residual.isna()
        left_out[zone] = {"hours": int(empty.sum()),
                          "negative_hours": int((flags["negative"] & empty).sum()),
                          "spike_hours": int((flags["spike"] & empty).sum())}
        inputs[zone] = {kind: stats.median_shares(drivers, flag) for kind, flag in flags.items()}
    first = next(iter(shares.values()))
    out = {
        "Hours per bin of the residual load": _column(shares, negative_label, "hours"),
        "Hours with a negative price per bin of the residual load (bin 1 = lowest)":
            _column(shares, negative_label, "flagged"),
        "Share of the hours of the bin with a negative price, percent":
            _column(shares, negative_label, "share_percent"),
        "Spike hours per bin of the residual load (bin 1 = lowest)":
            _column(shares, spike_label, "flagged"),
        "Share of the hours of the bin that are a spike, percent":
            _column(shares, spike_label, "share_percent"),
        "Hours left out because the residual load is empty": _by_zone(left_out),
    }
    kinds = {"negative": "hours with a negative price", "spike": "spike hours",
             "all": "all hours"}
    for kind, label in kinds.items():
        out[f"Load forecast in MW, and wind, solar and residual load as a percentage of it: "
            f"medians over {label}"] = _by_zone({zone: by_kind[kind]
                                                 for zone, by_kind in inputs.items()})
    note = (f"Bin 1 holds the {100 // len(first[negative_label])}% of hours with the lowest "
            f"residual load of the zone. Spike: a price above the mean plus {sd:g} standard "
            f"deviations of the {days} days before it. {_period_note(tables, market_tz)}")
    figure = plots.plot_shares_by_bin(
        shares, "Negative prices and spikes by residual load, train period",
        "Bin of the residual load, 1 = lowest", path, note)
    return out, figure


def quarter_hour_spread(tables: ZoneTables, config: dict,
                        path: Path | None = None) -> tuple[Tables, Figure]:
    """The spread of the four 15-minute prices of an hour, and where each one lies.

    Input: the 15-minute tables (experiment Q) by zone.
    """
    market_tz = config["market"]["timezone"]
    spreads = {zone: stats.hour_spread(table[PRICE]) for zone, table in tables.items()}
    profiles = {zone: price_stats.hour_profile(spread, market_tz)
                for zone, spread in spreads.items()}
    quarters = {zone: stats.quarter_profile(stats.quarter_differences(table[PRICE]), market_tz)
                for zone, table in tables.items()}
    out = {"Spread inside the hour: highest minus lowest quarter-hour price":
           _by_zone({zone: stats.spread_summary(spread) for zone, spread in spreads.items()})}
    names = {"median": "Median spread per hour of day", "q25": "25% quantile of the spread",
             "q75": "75% quantile of the spread", "count": "Hours with a spread"}
    for statistic, name in names.items():
        out[name] = pd.DataFrame({zone: profile[statistic]
                                  for zone, profile in profiles.items()}).rename_axis("hour")
    for zone, profile in quarters.items():
        out[f"Median difference of each quarter-hour from the mean of its hour, {zone}"] = profile
    note = ("Spread: the highest minus the lowest of the four 15-minute prices of an hour. "
            + _period_note(tables, market_tz))
    return out, plots.plot_quarter_hours(profiles, quarters, path, note)


def regime(tables: ZoneTables, config: dict, path: Path | None = None) -> tuple[Tables, Figure]:
    """The price before, in and after the high-price period.

    The period is one for all zones passed in: the months from the first to
    the last month whose mean price over the zones is above eda.regime_factor
    times the median of all months (driver_stats.high_price_period).
    """
    market_tz, factor = config["market"]["timezone"], config["eda"]["regime_factor"]
    bins = config["eda"]["median_bins"]
    drivers = {zone: stats.driver_table(table) for zone, table in tables.items()}
    summary, pooled = stats.high_price_period(_prices(drivers), factor, market_tz)
    first, last = summary["first_month"], summary["last_month"]
    outside = pooled[(pooled.index < first) | (pooled.index > last)].nlargest(3)
    out = {"High-price period, one for all zones":
           pd.DataFrame.from_dict({"all zones": summary}, orient="index"),
           "The three months outside the period with the highest mean price over the zones":
           outside.rename("mean_price").rename_axis("month").to_frame()}
    profiles, medians = {}, {}
    for zone, table in drivers.items():
        labels = stats.period_labels(table.index, first, last, market_tz)
        profiles[zone] = stats.hour_profile_by_group(table[PRICE], labels, market_tz,
                                                     stats.PERIODS)
        medians[zone] = stats.binned_median_by_group(table[stats.RESIDUAL], table[PRICE], labels,
                                                     bins, stats.PERIODS)
        out[f"Price per period, {zone}"] = _period_summary(table, labels)
    for period in stats.PERIODS:
        out[f"Median price per hour of day, {period.lower()}"] = pd.DataFrame(
            {zone: profile[period] for zone, profile in profiles.items()})
    for zone, by_period in medians.items():
        out[f"Median price per bin of the residual load (bin 1 = lowest), {zone}"] = pd.concat(
            {period: table[["median_price", "hours"]] for period, table in by_period.items()},
            axis=1)
    legend = {stats.BEFORE: f"Before {first}", stats.DURING: f"{first} to {last}",
              stats.AFTER: f"After {last}"}
    note = (f"High-price period: {first} to {last}, the months in which the mean price of the "
            f"zones is above {factor:g} times its median. {_period_note(tables, market_tz)}")
    return out, plots.plot_regime(profiles, medians, legend, path, note)


def holidays(tables: ZoneTables, config: dict,
             path: Path | None = None) -> tuple[Tables, Figure]:
    """The price on holidays against working days, Saturdays and Sundays.

    A holiday is a nationwide holiday of the zone's holiday_country in its
    holiday_categories. Regional holidays count as working days. The last
    tables measure what that leaves out.
    """
    market_tz, window = config["market"]["timezone"], config["eda"]["holiday_window_days"]
    edges = config["eda"]["regional_share_edges"]
    zones = {zone.key: zone for zone in ordered_zones(config)}
    profiles, counts, medians, plain, strict, left_out, by_share = {}, {}, {}, {}, {}, {}, {}
    for zone, table in tables.items():
        country, categories = zones[zone].holiday_country, zones[zone].holiday_categories
        daily = stats.daily_mean(table[PRICE], market_tz)
        years = range(daily.index[0].year, daily.index[-1].year + 1)
        nationwide = holiday_dates(country, categories, years)
        types = stats.day_types(daily.index, nationwide)
        profiles[zone] = stats.hour_profile_by_group(
            table[PRICE], stats.to_time_steps(types, table.index, market_tz), market_tz,
            stats.DAY_TYPES)
        counts[zone] = {**types.value_counts().reindex(stats.DAY_TYPES, fill_value=0).to_dict(),
                        "holidays_on_a_weekend": stats.weekend_holidays(daily.index, nationwide)}
        medians[zone] = daily.groupby(types).median().reindex(stats.DAY_TYPES).to_dict()
        holiday_days = types.index[types == stats.HOLIDAY]
        working = types.index[types == stats.WORKING]
        regional = regional_days(country, categories, years)
        is_regional = np.array([day in regional for day in working.date], dtype=bool)
        regional_working, never_holiday = working[is_regional], working[~is_regional]
        plain[zone] = stats.difference_summary(
            stats.matched_difference(daily, holiday_days, working, window))
        strict[zone] = stats.difference_summary(
            stats.matched_difference(daily, holiday_days, never_holiday, window))
        left_out[zone] = {"days": len(regional_working),
                          "percent_of_working_days": 100.0 * len(regional_working) / len(working),
                          "subdivisions": len(subdivisions(country))}
        by_share[zone] = _regional_by_share(
            daily, regional_working, never_holiday, regional, len(subdivisions(country)),
            window, edges)
    out = {
        "Delivery days per day type": _by_zone(counts),
        "Median of the daily mean price per day type": _by_zone(medians),
        f"Holiday on Monday to Friday: daily mean price minus the median of the working days "
        f"within {window} days": _by_zone(plain),
        "The same, with regional holidays taken out of the working days": _by_zone(strict),
        "Regional holidays on Monday to Friday that count as working days": _by_zone(left_out),
        "Regional holidays by the share of subdivisions that have them: days":
            _by_zone({zone: table["days"] for zone, table in by_share.items()}),
        f"Regional holidays by share of subdivisions: median of the daily mean price minus the "
        f"working days within {window} days":
            _by_zone({zone: table["median"] for zone, table in by_share.items()}),
    }
    for day_type in stats.DAY_TYPES:
        out[f"Median price per hour of day, {day_type.lower()}"] = pd.DataFrame(
            {zone: profile[day_type] for zone, profile in profiles.items()})
    note = ("Holiday: a nationwide public holiday. A holiday on a Saturday or Sunday counts as "
            f"that weekend day. {_period_note(tables, market_tz)}")
    figure = plots.plot_group_profiles(
        profiles, {name: name for name in stats.DAY_TYPES},
        "Price by hour of day and type of day, train period", f"Median price, {UNIT}", path, note)
    return out, figure


def sweden(tables: ZoneTables, config: dict, path: Path | None = None) -> tuple[Tables, Figure]:
    """The extra zones in one section: price level, identical prices and daily shape.

    Input: the hourly tables of the extra zones, in the order of the config.
    Each zone is compared with the next one in that order. Levels are shown
    relative to the mean of the zones, never in EUR against each other. The
    hours are split at eda.nordic_flow_based_start, the first delivery day of
    Nordic flow-based market coupling.
    """
    market_tz, start_day = config["market"]["timezone"], config["eda"]["nordic_flow_based_start"]
    start = pd.Timestamp(start_day, tz=market_tz)
    prices = _prices(tables)
    zones = list(prices)
    pairs = list(zip(zones[:-1], zones[1:]))
    yearly = pd.DataFrame({zone: stats.yearly_means(price, market_tz)
                           for zone, price in prices.items()})
    relative = yearly.div(yearly.mean(axis=1), axis=0)
    equal = pd.DataFrame({f"{one} = {other}": stats.equal_share_by_year(
        prices[one], prices[other], market_tz)["share_percent"] for one, other in pairs})
    profiles = pd.DataFrame({zone: price_stats.hour_profile(price / price.mean(),
                                                            market_tz)["median"]
                             for zone, price in prices.items()}).rename_axis("hour")
    correlations = {zone: stats.correlation_table(stats.driver_table(table))
                    for zone, table in tables.items()}
    out = {
        "Price over the train period": _by_zone(
            {zone: {"hours": int(price.count()), "mean": price.mean(), "median": price.median(),
                    "negative_hours": int(price_stats.negative_flags(price).sum())}
             for zone, price in prices.items()}),
        "Mean price per year": yearly,
        "Mean price per year divided by the mean of the zones": relative,
        "Hours with exactly the same price in neighbouring zones, percent": equal,
    }
    for one, other in pairs:
        out[f"Prices of {one} and {other} before and from {start_day}"] = (
            stats.difference_before_and_from(prices[one], prices[other], start))
    out["Rank correlation of the price with each input"] = _by_zone(
        {zone: table["rank_correlation"] for zone, table in correlations.items()})
    out["Hours left out because the input or the price is empty"] = _by_zone(
        {zone: table["hours_left_out"] for zone, table in correlations.items()})
    out["Median price per hour of day divided by the mean price of the zone"] = profiles
    days_in_year = 366 if start.is_leap_year else 365
    mark = start.year + (start.dayofyear - 1) / days_in_year
    title = (f"Extra zones {zones[0]} to {zones[-1]}, not in the approved Milestone 1 scope, "
             "train period")
    note = (f"Zones in the order of the config, each compared with the next. Dashed line: "
            f"Nordic flow-based market coupling from delivery day {start_day}. "
            f"{_period_note(tables, market_tz)}")
    figure = plots.plot_sweden(relative, equal, profiles, mark,
                               f"Flow-based coupling\n from {start_day}", title, path, note)
    return out, figure


FIGURES = {
    "eda2_price_vs_drivers": (price_vs_drivers, HOURLY, CORE),
    "eda2_solar_midday": (solar_midday, HOURLY, CORE),
    "eda2_negative_spike_by_residual": (negative_spike_by_residual, HOURLY, CORE),
    "eda2_quarter_hour_spread": (quarter_hour_spread, QUARTER_HOUR, CORE),
    "eda2_regime_2022": (regime, HOURLY, CORE),
    "eda2_holidays": (holidays, HOURLY, CORE),
    "eda2_sweden_north_south": (sweden, HOURLY, EXTRA),
}


def train_period(tables: ZoneTables, config: dict) -> pd.DataFrame:
    """Return per zone the number of time steps and the first and last one in market time."""
    period = base.train_period(_prices(tables), config)
    return period.rename(columns={"hours": "time_steps", "first_hour": "first", "last_hour": "last"})


def run(config: dict) -> None:
    """Write every figure of FIGURES and print the tables behind it.

    Input: the config dictionary.
    Output: nothing. Writes the PNG files to paths.figures.
    """
    folder = REPO_ROOT / config["paths"]["figures"]
    folder.mkdir(parents=True, exist_ok=True)
    loaded: dict[tuple[str, str], ZoneTables] = {}
    for name, (make, table_name, group) in FIGURES.items():
        if (table_name, group) not in loaded:
            loaded[table_name, group] = load_tables(config, table_name, group)
            base.print_tables({f"Train data, {table_name} table, {group} zones":
                               train_period(loaded[table_name, group], config)})
        path = folder / f"{name}.png"
        print(f"\n===== {name} =====")
        tables, figure = make(loaded[table_name, group], config, path)
        base.print_tables(tables)
        plt.close(figure)
        print(f"\nWrote {path}")


def main() -> None:
    """Write the EDA 2 figures of the project config."""
    matplotlib.use("Agg")   # draws to files, so no window opens
    run(load_config())


def _prices(tables: ZoneTables) -> dict[str, pd.Series]:
    """Return the price column of every table."""
    return {zone: table[PRICE] for zone, table in tables.items()}


def _by_zone(rows: dict) -> pd.DataFrame:
    """Return a table with one row per zone from one set of values per zone."""
    return pd.DataFrame.from_dict(rows, orient="index")


def _column(shares: dict[str, dict[str, pd.DataFrame]], row: str, column: str) -> pd.DataFrame:
    """Return one column of the share_by_bin tables of one row label, with one column per zone."""
    return pd.DataFrame({zone: by_row[row][column] for zone, by_row in shares.items()})


def _period_note(tables: ZoneTables, market_tz: str) -> str:
    """Return a sentence with the first and the last delivery day of the tables."""
    return base._period_note(_prices(tables), market_tz)


def _period_summary(drivers: pd.DataFrame, labels: pd.Series) -> pd.DataFrame:
    """Return per period the hours, the price level and its tie to the residual load."""
    rows = {}
    for period in stats.PERIODS:
        part = drivers[labels == period]
        price = part[PRICE]
        rows[period] = {"hours": len(part), "mean": price.mean(), "median": price.median(),
                        "q05": price.quantile(0.05), "q95": price.quantile(0.95),
                        "negative_hours": int(price_stats.negative_flags(price).sum()),
                        "rank_correlation_with_residual_load":
                            stats.rank_correlation(part[stats.RESIDUAL], price)["rank_correlation"]}
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("period")


def _regional_by_share(daily: pd.Series, regional_working: pd.DatetimeIndex,
                       reference: pd.DatetimeIndex, regional: dict, subdivision_count: int,
                       window: int, edges: list[float]) -> pd.DataFrame:
    """Return per share of subdivisions the regional holidays and their price difference.

    Output: one row per group of share_groups with days and the median of
        matched_difference against the reference days.
    """
    shares = pd.Series([regional[day] / subdivision_count for day in regional_working.date],
                       index=regional_working, dtype=float)
    groups, order = stats.share_groups(shares, edges)
    differences = stats.matched_difference(daily, regional_working, reference, window)
    by_group = differences.groupby(groups.to_numpy())
    return pd.DataFrame({"days": by_group.count().reindex(order, fill_value=0),
                         "median": by_group.median().reindex(order)})


if __name__ == "__main__":
    main()
