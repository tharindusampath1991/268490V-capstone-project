"""Load the project configuration from config/config.yaml."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"
GROUP_ORDER = ("core", "extra")


@dataclass(frozen=True)
class Zone:
    """One bidding zone entry from the config file."""

    key: str
    holiday_country: str
    group: str
    energy_charts: str | None = None
    weather_point: dict | None = None
    holiday_categories: Sequence[str] = ("public",)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Read the YAML config file.

    Input: path to a YAML file. The default is config/config.yaml in the repo.
    Output: the file content as a dictionary.
    """
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def ordered_zones(config: dict) -> list[Zone]:
    """Return the zones from the config, core zones first.

    Input: the dictionary returned by load_config.
    Output: one Zone per config entry. Core zones come before extra zones.
        Within each group the order of the config file is kept.
    Raises ValueError when a zone has a group other than core or extra.
    """
    zones = [Zone(**entry) for entry in config["zones"]]
    for zone in zones:
        if zone.group not in GROUP_ORDER:
            raise ValueError(
                f"Zone {zone.key} has unknown group '{zone.group}'. Use one of {GROUP_ORDER}."
            )
    return sorted(zones, key=lambda zone: GROUP_ORDER.index(zone.group))
