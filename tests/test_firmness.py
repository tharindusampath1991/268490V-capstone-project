"""Tests for the firmness command.

They use a small synthetic project in a temporary folder: price tables,
forecast files, results rows and daily rows, written with the functions the
backtest writes them with. No network and no data files. One test reads the
zone names of the project config.

The synthetic project has the zones A, B and C and four validation days,
Friday 2026-10-23 to Monday 2026-10-26, in the market time Europe/Berlin. On
Sunday 2026-10-25 the clocks go back, so that day has 25 hours and the four
days have 97. An error is a forecast minus the actual price in EUR/MWh.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epf.config import REPO_ROOT, load_config
from epf.data.market_time import hourly_index
from epf.data.splits import TEST, VALIDATION, split_range
from epf.data.validate import HOURLY, table_path
from epf.evaluation import firmness, results
from epf.evaluation.backtest import ACTUAL, EXPERIMENTS, FORECAST, KEYS, daily_rows, score
from epf.evaluation.firmness import (
    Request,
    bootstrap_means,
    days_table,
    file_checks,
    halves_table,
    hourly_relative_mae,
    hours_by_model,
    means_without,
    read_daily,
    read_prices,
    read_request,
    read_scored,
    recomputed_mae,
    relative_mae_of_days,
    run,
    split_index,
    weeks_table,
    zones_won,
)

MARKET_TZ = "Europe/Berlin"
FIRST_RUN = "2026-11-24T10:00:00Z"
SECOND_RUN = "2026-11-25T09:30:00Z"
ZONES = ["A", "B", "C"]
HOURS = [24, 24, 25, 24]

# Model to zone to the error of each of the four days, the same on every hour of a day.
# The absolute error of poor is that of good plus 1, on every day in every zone.
ERRORS = {
    "naive": {"A": [4, 2, 6, 8], "B": [2, 2, 2, 2], "C": [2, 4, 2, 4]},
    "good": {"A": [1, -2, 6, -2], "B": [1, 1, -3, 1], "C": [1, 1, 1, 1]},
    "poor": {"A": [2, 3, 7, 3], "B": [2, 2, 4, 2], "C": [2, 2, 2, 2]},
}
WITH_COPY = {**ERRORS, "copy": ERRORS["good"]}

# The relative MAE over the four days by hand: the absolute errors summed over the 97
# hours, divided by the same sum of naive.
NAIVE_SUMS = {"A": 4 * 24 + 2 * 24 + 6 * 25 + 8 * 24, "B": 2 * 97,
              "C": 2 * 24 + 4 * 24 + 2 * 25 + 4 * 24}
GOOD = {"A": (24 + 48 + 150 + 48) / NAIVE_SUMS["A"], "B": (24 + 24 + 75 + 24) / NAIVE_SUMS["B"],
        "C": 97 / NAIVE_SUMS["C"]}
POOR = {"A": (48 + 72 + 175 + 72) / NAIVE_SUMS["A"], "B": (48 + 48 + 100 + 48) / NAIVE_SUMS["B"],
        "C": 194 / NAIVE_SUMS["C"]}


def mean(values) -> float:
    """The plain mean of some numbers."""
    values = list(values)
    return sum(values) / len(values)


def four(value: float) -> str:
    """A number as the command prints it in a table."""
    return f"{value:.4f}"


def project_config(tmp_path, groups: dict[str, str] | None = None, seed: int = 11) -> dict:
    """A config with four validation days around the clock change, and the zones by group."""
    groups = groups or {zone: "core" for zone in ZONES}
    return {
        "seed": seed,
        "market": {"timezone": MARKET_TZ},
        "paths": {"processed": str(tmp_path / "processed"),
                  "forecasts": str(tmp_path / "forecasts"),
                  "results": str(tmp_path / "results")},
        "data": {"end": "2026-10-28"},
        "splits": {"validation_start": "2026-10-23", "test_start": "2026-10-27"},
        "backtest": {"price_column": "price"},
        "zones": [{"key": key, "holiday_country": "DE", "group": group}
                  for key, group in groups.items()],
    }


def validation_hours(config: dict) -> pd.DatetimeIndex:
    """Every hour of the validation days as a UTC index."""
    return hourly_index(*split_range(config, VALIDATION))


def by_day(config: dict, values: list[float]) -> pd.Series:
    """One value per validation day, set on every hour of that day. UTC index."""
    index = validation_hours(config)
    days = index.tz_convert(MARKET_TZ).strftime("%Y-%m-%d")
    of_day = dict(zip(sorted(set(days)), values, strict=True))
    return pd.Series([float(of_day[day]) for day in days], index=index)


def by_market_hour(config: dict, base: float, hour: int, value: float) -> pd.Series:
    """The same value on every validation hour, but another one in one hour of the day.

    The hour of the day is counted in market time. UTC index.
    """
    index = validation_hours(config)
    hours = index.tz_convert(MARKET_TZ).hour
    return pd.Series(np.where(hours == hour, value, base), index=index, dtype=float)


def save_prices(config: dict) -> None:
    """Write the hourly table of every zone, with a price for the validation and test days."""
    start, _ = split_range(config, VALIDATION)
    _, end = split_range(config, TEST)
    index = hourly_index(start, end)
    for zone in config["zones"]:
        path = table_path(Path(config["paths"]["processed"]), HOURLY, zone["key"])
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"price": 40.0 + np.arange(len(index)) % 5}, index=index).to_parquet(path)


def scored_frame(config: dict, zone: str, error: pd.Series | list[float]) -> pd.DataFrame:
    """Forecast and actual price of one zone. The forecast is the table price plus the error."""
    if isinstance(error, list):
        error = by_day(config, error)
    path = table_path(Path(config["paths"]["processed"]), HOURLY, zone)
    actual = pd.read_parquet(path)["price"].loc[error.index]
    return pd.DataFrame({FORECAST: actual + error, ACTUAL: actual})


def save_runs(config: dict, errors: dict, started: str = FIRST_RUN) -> None:
    """Save one validation run per model the way the backtest does.

    Input: the config and model to zone to error, with the model naive among
        them. An error is a series on the validation hours or one value per day.
    Output: nothing. Writes the forecast files, adds the results rows and
        replaces the daily rows.
    """
    folder = Path(config["paths"]["results"])
    groups = {zone["key"]: zone["group"] for zone in config["zones"]}
    for model, by_zone in errors.items():
        for zone, error in by_zone.items():
            scored = scored_frame(config, zone, error)
            reference = scored_frame(config, zone, errors["naive"][zone])
            row = {"run_started_utc": started, "model": model, "experiment": "H",
                   "split": VALIDATION, "zone": zone, **score(scored, reference)}
            results.write_forecasts(Path(config["paths"]["forecasts"]), model, "H", VALIDATION,
                                    zone, scored)
            results.append_rows(results.results_path(folder, "backtest", groups[zone]),
                                pd.DataFrame([row]))
            results.replace_rows(results.results_path(folder, "daily", groups[zone]),
                                 daily_rows(scored, row, MARKET_TZ), KEYS)


def save_project(tmp_path, errors: dict | None = None, seed: int = 11) -> dict:
    """Write the synthetic project with the runs of some models and return its config."""
    config = project_config(tmp_path, seed=seed)
    save_prices(config)
    save_runs(config, ERRORS if errors is None else errors)
    return config


def request(**changes) -> Request:
    """What the command line asks for: good against poor, unless a test changes a part."""
    parts = {"winner": "good", "models": ["good", "poor"], "experiment": "H",
             "split": VALIDATION, "without": None, "bootstrap": None, "resamples": 50}
    return Request(**{**parts, **changes})


def daily_path(config: dict) -> Path:
    """The daily file of the core zones of the synthetic project."""
    return results.results_path(Path(config["paths"]["results"]), "daily", "core")


def project_daily(config: dict, models: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The daily MAE and the hours per day of some models, read from the synthetic project."""
    return read_daily(daily_path(config), models, ZONES, "H", VALIDATION)


def written_daily(tmp_path, days: list[str], hours: list[int],
                  maes: dict[tuple[str, str], list[float]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write a daily file by hand and read it back with read_daily.

    Input: the delivery days, the market time units of each day, and
        (model, zone) to the MAE of each day.
    """
    rows = [{"model": model, "experiment": "H", "split": VALIDATION, "zone": zone,
             "delivery_day": day, "mtus": count, "mae": float(value), "mse": float(value) ** 2}
            for (model, zone), values in maes.items()
            for day, count, value in zip(days, hours, values, strict=True)]
    path = results.results_path(tmp_path, "daily", "core")
    results.append_rows(path, pd.DataFrame(rows))
    models = sorted({model for model, _ in maes})
    zones = sorted({zone for _, zone in maes})
    return read_daily(path, models, zones, "H", VALIDATION)


def block(printed: str, start: str) -> list[str]:
    """The printed lines from the one that starts with a text up to the next empty line."""
    lines = printed.splitlines()
    first = next(number for number, line in enumerate(lines) if line.startswith(start))
    rest = lines[first:]
    return rest[:rest.index("")] if "" in rest else rest


def files_under(folder: Path) -> dict[Path, bytes]:
    """Every file under a folder with its content."""
    return {path: path.read_bytes() for path in folder.rglob("*") if path.is_file()}


# Block 1: the MAE again from the forecast files, and the file checks.

def test_the_mae_and_the_relative_mae_are_computed_from_the_forecast_files(tmp_path):
    config = save_project(tmp_path)
    scored = read_scored(config, ["naive", "good", "poor"], ZONES, "H", VALIDATION)

    table = recomputed_mae(scored, ["good", "poor"], ZONES)

    assert list(table.index) == [(model, zone) for model in ("good", "poor") for zone in ZONES]
    assert table.loc[("good", "A"), "mae"] == pytest.approx((24 + 48 + 150 + 48) / 97)
    assert table.loc[("good", "B"), "mae"] == pytest.approx((24 + 24 + 75 + 24) / 97)
    assert table.loc[("poor", "C"), "mae"] == pytest.approx(2.0)
    for zone in ZONES:
        assert table.loc[("good", zone), "relative_mae"] == pytest.approx(GOOD[zone])
        assert table.loc[("poor", zone), "relative_mae"] == pytest.approx(POOR[zone])


def test_block_1_finds_no_difference_when_the_files_fit_together(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request())

    lines = block(capsys.readouterr().out, "1. ")
    assert lines[1].strip() == ("6 model and zone pairs. Largest relative difference of MAE "
                                "and relative MAE to the saved rows: 0.0e+00")
    assert lines[2].strip() == ("forecasts outside the validation days or not 97 per zone: 0. "
                                "Actual prices that differ from the processed table: 0. "
                                "Empty forecasts: 0")
    assert lines[4].strip().endswith("Days per model and zone: [4]")
    assert lines[5].strip() == ("largest difference of one daily MAE in the daily file to the "
                                "forecast files: 0.0e+00 EUR/MWh")


def test_block_1_shows_a_saved_row_that_does_not_fit_its_forecast_file(tmp_path, capsys):
    config = save_project(tmp_path)
    changed = scored_frame(config, "A", [2, -2, 6, -2])
    results.write_forecasts(Path(config["paths"]["forecasts"]), "good", "H", VALIDATION, "A",
                            changed)

    run(config, request())

    lines = block(capsys.readouterr().out, "1. ")
    saved_mae, file_mae = (24 + 48 + 150 + 48) / 97, (48 + 48 + 150 + 48) / 97
    difference = (file_mae - saved_mae) / saved_mae
    assert f"{difference:.1e}" == "8.9e-02"
    assert lines[1].endswith("to the saved rows: 8.9e-02")
    assert lines[5].strip() == ("largest difference of one daily MAE in the daily file to the "
                                "forecast files: 1.0e+00 EUR/MWh")


def test_block_1_shows_a_saved_relative_mae_that_does_not_fit_the_reference_file(
        tmp_path, capsys):
    config = save_project(tmp_path)
    doubled = scored_frame(config, "A", [8, 4, 12, 16])
    results.write_forecasts(Path(config["paths"]["forecasts"]), "naive", "H", VALIDATION, "A",
                            doubled)

    run(config, request())

    lines = block(capsys.readouterr().out, "1. ")
    saved, from_files = GOOD["A"], (24 + 48 + 150 + 48) / (2 * NAIVE_SUMS["A"])
    assert f"{(saved - from_files) / saved:.1e}" == "5.0e-01"
    assert lines[1].endswith("to the saved rows: 5.0e-01")


def test_an_actual_price_that_differs_from_the_table_is_counted(tmp_path, capsys):
    config = save_project(tmp_path)
    path = Path(config["paths"]["forecasts"]) / "poor" / "H" / VALIDATION / "B.parquet"
    frame = pd.read_parquet(path)
    frame.iloc[[3, 50], frame.columns.get_loc(ACTUAL)] += 0.5
    frame.to_parquet(path)
    scored = read_scored(config, ["naive", "good", "poor"], ZONES, "H", VALIDATION)
    prices = read_prices(config, ZONES, "H", VALIDATION)

    counts = file_checks(scored, prices, split_index(config, "H", VALIDATION))
    run(config, request())

    assert counts == {"outside": 0, "wrong_count": 0, "empty": 0, "actual_differs": 2}
    assert ("Actual prices that differ from the processed table: 2."
            in block(capsys.readouterr().out, "1. ")[2])


def test_the_file_checks_count_missing_outside_and_empty_forecasts(tmp_path):
    config = save_project(tmp_path)
    scored = read_scored(config, ["naive", "good", "poor"], ZONES, "H", VALIDATION)
    prices = read_prices(config, ZONES, "H", VALIDATION)
    expected = split_index(config, "H", VALIDATION)
    before = scored[("good", "A")]
    hour_before = before.iloc[[0]].shift(freq="-1h")
    scored[("good", "A")] = pd.concat([hour_before, before])
    scored[("good", "B")] = scored[("good", "B")].iloc[:-1]
    scored[("poor", "C")] = scored[("poor", "C")].assign(
        **{FORECAST: scored[("poor", "C")][FORECAST].where(expected != expected[5])})

    counts = file_checks(scored, prices, expected)

    assert len(expected) == 97
    assert counts == {"outside": 1, "wrong_count": 2, "empty": 1, "actual_differs": 1}


def test_the_price_table_is_read_from_the_folder_and_the_column_of_the_config(tmp_path):
    config = save_project(tmp_path)

    prices = read_prices(config, ["B"], "H", VALIDATION)

    hours = validation_hours(config)
    assert list(prices) == ["B"]
    assert prices["B"].index.equals(hours)
    assert prices["B"].tolist() == [40.0 + number % 5 for number in range(97)]


# Block 2: the halves.

def test_a_half_is_pooled_over_its_days_and_weighted_by_the_market_time_units(tmp_path):
    days = ["2026-03-28", "2026-03-29", "2026-10-25", "2026-10-26"]
    hours = [24, 23, 25, 24]
    daily_mae, daily_mtus = written_daily(tmp_path, days, hours, {
        ("naive", "A"): [4, 2, 6, 8], ("naive", "B"): [2, 2, 2, 2],
        ("good", "A"): [1, 2, 6, 2], ("good", "B"): [1, 1, 3, 1]})

    table = halves_table(daily_mae, daily_mtus, ["good"], ["A", "B"])

    first = mean([(1 * 24 + 2 * 23) / (4 * 24 + 2 * 23), (1 * 24 + 1 * 23) / (2 * 24 + 2 * 23)])
    last = mean([(6 * 25 + 2 * 24) / (6 * 25 + 8 * 24), (3 * 25 + 1 * 24) / (2 * 25 + 2 * 24)])
    whole = mean([(24 + 46 + 150 + 48) / (96 + 46 + 150 + 192), (24 + 23 + 75 + 24) / (2 * 96)])
    assert list(table.columns) == ["first 2 days", "last 2 days", "all 4 days"]
    assert table.loc["good"].tolist() == pytest.approx([first, last, whole])
    assert four(last) != four(mean([(6 + 2) / (6 + 8), (3 + 1) / (2 + 2)]))


def test_with_an_odd_number_of_days_the_last_half_has_one_day_more(tmp_path):
    days = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04", "2026-07-05"]
    daily_mae, daily_mtus = written_daily(tmp_path, days, [24] * 5, {
        ("naive", "A"): [2, 2, 2, 2, 2], ("good", "A"): [1, 1, 4, 1, 1]})

    table = halves_table(daily_mae, daily_mtus, ["good"], ["A"])

    assert list(table.columns) == ["first 2 days", "last 3 days", "all 5 days"]
    assert table.loc["good"].tolist() == pytest.approx([0.5, 1.0, 0.8])


def test_the_days_of_the_daily_file_are_put_in_the_order_of_time(tmp_path):
    days = ["2026-07-03", "2026-07-01", "2026-07-04", "2026-07-02"]
    daily_mae, daily_mtus = written_daily(tmp_path, days, [24] * 4, {
        ("naive", "A"): [2, 2, 2, 2], ("good", "A"): [3, 1, 3, 1]})

    table = halves_table(daily_mae, daily_mtus, ["good"], ["A"])

    assert list(daily_mae.index) == sorted(days)
    assert table.loc["good"].tolist() == pytest.approx([0.5, 1.5, 1.0])


def test_block_2_prints_the_halves_with_the_best_model_first(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request(models=["poor", "good"]))

    lines = block(capsys.readouterr().out, "2. ")
    good_first = mean([72 / 144, 48 / 96, 48 / 144])
    good_last = mean([198 / 342, 99 / 98, 49 / 146])
    poor_first = mean([120 / 144, 96 / 96, 96 / 144])
    poor_last = mean([247 / 342, 148 / 98, 98 / 146])
    assert lines[0] == "2. Mean relative MAE over the 3 zones, by half of the days"
    assert lines[1].split() == ["first", "2", "days", "last", "2", "days", "all", "4", "days"]
    assert [line.split() for line in lines[2:]] == [
        ["good", four(good_first), four(good_last), four(mean(GOOD.values()))],
        ["poor", four(poor_first), four(poor_last), four(mean(POOR.values()))]]


def test_the_relative_mae_of_some_days_counts_a_day_as_often_as_it_is_drawn(tmp_path):
    config = save_project(tmp_path)
    daily_mae, daily_mtus = project_daily(config, ["naive", "good"])

    table = relative_mae_of_days(daily_mae, daily_mtus, np.array([2, 2, 3]), ZONES)

    assert list(table.columns) == ZONES
    assert table.loc["good", "A"] == pytest.approx((150 + 150 + 48) / (150 + 150 + 192))
    assert table.loc["good", "B"] == pytest.approx((75 + 75 + 24) / (50 + 50 + 48))
    assert table.loc["naive"].tolist() == [1.0, 1.0, 1.0]


# Block 3: the zones won.

def test_zones_won_counts_the_best_model_of_every_zone_with_median_and_mean():
    table = pd.DataFrame({"A": [0.5, 0.6, 0.7], "B": [0.9, 0.7, 0.8], "C": [0.4, 0.5, 0.9]},
                         index=["one", "two", "three"])

    summary, best = zones_won(table)

    assert best.to_dict() == {"A": "one", "B": "two", "C": "one"}
    assert summary["zones won"].to_dict() == {"one": 2, "two": 1, "three": 0}
    assert summary["median over zones"].to_dict() == {"one": 0.5, "two": 0.6, "three": 0.8}
    assert summary["mean"].tolist() == pytest.approx([0.6, 0.6, 0.8])


def test_a_tie_in_a_zone_goes_to_the_model_that_stands_higher_in_the_table():
    table = pd.DataFrame({"A": [0.5, 0.5, 0.7], "B": [0.9, 0.8, 0.8]},
                         index=["one", "two", "three"])

    summary, best = zones_won(table)

    assert best.to_dict() == {"A": "one", "B": "two"}
    assert summary["zones won"].to_dict() == {"one": 1, "two": 1, "three": 0}


def test_block_3_prints_the_zones_won_and_the_best_model_per_zone(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request())

    lines = block(capsys.readouterr().out, "3. ")
    assert lines[0] == ("3. How often is each model the best of the 2 in a zone, and its "
                        "median and mean over the zones")
    assert lines[2].split() == ["good", "3", four(GOOD["A"]), four(mean(GOOD.values()))]
    assert lines[3].split() == ["poor", "0", four(POOR["A"]), four(mean(POOR.values()))]
    assert lines[4].strip() == "best model per zone: {'A': 'good', 'B': 'good', 'C': 'good'}"


# Block 4: the bootstrap over whole days.

def test_a_resample_draws_whole_days_once_for_every_model_zone_and_the_reference(tmp_path):
    config = save_project(tmp_path)
    daily_mae, daily_mtus = project_daily(config, ["naive", "good", "poor"])

    means = bootstrap_means(daily_mae, daily_mtus, ZONES, resamples=3, seed=5)

    generator = np.random.default_rng(5)
    for resample in range(3):
        drawn = generator.integers(0, 4, size=4)
        by_hand = mean(
            sum(abs(ERRORS["good"][zone][day]) * HOURS[day] for day in drawn)
            / sum(ERRORS["naive"][zone][day] * HOURS[day] for day in drawn)
            for zone in ZONES)
        assert means["good"].iloc[resample] == pytest.approx(by_hand)
    assert means.shape == (3, 3)
    assert means["naive"].tolist() == [1.0, 1.0, 1.0]


def test_the_same_seed_gives_the_same_resamples_and_another_seed_others(tmp_path):
    config = save_project(tmp_path)
    daily_mae, daily_mtus = project_daily(config, ["naive", "good", "poor"])

    first = bootstrap_means(daily_mae, daily_mtus, ZONES, resamples=40, seed=5)
    again = bootstrap_means(daily_mae, daily_mtus, ZONES, resamples=40, seed=5)
    other = bootstrap_means(daily_mae, daily_mtus, ZONES, resamples=40, seed=6)

    assert first.equals(again)
    assert not first.equals(other)


def test_the_drawn_days_do_not_depend_on_the_list_of_models(tmp_path, capsys):
    config = save_project(tmp_path, WITH_COPY)
    few = project_daily(config, ["naive", "good", "poor"])
    many = project_daily(config, ["copy", "naive", "poor", "good"])

    of_few = bootstrap_means(*few, ZONES, resamples=40, seed=5)
    of_many = bootstrap_means(*many, ZONES, resamples=40, seed=5)
    run(config, request(models=["good", "poor"]))
    line_of_few = block(capsys.readouterr().out, "4. ")[2]
    run(config, request(models=["copy", "poor", "good"]))
    line_of_many = block(capsys.readouterr().out, "4. ")[3]

    assert of_few["poor"].nunique() > 1
    assert np.allclose(of_few["poor"], of_many["poor"], rtol=1e-12, atol=0)
    assert np.allclose(of_few["good"], of_many["good"], rtol=1e-12, atol=0)
    assert line_of_few.split()[0] == "poor"
    assert line_of_few.split() == line_of_many.split()


def test_block_4_prints_the_same_lines_for_the_same_seed(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request())
    first = block(capsys.readouterr().out, "4. ")
    run(config, request())
    again = block(capsys.readouterr().out, "4. ")

    assert first[0] == "4. Bootstrap over the 4 days (50 resamples of whole days, seed 11):"
    assert first[1].strip() == ("difference in mean relative MAE over the 3 zones, "
                                "other model minus good")
    assert len(first) == 3 and first[2].split()[0] == "poor"
    assert first == again


def test_the_seed_of_the_bootstrap_is_the_seed_of_the_config(tmp_path, capsys):
    run(save_project(tmp_path / "one", seed=11), request())
    of_11 = block(capsys.readouterr().out, "4. ")
    run(save_project(tmp_path / "two", seed=12), request())
    of_12 = block(capsys.readouterr().out, "4. ")

    assert "seed 11" in of_11[0] and "seed 12" in of_12[0]
    assert of_11[2] != of_12[2]


def test_a_model_equal_to_the_winner_has_a_difference_of_exactly_zero(tmp_path, capsys):
    config = save_project(tmp_path, WITH_COPY)
    daily_mae, daily_mtus = project_daily(config, ["naive", "good", "copy"])

    means = bootstrap_means(daily_mae, daily_mtus, ZONES, resamples=50, seed=11)
    run(config, request(models=["good", "copy"]))

    assert (means["copy"] - means["good"]).tolist() == [0.0] * 50
    assert block(capsys.readouterr().out, "4. ")[2].split() == [
        "copy", "mean", "+0.0000", "95%", "interval", "+0.0000", "to", "+0.0000", "share", "of",
        "resamples", "where", "good", "is", "better:", "0.0%"]


def test_a_model_that_is_worse_on_every_day_in_every_zone_loses_every_resample(
        tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request())

    words = block(capsys.readouterr().out, "4. ")[2].split()
    assert words[0] == "poor" and words[-1] == "100.0%"
    assert words[5].startswith("+") and float(words[5]) > 0
    assert float(words[5]) < float(words[2]) < float(words[7])


def test_the_bootstrap_lines_are_those_of_the_models_asked_for(tmp_path, capsys):
    config = save_project(tmp_path, WITH_COPY)

    run(config, request(models=["good", "poor", "copy"]))
    every = block(capsys.readouterr().out, "4. ")
    run(config, request(models=["good", "poor", "copy"], bootstrap=["poor"]))
    one = block(capsys.readouterr().out, "4. ")

    assert [line.split()[0] for line in every[2:]] == ["copy", "poor"]
    assert [line.split() for line in one[2:]] == [every[3].split()]


def test_block_4_says_so_when_the_winner_is_the_only_model(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request(models=["good"]))

    lines = block(capsys.readouterr().out, "4. ")
    assert len(lines) == 3
    assert lines[2].strip() == "no other model was given"


# Block 5: the mean without one zone.

def test_the_mean_without_one_zone_is_the_mean_over_the_other_zones():
    table = pd.DataFrame({"A": [0.5, 0.2], "B": [0.9, 0.1], "C": [0.3, 0.8]},
                         index=["one", "two"])

    means = means_without(table, "B")

    assert means.index.tolist() == ["one", "two"]
    assert means.tolist() == pytest.approx([0.4, 0.5])


def test_block_5_prints_the_mean_without_the_zone_of_the_option(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request(without="B"))

    lines = block(capsys.readouterr().out, "5. ")
    assert lines[0] == "5. Mean relative MAE over the 2 zones without B"
    assert [line.split() for line in lines[1:]] == [
        ["good", four(mean([GOOD["A"], GOOD["C"]]))],
        ["poor", four(mean([POOR["A"], POOR["C"]]))]]


def test_there_is_no_block_5_without_the_option(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request())

    printed = capsys.readouterr().out
    assert "without" not in printed.replace("without the harness metrics", "")
    assert not any(line.startswith("5.") for line in printed.splitlines())
    assert [line[:2] for line in printed.splitlines() if re.match(r"\d[a-d]?\. ", line)] == [
        "1.", "2.", "3.", "4.", "6a", "6b", "6c", "6d"]


# Block 6: by hour of the day, by calendar week and by day.

def hour_errors(config: dict) -> dict:
    """Errors with one hour that stands out: good is 3 off in hour 2 of zone A, else 1."""
    flat = {zone: [2, 2, 2, 2] for zone in ZONES}
    return {"naive": flat,
            "good": {"A": by_market_hour(config, 1, 2, 3), "B": [1, 1, 1, 1], "C": [1, 1, 1, 1]},
            "poor": flat}


def test_the_hour_of_the_day_is_the_hour_in_market_time_also_on_a_clock_change_day(tmp_path):
    config = project_config(tmp_path)
    save_prices(config)
    save_runs(config, hour_errors(config))
    scored = read_scored(config, ["naive", "good", "poor"], ZONES, "H", VALIDATION)

    by_zone = hourly_relative_mae(scored, "good", ZONES, MARKET_TZ)
    by_model = hours_by_model(scored, ["good", "poor"], ZONES, MARKET_TZ)

    stands_out = (by_market_hour(config, 1, 2, 3) == 3).to_numpy()
    assert sorted(set(validation_hours(config).hour[stands_out])) == [0, 1]
    assert stands_out.sum() == 5
    assert by_zone.index.tolist() == list(range(24))
    assert by_zone["A"].tolist() == [0.5, 0.5, 1.5] + [0.5] * 21
    assert by_zone["B"].tolist() == [0.5] * 24
    assert by_model["good"].tolist() == pytest.approx([0.5, 0.5, 2.5 / 3] + [0.5] * 21)
    assert by_model["poor"].tolist() == [1.0] * 24


def test_block_6_prints_the_hours_per_model_and_per_zone_for_the_winner(tmp_path, capsys):
    config = project_config(tmp_path)
    save_prices(config)
    save_runs(config, hour_errors(config))

    run(config, request())

    printed = capsys.readouterr().out
    per_model, per_zone = block(printed, "6a. "), block(printed, "6b. ")
    assert per_model[0] == ("6a. Relative MAE by hour of the day (Europe/Berlin), "
                            "mean over the 3 zones")
    assert per_model[1].split() == ["good", "poor"]
    assert per_model[5].split() == ["2", four(2.5 / 3), "1.0000"]
    assert per_model[6].split() == ["3", "0.5000", "1.0000"]
    assert len(per_model) == 3 + 24
    assert per_zone[0] == "6b. Relative MAE of good by hour of the day (Europe/Berlin) and zone"
    assert per_zone[1].split() == ["A", "B", "C", "mean"]
    assert per_zone[5].split() == ["2", "1.5000", "0.5000", "0.5000", four(2.5 / 3)]


def test_a_calendar_week_runs_from_monday_to_sunday(tmp_path):
    config = save_project(tmp_path)
    daily_mae, daily_mtus = project_daily(config, ["naive", "good", "poor"])

    weeks = weeks_table(daily_mae, daily_mtus, ["good", "poor"], ZONES)

    friday_to_sunday = mean([(24 + 48 + 150) / (96 + 48 + 150), (24 + 24 + 75) / (48 + 48 + 50),
                             (24 + 24 + 25) / (48 + 96 + 50)])
    monday = mean([2 / 8, 1 / 2, 1 / 4])
    assert weeks.index.tolist() == ["2026-10-19", "2026-10-26"]
    assert weeks["days"].tolist() == [3, 1]
    assert weeks["good"].tolist() == pytest.approx([friday_to_sunday, monday])
    assert weeks.loc["2026-10-26", "poor"] == pytest.approx(mean([3 / 8, 2 / 2, 2 / 4]))


def test_block_6_prints_the_weeks_with_their_number_of_days(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request())

    lines = block(capsys.readouterr().out, "6c. ")
    assert lines[0] == ("6c. Mean relative MAE over the 3 zones by calendar week "
                        "(Monday to Sunday)")
    assert lines[1].split() == ["days", "good", "poor"]
    assert lines[4].split() == ["2026-10-26", "1", four(mean([2 / 8, 1 / 2, 1 / 4])),
                                four(mean([3 / 8, 2 / 2, 2 / 4]))]


def test_the_days_above_the_reference_and_the_share_of_the_six_worst_days(tmp_path):
    days = [f"2026-10-{day}" for day in range(19, 27)]
    hours = [24, 24, 24, 24, 24, 24, 25, 24]
    daily_mae, daily_mtus = written_daily(tmp_path, days, hours, {
        ("naive", "A"): [5, 5, 5, 5, 5, 5, 5, 5], ("naive", "B"): [2, 2, 2, 2, 2, 2, 2, 2],
        ("good", "A"): [1, 6, 1, 6, 1, 1, 8, 1], ("good", "B"): [2, 1, 1, 1, 1, 1, 1, 3]})

    table = days_table(daily_mae, daily_mtus, "good", ["A", "B"])

    summed_a = [24, 144, 24, 144, 24, 24, 200, 24]
    summed_b = [48, 24, 24, 24, 24, 24, 25, 72]
    assert table.index.tolist() == ["A", "B"]
    assert table["days above"].tolist() == [3, 1]
    assert table["days"].tolist() == [8, 8]
    assert table["worst share"].tolist() == pytest.approx(
        [(200 + 144 + 144 + 24 + 24 + 24) / sum(summed_a),
         (72 + 48 + 25 + 24 + 24 + 24) / sum(summed_b)])
    assert f"{table.loc['B', 'worst share']:.1%}" == "81.9%"
    assert f"{(3 + 2 + 1 + 1 + 1 + 1) / (2 + 1 * 6 + 3):.1%}" == "81.8%"


def test_block_6_prints_the_days_above_the_reference_per_zone_and_in_total(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request())

    lines = block(capsys.readouterr().out, "6d. ")
    assert lines[0] == ("6d. Days of good: delivery days with a daily MAE above naive, and the "
                        "share of its summed absolute error in its 6 worst days")
    assert [line.split() for line in lines[2:5]] == [
        ["A", "0", "4", "100.0%"], ["B", "1", "4", "100.0%"], ["C", "0", "4", "100.0%"]]
    assert lines[5].strip() == "daily MAE above naive on 1 of the 12 days of all zones"


# The whole command, on the synthetic project.

def test_the_first_line_names_the_experiment_the_days_and_the_zones(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request())

    assert capsys.readouterr().out.splitlines()[:3] == [
        "", "Experiment H, validation days 2026-10-23 to 2026-10-26, zones ['A', 'B', 'C']", ""]


def test_the_reference_among_the_models_is_shown_with_a_relative_mae_of_one(tmp_path, capsys):
    config = save_project(tmp_path)

    run(config, request(models=["good", "naive"]))

    printed = capsys.readouterr().out
    assert block(printed, "2. ")[3].split() == ["naive", "1.0000", "1.0000", "1.0000"]
    assert block(printed, "1. ")[1].strip().startswith("6 model and zone pairs.")


def test_the_newest_row_is_used_when_a_model_was_run_twice(tmp_path, capsys):
    config = save_project(tmp_path)
    second = {"naive": ERRORS["naive"], "good": {"A": [1, 1, 1, 1], "B": [1, 1, 1, 1],
                                                 "C": [1, 1, 1, 1]}}
    save_runs(config, second, started=SECOND_RUN)

    run(config, request())

    printed = capsys.readouterr().out
    saved = results.read_rows(results.results_path(Path(config["paths"]["results"]),
                                                   "backtest", "core"))
    assert (saved["model"] == "good").sum() == 6
    assert block(printed, "1. ")[1].endswith("to the saved rows: 0.0e+00")
    assert block(printed, "2. ")[2].split()[-1] == four(mean(
        [97 / NAIVE_SUMS["A"], 97 / NAIVE_SUMS["B"], 97 / NAIVE_SUMS["C"]]))


def test_a_daily_row_that_stands_twice_ends_the_command_with_a_line_that_names_it(tmp_path):
    config = save_project(tmp_path)
    rows = results.read_rows(daily_path(config))
    twice = rows[(rows["model"] == "good") & (rows["zone"] == "B")
                 & (rows["delivery_day"] == "2026-10-24")]
    results.append_rows(daily_path(config), twice)

    with pytest.raises(SystemExit) as error:
        run(config, request())

    message = str(error.value.code)
    assert re.search(r"daily_core\.csv.*more than one row.*good.*B.*2026-10-24", message)
    assert "\n" not in message


def test_a_model_without_a_day_that_the_others_have_ends_the_command(tmp_path):
    config = save_project(tmp_path)
    rows = results.read_rows(daily_path(config))
    lost = ((rows["model"] == "poor") & (rows["zone"] == "C")
            & (rows["delivery_day"] == "2026-10-25"))
    rows[~lost].to_csv(daily_path(config), index=False)

    with pytest.raises(SystemExit, match="daily_core.csv.*same delivery days"):
        run(config, request())


def test_every_zone_group_gets_its_own_blocks_core_zones_first(tmp_path, capsys):
    config = project_config(tmp_path, {"C": "extra", "A": "core", "D": "extra", "B": "core"})
    save_prices(config)
    save_runs(config, {model: {**by_zone, "D": by_zone["A"]}
                       for model, by_zone in ERRORS.items()})

    run(config, request(without="D"))

    lines = capsys.readouterr().out.splitlines()
    assert [line for line in lines if line.startswith("Experiment")] == [
        "Experiment H, validation days 2026-10-23 to 2026-10-26, zones ['A', 'B']",
        "Experiment H, validation days 2026-10-23 to 2026-10-26, zones ['C', 'D']"]
    assert [line.split() for line in lines if line.startswith("good ")][:2] == [
        ["good", four(mean([72 / 144, 48 / 96])), four(mean([198 / 342, 99 / 98])),
         four(mean([GOOD["A"], GOOD["B"]]))],
        ["good", "2", four(mean([GOOD["A"], GOOD["B"]])), four(mean([GOOD["A"], GOOD["B"]]))]]
    assert [line for line in lines if line.startswith("5. ")] == [
        "5. Mean relative MAE over the 1 zones without D"]
    assert lines[lines.index("5. Mean relative MAE over the 1 zones without D") + 1].split() == [
        "good", four(GOOD["C"])]


def test_run_writes_and_changes_no_file(tmp_path, capsys):
    config = save_project(tmp_path)
    before = files_under(tmp_path)

    run(config, request(without="A"))

    assert "6d. " in capsys.readouterr().out
    assert files_under(tmp_path) == before
    assert len(before) == 3 + 9 + 2


# Wrong arguments and missing files end with one line.

@pytest.mark.parametrize("changes, message", [
    ({"winner": "best"}, "winner best is not among --models"),
    ({"models": ["good", "poor", "good"]}, "named twice in --models"),
    ({"models": ["good", "poor", "nomodel"]}, r"backtest_core\.csv has no row.*nomodel"),
    ({"bootstrap": ["poor", "other"]}, r"--bootstrap.*not among --models.*other"),
    ({"without": "Z"}, "--without Z is not a zone of the config"),
    ({"split": TEST}, r"backtest_core\.csv has no row for experiment H and the test days"),
    ({"experiment": "Q"}, r"backtest_core\.csv has no row for experiment Q"),
    ({"resamples": 0}, "--resamples must be at least 1"),
])
def test_wrong_arguments_end_the_command_with_one_line(changes, message, tmp_path, capsys):
    config = save_project(tmp_path)

    with pytest.raises(SystemExit, match=message) as error:
        run(config, request(**changes))

    assert "\n" not in str(error.value.code)
    assert capsys.readouterr().out == ""


def test_a_missing_results_file_ends_the_command_with_a_line_that_names_it(tmp_path):
    config = project_config(tmp_path)

    with pytest.raises(SystemExit, match=r"backtest_core\.csv does not exist"):
        run(config, request())


def test_a_missing_forecast_file_ends_the_command_with_a_line_that_names_it(tmp_path, capsys):
    config = save_project(tmp_path)
    (Path(config["paths"]["forecasts"]) / "poor" / "H" / VALIDATION / "B.parquet").unlink()

    with pytest.raises(SystemExit, match=r"forecast file .*poor.*B\.parquet does not exist"):
        run(config, request())

    assert capsys.readouterr().out == ""


# The command line.

def test_the_command_line_needs_only_the_winner_and_the_models(monkeypatch):
    monkeypatch.setattr("sys.argv", ["firmness", "--winner", "good", "--models", "good", "poor"])

    asked = read_request()

    assert asked == Request(winner="good", models=["good", "poor"],
                            experiment=list(EXPERIMENTS)[0], split=VALIDATION, without=None,
                            bootstrap=None, resamples=2000)
    assert asked.experiment == "H"


def test_the_command_reads_every_option_from_the_command_line(tmp_path, capsys, monkeypatch):
    config = save_project(tmp_path, WITH_COPY)
    monkeypatch.setattr(firmness, "load_config", lambda: config)
    monkeypatch.setattr("sys.argv", [
        "firmness", "--winner", "good", "--models", "good", "poor", "copy", "--experiment", "H",
        "--split", "validation", "--without", "C", "--bootstrap", "poor", "--resamples", "20"])

    firmness.main()

    printed = capsys.readouterr().out
    bootstrap = block(printed, "4. ")
    assert bootstrap[0] == "4. Bootstrap over the 4 days (20 resamples of whole days, seed 11):"
    assert [line.split()[0] for line in bootstrap[2:]] == ["poor"]
    assert block(printed, "5. ")[0] == "5. Mean relative MAE over the 2 zones without C"


@pytest.mark.parametrize("arguments", [
    ["--models", "good", "poor"],
    ["--winner", "good"],
    ["--winner", "good", "--models", "good", "--experiment", "D"],
    ["--winner", "good", "--models", "good", "--split", "train"],
    ["--winner", "good", "--models", "good", "--resamples", "many"],
])
def test_the_command_refuses_a_missing_or_unknown_argument(arguments, monkeypatch):
    monkeypatch.setattr("sys.argv", ["firmness", *arguments])

    with pytest.raises(SystemExit) as error:
        firmness.main()

    assert error.value.code == 2


# The code.

def test_the_module_names_no_zone():
    config = load_config()
    names = [str(zone[key]) for zone in config["zones"] for key in ("key", "energy_charts")]
    names += [zone["weather_point"]["place"] for zone in config["zones"]]

    text = (REPO_ROOT / "src" / "epf" / "evaluation" / "firmness.py").read_text(encoding="utf-8")

    found = [name for name in names if re.search(rf"\b{re.escape(name)}\b", text)]
    assert len(names) == 3 * len(config["zones"])
    assert found == []
