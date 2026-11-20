"""Tests for the Energy-Charts price download. They use a fake HTTP call and no network."""

import pandas as pd
import pytest

from epf.data.download_energy_charts import (
    EnergyChartsError,
    fetch_energy_charts_prices,
    fetch_politely,
    parse_price_response,
)

MARKET_TZ = "Europe/Berlin"
URL = "https://example.invalid/v2/price"
CC_BY = "CC BY 4.0 (creativecommons.org/licenses/by/4.0) from Bundesnetzagentur | SMARD.de"
RESTRICTED = "The data provided herein is for private and internal use only."


def price_body(records: list[tuple[str, float | None]], licence: str = CC_BY) -> dict:
    """An answer with every key of a real /v2/price response."""
    return {
        "schema_version": "2.0",
        "endpoint": "price",
        "country": "de",
        "bidding_zone": "DE-LU",
        "timezone": "Europe/Berlin",
        "resolution": "PT1H",
        "interval_minutes": 60,
        "unit": "EUR / MWh",
        "generated_at": "2026-11-20T12:00:00+01:00",
        "available_from": records[0][0] if records else None,
        "available_until": records[-1][0] if records else None,
        "series": [{"id": "day_ahead_price", "name": "Day Ahead Price"}],
        "data": [{"timestamp": timestamp, "values": {"day_ahead_price": price}}
                 for timestamp, price in records],
        "attributes": {},
        "license": licence,
        "deprecated": False,
    }


class FakeResponse:
    """Stands in for requests.Response."""

    def __init__(self, status_code: int, body: dict, headers: dict | None = None) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}

    def json(self) -> dict:
        return self.body


def get_returning(response: FakeResponse, calls: list):
    """A function with the call of requests.get that records its arguments."""
    def get(url: str, params: dict) -> FakeResponse:
        calls.append((url, params))
        return response
    return get


def get_answering_in_turn(responses: list[FakeResponse]):
    """A function with the call of requests.get that gives the next response on each call."""
    remaining = list(responses)

    def get(url: str, params: dict) -> FakeResponse:
        return remaining.pop(0)
    return get


DAY_START = pd.Timestamp("2025-01-15", tz=MARKET_TZ)
DAY_END = pd.Timestamp("2025-01-16", tz=MARKET_TZ)
ONE_HOUR = price_body([("2025-01-15T00:00:00+01:00", 50.0)])
TOO_MANY = FakeResponse(429, {"detail": "Too many requests"}, headers={"Retry-After": "17"})


def test_parse_price_response_returns_prices_with_a_utc_index():
    body = price_body([("2025-03-30T01:00:00+01:00", 40.5), ("2025-03-30T03:00:00+02:00", -3.0)])

    data = parse_price_response(body)

    assert str(data.index.tz) == "UTC"
    assert data.index.tolist() == [pd.Timestamp("2025-03-30 00:00", tz="UTC"),
                                   pd.Timestamp("2025-03-30 01:00", tz="UTC")]
    assert data["price"].tolist() == [40.5, -3.0]


def test_parse_price_response_keeps_a_missing_price_as_an_empty_value():
    body = price_body([("2025-01-15T00:00:00+01:00", None), ("2025-01-15T01:00:00+01:00", 50.0)])

    data = parse_price_response(body)

    assert data["price"].isna().tolist() == [True, False]


def test_parse_price_response_marks_whether_the_licence_is_cc_by():
    record = [("2025-01-15T00:00:00+01:00", 50.0)]

    open_data = parse_price_response(price_body(record))
    restricted = parse_price_response(price_body(record, licence=RESTRICTED))

    assert open_data["open_licence"].tolist() == [True]
    assert restricted["open_licence"].tolist() == [False]


def test_fetch_energy_charts_prices_asks_for_whole_days_and_leaves_out_the_end():
    hours = pd.date_range("2025-01-15", "2025-01-16", freq="h", tz=MARKET_TZ)
    body = price_body([(hour.isoformat(), 50.0) for hour in hours])
    calls = []

    data = fetch_energy_charts_prices(get_returning(FakeResponse(200, body), calls), URL, "DE-LU",
                                      pd.Timestamp("2025-01-15", tz=MARKET_TZ),
                                      pd.Timestamp("2025-01-16", tz=MARKET_TZ))

    assert calls == [(URL, {"bzn": "DE-LU", "start": "2025-01-15", "end": "2025-01-15"})]
    assert len(data) == 24
    assert data.index[0] == pd.Timestamp("2025-01-14 23:00", tz="UTC")
    assert data.index[-1] == pd.Timestamp("2025-01-15 22:00", tz="UTC")


def test_fetch_energy_charts_prices_raises_on_an_http_error_status():
    get = get_returning(FakeResponse(429, {"detail": "Too many requests"}), [])

    with pytest.raises(EnergyChartsError, match="429"):
        fetch_energy_charts_prices(get, URL, "DE-LU", pd.Timestamp("2025-01-15", tz=MARKET_TZ),
                                   pd.Timestamp("2025-01-16", tz=MARKET_TZ))


def test_fetch_energy_charts_prices_reports_the_wait_of_a_rate_limit_answer():
    with pytest.raises(EnergyChartsError) as caught:
        fetch_energy_charts_prices(get_returning(TOO_MANY, []), URL, "DE-LU", DAY_START, DAY_END)

    assert caught.value.retry_after == 17.0


def test_fetch_politely_waits_before_it_asks():
    waits = []

    data = fetch_politely(31, get_returning(FakeResponse(200, ONE_HOUR), []), URL, "DE-LU",
                          DAY_START, DAY_END, sleep=waits.append)

    assert waits == [31]
    assert len(data) == 1


def test_fetch_politely_waits_as_told_by_a_rate_limit_answer_and_asks_again():
    waits = []
    get = get_answering_in_turn([TOO_MANY, FakeResponse(200, ONE_HOUR)])

    data = fetch_politely(31, get, URL, "DE-LU", DAY_START, DAY_END, sleep=waits.append)

    assert waits == [31, 17.0]
    assert len(data) == 1


def test_fetch_politely_does_not_ask_again_after_another_http_error():
    waits = []
    get = get_answering_in_turn([FakeResponse(500, {"detail": "Server error"}),
                                 FakeResponse(200, ONE_HOUR)])

    with pytest.raises(EnergyChartsError, match="500"):
        fetch_politely(31, get, URL, "DE-LU", DAY_START, DAY_END, sleep=waits.append)

    assert waits == [31]
