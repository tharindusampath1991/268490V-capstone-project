"""Statistical baselines: ARIMA, ETS and MSTL from statsforecast, on the price history only.

A model is fitted on the prices it receives for a delivery day. That window
ends at the price cut (epf.evaluation.cutoff). On every delivery day the
forecast applies the fitted model to the window of that day, with the forward
method of statsforecast. So between two fits the form of the model and its
estimated parameters stay as they are, and the newer prices enter through the
window. For MSTL forward decomposes the window again and keeps only the
fitted trend model.

statsforecast counts steps, not clock time. A season of one day is 24 hourly
or 96 quarter-hour steps, also across a clock change.

Prices can be negative. No Box-Cox transform is used and every ETS form is
additive. Prices are in EUR/MWh with a UTC index.
"""

from datetime import timedelta

import pandas as pd
from statsforecast.models import MSTL, AutoARIMA, AutoETS

from epf.evaluation.cutoff import DayInputs

ARIMA = "arima"
ETS = "ets"
MSTL_FAMILY = "mstl"
FAMILIES = (ARIMA, ETS, MSTL_FAMILY)
ONE_SEASON_FAMILIES = (ARIMA, ETS)
BOX_COX_ARGUMENTS = ("blambda", "biasadj")


class StatsModel:
    """One statistical model as a model of the backtest, set up from its config entry."""

    def __init__(self, name: str, settings: dict):
        """Keep the name and the settings of a config entry.

        Input: the name of the entry and its settings. family is arima, ets
            or mstl. season_days holds the season lengths in days. An ets
            entry has form, an mstl entry has trend_form, and an arima entry
            may have search, the arguments of AutoARIMA.
        Raises ValueError for settings that check_settings refuses.
        """
        check_settings(settings)
        self.name = name
        self.settings = settings
        self.fitted = None

    @property
    def params(self) -> dict:
        """The settings of the model, for the results."""
        return dict(self.settings)

    def fit(self, inputs: DayInputs) -> None:
        """Choose the form of the model and estimate it on the prices of the inputs."""
        seasons = season_lengths(self.settings["season_days"], inputs.target_index)
        self.fitted = build(self.settings, seasons).fit(inputs.prices.to_numpy(dtype=float))

    def predict(self, inputs: DayInputs) -> pd.Series:
        """Return the forecast for the market time units of the delivery day.

        The fitted model is applied to the prices of the inputs, which end at
        the price cut of this delivery day. Nothing is estimated again.
        """
        result = self.fitted.forward(y=inputs.prices.to_numpy(dtype=float),
                                     h=len(inputs.target_index))
        return pd.Series(result["mean"], index=inputs.target_index, name="forecast")


def season_lengths(season_days: list[int], target_index: pd.DatetimeIndex) -> list[int]:
    """Return season lengths in market time units.

    Input: season lengths in days, and the market time units of a delivery
        day in UTC. Their step gives the units per day: 24 or 96.
    Output: one length per entry of season_days.
    """
    step = target_index[1] - target_index[0]
    units_per_day = round(timedelta(days=1).total_seconds() / step.total_seconds())
    return [days * units_per_day for days in season_days]


def build(settings: dict, seasons: list[int]) -> AutoARIMA | AutoETS | MSTL:
    """Return the statsforecast model of a config entry, not yet fitted.

    Input: the settings of the entry and its season lengths in market time units.
    """
    family = settings["family"]
    if family == ARIMA:
        return AutoARIMA(season_length=seasons[0], **settings.get("search", {}))
    if family == ETS:
        return AutoETS(season_length=seasons[0], model=settings["form"])
    return MSTL(season_length=seasons, trend_forecaster=AutoETS(model=settings["trend_form"]))


def check_settings(settings: dict) -> None:
    """Refuse settings that name no known model or that could transform the price.

    Raises ValueError for an unknown family, for more than one season in a
        model that has one, for an ETS form that is not additive, for an MSTL
        trend form that is not additive or has a season, and for a Box-Cox
        argument of ARIMA.
    """
    family = settings["family"]
    if family not in FAMILIES:
        raise ValueError(f"Unknown family '{family}'. Known: {list(FAMILIES)}.")
    if family in ONE_SEASON_FAMILIES and len(settings["season_days"]) != 1:
        raise ValueError(f"A model of the family '{family}' has exactly one season, "
                         f"not {settings['season_days']}.")
    if family == ETS:
        check_additive(settings["form"], seasons="NAZ")
    if family == MSTL_FAMILY:
        check_additive(settings["trend_form"], seasons="N")
    forbidden = [name for name in settings.get("search", {}) if name in BOX_COX_ARGUMENTS]
    if forbidden:
        raise ValueError(f"Prices can be negative, so {forbidden} may not be set.")


def check_additive(form: str, seasons: str) -> None:
    """Refuse an ETS form that statsforecast could fit with a multiplicative part.

    Input: the three letters for error, trend and season, and the letters
        allowed for the season. The error must be A. With an additive error
        the letter Z chooses among none and additive only.
    Raises ValueError for any other form.
    """
    if len(form) != 3 or form[0] != "A" or form[1] not in "NAZ" or form[2] not in seasons:
        raise ValueError(f"The ETS form '{form}' is not allowed. The error must be A, the trend "
                         f"one of NAZ and the season one of {seasons}.")
