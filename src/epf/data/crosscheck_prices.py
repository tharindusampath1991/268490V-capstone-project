"""Cross-check the saved ENTSO-E prices against Energy-Charts (DECISIONS entries 7 and 12).

Usage, from the repo root, after epf.data.download_prices:
    .venv\\Scripts\\python -m epf.data.crosscheck_prices

ENTSO-E stays the only source of prices. Energy-Charts prices are compared
timestamp by timestamp, and the differences are written to a report. They
are never used to correct or fill ENTSO-E values.

Energy-Charts data is CC BY 4.0 for some zones and for private and internal
use only for the others. Results of the first kind go into the committed
report. Results of the second kind go into a local file under data/, which
git ignores.
"""

import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

import pandas as pd
import requests

from epf.config import REPO_ROOT, Zone, load_config, ordered_zones
from epf.data.coverage_gate import to_markdown
from epf.data.download_energy_charts import EnergyChartsError, fetch_politely
from epf.data.entsoe_cache import cached_fetch, read_saved
from epf.data.market_time import data_range, year_ranges

FetchOther = Callable[[str, pd.Timestamp, pd.Timestamp], pd.DataFrame]


def compare_prices(entsoe: pd.DataFrame, other: pd.DataFrame, tolerance: float) -> dict:
    """Compare two price frames timestamp by timestamp.

    Input: two frames with a "price" column and a UTC index, and the largest
        difference in EUR/MWh that still counts as equal.
    Output: counts.
        compared            timestamps with a price in both frames
        mismatches          compared timestamps that differ by more than the tolerance
        max_abs_diff        largest absolute difference in EUR/MWh
        only_entsoe         timestamps with a price in the first frame only
        only_energy_charts  timestamps with a price in the second frame only
    """
    first = entsoe["price"].dropna()
    second = other["price"].dropna()
    common = first.index.intersection(second.index)
    # In floating point 0.07 - 0.06 is 0.010000000000000009, just above a tolerance of 0.01.
    difference = (first.loc[common] - second.loc[common]).abs().round(6)
    return {
        "compared": len(common),
        "mismatches": int((difference > tolerance).sum()),
        "max_abs_diff": float(difference.max()) if len(common) else float("nan"),
        "only_entsoe": len(first.index.difference(second.index)),
        "only_energy_charts": len(second.index.difference(first.index)),
    }


def run_crosscheck(zones: list[Zone], years: list[int], entsoe_dir: Path, other_dir: Path,
                   fetch_other: FetchOther, tolerance: float, market_tz: str) -> pd.DataFrame:
    """Compare the saved ENTSO-E prices of each zone and year with a second source.

    Input: zones in the order they should run, the years to check, the folder
        of the ENTSO-E cache, the folder that caches the second source, a
        function that downloads the second source for a zone code and [start,
        end) in market time, the tolerance in EUR/MWh and the market time zone.
    Output: one row per zone and year with the counts from compare_prices.
        open_licence is True when the second source is CC BY 4.0 data. It is
        False for restricted data and when the second source has no data.
        Zones without an energy_charts code are left out.
    Raises FileNotFoundError when an ENTSO-E price file is not in the cache.
    """
    rows = []
    for zone in zones:
        if zone.energy_charts is None:
            continue
        for year in years:
            print(f"{zone.key:6s} cross-check {year}", flush=True)
            entsoe, start, end = read_saved(entsoe_dir, "prices", zone.key, year)
            other = cached_fetch(partial(fetch_other, zone.energy_charts),
                                 other_dir, "prices", zone.key, year,
                                 start.tz_convert(market_tz), end.tz_convert(market_tz))
            open_licence = len(other) > 0 and bool(other["open_licence"].all())
            rows.append({"zone": zone.key, "year": year,
                         **compare_prices(entsoe, other, tolerance),
                         "open_licence": open_licence})
    return pd.DataFrame(rows)


def write_reports(rows: pd.DataFrame, tolerance: float, public_path: Path,
                  local_path: Path) -> None:
    """Write the cross-check results to a committed report and a local file.

    Input: the frame from run_crosscheck, the tolerance in EUR/MWh, the path
        of the committed report and the path of the local file.
    Output: rows with open_licence go to the committed report. All other rows
        go to the local file only. The committed report names those zones but
        shows none of their numbers.
    """
    is_open = rows["open_licence"].astype(bool)
    public = rows[is_open].drop(columns="open_licence")
    restricted = rows[~is_open].drop(columns="open_licence")
    restricted_zones = ", ".join(restricted["zone"].unique()) or "none"
    intro = (
        "ENTSO-E is the only source of prices in this project (DECISIONS entries 7 and 12). "
        "Energy-Charts prices are compared timestamp by timestamp. They are never used to "
        "correct or fill ENTSO-E values.\n\n"
        f"Two prices count as different when they are more than {tolerance} EUR/MWh apart. "
        "max_abs_diff is in EUR/MWh. The last two columns count timestamps that only one "
        "source has."
    )

    public_path.write_text("\n\n".join([
        "## Price cross-check: ENTSO-E against Energy-Charts",
        intro,
        "Energy-Charts data: CC BY 4.0, Bundesnetzagentur | SMARD.de, through the "
        "Energy-Charts API of Fraunhofer ISE (api.energy-charts.info).",
        f"Checked locally, results not published: {restricted_zones}. Energy-Charts provides "
        "the prices of these zones for private and internal use only.",
        "### Result by zone and year\n\n" + to_markdown(public, float_format="{:.2f}"),
    ]) + "\n", encoding="utf-8")

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text("\n\n".join([
        "## Price cross-check, restricted zones. Local file, do not commit or publish",
        intro,
        "Energy-Charts provides the prices of these zones for private and internal use only.",
        "### Result by zone and year\n\n" + to_markdown(restricted, float_format="{:.2f}"),
    ]) + "\n", encoding="utf-8")


def main() -> None:
    """Cross-check the saved prices of all configured zones and write both reports."""
    config = load_config()
    market_tz = config["market"]["timezone"]
    settings = config["energy_charts"]
    today = pd.Timestamp.now(tz=market_tz).normalize()
    years = [year for year, _, _ in year_ranges(*data_range(config, today))]
    raw_dir = REPO_ROOT / config["paths"]["raw"]
    get = partial(requests.get, timeout=settings["timeout_seconds"])
    fetch_other = partial(fetch_politely, settings["pause_seconds"], get, settings["price_url"])

    try:
        rows = run_crosscheck(ordered_zones(config), years, raw_dir / "entsoe",
                              raw_dir / "energy_charts", fetch_other,
                              config["crosscheck"]["tolerance"], market_tz)
    except FileNotFoundError as error:
        sys.exit(f"{error} Run epf.data.download_prices first.")
    except EnergyChartsError as error:
        sys.exit(f"{error} Finished years are saved, so run the command again to resume.")

    public_path = REPO_ROOT / config["paths"]["crosscheck_report"]
    local_path = REPO_ROOT / config["paths"]["crosscheck_local_report"]
    write_reports(rows, config["crosscheck"]["tolerance"], public_path, local_path)
    print("\n" + rows.to_string(index=False))
    print(f"\nPublic report: {public_path}\nLocal report, not for publishing: {local_path}")


if __name__ == "__main__":
    main()
