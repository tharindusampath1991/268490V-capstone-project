"""Download archived weather forecast runs from the Open-Meteo Single Runs API.

Usage, from the repo root:
    .venv\\Scripts\\python -m epf.data.download_weather

For each delivery day D the download asks for one model run by its
initialisation time: the run of day D-1 at the hour set in the config. It
keeps the hours of delivery day D and the run time of every value, so the
issue time of each forecast is known. It never asks for reanalysis or
measured weather.

Zones, their weather points, the model, the variables and the folders come
from config/config.yaml. Core zones run first. Timestamps are in UTC.
"""

import sys
import time
from collections.abc import Callable
from datetime import date, timedelta
from functools import partial
from pathlib import Path

import pandas as pd
import requests

from epf.config import REPO_ROOT, Zone, load_config, ordered_zones
from epf.data.download_forecasts import hourly_coverage
from epf.data.entsoe_cache import cached_fetch
from epf.data.market_time import data_range, delivery_days, year_ranges

DATASET = "weather_forecast"
RUN_COLUMN = "run"
RUN_NOT_AVAILABLE = "run is not available"
YearRange = tuple[int, pd.Timestamp, pd.Timestamp]


class OpenMeteoError(Exception):
    """The Open-Meteo API did not answer with usable data."""


def parse_forecast_response(body: dict) -> pd.DataFrame:
    """Turn the JSON body of a forecast answer into a frame.

    Input: the decoded JSON body. Its times are in UTC without an offset.
    Output: a UTC index and one column per weather variable. A null value
        becomes an empty value.
    Raises OpenMeteoError when the answer states a time zone other than UTC.
    """
    if body.get("utc_offset_seconds") != 0:
        raise OpenMeteoError("The Open-Meteo answer is not in UTC.")
    hourly = dict(body["hourly"])
    index = pd.to_datetime(hourly.pop("time"), utc=True)
    return pd.DataFrame(hourly, index=index, dtype="float64")


def run_time(day_start: pd.Timestamp, run_hour_utc: int) -> pd.Timestamp:
    """Return the initialisation time of the run used for one delivery day.

    Input: 00:00 of delivery day D in market time, and the hour of the run.
    Output: run_hour_utc on the calendar day before D, in UTC.
    """
    day_before = day_start.date() - timedelta(days=1)
    return pd.Timestamp(day_before, tz="UTC") + timedelta(hours=run_hour_utc)


def fetch_delivery_day(get: Callable, settings: dict, point: dict,
                       day_start: pd.Timestamp, day_end: pd.Timestamp,
                       sleep: Callable[[float], None] = time.sleep) -> pd.DataFrame:
    """Download the weather forecast for the hours of one delivery day.

    Input: get is requests.get or a function with the same call. settings is
        the open_meteo part of the config. point holds latitude and longitude.
        day_start and day_end are 00:00 of day D and of day D+1 in market time.
        sleep is replaced in tests.
    Output: one row per hour of [day_start, day_end) with a UTC index, one
        column per weather variable, and the column "run" with the
        initialisation time of the run in UTC. No rows when the run is not in
        the archive.
    Raises OpenMeteoError for every other error answer. A dropped connection
        or a timeout is asked again, up to settings["retry_attempts"] times.
    """
    run = run_time(day_start, settings["run_hour_utc"])
    params = {
        "latitude": point["latitude"],
        "longitude": point["longitude"],
        "run": run.strftime("%Y-%m-%dT%H:%M"),
        "hourly": ",".join(settings["variables"]),
        "models": settings["model"],
        "forecast_hours": settings["forecast_hours"],
        "wind_speed_unit": settings["wind_speed_unit"],
    }
    response = _get_with_retries(get, settings, params, sleep)
    if response.status_code != 200:
        reason = _error_reason(response)
        if response.status_code == 400 and RUN_NOT_AVAILABLE in reason:
            return _no_rows()
        raise OpenMeteoError(
            f"Open-Meteo answered HTTP {response.status_code} for run {params['run']}: {reason}")
    data = parse_forecast_response(response.json())
    data = data[(data.index >= day_start) & (data.index < day_end)]
    return data.assign(**{RUN_COLUMN: run})


def fetch_weather(get: Callable, settings: dict, point: dict, start: pd.Timestamp,
                  end: pd.Timestamp, sleep: Callable[[float], None] = time.sleep) -> pd.DataFrame:
    """Download the weather forecast for every delivery day in [start, end).

    Input: the arguments of fetch_delivery_day, with start and end at 00:00 of
        a day in market time. sleep is replaced in tests.
    Output: the frames of fetch_delivery_day joined in time order. One request
        is made per delivery day, after a pause of settings["pause_seconds"].
        A day whose run is not in the archive adds no rows.
    """
    frames = []
    for day_start, day_end in delivery_days(start, end):
        sleep(settings["pause_seconds"])
        data = fetch_delivery_day(get, settings, point, day_start, day_end, sleep=sleep)
        if not data.empty:
            frames.append(data)
    return pd.concat(frames) if frames else _no_rows()


def download_weather(get: Callable, settings: dict, zones: list[Zone], ranges: list[YearRange],
                     cache_dir: Path, sleep: Callable[[float], None] = time.sleep) -> pd.DataFrame:
    """Download the weather forecast of every zone and year, or read it from the cache.

    Input: zones in the order they should run, year pieces from year_ranges in
        market time, and the folder of the Open-Meteo cache. A zone without a
        weather point is left out.
    Output: one row per zone, year and weather variable.
        rows            rows in the saved file
        runs            model runs in the saved file
        expected_hours  hours in the year piece
        missing_hours   hours in which the variable has no value
        repeated        timestamps that repeat an earlier one
    """
    rows = []
    for zone in zones:
        if zone.weather_point is None:
            continue
        for year, start, end in ranges:
            print(f"{zone.key:6s} {DATASET} {year}", flush=True)
            fetch = partial(fetch_weather, get, settings, zone.weather_point, sleep=sleep)
            data = cached_fetch(fetch, cache_dir, DATASET, zone.key, year, start, end)
            runs = data[RUN_COLUMN].nunique() if RUN_COLUMN in data else 0
            for found in hourly_coverage(data.drop(columns=RUN_COLUMN, errors="ignore"),
                                         start, end):
                rows.append({
                    "zone": zone.key, "year": year, "column": found["column"],
                    "rows": len(data), "runs": runs,
                    "expected_hours": found["expected"],
                    "missing_hours": found["expected"] - found["present"],
                    "repeated": found["duplicates"],
                })
    return pd.DataFrame(rows)


def main() -> None:
    """Download the weather forecast of all configured zones and print the counts."""
    config = load_config()
    market_tz = config["market"]["timezone"]
    settings = config["open_meteo"]
    today = pd.Timestamp.now(tz=market_tz).normalize()
    data_start, end = data_range(config, today)
    first_delivery_day = date.fromisoformat(settings["first_run"]) + timedelta(days=1)
    start = max(data_start, pd.Timestamp(first_delivery_day, tz=market_tz))
    cache_dir = REPO_ROOT / config["paths"]["raw"] / "open_meteo"
    get = partial(requests.get, timeout=settings["timeout_seconds"])

    try:
        summary = download_weather(get, settings, ordered_zones(config),
                                   year_ranges(start, end), cache_dir)
    except OpenMeteoError as error:
        sys.exit(f"{error} Finished years are saved, so run the command again to resume.")
    except requests.RequestException as error:
        sys.exit(f"Open-Meteo request failed: {type(error).__name__}. "
                 "Finished years are saved, so run the command again to resume.")
    print(summary.to_string(index=False))


def _get_with_retries(get: Callable, settings: dict, params: dict,
                      sleep: Callable[[float], None]) -> requests.Response:
    """Send one request and ask again after a dropped connection or a timeout.

    Output: the first answer that arrives. An error answer is returned, not
        retried. After settings["retry_attempts"] failed attempts the last
        error is raised. The wait between attempts is
        settings["retry_wait_seconds"].
    """
    for attempt in range(1, settings["retry_attempts"] + 1):
        try:
            return get(settings["url"], params=params)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == settings["retry_attempts"]:
                raise
            sleep(settings["retry_wait_seconds"])


def _error_reason(response: requests.Response) -> str:
    """Return the reason text of an error answer, or an empty string."""
    try:
        return str(response.json().get("reason", ""))
    except ValueError:
        return ""


def _no_rows() -> pd.DataFrame:
    """Return an empty frame with a UTC index."""
    return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"))


if __name__ == "__main__":
    main()
