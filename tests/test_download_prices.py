"""Tests for the price downloader. They use a fake client, a temporary folder and no network."""

import pandas as pd
from entsoe.exceptions import NoMatchingDataError

from epf.config import Zone
from epf.data.download_prices import check_prices, download_prices, fetch_prices

MARKET_TZ = "Europe/Berlin"
SWITCH = pd.Timestamp("2025-10-01", tz=MARKET_TZ)
DAY_START = pd.Timestamp("2025-01-15", tz=MARKET_TZ)
DAY_END = pd.Timestamp("2025-01-16", tz=MARKET_TZ)
# The 24 hours of delivery day 15 Jan 2025 in market time (UTC+1 in winter).
FULL_DAY = pd.date_range("2025-01-14 23:00", periods=24, freq="h", tz="UTC")


class FakeClient:
    """Stands in for EntsoePandasClient.

    Like the real client it answers in local time, includes the end timestamp
    and raises NoMatchingDataError when nothing is left.
    """

    def __init__(self, prices: pd.Series) -> None:
        self.prices = prices
        self.calls = []

    def query_day_ahead_prices(self, country_code: str, start: pd.Timestamp,
                               end: pd.Timestamp) -> pd.Series:
        self.calls.append((country_code, start, end))
        answer = self.prices.truncate(before=start, after=end)
        if len(answer) == 0:
            raise NoMatchingDataError
        return answer


def hourly_prices(first: str, last: str) -> pd.Series:
    """One price per hour from first to last, both included, in market time."""
    index = pd.date_range(first, last, freq="h", tz=MARKET_TZ)
    return pd.Series(50.0, index=index)


def price_frame(index: pd.DatetimeIndex) -> pd.DataFrame:
    """A raw price frame with the same price at every timestamp of the index."""
    return pd.DataFrame({"price": 50.0}, index=index)


def test_fetch_prices_returns_utc_prices_without_the_end_timestamp():
    client = FakeClient(hourly_prices("2025-01-15", "2025-01-16"))

    data = fetch_prices(client, "DE_LU", DAY_START, DAY_END)

    assert list(data.columns) == ["price"]
    assert str(data.index.tz) == "UTC"
    assert len(data) == 24
    assert data.index[0] == pd.Timestamp("2025-01-14 23:00", tz="UTC")
    assert data.index[-1] == pd.Timestamp("2025-01-15 22:00", tz="UTC")
    assert client.calls == [("DE_LU", DAY_START, DAY_END)]


def test_fetch_prices_returns_an_empty_frame_when_entsoe_has_no_data():
    client = FakeClient(hourly_prices("2024-01-01", "2024-01-02"))

    data = fetch_prices(client, "DE_LU", DAY_START, DAY_END)

    assert data.empty
    assert list(data.columns) == ["price"]


def test_check_prices_finds_nothing_wrong_in_a_complete_day():
    counts = check_prices(price_frame(FULL_DAY), DAY_START, DAY_END, SWITCH)

    assert counts == {"expected": 24, "missing": 0, "days_with_gaps": 0,
                      "unexpected": 0, "duplicates": 0}


def test_check_prices_counts_gap_days_by_delivery_day_in_market_time():
    two_days = pd.date_range("2025-01-14 23:00", periods=48, freq="h", tz="UTC")
    # Both dropped hours belong to delivery day 15 Jan in market time, but to two UTC dates.
    kept = two_days.drop([pd.Timestamp("2025-01-14 23:00", tz="UTC"),
                          pd.Timestamp("2025-01-15 10:00", tz="UTC")])

    counts = check_prices(price_frame(kept), DAY_START, pd.Timestamp("2025-01-17", tz=MARKET_TZ),
                          SWITCH)

    assert counts["missing"] == 2
    assert counts["days_with_gaps"] == 1


def test_check_prices_counts_an_empty_price_as_missing():
    data = price_frame(FULL_DAY)
    data.iloc[3, 0] = float("nan")

    counts = check_prices(data, DAY_START, DAY_END, SWITCH)

    assert counts["missing"] == 1


def test_check_prices_counts_every_unit_as_missing_when_there_is_no_data():
    client = FakeClient(hourly_prices("2024-01-01", "2024-01-02"))
    no_data = fetch_prices(client, "DE_LU", DAY_START, DAY_END)

    counts = check_prices(no_data, DAY_START, DAY_END, SWITCH)

    assert counts["missing"] == 24
    assert counts["days_with_gaps"] == 1


def test_check_prices_counts_values_between_market_time_units_as_unexpected():
    half_past = pd.DatetimeIndex([pd.Timestamp("2025-01-15 10:30", tz="UTC")])

    counts = check_prices(price_frame(FULL_DAY.append(half_past)), DAY_START, DAY_END, SWITCH)

    assert counts["unexpected"] == 1
    assert counts["missing"] == 0


def test_check_prices_counts_repeated_timestamps():
    counts = check_prices(price_frame(FULL_DAY.append(FULL_DAY[:1])), DAY_START, DAY_END, SWITCH)

    assert counts["duplicates"] == 1
    assert counts["missing"] == 0


def test_download_prices_reports_each_zone_and_year_in_the_given_order(tmp_path):
    client = FakeClient(hourly_prices("2025-01-15", "2025-01-16"))
    zones = [Zone("DE_LU", "DE", "core"), Zone("SE_1", "SE", "extra")]

    summary = download_prices(client, zones, [(2025, DAY_START, DAY_END)], tmp_path, SWITCH)

    assert summary["zone"].tolist() == ["DE_LU", "SE_1"]
    assert summary["year"].tolist() == [2025, 2025]
    assert summary["rows"].tolist() == [24, 24]
    assert summary["missing"].tolist() == [0, 0]


def test_download_prices_uses_the_saved_files_on_a_second_run(tmp_path):
    client = FakeClient(hourly_prices("2025-01-15", "2025-01-16"))
    zones = [Zone("DE_LU", "DE", "core")]
    download_prices(client, zones, [(2025, DAY_START, DAY_END)], tmp_path, SWITCH)

    summary = download_prices(client, zones, [(2025, DAY_START, DAY_END)], tmp_path, SWITCH)

    assert len(client.calls) == 1
    assert summary["rows"].tolist() == [24]
    assert summary["missing"].tolist() == [0]
