"""Tests for the results table command.

They use small synthetic results files in a temporary folder, no network and
no data files. One test reads the zones of the project config.
"""

from pathlib import Path

import pandas as pd
import pytest

from epf.config import load_config, ordered_zones
from epf.evaluation import tables
from epf.evaluation.results import append_rows, results_path
from epf.evaluation.tables import newest_rows, relative_mae_table, run, to_markdown

FIRST_RUN = "2026-11-24T10:00:00Z"
SECOND_RUN = "2026-11-25T09:30:00Z"


def result_rows(model: str, values: dict[str, float], started: str = FIRST_RUN,
                experiment: str = "H", split: str = "validation") -> pd.DataFrame:
    """Results rows of one run of a model: zone key to relative MAE."""
    return pd.DataFrame({"run_started_utc": started, "model": model, "experiment": experiment,
                         "split": split, "zone": list(values),
                         "relative_mae": list(values.values())})


def project_config(tmp_path) -> dict:
    """A config with the core zones A and C and the extra zone B, B first in the file."""
    return {
        "paths": {"results": str(tmp_path / "results")},
        "zones": [{"key": "B", "holiday_country": "PL", "group": "extra"},
                  {"key": "A", "holiday_country": "DE", "group": "core"},
                  {"key": "C", "holiday_country": "FR", "group": "core"}],
    }


def save_rows(config: dict, group: str, *runs: pd.DataFrame) -> None:
    """Add the rows of some runs to the results file of a zone group."""
    path = results_path(Path(config["paths"]["results"]), "backtest", group)
    append_rows(path, pd.concat(runs, ignore_index=True))


def files_under(folder: Path) -> dict[Path, bytes]:
    """Every file under a folder with its content."""
    return {path: path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def table_lines(text: str) -> list[list[str]]:
    """The cells of every table line of a printed text, without the rule line."""
    lines = [line for line in text.splitlines() if line.startswith("| ")]
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]


# The newest row of a model, experiment, split and zone.

def test_newest_rows_keeps_the_row_of_the_latest_run_and_names_the_model():
    rows = pd.concat([result_rows("lgbm", {"A": 0.5, "C": 0.6}, SECOND_RUN),
                      result_rows("lgbm", {"A": 0.9}, FIRST_RUN),
                      result_rows("naive", {"A": 1.0, "C": 1.0}, FIRST_RUN)], ignore_index=True)

    newest, repeated = newest_rows(rows)

    cells = newest.set_index(["model", "zone"])["relative_mae"].to_dict()
    assert cells == {("lgbm", "A"): 0.5, ("lgbm", "C"): 0.6,
                     ("naive", "A"): 1.0, ("naive", "C"): 1.0}
    assert repeated == ["lgbm"]


def test_newest_rows_takes_the_later_row_of_the_file_when_two_runs_started_together():
    rows = pd.concat([result_rows("lgbm", {"A": 0.9}), result_rows("lgbm", {"A": 0.5})],
                     ignore_index=True)

    newest, repeated = newest_rows(rows)

    assert newest["relative_mae"].tolist() == [0.5]
    assert repeated == ["lgbm"]


def test_newest_rows_keeps_runs_of_another_experiment_or_split_apart():
    rows = pd.concat([result_rows("naive", {"A": 1.0}, FIRST_RUN, experiment="H"),
                      result_rows("naive", {"A": 1.1}, SECOND_RUN, experiment="Q"),
                      result_rows("naive", {"A": 1.2}, SECOND_RUN, split="test")],
                     ignore_index=True)

    newest, repeated = newest_rows(rows)

    assert sorted(newest["relative_mae"]) == [1.0, 1.1, 1.2]
    assert repeated == []


# The table of one experiment and split.

def test_the_table_has_one_row_per_model_and_one_column_per_zone_in_the_given_order():
    rows = pd.concat([result_rows("naive", {"A": 1.0, "B": 1.0, "C": 1.0}),
                      result_rows("lgbm", {"C": 0.6, "A": 0.4, "B": 0.5})], ignore_index=True)

    table = relative_mae_table(rows, ["C", "A", "B"])

    assert list(table.columns) == ["Model", "C", "A", "B", "Mean"]
    assert table.to_dict("records") == [
        {"Model": "lgbm", "C": 0.6, "A": 0.4, "B": 0.5, "Mean": 0.5},
        {"Model": "naive", "C": 1.0, "A": 1.0, "B": 1.0, "Mean": 1.0},
    ]


def test_the_mean_is_the_mean_over_the_zones():
    rows = result_rows("lgbm", {"A": 0.25, "B": 0.5, "C": 1.0})

    table = relative_mae_table(rows, ["A", "B", "C"])

    assert table["Mean"].tolist() == [(0.25 + 0.5 + 1.0) / 3]


def test_a_model_without_a_row_for_a_zone_has_an_empty_cell_and_an_empty_mean():
    rows = pd.concat([result_rows("naive", {"A": 1.0, "B": 1.0}),
                      result_rows("lgbm", {"A": 0.4})], ignore_index=True)

    table = relative_mae_table(rows, ["A", "B"]).set_index("Model")

    assert table.loc["lgbm", "A"] == 0.4
    assert pd.isna(table.loc["lgbm", "B"])
    assert pd.isna(table.loc["lgbm", "Mean"])
    assert table.loc["naive", "Mean"] == 1.0


def test_models_are_sorted_by_their_mean_then_by_name_and_those_without_a_mean_come_last():
    rows = pd.concat([result_rows("naive", {"A": 1.0, "B": 1.0}),
                      result_rows("b_half", {"A": 0.9}),
                      result_rows("mstl", {"A": 0.6, "B": 0.8}),
                      result_rows("a_half", {"B": 0.1}),
                      result_rows("ets", {"A": 0.8, "B": 0.6}),
                      result_rows("lgbm", {"A": 0.5, "B": 0.5})], ignore_index=True)

    table = relative_mae_table(rows, ["A", "B"])

    assert table["Model"].tolist() == ["lgbm", "ets", "mstl", "naive", "a_half", "b_half"]


# The Markdown text.

def test_to_markdown_writes_four_decimals_and_leaves_an_empty_cell_empty():
    table = pd.DataFrame({"Model": ["lgbm", "naive"], "A": [0.41236, 1.0],
                          "B": [float("nan"), 1.0], "Mean": [float("nan"), 1.0]})

    assert to_markdown(table).splitlines() == [
        "| Model | A | B | Mean |",
        "|---|---|---|---|",
        "| lgbm | 0.4124 |  |  |",
        "| naive | 1.0000 | 1.0000 | 1.0000 |",
    ]


# The command, on a small project in a temporary folder.

def test_run_prints_the_table_of_one_experiment_and_split(tmp_path, capsys):
    config = project_config(tmp_path)
    save_rows(config, "core",
              result_rows("naive", {"A": 1.0, "C": 1.0}),
              result_rows("mstl", {"A": 0.7, "C": 0.65}),
              result_rows("mstl", {"A": 0.3, "C": 0.3}, experiment="Q"),
              result_rows("mstl", {"A": 0.2, "C": 0.2}, split="test"))
    save_rows(config, "extra", result_rows("naive", {"B": 1.0}))

    run(config, "H", "validation")

    printed = capsys.readouterr().out
    assert table_lines(printed)[:3] == [["Model", "A", "C", "Mean"],
                                        ["mstl", "0.7000", "0.6500", "0.6750"],
                                        ["naive", "1.0000", "1.0000", "1.0000"]]
    assert "0.3000" not in printed and "0.2000" not in printed


def test_run_prints_one_table_per_zone_group_core_first_under_a_line_that_names_the_group(
        tmp_path, capsys):
    config = project_config(tmp_path)
    save_rows(config, "core", result_rows("naive", {"A": 1.0, "C": 1.0}))
    save_rows(config, "extra", result_rows("naive", {"B": 1.0}))

    run(config, "H", "validation")

    lines = capsys.readouterr().out.splitlines()
    headings = [line for line in lines if line.startswith("Relative MAE")]
    assert headings == ["Relative MAE, experiment H, validation days, core zones",
                        "Relative MAE, experiment H, validation days, extra zones"]
    headers = [line for line in lines if line.startswith("| Model")]
    assert headers == ["| Model | A | C | Mean |", "| Model | B | Mean |"]
    assert lines.index(headings[0]) < lines.index(headers[0]) < lines.index(headings[1])


def test_run_prints_no_table_for_a_group_without_zones(tmp_path, capsys):
    config = project_config(tmp_path)
    config["zones"] = [zone for zone in config["zones"] if zone["group"] == "core"]
    save_rows(config, "core", result_rows("naive", {"A": 1.0, "C": 1.0}))

    run(config, "H", "validation")

    printed = capsys.readouterr().out
    assert printed.count("| Model") == 1
    assert "extra" not in printed


def test_run_uses_the_newest_row_and_says_for_which_models(tmp_path, capsys):
    config = project_config(tmp_path)
    save_rows(config, "core",
              result_rows("naive", {"A": 1.0, "C": 1.0}),
              result_rows("lgbm", {"A": 0.9, "C": 0.9}, FIRST_RUN),
              result_rows("mstl", {"A": 0.8, "C": 0.8}, FIRST_RUN),
              result_rows("lgbm", {"A": 0.4, "C": 0.5}, SECOND_RUN),
              result_rows("mstl", {"A": 0.7}, SECOND_RUN))
    save_rows(config, "extra", result_rows("naive", {"B": 1.0}))

    run(config, "H", "validation")

    printed = capsys.readouterr().out
    assert table_lines(printed)[1:4] == [["lgbm", "0.4000", "0.5000", "0.4500"],
                                         ["mstl", "0.7000", "0.8000", "0.7500"],
                                         ["naive", "1.0000", "1.0000", "1.0000"]]
    assert printed.count("More than one run, newest row used: lgbm, mstl.") == 1


def test_run_prints_no_line_about_runs_when_every_model_has_one_run(tmp_path, capsys):
    config = project_config(tmp_path)
    save_rows(config, "core", result_rows("naive", {"A": 1.0, "C": 1.0}))
    save_rows(config, "extra", result_rows("naive", {"B": 1.0}))

    run(config, "H", "validation")

    printed = capsys.readouterr().out
    assert printed.count("| naive | 1.0000 |") == 2
    assert "More than one run" not in printed


def test_an_older_run_of_another_split_is_not_reported_as_left_out(tmp_path, capsys):
    config = project_config(tmp_path)
    save_rows(config, "core",
              result_rows("naive", {"A": 1.0, "C": 1.0}, FIRST_RUN, split="test"),
              result_rows("naive", {"A": 1.0, "C": 1.0}, SECOND_RUN))
    save_rows(config, "extra", result_rows("naive", {"B": 1.0}))

    run(config, "H", "validation")

    printed = capsys.readouterr().out
    assert printed.count("| naive | 1.0000 |") == 2
    assert "More than one run" not in printed


def test_a_zone_of_the_file_that_the_config_does_not_hold_is_not_shown(tmp_path, capsys):
    config = project_config(tmp_path)
    save_rows(config, "core",
              result_rows("naive", {"A": 1.0, "C": 1.0, "OLD": 1.0}),
              result_rows("gone", {"OLD": 0.1234}),
              result_rows("naive", {"OLD": 1.0}, SECOND_RUN))
    save_rows(config, "extra", result_rows("naive", {"B": 1.0}))

    run(config, "H", "validation")

    printed = capsys.readouterr().out
    assert table_lines(printed)[:2] == [["Model", "A", "C", "Mean"],
                                        ["naive", "1.0000", "1.0000", "1.0000"]]
    assert "OLD" not in printed and "gone" not in printed
    assert "More than one run" not in printed


def test_a_model_without_a_row_for_a_zone_is_printed_with_an_empty_cell_and_no_mean(
        tmp_path, capsys):
    config = project_config(tmp_path)
    save_rows(config, "core",
              result_rows("naive", {"A": 1.0, "C": 1.0}),
              result_rows("lgbm", {"C": 0.4}))
    save_rows(config, "extra", result_rows("naive", {"B": 1.0}))

    run(config, "H", "validation")

    assert table_lines(capsys.readouterr().out)[1:3] == [["naive", "1.0000", "1.0000", "1.0000"],
                                                         ["lgbm", "", "0.4000", ""]]


def test_run_ends_with_an_error_that_names_a_missing_results_file(tmp_path):
    config = project_config(tmp_path)
    save_rows(config, "core", result_rows("naive", {"A": 1.0, "C": 1.0}))

    with pytest.raises(SystemExit, match="backtest_extra.csv"):
        run(config, "H", "validation")


def test_run_ends_with_an_error_when_no_row_has_the_experiment_and_the_split(tmp_path):
    config = project_config(tmp_path)
    save_rows(config, "core", result_rows("naive", {"A": 1.0, "C": 1.0}))
    save_rows(config, "extra", result_rows("naive", {"B": 1.0}))

    with pytest.raises(SystemExit, match="backtest_core.csv.*experiment Q.*test days"):
        run(config, "Q", "test")


def test_run_writes_and_changes_no_file(tmp_path, capsys):
    config = project_config(tmp_path)
    save_rows(config, "core",
              result_rows("naive", {"A": 1.0, "C": 1.0}, FIRST_RUN),
              result_rows("naive", {"A": 1.0, "C": 1.0}, SECOND_RUN))
    save_rows(config, "extra", result_rows("naive", {"B": 1.0}))
    before = files_under(tmp_path)

    run(config, "H", "validation")

    assert capsys.readouterr().out.count("| naive | 1.0000 |") == 2
    assert files_under(tmp_path) == before
    assert len(before) == 2


def test_every_zone_of_the_project_config_is_a_column_of_the_table(tmp_path, capsys):
    config = load_config()
    zones = ordered_zones(config)
    config["paths"] = {"results": str(tmp_path / "results")}
    for group in {zone.group for zone in zones}:
        values = {zone.key: 1.0 for zone in zones if zone.group == group}
        save_rows(config, group, result_rows("naive", values))

    run(config, "H", "validation")

    headers = [cells for cells in table_lines(capsys.readouterr().out) if cells[0] == "Model"]
    shown = [cell for cells in headers for cell in cells if cell not in ("Model", "Mean")]
    assert shown == [zone.key for zone in zones]
    assert len(shown) == len(config["zones"])


# The command line.

def test_the_command_reads_the_experiment_and_the_split_from_the_command_line(
        tmp_path, capsys, monkeypatch):
    config = project_config(tmp_path)
    save_rows(config, "core",
              result_rows("naive", {"A": 1.0, "C": 1.0}),
              result_rows("naive", {"A": 0.5, "C": 0.5}, experiment="Q", split="test"))
    save_rows(config, "extra",
              result_rows("naive", {"B": 0.25}, experiment="Q", split="test"))
    monkeypatch.setattr(tables, "load_config", lambda: config)
    monkeypatch.setattr("sys.argv", ["tables", "--experiment", "Q", "--split", "test"])

    tables.main()

    assert table_lines(capsys.readouterr().out) == [["Model", "A", "C", "Mean"],
                                                    ["naive", "0.5000", "0.5000", "0.5000"],
                                                    ["Model", "B", "Mean"],
                                                    ["naive", "0.2500", "0.2500"]]


@pytest.mark.parametrize("arguments", [
    ["--experiment", "H"],
    ["--split", "validation"],
    ["--experiment", "D", "--split", "validation"],
    ["--experiment", "H", "--split", "train"],
])
def test_the_command_refuses_a_missing_or_unknown_experiment_or_split(
        arguments, tmp_path, monkeypatch):
    monkeypatch.setattr(tables, "load_config", lambda: project_config(tmp_path))
    monkeypatch.setattr("sys.argv", ["tables", *arguments])

    with pytest.raises(SystemExit) as error:
        tables.main()

    assert error.value.code == 2
