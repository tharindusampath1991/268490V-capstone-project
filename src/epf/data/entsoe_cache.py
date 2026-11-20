"""Cache for raw ENTSO-E downloads: one Parquet file per dataset, zone and year.

A manifest file records which query produced each saved file. A saved file is
reused only for the same query start and end. A partial year is therefore
downloaded again when the requested end moves. An empty answer is never saved.
Manifest times are in UTC.
"""

import json
from collections.abc import Callable
from pathlib import Path

import entsoe
import pandas as pd

MANIFEST_NAME = "manifest.json"

Fetch = Callable[[pd.Timestamp, pd.Timestamp], pd.DataFrame]


def cached_fetch(fetch: Fetch, cache_dir: Path, dataset: str, zone: str, year: int,
                 start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Return one dataset for one zone and year, from disk when the same query was saved.

    Input: fetch downloads the data for [start, end) and returns a frame with
        a UTC index. cache_dir is the folder of the ENTSO-E cache. start and
        end are time zone aware.
    Output: the frame returned by fetch, or the saved copy of it. An empty
        answer is returned but never saved, so it is asked again next time.
    """
    path, key = _locate(cache_dir, dataset, zone, year)
    manifest = read_manifest(cache_dir)
    if path.exists() and _is_same_query(manifest.get(key), start, end):
        return pd.read_parquet(path)

    data = fetch(start, end)
    if not data.empty:
        path.parent.mkdir(parents=True, exist_ok=True)
        data.to_parquet(path)
        manifest[key] = _manifest_entry(data, start, end)
        _write_manifest(cache_dir, manifest)
    return data


def read_saved(cache_dir: Path, dataset: str, zone: str,
               year: int) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """Return a saved download and the start and end of the query that produced it.

    Input: the folder of the cache, and the dataset, zone and year of the file.
    Output: the saved frame, then the query start and query end in UTC.
    Raises FileNotFoundError when the download is not in the cache.
    """
    path, key = _locate(cache_dir, dataset, zone, year)
    entry = read_manifest(cache_dir).get(key)
    if entry is None or not path.exists():
        raise FileNotFoundError(f"No saved download for {dataset} {zone} {year} in {cache_dir}.")
    return pd.read_parquet(path), pd.Timestamp(entry["query_start"]), pd.Timestamp(entry["query_end"])


def _locate(cache_dir: Path, dataset: str, zone: str, year: int) -> tuple[Path, str]:
    """Return the Parquet file of one download and its key in the manifest."""
    path = cache_dir / dataset / f"{zone}_{year}.parquet"
    return path, f"{dataset}/{path.name}"


def read_manifest(cache_dir: Path) -> dict:
    """Return the manifest of a cache folder.

    Input: the folder of the ENTSO-E cache.
    Output: one entry per saved file, keyed by "{dataset}/{ZONE}_{YEAR}.parquet".
        An empty dictionary when no manifest exists yet.
    """
    path = cache_dir / MANIFEST_NAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(cache_dir: Path, manifest: dict) -> None:
    """Write the manifest of a cache folder as JSON."""
    path = cache_dir / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _manifest_entry(data: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Describe one download: query start and end, download time, rows, client version."""
    return {
        "query_start": start.tz_convert("UTC").isoformat(),
        "query_end": end.tz_convert("UTC").isoformat(),
        "downloaded_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "rows": len(data),
        "entsoe_py_version": entsoe.__version__,
    }


def _is_same_query(entry: dict | None, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    """True when a manifest entry was written for exactly this query start and end."""
    if entry is None:
        return False
    return pd.Timestamp(entry["query_start"]) == start and pd.Timestamp(entry["query_end"]) == end
