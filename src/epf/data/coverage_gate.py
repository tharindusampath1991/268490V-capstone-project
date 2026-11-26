"""Coverage gate for the ENTSO-E inputs (PROJECT_CONTEXT section 3.1).

For each zone and year the gate measures how much of the expected data exists:
  prices          share of market time units with a price
  load forecast   share of hours with a value
  wind and solar  share of hours with a value, per production type

A zone passes when, in every year, prices reach price_min_share and the load
forecast and at least one wind column reach forecast_min_share. Solar does not
decide the gate. The gate decides the extra zones only. Core zones are never
cut, so they are measured but not gated.

A forecast column below forecast_min_share in any year is marked "drop" for
that zone, unless the config lists it under keep_columns. Such a column is
kept by a logged decision, and its missing days are handled in cleaning.
"""

from datetime import timedelta
from functools import partial
from pathlib import Path

import pandas as pd
from entsoe import EntsoePandasClient

from epf.config import Zone
from epf.data.download_forecasts import (
    NO_DATA,
    fetch_load_forecast,
    fetch_wind_solar_forecast,
    hourly_coverage,
)
from epf.data.download_prices import check_prices, fetch_prices
from epf.data.entsoe_cache import cached_fetch
from epf.data.market_time import native_resolution

FETCHERS = {
    "prices": fetch_prices,
    "load_forecast": fetch_load_forecast,
    "wind_solar_forecast": fetch_wind_solar_forecast,
}
UNGATED_GROUP = "core"
YearRange = tuple[int, pd.Timestamp, pd.Timestamp]


def price_coverage(data: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                   quarter_hour_start: pd.Timestamp) -> dict:
    """Return the coverage row of one zone's prices in [start, end).

    Input: a frame from fetch_prices, start and end in market time.
    Output: the share of market time units with a price, plus the counts
        from check_prices.
    """
    counts = check_prices(data, start, end, quarter_hour_start)
    present = counts["expected"] - counts["missing"]
    return {
        "column": "price",
        "resolution": native_resolution(data.index),
        "expected": counts["expected"],
        "present": present,
        "share": present / counts["expected"],
        "days_with_gaps": counts["days_with_gaps"],
        "unexpected": counts["unexpected"],
        "duplicates": counts["duplicates"],
    }


def collect_coverage(client: EntsoePandasClient, zones: list[Zone], ranges: list[YearRange],
                     cache_dir: Path, quarter_hour_start: pd.Timestamp) -> pd.DataFrame:
    """Download every dataset, or read it from the cache, and measure its coverage.

    Input: zones in the order they should run, year pieces from year_ranges,
        the folder of the ENTSO-E cache and the first 15-minute delivery day.
    Output: one row per zone, dataset, column and year.
    """
    rows = []
    for zone in zones:
        for dataset, fetch in FETCHERS.items():
            for year, start, end in ranges:
                print(f"{zone.key:6s} {dataset:20s} {year}", flush=True)
                data = cached_fetch(partial(fetch, client, zone.key),
                                    cache_dir, dataset, zone.key, year, start, end)
                if dataset == "prices":
                    found = [price_coverage(data, start, end, quarter_hour_start)]
                else:
                    found = hourly_coverage(data, start, end)
                rows += [{"zone": zone.key, "dataset": dataset, "year": year, **row}
                         for row in found]
    return pd.DataFrame(rows)


def worst_share(coverage: pd.DataFrame, zone_key: str, dataset: str, years: list[int],
                column_prefix: str | None = None) -> float:
    """Return the lowest yearly share of one zone and dataset.

    Input: coverage rows, and the years that must all be covered. With a
        column prefix, only columns that start with it are used.
    Output: the best matching column is taken in each year, then the lowest
        year. A year without a matching row counts as 0.
    """
    part = coverage[(coverage["zone"] == zone_key) & (coverage["dataset"] == dataset)]
    if column_prefix is not None:
        part = part[part["column"].str.startswith(column_prefix)]
    best_per_year = part.groupby("year")["share"].max().reindex(years, fill_value=0.0)
    return float(best_per_year.min())


def verdicts(coverage: pd.DataFrame, zones: list[Zone], years: list[int],
             thresholds: dict) -> pd.DataFrame:
    """Apply the gate rule to each zone on its own.

    Input: coverage rows, the zones, the years that must all be covered, and
        the thresholds price_min_share and forecast_min_share.
    Output: one row per zone with the lowest yearly shares. The gate is PASS
        or FAIL for an extra zone and "not gated (core)" for a core zone.
    """
    rows = []
    for zone in zones:
        price = worst_share(coverage, zone.key, "prices", years)
        load = worst_share(coverage, zone.key, "load_forecast", years)
        wind = worst_share(coverage, zone.key, "wind_solar_forecast", years, column_prefix="Wind")
        passed = (price >= thresholds["price_min_share"]
                  and load >= thresholds["forecast_min_share"]
                  and wind >= thresholds["forecast_min_share"])
        if zone.group == UNGATED_GROUP:
            gate = "not gated (core)"
        else:
            gate = "PASS" if passed else "FAIL"
        rows.append({"zone": zone.key, "group": zone.group, "prices_min": price,
                     "load_fc_min": load, "wind_fc_min": wind, "gate": gate})
    return pd.DataFrame(rows)


def column_decisions(coverage: pd.DataFrame, years: list[int], thresholds: dict) -> pd.DataFrame:
    """Mark each forecast column of each zone as keep or drop.

    Input: coverage rows, the years that must all be covered, and the
        thresholds. thresholds may hold keep_columns, a list of zone and
        column pairs that are kept by a logged decision.
    Output: one row per zone and forecast column with its lowest yearly share.
        A column is "keep" when it reaches forecast_min_share in every year. A
        year in which the column is absent counts as 0. A column below the
        threshold is "keep by decision" when it is listed, otherwise "drop".
    """
    listed = {(entry["zone"], entry["column"]) for entry in thresholds.get("keep_columns", [])}
    forecasts = coverage[(coverage["dataset"] != "prices") & (coverage["column"] != NO_DATA)]
    rows = []
    for (zone_key, dataset, column), part in forecasts.groupby(["zone", "dataset", "column"],
                                                               sort=False):
        lowest = float(part.set_index("year")["share"].reindex(years, fill_value=0.0).min())
        if lowest >= thresholds["forecast_min_share"]:
            use = "keep"
        elif (zone_key, column) in listed:
            use = "keep by decision"
        else:
            use = "drop"
        rows.append({"zone": zone_key, "dataset": dataset, "column": column,
                     "min_share": lowest, "use": use})
    return pd.DataFrame(rows)


def to_markdown(table: pd.DataFrame, float_format: str = "{:.2%}") -> str:
    """Write a frame as a Markdown table.

    Input: a frame, and the format of float cells. The default shows shares
        as percentages. An empty float cell is shown as "-".
    """
    def cell(value: object) -> str:
        if isinstance(value, float):
            return "-" if pd.isna(value) else float_format.format(value)
        return str(value)

    header = "| " + " | ".join(str(name) for name in table.columns) + " |"
    rule = "|" + "---|" * len(table.columns)
    body = ["| " + " | ".join(cell(value) for value in row) + " |"
            for row in table.itertuples(index=False)]
    return "\n".join([header, rule, *body])


def build_report(coverage: pd.DataFrame, verdict: pd.DataFrame, decisions: pd.DataFrame,
                 start: pd.Timestamp, end: pd.Timestamp, thresholds: dict) -> str:
    """Write the gate report as Markdown.

    Input: the frames from collect_coverage, verdicts and column_decisions,
        the data period [start, end) in market time, and the thresholds.
    Output: the report text.
    """
    keys = ["zone", "dataset", "column"]
    shares = coverage.pivot_table(index=keys, columns="year", values="share",
                                  sort=False).reset_index()
    shares.columns = [str(name) for name in shares.columns]
    resolution = (coverage.groupby(keys, sort=False)["resolution"]
                  .agg(lambda values: ", ".join(sorted(set(values) - {"-"})) or "-")
                  .reset_index())
    prices = coverage[coverage["dataset"] == "prices"]
    gaps = (prices.pivot_table(index="zone", columns="year", values="days_with_gaps", sort=False)
            .fillna(0).astype(int).reset_index())
    gaps.columns = [str(name) for name in gaps.columns]
    repeats = (coverage.drop_duplicates(["zone", "dataset", "year"])
               .groupby(["zone", "dataset"], sort=False)["duplicates"].sum().reset_index())
    last_day = end.date() - timedelta(days=1)
    price_min = f"{thresholds['price_min_share']:.0%}"
    forecast_min = f"{thresholds['forecast_min_share']:.0%}"

    return "\n\n".join([
        "## ENTSO-E coverage gate\n\n"
        f"Delivery days {start.date()} to {last_day}. Core zones come first, then the zones in "
        "the group \"extra\".\n\n"
        f"A zone passes when prices reach {price_min} and the load forecast and at least one "
        f"wind column reach {forecast_min}, in every year. The gate table shows the lowest "
        "yearly share. The gate decides the extra zones only. Core zones are never cut, so "
        "their shares are shown without a verdict.",
        "### Gate result\n\n" + to_markdown(verdict),
        f"### Forecast columns\n\nA column below {forecast_min} in any year is marked drop "
        "for that zone. \"keep by decision\" marks a column that is below the threshold and "
        "is kept by a logged decision (docs/DECISIONS.md). Its missing days are handled in "
        "the cleaning step.\n\n" + to_markdown(decisions),
        "### Share of expected time steps present, by year\n\n" + to_markdown(shares),
        "### Native resolution\n\n" + to_markdown(resolution),
        "### Delivery days with at least one missing price\n\n" + to_markdown(gaps),
        "### Repeated timestamps, summed over the years\n\n" + to_markdown(repeats),
    ]) + "\n"
