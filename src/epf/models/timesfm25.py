"""TimesFM 2.5 zero-shot as a model of the backtest: the price history only.

TimesFM 2.5 is a pretrained model (google/timesfm-2.5-200m-pytorch). Nothing
is fitted on the prices of the project. For delivery day D the model reads
the last prices before the price cut (epf.evaluation.cutoff), its context, and
answers with one value per market time unit of D. The horizon is the number
of market time units of D, so 23 or 25 hours and 92 or 100 quarter-hours on a
clock-change day.

The point forecast is the first answer of TimesFM. In timesfm 3.0.2 that is
the 0.5 quantile, the median, and not the mean.

Prices can be negative. With infer_is_positive TimesFM cuts every forecast at
0 when its context holds no negative price, so the option must be false.

The model ID, the revision and the forecast options stand in the config under
foundation_models.timesfm25. The weights are loaded on the first call of fit,
from the Hugging Face cache of the user or, the first time, from the hub.
TimesFM takes its longest context when the options are set, and that length
depends on the table. So fit sets the options again for the table of its inputs.

torch and timesfm are imported inside the functions that need them. Every
backtest command imports this module, and importing torch takes about a second.

Prices are in EUR/MWh. Tables have a UTC index. Delivery days are in market time.
"""

from collections.abc import Callable

import pandas as pd

from epf.evaluation.cutoff import DayInputs
from epf.models.zero_shot import CONTEXT, check_entry, context_steps, price_context

FAMILY = "timesfm25"
FORECAST = "forecast"
POSITIVE = "infer_is_positive"
OPTION_KEYS = ("max_horizon", "normalize_inputs", "force_flip_invariance", POSITIVE)
SOURCE_KEYS = ("model_id", "revision", "torch_compile", *OPTION_KEYS)


def load_model(source: dict, seed: int):
    """Load the pretrained TimesFM 2.5 model at its pinned revision.

    Input: the section foundation_models.timesfm25 of the config, and the
        seed of the project. A forecast draws no random number, so the seed
        changes nothing. It is set so that every generator of a run is seeded.
    Output: a timesfm.TimesFM_2p5_200M_torch. It runs on the GPU when torch
        finds one and on the CPU otherwise. timesfm offers no choice.
    """
    import timesfm
    import torch

    torch.manual_seed(seed)
    return timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        source["model_id"], revision=source["revision"], torch_compile=source["torch_compile"])


def forecast_options(source: dict, max_context: int):
    """Return the forecast options of TimesFM for one table.

    Input: the section foundation_models.timesfm25 of the config, and the
        longest context in market time units.
    Output: a timesfm.ForecastConfig with the options of the section. Every
        other option keeps the default of timesfm.
    """
    import timesfm

    return timesfm.ForecastConfig(max_context=max_context,
                                  **{key: source[key] for key in OPTION_KEYS})


class TimesFm25Model:
    """TimesFM 2.5 zero-shot as a model of the backtest, set up from its config entry."""

    def __init__(self, name: str, settings: dict, source: dict, seed: int,
                 load: Callable = load_model):
        """Keep the name, the settings of a config entry and where the model comes from.

        Input: the name of the entry and its settings. family is timesfm25
            and context_days is the context length in days. Then the section
            foundation_models.timesfm25 of the config, the seed of the
            project, and the function that loads the model. The tests hand
            over one that loads nothing.
        Raises ValueError for an entry or a section that check_entry refuses,
            and for a section whose infer_is_positive is not false.
        """
        check_entry(settings, FAMILY, source, SOURCE_KEYS)
        if source[POSITIVE] is not False:
            raise ValueError(f"Entry of the family '{FAMILY}': {POSITIVE} must be false, not "
                             f"{source[POSITIVE]!r}, because prices can be negative.")
        self.name = name
        self.settings = settings
        self.source = source
        self.seed = seed
        self.load = load
        self.model = None

    @property
    def params(self) -> dict:
        """The settings of the entry and the model section, for the results."""
        return {**self.settings, **self.source}

    def fit(self, inputs: DayInputs) -> None:
        """Load the pretrained model on the first call and set its options. Nothing is estimated.

        The options are set on every call, with the context length of the
        table of the inputs.
        Raises ValueError when TimesFM refuses the options, for example a
            context and a horizon that are together longer than it allows.
        """
        if self.model is None:
            self.model = self.load(self.source, self.seed)
        steps = context_steps(self.settings[CONTEXT], inputs.target_index)
        self.model.compile(forecast_options(self.source, steps))

    def predict(self, inputs: DayInputs) -> pd.Series:
        """Return the forecast for the market time units of the delivery day.

        Output: the point forecast of TimesFM for each market time unit, in
            EUR/MWh, on inputs.target_index (UTC).
        Raises ValueError when the model has not been loaded, when
            price_context refuses the prices, and when the delivery day has
            more market time units than max_horizon of the model section.
        """
        if self.model is None:
            raise ValueError(f"The model '{self.name}' has not been loaded, so it cannot "
                             f"forecast {inputs.delivery_day}.")
        context = price_context(inputs, self.settings[CONTEXT])
        point, _ = self.model.forecast(horizon=len(inputs.target_index), inputs=[context])
        return pd.Series(point[0], index=inputs.target_index, name=FORECAST)
