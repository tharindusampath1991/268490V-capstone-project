# Decisions

Numbered entries: decision, reason, alternative rejected, date.

## 1. Add SE1–SE4 as extra zones in M2
- Date: 2026-11-19
- Decision: SE1, SE2, SE3 and SE4 are added as extra zones in Milestone 2, next to the three core zones approved in Milestone 1. They use the same pipeline through config entries, with no zone-specific tuning or features.
- Reason: To extend the scope a little beyond the three approved zones. A zone is added through a config entry and runs through the same pipeline, so the Swedish zones add no technical difficulty.
- Alternatives rejected: SE3 only. Sweden after M2.
- Risks: Milestone 1 was approved with 3 zones. Seven zones with 14 days to M2.

## 2. Python 3.12 in `.venv`
- Date: 2026-11-20
- Decision: The project runs on Python 3.12 in a virtual environment named `.venv`.
- Reason: `entsoe-py` 1.0.0 requires Python 3.12 or newer. Every other planned library declares Python 3.12 support on PyPI.
- Alternatives rejected: Python 3.11 with `entsoe-py` 0.8.1, the newest version that installs there. Python 3.14, the newest Python, with the highest chance of an untested dependency.

## 3. Pin direct dependencies only, with pandas 2.3.3
- Date: 2026-11-20
- Decision: `requirements.txt` lists only the packages the code imports, each pinned with `==`. A package is added when the code first imports it. pandas is pinned to 2.3.3.
- Reason: Every line can be explained. `statsforecast` 2.1.1 requires pandas below 3.0, so a pandas 3 pin would have to change when the statistical baseline is added. A dry-run resolve of the full planned library set on 2026-11-20 chose pandas 2.3.3.
- Alternative rejected: A full `pip freeze`. It is exact, but it lists packages the code never imports, and packages that pip installs only on Windows, such as `colorama`.
- Exception, added 2026-11-20: numpy is pinned to 2.5.5 although the code does not import it. With numpy 2.5.5 and pandas 2.3.3, `pd.Timedelta(days=1)` raises a DeprecationWarning that says it "will raise an error in the future". `entsoe-py` 1.0.0 calls it in `query_day_ahead_prices`. An unpinned numpy could therefore break the price download on a later fresh install.
- Exception, added 2026-11-22: pyarrow is pinned although the code does not import it. pandas needs it to read and write the Parquet files of the raw cache.

## 4. One shared ENTSO-E fetch-and-cache module
- Date: 2026-11-20
- Decision: The token loading, fetch and cache functions move from `scripts/check_coverage.py` into `src/epf/data/`. The gate script and the price downloader both import them.
- Reason: One code path and one cache. The gate had not been run, so no cached files need migrating.
- Alternatives rejected: A separate downloader with its own cache. Running the gate as it was and reusing its files, which keeps its cache flaws.

## 5. One cache file per zone and year, with a manifest
- Date: 2026-11-20
- Decision: Raw ENTSO-E downloads are cached as `data/raw/entsoe/{dataset}/{ZONE}_{YEAR}.parquet`. A manifest records the query start, query end, download time in UTC, row count and `entsoe-py` version of each file. A saved file is reused only when the manifest shows the same query start and end. An empty answer is never saved.
- Reason: The first version of the gate cache treated a partial current-year file as finished once the calendar year changed, and kept an empty file forever. With the same-query rule a partial year is downloaded again when the requested end moves, and it is reused once `DATA_END` is frozen.
- Changed on 2026-11-20: The first wording said that a year counts as complete only when the query end reaches the end of that year. Under that rule the current year is never complete, so every rebuild would download it again and the frozen snapshot of PROJECT_CONTEXT §4 could change.
- Alternatives rejected: One file per zone and month, which gives twelve times more files for no gain. One file per zone for the whole range, which downloads every year again to add one day.

## 6. Every ENTSO-E call goes through one error wrapper
- Date: 2026-11-20
- Decision: All ENTSO-E calls pass through one function. On failure it raises a project error that carries only the exception type and the HTTP status. Logging is never set to DEBUG for `urllib3`.
- Reason: The request URL carries the token. `entsoe-py` 1.0.0 masks the token in error messages, but the exception object still holds the request with the full URL, and `urllib3` writes the request path to its DEBUG log.
- Alternative rejected: Catching `requests` errors once in `main`. Other exception types would print a raw traceback.
- Added 2026-11-20: The project error is raised after the `except` block has ended, so it holds no link to the original error. Alternative rejected: `raise ... from None` inside the block. A test showed that the new error then still holds the original in `__context__`, with the request URL.

## 7. Energy-Charts is a cross-check only
- Date: 2026-11-20
- Decision: ENTSO-E is the single source for prices. Energy-Charts prices are downloaded for the full history and compared with a tolerance of 0.01 EUR/MWh. Differences are reported in `docs/price_crosscheck.md`. They are never used to correct or fill ENTSO-E values.
- Reason: One source keeps the data lineage simple. A full comparison finds shifted hours that daily means would hide.
- Alternatives rejected: Comparing a sample or daily means only. Failing the run on a mismatch. Filling ENTSO-E gaps from Energy-Charts.
- Condition: If the Energy-Charts API cannot return a full year per request, the comparison falls back to a sample: one week per zone and year, the weeks around 1 Oct 2025, and the clock-change days.

## 8. The token is read by a small parser of our own
- Date: 2026-11-20
- Decision: The `.env` file is read by a short parser of our own, with the path resolved from the repo root.
- Reason: It is about ten lines and adds no dependency.
- Alternative rejected: `python-dotenv`.
- Changed on 2026-11-22: The first wording placed the parser in the gate script. Entry 4 moved it into the package. It is `_token_from_env_file` in `src/epf/data/entsoe_api.py`.

## 9. Market time zone and the 15-minute switch date live in config
- Date: 2026-11-20
- Decision: `config/config.yaml` holds the market time zone (Europe/Berlin) and the first 15-minute delivery day (2025-10-01). The gate script's Europe/Brussels constant is replaced by the config value.
- Reason: One definition for all code. Europe/Berlin and Europe/Brussels have the same UTC offset over the whole data period, so results do not change.
- Alternative rejected: Constants in each script.

## 10. Raw price files hold the `entsoe-py` pandas client output
- Date: 2026-11-20
- Decision: The raw price layer stores the series returned by `EntsoePandasClient.query_day_ahead_prices`, with the index converted to UTC and cut to [start, end). The project adds its own checks on top: a unique index and the expected number of values on every delivery day.
- Reason: The client already returns the main day-ahead auction price at the market's resolution, hourly before 2025-10-01 and 15-minute from then. This is far less code to defend than a second parser path. The Energy-Charts cross-check gives independent evidence.
- Alternative rejected: Saving the XML from the raw client and selecting the resolution in project code. It shows each resolution separately, but it needs paging and the DE_LU auction-sequence rule in our code.
- Limit: The client merges resolutions and collapses duplicate timestamps before we see them (DATA_NOTES). The one-value-per-market-time-unit check therefore runs on the client's output, not on the raw API response.

## 11. Editable install through a minimal `pyproject.toml`
- Date: 2026-11-20
- Decision: `src/epf` is installed in editable mode by the `-e .` line in `requirements.txt`. `pyproject.toml` holds only the package metadata, the `src` layout and the pytest test path. Dependencies stay in `requirements.txt`.
- Reason: After one setup command, the tests and `python -m epf...` commands can import the package from any folder.
- Alternative rejected: Setting `PYTHONPATH=src` by hand. It differs per operating system and is easy to forget on a fresh clone.

## 12. Energy-Charts prices are downloaded for all seven zones; restricted results stay local
- Date: 2026-11-20
- Decision: The cross-check of entry 7 downloads Energy-Charts prices for all seven zones, with the `bzn` codes DE-LU, FR, ES, SE1, SE2, SE3 and SE4. Each saved file records whether the API stated CC BY 4.0 for that answer. Results for CC BY 4.0 zones go into the committed `docs/price_crosscheck.md`. Results for the other zones go only into `data/local/price_crosscheck_restricted.md`, which git ignores. The committed report names those zones and shows none of their numbers. Raw Energy-Charts files are never committed.
- Reason: All zones are free to query. Only the licence differs. On 2026-11-20 the `license` field of the API stated CC BY 4.0 (Bundesnetzagentur | SMARD.de) for DE-LU, FR and SE4, and "private and internal use only" for ES, SE1, SE2 and SE3, with external use of raw or derived data prohibited. A check on the owner's machine is internal use. A public repository is not.
- Alternatives rejected: Checking only the three CC BY 4.0 zones, which leaves ES and three Swedish zones without an independent check. Publishing the results of all seven zones, which the licence of four zones does not allow.
- Note: This entry refines entry 7. PROJECT_CONTEXT §3 lists Energy-Charts as CC BY 4.0 without this limit.

## 13. A "no data" answer raises its own error
- Date: 2026-11-20
- Decision: `call_entsoe` raises `EntsoeNoDataError` when ENTSO-E has no data for a query, and `EntsoeRequestError` for every other failure. The fetch functions turn the first into an empty frame.
- Reason: A missing series is a result to record, for example a solar forecast that a zone does not publish. A failed call must stop the run. The two need different handling.
- Alternative rejected: Returning an empty frame from the wrapper for both cases. A caller can then mistake a failed call for a finished download.

## 14. `data.end` is the last delivery day included
- Date: 2026-11-20
- Decision: `data.end` in the config names the last delivery day that belongs to the data. The data period ends at 00:00 market time on the following day. While `data.end` is not set, the period ends at 00:00 today.
- Reason: "DATA_END" reads naturally as the last day in the data. The following day is computed with calendar-day arithmetic, so a clock-change day gives the right midnight.
- Alternative rejected: An exclusive end date, which is easy to misread by one day.

## 15. ENTSO-E requests time out after 120 seconds
- Date: 2026-11-20
- Decision: The `entsoe-py` client is created with a timeout of 120 seconds per request, set in the config.
- Reason: The client has no timeout by default. A stalled request would then hang a download of several hundred requests with no message. After a timeout the run stops with a clear error and resumes from the saved files.
- Alternative rejected: The client default.

## 16. Price checks report counts and change nothing
- Date: 2026-11-20
- Decision: The price downloader counts missing market time units, delivery days with gaps, prices at unexpected times and repeated timestamps. It prints the counts and neither changes the data nor stops the run.
- Reason: The raw layer keeps what ENTSO-E returned. Gaps are judged by the coverage gate and handled in the cleaning step, where each rule can be documented.
- Alternative rejected: Stopping on the first repeated timestamp, which would block all zones on one bad year. Dropping repeated timestamps silently, as the first gate script did.

## 17. The coverage gate logic lives in the package
- Date: 2026-11-20
- Decision: The gate logic is in `src/epf/data/coverage_gate.py`. `scripts/check_coverage.py` only reads the config, runs the logic and writes the report. Repeated timestamps in forecasts are kept in the raw files and counted in the report. Each forecast column is marked keep or drop per zone by the forecast threshold.
- Reason: Code in the package can be tested and shares the cache, the error wrapper and the price checks with the downloader. The first script had its own copies of these and its own constants.
- Alternative rejected: Keeping the logic inside the script.

## 18. Energy-Charts requests are 31 seconds apart
- Date: 2026-11-20
- Decision: The cross-check waits 31 seconds before each Energy-Charts request. When the API answers HTTP 429, it waits the seconds of the `Retry-After` header and asks once more.
- Reason: The API's endpoint catalogue states a limit of 2 price requests per minute and asks clients to honour `Retry-After`. With 6 seconds between requests the sixth request got HTTP 429.
- Alternative rejected: A shorter fixed pause. Retrying without limit.

## 19. ES stays in every experiment and keeps its wind forecast
- Date: 2026-11-21, decided by the owner
- Decision: The coverage gate decides the extra zones only. Core zones are measured and never cut. The ES `Wind Onshore` forecast is kept although its 2026 coverage is below the 95% threshold. It is listed under `coverage_gate.keep_columns` in the config, and the gate report marks it "keep by decision". The missing days stay missing in the raw data, and no value is invented for them. How the models treat those days is fixed in the cleaning step and logged there.
- Reason: ES is one of the three core zones approved in Milestone 1. In the data downloaded on 2026-11-20, the ES wind forecast covers at least 99.73% of hours in every year from 2019 to 2025. In 2026 it covers 93.81%: 20 whole days are missing, 480 of 7752 hours, in 9 blocks. Dropping the column would take the wind forecast out of RQ2 for a core zone because of 20 days.
- Alternatives rejected: Applying the drop rule to the ES wind column. Removing ES from M2, which the approved scope does not allow.
- Risk: The longest missing blocks are 13 to 17 February and 6 to 12 November 2026. The November block lies in the last 90 days of the data, which is the planned test window. The ES results that use the wind forecast must state how these days were handled.

## 20. The time functions refuse an index that is not UTC, sorted and unique
- Date: 2026-11-22
- Decision: `check_utc_index` in `src/epf/data/resolution.py` raises an error when the index of a series is not a time index in UTC, is not sorted from old to new, or holds a timestamp more than once. The price split and the covariate alignment call it first. It repairs nothing.
- Reason: A mean over an hour is wrong when a timestamp appears twice, and a local-time index has a repeated hour on the day the clocks go back. Stopping makes the problem visible. The repair belongs to the cleaning step, where each rule is documented.
- Alternative rejected: Sorting the index and dropping repeated timestamps inside the function. A bad download would then pass unnoticed.

## 21. The hourly price from 1 Oct 2025 is the mean of the four quarter-hours
- Date: 2026-11-22
- Decision: For experiment H, `hourly_prices` keeps the hourly prices before the switch unchanged. From delivery day 2025-10-01 the price of an hour is the plain mean of its four quarter-hour prices. An hour with fewer than four quarter-hour prices stays empty. Experiment Q uses the 15-minute prices from the switch on, unchanged (`quarter_hour_prices`).
- Reason: PROJECT_CONTEXT §4 sets the mean. It keeps one hourly series across the switch, and it is the price of a flat delivery over the hour. A mean of three values would look like a full hour and hide the gap, so the gap is left for the cleaning step.
- Alternatives rejected: The first quarter-hour of each hour, which drops three of four prices. A volume-weighted mean, which needs traded volumes that are not downloaded. A mean of the quarter-hours that are present.

## 22. Covariates are aligned per hour: mean to the hourly grid, repetition to the 15-minute grid
- Date: 2026-11-22
- Decision: `align_to_hours` and `align_to_quarter_hours` apply one rule per column and per UTC hour. To the hourly grid: an hour with one value at minute 0 keeps that value, an hour with four quarter-hour values gets their mean, and any other hour stays empty. To the 15-minute grid: an hour with one value at minute 0 has that value repeated on its four quarter-hours, and every other value stays at its own time.
- Reason: The load, wind and solar values are mean power in MW over their interval. The mean of four quarter-hour values is therefore the hourly value, and an hourly value holds for each of its quarter-hours. In the raw forecast files of 2026-11-21, every hour with data held either one value at minute 0 or four values, in every zone and column. Some zones change from hourly to 15-minute inside a year, so the rule is applied per hour and not per file.
- Alternatives rejected: Linear interpolation between hourly values, which invents a shape inside the hour that the forecast does not contain. A mean of the values present in a partly filled hour, which hides the gap. One resolution per file, which fails for the years that change resolution.

## 23. The hourly coverage check lives beside the forecast downloader
- Date: 2026-11-22
- Decision: `hourly_coverage` moves from `coverage_gate.py` to `download_forecasts.py`, and `native_resolution` moves to `market_time.py`. The gate module imports both. Nothing in their behaviour changes.
- Reason: The forecast downloader needs the same counts for its own printed summary. This is the layout the prices already have: `check_prices` is in `download_prices.py` and the gate imports it.
- Alternative rejected: Importing the check from the gate module. The gate module already imports the fetch functions from the downloader, so the two modules would import each other.

## 24. Actual load is its own raw dataset
- Date: 2026-11-22
- Decision: The actual total load is downloaded with `EntsoePandasClient.query_load` and saved as the dataset `actual_load`, one file per zone and year, through the same cache and the same printed counts as the forecasts. The code is in `src/epf/data/download_actual_load.py`.
- Reason: The load forecast files are already in the cache and keep their name and content. Actual load also follows a different rule from the forecasts: a model input may use it through D-2 only (PROJECT_CONTEXT §5). A separate dataset keeps that visible.
- Alternative rejected: `query_load_and_forecast`, which returns the forecast and the actual load joined in one frame. It would download the load forecast a second time and put a leakage-sensitive column next to a safe one.

## 25. Weather forecasts come from the Open-Meteo Single Runs API
- Date: 2026-11-22, approved by the owner
- Decision: Weather inputs are downloaded from `https://single-runs-api.open-meteo.com/v1/forecast`. Each request names one model run by its initialisation time (`run=`). For delivery day D the download keeps the hours of D and stores the run time next to every value, in the column `run`. Raw files are `data/raw/open_meteo/weather_forecast/{ZONE}_{YEAR}.parquet`, through the same cache code as the ENTSO-E downloads.
- Reason: The leakage rule needs forecasts with a known issue time. This endpoint is the only one in the Open-Meteo docs that returns a run by its initialisation time. Storing the run time lets the backtest check each value against the forecast cutoff.
- Alternatives rejected: The Historical Forecast API, which stitches the first hours of each run into one series, so a value has no usable issue time and is close to an analysis. The Previous Runs API, which only gives "the value predicted 24 hours before valid time" and does not state the run. The reanalysis archive, which is not a forecast.
- Limit: Only the hours of delivery day D are kept from each run, about 24 of 48 downloaded hours. A request for a run that is not in the archive adds no rows, and the hours are counted as missing.

## 26. ECMWF IFS HRES, the 00:00 UTC run of day D-1, four variables
- Date: 2026-11-22, approved by the owner
- Decision: The model is ECMWF IFS HRES at 9 km (`models=ecmwf_ifs`). For delivery day D the run of day D-1 at 00:00 UTC is used. The variables are `temperature_2m`, `wind_speed_10m`, `wind_speed_100m` and `shortwave_radiation`, with wind speed in m/s. The first run is 2024-03-14, so the first delivery day with weather is 2024-03-15.
- Reason: The Open-Meteo docs give this model an archive from 14 March 2024 and every other model one from 2 April 2026. The docs state that a 00 UTC run is available from about 04 to 06 UTC. Gate closure at 12:00 CET is 11:00 UTC in winter and 10:00 UTC in summer, so the run is known at the forecast origin. The hours of D are 22 to 47 hours after the run, inside the model's hourly range of 90 hours.
- Alternatives rejected: The 18:00 UTC run of D-2, which is safer on timing but six hours older. The 06:00 UTC run of D-1, which the docs make available at about 10 to 12 UTC, too close to gate closure. Wind at 100 m only: the owner chose to keep the 10 m wind as well.
- Limits: Availability before gate closure is taken from the docs, not measured. The docs call the archive from March 2024 "IFS Cycle 49R1 hindcasts", so the early runs may be re-run forecasts and not the ones issued at the time. A request for the run of 2024-03-13 was refused as not available.

## 27. One weather point per zone
- Date: 2026-11-22, approved by the owner
- Decision: Each zone has one `weather_point` in the config, and the forecast of the model grid cell at that point stands for the zone. DE_LU: Kassel (51.32, 9.50). FR: Paris (48.86, 2.35). ES: Madrid (40.42, -3.70). SE_1: Luleå (65.58, 22.15). SE_2: Sundsvall (62.40, 17.32). SE_3: Stockholm (59.33, 18.07). SE_4: Malmö (55.60, 13.01). Coordinates are from Wikipedia, rounded to two decimals.
- Reason: One point per zone is one config entry and one rule for all seven zones. Paris and Madrid are the largest demand centres. Kassel is near the centre of Germany, between the wind in the north and the solar in the south. The four Swedish price areas are named after these four cities.
- Alternative rejected: Several points per zone with an average. It fits a large zone better, but it needs more requests and an averaging rule to defend.
- Limit: One point cannot stand for the weather of a whole zone. This is weakest for DE_LU.
