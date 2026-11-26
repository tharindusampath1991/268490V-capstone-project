"""Build the LightGBM features of every zone and experiment, print their counts and save a copy.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.features.build

For experiment H (hourly table) and experiment Q (15-minute table) and every
zone of the config, the command builds the features of every delivery day of
the processed table with epf.features.builder. Each day is built from inputs
cut to that day, as in the backtest. It prints the rows and the empty cells
per feature and zone, and saves one frame per zone and experiment under
paths.features:
    {experiment}/{ZONE}.parquet

The saved frames are for inspection. The backtest never reads them: a model
builds its features from the inputs the backtest hands it. The frames cover
the validation and the test days too, so they are not train data as a whole.

The command ends with an error and saves nothing when a table is missing,
when a table column stands under no cut, or when a check fails.

The index is in UTC. Delivery days are defined in market time.
"""

import sys
import time
from pathlib import Path

import pandas as pd

from epf.config import REPO_ROOT, Zone, load_config, ordered_zones
from epf.data.market_time import delivery_days
from epf.data.splits import TEST, split_range
from epf.evaluation.backtest import EXPERIMENTS, read_table, read_weather
from epf.evaluation.cutoff import cut_columns, weather_rule
from epf.features.builder import build_features, feature_settings
from epf.features.holiday_calendar import holiday_dates


def features_path(folder: Path, experiment: str, zone_key: str) -> Path:
    """Return the file of the saved features of one zone and experiment."""
    return folder / experiment / f"{zone_key}.parquet"


def zone_features(config: dict, zone: Zone, experiment: str) -> pd.DataFrame:
    """Return the features of every delivery day of one zone and experiment.

    Input: the config, the zone and the experiment name (a key of EXPERIMENTS).
    Output: one row per market time unit of the processed table, in UTC. The
        holidays are those of the country of the zone. The weather table is
        read for a zone with a weather point.
    Raises FileNotFoundError when a table is missing, and ValueError when a
        table is refused or the features do not stand on its time steps.
    """
    table_name, make_index = EXPERIMENTS[experiment]
    _, end = split_range(config, TEST)
    table = read_table(config, table_name, zone.key, end)
    weather = read_weather(config, zone, end)
    rule = None if weather is None else weather_rule(config)
    start = table.index[0].tz_convert(config["market"]["timezone"])
    holidays = holiday_dates(zone.holiday_country, zone.holiday_categories,
                             range(start.year, end.year + 1))
    features = build_features(table, delivery_days(start, end), make_index, cut_columns(config),
                              feature_settings(config), holidays, weather, rule)
    if not features.index.equals(table.index):
        raise ValueError("The features do not stand on the time steps of the table.")
    return features


def empty_counts(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return the number of empty cells per feature (rows) and zone (columns)."""
    return pd.DataFrame({zone_key: features.isna().sum() for zone_key, features in frames.items()})


def report(experiment: str, frames: dict[str, pd.DataFrame], seconds: dict[str, float],
           market_tz: str) -> None:
    """Print the size of the frames of one experiment, then the empty cells per feature."""
    print(f"\n===== experiment {experiment}: features per zone =====")
    print(f"{'zone':6s} {'rows':>7s} {'days':>6s} {'features':>9s} {'empty cells':>12s} "
          f"{'seconds':>8s}")
    for zone_key, features in frames.items():
        days = len(set(features.index.tz_convert(market_tz).date))
        print(f"{zone_key:6s} {len(features):7d} {days:6d} {features.shape[1]:9d} "
              f"{int(features.isna().sum().sum()):12d} {seconds[zone_key]:8.1f}")
    print(f"\nexperiment {experiment}: empty cells per feature and zone")
    print(empty_counts(frames).to_string())


def same_columns(frames: dict[str, pd.DataFrame]) -> bool:
    """Return True when every frame has the same columns in the same order."""
    columns = [list(features.columns) for features in frames.values()]
    return all(names == columns[0] for names in columns)


def run(config: dict) -> None:
    """Build, report and save the features of every zone and experiment.

    Input: the config dictionary.
    Output: nothing. Prints the counts and writes the frames after all of
        them are built. Ends with an error and writes nothing when a table
        is missing or refused, or when the zones do not get the same columns.
    """
    market_tz = config["market"]["timezone"]
    built: dict[str, dict[str, pd.DataFrame]] = {}
    for experiment in EXPERIMENTS:
        frames, seconds = {}, {}
        for zone in ordered_zones(config):
            started = time.perf_counter()
            try:
                frames[zone.key] = zone_features(config, zone, experiment)
            except (FileNotFoundError, ValueError) as error:
                sys.exit(f"{zone.key} {experiment}: {error}")
            seconds[zone.key] = time.perf_counter() - started
        report(experiment, frames, seconds, market_tz)
        if not same_columns(frames):
            sys.exit(f"Experiment {experiment}: the zones do not have the same features. "
                     "Nothing was written.")
        built[experiment] = frames

    folder = REPO_ROOT / config["paths"]["features"]
    for experiment, frames in built.items():
        for zone_key, features in frames.items():
            path = features_path(folder, experiment, zone_key)
            path.parent.mkdir(parents=True, exist_ok=True)
            features.to_parquet(path)
    print(f"\nWrote {sum(len(frames) for frames in built.values())} files under {folder}")


def main() -> None:
    """Build the features of the project config."""
    run(load_config())


if __name__ == "__main__":
    main()
