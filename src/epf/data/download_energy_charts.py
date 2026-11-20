"""Download day-ahead prices from the Energy-Charts API for the price cross-check.

All zones are free to query. Energy-Charts states the licence of each answer:
CC BY 4.0 for some zones, "private and internal use only" for the others. Each
downloaded frame records which of the two applies, so that data and results of
the second kind stay out of committed files.
"""

import time
from collections.abc import Callable
from datetime import timedelta

import pandas as pd

OPEN_LICENCE = "CC BY 4.0"


class EnergyChartsError(Exception):
    """The Energy-Charts API did not answer with data.

    retry_after holds the seconds to wait when the API answered "too many
    requests" (HTTP 429). It is None for every other failure.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def parse_price_response(body: dict) -> pd.DataFrame:
    """Turn the JSON body of a /v2/price answer into a price frame.

    Input: the decoded JSON body. Its timestamps carry their own UTC offset.
    Output: a UTC index and two columns. "price" is in EUR/MWh, and a null
        price becomes an empty value. "open_licence" is True when the answer
        states CC BY 4.0 and False for private and internal use only.
    """
    records = body["data"]
    index = pd.to_datetime([record["timestamp"] for record in records], utc=True)
    prices = [record["values"]["day_ahead_price"] for record in records]
    data = pd.DataFrame({"price": pd.Series(prices, index=index, dtype="float64")})
    data["open_licence"] = (body.get("license") or "").startswith(OPEN_LICENCE)
    return data


def fetch_energy_charts_prices(get: Callable, url: str, zone_code: str,
                               start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Download the Energy-Charts day-ahead prices of one zone for [start, end).

    Input: get is requests.get or a function with the same call. url is the
        /v2/price endpoint. zone_code is the Energy-Charts bidding zone. start
        and end are 00:00 of a day in market time.
    Output: the frame from parse_price_response, without the end timestamp.
    Raises EnergyChartsError when the API answers with an HTTP error status.
    """
    last_day = end.date() - timedelta(days=1)
    params = {"bzn": zone_code, "start": str(start.date()), "end": str(last_day)}
    response = get(url, params=params)
    if response.status_code != 200:
        wait = response.headers.get("Retry-After") if response.status_code == 429 else None
        raise EnergyChartsError(
            f"Energy-Charts answered HTTP {response.status_code} for {zone_code}, "
            f"{params['start']} to {params['end']}.",
            retry_after=float(wait) if wait is not None else None,
        )
    data = parse_price_response(response.json())
    return data[(data.index >= start) & (data.index < end)]


def fetch_politely(pause_seconds: float, get: Callable, url: str, zone_code: str,
                   start: pd.Timestamp, end: pd.Timestamp,
                   sleep: Callable[[float], None] = time.sleep) -> pd.DataFrame:
    """Download Energy-Charts prices at the request rate the API allows.

    Input: pause_seconds is the wait before the request. The other arguments
        are those of fetch_energy_charts_prices. sleep is replaced in tests.
    Output: the frame from fetch_energy_charts_prices. When the API answers
        "too many requests", the function waits the seconds of the Retry-After
        header and asks one more time.
    """
    sleep(pause_seconds)
    try:
        return fetch_energy_charts_prices(get, url, zone_code, start, end)
    except EnergyChartsError as error:
        if error.retry_after is None:
            raise
        sleep(error.retry_after)
        return fetch_energy_charts_prices(get, url, zone_code, start, end)
