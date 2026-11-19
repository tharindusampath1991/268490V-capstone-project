"""Coverage gate for ENTSO-E inputs (PROJECT_CONTEXT section 3.1).

For each zone and year this script downloads
  - day-ahead prices,
  - the day-ahead load forecast,
  - the day-ahead wind and solar forecast,
caches them as Parquet under data/raw/entsoe/, and reports the share of
expected time steps that are present. It then applies the gate:

  prices         at least 99% of market time units present in every year
  load forecast  at least 95% of hours present in every year
  wind forecast  at least one wind column with 95% of hours in every year

Solar is reported but does not decide the gate. A column below 95% should be
dropped for that zone.

Written against entsoe-py 1.0.0. Needs: entsoe-py, pandas, pyarrow.

Usage (from the repo root):
    python scripts/check_coverage.py
    python scripts/check_coverage.py --zones SE_1 SE_2 SE_3 SE_4 --years 2019 2023 2026

The token is read from the ENTSOE_API_TOKEN environment variable, or from a
.env file in the working directory. It is never printed or written anywhere.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import requests
from entsoe import EntsoePandasClient
from entsoe.exceptions import NoMatchingDataError

MARKET_TZ = "Europe/Brussels"  # CET/CEST, the day-ahead market's clock
# First delivery day with 15-minute prices in the day-ahead market.
QUARTER_HOUR_START = pd.Timestamp("2025-10-01", tz=MARKET_TZ)

DEFAULT_ZONES = ["DE_LU", "FR", "ES", "SE_1", "SE_2", "SE_3", "SE_4"]
FIRST_YEAR = 2019

PRICE_MIN_SHARE = 0.99
FORECAST_MIN_SHARE = 0.95

DATASETS = ["prices", "load_forecast", "wind_solar_forecast"]


def load_token() -> str:
    """Return the API token from the environment or a local .env file."""
    token = os.environ.get("ENTSOE_API_TOKEN")
    env_file = Path(".env")
    if not token and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "ENTSOE_API_TOKEN":
                token = value.strip().strip('"').strip("'")
    if not token:
        sys.exit("ENTSOE_API_TOKEN is not set (environment variable or .env file).")
    return token


def year_bounds(year: int, today: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Start (inclusive) and end (exclusive) of a year, cut at today 00:00."""
    start = pd.Timestamp(f"{year}-01-01", tz=MARKET_TZ)
    end = min(pd.Timestamp(f"{year + 1}-01-01", tz=MARKET_TZ), today)
    return start, end


def fetch(client, dataset: str, zone: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Download one dataset for one zone and period. Empty frame if no data."""
    try:
        if dataset == "prices":
            data = client.query_day_ahead_prices(zone, start=start, end=end).to_frame("price")
        elif dataset == "load_forecast":
            data = client.query_load_forecast(zone, start=start, end=end)
        elif dataset == "wind_solar_forecast":
            data = client.query_wind_and_solar_forecast(zone, start=start, end=end)
        else:
            raise ValueError(f"Unknown dataset: {dataset}")
    except NoMatchingDataError:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [" ".join(str(level) for level in column) for column in data.columns]
    data = data.tz_convert("UTC")
    data = data[~data.index.duplicated(keep="first")].sort_index()
    # The client includes the end timestamp. Keep [start, end) only.
    return data[(data.index >= start) & (data.index < end)]


def cached_fetch(client, raw_dir: Path, dataset: str, zone: str, year: int,
                 start: pd.Timestamp, end: pd.Timestamp, is_current_year: bool) -> pd.DataFrame:
    """Read a finished year from disk if present, otherwise download and save."""
    path = raw_dir / dataset / f"{zone}_{year}.parquet"
    if path.exists() and not is_current_year:
        return pd.read_parquet(path)
    data = fetch(client, dataset, zone, start, end)
    path.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(path)
    return data


def native_resolution(index: pd.DatetimeIndex) -> str:
    """Most common step between consecutive timestamps, for example '15min'."""
    if len(index) < 2:
        return "-"
    step = index.to_series().diff().mode().iloc[0]
    return f"{int(step.total_seconds() // 60)}min"


def steps(start: pd.Timestamp, end: pd.Timestamp, freq: str) -> pd.DatetimeIndex:
    """Time steps in [start, end). Empty when the period is empty."""
    index = pd.date_range(start, end, freq=freq)
    return index[index < end]


def expected_price_index(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Hourly steps before the 15-minute switch, quarter-hourly from it."""
    switch = min(max(QUARTER_HOUR_START, start), end)
    return steps(start, switch, "h").append(steps(switch, end, "15min")).tz_convert("UTC")


def price_coverage(data: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Share of expected market time units with a price, and days with gaps."""
    expected = expected_price_index(start, end)
    if data.empty:
        present = pd.Series(False, index=expected)
    else:
        present = data["price"].reindex(expected).notna()
    local_day = present.index.tz_convert(MARKET_TZ).date
    days_with_gaps = int((~present).groupby(local_day).any().sum())
    return {
        "column": "price",
        "resolution": native_resolution(data.index) if not data.empty else "-",
        "expected": len(expected),
        "present": int(present.sum()),
        "share": float(present.mean()) if len(expected) else float("nan"),
        "days_with_gaps": days_with_gaps,
    }


def hourly_coverage(data: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    """Per column: share of hours in [start, end) that have at least one value."""
    expected = steps(start, end, "h").tz_convert("UTC")
    if data.empty:
        return [{"column": "(no data)", "resolution": "-", "expected": len(expected),
                 "present": 0, "share": 0.0, "days_with_gaps": None}]
    resolution = native_resolution(data.index)
    hourly = data.resample("h").mean().reindex(expected)
    rows = []
    for column in hourly.columns:
        present = hourly[column].notna()
        rows.append({"column": str(column), "resolution": resolution, "expected": len(expected),
                     "present": int(present.sum()), "share": float(present.mean()),
                     "days_with_gaps": None})
    return rows


def collect(client, zones: list[str], years: list[int], raw_dir: Path,
            today: pd.Timestamp) -> pd.DataFrame:
    """Download everything and return one coverage row per zone, series and year."""
    rows = []
    for zone in zones:
        for dataset in DATASETS:
            for year in years:
                start, end = year_bounds(year, today)
                if start >= end:
                    continue
                print(f"{zone:6s} {dataset:20s} {year}", flush=True)
                data = cached_fetch(client, raw_dir, dataset, zone, year, start, end,
                                    is_current_year=(year == today.year))
                if dataset == "prices":
                    results = [price_coverage(data, start, end)]
                else:
                    results = hourly_coverage(data, start, end)
                for result in results:
                    rows.append({"zone": zone, "dataset": dataset, "year": year, **result})
    return pd.DataFrame(rows)


def worst_share(coverage: pd.DataFrame, zone: str, dataset: str, years: list[int],
                column_prefix: str | None = None) -> float:
    """Lowest yearly share for a zone and dataset. With a prefix, the best
    matching column is used in each year (for example any 'Wind' column)."""
    part = coverage[(coverage["zone"] == zone) & (coverage["dataset"] == dataset)]
    if column_prefix is not None:
        part = part[part["column"].str.startswith(column_prefix)]
    best_per_year = part.groupby("year")["share"].max().reindex(years, fill_value=0.0)
    return float(best_per_year.min())


def verdicts(coverage: pd.DataFrame, zones: list[str], years: list[int]) -> pd.DataFrame:
    """Apply the gate rules to each zone."""
    rows = []
    for zone in zones:
        price = worst_share(coverage, zone, "prices", years)
        load = worst_share(coverage, zone, "load_forecast", years)
        wind = worst_share(coverage, zone, "wind_solar_forecast", years, column_prefix="Wind")
        solar = worst_share(coverage, zone, "wind_solar_forecast", years, column_prefix="Solar")
        passed = (price >= PRICE_MIN_SHARE and load >= FORECAST_MIN_SHARE
                  and wind >= FORECAST_MIN_SHARE)
        rows.append({"zone": zone, "prices_min": price, "load_fc_min": load, "wind_fc_min": wind,
                     "solar_fc_min": solar,
                     "solar": "keep" if solar >= FORECAST_MIN_SHARE else "drop",
                     "gate": "PASS" if passed else "FAIL"})
    return pd.DataFrame(rows)


def to_markdown(table: pd.DataFrame) -> str:
    """Small Markdown table writer, so no extra dependency is needed."""
    def cell(value) -> str:
        if isinstance(value, float):
            return "-" if pd.isna(value) else f"{value:.1%}"
        return str(value)
    header = "| " + " | ".join(str(c) for c in table.columns) + " |"
    rule = "|" + "---|" * len(table.columns)
    body = ["| " + " | ".join(cell(v) for v in row) + " |" for row in table.itertuples(index=False)]
    return "\n".join([header, rule, *body])


def build_report(coverage: pd.DataFrame, verdict: pd.DataFrame, today: pd.Timestamp) -> str:
    """Markdown report: gate result, then yearly coverage per series."""
    shares = coverage.pivot_table(index=["zone", "dataset", "column"], columns="year",
                                  values="share", sort=False).reset_index()
    shares.columns = [str(c) for c in shares.columns]
    resolution = (coverage.groupby(["zone", "dataset", "column"], sort=False)["resolution"]
                  .agg(lambda s: ", ".join(sorted(set(s) - {"-"})) or "-").reset_index())
    gaps = coverage[coverage["dataset"] == "prices"].pivot_table(
        index="zone", columns="year", values="days_with_gaps", sort=False).fillna(0).astype(int).reset_index()
    gaps.columns = [str(c) for c in gaps.columns]
    return "\n\n".join([
        f"## ENTSO-E coverage gate\n\nData through {(today - pd.Timedelta(days=1)).date()}. "
        f"Gate: prices >= {PRICE_MIN_SHARE:.0%}, load and wind forecast >= {FORECAST_MIN_SHARE:.0%}, "
        "in every year (minimum yearly share shown).",
        "### Gate result\n\n" + to_markdown(verdict),
        "### Share of expected time steps present, by year\n\n" + to_markdown(shares),
        "### Native resolution\n\n" + to_markdown(resolution),
        "### Delivery days with at least one missing price\n\n" + to_markdown(gaps),
    ]) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="ENTSO-E coverage gate")
    parser.add_argument("--zones", nargs="+", default=DEFAULT_ZONES)
    parser.add_argument("--years", nargs="+", type=int, default=None)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/entsoe"))
    parser.add_argument("--out", type=Path, default=Path("docs/coverage_gate.md"))
    args = parser.parse_args()

    today = pd.Timestamp.now(tz=MARKET_TZ).normalize()
    years = args.years or list(range(FIRST_YEAR, today.year + 1))

    client = EntsoePandasClient(api_key=load_token())
    try:
        coverage = collect(client, args.zones, years, args.raw_dir, today)
    except requests.exceptions.RequestException as error:
        # The request URL carries the token, so never print the error itself.
        status = getattr(getattr(error, "response", None), "status_code", None)
        sys.exit(f"ENTSO-E request failed: {type(error).__name__}, HTTP status {status}. "
                 "401 means the token was rejected. Finished years are cached, so rerun to resume.")
    verdict = verdicts(coverage, args.zones, years)

    report = build_report(coverage, verdict, today)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
