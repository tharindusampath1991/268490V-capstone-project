"""What the two zero-shot wrappers share: the context of a delivery day and the entry checks.

A zero-shot model is not fitted on the prices of the project. It reads the
last prices before the price cut, its context, and answers with a forecast.
The context length of a config entry is given in days and counted in market
time units: one day is 24 hourly or 96 quarter-hour steps, also across a
clock change. So one entry covers the same number of days on both tables.

The model ID, the revision and the fixed options of a model stand in the
config under foundation_models, one section per family.

Prices are in EUR/MWh with a UTC index.
"""

from datetime import timedelta

import numpy as np
import pandas as pd

from epf.evaluation.cutoff import DayInputs

SECTION = "foundation_models"
CONTEXT = "context_days"
ENTRY_KEYS = ("family", CONTEXT)


def units_per_day(target_index: pd.DatetimeIndex) -> int:
    """Return the market time units of a day without a clock change: 24 or 96.

    Input: the market time units of a delivery day in UTC. Their step gives the number.
    """
    step = target_index[1] - target_index[0]
    return round(timedelta(days=1).total_seconds() / step.total_seconds())


def context_steps(context_days: int, target_index: pd.DatetimeIndex) -> int:
    """Return a context length of some days in market time units.

    Input: the context length in days, and the market time units of a
        delivery day in UTC.
    """
    return context_days * units_per_day(target_index)


def price_context(inputs: DayInputs, context_days: int) -> np.ndarray:
    """Return the last prices before the price cut of a delivery day, oldest first.

    Input: the inputs of delivery day D and the context length in days.
    Output: the last context_days times 24 or 96 prices of the inputs, in
        EUR/MWh. The prices of the inputs end before 00:00 market time on D.
        A history that is shorter is handed over whole.
    Raises ValueError when the inputs hold no price, and when a price of the
        context is empty. TimesFM would fill it by linear interpolation
        without a word.
    """
    steps = context_steps(context_days, inputs.target_index)
    context = inputs.prices.to_numpy(dtype=float)[-steps:]
    if not len(context):
        raise ValueError(f"The inputs of {inputs.delivery_day} hold no price before it.")
    empty = int(np.isnan(context).sum())
    if empty:
        raise ValueError(f"The context of {inputs.delivery_day} holds {empty} empty prices "
                         f"in its last {steps} market time units.")
    return context


def source_settings(config: dict, family: str) -> dict:
    """Return the section of a model family under foundation_models in the config.

    Raises ValueError when the config has no such section.
    """
    sections = config.get(SECTION, {})
    if family not in sections:
        raise ValueError(f"A model entry of the family '{family}' needs the config section "
                         f"{SECTION}.{family}.")
    return sections[family]


def check_entry(settings: dict, family: str, source: dict, source_keys: tuple[str, ...]) -> None:
    """Refuse a config entry or a model section that the wrapper cannot run as written.

    Input: the settings of an entry under models, the family of the wrapper,
        its section under foundation_models and the keys that section must have.
    Raises ValueError with every problem in one line: a missing or an unknown
        key of the entry or of the section, another family, and a context
        length that is not a whole number of days above 0.
    """
    problems = [f"the key '{key}' is missing" for key in ENTRY_KEYS if key not in settings]
    problems += [f"the key '{key}' is unknown" for key in settings if key not in ENTRY_KEYS]
    problems += [f"the key '{key}' of {SECTION}.{family} is missing"
                 for key in source_keys if key not in source]
    problems += [f"the key '{key}' of {SECTION}.{family} is unknown"
                 for key in source if key not in source_keys]
    if "family" in settings and settings["family"] != family:
        problems.append(f"the family is '{settings['family']}', not '{family}'")
    days = settings.get(CONTEXT)
    # In Python a bool is an int, so True would pass as 1 day.
    if CONTEXT in settings and (not isinstance(days, int) or isinstance(days, bool) or days < 1):
        problems.append(f"{CONTEXT} must be a whole number of days above 0, not {days!r}")
    if problems:
        raise ValueError(f"Entry of the family '{family}': " + "; ".join(problems) + ".")
