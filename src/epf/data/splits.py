"""The time-based split: the train loader and the range of the validation and test set.

The train set is every delivery day before splits.validation_start
(PROJECT_CONTEXT section 4). The validation set runs from there to
splits.test_start, and the test set from there to data.end. Tables have a UTC
index. Every cut is defined in market time.
"""

from datetime import date, timedelta

import pandas as pd

from epf.config import REPO_ROOT
from epf.data.resolution import check_utc_index
from epf.data.validate import table_path

VALIDATION = "validation"
TEST = "test"


def train_cut(config: dict) -> pd.Timestamp:
    """Return the first moment that is not in the train set.

    Input: the config dictionary.
    Output: 00:00 in market time on splits.validation_start.
    """
    return pd.Timestamp(config["splits"]["validation_start"], tz=config["market"]["timezone"])


def split_range(config: dict, split: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the validation or the test set as [start, end) in market time.

    Input: the config dictionary and the split name, VALIDATION or TEST.
    Output: start is 00:00 on the first delivery day of the split. end is
        00:00 on the day after its last delivery day. The validation set ends
        where the test set starts, and the test set ends with data.end.
    Raises ValueError for any other split name.
    """
    market_tz = config["market"]["timezone"]
    test_start = pd.Timestamp(config["splits"]["test_start"], tz=market_tz)
    if split == VALIDATION:
        return train_cut(config), test_start
    if split == TEST:
        day_after_end = date.fromisoformat(config["data"]["end"]) + timedelta(days=1)
        return test_start, pd.Timestamp(day_after_end, tz=market_tz)
    raise ValueError(f"Unknown split '{split}'. Use {VALIDATION} or {TEST}.")


def keep_train(table: pd.DataFrame, cut: pd.Timestamp) -> pd.DataFrame:
    """Return the rows of a table that lie before the cut.

    Input: a table with a UTC index, and the cut from train_cut.
    Output: the same columns, with every row at or after the cut removed.
    Raises ValueError when the index is not UTC, sorted and free of repeats.
    """
    check_utc_index(table)
    return table[table.index < cut]


def load_train(config: dict, table_name: str, zone_key: str) -> pd.DataFrame:
    """Read one processed table and keep its train delivery days.

    Input: the config dictionary, a table name (HOURLY, QUARTER_HOUR or
        WEATHER_TABLE of epf.data.validate) and a zone key.
    Output: the table with a UTC index, ending with the last time step
        before 00:00 market time on splits.validation_start.
    """
    path = table_path(REPO_ROOT / config["paths"]["processed"], table_name, zone_key)
    return keep_train(pd.read_parquet(path), train_cut(config))
