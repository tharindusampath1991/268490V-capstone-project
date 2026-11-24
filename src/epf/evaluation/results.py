"""Results files of the backtest, and the readings of memory and hardware.

Files under paths.results are committed. The name ends with the zone group
of the config, so core zones and extra zones never share a file:
    backtest_{group}.csv   one row per run, zone and experiment. Rows are
                           only ever added.
    daily_{group}.csv      the losses per delivery day. A new run replaces
                           the rows of the same model, experiment, split
                           and zone.
Forecasts per market time unit go to paths.forecasts as Parquet files with a
UTC index. That folder is not committed.
"""

import platform
from pathlib import Path

import pandas as pd
import psutil

BYTES_PER_MB = 2**20
BYTES_PER_GB = 2**30


def results_path(folder: Path, kind: str, group: str) -> Path:
    """Return the results file of one kind (backtest or daily) and zone group."""
    return folder / f"{kind}_{group}.csv"


def append_rows(path: Path, rows: pd.DataFrame) -> None:
    """Add rows to the end of a CSV file. The file is created when it does not exist."""
    if path.exists():
        rows = pd.concat([pd.read_csv(path), rows], ignore_index=True)
    _write(path, rows)


def replace_rows(path: Path, rows: pd.DataFrame, keys: list[str]) -> None:
    """Write rows to a CSV file in place of the saved rows with the same key values.

    Input: the file, the new rows and the key columns. A saved row is
        removed when its key values occur in the new rows. Other saved rows stay.
    """
    if path.exists():
        saved = pd.read_csv(path)
        new_keys = set(rows[keys].itertuples(index=False, name=None))
        keep = [key not in new_keys for key in saved[keys].itertuples(index=False, name=None)]
        rows = pd.concat([saved[keep], rows], ignore_index=True)
    _write(path, rows)


def write_forecasts(folder: Path, model: str, experiment: str, split: str, zone_key: str,
                    scored: pd.DataFrame) -> Path:
    """Save the forecasts and actual prices of one zone and return the file path.

    Input: the forecasts folder, the names that make the path, and a frame
        with a UTC index, one row per market time unit.
    """
    path = folder / model / experiment / split / f"{zone_key}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(path)
    return path


def read_forecasts(path: Path) -> pd.DataFrame:
    """Read a file written by write_forecasts."""
    return pd.read_parquet(path)


def peak_memory_mb() -> float | None:
    """Return the highest memory use of this process so far, in megabytes.

    Output: the peak working set, which also counts memory used by native
        code. It never falls while the process runs. None on a system
        without this reading.
    """
    return peak_of(psutil.Process().memory_info())


def peak_of(memory_info: tuple) -> float | None:
    """Return the peak working set of a psutil memory reading in megabytes, or None."""
    peak = getattr(memory_info, "peak_wset", None)   # the field exists on Windows only
    return None if peak is None else peak / BYTES_PER_MB


def hardware() -> str:
    """Return one line that names the processor, its cores, the memory and the system."""
    memory_gb = psutil.virtual_memory().total / BYTES_PER_GB
    return (f"{platform.processor()} | {psutil.cpu_count(logical=False)} cores, "
            f"{psutil.cpu_count()} threads | {memory_gb:.1f} GB RAM | "
            f"{platform.system()} {platform.release()}")


def _write(path: Path, rows: pd.DataFrame) -> None:
    """Write rows to a CSV file without the row numbers, creating the folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(path, index=False)
