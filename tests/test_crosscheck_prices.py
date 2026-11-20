"""Tests for the price cross-check. They use small synthetic frames and no network."""

import pandas as pd

from epf.config import Zone
from epf.data.crosscheck_prices import compare_prices, run_crosscheck, write_reports
from epf.data.entsoe_cache import cached_fetch

MARKET_TZ = "Europe/Berlin"
HOURS = pd.date_range("2025-01-14 23:00", periods=4, freq="h", tz="UTC")


def prices(values: list[float], index: pd.DatetimeIndex = HOURS) -> pd.DataFrame:
    """A price frame with a UTC index, like the raw price files."""
    return pd.DataFrame({"price": values}, index=index)


def test_compare_prices_finds_no_mismatch_between_equal_series():
    counts = compare_prices(prices([10.0, -5.0, 30.5, 0.0]), prices([10.0, -5.0, 30.5, 0.0]),
                            tolerance=0.01)

    assert counts == {"compared": 4, "mismatches": 0, "max_abs_diff": 0.0,
                      "only_entsoe": 0, "only_energy_charts": 0}


def test_compare_prices_counts_only_differences_above_the_tolerance():
    counts = compare_prices(prices([50.00, 50.00, 50.00, 50.00]),
                            prices([50.00, 50.01, 50.02, 49.00]), tolerance=0.01)

    assert counts["mismatches"] == 2
    assert counts["max_abs_diff"] == 1.0


def test_compare_prices_treats_a_difference_of_exactly_the_tolerance_as_equal():
    counts = compare_prices(prices([0.07, 50.00, 50.00, 50.00]),
                            prices([0.06, 50.00, 50.00, 50.00]), tolerance=0.01)

    assert counts["mismatches"] == 0


def test_compare_prices_counts_timestamps_that_only_one_source_has():
    counts = compare_prices(prices([10.0, 10.0, 10.0], HOURS[:3]),
                            prices([10.0, 10.0, 10.0], HOURS[1:]), tolerance=0.01)

    assert counts["compared"] == 2
    assert counts["only_entsoe"] == 1
    assert counts["only_energy_charts"] == 1


def test_compare_prices_does_not_compare_an_empty_price():
    counts = compare_prices(prices([10.0, float("nan"), 10.0, 10.0]),
                            prices([10.0, 10.0, 10.0, 10.0]), tolerance=0.01)

    assert counts["compared"] == 3
    assert counts["only_energy_charts"] == 1


def test_run_crosscheck_records_whether_the_second_source_is_open_data(tmp_path):
    start = pd.Timestamp("2025-01-15", tz=MARKET_TZ)
    end = pd.Timestamp("2025-01-16", tz=MARKET_TZ)
    saved = prices([10.0, -5.0, 30.5, 0.0])
    for zone_key in ["FR", "ES"]:
        cached_fetch(lambda query_start, query_end: saved, tmp_path / "entsoe", "prices",
                     zone_key, 2025, start, end)

    def fetch_other(zone_code: str, query_start: pd.Timestamp,
                    query_end: pd.Timestamp) -> pd.DataFrame:
        return saved.assign(open_licence=(zone_code == "FR"))

    zones = [Zone("FR", "FR", "core", energy_charts="FR"),
             Zone("ES", "ES", "core", energy_charts="ES")]

    rows = run_crosscheck(zones, [2025], tmp_path / "entsoe", tmp_path / "energy_charts",
                          fetch_other, tolerance=0.01, market_tz=MARKET_TZ)

    assert rows["zone"].tolist() == ["FR", "ES"]
    assert rows["open_licence"].tolist() == [True, False]


def test_run_crosscheck_compares_only_zones_with_an_energy_charts_code(tmp_path):
    start = pd.Timestamp("2025-01-15", tz=MARKET_TZ)
    end = pd.Timestamp("2025-01-16", tz=MARKET_TZ)
    saved = prices([10.0, -5.0, 30.5, 0.0])
    for zone_key in ["DE_LU", "ES"]:
        cached_fetch(lambda query_start, query_end: saved, tmp_path / "entsoe", "prices",
                     zone_key, 2025, start, end)
    calls = []

    def fetch_other(zone_code: str, query_start: pd.Timestamp,
                    query_end: pd.Timestamp) -> pd.DataFrame:
        calls.append((zone_code, query_start, query_end))
        return prices([10.0, -5.0, 30.5, 9.0]).assign(open_licence=True)

    zones = [Zone("DE_LU", "DE", "core", energy_charts="DE-LU"), Zone("ES", "ES", "core")]

    rows = run_crosscheck(zones, [2025], tmp_path / "entsoe", tmp_path / "energy_charts",
                          fetch_other, tolerance=0.01, market_tz=MARKET_TZ)

    assert rows["zone"].tolist() == ["DE_LU"]
    assert rows["year"].tolist() == [2025]
    assert rows["mismatches"].tolist() == [1]
    assert calls == [("DE-LU", start, end)]
    assert str(calls[0][1].tz) == MARKET_TZ


def test_write_reports_keeps_restricted_results_out_of_the_public_report(tmp_path):
    rows = pd.DataFrame([
        {"zone": "DE_LU", "year": 2025, "compared": 4, "mismatches": 1, "max_abs_diff": 1.0,
         "only_entsoe": 0, "only_energy_charts": 0, "open_licence": True},
        {"zone": "ES", "year": 2025, "compared": 7, "mismatches": 3, "max_abs_diff": 2.5,
         "only_entsoe": 0, "only_energy_charts": 0, "open_licence": False},
    ])
    public_path = tmp_path / "docs" / "public.md"
    local_path = tmp_path / "data" / "local" / "restricted.md"
    public_path.parent.mkdir()

    write_reports(rows, 0.01, public_path, local_path)

    public = public_path.read_text(encoding="utf-8")
    local = local_path.read_text(encoding="utf-8")
    assert "| DE_LU | 2025 | 4 | 1 | 1.00 | 0 | 0 |" in public
    assert "| ES |" not in public
    assert "2.50" not in public
    assert "| ES | 2025 | 7 | 3 | 2.50 | 0 | 0 |" in local
    assert "| DE_LU |" not in local
