"""Tests for the coverage gate. They use synthetic frames, a fake client and no network."""

import pandas as pd
import pytest

from epf.config import Zone
from epf.data.coverage_gate import (
    build_report,
    collect_coverage,
    column_decisions,
    hourly_coverage,
    native_resolution,
    verdicts,
)

MARKET_TZ = "Europe/Berlin"
SWITCH = pd.Timestamp("2025-10-01", tz=MARKET_TZ)
DAY_START = pd.Timestamp("2025-01-15", tz=MARKET_TZ)
DAY_END = pd.Timestamp("2025-01-16", tz=MARKET_TZ)
# The 24 hours of delivery day 15 Jan 2025 in market time (UTC+1 in winter).
FULL_DAY = pd.date_range("2025-01-14 23:00", periods=24, freq="h", tz="UTC")
THRESHOLDS = {"price_min_share": 0.99, "forecast_min_share": 0.95}
SE_3 = Zone("SE_3", "SE", "extra")
# Yearly shares of a zone that passes the gate. Solar is low on purpose.
GOOD = {
    ("prices", "price"): 1.0,
    ("load_forecast", "Forecasted Load"): 0.99,
    ("wind_solar_forecast", "Wind Onshore"): 0.97,
    ("wind_solar_forecast", "Solar"): 0.10,
}


class FakeClient:
    """Stands in for EntsoePandasClient with complete data for 15 Jan 2025.

    Like the real client it answers in local time and includes the end timestamp.
    """

    def __init__(self) -> None:
        self.index = pd.date_range("2025-01-15", "2025-01-16", freq="h", tz=MARKET_TZ)

    def query_day_ahead_prices(self, country_code, start, end) -> pd.Series:
        return pd.Series(50.0, index=self.index).truncate(before=start, after=end)

    def query_load_forecast(self, country_code, start, end) -> pd.DataFrame:
        frame = pd.DataFrame({"Forecasted Load": 1000.0}, index=self.index)
        return frame.truncate(before=start, after=end)

    def query_wind_and_solar_forecast(self, country_code, start, end) -> pd.DataFrame:
        frame = pd.DataFrame({"Wind Onshore": 200.0}, index=self.index)
        return frame.truncate(before=start, after=end)


def coverage_rows(zone_key: str, shares: dict, year: int = 2025) -> list[dict]:
    """Coverage rows of one zone and year from {(dataset, column): share}."""
    return [{"zone": zone_key, "dataset": dataset, "column": column, "year": year, "share": share}
            for (dataset, column), share in shares.items()]


@pytest.mark.parametrize("freq, expected", [("h", "60min"), ("15min", "15min")])
def test_native_resolution_names_the_most_common_step(freq, expected):
    index = pd.date_range("2025-01-01", periods=8, freq=freq, tz="UTC")

    assert native_resolution(index) == expected


def test_native_resolution_is_not_changed_by_one_gap():
    index = pd.date_range("2025-01-01", periods=8, freq="h", tz="UTC").delete(3)

    assert native_resolution(index) == "60min"


def test_native_resolution_is_a_dash_for_fewer_than_two_timestamps():
    assert native_resolution(FULL_DAY[:1]) == "-"


def test_hourly_coverage_gives_the_share_of_hours_with_a_value_per_column():
    data = pd.DataFrame({"Solar": 1.0, "Wind Onshore": 1.0}, index=FULL_DAY)
    data.loc[FULL_DAY[:6], "Solar"] = float("nan")

    rows = hourly_coverage(data, DAY_START, DAY_END)

    assert {row["column"]: row["share"] for row in rows} == {"Solar": 0.75, "Wind Onshore": 1.0}
    assert {row["column"]: row["present"] for row in rows} == {"Solar": 18, "Wind Onshore": 24}


def test_hourly_coverage_counts_an_hour_as_present_when_it_holds_any_value():
    quarter_past = pd.date_range("2025-01-14 23:15", periods=24, freq="h", tz="UTC")
    data = pd.DataFrame({"Forecasted Load": 1.0}, index=quarter_past)

    rows = hourly_coverage(data, DAY_START, DAY_END)

    assert [row["share"] for row in rows] == [1.0]


def test_hourly_coverage_reports_no_data_as_one_row_with_share_zero():
    empty = pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"))

    rows = hourly_coverage(empty, DAY_START, DAY_END)

    assert [(row["column"], row["expected"], row["present"], row["share"]) for row in rows] == [
        ("(no data)", 24, 0, 0.0)]


def test_hourly_coverage_counts_repeated_timestamps():
    data = pd.DataFrame({"Forecasted Load": 1.0}, index=FULL_DAY.append(FULL_DAY[:1]))

    rows = hourly_coverage(data, DAY_START, DAY_END)

    assert [(row["duplicates"], row["share"]) for row in rows] == [(1, 1.0)]


def test_verdicts_pass_a_zone_that_meets_all_three_thresholds():
    coverage = pd.DataFrame(coverage_rows("SE_3", GOOD))

    verdict = verdicts(coverage, [SE_3], [2025], THRESHOLDS)

    assert verdict["gate"].tolist() == ["PASS"]
    assert verdict["group"].tolist() == ["extra"]


def test_verdicts_fail_a_zone_when_one_year_is_below_a_threshold():
    low_prices = {**GOOD, ("prices", "price"): 0.98}
    coverage = pd.DataFrame(coverage_rows("SE_3", GOOD, 2024) + coverage_rows("SE_3", low_prices, 2025))

    verdict = verdicts(coverage, [SE_3], [2024, 2025], THRESHOLDS)

    assert verdict["prices_min"].tolist() == [0.98]
    assert verdict["gate"].tolist() == ["FAIL"]


def test_verdicts_use_the_best_wind_column_of_each_year():
    shares = {**GOOD, ("wind_solar_forecast", "Wind Onshore"): 0.50,
              ("wind_solar_forecast", "Wind Offshore"): 0.99}
    coverage = pd.DataFrame(coverage_rows("SE_3", shares))

    verdict = verdicts(coverage, [SE_3], [2025], THRESHOLDS)

    assert verdict["wind_fc_min"].tolist() == [0.99]
    assert verdict["gate"].tolist() == ["PASS"]


def test_verdicts_fail_a_zone_with_no_wind_forecast_in_one_year():
    without_wind = {key: share for key, share in GOOD.items() if key[1] != "Wind Onshore"}
    coverage = pd.DataFrame(coverage_rows("SE_3", GOOD, 2024)
                            + coverage_rows("SE_3", without_wind, 2025))

    verdict = verdicts(coverage, [SE_3], [2024, 2025], THRESHOLDS)

    assert verdict["wind_fc_min"].tolist() == [0.0]
    assert verdict["gate"].tolist() == ["FAIL"]


def test_verdicts_judge_each_zone_on_its_own():
    low_load = {**GOOD, ("load_forecast", "Forecasted Load"): 0.50}
    coverage = pd.DataFrame(coverage_rows("SE_3", GOOD) + coverage_rows("SE_4", low_load))

    verdict = verdicts(coverage, [SE_3, Zone("SE_4", "SE", "extra")], [2025], THRESHOLDS)

    assert verdict["zone"].tolist() == ["SE_3", "SE_4"]
    assert verdict["gate"].tolist() == ["PASS", "FAIL"]


def test_column_decisions_drop_a_forecast_column_that_is_low_or_absent_in_any_year():
    with_offshore = {**GOOD, ("wind_solar_forecast", "Wind Offshore"): 0.99}
    coverage = pd.DataFrame(coverage_rows("SE_3", GOOD, 2024)
                            + coverage_rows("SE_3", with_offshore, 2025))

    decisions = column_decisions(coverage, [2024, 2025], THRESHOLDS)

    assert {row.column: row.use for row in decisions.itertuples()} == {
        "Forecasted Load": "keep",
        "Wind Onshore": "keep",
        "Solar": "drop",
        "Wind Offshore": "drop",
    }


def test_collect_coverage_measures_prices_and_both_forecasts(tmp_path):
    coverage = collect_coverage(FakeClient(), [SE_3], [(2025, DAY_START, DAY_END)], tmp_path, SWITCH)

    assert {(row.dataset, row.column): row.share for row in coverage.itertuples()} == {
        ("prices", "price"): 1.0,
        ("load_forecast", "Forecasted Load"): 1.0,
        ("wind_solar_forecast", "Wind Onshore"): 1.0,
    }
    assert coverage["zone"].unique().tolist() == ["SE_3"]
    assert coverage["year"].unique().tolist() == [2025]


def test_build_report_shows_the_gate_result_and_the_yearly_shares(tmp_path):
    coverage = collect_coverage(FakeClient(), [SE_3], [(2025, DAY_START, DAY_END)], tmp_path, SWITCH)
    verdict = verdicts(coverage, [SE_3], [2025], THRESHOLDS)
    decisions = column_decisions(coverage, [2025], THRESHOLDS)

    report = build_report(coverage, verdict, decisions, DAY_START, DAY_END, THRESHOLDS)

    assert "| SE_3 | extra | 100.00% | 100.00% | 100.00% | PASS |" in report
    assert "| SE_3 | wind_solar_forecast | Wind Onshore | 100.00% | keep |" in report
    assert "| SE_3 | prices | price | 100.00% |" in report
    assert "2025-01-15 to 2025-01-15" in report
