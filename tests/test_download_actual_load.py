"""Tests for the actual load download. They use a fake client, a temporary folder and no network."""

import pandas as pd
from entsoe.exceptions import NoMatchingDataError

from epf.config import Zone
from epf.data.download_actual_load import DATASET, fetch_actual_load
from epf.data.download_forecasts import download_datasets

MARKET_TZ = "Europe/Berlin"
DAY_START = pd.Timestamp("2025-01-15", tz=MARKET_TZ)
DAY_END = pd.Timestamp("2025-01-16", tz=MARKET_TZ)


class FakeClient:
    """Stands in for EntsoePandasClient.

    Like the real client it answers in local time, includes the end timestamp
    and raises NoMatchingDataError when nothing is left.
    """

    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls = []

    def query_load(self, country_code: str, start: pd.Timestamp,
                   end: pd.Timestamp) -> pd.DataFrame:
        self.calls.append((country_code, start, end))
        answer = self.frame.truncate(before=start, after=end)
        if len(answer) == 0:
            raise NoMatchingDataError
        return answer


def hourly_load(first: str, last: str) -> pd.DataFrame:
    """One load value per hour from first to last, both included, in market time."""
    index = pd.date_range(first, last, freq="h", tz=MARKET_TZ)
    return pd.DataFrame({"Actual Load": 1000.0}, index=index)


def test_fetch_actual_load_returns_utc_values_without_the_end_timestamp():
    client = FakeClient(hourly_load("2025-01-15", "2025-01-16"))

    data = fetch_actual_load(client, "FR", DAY_START, DAY_END)

    assert list(data.columns) == ["Actual Load"]
    assert str(data.index.tz) == "UTC"
    assert len(data) == 24
    assert data.index[0] == pd.Timestamp("2025-01-14 23:00", tz="UTC")
    assert data.index[-1] == pd.Timestamp("2025-01-15 22:00", tz="UTC")
    assert client.calls == [("FR", DAY_START, DAY_END)]


def test_fetch_actual_load_returns_an_empty_frame_when_entsoe_has_no_data():
    client = FakeClient(hourly_load("2024-01-01", "2024-01-02"))

    data = fetch_actual_load(client, "FR", DAY_START, DAY_END)

    assert data.empty
    assert str(data.index.tz) == "UTC"


def test_actual_load_is_saved_as_its_own_dataset(tmp_path):
    client = FakeClient(hourly_load("2025-01-15", "2025-01-16"))

    summary = download_datasets(client, {DATASET: fetch_actual_load}, [Zone("FR", "FR", "core")],
                                [(2025, DAY_START, DAY_END)], tmp_path)

    assert (tmp_path / "actual_load" / "FR_2025.parquet").exists()
    assert summary["dataset"].tolist() == ["actual_load"]
    assert summary["column"].tolist() == ["Actual Load"]
    assert summary["missing_hours"].tolist() == [0]
