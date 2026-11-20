"""Day-1 coverage gate for the ENTSO-E inputs (PROJECT_CONTEXT section 3.1).

Usage, from the repo root:
    .venv\\Scripts\\python scripts/check_coverage.py

For every configured zone and year the script downloads day-ahead prices, the
day-ahead load forecast and the day-ahead wind and solar forecast. Downloads
are saved in the raw cache, so a second run on the same day only reads files.
It then applies the gate rule and writes the report named in the config.

Zones, dates, thresholds and paths come from config/config.yaml. Core zones
run first. The gate logic is in src/epf/data/coverage_gate.py. The token is
read from ENTSOE_API_TOKEN or the .env file and is never printed.
"""

import sys

import pandas as pd
from entsoe import EntsoePandasClient

from epf.config import REPO_ROOT, load_config, ordered_zones
from epf.data.coverage_gate import build_report, collect_coverage, column_decisions, verdicts
from epf.data.entsoe_api import EntsoeRequestError, MissingTokenError, load_token
from epf.data.market_time import data_range, year_ranges


def main() -> None:
    """Run the gate for all configured zones and write the Markdown report."""
    config = load_config()
    market_tz = config["market"]["timezone"]
    today = pd.Timestamp.now(tz=market_tz).normalize()
    start, end = data_range(config, today)
    ranges = year_ranges(start, end)
    years = [year for year, _, _ in ranges]
    zones = ordered_zones(config)
    thresholds = config["coverage_gate"]
    quarter_hour_start = pd.Timestamp(config["market"]["quarter_hour_start"], tz=market_tz)
    cache_dir = REPO_ROOT / config["paths"]["raw"] / "entsoe"

    try:
        token = load_token()
    except MissingTokenError as error:
        sys.exit(str(error))
    client = EntsoePandasClient(api_key=token, timeout=config["entsoe"]["timeout_seconds"])
    try:
        coverage = collect_coverage(client, zones, ranges, cache_dir, quarter_hour_start)
    except EntsoeRequestError as error:
        sys.exit(f"{error} HTTP status 401 means the token was rejected. "
                 "Finished years are saved, so run the command again to resume.")

    verdict = verdicts(coverage, zones, years, thresholds)
    decisions = column_decisions(coverage, years, thresholds)
    report = build_report(coverage, verdict, decisions, start, end, thresholds)
    report_path = REPO_ROOT / config["paths"]["coverage_report"]
    report_path.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
