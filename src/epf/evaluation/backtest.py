"""The backtest: one forecast per delivery day, from inputs cut to that day.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.evaluation.backtest --model naive --split validation

One run scores a model on the validation or the test days, for experiment H
(hourly table) and experiment Q (15-minute table) and every zone of the
config. --experiment H or --experiment Q runs one of the two. The core zones
run first and their files are written before the extra zones start. The test
days are open only to the models listed under backtest.test_models.

A model is an entry under models in the config, and --model takes its name.
An entry may hold history_days, the days of history the model receives. An
entry without it uses backtest.history_days.

For every delivery day the loop cuts the table with day_inputs (see
epf.evaluation.cutoff), hands the result to the model and takes back one
forecast per market time unit. A zone with a weather point also has its
weather table cut and handed over. The holiday dates of the country of the
zone are handed over too, so a model need not know its zone. The actual
prices of the day stay here and are set beside the forecast only after the
model has answered.

A model has a name, its settings as params, and two methods:
    fit(inputs)      called on the first scored day and then every
                     refit_every_days delivery days
    predict(inputs)  returns a price series on inputs.target_index

The command prints its checks per zone and experiment. A failed check ends it
with an error, and the files of that zone group are not written.

Tables have a UTC index. Delivery days are defined in market time.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import numpy as np
import pandas as pd

from epf.config import GROUP_ORDER, REPO_ROOT, Zone, load_config, ordered_zones
from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.data.resolution import check_utc_index
from epf.data.splits import TEST, VALIDATION, split_range
from epf.data.validate import HOURLY, QUARTER_HOUR, WEATHER_TABLE, table_path
from epf.evaluation import results
from epf.evaluation.cutoff import (
    Columns,
    DayInputs,
    WeatherRule,
    check_columns,
    cut_columns,
    day_inputs,
    weather_rule,
)
from epf.evaluation.metrics import daily_losses, mae, relative_mae, rmse
from epf.features.builder import feature_settings
from epf.features.holiday_calendar import holiday_dates
from epf.models import lgbm
from epf.models.naive import SeasonalNaive
from epf.models.stats import StatsModel
from epf.seed import set_seed

FORECAST = "forecast"
ACTUAL = "actual"
ALL_HISTORY = "all"
DAY_FORMAT = "%Y-%m-%d"
KEYS = ["model", "experiment", "split", "zone"]
ROW_COLUMNS = [
    "run_started_utc", "model", "model_params", "experiment", "split", "zone", "group",
    "first_day", "last_day", "days", "mtus", "empty_forecasts", "mae", "rmse", "naive_mae",
    "relative_mae", "wall_seconds", "peak_memory_mb", "hardware", "seed", "refit_every_days",
    "history_days", "data_start", "data_end", "validation_start", "test_start",
]

Day = tuple[pd.Timestamp, pd.Timestamp]   # 00:00 market time on D and on D+1
MakeIndex = Callable[[pd.Timestamp, pd.Timestamp], pd.DatetimeIndex]

# Experiment name to its table and the function that gives the market time units.
EXPERIMENTS: dict[str, tuple[str, MakeIndex]] = {
    "H": (HOURLY, hourly_index),
    "Q": (QUARTER_HOUR, quarter_hour_index),
}


class Model(Protocol):
    """What the backtest asks of a model."""

    name: str

    @property
    def params(self) -> dict: ...

    def fit(self, inputs: DayInputs) -> None: ...

    def predict(self, inputs: DayInputs) -> pd.Series: ...


@dataclass(frozen=True)
class ZoneResult:
    """The outcome of one zone and experiment."""

    row: dict                 # one row of backtest_{group}.csv. Empty when a check failed early.
    daily: pd.DataFrame       # the rows of daily_{group}.csv
    scored: pd.DataFrame      # forecast and actual per market time unit
    checks: dict[str, bool]   # check name to passed


def run_days(table: pd.DataFrame, days: list[Day], make_index: MakeIndex, model: Model,
             columns: Columns, refit_every_days: int,
             history_days: int | None = None, weather: pd.DataFrame | None = None,
             rule: WeatherRule | None = None,
             holidays: frozenset[date] = frozenset()) -> tuple[pd.DataFrame, float]:
    """Forecast every delivery day of a list and set the actual prices beside the forecasts.

    Input: a table with a UTC index, the delivery days as (day start, next
        day start) in market time, the function that gives the market time
        units of a day (hourly_index or quarter_hour_index), the model, the
        columns under each cut, the number of days between two fits, and the
        days of history a model receives (None for all). Optionally the
        weather table with a UTC index, and its rule. Optionally the holiday
        dates, as calendar dates in market time. The model receives all of
        them on every day.
    Output: a frame with a UTC index and the columns forecast and actual,
        one row per market time unit of the days, then the seconds the loop
        took. The time covers the cuts, fit and predict.
    Raises ValueError when a table column stands under no cut or a forecast
        is not on the market time units of its day.
    """
    check_columns(table, columns)
    forecasts = []
    started = time.perf_counter()
    for number, (day_start, day_end) in enumerate(days):
        inputs = day_inputs(table, day_start, day_end, make_index(day_start, day_end), columns,
                            history_days, weather, rule, holidays)
        if number % refit_every_days == 0:
            model.fit(inputs)
        forecasts.append(checked_forecast(model.predict(inputs), inputs.target_index))
    seconds = time.perf_counter() - started

    forecast = pd.concat(forecasts)
    actual = table.loc[forecast.index, columns.price]
    return pd.DataFrame({FORECAST: forecast, ACTUAL: actual}), seconds


def checked_forecast(forecast: pd.Series, target_index: pd.DatetimeIndex) -> pd.Series:
    """Return a forecast as numbers after checking that it answers the right market time units.

    Raises ValueError when the forecast is not a series on exactly target_index.
    """
    if not isinstance(forecast, pd.Series) or not forecast.index.equals(target_index):
        raise ValueError("The forecast does not have the index of the market time units "
                         f"of the delivery day that starts at {target_index[0]}.")
    return forecast.astype(float).rename(FORECAST)


def build_model(config: dict, name: str) -> Model:
    """Return the model with a name, set up from its entry under models in the config.

    The entry named naive is the seasonal naive forecast. Every other entry
    names its family. An entry of the family lgbm is the LightGBM model. It
    also gets the feature settings, the columns under each cut, the weather
    rule and the seed of the config, and only such an entry needs the
    sections features and open_meteo. An entry of any other family is a
    statistical model.
    Raises ValueError for a name that has no entry, for an entry without a
        family, for an lgbm entry in a config without one of its two
        sections and for settings that the model refuses.
    """
    entries = config["models"]
    if name not in entries:
        raise ValueError(f"Unknown model '{name}'. Known: {sorted(entries)}.")
    if name == SeasonalNaive.name:
        return SeasonalNaive(entries[name]["lag_days"])
    if "family" not in entries[name]:
        raise ValueError(f"The model entry '{name}' names no family.")
    if entries[name]["family"] == lgbm.FAMILY:
        missing = [section for section in ("features", "open_meteo") if section not in config]
        if missing:
            raise ValueError(f"The model entry '{name}' is of the family {lgbm.FAMILY}, which "
                             f"needs the config sections {missing}.")
        return lgbm.LgbmModel(name, entries[name], feature_settings(config), cut_columns(config),
                              weather_rule(config), set_seed(config))
    return StatsModel(name, entries[name])


def model_history(config: dict, name: str) -> int | None:
    """Return the days of history a model receives. None means every row from the first one.

    The value is history_days of the model entry, or backtest.history_days
    when the entry does not have it.
    """
    return config["models"][name].get("history_days", config["backtest"]["history_days"])


def check_experiments(experiments: list[str]) -> None:
    """Refuse an experiment name that is not a key of EXPERIMENTS."""
    unknown = [name for name in experiments if name not in EXPERIMENTS]
    if unknown:
        raise ValueError(f"Unknown experiments {unknown}. Known: {list(EXPERIMENTS)}.")


def check_split_allowed(config: dict, model_name: str, split: str) -> None:
    """Refuse the test days for a model that backtest.test_models does not list."""
    allowed = config["backtest"]["test_models"]
    if split == TEST and model_name not in allowed:
        raise ValueError(f"Model '{model_name}' may not be scored on the test days. "
                         f"backtest.test_models lists {allowed}.")


def read_table(config: dict, table_name: str, zone_key: str, end: pd.Timestamp) -> pd.DataFrame:
    """Read one processed table and keep the rows before end.

    Input: the config, a table name (HOURLY or QUARTER_HOUR), a zone key and
        the end of the scored split in market time.
    Output: the table with a UTC index. In a validation run end is the start
        of the test set, so no row of a test day is kept.
    """
    path = table_path(REPO_ROOT / config["paths"]["processed"], table_name, zone_key)
    table = pd.read_parquet(path)
    check_utc_index(table)
    return table[table.index < end]


def read_weather(config: dict, zone: Zone, end: pd.Timestamp) -> pd.DataFrame | None:
    """Read the weather table of a zone and keep the rows before end.

    Input: the config, the zone and the end of the scored split in market time.
    Output: the table with a UTC index, or None for a zone without a weather point.
    """
    if zone.weather_point is None:
        return None
    return read_table(config, WEATHER_TABLE, zone.key, end)


def zone_holidays(zone: Zone, first: pd.Timestamp, end: pd.Timestamp) -> frozenset[date]:
    """Return the holiday dates of the country of a zone for the years from first to end.

    Input: the zone, the first moment of its table and the end of the period
        the caller covers, both in market time. The backtest hands over the
        end of the scored split, the feature build the end of the days it
        builds.
    Output: the dates of the holiday categories of the zone, for every whole
        year from the year of first to the year of end. They are calendar
        dates in market time.
    """
    return frozenset(holiday_dates(zone.holiday_country, zone.holiday_categories,
                                   range(first.year, end.year + 1)))


def lag_check_days(days: list[Day], lag_days: int) -> list[Day]:
    """Return the first, the middle and the last day that has no clock change before it.

    Input: delivery days, and the lag of the naive forecast in days.
    Output: up to three days. On each of them the time from 00:00 on the day
        lag_days before to the end of the day is a whole number of 24 hours,
        so the naive forecast must equal the price lag_days times 24 hours earlier.
    """
    whole = timedelta(days=lag_days + 1)
    plain = [(day_start, day_end) for day_start, day_end in days
             if day_end - pd.Timestamp(day_start.date() - timedelta(days=lag_days),
                                       tz=day_start.tz) == whole]
    if not plain:
        return []
    return [plain[0], plain[len(plain) // 2], plain[-1]]


def matches_price_before(scored: pd.DataFrame, prices: pd.Series, day: Day,
                         lag_days: int) -> bool:
    """Return True when the forecasts of a day equal the prices lag_days times 24 hours before.

    Input: the scored frame, the price column of the table, one delivery day
        and the lag in days. The comparison reads the table and does not call
        the naive model.
    """
    day_start, day_end = day
    forecast = scored.loc[(scored.index >= day_start) & (scored.index < day_end), FORECAST]
    earlier = prices.reindex(forecast.index - timedelta(days=lag_days))
    return forecast.tolist() == earlier.tolist()


def count_checks(scored: pd.DataFrame, reference: pd.DataFrame,
                 expected_index: pd.DatetimeIndex, expected_days: int,
                 market_tz: str) -> dict[str, bool]:
    """Check the scored days, the market time units and that every forecast is a number.

    Input: the scored frames of the model and of the naive reference, the
        market time units of the split, its number of delivery days and the
        market time zone.
    Output: check name to passed.
    """
    scored_days = len(set(scored.index.tz_convert(market_tz).date))
    return {
        f"{expected_days} scored days": scored_days == expected_days,
        f"{len(expected_index)} market time units": scored.index.equals(expected_index),
        "no empty forecast": empty_forecasts(scored, reference) == 0,
        "every forecast is finite": not np.isinf(scored[FORECAST]).any(),
    }


def empty_forecasts(scored: pd.DataFrame, reference: pd.DataFrame) -> int:
    """Return the number of empty forecasts of the model and of the naive reference."""
    return int(scored[FORECAST].isna().sum() + reference[FORECAST].isna().sum())


def naive_checks(scored: pd.DataFrame, prices: pd.Series, days: list[Day], lag_days: int,
                 relative: float) -> dict[str, bool]:
    """Check the naive model against its definition.

    Input: its scored frame, the price column of the table, the scored days,
        its lag in days and its relative MAE.
    Output: check name to passed. The relative MAE must be 1, and on three
        days the forecast must equal the table price lag_days times 24 hours earlier.
    """
    check_days = lag_check_days(days, lag_days)
    names = ", ".join(day_start.strftime(DAY_FORMAT) for day_start, _ in check_days)
    equal = [matches_price_before(scored, prices, day, lag_days) for day in check_days]
    return {
        "relative MAE is 1": relative == 1.0,
        f"forecast equals the price {lag_days * 24} hours earlier on {names}":
            len(equal) == 3 and all(equal),
    }


def score(scored: pd.DataFrame, reference: pd.DataFrame) -> dict[str, float]:
    """Return MAE, RMSE, the MAE of the naive reference and the relative MAE, all pooled."""
    actual, forecast = scored[ACTUAL], scored[FORECAST]
    return {"mae": mae(actual, forecast), "rmse": rmse(actual, forecast),
            "naive_mae": mae(actual, reference[FORECAST]),
            "relative_mae": relative_mae(actual, forecast, reference[FORECAST])}


def daily_rows(scored: pd.DataFrame, row: dict, market_tz: str) -> pd.DataFrame:
    """Return the daily losses of one zone and experiment with the key columns in front."""
    daily = daily_losses(scored[ACTUAL], scored[FORECAST], market_tz).reset_index()
    daily["delivery_day"] = daily["delivery_day"].astype(str)
    for position, key in enumerate(KEYS):
        daily.insert(position, key, row[key])
    return daily


def backtest_zone(config: dict, zone: Zone, experiment: str, split: str, model: Model,
                  run_info: dict) -> ZoneResult:
    """Run one zone and experiment, score it and run the checks.

    Input: the config, the zone, the experiment name (a key of EXPERIMENTS),
        the split, the model and the row values that are the same for the whole run.
    Output: the results row, the daily losses, the forecasts and the checks.
        When the count of days or market time units is wrong or a forecast is
        empty or infinite, the row and the daily losses are empty and only the
        checks say why. The model receives the history length of its own
        entry. The naive reference always receives backtest.history_days.
        Both receive the weather of a zone that has a weather point, and
        the holiday dates of the country of the zone.
    """
    table_name, make_index = EXPERIMENTS[experiment]
    market_tz = config["market"]["timezone"]
    start, end = split_range(config, split)
    days = delivery_days(start, end)
    columns = cut_columns(config)
    refit = config["backtest"]["refit_every_days"]
    lag_days = config["models"][SeasonalNaive.name]["lag_days"]
    table = read_table(config, table_name, zone.key, end)
    weather = read_weather(config, zone, end)
    rule = None if weather is None else weather_rule(config)
    holidays = zone_holidays(zone, table.index[0].tz_convert(market_tz), end)

    scored, seconds = run_days(table, days, make_index, model, columns, refit,
                               model_history(config, model.name), weather, rule, holidays=holidays)
    peak = results.peak_memory_mb()
    reference, _ = run_days(table, days, make_index, SeasonalNaive(lag_days), columns, refit,
                            config["backtest"]["history_days"], weather, rule, holidays=holidays)

    checks = count_checks(scored, reference, make_index(start, end),
                          config["splits"][f"{split}_days"], market_tz)
    if not all(checks.values()):
        return ZoneResult({}, pd.DataFrame(), scored, checks)
    metrics = score(scored, reference)
    if model.name == SeasonalNaive.name:
        checks.update(naive_checks(scored, table[columns.price], days, lag_days,
                                   metrics["relative_mae"]))

    row = {**run_info, "experiment": experiment, "zone": zone.key, "group": zone.group,
           "first_day": days[0][0].strftime(DAY_FORMAT),
           "last_day": days[-1][0].strftime(DAY_FORMAT),
           "days": len(days), "mtus": len(scored),
           "empty_forecasts": empty_forecasts(scored, reference), **metrics,
           "wall_seconds": seconds, "peak_memory_mb": peak}
    return ZoneResult(row, daily_rows(scored, row, market_tz), scored, checks)


def run_group(config: dict, group: str, zones: list[Zone], split: str, model: Model,
              run_info: dict, experiments: list[str]) -> None:
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
                outcome = backtest_zone(config, zone, experiment, split, model, run_info)
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
    folder = REPO_ROOT / config["paths"]["results"]
    rows = pd.DataFrame([outcome.row for _, _, outcome in outcomes])[ROW_COLUMNS]
    daily = pd.concat([outcome.daily for _, _, outcome in outcomes], ignore_index=True)
    results.append_rows(results.results_path(folder, "backtest", group), rows)
    results.replace_rows(results.results_path(folder, "daily", group), daily, KEYS)
    print(f"\nWrote {len(rows)} rows to {results.results_path(folder, 'backtest', group)}")
    print(f"Wrote {len(daily)} rows to {results.results_path(folder, 'daily', group)}")


def print_outcome(zone_key: str, experiment: str, outcome: ZoneResult) -> None:
    """Print the numbers of one zone and experiment, then its checks."""
    row = outcome.row
    if row:
        peak = "-" if row["peak_memory_mb"] is None else f"{row['peak_memory_mb']:.0f} MB"
        print(f"{zone_key:6s} {experiment}  days {row['days']}  mtus {row['mtus']}  "
              f"empty {row['empty_forecasts']}  MAE {row['mae']:.2f}  RMSE {row['rmse']:.2f}  "
              f"relative MAE {row['relative_mae']:.4f}  {row['wall_seconds']:.2f} s  peak {peak}")
    marks = [f"{'pass' if passed else 'FAIL'}: {name}" for name, passed in outcome.checks.items()]
    print(f"{zone_key:6s} {experiment}  " + " | ".join(marks), flush=True)


def run(config: dict, model_name: str, split: str, experiments: list[str] | None = None) -> None:
    """Score one model on the validation or the test days of every zone, core zones first.

    Input: the config dictionary, a model name, the split, VALIDATION or TEST,
        and the experiments to run, keys of EXPERIMENTS. None runs all of them.
    Output: nothing. Prints numbers and checks and writes the results files
        and the forecasts. Ends with an error for an unknown model, split or
        experiment, for a model that may not see the test days, and for a
        failed check.
    """
    experiments = list(EXPERIMENTS) if experiments is None else experiments
    try:
        model = build_model(config, model_name)
        check_split_allowed(config, model_name, split)
        split_range(config, split)
        check_experiments(experiments)
    except ValueError as error:
        sys.exit(str(error))
    settings = config["backtest"]
    history = model_history(config, model_name)
    history = ALL_HISTORY if history is None else history
    run_info = {
        "run_started_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model.name, "model_params": json.dumps(model.params), "split": split,
        "hardware": results.hardware(), "seed": set_seed(config),
        "refit_every_days": settings["refit_every_days"], "history_days": history,
        "data_start": config["data"]["start"], "data_end": config["data"]["end"],
        "validation_start": config["splits"]["validation_start"],
        "test_start": config["splits"]["test_start"],
    }
    zones = ordered_zones(config)
    for group in GROUP_ORDER:
        group_zones = [zone for zone in zones if zone.group == group]
        if group_zones:
            run_group(config, group, group_zones, split, model, run_info, experiments)


def main() -> None:
    """Read the model, the split and the experiment from the command line and run the backtest."""
    parser = argparse.ArgumentParser(description="Score a model on the validation or test days.")
    parser.add_argument("--model", required=True, help="a name under models in the config")
    parser.add_argument("--split", required=True, choices=[VALIDATION, TEST])
    parser.add_argument("--experiment", choices=list(EXPERIMENTS),
                        help="run this experiment only. Without it all of them run")
    arguments = parser.parse_args()
    experiments = None if arguments.experiment is None else [arguments.experiment]
    run(load_config(), arguments.model, arguments.split, experiments)


if __name__ == "__main__":
    main()
