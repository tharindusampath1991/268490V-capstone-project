"""Chronos-2 zero-shot as a model of the backtest: the price history only.

Chronos-2 is a pretrained model (amazon/chronos-2). Nothing is fitted on the
prices of the project. For delivery day D the model reads the last prices
before the price cut (epf.evaluation.cutoff), its context, and answers with
one value per market time unit of D. The horizon is the number of market time
units of D, so 23 or 25 hours and 92 or 100 quarter-hours on a clock-change day.

The point forecast is the 0.5 quantile, the median. Chronos-2 forecasts
quantiles and has no separate mean. It works on its own scaling of the
context, so a negative price needs no setting.

The model ID, the revision and the device stand in the config under
foundation_models.chronos2. The weights are loaded on the first call of fit,
from the Hugging Face cache of the user or, the first time, from the hub.

torch and chronos are imported inside load_pipeline. Every backtest command
imports this module, and the two imports take more than 4 seconds.

Prices are in EUR/MWh. Tables have a UTC index. Delivery days are in market time.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd

from epf.evaluation.cutoff import DayInputs
from epf.models.zero_shot import CONTEXT, check_entry, context_steps, price_context

FAMILY = "chronos2"
FORECAST = "forecast"
SOURCE_KEYS = ("model_id", "revision", "device")
MEDIAN = 0.5


def load_pipeline(source: dict, seed: int):
    """Load the pretrained Chronos-2 pipeline at its pinned revision.

    Input: the section foundation_models.chronos2 of the config, and the seed
        of the project. A forecast draws no random number, so the seed
        changes nothing. It is set so that every generator of a run is seeded.
    Output: a chronos.Chronos2Pipeline on the device of the section.
    """
    import torch
    from chronos import Chronos2Pipeline

    torch.manual_seed(seed)
    return Chronos2Pipeline.from_pretrained(source["model_id"], revision=source["revision"],
                                            device_map=source["device"])


class Chronos2Model:
    """Chronos-2 zero-shot as a model of the backtest, set up from its config entry."""

    def __init__(self, name: str, settings: dict, source: dict, seed: int,
                 load: Callable = load_pipeline):
        """Keep the name, the settings of a config entry and where the model comes from.

        Input: the name of the entry and its settings. family is chronos2 and
            context_days is the context length in days. Then the section
            foundation_models.chronos2 of the config, the seed of the
            project, and the function that loads the pipeline. The tests
            hand over one that loads nothing.
        Raises ValueError for an entry or a section that check_entry refuses.
        """
        check_entry(settings, FAMILY, source, SOURCE_KEYS)
        self.name = name
        self.settings = settings
        self.source = source
        self.seed = seed
        self.load = load
        self.pipeline = None

    @property
    def params(self) -> dict:
        """The settings of the entry and the model section, for the results."""
        return {**self.settings, **self.source}

    def fit(self, inputs: DayInputs) -> None:
        """Load the pretrained pipeline on the first call. Nothing is estimated."""
        if self.pipeline is None:
            self.pipeline = self.load(self.source, self.seed)

    def predict(self, inputs: DayInputs) -> pd.Series:
        """Return the forecast for the market time units of the delivery day.

        Output: the 0.5 quantile of Chronos-2 for each market time unit, in
            EUR/MWh, on inputs.target_index (UTC).
        Raises ValueError when the pipeline has not been loaded, when the
            context is longer than the model allows, and when price_context
            refuses the prices.
        """
        if self.pipeline is None:
            raise ValueError(f"The model '{self.name}' has not been loaded, so it cannot "
                             f"forecast {inputs.delivery_day}.")
        steps = context_steps(self.settings[CONTEXT], inputs.target_index)
        limit = self.pipeline.model_context_length
        # Chronos-2 shortens a longer context to its limit with a warning only.
        if steps > limit:
            raise ValueError(f"The context of '{self.name}' is {steps} market time units. "
                             f"The model allows {limit}.")
        context = price_context(inputs, self.settings[CONTEXT])
        quantiles, _ = self.pipeline.predict_quantiles(
            [context], prediction_length=len(inputs.target_index), quantile_levels=[MEDIAN],
            context_length=steps)
        # One series with one variate and one level: (1, steps of the day, 1).
        return pd.Series(np.asarray(quantiles[0])[0, :, 0], index=inputs.target_index,
                         name=FORECAST)
