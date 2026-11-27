"""Quantile forecasts of the frozen LightGBM setting, scored on the validation days.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.evaluation.quantiles --split validation

The model is the entry that backtest.lightgbm_model names, fitted once per
level of backtest.quantile_levels (epf.models.lgbm.LgbmQuantileModel). Its
name in the results is the name of the entry plus _quantiles. That name is
not under backtest.test_models, so the test days are refused.

The days, the cuts, the weather, the holidays, the history length and the
days between two fits are those of the backtest command. For every delivery
day the loop cuts the table with day_inputs (see epf.evaluation.cutoff) and
hands the result to the model. --experiment H or --experiment Q runs one of
the two experiments. The core zones run first.

Each level is fitted on its own, so the values of a market time unit can
cross: a lower level can stand above a higher one. The values of every market
time unit are sorted before they are scored, and the share of market time
units that sorting changed is reported.

One row per zone and experiment goes to quantile_{group}.csv under
paths.results. Rows are only ever added, as in backtest_{group}.csv. A row
holds, after the values of the run:
    pinball_{level}    the mean pinball loss of one level, in EUR/MWh
    mean_pinball       the mean of these losses
    coverage_{p}       the share of actual prices inside the interval that
                       should hold p percent of them
    width_{p}          the mean width of that interval, in EUR/MWh
    crossing_share     the share of market time units that sorting changed
An interval runs from a level to its mirror: 0.25 to 0.75 holds 50 percent.

The sorted forecasts with the actual prices go to paths.forecasts, under the
name of the model. A second run writes these files again. The results files
of the backtest command are never opened.

The command prints its checks per zone and experiment. A failed check ends it
with an error, and the files of that zone group are not written.

Tables have a UTC index. Delivery days are defined in market time.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from epf.config import GROUP_ORDER, REPO_ROOT, Zone, load_config, ordered_zones
from epf.data.market_time import delivery_days
from epf.data.splits import TEST, VALIDATION, split_range
from epf.evaluation import results
from epf.evaluation.backtest import (
    ACTUAL,
    ALL_HISTORY,
    DAY_FORMAT,
    EXPERIMENTS,
    Day,
    MakeIndex,
    check_experiments,
    check_split_allowed,
    model_history,
    read_table,
    read_weather,
    zone_holidays,
)
from epf.evaluation.cutoff import (
    Columns,
    WeatherRule,
    check_columns,
    cut_columns,
    day_inputs,
    weather_rule,
)
from epf.evaluation.metrics import coverage, mean_pinball_loss, pinball_loss
from epf.features.builder import feature_settings
from epf.models.lgbm import LgbmQuantileModel
from epf.seed import set_seed

KIND = "quantile"        # the results file is quantile_{group}.csv
SUFFIX = "_quantiles"    # added to the name of the entry


@dataclass(frozen=True)
class ZoneQuantiles:
    """The outcome of one zone and experiment."""

    row: dict                 # one row of quantile_{group}.csv. Empty when a check failed.
    scored: pd.DataFrame      # the sorted quantiles and the actual price per market time unit
    checks: dict[str, bool]   # check name to passed


def quantile_model(config: dict) -> LgbmQuantileModel:
    """Return the quantile model of the frozen LightGBM setting.

    Input: the config. backtest.lightgbm_model names the entry under models
        and backtest.quantile_levels holds the levels.
    Output: the model, named after the entry with SUFFIX added. It gets the
        feature settings, the columns under each cut, the weather rule and
        the seed of the config, as the point model does.
    Raises ValueError when the config has no levels or no name, when the
        name has no entry, and for an entry or levels that the model refuses.
    """
    if "quantile_levels" not in config["backtest"]:
        raise ValueError("The config has no backtest.quantile_levels, the levels of the "
                         "quantile forecasts.")
    if "lightgbm_model" not in config["backtest"]:
        raise ValueError("The config has no backtest.lightgbm_model, the name of the "
                         "frozen LightGBM entry.")
    name = config["backtest"]["lightgbm_model"]
    if name not in config["models"]:
        raise ValueError(f"backtest.lightgbm_model names '{name}', which is no entry "
                         "under models.")
    return LgbmQuantileModel(name + SUFFIX, config["models"][name],
                             config["backtest"]["quantile_levels"], feature_settings(config),
                             cut_columns(config), weather_rule(config), set_seed(config))


def run_quantile_days(table: pd.DataFrame, days: list[Day], make_index: MakeIndex,
                      model: LgbmQuantileModel, columns: Columns, refit_every_days: int,
                      history_days: int | None = None, weather: pd.DataFrame | None = None,
                      rule: WeatherRule | None = None,
                      holidays: frozenset[date] = frozenset()) -> tuple[pd.DataFrame, float]:
    """Forecast the quantiles of every delivery day of a list.

    Input: as run_days of the backtest: a table with a UTC index, the
        delivery days as (day start, next day start) in market time, the
        function that gives the market time units of a day, the model, the
        columns under each cut, the number of days between two fits, and the
        days of history the model receives (None for all). Optionally the
        weather table with its rule, and the holiday dates in market time.
    Output: a frame with a UTC index, one row per market time unit of the
        days and one column per level, in EUR/MWh and not sorted, then the
        seconds the loop took. The time covers the cuts, fit and predict.
        The model receives the inputs of day_inputs and nothing else.
    Raises ValueError when a table column stands under no cut, or when the
        forecasts of a day are not on its market time units and the levels
        of the model.
    """
    check_columns(table, columns)
    frames = []
    started = time.perf_counter()
    for number, (day_start, day_end) in enumerate(days):
        inputs = day_inputs(table, day_start, day_end, make_index(day_start, day_end), columns,
                            history_days, weather, rule, holidays)
        if number % refit_every_days == 0:
            model.fit(inputs)
        frames.append(checked_quantiles(model.predict_quantiles(inputs), inputs.target_index,
                                        model.levels))
    seconds = time.perf_counter() - started
    return pd.concat(frames), seconds


def checked_quantiles(frame: pd.DataFrame, target_index: pd.DatetimeIndex,
                      levels: tuple[float, ...]) -> pd.DataFrame:
    """Return the quantile forecasts of a day as numbers after checking their rows and columns.

    Raises ValueError when the frame is not on exactly target_index, or when
        its columns are not the levels in their order.
    """
    if not isinstance(frame, pd.DataFrame) or not frame.index.equals(target_index):
        raise ValueError("The quantile forecasts do not have the index of the market time "
                         f"units of the delivery day that starts at {target_index[0]}.")
    if list(frame.columns) != list(levels):
        raise ValueError(f"The quantile forecasts have the columns {list(frame.columns)}, "
                         f"not the levels {list(levels)}.")
    return frame.astype(float)


def sort_quantiles(quantiles: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Put the values of every market time unit in ascending order.

    Input: quantile forecasts, one column per level, the levels ascending.
    Output: a frame of the same shape in which every row ascends from the
        lowest level to the highest, and a series that is True for the rows
        in which sorting moved a value. The frame that was given stays as it is.
    """
    ordered = pd.DataFrame(np.sort(quantiles.to_numpy(), axis=1), index=quantiles.index,
                           columns=quantiles.columns)
    changed = (ordered != quantiles).any(axis=1)
    return ordered, changed


def intervals(levels: list[float]) -> list[tuple[float, float]]:
    """Return the intervals that the levels give, as (low level, high level), narrowest first.

    Input: ascending levels in which every level has its mirror 1 - level.
    Output: the first level with the last, the second with the second last
        and so on, then turned around. A median has no partner and gives no interval.
    """
    pairs = [(low, high) for low, high in zip(levels, reversed(levels)) if low < high]
    return pairs[::-1]


def score(actual: pd.Series, quantiles: pd.DataFrame) -> dict[str, float]:
    """Return the pinball losses, the coverage and the width of sorted quantile forecasts.

    Input: actual prices in EUR/MWh, and the quantile forecasts on the same
        UTC index, one column per level, every row ascending.
    Output: pinball_{level} per level and mean_pinball in EUR/MWh, then per
        interval coverage_{p}, a share between 0 and 1, and width_{p}, the
        mean of high minus low in EUR/MWh. p is the share the interval
        should hold, in percent: 90 for the levels 0.05 and 0.95.
    """
    levels = list(quantiles.columns)
    scores = {f"pinball_{level:g}": pinball_loss(actual, quantiles[level], level)
              for level in levels}
    scores["mean_pinball"] = mean_pinball_loss(
        actual, {level: quantiles[level] for level in levels})
    for low, high in intervals(levels):
        # 100 * (0.95 - 0.05) is 89.99999999999999 in floating point. The format g keeps six
        # significant digits, so the label is 90.
        percent = f"{100 * (high - low):g}"
        scores[f"coverage_{percent}"] = coverage(actual, quantiles[low], quantiles[high])
        scores[f"width_{percent}"] = float((quantiles[high] - quantiles[low]).mean())
    return scores


def quantile_checks(quantiles: pd.DataFrame, ordered: pd.DataFrame,
                    expected_index: pd.DatetimeIndex, expected_days: int,
                    market_tz: str) -> dict[str, bool]:
    """Check the scored days, the market time units and the values of the quantile forecasts.

    Input: the forecasts as the model gave them and after sorting, the
        market time units of the split, its number of delivery days and the
        market time zone.
    Output: check name to passed.
    """
    scored_days = len(set(quantiles.index.tz_convert(market_tz).date))
    return {
        f"{expected_days} scored days": scored_days == expected_days,
        f"{len(expected_index)} market time units": quantiles.index.equals(expected_index),
        "no empty quantile": not quantiles.isna().any().any(),
        "every quantile is finite": not np.isinf(quantiles).any().any(),
        "every row ascends after sorting": bool((np.diff(ordered.to_numpy(), axis=1) >= 0).all()),
    }


def scored_frame(ordered: pd.DataFrame, actual: pd.Series) -> pd.DataFrame:
    """Set the actual prices beside the sorted quantile forecasts, for the forecasts file.

    Output: the columns quantile_{level} per level and actual, on the UTC index.
    """
    frame = ordered.rename(columns=lambda level: f"quantile_{level:g}")
    frame[ACTUAL] = actual
    return frame


def quantile_zone(config: dict, zone: Zone, experiment: str, split: str,
                  model: LgbmQuantileModel, run_info: dict) -> ZoneQuantiles:
    """Run one zone and experiment, sort the quantiles, score them and run the checks.

    Input: the config, the zone, the experiment name (a key of EXPERIMENTS),
        the split, the model and the row values that are the same for the
        whole run.
    Output: the results row, the sorted forecasts with the actual prices and
        the checks. When a check fails the row is empty and only the checks
        say why. The table, the days, the weather, the holidays and the days
        between two fits are read as backtest_zone reads them. The history
        length is that of the entry that backtest.lightgbm_model names.
    """
    table_name, make_index = EXPERIMENTS[experiment]
    market_tz = config["market"]["timezone"]
    start, end = split_range(config, split)
    days = delivery_days(start, end)
    columns = cut_columns(config)
    table = read_table(config, table_name, zone.key, end)
    weather = read_weather(config, zone, end)
    rule = None if weather is None else weather_rule(config)
    holidays = zone_holidays(zone, table.index[0].tz_convert(market_tz), end)

    quantiles, seconds = run_quantile_days(
        table, days, make_index, model, columns, config["backtest"]["refit_every_days"],
        model_history(config, config["backtest"]["lightgbm_model"]), weather, rule, holidays)
    peak = results.peak_memory_mb()
    ordered, changed = sort_quantiles(quantiles)
    actual = table.loc[ordered.index, columns.price]
    scored = scored_frame(ordered, actual)

    checks = quantile_checks(quantiles, ordered, make_index(start, end),
                             config["splits"][f"{split}_days"], market_tz)
    if not all(checks.values()):
        return ZoneQuantiles({}, scored, checks)
    row = {**run_info, "experiment": experiment, "zone": zone.key, "group": zone.group,
           "first_day": days[0][0].strftime(DAY_FORMAT),
           "last_day": days[-1][0].strftime(DAY_FORMAT),
           "days": len(days), "mtus": len(ordered), **score(actual, ordered),
           "crossing_share": float(changed.mean()), "wall_seconds": seconds,
           "peak_memory_mb": peak}
    return ZoneQuantiles(row, scored, checks)


def run_group(config: dict, group: str, zones: list[Zone], split: str,
              model: LgbmQuantileModel, run_info: dict, experiments: list[str]) -> None:
    """Run the experiments for the zones of one group, then write the files of the group.

    Output: nothing. Prints one line of numbers and one line of checks per
        zone and experiment. Ends with an error and writes nothing when a
        table is missing, a model input is refused or a check fails.
    """
    print(f"\n===== {group} zones, {split} days, model {model.name} =====")
    outcomes = []
    for experiment in experiments:
        for zone in zones:
            try:
                outcome = quantile_zone(config, zone, experiment, split, model, run_info)
            except (FileNotFoundError, ValueError) as error:
                sys.exit(f"{zone.key} {experiment}: {error}")
            print_outcome(zone.key, experiment, outcome)
            failed = [name for name, passed in outcome.checks.items() if not passed]
            if failed:
                sys.exit(f"{zone.key} {experiment}: failed checks: {failed}. Nothing was "
                         f"written for the {group} zones.")
            outcomes.append((zone.key, experiment, outcome))

    for zone_key, experiment, outcome in outcomes:
        results.write_forecasts(REPO_ROOT / config["paths"]["forecasts"], model.name, experiment,
                                split, zone_key, outcome.scored)
    path = results.results_path(REPO_ROOT / config["paths"]["results"], KIND, group)
    rows = pd.DataFrame([outcome.row for _, _, outcome in outcomes])
    results.append_rows(path, rows)
    print(f"\nWrote {len(rows)} rows to {path}")


def print_outcome(zone_key: str, experiment: str, outcome: ZoneQuantiles) -> None:
    """Print the numbers of one zone and experiment, then its checks."""
    row = outcome.row
    if row:
        peak = "-" if row["peak_memory_mb"] is None else f"{row['peak_memory_mb']:.0f} MB"
        shares = "  ".join(f"{name.replace('_', ' ')}% {value:.3f}"
                           for name, value in row.items() if name.startswith("coverage_"))
        print(f"{zone_key:6s} {experiment}  days {row['days']}  mtus {row['mtus']}  "
              f"mean pinball {row['mean_pinball']:.2f}  {shares}  "
              f"crossing {row['crossing_share']:.3f}  {row['wall_seconds']:.2f} s  peak {peak}")
    marks = [f"{'pass' if passed else 'FAIL'}: {name}" for name, passed in outcome.checks.items()]
    print(f"{zone_key:6s} {experiment}  " + " | ".join(marks), flush=True)


def run_values(config: dict, model: LgbmQuantileModel, split: str) -> dict:
    """Return the row values that are the same for every zone and experiment of a run.

    They are the run values of a backtest row. history_days is that of the
    entry that backtest.lightgbm_model names.
    """
    settings = config["backtest"]
    history = model_history(config, settings["lightgbm_model"])
    return {
        "run_started_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model.name, "model_params": json.dumps(model.params), "split": split,
        "hardware": results.hardware(), "seed": model.seed,
        "refit_every_days": settings["refit_every_days"],
        "history_days": ALL_HISTORY if history is None else history,
        "data_start": config["data"]["start"], "data_end": config["data"]["end"],
        "validation_start": config["splits"]["validation_start"],
        "test_start": config["splits"]["test_start"],
    }


def run(config: dict, split: str, experiments: list[str] | None = None) -> None:
    """Score the quantile forecasts on the days of a split for every zone, core zones first.

    Input: the config dictionary, the split and the experiments to run, keys
        of EXPERIMENTS. None runs all of them.
    Output: nothing. Prints numbers and checks and writes the results rows
        and the forecasts. Ends with an error for an entry or levels that
        the model refuses, for the test days, which backtest.test_models
        does not open to this model, for an unknown split or experiment and
        for a failed check.
    """
    experiments = list(EXPERIMENTS) if experiments is None else experiments
    try:
        model = quantile_model(config)
        check_split_allowed(config, model.name, split)
        split_range(config, split)
        check_experiments(experiments)
    except ValueError as error:
        sys.exit(str(error))
    run_info = run_values(config, model, split)
    zones = ordered_zones(config)
    for group in GROUP_ORDER:
        group_zones = [zone for zone in zones if zone.group == group]
        if group_zones:
            run_group(config, group, group_zones, split, model, run_info, experiments)


def main() -> None:
    """Read the split and the experiment from the command line and score the quantiles."""
    parser = argparse.ArgumentParser(
        description="Score the quantile forecasts of the frozen LightGBM setting.")
    parser.add_argument("--split", required=True, choices=[VALIDATION, TEST])
    parser.add_argument("--experiment", choices=list(EXPERIMENTS),
                        help="run this experiment only. Without it all of them run")
    arguments = parser.parse_args()
    experiments = None if arguments.experiment is None else [arguments.experiment]
    run(load_config(), arguments.split, experiments)


if __name__ == "__main__":
    main()
