"""Download the actual total load from ENTSO-E into the raw cache.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.data.download_actual_load

Zones, dates and folders come from config/config.yaml. Core zones run first.
The command prints the same counts as epf.data.download_forecasts and changes
no value. The token is read from ENTSOE_API_TOKEN or the .env file and is
never printed.

Actual load is measured after delivery. A forecast for delivery day D may use
it through day D-2 only (PROJECT_CONTEXT section 5).
"""

import pandas as pd
from entsoe import EntsoePandasClient

from epf.data.download_forecasts import fetch_frame, run_downloads

DATASET = "actual_load"


def fetch_actual_load(client: EntsoePandasClient, zone_key: str,
                      start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Download the actual total load of one zone for [start, end).

    Input: an entsoe-py client, the ENTSO-E area key of the zone, and a time
        zone aware start and end.
    Output: one column "Actual Load" in MW with a UTC index. The end timestamp
        is left out. The frame is empty when ENTSO-E has no data.
    """
    return fetch_frame(client.query_load, zone_key, start, end)


def main() -> None:
    """Download the actual load of all configured zones and print the counts."""
    run_downloads({DATASET: fetch_actual_load})


if __name__ == "__main__":
    main()
