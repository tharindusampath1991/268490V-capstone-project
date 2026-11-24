"""The time-based split: read a processed table and keep the train delivery days.

The train set is every delivery day before splits.validation_start
(PROJECT_CONTEXT section 4). Tables have a UTC index. The cut is defined in
market time.
"""

import pandas as pd

from epf.config import REPO_ROOT
from epf.data.resolution import check_utc_index
from epf.data.validate import table_path


def train_cut(config: dict) -> pd.Timestamp:
    """Return the first moment that is not in the train set.

    Input: the config dictionary.
    Output: 00:00 in market time on splits.validation_start.
    """
    return pd.Timestamp(config["splits"]["validation_start"], tz=config["market"]["timezone"])


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
