"""Tests for the coverage gate. They use synthetic frames, a fake client and no network."""

import pandas as pd

from epf.config import Zone
from epf.data.coverage_gate import (
    build_report,
    collect_coverage,
    column_decisions,
    verdicts,
)

MARKET_TZ = "Europe/Berlin"
SWITCH = pd.Timestamp("2025-10-01", tz=MARKET_TZ)
DAY_START = pd.Timestamp("2025-01-15", tz=MARKET_TZ)
DAY_END = pd.Timestamp("2025-01-16", tz=MARKET_TZ)
THRESHOLDS = {"price_min_share": 0.99, "forecast_min_share": 0.95}
XX = Zone("XX", "PL", "extra")
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


def test_verdicts_pass_a_zone_that_meets_all_three_thresholds():
    coverage = pd.DataFrame(coverage_rows("XX", GOOD))

    verdict = verdicts(coverage, [XX], [2025], THRESHOLDS)

    assert verdict["gate"].tolist() == ["PASS"]
    assert verdict["group"].tolist() == ["extra"]


def test_verdicts_fail_a_zone_when_one_year_is_below_a_threshold():
    low_prices = {**GOOD, ("prices", "price"): 0.98}
    coverage = pd.DataFrame(coverage_rows("XX", GOOD, 2024) + coverage_rows("XX", low_prices, 2025))

    verdict = verdicts(coverage, [XX], [2024, 2025], THRESHOLDS)

    assert verdict["prices_min"].tolist() == [0.98]
    assert verdict["gate"].tolist() == ["FAIL"]


def test_verdicts_use_the_best_wind_column_of_each_year():
    shares = {**GOOD, ("wind_solar_forecast", "Wind Onshore"): 0.50,
              ("wind_solar_forecast", "Wind Offshore"): 0.99}
    coverage = pd.DataFrame(coverage_rows("XX", shares))

    verdict = verdicts(coverage, [XX], [2025], THRESHOLDS)

    assert verdict["wind_fc_min"].tolist() == [0.99]
    assert verdict["gate"].tolist() == ["PASS"]


def test_verdicts_fail_a_zone_with_no_wind_forecast_in_one_year():
    without_wind = {key: share for key, share in GOOD.items() if key[1] != "Wind Onshore"}
    coverage = pd.DataFrame(coverage_rows("XX", GOOD, 2024)
                            + coverage_rows("XX", without_wind, 2025))

    verdict = verdicts(coverage, [XX], [2024, 2025], THRESHOLDS)

    assert verdict["wind_fc_min"].tolist() == [0.0]
    assert verdict["gate"].tolist() == ["FAIL"]


def test_verdicts_judge_each_zone_on_its_own():
    low_load = {**GOOD, ("load_forecast", "Forecasted Load"): 0.50}
    coverage = pd.DataFrame(coverage_rows("XX", GOOD) + coverage_rows("YY", low_load))

    verdict = verdicts(coverage, [XX, Zone("YY", "PL", "extra")], [2025], THRESHOLDS)

    assert verdict["zone"].tolist() == ["XX", "YY"]
    assert verdict["gate"].tolist() == ["PASS", "FAIL"]


def test_column_decisions_drop_a_forecast_column_that_is_low_or_absent_in_any_year():
    with_offshore = {**GOOD, ("wind_solar_forecast", "Wind Offshore"): 0.99}
    coverage = pd.DataFrame(coverage_rows("XX", GOOD, 2024)
                            + coverage_rows("XX", with_offshore, 2025))

    decisions = column_decisions(coverage, [2024, 2025], THRESHOLDS)

    assert {row.column: row.use for row in decisions.itertuples()} == {
        "Forecasted Load": "keep",
        "Wind Onshore": "keep",
        "Solar": "drop",
        "Wind Offshore": "drop",
    }


def test_collect_coverage_measures_prices_and_both_forecasts(tmp_path):
    coverage = collect_coverage(FakeClient(), [XX], [(2025, DAY_START, DAY_END)], tmp_path, SWITCH)

    assert {(row.dataset, row.column): row.share for row in coverage.itertuples()} == {
        ("prices", "price"): 1.0,
        ("load_forecast", "Forecasted Load"): 1.0,
        ("wind_solar_forecast", "Wind Onshore"): 1.0,
    }
    assert coverage["zone"].unique().tolist() == ["XX"]
    assert coverage["year"].unique().tolist() == [2025]


def test_build_report_shows_the_gate_result_and_the_yearly_shares(tmp_path):
    coverage = collect_coverage(FakeClient(), [XX], [(2025, DAY_START, DAY_END)], tmp_path, SWITCH)
    verdict = verdicts(coverage, [XX], [2025], THRESHOLDS)
    decisions = column_decisions(coverage, [2025], THRESHOLDS)

    report = build_report(coverage, verdict, decisions, DAY_START, DAY_END, THRESHOLDS)

    assert "| XX | extra | 100.00% | 100.00% | 100.00% | PASS |" in report
    assert "| XX | wind_solar_forecast | Wind Onshore | 100.00% | keep |" in report
    assert "| XX | prices | price | 100.00% |" in report
    assert "2025-01-15 to 2025-01-15" in report


def test_verdicts_do_not_gate_a_core_zone():
    low_wind = {**GOOD, ("wind_solar_forecast", "Wind Onshore"): 0.90}
    coverage = pd.DataFrame(coverage_rows("ES", low_wind))

    verdict = verdicts(coverage, [Zone("ES", "ES", "core")], [2025], THRESHOLDS)

    assert verdict["wind_fc_min"].tolist() == [0.90]
    assert verdict["gate"].tolist() == ["not gated (core)"]


def test_column_decisions_keep_a_column_that_the_config_lists_as_an_exception():
    low_wind = {**GOOD, ("wind_solar_forecast", "Wind Onshore"): 0.90}
    coverage = pd.DataFrame(coverage_rows("ES", low_wind) + coverage_rows("XX", low_wind))
    thresholds = {**THRESHOLDS, "keep_columns": [{"zone": "ES", "column": "Wind Onshore"}]}

    decisions = column_decisions(coverage, [2025], thresholds)

    uses = {(row.zone, row.column): row.use for row in decisions.itertuples()}
    assert uses[("ES", "Wind Onshore")] == "keep by decision"
    assert uses[("XX", "Wind Onshore")] == "drop"
    assert uses[("ES", "Solar")] == "drop"
    assert uses[("ES", "Forecasted Load")] == "keep"
