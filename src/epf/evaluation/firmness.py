"""How firm is the choice of a winner among the model settings of the backtest?

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.evaluation.firmness --winner NAME --models NAME [NAME ...]

Options:
    --experiment   a key of EXPERIMENTS. Without it the first one
    --split        validation or test. Without it validation
    --without      a zone key. Adds block 5, the mean without that zone
    --bootstrap    the models of the bootstrap lines. Without it every model
                   but the winner
    --resamples    the number of bootstrap resamples. Without it 2000

The command only reads and writes no file. For every zone group that has
zones in the config, the core zones first, it reads
    backtest_{group}.csv   the saved rows of the backtest, the newest row per
                           model and zone
    daily_{group}.csv      the saved losses per delivery day
    the forecast files     forecast and actual price per market time unit
    the processed table    its price column, to check the actual prices
and prints these blocks:
    1.  the MAE and the relative MAE computed again from the forecast files,
        without the metrics of the backtest, and checks of the files
    2.  the mean relative MAE over the zones by half of the days
    3.  the zones each model wins, its median and its mean over the zones
    4.  a bootstrap over whole delivery days: other model minus the winner
    5.  the mean relative MAE without one zone, only with --without
    6a. the relative MAE by hour of the day, per model
    6b. the same per zone, for the winner
    6c. the mean relative MAE by calendar week
    6d. for the winner, the days on which it is worse than the reference,
        and how much of its error its worst days hold

Relative MAE is the MAE of a model divided by the MAE of the seasonal naive
forecast, the reference, on the same market time units. Lower is better.
Every MAE is pooled: one mean over all market time units, so a day with more
units weighs more. Prices and errors are in EUR/MWh.

A model can have more than one run in backtest_{group}.csv. The newest row
is used then, and a line at the end of block 1 names those models. A
difference of block 1 for which a value is missing on one side is printed as
words, not as a number.

The bootstrap draws days as if one day did not depend on the day before.
Errors of neighbouring days are related, so its intervals are rather too
narrow than too wide.

Times: the index of every file is UTC. Delivery days, hours of the day and
calendar weeks are in market time, market.timezone of the config.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from epf.config import GROUP_ORDER, REPO_ROOT, load_config, ordered_zones
from epf.data.splits import TEST, VALIDATION, split_range
from epf.evaluation import results
from epf.evaluation.backtest import ACTUAL, DAY_FORMAT, EXPERIMENTS, FORECAST, read_table
from epf.evaluation.tables import newest_rows, selected_rows
from epf.models.naive import SeasonalNaive
from epf.seed import set_seed

REFERENCE = SeasonalNaive.name
RESAMPLES = 2000
INTERVAL = [2.5, 97.5]   # the bounds of the 95% interval of the bootstrap, in percent
WORST_DAYS = 6
PAIR = ["model", "zone"]
DAY = "delivery_day"
FOUR_DECIMALS = "{:.4f}".format
MISSING = "no number, a value is missing on one side"

Scored = dict[tuple[str, str], pd.DataFrame]   # (model, zone) to its forecast file


@dataclass(frozen=True)
class Request:
    """What the command line asks for."""

    winner: str                    # the model the others are compared with
    models: list[str]              # the models to compare, the winner among them
    experiment: str                # a key of EXPERIMENTS
    split: str                     # VALIDATION or TEST
    without: str | None            # the zone left out in block 5. None for no block 5
    bootstrap: list[str] | None    # the models of block 4. None for all but the winner
    resamples: int                 # the number of bootstrap resamples


@dataclass(frozen=True)
class Files:
    """What the command reads for the zones of one group. Every time index is UTC."""

    saved: pd.DataFrame            # the newest backtest row per model and zone
    left_out: list[str]            # the models with an older backtest row that is not used
    daily_mae: pd.DataFrame        # delivery days down, (model, zone) across, EUR/MWh
    daily_mtus: pd.DataFrame       # the same shape: the market time units of each day
    scored: Scored                 # forecast and actual price per market time unit
    prices: dict[str, pd.Series]   # zone to the price column of the processed table


# Reading.

def with_reference(models: list[str]) -> list[str]:
    """Return the models with the reference model in front, unless it is among them."""
    return models if REFERENCE in models else [REFERENCE, *models]


def forecast_path(config: dict, model: str, experiment: str, split: str, zone_key: str) -> Path:
    """Return the file that results.write_forecasts writes for one model and zone."""
    folder = REPO_ROOT / config["paths"]["forecasts"]
    return folder / model / experiment / split / f"{zone_key}.parquet"


def read_scored(config: dict, models: list[str], zone_keys: list[str], experiment: str,
                split: str) -> Scored:
    """Read the forecast file of every model and zone.

    Input: the config, model names, zone keys, an experiment name and a split name.
    Output: (model, zone) to a frame with the columns forecast and actual in
        EUR/MWh and a UTC index, one row per market time unit.
    Raises FileNotFoundError when a file does not exist.
    """
    scored = {}
    for model in models:
        for zone in zone_keys:
            path = forecast_path(config, model, experiment, split, zone)
            if not path.exists():
                raise FileNotFoundError(f"The forecast file {path} does not exist.")
            scored[(model, zone)] = results.read_forecasts(path)
    return scored


def read_prices(config: dict, zone_keys: list[str], experiment: str,
                split: str) -> dict[str, pd.Series]:
    """Read the price column of the processed table of every zone.

    Input: the config, zone keys, an experiment name and a split name.
    Output: zone key to the prices in EUR/MWh with a UTC index. The rows
        from the end of the split on are left out.
    """
    table_name, _ = EXPERIMENTS[experiment]
    _, end = split_range(config, split)
    column = config["backtest"]["price_column"]
    return {zone: read_table(config, table_name, zone, end)[column] for zone in zone_keys}


def rows_of_models(path: Path, models: list[str], zone_keys: list[str], experiment: str,
                   split: str) -> pd.DataFrame:
    """Read a results file and keep the rows of some models, some zones and one run.

    Input: the file, model names, zone keys, an experiment name and a split name.
    Output: the matching rows in the order of the file.
    Raises FileNotFoundError when the file does not exist and ValueError when
        no row has the experiment and the split.
    """
    rows = selected_rows(path, experiment, split, zone_keys)
    return rows[rows["model"].isin(models)]


def check_pairs(found: pd.Index, models: list[str], zone_keys: list[str], source: str) -> None:
    """Raise ValueError when a results file lacks a model and zone pair.

    Input: the (model, zone) pairs the file holds, the models and the zones
        asked for, and the name of the file.
    """
    missing = [(model, zone) for model in models for zone in zone_keys
               if (model, zone) not in found]
    if missing:
        raise ValueError(f"{source} has no row for the model and zone pairs {missing}. If a "
                         f"backtest is writing the file right now, run the command again.")


def read_saved_rows(path: Path, models: list[str], zone_keys: list[str], experiment: str,
                    split: str) -> tuple[pd.DataFrame, list[str]]:
    """Read the newest saved backtest row of every model and zone.

    Input: the file backtest_{group}.csv, model names, zone keys, an
        experiment name and a split name.
    Output: the rows with the index (model, zone), then the sorted names of
        the models that had an older row left out. A model that was run more
        than once has the row of its latest run, as in the results table.
    Raises ValueError when a model lacks a zone.
    """
    newest, left_out = newest_rows(rows_of_models(path, models, zone_keys, experiment, split))
    newest = newest.set_index(PAIR)
    check_pairs(newest.index, models, zone_keys, path.name)
    return newest, left_out


def read_daily(path: Path, models: list[str], zone_keys: list[str], experiment: str,
               split: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the saved daily losses as two tables with one row per delivery day.

    Input: the file daily_{group}.csv, model names, zone keys, an experiment
        name and a split name.
    Output: the daily MAE in EUR/MWh and the number of market time units of
        the day. Both have the delivery days as index (market time, as text,
        sorted) and one column per (model, zone).
    Raises ValueError when a model lacks a zone or a day, and when a model,
        zone and day stand in the file more than once. A backtest run
        replaces its daily rows and the file holds no start time of a run,
        so a row that stands twice was not written by the backtest and no
        newest one can be picked.
    """
    rows = rows_of_models(path, models, zone_keys, experiment, split)
    repeated = rows[rows.duplicated([*PAIR, DAY])]
    if len(repeated):
        model, zone, day = repeated.iloc[0][[*PAIR, DAY]]
        raise ValueError(f"{path.name} holds more than one row for the model {model}, the "
                         f"zone {zone} and the delivery day {day}.")
    daily_mae = rows.pivot(index=DAY, columns=PAIR, values="mae").sort_index()
    daily_mtus = rows.pivot(index=DAY, columns=PAIR, values="mtus").sort_index()
    check_pairs(daily_mae.columns, models, zone_keys, path.name)
    if daily_mae.isna().any().any():
        raise ValueError(f"{path.name}: the models do not all have the same delivery days.")
    return daily_mae, daily_mtus


def read_files(config: dict, group: str, zone_keys: list[str], request: Request) -> Files:
    """Read everything the blocks of one zone group need.

    Input: the config, the group name, its zone keys and the request.
    Output: the files of the models of the request and of the reference
        model. The saved backtest rows are those of the models of the
        request alone, since only they are compared with the forecast files.
    Raises FileNotFoundError when a file does not exist and ValueError when a
        results file lacks a row or holds one twice.
    """
    models = with_reference(request.models)
    experiment, split = request.experiment, request.split
    folder = REPO_ROOT / config["paths"]["results"]
    saved, left_out = read_saved_rows(results.results_path(folder, "backtest", group),
                                      request.models, zone_keys, experiment, split)
    daily_mae, daily_mtus = read_daily(results.results_path(folder, "daily", group), models,
                                       zone_keys, experiment, split)
    scored = read_scored(config, models, zone_keys, experiment, split)
    prices = read_prices(config, zone_keys, experiment, split)
    return Files(saved, left_out, daily_mae, daily_mtus, scored, prices)


# Relative MAE from the daily losses and from the forecast files.

def pooled_mae(daily_mae: pd.DataFrame, daily_mtus: pd.DataFrame) -> pd.Series:
    """Return the MAE over all market time units of some days, per (model, zone).

    Input: the two tables of read_daily, or some of their rows.
    Output: the daily MAE values weighted by the market time units of their
        day, in EUR/MWh. A day of 25 hours weighs more than one of 23.
    """
    return (daily_mae * daily_mtus).sum() / daily_mtus.sum()


def relative_mae_of_days(daily_mae: pd.DataFrame, daily_mtus: pd.DataFrame,
                         positions: np.ndarray, zone_keys: list[str]) -> pd.DataFrame:
    """Return the relative MAE per model and zone over some delivery days.

    Input: the two tables of read_daily, the row numbers of the days to use
        and the zone keys in the order of the columns. A row number may
        occur more than once, as in a bootstrap resample.
    Output: one row per model, one column per zone. A cell is the pooled MAE
        of the model over the days divided by the pooled MAE of the
        reference model over the same days.
    """
    pooled = pooled_mae(daily_mae.iloc[positions], daily_mtus.iloc[positions])
    table = pooled.unstack("zone")[zone_keys].rename_axis(index=None, columns=None)
    return table / table.loc[REFERENCE]


def absolute_errors(scored: pd.DataFrame) -> pd.Series:
    """Return the absolute error per market time unit of one forecast file, UTC index."""
    return (scored[ACTUAL] - scored[FORECAST]).abs()


# Block 1.

def recomputed_mae(scored: Scored, models: list[str], zone_keys: list[str]) -> pd.DataFrame:
    """Compute the MAE and the relative MAE again from the forecast files.

    Input: the forecast files, with those of the reference model, the models
        and the zones.
    Output: the index (model, zone) and the columns mae, in EUR/MWh, and
        relative_mae.
    """
    rows = {}
    for model in models:
        for zone in zone_keys:
            mae = float(absolute_errors(scored[(model, zone)]).mean())
            reference_mae = float(absolute_errors(scored[(REFERENCE, zone)]).mean())
            rows[(model, zone)] = {"mae": mae, "relative_mae": mae / reference_mae}
    return pd.DataFrame.from_dict(rows, orient="index")


def largest_relative_difference(new: pd.Series, old: pd.Series) -> float:
    """Return the largest |new - old| / |old| of two series.

    Output: NaN when a value is empty or stands in one of the series only,
        so that a missing value is not passed over as no difference.
    """
    return float(((new - old).abs() / old.abs()).max(skipna=False))


def difference_to_saved(new: pd.DataFrame, saved: pd.DataFrame) -> float:
    """Return how far the recomputed numbers are from the saved backtest rows.

    Input: the frame of recomputed_mae and the rows of read_saved_rows.
    Output: the largest relative difference of the MAE and of the relative
        MAE. NaN when a saved value is empty.
    """
    old = saved.loc[new.index]
    differences = [largest_relative_difference(new[column], old[column])
                   for column in ("mae", "relative_mae")]
    # np.max keeps a NaN. The built-in max can lose one, depending on the order.
    return float(np.max(differences))


def difference_to_daily(new: pd.DataFrame, daily_mae: pd.DataFrame,
                        daily_mtus: pd.DataFrame) -> float:
    """Return how far the MAE pooled from the daily file is from the recomputed MAE.

    Input: the frame of recomputed_mae and the two tables of read_daily.
    Output: the largest relative difference over the model and zone pairs.
        NaN when a value is missing on one side.
    """
    return largest_relative_difference(pooled_mae(daily_mae, daily_mtus)[new.index], new["mae"])


def split_index(config: dict, experiment: str, split: str) -> pd.DatetimeIndex:
    """Return the market time units of a split as a UTC index."""
    _, make_index = EXPERIMENTS[experiment]
    return make_index(*split_range(config, split))


def file_checks(scored: Scored, prices: dict[str, pd.Series],
                expected: pd.DatetimeIndex) -> dict[str, int]:
    """Check every forecast file against the split and the processed table.

    Input: the forecast files, the prices of read_prices and the market time
        units of the split, all with a UTC index.
    Output: four counts over all files:
        outside        forecasts before the first or after the last unit of the split
        wrong_count    files whose index is not exactly the units of the split
        empty          forecasts without a value
        actual_differs actual prices that are not the price of the processed table
    """
    counts = {"outside": 0, "wrong_count": 0, "empty": 0, "actual_differs": 0}
    for (_, zone), frame in scored.items():
        price = prices[zone].reindex(frame.index)
        same = (frame[ACTUAL] == price) | (frame[ACTUAL].isna() & price.isna())
        outside = (frame.index < expected[0]) | (frame.index > expected[-1])
        counts["outside"] += int(outside.sum())
        counts["wrong_count"] += int(not frame.index.equals(expected))
        counts["empty"] += int(frame[FORECAST].isna().sum())
        counts["actual_differs"] += int((~same).sum())
    return counts


def daily_mae_of_files(scored: Scored, market_tz: str) -> pd.DataFrame:
    """Compute the MAE per delivery day again from the forecast files.

    Input: the forecast files and the market time zone.
    Output: the shape of the daily MAE table of read_daily: delivery days in
        market time as text down, (model, zone) across.
    """
    columns = {}
    for pair, frame in scored.items():
        errors = absolute_errors(frame)
        days = errors.index.tz_convert(market_tz).strftime(DAY_FORMAT)
        columns[pair] = errors.groupby(days).mean()
    return pd.DataFrame(columns)


def largest_daily_difference(scored: Scored, daily_mae: pd.DataFrame, market_tz: str) -> float:
    """Return the largest difference of one daily MAE in the daily file to the forecast files.

    Input: the forecast files, the daily MAE table of read_daily and the
        market time zone.
    Output: the difference in EUR/MWh. NaN when a delivery day stands in
        the daily file or in the forecast files only.
    """
    from_files = daily_mae_of_files(scored, market_tz)
    differences = (from_files - daily_mae[from_files.columns]).abs()
    return float(differences.max(skipna=False).max(skipna=False))


def difference_text(difference: float, unit: str = "") -> str:
    """Return a difference of block 1 as it is printed.

    Input: the difference, NaN when a value was missing on one side of the
        comparison, and the unit to print after the number.
    Output: the number with two digits, such as 4.3e-16, or words for NaN.
    """
    return MISSING if np.isnan(difference) else f"{difference:.1e}{unit}"


def zones_text(zones: int) -> str:
    """Return a number of zones as it is printed: 1 zone, 7 zones."""
    return f"{zones} zone" if zones == 1 else f"{zones} zones"


def print_recompute(config: dict, files: Files, zone_keys: list[str], request: Request) -> None:
    """Print block 1: the saved numbers against the forecast files.

    Input: the config, the files of read_files, the zone keys of the group
        and the request.
    Output: nothing. A difference for which a value was missing on one side
        is printed as words, not as a number. The last line is there only
        when a model had more than one run.
    """
    new = recomputed_mae(files.scored, request.models, zone_keys)
    expected = split_index(config, request.experiment, request.split)
    counts = file_checks(files.scored, files.prices, expected)
    days = sorted(set(files.daily_mae[request.models].count()))
    to_saved = difference_to_saved(new, files.saved)
    to_daily = difference_to_daily(new, files.daily_mae, files.daily_mtus)
    per_day = largest_daily_difference(files.scored, files.daily_mae,
                                       config["market"]["timezone"])
    print("\n1. Recompute from the forecast files, without the harness metrics")
    print(f"   {len(new)} model and zone pairs. Largest relative difference of MAE and "
          f"relative MAE to the saved rows: {difference_text(to_saved)}")
    print(f"   forecasts outside the {request.split} days or not {len(expected)} per zone: "
          f"{counts['outside'] + counts['wrong_count']}. Actual prices that differ from the "
          f"processed table: {counts['actual_differs']}. Empty forecasts: {counts['empty']}")
    print(f"   (these three counts are over the files of the given models and of {REFERENCE})")
    print(f"   mean of the daily MAE values, weighted by their market time units, against the "
          f"pooled MAE, largest relative difference: {difference_text(to_daily)}. "
          f"Days per model and zone: {days}")
    print(f"   largest difference of one daily MAE in the daily file to the forecast files: "
          f"{difference_text(per_day, ' EUR/MWh')}")
    if files.left_out:
        print(f"   More than one run, newest row used: {', '.join(files.left_out)}.")


# Blocks 2 to 5.

def halves_table(daily_mae: pd.DataFrame, daily_mtus: pd.DataFrame, models: list[str],
                 zone_keys: list[str]) -> pd.DataFrame:
    """Return the mean relative MAE over the zones by half of the days.

    Input: the two tables of read_daily, the models to show and the zones.
    Output: one row per model and three columns: the first half of the
        delivery days, the last half and all days. A half holds whole days:
        the first half the first n // 2 days, the last half the rest. The
        rows are sorted by the column of all days, the lowest first. Equal
        values keep the order of models.
    """
    days = len(daily_mae)
    middle = days // 2
    parts = {f"first {middle} days": np.arange(0, middle),
             f"last {days - middle} days": np.arange(middle, days),
             f"all {days} days": np.arange(0, days)}
    table = pd.DataFrame({
        name: relative_mae_of_days(daily_mae, daily_mtus, positions, zone_keys).mean(axis=1)
        for name, positions in parts.items()})
    return table.loc[models].sort_values(f"all {days} days", kind="stable")


def print_halves(halves: pd.DataFrame, zones: int) -> None:
    """Print block 2 from the frame of halves_table and the number of zones."""
    print(f"\n2. Mean relative MAE over the {zones_text(zones)}, by half of the days")
    print(halves.to_string(float_format=FOUR_DECIMALS))


def zones_won(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Count how often each model is the best of a zone.

    Input: the relative MAE of all days, models down and zones across.
    Output: a frame with one row per model in the order of the input: the
        zones it wins, and the median and the mean of its relative MAE over
        the zones. Then zone to its best model. Of two models that are equal
        in a zone, the one that stands higher in the input wins the zone.
    """
    best = table.idxmin()
    summary = pd.DataFrame({
        "zones won": best.value_counts().reindex(table.index, fill_value=0),
        "median over zones": table.median(axis=1),
        "mean": table.mean(axis=1)})
    return summary, best


def print_zones_won(table: pd.DataFrame) -> None:
    """Print block 3 from the relative MAE of all days, models down and zones across."""
    summary, best = zones_won(table)
    print(f"\n3. How often is each model the best of the {len(table)} in a zone, "
          f"and its median and mean over the zones")
    print(summary.to_string(float_format=FOUR_DECIMALS))
    print(f"   best model per zone: {best.to_dict()}")


def bootstrap_means(daily_mae: pd.DataFrame, daily_mtus: pd.DataFrame, zone_keys: list[str],
                    resamples: int, seed: int) -> pd.DataFrame:
    """Draw whole delivery days with replacement and return the mean relative MAE per resample.

    Input: the two tables of read_daily, the zones, the number of resamples
        and the seed of the random number generator.
    Output: one row per resample, one column per model: its mean relative
        MAE over the zones. A resample draws as many days as there are, with
        replacement. The same drawn days are used for every model, every
        zone and the reference model, so the drawn days do not depend on the
        models.
    """
    generator = np.random.default_rng(seed)
    days = len(daily_mae)
    means = []
    for _ in range(resamples):
        positions = generator.integers(0, days, size=days)
        table = relative_mae_of_days(daily_mae, daily_mtus, positions, zone_keys)
        means.append(table.mean(axis=1))
    return pd.DataFrame(means)


def bootstrap_lines(means: pd.DataFrame, winner: str, others: list[str]) -> list[str]:
    """Return one line per other model: its difference to the winner over the resamples.

    Input: the frame of bootstrap_means, the winner and the other models.
    Output: per other model the mean of other minus winner, the bounds of
        the 95% interval, and the share of resamples with a difference above
        0. In those the winner is better.
    """
    width = max((len(name) for name in others), default=0)
    lines = []
    for other in others:
        difference = means[other] - means[winner]
        low, high = np.percentile(difference, INTERVAL)
        share = (difference > 0).mean()
        lines.append(f"{other:<{width}}  mean {difference.mean():+.4f}   95% interval "
                     f"{low:+.4f} to {high:+.4f}   share of resamples where {winner} is "
                     f"better: {share:.1%}")
    return lines


def print_bootstrap(files: Files, zone_keys: list[str], request: Request, ordered: list[str],
                    seed: int) -> None:
    """Print block 4: the bootstrap over whole days.

    Input: the files, the zones, the request, the models in the order of
        block 2 and the seed. Without request.bootstrap every model but the
        winner gets a line.
    """
    others = request.bootstrap or [name for name in ordered if name != request.winner]
    means = bootstrap_means(files.daily_mae, files.daily_mtus, zone_keys, request.resamples,
                            seed)
    print(f"\n4. Bootstrap over the {len(files.daily_mae)} days ({request.resamples} resamples "
          f"of whole days, seed {seed}):")
    print(f"   difference in mean relative MAE over the {zones_text(len(zone_keys))}, other "
          f"model minus {request.winner}")
    for line in bootstrap_lines(means, request.winner, others) or ["no other model was given"]:
        print(f"   {line}")


def means_without(table: pd.DataFrame, without: str) -> pd.Series:
    """Return the mean relative MAE over the zones with one zone left out.

    Input: the relative MAE of all days, models down and zones across, and
        the zone to leave out.
    Output: one value per model, the lowest first. Equal values keep the
        order of the input.
    """
    return table.drop(columns=without).mean(axis=1).sort_values(kind="stable")


def print_without(table: pd.DataFrame, without: str) -> None:
    """Print block 5 from the relative MAE of all days and the zone to leave out."""
    print(f"\n5. Mean relative MAE over the {zones_text(table.shape[1] - 1)} without {without}")
    print(means_without(table, without).to_string(float_format=FOUR_DECIMALS))


# Block 6.

def hourly_mae(scored: pd.DataFrame, market_tz: str) -> pd.Series:
    """Return the MAE per hour of the day of one forecast file.

    Input: one forecast file with a UTC index and the market time zone.
    Output: index 0 to 23, the hour of the day in market time in which the
        market time unit starts. Each value is pooled over all days, in EUR/MWh.
    """
    errors = absolute_errors(scored)
    hours = pd.Index(errors.index.tz_convert(market_tz).hour, name="hour")
    return errors.groupby(hours).mean()


def hourly_relative_mae(scored: Scored, model: str, zone_keys: list[str],
                        market_tz: str) -> pd.DataFrame:
    """Return the relative MAE of one model per hour of the day and zone.

    Input: the forecast files, the model, the zones and the market time zone.
    Output: the hours of the day in market time down, the zones across. A
        cell is the MAE of the model in that hour divided by the MAE of the
        reference model in that hour.
    """
    return pd.DataFrame({
        zone: hourly_mae(scored[(model, zone)], market_tz)
        / hourly_mae(scored[(REFERENCE, zone)], market_tz)
        for zone in zone_keys})


def hours_by_model(scored: Scored, models: list[str], zone_keys: list[str],
                   market_tz: str) -> pd.DataFrame:
    """Return the relative MAE per hour of the day and model, as the mean over the zones.

    Input: the forecast files, the models, the zones and the market time zone.
    Output: the hours of the day in market time down, the models across.
    """
    return pd.DataFrame({
        model: hourly_relative_mae(scored, model, zone_keys, market_tz).mean(axis=1)
        for model in models})


def print_hours(scored: Scored, models: list[str], winner: str, zone_keys: list[str],
                market_tz: str) -> None:
    """Print the two hour tables of block 6.

    Input: the forecast files, the models of the first table in the order
        of its columns, the winner, whose zones the second table shows, the
        zones and the market time zone.
    Output: nothing. The hours of the day are in market time.
    """
    by_zone = hourly_relative_mae(scored, winner, zone_keys, market_tz)
    by_zone["mean"] = by_zone.mean(axis=1)
    print(f"\n6a. Relative MAE by hour of the day ({market_tz}), mean over the "
          f"{zones_text(len(zone_keys))}")
    print(hours_by_model(scored, models, zone_keys, market_tz)
          .to_string(float_format=FOUR_DECIMALS))
    print(f"\n6b. Relative MAE of {winner} by hour of the day ({market_tz}) and zone")
    print(by_zone.to_string(float_format=FOUR_DECIMALS))


def weeks_table(daily_mae: pd.DataFrame, daily_mtus: pd.DataFrame, models: list[str],
                zone_keys: list[str]) -> pd.DataFrame:
    """Return the mean relative MAE over the zones by calendar week.

    Input: the two tables of read_daily, the models to show and the zones.
    Output: one row per week, named by its Monday. The column days is the
        number of delivery days of the split in that week, then one column
        per model. A week runs from Monday to Sunday in market time. The
        first and the last week of a split can hold fewer than seven days.
    """
    days = pd.to_datetime(daily_mae.index)
    mondays = (days - pd.to_timedelta(days.weekday, unit="D")).strftime(DAY_FORMAT)
    counts, means = {}, {}
    for monday in mondays.unique():
        positions = np.flatnonzero(mondays == monday)
        table = relative_mae_of_days(daily_mae, daily_mtus, positions, zone_keys)
        counts[monday] = len(positions)
        means[monday] = table.mean(axis=1)[models]
    weeks = pd.DataFrame.from_dict(means, orient="index").rename_axis("week from")
    weeks.insert(0, "days", pd.Series(counts))
    return weeks


def print_weeks(weeks: pd.DataFrame, zones: int) -> None:
    """Print the week table of block 6 from the frame of weeks_table and the number of zones."""
    print(f"\n6c. Mean relative MAE over the {zones_text(zones)} by calendar week "
          f"(Monday to Sunday)")
    print(weeks.to_string(float_format=FOUR_DECIMALS))


def days_table(daily_mae: pd.DataFrame, daily_mtus: pd.DataFrame, winner: str,
               zone_keys: list[str]) -> pd.DataFrame:
    """Return how the errors of the winner are spread over the delivery days, per zone.

    Input: the two tables of read_daily, the winner and the zones.
    Output: one row per zone with
        days above    the days on which the daily MAE of the winner is above
                      the daily MAE of the reference model
        days          the delivery days of the split
        worst share   the share of the summed absolute error of the winner
                      that its WORST_DAYS worst days hold, between 0 and 1.
                      The error of a day is summed over its market time
                      units, and the worst days are those with the largest sum.
    """
    above = (daily_mae[winner] > daily_mae[REFERENCE])[zone_keys]
    summed = (daily_mae[winner] * daily_mtus[winner])[zone_keys]
    worst = pd.Series({zone: summed[zone].nlargest(WORST_DAYS).sum() for zone in zone_keys})
    table = pd.DataFrame({"days above": above.sum(), "days": above.count(),
                          "worst share": worst / summed.sum()})
    return table.rename_axis(index=None)


def print_days(days: pd.DataFrame, winner: str) -> None:
    """Print the day table of block 6 from the frame of days_table."""
    shown = pd.DataFrame({
        f"days above {REFERENCE}": days["days above"],
        "of days": days["days"],
        f"share in the {WORST_DAYS} worst days": days["worst share"].map("{:.1%}".format)})
    print(f"\n6d. Days of {winner}: delivery days with a daily MAE above {REFERENCE}, and the "
          f"share of its summed absolute error in its {WORST_DAYS} worst days")
    print(shown.to_string())
    print(f"   daily MAE above {REFERENCE} on {days['days above'].sum()} of the "
          f"{days['days'].sum()} days of all zones")


# The command.

def print_blocks(config: dict, files: Files, zone_keys: list[str], request: Request,
                 seed: int) -> None:
    """Print every block for the zones of one group.

    Input: the config, the files of read_files, the zone keys of the group,
        the request and the seed of the bootstrap.
    Output: nothing. The models stand in the order of block 2 in every later
        block.
    """
    daily_mae, daily_mtus = files.daily_mae, files.daily_mtus
    market_tz = config["market"]["timezone"]
    halves = halves_table(daily_mae, daily_mtus, request.models, zone_keys)
    ordered = list(halves.index)
    all_days = np.arange(len(daily_mae))
    table = relative_mae_of_days(daily_mae, daily_mtus, all_days, zone_keys).loc[ordered]

    print(f"\nExperiment {request.experiment}, {request.split} days {daily_mae.index[0]} to "
          f"{daily_mae.index[-1]}, zones {zone_keys}")
    print_recompute(config, files, zone_keys, request)
    print_halves(halves, len(zone_keys))
    print_zones_won(table)
    print_bootstrap(files, zone_keys, request, ordered, seed)
    if request.without in zone_keys:
        print_without(table, request.without)
    print_hours(files.scored, ordered, request.winner, zone_keys, market_tz)
    print_weeks(weeks_table(daily_mae, daily_mtus, ordered, zone_keys), len(zone_keys))
    print_days(days_table(daily_mae, daily_mtus, request.winner, zone_keys), request.winner)


def zone_groups(config: dict) -> dict[str, list[str]]:
    """Return the zone keys of every zone group that has zones, the core zones first."""
    zones = ordered_zones(config)
    groups = {group: [zone.key for zone in zones if zone.group == group]
              for group in GROUP_ORDER}
    return {group: zone_keys for group, zone_keys in groups.items() if zone_keys}


def check_request(request: Request, zone_keys: list[str]) -> None:
    """Raise ValueError when the parts of a request do not fit together.

    Input: the request and the zone keys of the config.
    """
    if request.winner not in request.models:
        raise ValueError(f"The winner {request.winner} is not among --models.")
    if len(set(request.models)) != len(request.models):
        raise ValueError("A model is named twice in --models.")
    unknown = [name for name in request.bootstrap or [] if name not in request.models]
    if unknown:
        raise ValueError(f"--bootstrap names models that are not among --models: {unknown}.")
    if request.without is not None and request.without not in zone_keys:
        raise ValueError(f"--without {request.without} is not a zone of the config.")
    if request.resamples < 1:
        raise ValueError("--resamples must be at least 1.")


def run(config: dict, request: Request) -> None:
    """Print the blocks for every zone group of the config, the core zones first.

    Input: the config dictionary and the request.
    Output: nothing. Prints the blocks and writes no file. Every file is
        read before the first line is printed. The seed of the bootstrap is
        the seed of the config, set once for all groups. Ends with one line
        when the request does not fit together, a file does not exist, a
        results file lacks a row of a model or the daily file holds a row twice.
    """
    groups = zone_groups(config)
    seed = set_seed(config)
    try:
        check_request(request, [zone for zone_keys in groups.values() for zone in zone_keys])
        files = {group: read_files(config, group, zone_keys, request)
                 for group, zone_keys in groups.items()}
    except (FileNotFoundError, ValueError) as error:
        sys.exit(str(error))
    for group, zone_keys in groups.items():
        print_blocks(config, files[group], zone_keys, request, seed)


def read_request() -> Request:
    """Read the request from the command line. An option has the name of its part of Request."""
    parser = argparse.ArgumentParser(
        description="Print how firm the choice of a winner among model settings is.")
    parser.add_argument("--winner", required=True, help="the model the others are compared with")
    parser.add_argument("--models", required=True, nargs="+",
                        help="the models to compare, the winner among them")
    parser.add_argument("--experiment", default=list(EXPERIMENTS)[0], choices=list(EXPERIMENTS))
    parser.add_argument("--split", default=VALIDATION, choices=[VALIDATION, TEST])
    parser.add_argument("--without", help="a zone key. Adds the mean without that zone")
    parser.add_argument("--bootstrap", nargs="+",
                        help="the models of the bootstrap lines. Without it all but the winner")
    parser.add_argument("--resamples", type=int, default=RESAMPLES,
                        help="the number of bootstrap resamples")
    return Request(**vars(parser.parse_args()))


def main() -> None:
    """Read the request from the command line and print the blocks."""
    request = read_request()
    run(load_config(), request)


if __name__ == "__main__":
    main()
