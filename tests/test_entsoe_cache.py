"""Tests for the ENTSO-E download cache. They use a temporary folder and no network."""

import json

import entsoe
import pandas as pd
import pytest

from epf.data.entsoe_cache import cached_fetch, read_saved

YEAR_START = pd.Timestamp("2025-01-01", tz="Europe/Berlin")
YEAR_END = pd.Timestamp("2026-01-01", tz="Europe/Berlin")
DE_LU_2025 = ("prices", "DE_LU", 2025)


def price_frame(prices: list[float]) -> pd.DataFrame:
    """Hourly prices from YEAR_START on, with a UTC index like the raw layer."""
    index = pd.date_range(YEAR_START.tz_convert("UTC"), periods=len(prices), freq="h")
    return pd.DataFrame({"price": prices}, index=index)


def fetch_returning(data: pd.DataFrame, calls: list):
    """A fetch function that returns fixed data and records the start and end of each call."""
    def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        calls.append((start, end))
        return data
    return fetch


def fetch_that_must_not_run(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """A fetch function for tests where the saved file must be used."""
    pytest.fail("The cache downloaded again instead of reading the saved file.")


def test_cached_fetch_downloads_when_nothing_is_saved(tmp_path):
    calls = []
    data = price_frame([10.0, -5.0, 30.5])

    result = cached_fetch(fetch_returning(data, calls), tmp_path, *DE_LU_2025, YEAR_START, YEAR_END)

    pd.testing.assert_frame_equal(result, data)
    assert calls == [(YEAR_START, YEAR_END)]


def test_cached_fetch_reads_the_saved_file_for_the_same_query(tmp_path):
    data = price_frame([10.0, -5.0, 30.5])
    cached_fetch(fetch_returning(data, []), tmp_path, *DE_LU_2025, YEAR_START, YEAR_END)

    result = cached_fetch(fetch_that_must_not_run, tmp_path, *DE_LU_2025, YEAR_START, YEAR_END)

    pd.testing.assert_frame_equal(result, data, check_freq=False)


def test_cached_fetch_downloads_again_when_the_query_end_moves(tmp_path):
    partial_end = pd.Timestamp("2025-11-20", tz="Europe/Berlin")
    cached_fetch(fetch_returning(price_frame([10.0]), []), tmp_path, *DE_LU_2025, YEAR_START, partial_end)
    calls = []
    full_year = price_frame([10.0, 20.0])

    result = cached_fetch(fetch_returning(full_year, calls), tmp_path, *DE_LU_2025, YEAR_START, YEAR_END)

    pd.testing.assert_frame_equal(result, full_year)
    assert calls == [(YEAR_START, YEAR_END)]


def test_cached_fetch_records_the_download_in_the_manifest(tmp_path):
    before = pd.Timestamp.now(tz="UTC")
    cached_fetch(fetch_returning(price_frame([10.0, -5.0, 30.5]), []), tmp_path, *DE_LU_2025,
                 YEAR_START, YEAR_END)
    after = pd.Timestamp.now(tz="UTC")

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["prices/DE_LU_2025.parquet"]

    assert entry["query_start"] == "2024-12-31T23:00:00+00:00"
    assert entry["query_end"] == "2025-12-31T23:00:00+00:00"
    assert entry["rows"] == 3
    assert entry["entsoe_py_version"] == entsoe.__version__
    assert before <= pd.Timestamp(entry["downloaded_at"]) <= after


def test_cached_fetch_does_not_save_an_empty_answer(tmp_path):
    calls = []
    empty = pd.DataFrame()

    cached_fetch(fetch_returning(empty, calls), tmp_path, *DE_LU_2025, YEAR_START, YEAR_END)
    result = cached_fetch(fetch_returning(empty, calls), tmp_path, *DE_LU_2025, YEAR_START, YEAR_END)

    assert result.empty
    assert len(calls) == 2


def test_cached_fetch_keeps_earlier_downloads_when_a_new_one_is_saved(tmp_path):
    german = price_frame([10.0, -5.0])
    french = price_frame([40.0, 41.0])
    cached_fetch(fetch_returning(german, []), tmp_path, "prices", "DE_LU", 2025, YEAR_START, YEAR_END)
    cached_fetch(fetch_returning(french, []), tmp_path, "prices", "FR", 2025, YEAR_START, YEAR_END)

    result = cached_fetch(fetch_that_must_not_run, tmp_path, "prices", "DE_LU", 2025,
                          YEAR_START, YEAR_END)

    pd.testing.assert_frame_equal(result, german, check_freq=False)


def test_cached_fetch_downloads_again_when_the_saved_file_is_gone(tmp_path):
    data = price_frame([10.0, -5.0, 30.5])
    cached_fetch(fetch_returning(data, []), tmp_path, *DE_LU_2025, YEAR_START, YEAR_END)
    (tmp_path / "prices" / "DE_LU_2025.parquet").unlink()
    calls = []

    result = cached_fetch(fetch_returning(data, calls), tmp_path, *DE_LU_2025, YEAR_START, YEAR_END)

    pd.testing.assert_frame_equal(result, data)
    assert len(calls) == 1


def test_cached_fetch_downloads_again_when_the_query_start_moves(tmp_path):
    later_start = pd.Timestamp("2025-06-01", tz="Europe/Berlin")
    cached_fetch(fetch_returning(price_frame([10.0]), []), tmp_path, *DE_LU_2025, later_start, YEAR_END)
    calls = []
    full_year = price_frame([10.0, 20.0])

    result = cached_fetch(fetch_returning(full_year, calls), tmp_path, *DE_LU_2025, YEAR_START, YEAR_END)

    pd.testing.assert_frame_equal(result, full_year)
    assert calls == [(YEAR_START, YEAR_END)]


def test_read_saved_returns_the_data_and_the_range_of_its_query(tmp_path):
    data = price_frame([10.0, -5.0, 30.5])
    cached_fetch(fetch_returning(data, []), tmp_path, *DE_LU_2025, YEAR_START, YEAR_END)

    saved, start, end = read_saved(tmp_path, *DE_LU_2025)

    pd.testing.assert_frame_equal(saved, data, check_freq=False)
    assert (start, end) == (YEAR_START, YEAR_END)


def test_read_saved_raises_when_nothing_is_saved(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_saved(tmp_path, *DE_LU_2025)
