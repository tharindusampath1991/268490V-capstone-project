"""The results table: the relative MAE of every model per zone, as Markdown.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.evaluation.tables --experiment H --split validation

The command reads backtest_{group}.csv under paths.results, the rows that the
backtest command has saved, and prints one table per zone group that has zones
in the config, the core zones first. A table has one row per model and one
column per zone, in the order of the config, then the mean over those zones.
Every number is a relative MAE: the MAE of the model divided by the MAE of
the seasonal naive forecast on the same days. Lower is better. The models
are sorted by their mean, the lowest first.

A model can have more than one run of the same experiment, split and zone,
because a run adds rows. The newest row by run_started_utc is used then, and
a line under the table names the models for which that happened.

A model without a row for a zone has an empty cell there. Its mean is left
empty too, and is not computed over fewer zones, because a mean over other
zones cannot be compared with the mean of the other models. Such a model
stands below the models with a mean. A row whose stored relative_mae is
empty prints like a missing row: an empty cell and an empty mean.

The command writes no file.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from epf.config import GROUP_ORDER, REPO_ROOT, load_config, ordered_zones
from epf.data.splits import TEST, VALIDATION
from epf.evaluation import results
from epf.evaluation.backtest import EXPERIMENTS, KEYS

MODEL = "Model"
MEAN = "Mean"
NUMBER_FORMAT = "{:.4f}"


def newest_rows(rows: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Keep the newest row of every model, experiment, split and zone.

    Input: results rows with the columns run_started_utc, model, experiment,
        split and zone. run_started_utc is text such as 2026-11-24T14:52:26Z
        in UTC, so its order as text is its order in time.
    Output: the rows without the older ones, then the sorted names of the
        models that had an older row left out. Of two rows with the same
        start time the later one of the file is kept.
    """
    left_out = sorted(set(rows.loc[rows.duplicated(KEYS, keep="last"), "model"]))
    in_time_order = rows.sort_values("run_started_utc", kind="stable")
    return in_time_order.drop_duplicates(KEYS, keep="last"), left_out


def relative_mae_table(rows: pd.DataFrame, zone_keys: list[str]) -> pd.DataFrame:
    """Set the relative MAE of every model beside each other, one column per zone.

    Input: results rows of one experiment and split with at most one row per
        model and zone, and the zone keys in the order of the columns.
    Output: a frame with the columns Model, one per zone key and Mean, one
        row per model. A zone without a row is empty, and so is the mean of
        that model. The rows are sorted by the mean, the lowest first, then
        the models without a mean. Equal means are sorted by the model name.
    """
    table = rows.pivot(index="model", columns="zone", values="relative_mae")
    table = table.reindex(columns=zone_keys)
    table[MEAN] = table.mean(axis=1, skipna=False)
    table = table.rename_axis(index=MODEL, columns=None).reset_index()
    return table.sort_values([MEAN, MODEL], na_position="last", ignore_index=True)


def to_markdown(table: pd.DataFrame) -> str:
    """Write a frame as a Markdown table.

    Input: a frame. A number is written with four decimals and an empty
        number as an empty cell.
    Output: the header line, the rule line and one line per row.
    """
    def cell(value: object) -> str:
        if isinstance(value, float):
            return "" if pd.isna(value) else NUMBER_FORMAT.format(value)
        return str(value)

    header = "| " + " | ".join(str(name) for name in table.columns) + " |"
    rule = "|" + "---|" * len(table.columns)
    body = ["| " + " | ".join(cell(value) for value in row) + " |"
            for row in table.itertuples(index=False)]
    return "\n".join([header, rule, *body])


def selected_rows(path: Path, experiment: str, split: str, zone_keys: list[str]) -> pd.DataFrame:
    """Read a results file and keep the rows of one experiment, one split and some zones.

    Input: the file, an experiment name, a split name and the zone keys to keep.
    Output: the matching rows in the order of the file.
    Raises FileNotFoundError when the file does not exist and ValueError when
        no row matches.
    """
    if not path.exists():
        raise FileNotFoundError(f"The results file {path} does not exist.")
    rows = results.read_rows(path)
    keep = ((rows["experiment"] == experiment) & (rows["split"] == split)
            & rows["zone"].isin(zone_keys))
    if not keep.any():
        raise ValueError(f"{path} has no row for experiment {experiment} and the {split} days "
                         f"of the zones {zone_keys}.")
    return rows[keep]


def group_text(config: dict, group: str, zone_keys: list[str], experiment: str,
               split: str) -> str:
    """Return the heading, the table and the line about left-out runs of one zone group.

    Input: the config, the group name, its zone keys in the order of the
        config, an experiment name and a split name.
    Output: the text to print. The last line is there only when a model had
        more than one run.
    """
    path = results.results_path(REPO_ROOT / config["paths"]["results"], "backtest", group)
    rows, left_out = newest_rows(selected_rows(path, experiment, split, zone_keys))
    parts = [f"Relative MAE, experiment {experiment}, {split} days, {group} zones",
             to_markdown(relative_mae_table(rows, zone_keys))]
    if left_out:
        parts.append(f"More than one run, newest row used: {', '.join(left_out)}.")
    return "\n\n".join(parts)


def run(config: dict, experiment: str, split: str) -> None:
    """Print the table of one experiment and split for every zone group, core zones first.

    Input: the config dictionary, an experiment name (a key of EXPERIMENTS)
        and a split name, VALIDATION or TEST.
    Output: nothing. Prints one table per group that has zones in the config.
        Ends with an error when the results file of a group does not exist
        or holds no row for the experiment and the split.
    """
    zones = ordered_zones(config)
    for group in GROUP_ORDER:
        zone_keys = [zone.key for zone in zones if zone.group == group]
        if not zone_keys:
            continue
        try:
            text = group_text(config, group, zone_keys, experiment, split)
        except (FileNotFoundError, ValueError) as error:
            sys.exit(str(error))
        print(f"\n{text}")


def main() -> None:
    """Read the experiment and the split from the command line and print the tables."""
    parser = argparse.ArgumentParser(
        description="Print the relative MAE per model and zone as a Markdown table.")
    parser.add_argument("--experiment", required=True, choices=list(EXPERIMENTS))
    parser.add_argument("--split", required=True, choices=[VALIDATION, TEST])
    arguments = parser.parse_args()
    run(load_config(), arguments.experiment, arguments.split)


if __name__ == "__main__":
    main()
