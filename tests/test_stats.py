"""Tests for the statistical baseline models, run through the backtest loop.

They use small synthetic price tables with a known daily shape, no network and no data files.
The price is in EUR/MWh with a UTC index. Delivery days are in market time.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from epf.data.market_time import delivery_days, hourly_index, quarter_hour_index
from epf.evaluation.backtest import run_days
from epf.evaluation.cutoff import Columns
from epf.models.stats import StatsModel, season_lengths

MARKET_TZ = "Europe/Berlin"
COLUMNS = Columns(price="price", day_ahead=("load_forecast",), delayed=("actual_load",))

ETS = {"family": "ets", "form": "ANA", "season_days": [1], "history_days": 14}
MSTL = {"family": "mstl", "trend_form": "ANN", "season_days": [1, 7], "history_days": 21}
ARIMA = {"family": "arima", "search": {"max_p": 1, "max_q": 1, "max_P": 0, "max_Q": 1},
         "season_days": [1], "history_days": 14}
SETTINGS = {"ets": ETS, "mstl": MSTL, "arima": ARIMA}


def market_time(day: str | date) -> pd.Timestamp:
    """00:00 in market time on a day."""
    return pd.Timestamp(day, tz=MARKET_TZ)


def day_after(day: str, days: int = 1) -> date:
    """The calendar day some days after a day. A negative number goes back."""
    return date.fromisoformat(day) + timedelta(days=days)


def daily_shape(index: pd.DatetimeIndex) -> np.ndarray:
    """A price that depends on the local time of day only: 20 plus a sine of 30, so -10 to 50."""
    local = index.tz_convert(MARKET_TZ)
    return 20 + 30 * np.sin(2 * np.pi * (local.hour + local.minute / 60) / 24)


def price_table(delivery_day: str, make_index=hourly_index, level: float = 0.0) -> pd.DataFrame:
    """A table from 25 days before a delivery day to 2 days after it.

    The price is the daily shape plus a small noise plus level. The other two columns
    are constants.
    """
    index = make_index(market_time(day_after(delivery_day, -25)),
                       market_time(day_after(delivery_day, 2)))
    noise = np.random.default_rng(0).normal(0, 1, len(index))
    return pd.DataFrame({"price": daily_shape(index) + noise + level, "load_forecast": 1.0,
                         "actual_load": 2.0}, index=index)


def forecasts(settings: dict, table: pd.DataFrame, first_day: str, count: int = 1,
              make_index=hourly_index) -> pd.Series:
    """The forecasts of count delivery days through the backtest loop, with one fit."""
    days = delivery_days(market_time(first_day), market_time(day_after(first_day, count)))
    scored, _ = run_days(table, days, make_index, StatsModel("candidate", settings), COLUMNS,
                         refit_every_days=7, history_days=settings["history_days"])
    return scored["forecast"]


@pytest.mark.parametrize("family", ["ets", "mstl", "arima"])
@pytest.mark.parametrize("day, hours", [("2026-07-01", 24), ("2026-03-29", 23),
                                        ("2026-10-25", 25)])
def test_the_forecast_has_one_finite_value_per_hour_of_the_delivery_day(family, day, hours):
    forecast = forecasts(SETTINGS[family], price_table(day), day)

    assert len(forecast) == hours
    assert forecast.index.equals(hourly_index(market_time(day), market_time(day_after(day))))
    assert np.isfinite(forecast).all()


@pytest.mark.parametrize("day, quarter_hours", [("2026-03-29", 92), ("2026-10-25", 100)])
def test_the_forecast_has_one_value_per_quarter_hour_of_a_clock_change_day(day, quarter_hours):
    forecast = forecasts(ETS, price_table(day, quarter_hour_index), day,
                         make_index=quarter_hour_index)

    assert len(forecast) == quarter_hours
    assert np.isfinite(forecast).all()


@pytest.mark.parametrize("family", ["ets", "mstl", "arima"])
def test_the_forecast_follows_the_daily_shape_of_the_history(family):
    day = "2026-07-01"

    forecast = forecasts(SETTINGS[family], price_table(day), day)

    # The noise has a standard deviation of 1 and the shape runs from -10 to 50.
    assert np.abs(forecast - daily_shape(forecast.index)).max() < 4


def test_the_quarter_hour_forecast_follows_the_daily_shape_of_the_history():
    day = "2026-07-01"

    forecast = forecasts(ETS, price_table(day, quarter_hour_index), day,
                         make_index=quarter_hour_index)

    assert np.abs(forecast - daily_shape(forecast.index)).max() < 4


def test_season_lengths_are_the_season_days_in_market_time_units():
    hours = hourly_index(market_time("2026-07-01"), market_time("2026-07-02"))
    quarter_hours = quarter_hour_index(market_time("2026-07-01"), market_time("2026-07-02"))

    assert season_lengths([1, 7], hours) == [24, 168]
    assert season_lengths([1, 7], quarter_hours) == [96, 672]


# The model is fitted for 2026-07-01 only. The forecast of 2026-07-02 lies between two fits.
@pytest.mark.parametrize("family", ["ets", "mstl", "arima"])
def test_a_forecast_between_two_fits_uses_the_newest_price_before_its_cut(family):
    table = price_table("2026-07-01")
    changed = table.copy()
    changed.loc[pd.Timestamp("2026-07-01 23:00", tz=MARKET_TZ), "price"] += 50

    before = forecasts(SETTINGS[family], table, "2026-07-01", count=2)
    after = forecasts(SETTINGS[family], changed, "2026-07-01", count=2)

    second_day = before.index >= market_time("2026-07-02")
    pd.testing.assert_series_equal(before[~second_day], after[~second_day])
    assert np.abs(after[second_day] - before[second_day]).max() > 1


@pytest.mark.parametrize("family", ["ets", "mstl", "arima"])
def test_a_forecast_between_two_fits_ignores_every_value_after_the_cuts(family):
    table = price_table("2026-07-01")
    changed = table.copy()
    changed.loc[changed.index >= market_time("2026-07-02"), "price"] += 1000
    changed["load_forecast"] += 1000
    changed["actual_load"] += 1000

    before = forecasts(SETTINGS[family], table, "2026-07-01", count=2)
    after = forecasts(SETTINGS[family], changed, "2026-07-01", count=2)

    pd.testing.assert_series_equal(before, after)


def test_a_forecast_between_two_fits_is_not_the_forecast_of_a_new_fit():
    table = price_table("2026-07-01")
    table.loc[pd.Timestamp("2026-07-01 12:00", tz=MARKET_TZ), "price"] += 200

    kept = forecasts(ETS, table, "2026-07-01", count=2)
    refitted = forecasts(ETS, table, "2026-07-02")

    second_day = kept.index >= market_time("2026-07-02")
    assert np.abs(kept[second_day] - refitted).max() > 0.01


@pytest.mark.parametrize("family", ["ets", "mstl", "arima"])
def test_a_history_of_negative_prices_gives_a_negative_forecast(family):
    day = "2026-07-01"

    forecast = forecasts(SETTINGS[family], price_table(day, level=-100.0), day)

    # The history runs from about -110 to -50.
    assert forecast.max() < -40
    assert forecast.min() > -120


@pytest.mark.parametrize("form", ["ZZZ", "MNA", "AAM", "AMA", "ZNA"])
def test_an_ets_form_that_can_be_multiplicative_is_refused(form):
    with pytest.raises(ValueError, match=form):
        StatsModel("candidate", {**ETS, "form": form})


@pytest.mark.parametrize("trend_form", ["ZZN", "MNN", "ANA"])
def test_an_mstl_trend_form_that_is_multiplicative_or_seasonal_is_refused(trend_form):
    with pytest.raises(ValueError, match=trend_form):
        StatsModel("candidate", {**MSTL, "trend_form": trend_form})


def test_a_box_cox_argument_for_arima_is_refused():
    with pytest.raises(ValueError, match="blambda"):
        StatsModel("candidate", {**ARIMA, "search": {"blambda": 0.5}})


def test_an_unknown_family_is_refused():
    with pytest.raises(ValueError, match="prophet"):
        StatsModel("candidate", {**ETS, "family": "prophet"})


@pytest.mark.parametrize("family", ["ets", "arima"])
def test_two_seasons_are_refused_for_a_model_with_one_season(family):
    with pytest.raises(ValueError, match="season"):
        StatsModel("candidate", {**SETTINGS[family], "season_days": [1, 7]})


def test_the_settings_of_the_entry_are_the_params_for_the_results():
    assert StatsModel("candidate", ETS).params == ETS
    assert StatsModel("candidate", ETS).name == "candidate"
