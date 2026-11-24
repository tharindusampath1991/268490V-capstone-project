"""Tests for the results files and the cost readings.

They use a temporary folder, no network and no data files.
"""

from collections import namedtuple

import pandas as pd
import psutil

from epf.evaluation.results import (
    append_rows,
    hardware,
    peak_memory_mb,
    peak_of,
    read_forecasts,
    replace_rows,
    results_path,
    write_forecasts,
)

KEYS = ["model", "zone"]


def rows(model: str, zone: str, values: list[float]) -> pd.DataFrame:
    """Result rows of one model and zone."""
    return pd.DataFrame({"model": model, "zone": zone, "mae": values})


def test_results_path_carries_the_kind_and_the_zone_group(tmp_path):
    assert results_path(tmp_path, "backtest", "core") == tmp_path / "backtest_core.csv"
    assert results_path(tmp_path, "daily", "extra") == tmp_path / "daily_extra.csv"


def test_append_rows_writes_a_new_file_with_a_header(tmp_path):
    path = tmp_path / "results" / "backtest_core.csv"

    append_rows(path, rows("naive", "ES", [1.5]))

    assert pd.read_csv(path).to_dict("records") == [{"model": "naive", "zone": "ES", "mae": 1.5}]


def test_append_rows_keeps_the_rows_of_earlier_runs(tmp_path):
    path = tmp_path / "backtest_core.csv"

    append_rows(path, rows("naive", "ES", [1.5]))
    append_rows(path, rows("naive", "ES", [2.5]))

    assert pd.read_csv(path)["mae"].tolist() == [1.5, 2.5]


def test_append_rows_keeps_a_column_that_only_later_rows_have(tmp_path):
    path = tmp_path / "backtest_core.csv"

    append_rows(path, rows("naive", "ES", [1.5]))
    append_rows(path, rows("lgbm", "ES", [0.5]).assign(coverage=0.8))

    saved = pd.read_csv(path)
    assert saved["mae"].tolist() == [1.5, 0.5]
    assert saved["coverage"].isna().tolist() == [True, False]


# Numbers that the default pandas parser reads back with another last digit.
LONG_NUMBERS = [62.167291666666664, 0.27784269995754585]


def test_append_rows_leaves_the_saved_lines_unchanged_to_the_last_digit(tmp_path):
    path = tmp_path / "backtest_core.csv"
    append_rows(path, rows("naive", "ES", LONG_NUMBERS))
    before = path.read_text().splitlines()

    append_rows(path, rows("naive", "FR", [1.5]))

    assert before[1:] == ["naive,ES,62.167291666666664", "naive,ES,0.27784269995754585"]
    assert path.read_text().splitlines()[:3] == before


def test_replace_rows_leaves_the_kept_lines_unchanged_to_the_last_digit(tmp_path):
    path = tmp_path / "daily_core.csv"
    replace_rows(path, rows("naive", "ES", LONG_NUMBERS), KEYS)
    before = path.read_text().splitlines()

    replace_rows(path, rows("naive", "FR", [1.5]), KEYS)

    assert path.read_text().splitlines()[:3] == before


def test_replace_rows_replaces_the_rows_with_the_same_key_and_keeps_the_others(tmp_path):
    path = tmp_path / "daily_core.csv"
    replace_rows(path, rows("naive", "ES", [1.0, 2.0]), KEYS)
    replace_rows(path, rows("naive", "FR", [3.0, 4.0]), KEYS)

    replace_rows(path, rows("naive", "ES", [5.0, 6.0]), KEYS)

    saved = pd.read_csv(path)
    assert saved[saved["zone"] == "FR"]["mae"].tolist() == [3.0, 4.0]
    assert saved[saved["zone"] == "ES"]["mae"].tolist() == [5.0, 6.0]
    assert len(saved) == 4


def test_forecasts_are_saved_per_model_experiment_split_and_zone(tmp_path):
    index = pd.date_range("2026-07-01", periods=3, freq="h", tz="UTC")
    scored = pd.DataFrame({"forecast": [1.0, -2.0, 3.0], "actual": [1.5, -2.5, 0.0]}, index=index)

    path = write_forecasts(tmp_path, "naive", "H", "validation", "ES", scored)

    assert path == tmp_path / "naive" / "H" / "validation" / "ES.parquet"
    pd.testing.assert_frame_equal(read_forecasts(path), scored, check_freq=False)


def test_peak_of_reads_the_peak_working_set_in_megabytes():
    Info = namedtuple("Info", ["rss", "peak_wset"])

    assert peak_of(Info(rss=1, peak_wset=3 * 2**20)) == 3.0


def test_peak_of_is_empty_on_a_system_without_a_peak_reading():
    Info = namedtuple("Info", ["rss"])

    assert peak_of(Info(rss=1)) is None


def test_peak_memory_is_at_least_the_memory_in_use_now():
    in_use_mb = psutil.Process().memory_info().rss / 2**20

    peak = peak_memory_mb()

    assert peak is None or peak >= in_use_mb


def test_hardware_names_the_cores_the_memory_and_the_system():
    line = hardware()

    assert f"{psutil.cpu_count(logical=False)} cores" in line
    assert "GB RAM" in line
