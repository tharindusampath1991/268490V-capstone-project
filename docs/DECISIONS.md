# Decisions

Numbered entries: decision, reason, alternative rejected, date.

## 1. Add SE1–SE4 as extra zones in M2
- Date: 2026-11-19
- Decision: SE1, SE2, SE3 and SE4 are added as extra zones in Milestone 2, next to the three core zones approved in Milestone 1. They use the same pipeline through config entries, with no zone-specific tuning or features.
- Reason: To extend the scope a little beyond the three approved zones. A zone is added through a config entry and runs through the same pipeline, so the Swedish zones add no technical difficulty.
- Alternatives rejected: SE3 only. Sweden after M2.
- Risks: Milestone 1 was approved with 3 zones. Seven zones with 14 days to M2.
- Update, 2026-11-24: SE1 to SE4 are core zones from this day (entry 59). The sentence "with no zone-specific tuning or features" now means one setting per model for all seven zones.

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
- Update, 2026-11-24: The code imports numpy from this day on, first in `src/epf/seed.py` (entry 57). The pin stays for the reason above.
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
- Added 2026-11-22, after the actual load pull: the actual load has 8 partly filled hours, 2 in FR and 6 in ES (DATA_NOTES, "Actual load"). They stay empty on the hourly grid.

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
- Reason: The Open-Meteo docs give this model an archive from 14 March 2024 and every other model one from 2 April 2026. The docs state that a 00 UTC run is available from about 04 to 06 UTC. Gate closure at 12:00 CET is 11:00 UTC in winter and 10:00 UTC in summer, so the run is known at the forecast origin. The hours of D start 22 to 46 hours after the run, inside the model's hourly range of 90 hours.
- Alternatives rejected: The 18:00 UTC run of D-2, which is safer on timing but six hours older. The 06:00 UTC run of D-1, which the docs make available at about 10 to 12 UTC, too close to gate closure. Wind at 100 m only: the owner chose to keep the 10 m wind as well.
- Limits: Availability before gate closure is taken from the docs, not measured. The docs call the archive from March 2024 "IFS Cycle 49R1 hindcasts", so the early runs may be re-run forecasts and not the ones issued at the time. A request for the run of 2024-03-13 was refused as not available.

## 27. One weather point per zone
- Date: 2026-11-22, approved by the owner
- Decision: Each zone has one `weather_point` in the config, and the forecast of the model grid cell at that point stands for the zone. DE_LU: Kassel (51.32, 9.50). FR: Paris (48.86, 2.35). ES: Madrid (40.42, -3.70). SE_1: Luleå (65.58, 22.15). SE_2: Sundsvall (62.40, 17.32). SE_3: Stockholm (59.33, 18.07). SE_4: Malmö (55.60, 13.01). Coordinates are from Wikipedia, rounded to two decimals.
- Reason: One point per zone is one config entry and one rule for all seven zones. Paris and Madrid are the largest demand centres. Kassel is near the centre of Germany, between the wind in the north and the solar in the south. The four Swedish price areas are named after these four cities.
- Alternative rejected: Several points per zone with an average. It fits a large zone better, but it needs more requests and an averaging rule to defend.
- Limit: One point cannot stand for the weather of a whole zone. This is weakest for DE_LU.

## 28. A dropped Open-Meteo connection is asked again, up to three attempts
- Date: 2026-11-22
- Decision: When a weather request ends in a connection error or a timeout, the downloader waits 10 seconds and asks again, at most 3 attempts per request. An error answer from the API is never retried. Both numbers are in the config.
- Reason: The first full run stopped after one minute with a connection error. A test of 49 requests one second apart had one connection reset by the remote host, and the same request then answered normally four times. The download needs about 6,900 requests, and a zone and year is saved only when all its requests succeed.
- Alternatives rejected: No retry, which loses up to a year of requests on each reset. Retrying error answers too, which would hide a refused request or a rate limit.

## 29. `DATA_END` is 2026-11-19, with validation from 2026-06-23 and test from 2026-08-22
- Date: 2026-11-24, decided by the owner
- Decision: `data.end` is frozen at delivery day 2026-11-19. The test set is the last 90 delivery days, 2026-08-22 to 2026-11-19. The validation set is the 60 days before, 2026-06-23 to 2026-08-21. Train is the rest: 2019-01-01 to 2026-06-22 for experiment H (2730 days), 2025-10-01 to 2026-06-22 for experiment Q (265 days) and 2024-03-15 to 2026-06-22 for the weather sub-experiment (830 days). The two lengths are in the config as `splits.test_days` and `splits.validation_days`, and `split_starts` in `src/epf/data/market_time.py` computes the two dates. A test checks the dates in the config against it. The three values are never moved.
- Reason: 2026-11-19 is the last delivery day with every price in every zone and no hole before it. ENTSO-E has no DE_LU price for 2026-11-20 and 2026-11-21 and no FR price for 2026-11-21 in the series this project uses. It was asked six times between 2026-11-23 02:55 and 2026-11-24 04:38 market time. The three zone-days stayed empty while the delivery days 22, 23 and 24 November were published.
- Alternatives rejected: Waiting longer, which had already blocked two plan rows. Filling the three zone-days by calculation, for example with the prices of seven days earlier, and freezing a later day: the price is the target and the days lie in the test set, so the models would be scored against invented values. Filling DE_LU from Energy-Charts, which reverses entry 7 and leaves the FR day empty. Freezing a later day with the three zone-days left empty, which gives every model a broken price history for a gain of three or four days.
- Note: The 25-hour day 2026-10-25 lies in the test set.

## 30. The cleaning step leaves every gap empty
- Date: 2026-11-23, rules approved by the owner
- Decision: Inside the data period the cleaning step fills no value, clips none and removes no day. A forecast, load or weather value that is empty or missing in the raw files is empty in the processed tables. Rows after `DATA_END` are removed. Negative prices and spikes stay. The approved cleaning rules and their counts are in DATA_NOTES, "Preprocessing". This settles the point left open in entry 19: the ES days without a wind forecast stay empty.
- Reason: No value is invented, and no rule uses information from after the forecast origin. Whether a model fills an empty input is a modelling choice. It belongs to the feature builder, where it is tested against the leakage cutoff.
- Alternatives rejected: Filling a forecast from the day before or from seven days earlier. Interpolating between neighbouring hours or days, which uses later values. Dropping the delivery days with a gap, which breaks the daily series. For the weather day 2026-06-24, taking the model run of D-2, which needs a new download rule.
- Risk: 7 of the 90 ES test days, 6 to 12 November 2026, have no wind and no solar forecast. Results for ES that use these inputs must say so.

## 31. The cleaning step refuses bad data and repairs nothing
- Date: 2026-11-23
- Decision: `clean_zone` in `src/epf/data/clean.py` stops with an error when a raw file has a repeated timestamp, an index that is not UTC or not sorted, a timestamp that is not on the time grid, a column without a name in `ENTSOE_NAMES`, or a saved query that does not cover the data period. For prices it also stops when a market time unit has no price.
- Reason: The price is the target, so the period must hold exactly one price per market time unit (PROJECT_CONTEXT §3). Picking one of two values, or passing over a missing price, would hide a bad download. This is the repair step that entry 20 left to the cleaning, and the rule chosen is to refuse.
- Alternative rejected: Keeping the first or the last of repeated values and reporting the count. No raw file has a repeated timestamp, so the rule would only ever act on a download that went wrong.

## 32. The forecast columns the gate marks drop are listed in the config
- Date: 2026-11-23
- Decision: `coverage_gate.drop_columns` in the config lists FR `Wind Offshore` and `Solar` for SE_1 to SE_4. The cleaning step leaves these columns out. The list must equal the drop marks in `docs/coverage_gate.md`, and it is compared with the report after each gate run.
- Reason: The gate wrote its marks only into a Markdown report, which code cannot read. Both columns fail on training years alone: FR has no offshore forecast before 2023 and Sweden no solar forecast in 2019 and 2020. So the choice does not depend on validation or test data.
- Alternatives rejected: Computing the marks again inside the build, which runs the gate rule in a second place and over the validation and test period. Reading the marks out of the Markdown report.

## 33. Three processed tables per zone, with the weather in its own table
- Date: 2026-11-23, layout approved by the owner
- Decision: `python -m epf.data.build_dataset` writes `data/processed/hourly/{ZONE}.parquet` for experiment H, `data/processed/quarter_hour/{ZONE}.parquet` for experiment Q and `data/processed/weather/{ZONE}.parquet`. Each table has a UTC index with a row for every time step of its period, also where all values are empty. The columns are `price`, `load_forecast`, `wind_onshore_forecast`, `wind_offshore_forecast`, `solar_forecast` and `actual_load`, minus the columns a zone does not have. The weather table keeps the four variables as downloaded and the run time in `run`.
- Reason: One file per zone and experiment is what a model reads. A full time grid makes a gap visible as an empty value and lets the validation count it. Weather starts in March 2024, so inside the main tables its columns would be empty for five years. Weather is hourly and kept off the 15-minute grid, because repeating or interpolating it is a feature choice, not a cleaning rule.
- Alternatives rejected: Weather columns inside the main tables. One long table for all zones. The ENTSO-E column names, which contain spaces and do not say that a column is a forecast.
- Limits: `actual_load` stands at its own delivery time. A forecast for day D may use it through D-2 only, and the feature builder applies that cut. `shortwave_radiation` is the mean of the hour before its timestamp, while the ENTSO-E values apply from their timestamp on. The feature builder must line them up.

## 34. The validation compares each column with an approved number of empty values
- Date: 2026-11-23, approved by the owner
- Decision: `config/approved_gaps.yaml` holds, per zone, table and column, the number of empty values that was approved with the cleaning rules. `validate.py` fails when a table has other columns or when a count differs in either direction. It also checks the index against the time grid, the length of every delivery day and the last delivery day.
- Reason: The snapshot is frozen. If a later download changes how many values exist, the build stops and the change is looked at before any model sees it. The same file gives the expected columns per zone.
- Alternatives rejected: A threshold such as "at most 1% empty", which lets a new gap pass. A list of every empty timestamp, which is exact but several thousand lines long.
- Limit: A count notices a changed number of gaps. It does not notice a gap that moves to another hour while the count stays the same.
- Changed on 2026-11-24, approved by the owner: the counts of ES `actual_load` went from 41 to 40 in the hourly table and from 4 to 3 in the 15-minute table. The download to `DATA_END` brought the missing quarter-hour of 2026-11-17 05:00 UTC, and the validation stopped the first build on that difference. No other count changed.

## 35. The validate and build commands take the config as an argument
- Date: 2026-11-23
- Decision: `validate.py` and `build_dataset.py` each have a function `run(config)`, and `main()` only calls it with the project config. A path in the config may be absolute.
- Reason: A test can run the whole command on a temporary folder with a small config, including the exit with an error. The older download commands read the config inside `main()` and have no such test.
- Alternative rejected: Replacing `load_config` in the tests with `monkeypatch`. The existing tests pass their dependencies as arguments.

## 36. One loader cuts a table to the train set, at 00:00 market time on `splits.validation_start`
- Date: 2026-11-24, layout approved by the owner
- Decision: `src/epf/data/splits.py` holds `train_cut`, `keep_train` and `load_train`. `load_train` reads a processed table and keeps the rows before 00:00 Europe/Berlin on `splits.validation_start`, which is 2026-06-22 22:00 UTC. The EDA reads its data only through this loader.
- Reason: The split is defined in delivery days and the tables have a UTC index. One tested function keeps the two apart, and the backtest will need the same cut. A test checks that no row at or after the cut is returned, on the hourly and on the 15-minute table.
- Alternatives rejected: A date filter written again in each notebook or figure function. A cut at midnight UTC, which would read the first two hours of delivery day 2026-06-23 as train.

## 37. The EDA code lives in `src/epf/eda/` and the notebook calls it
- Date: 2026-11-24, layout approved by the owner
- Decision: `price_stats.py` computes the numbers, `price_plots.py` draws them, and `python -m epf.eda.price_figures` prints the numbers and writes the figures to `reports/figures/` (`paths.figures` in the config). Each figure function returns its tables and its figure. `notebooks/01_eda_prices.ipynb` calls the same functions without a path, so it writes no PNG file. It is run with nbconvert and committed with outputs. EDA 1 covers the core zones, taken from the config by `group: core`, on the hourly table, with train days only. The folder `src/epf/eda/` is new. The layout in PROJECT_CONTEXT §8 now lists it.
- Reason: Every number has a test on a synthetic frame. The command and the notebook print the same tables, so each number in a finding can be traced to code. Figures come from a command, as CLAUDE.md requires.
- Alternative rejected: The analysis code inside the notebook. It cannot be tested, and the figures would exist only after a notebook run.
- Update, 2026-11-24: The core group holds seven zones from this day, so EDA 1 covers SE_1 to SE_4 too (entries 59 and 60).

## 38. A spike is a price above the mean plus 3 standard deviations of the 28 days before it
- Date: 2026-11-24, approved by the owner
- Decision: An hour is a spike when its price is above the mean of the 672 hourly prices before it plus 3 times their sample standard deviation. Only upward spikes count. Negative prices are counted on their own. The two numbers are in the config as `eda.spike_window_days` and `eda.spike_sd`. They are conventions and were not tuned. The functions are `spike_threshold` and `spike_flags` in `src/epf/eda/price_stats.py`.
- Reason: Each hour is judged only on hours before it, so every threshold comes from train data and the rule follows the price level. 28 days are four full weeks, so every weekday and hour has the same weight in the window. On the train set the rule flags 486 hours in DE_LU, 493 in FR and 305 in ES, between 0.47% and 0.76% of the 64847 judged hours. DE_LU has 101 spike hours in 2022 and 89 and 100 in 2024 and 2025.
- Alternatives rejected: One fixed threshold per zone at the 99% quantile of the train prices. It marks the crisis years and not spikes: 619 of its 656 DE_LU hours and 642 of its 654 FR hours fall in 2022, and all 656 ES hours fall in 2021 and 2022. The same rolling rule with median and MAD, which flags 393 ES hours in 2024 at 5 MADs.
- Limits: The first 672 hours of 2019 have no full window and are not judged. A window that holds an empty price gives no threshold. After a run of very high prices the standard deviation is large, so the hours that follow are judged less strictly. The flag describes the data. It is not a model input.

## 39. The hour and weekday figures show the median and the quartiles, in market time
- Date: 2026-11-24, figures approved by the owner
- Decision: `hour_profile` and `weekday_profile` give the median and the 25% and 75% quantiles per hour of day and per weekday in Europe/Berlin. On a 25-hour day both hours 2 count under hour 2, and a 23-hour day has no hour 2. The year and month figure shows the mean. The histograms of the three zones share one price range, the 0.1% and 99.9% quantiles of the train prices of all core zones together, and the command prints how many hours lie outside it.
- Reason: The tails are long. FR has a maximum of 2987.78 EUR/MWh against a 99% quantile of 510.00, and a mean per hour would follow such values. The daily pattern belongs to the local clock, which is also how delivery days are defined. A monthly mean is the usual way to state a price level.
- Alternatives rejected: Mean and standard deviation per hour. Profiles by UTC hour, which shift by one hour between winter and summer. A histogram over the full range, where most of the axis would be empty: only 137 DE_LU hours lie below the shared range and 75 above.
- Update, 2026-11-24: With seven core zones the shared range is -33.77 to 629.38, and 288 DE_LU hours lie below it and 135 above (entry 60). The numbers above are those of the three zones DE_LU, FR and ES.

## 40. matplotlib and seaborn draw the figures, and nbconvert and ipykernel are pinned without being imported
- Date: 2026-11-24, packages approved by the owner
- Decision: `requirements.txt` pins matplotlib 3.11.2, seaborn 0.13.2, nbconvert 7.17.2 and ipykernel 7.4.0. The code imports the first two. seaborn draws the heatmap only. nbconvert and ipykernel are not imported. They run the notebook from the command line, and each has a comment that says so, as pyarrow has (entry 3). The 44 packages they bring in stay unpinned, as entry 3 rules for indirect dependencies.
- Reason: A fresh clone must be able to run the notebook with one install step. The install changed no existing pin, checked with a dry run first.
- Alternative rejected: A second requirements file for the notebook tools, which adds an install step to the README for four lines.

## 41. The month panels of the spike and negative price figures show the mean per year
- Date: 2026-11-24, decided by the owner
- Decision: In `eda1_spikes.png` and `eda1_negative_prices.png` the month panel shows the flagged hours of a month divided by the number of years in which that month has a judged hour. The function is `month_means` in `src/epf/eda/price_stats.py`. The command still prints the raw count per month and the number of years beside the mean. The year panel and the hour panel show counts.
- Reason: The train set ends on 2026-06-22. January to June occur in eight years and July to December in seven, so a raw count favours the first half of the year. In DE_LU the negative hours of May are 416 in eight years, a mean of 52.00, and those of December 177 in seven years, a mean of 25.29.
- Alternative rejected: The raw count per month with a note under the figure. It matches the printed counts one to one, but the months cannot be compared.
- Limit: A month that is only partly in the data counts as one year. June 2026 ends on the 22nd, and for spikes January 2019 is judged only after its first 28 days. The means of June and of January are therefore slightly low.

## 42. Residual load is the load forecast minus the wind and the solar forecast
- Date: 2026-11-24, approved by the owner
- Decision: `driver_table` in `src/epf/eda/driver_stats.py` gives the residual load as `load_forecast` minus the wind forecast minus `solar_forecast`, in MW. The wind forecast is onshore plus offshore where the table has an offshore column. Solar is subtracted where the table has the column. The function reads which columns exist and holds no zone name. An hour in which one input is empty has no residual load. It is left out of every comparison that needs it, and the command prints the count. EDA 2 does not use `actual_load`.
- Reason: The residual load is what plants other than wind and solar must cover, so it should explain the price better than one forecast. On the train set its rank correlation with the price is 0.52 in DE_LU, 0.39 in FR and 0.41 in ES, against 0.21, 0.27 and 0.20 for the load forecast alone. All three inputs are day-ahead forecasts, so the comparison keeps to the leakage rule (PROJECT_CONTEXT §5).
- Alternatives rejected: Counting an empty wind or solar forecast as zero, which overstates the residual load on the gap days and breaks entry 30. `actual_load` of the delivery day, which is not known at the forecast origin.
- Limits: 51 train hours are left out in DE_LU, 480 in FR and 505 in ES. The ES hours hold 99 of its 1428 negative hours. FR has no offshore wind column and the Swedish zones have no solar forecast (entry 32), so the Swedish residual load is the load forecast minus the wind forecast.

## 43. The rank correlation is the Pearson correlation of the ranks, computed with pandas
- Date: 2026-11-24, approved by the owner
- Decision: `rank_correlation` ranks both series with pandas `rank()` and takes their correlation with `corr()`, over the hours in which both have a value. It returns the hours used and the hours left out. The command prints it for the whole train period and per year.
- Reason: The price rises with the residual load along a curve and has a long upper tail. A rank correlation asks only whether the price rises when the input rises. The yearly numbers are needed beside the total: DE_LU has 0.82 to 0.91 in every year except 2021 and 2022, against 0.52 for the whole period, because the price level moved between years.
- Alternatives rejected: `corr(method="spearman")`, which needs scipy. It raised `ModuleNotFoundError: No module named 'scipy'` on 2026-11-24, and scipy is not an approved dependency. The Pearson correlation of the raw prices, which the prices of 2022 would dominate.

## 44. Dense comparisons use every hour: a 2D histogram and medians in bins of equal count
- Date: 2026-11-24, approved by the owner
- Decision: The price against an input is drawn from every train hour, as counts in a grid of 50 by 50 cells on a logarithmic colour scale, with the median price in `eda.median_bins` (20) bins as a line. Negative prices and spikes are counted in `eda.share_bins` (10) bins of the residual load. Delivery days are sorted into `eda.solar_day_groups` (3) groups by the sum of their solar forecast. `bin_numbers` takes the bin edges from the quantiles of the train values of the zone, so the bins hold about the same number of values. Equal edges are merged. No hour is sampled.
- Reason: 65519 points per panel hide each other in a scatter plot, and a random sample would make the figure depend on a seed. Bins by quantile hold enough hours everywhere and read the same way in zones of different size.
- Alternatives rejected: A scatter plot of a random sample. Bins with fixed MW edges, which cannot be shared between zones.
- Limits: Many hours have a solar forecast of zero, so the lowest solar bins merge: DE_LU has 12 bins and FR 11 instead of 20. The price range of the panels is the shared range of EDA 1 (entry 39), -55.64 to 678.27. The spike share of a bin is taken over all its hours, also the first 672 hours that the spike rule does not judge. A day with an empty solar hour is left out of the solar groups: 3 days in DE_LU, 22 in FR and 8 in ES.
- Update, 2026-11-24: The price range of the panels is now -33.77 to 629.38 (entry 60). The Swedish zones have no solar forecast, so they are not in the solar groups.

## 45. The high-price period is 2021-09 to 2022-12, from one rule on the monthly mean of the core zones
- Date: 2026-11-24, approved by the owner
- Decision: `high_price_period` takes the mean price per month in each core zone and averages the three. A month is high when this value is above `eda.regime_factor` (2) times its median over the train months. The period runs from the first to the last high month and is the same for the three zones. On the train set the median is 68.62, the threshold 137.24 and the period 2021-09 to 2022-12: 16 months, all of them high. The factor is a convention and was not tuned.
- Reason: The rule uses train prices only and gives one period, so the three zones are compared on the same months. It puts the start in autumn 2021, when prices were already far above the earlier level.
- Alternatives rejected: Calendar year 2022, which leaves out the last months of 2021. The DE_LU monthly mean was about 221 in December 2021. One period per zone by the same rule, which gave three different periods and marked FR months up to February 2025.
- Limits: The end is a close call. February 2023 has 136.85, just under the threshold. June 2026 counts as a month although the train set ends on the 22nd. The period describes the data. It is not a model input, and no fuel price is in scope to explain it.
- Update, 2026-11-24: The rule now averages the seven core zones. It gives the same period, 2021-09 to 2022-12, with a median of 50.80 and a threshold of 101.60. 15 of the 16 months are above the threshold. The end is no longer a close call: the highest month outside is February 2023 with 95.55 (entry 60).

## 46. A holiday is a nationwide public holiday, and regional holidays are measured, not used
- Date: 2026-11-24, approved by the owner, who chose the second of three options for regional holidays
- Decision: A holiday is a nationwide public holiday of the zone's `holiday_country` from `holidays` 0.109, without a subdivision, on the delivery day. Each zone names its categories in the new config key `holiday_categories`: `public` for the core zones, `public` plus `de_facto` for the Swedish zones (PROJECT_CONTEXT §3). `src/epf/features/holiday_calendar.py` is the only module that calls the package. Days are compared in four types: working day, holiday on Monday to Friday, Saturday and Sunday. A holiday on a Saturday or Sunday counts as that weekend day. Beside the plain medians the command prints a number corrected for season: the daily mean price of each holiday minus the median daily mean of the working days within `eda.holiday_window_days` (7) days before and after it. Regional holidays count as working days, and the command prints how many days that is and what the price did on them.
- Reason: A national calendar needs no data beyond the package. The corrected number is needed because holidays cluster in spring and in December. It is -20.24 EUR/MWh in DE_LU, -16.91 in FR and -11.18 in ES. Measuring the regional days turns a stated limit into a number. The calendar module is under `features/` because the LightGBM feature builder needs the same dates.
- Alternatives rejected: Holidays against all other days, which puts weekends on both sides. A national calendar with the limit stated in words only. A regional measure such as the share of the population that has a holiday: the calls used here return dates and names only, so population would be a new data source outside the locked scope, and the subdivision lists of the package are not the regions of the bidding zones.
- Limits: Regional holidays on Monday to Friday are 53 train days in DE_LU, 94 in FR and 186 in ES, which is 2.80%, 4.99% and 9.82% of the working days. With these days taken out of the working days the corrected difference is -20.24, -17.48 and -11.61. The package lists the city of Augsburg beside the German states, and for FR mostly overseas territories. The holidays of Luxembourg are not counted for DE_LU. A day on which a holiday is observed in lieu counts, which is the default of the package. `eda.regional_share_edges` (0.25 and 0.5) only groups the regional days in one printed table. It was not in the approved proposal and came with the regional table.

## 47. The spread inside an hour is the highest minus the lowest quarter-hour price
- Date: 2026-11-24, approved by the owner
- Decision: `hour_spread` in `src/epf/eda/spread_stats.py` gives the highest minus the lowest of the four 15-minute prices of an hour, in EUR/MWh. `quarter_differences` gives each 15-minute price minus the mean of its hour. An hour with fewer than four prices has neither. Both are shown per hour of day in market time, on the 15-minute table (experiment Q), for the train days 2025-10-01 to 2026-06-22.
- Reason: Experiment H uses the mean of the four prices (entry 21). The range says in EUR what that mean hides, and the differences show that the prices inside an hour run in one direction. The median spread is 13.98 in DE_LU, 14.63 in FR and 6.00 in ES. All 6360 train hours per zone have four prices.
- Alternatives rejected: The standard deviation of four values, which is harder to read and says the same. The spread divided by the hourly mean, which breaks when the mean is near zero or negative.

## 48. The Sweden section compares each zone with the next, on exact equality and on relative levels
- Date: 2026-11-24, approved by the owner
- Decision: The four Swedish zones get one figure, `eda2_sweden_north_south.png`, and one notebook section, both labelled as extra zones. `sweden` in `src/epf/eda/driver_figures.py` takes the extra zones in the order of the config, which runs from north to south, and compares each zone with the next. Two zones are identical in an hour when their prices are exactly equal. Beside that share the command prints the median and the 95% quantile of the absolute difference, before and from `eda.nordic_flow_based_start` (2024-10-30). Levels are drawn as the yearly mean divided by the mean of the four zones, and the daily shape as the price divided by the mean price of the zone.
- Reason: PROJECT_CONTEXT §1 asks for one combined section and §3.1 for the share of identical SE_1 and SE_2 prices. Exact equality alone would mislead. SE_1 and SE_2 had the same price in 98.61% of the hours before 2024-10-30 and in 3.41% from that day, yet their median absolute difference from that day is 1.23 EUR/MWh.
- Alternatives rejected: A tolerance such as 1 EUR/MWh as the meaning of identical, which is one more threshold to defend. A figure of the price levels in EUR side by side, since the levels differ several-fold (PROJECT_CONTEXT §7).
- Limits: No holiday, high-price period or 15-minute analysis for Sweden. The yearly ratio uses the plain mean of the four zones, not a Swedish price weighted by load.
- Update, 2026-11-24: The first limit is gone. Every section of EDA 2 covers the Swedish zones, except the solar section (entry 60). The figure is no longer labelled as extra zones, and `sweden` takes its zones from `eda.neighbour_zones` in the config instead of the extra group.

## 49. EDA 2 keeps the layout of EDA 1, and `holidays` is pinned without `python-dateutil`
- Date: 2026-11-24, layout and package approved by the owner
- Decision: EDA 2 follows entry 37. `driver_stats.py` and `spread_stats.py` compute the numbers, `driver_plots.py` draws them, and `python -m epf.eda.driver_figures` prints the numbers and writes seven `eda2_*.png` files. `notebooks/01_eda_drivers.ipynb` calls the same functions. `driver_plots.py` reuses the colours, `_panels` and `_finish` of `price_plots.py`. Lines of groups without an order use four colours in a fixed order. `requirements.txt` pins `holidays` 0.109. `python-dateutil` is not pinned.
- Reason: One layout for both parts of the EDA. `holidays` 0.109 requires `python-dateutil` below 3, so installing it moved the installed 4.0.0 to 2.9.0.post0, and a fresh install resolves to the same version. It is an indirect dependency (entry 3). The 268 tests, the build and the six EDA 1 figures gave the same result before and after the install.
- Alternative rejected: A pin for `python-dateutil`, as numpy has one. numpy is pinned because of a known warning (entry 3). No problem was seen here.
- Limits: The proposal named 300 lines as the size at which `driver_stats.py` would be split. It reached 437. The 15-minute and two-zone functions moved to `spread_stats.py`, and `driver_stats.py` still has 349 lines. `driver_figures.py` reads `_period_note` of `price_figures.py`, a private helper, to avoid a copy.

## 50. The seasonal naive forecast is scored on validation and on test in the same session
- Date: 2026-11-24, decided by the owner
- Decision: `python -m epf.evaluation.backtest --model naive --split validation` and the same command with `--split test` were each run once on 2026-11-24, the test run after the validation results were committed. No other model has seen the test days. No rule and no metric was changed after the test run.
- Reason: The naive forecast has no tuned parameter, so its test score cannot be improved by looking at it. Every later model needs its MAE on the test days as the reference for relative MAE.
- Alternative rejected: Keeping the test days closed until the final backtest of all models. The reference would then be computed in the same run as the models it judges, and a harness bug on the 25-hour day 2026-10-25 would show only at the end.
- Limit: The numbers of the test run are known from now on. They must not steer any later choice.

## 51. A model receives the inputs of one delivery day, cut at three midnights in market time
- Date: 2026-11-24, proposal approved by the owner
- Decision: `day_inputs` in `src/epf/evaluation/cutoff.py` cuts a table for delivery day D into a `DayInputs` object. The price ends before 00:00 Europe/Berlin on D. The day-ahead columns (load, wind and solar forecast) end before 00:00 on D+1. The delayed column `actual_load` ends before 00:00 on D-1. Each midnight is built from a calendar date, not by subtracting 24 hours. The config lists the columns under each cut (`backtest.price_column`, `day_ahead_columns`, `delayed_columns`), and a table column that is listed nowhere stops the run. The market time units of D come from `hourly_index` or `quarter_hour_index`, not from the table. A model has `fit(inputs)` and `predict(inputs)`. `run_days` in `backtest.py` refuses a forecast that is not on exactly those market time units, and sets the actual prices beside the forecast only after the model has answered. A validation run drops every row from `splits.test_start` on when it reads the table.
- Reason: PROJECT_CONTEXT §5. The model holds copies that end at the cuts, so data after a cut cannot be reached, whatever the model does. The whole rule is one file of about 100 lines.
- Tests: A recording model shows that nothing it receives in `fit` or `predict` lies after its cut, on days around the 25-hour day, hourly and 15-minute. A model that sums every value it receives gives the same forecast after every value behind the three cuts is changed, and another forecast when the last value before a cut is changed. A model that overwrites its inputs changes neither the table nor the actual prices. Each cut was also moved on purpose once: 16 or 17 tests failed each time.
- Alternative rejected: One frame up to the end of D with the values a model may not see set to empty. It is handy for a feature builder, but a wrong mask then leaks silently, and "empty" would mean both "not known yet" and "a real gap".
- Assumption: The day-ahead wind and solar forecast is taken as known before the 12:00 gate closure, although ENTSO-E allows it until 18:00 on D-1 (PROJECT_CONTEXT §5). The naive forecast does not use these columns.
- Limits: Weather is not passed yet. `cutoff.py` is a file beyond the layout of the first plan. It is separate from `backtest.py` so that a model file can import `DayInputs` without a circular import.

## 52. The naive forecast takes the same wall-clock time 7 days before, and 168 hours back where that time is missing or double
- Date: 2026-11-24, proposal approved by the owner
- Decision: `seasonal_naive` in `src/epf/models/naive.py` gives each market time unit of D the price at the same wall-clock time in Europe/Berlin `models.naive.lag_days` (7) calendar days earlier. Where that wall-clock time does not exist on D-7 or exists twice, it takes the price exactly 168 hours before the target. On a 25-hour D both 02:00 hours take the 02:00 price of D-7. When D-7 has 25 hours, 02:00 takes its second 02:00 hour. On a 23-hour D the 02:00 price of D-7 is not used. When D-7 has 23 hours, 02:00 takes its 01:00 price. A market time unit whose source is not in the history gets an empty forecast, and a scored run with an empty forecast fails.
- Reason: PROJECT_CONTEXT §6 defines the model as the same local market time unit on D-7, and the daily price shape follows the local clock (entry 39). The test days hold both cases that matter: 2026-10-25 has 25 hours and 2026-11-01 has a D-7 of 25 hours. Every source lies on D-7, before the price cut of entry 51.
- Alternative rejected: Always 168 hours back in UTC. It needs no special case. But in the 7 days after a clock change it reads the price one local hour off, and for the last hour of 2026-10-25 it reads a price of D-6.
- Limit: `lag_days` is the definition of the model. It was not tuned.

## 53. Metrics are pooled over market time units, and the losses per delivery day are kept
- Date: 2026-11-24, proposal approved by the owner
- Decision: `src/epf/evaluation/metrics.py` has `mae`, `rmse`, `relative_mae`, `pinball_loss`, `mean_pinball_loss`, `coverage` and `daily_losses`. With e as the actual price minus the forecast, MAE is the mean of |e| and RMSE the root of the mean of e², each over all market time units of one zone, experiment and split. Relative MAE is the MAE of the model divided by the MAE of the naive forecast on the same market time units. The harness always runs the naive forecast on the same days for this. The pinball loss at level q is the mean of max(q·e, (q − 1)·e), and coverage is the share of actual prices inside an interval, bounds included. `daily_losses` gives per delivery day the number of market time units, the MAE and the MSE. An empty value or a forecast on other timestamps raises an error.
- Reason: Pooling gives every market time unit the same weight, and no metric divides by a price, which can be zero or negative. The daily losses are what the Diebold-Mariano test of M3 needs, and the pooled MAE can be recomputed from them.
- Alternative rejected: The mean of daily values. For MAE it differs only through the days of 23 or 25 hours. For RMSE it is another quantity.
- Limits: The naive forecast gives no quantiles, so pinball loss and coverage are tested but not yet in a results file. Relative MAE is not defined when the naive forecast has no error, and the function raises an error then.

## 54. Results are committed per zone group, and forecasts per market time unit stay out of git
- Date: 2026-11-24, proposal approved by the owner
- Decision: The backtest writes to `reports/results/` (`paths.results`). `backtest_core.csv` and `backtest_extra.csv` hold one row per run, zone and experiment, with the model settings, the split, the seed, the metrics, the wall-clock time, the peak memory, the hardware and the config dates. Rows are only added. `daily_core.csv` and `daily_extra.csv` hold the losses per delivery day, and a new run replaces the rows of the same model, experiment, split and zone. The file name ends with the `group` of the config, so the Swedish zones have their own tables and no zone name is in the code. The forecasts per market time unit go to `data/forecasts/{model}/{experiment}/{split}/{ZONE}.parquet` (`paths.forecasts`), with the actual price beside each forecast. That folder is not committed. The core files are written before the extra zones start. A failed check writes nothing for its zone group.
- Reason: The naive forecast is the ENTSO-E price of 7 days before, so a committed forecast file would be raw data in git, which CLAUDE.md forbids. The command writes the files again on any machine that has the processed tables. A log that only grows shows every run, also a second run on the test days.
- Alternative rejected: Replacing the row of an earlier run in the log as well. The file would always show one row per result, but a repeated test run would leave no trace.
- Correction, 2026-11-24: The first version read the saved files with the default pandas parser, which can return a number with another last digit. The test run therefore rewrote 273 saved validation cells, with a largest relative change of 8.0e-16. No printed number changed. The files are now read with `float_precision="round_trip"`, a test compares the saved lines as text, and the validation lines were restored from commit `762243f`. The test command was not run again. The body of commit `5cf0e37` says the validation rows were unchanged, which was wrong in the last digit.
- Limits: `results.py` is a file beyond the layout of the first plan. Error slices by hour or by spike need the forecast files, which exist only where the command has run.
- Update, 2026-11-24: All seven zones are in the core group, so there is one `backtest_core.csv` and one `daily_core.csv`. The two extra files were merged into them and removed (entry 61).

## 55. Run time is read with `perf_counter` and peak memory with psutil, which is now pinned
- Date: 2026-11-24, package approved by the owner
- Decision: `wall_seconds` is `time.perf_counter()` around the day loop of one zone and experiment: the cuts, `fit` and `predict`, without reading the table or writing results. `peak_memory_mb` is `psutil.Process().memory_info().peak_wset`, the highest working set of the process, read after the loop. `hardware` is one line built from `platform` and `psutil`. `requirements.txt` pins `psutil` 7.2.2. It was already installed as a dependency of `ipykernel`, and a dry run of the install reported it as already satisfied.
- Reason: The working set counts memory used by native code, so LightGBM and PyTorch will be measured the same way as the naive forecast. One readable line replaces about 20 lines of Windows API code.
- Alternatives rejected: `tracemalloc` of the standard library, which counts only memory that Python allocates and slows the run. The Windows API through `ctypes`.
- Limits: The peak never falls during one command, so the value of a row is the peak up to that zone. For the naive forecast it is mostly the imports: 138 to 161 MB. The field exists on Windows only. On another system the column is empty until a Linux reading is added and tested, which the Colab runs of M3 will need.

## 56. Refit cadence and history length are config values with the defaults of the forecast protocol
- Date: 2026-11-24, proposal approved by the owner
- Decision: `backtest.refit_every_days` is 7 and `backtest.history_days` is null, which means every row from the first one. `run_days` calls `fit` on the first scored day and then every 7th delivery day. Both values are written into every results row.
- Reason: These are the defaults of PROJECT_CONTEXT §5: a weekly refit on an expanding window. The naive forecast has nothing to fit, so neither value changes its result.
- Alternative rejected: Choosing a history length now. It can only be judged with a model that trains, on the validation days. That belongs to the SARIMA or ETS step, since the train set holds three price regimes (entry 45).
- Update, 2026-11-25: The history length is now a value of each model entry, and `backtest.history_days` is the value for an entry without one (entry 65). The statistical baseline uses 182 days (entry 64).

## 57. One helper sets the seed
- Date: 2026-11-24
- Decision: `set_seed` in `src/epf/seed.py` seeds the `random` module and the global numpy generator from `seed` in the config (42) and returns the seed. The backtest calls it at the start of a run and writes the seed into every results row. numpy is now imported by the code, so its note in `requirements.txt` says so and the exception of entry 3 has an update line.
- Reason: CLAUDE.md asks for seeds set through one helper. The naive forecast uses no random number, so the seed does not change its result.
- Limit: PyTorch is not seeded yet. That line is added with the first model that uses it.

## 58. The test days are open only to the models listed in the config
- Date: 2026-11-24, proposal approved by the owner
- Decision: `backtest.test_models` lists the models that may be scored with `--split test`. It holds `naive` only. The command refuses any other model there and writes nothing.
- Reason: CLAUDE.md says the test set is touched only by the final backtest. A list in the config makes opening the test days for a model a visible, logged change instead of a habit.
- Alternative rejected: Relying on the rule in words only.
- Limit: The list guards the backtest command. It does not stop other code from reading the processed tables, which hold the test days.
- Update, 2026-11-25: The list also holds `mstl_182`, the frozen statistical baseline (entries 64 and 67). The 14 candidates that lost are refused on the test days.

## 59. SE_1 to SE_4 are core zones
- Date: 2026-11-24, decided by the owner
- Decision: The four Swedish zones have `group: core` in the config, like DE_LU, FR and ES. Every analysis, model and results table covers all seven zones. Three earlier rules end with this. First, the EDA no longer gives Sweden one section only. Second, hyperparameters, history length and context lengths are chosen on the validation days of all seven zones, one setting per model, instead of on DE_LU, FR and ES alone. Third, Swedish work is no longer the first thing cut if M2 is at risk. The group in the config does not say what Milestone 1 approved: it approved DE_LU, FR and ES only, and README, CLAUDE.md, PROJECT_CONTEXT and both notebooks say so.
- Reason: The owner wants the Swedish zones analysed, tuned and reported to the same depth as the other three.
- Alternatives rejected by the owner: The same analysis for Sweden with the two groups kept, which would have left the existing figures, numbers and results files unchanged. Tuning on DE_LU, FR and ES only. Keeping the cut order.
- Risks: Milestone 1 was approved with 3 zones, and the supervisor has not been told (PROJECT_CONTEXT §11). M2 is assumed on 3 Dec 2026, SARIMA or ETS, LightGBM and the zero-shot models are still open, and no Swedish item can be cut any more. Validation runs take about 2.3 times as long as with three zones, by the estimate in PROJECT_CONTEXT §3.1. SE_1 and SE_2 are near-duplicates (entry 48), so seven zones are not seven independent results. The Swedish zones have no solar forecast (entry 32), so they enter the same tuning with one input fewer.
- Limit: "One setting per model" is how the tuning rule was written down from the owner's answer "tune on all seven". No setting per zone was asked for.

## 60. What changed in the EDA with seven core zones
- Date: 2026-11-24
- Decision: Both EDA commands and notebooks cover all seven zones. A figure with one panel per zone starts a new row after four zones (`MAX_COLUMNS` in `price_plots.py`). A figure with several panels per zone has one row per zone, where it had one column per zone before. The values that are pooled over the core zones now come from seven zones: the shared price range is -33.77 to 629.38 (entry 39), and the high-price period is still 2021-09 to 2022-12, with a threshold of 101.60 (entry 45). The solar section holds DE_LU, FR and ES only. The Sweden section stays as the comparison of the four zones with each other, and reads its zones from the new config key `eda.neighbour_zones`.
- Reason: Seven panels in one row gave a figure of 29 inches, which cannot be read in a notebook. One rule for the pooled values keeps every zone in the same figure on the same scale. `eda.neighbour_zones` keeps zone names out of the code now that no zone is in the extra group.
- Alternative rejected: A second set of figures for Sweden beside the unchanged figures of the three zones. It was the option the owner declined in entry 59.
- What the Swedish zones show, on the train days: The median price is 25.99 in SE_1, 26.29 in SE_2, 38.10 in SE_3 and 46.66 in SE_4. The spike rule of entry 38 flags 2.60%, 2.63%, 1.74% and 1.23% of the judged hours, against 0.47% to 0.76% in the other zones. Negative prices are 2.30% to 2.97% of the hours, with at most 29 a year up to 2022 and 368 to 434 in 2023. The rank correlation of the price with the residual load is 0.49, 0.56, 0.54 and 0.47. In the negative hours the wind forecast is a median of 89.99% of the load forecast in SE_1 and 162.38% in SE_2. The median spread inside an hour is 4.73, 4.65, 7.89 and 9.09. A holiday on a weekday is a median of 4.43 lower than the working days around it in SE_1 and SE_2 and about 11 lower in SE_3 and SE_4.
- Limits: The spike rule measures a jump against the last 28 days, so it flags more hours in zones with a low and quiet price. That is a guess at the cause, not a tested result. The solar guess of EDA 1 cannot be tested for Sweden. The Swedish holiday count depends on the categories `public` and `de_facto` (entry 46). The numbers of DE_LU, FR and ES are unchanged, except where a pooled value enters: the hours outside the shared price range and the threshold of the high-price period.

## 61. The Swedish naive results were moved into the core results files as text
- Date: 2026-11-24, approved by the owner
- Decision: The 16 lines of SE_1 to SE_4 in `backtest_extra.csv` and the 1200 lines in `daily_extra.csv` were copied into `backtest_core.csv` and `daily_core.csv` as text. In the 16 backtest lines the `group` cell changed from extra to core. No other cell changed, and no backtest was run again. The lines are in the order a run with seven core zones writes them. The two extra files were removed with `git rm`.
- Reason: From now on the backtest writes all seven zones to the core files. The naive forecast is the reference for relative MAE, so its Swedish rows must be in the same file as the models compared with it. The naive test run may not be repeated (entry 50).
- Alternatives rejected by the owner: Leaving the two files as they were, so that later tables read both. Running validation and test again, which would have been a second test run.
- Limits: The `group` cell of these 16 rows no longer shows the group the zones had when the runs were made. The run time stamp does: the runs are of 2026-11-24, before the change, and entry 59 gives the date. `docs/coverage_gate.md` still lists SE_1 to SE_4 as extra zones with a verdict. It is the report of 24 Nov 2026 and is not written again (PROJECT_CONTEXT §3.1).

## 62. `statsforecast` 2.1.1 is pinned, and the statistical models read the price history only
- Date: 2026-11-25, package approved by the owner after a dry run
- Decision: `requirements.txt` pins `statsforecast` 2.1.1. The install added 16 dependencies (adagio, cloudpickle, coreforecast, formulaic, fsspec, fugue, interface-meta, narwhals, patsy, scipy, statsmodels, threadpoolctl, tqdm, triad, utilsforecast, wrapt) and moved no existing pin. `StatsModel` in `src/epf/models/stats.py` wraps `AutoARIMA`, `AutoETS` and `MSTL` as one model of the backtest, set up from a config entry with a `family`. It reads `inputs.prices` and nothing else: no load, wind, solar or weather input, and no prediction interval. Season lengths are given in days (`season_days`) and multiplied by the market time units per day, which the model reads from the step of the target index. So one entry means 24 and 168 steps on the hourly table and 96 and 672 on the 15-minute table. No Box-Cox argument is set, and the code refuses `blambda` and `biasadj`. Every ETS form has the error `A`, and the code refuses any other form. The trend model inside MSTL is `AutoETS(model="AZN")`, not the default `ZZN`.
- Reason: PROJECT_CONTEXT §6 names `statsforecast` for the statistical baseline. Prices go negative, so no transform and no multiplicative form may be used. The installed source shows that with the error `A` every multiplicative trend and season is skipped. The defaults `ZZZ` and `ZZN` leave the multiplicative error to the data: it is skipped only when the window holds a price of zero or below.
- Alternative rejected: The default forms. A window with positive prices only could then get a multiplicative model, and the form would differ between zones and weeks for a reason that has nothing to do with the forecast.
- Limits: `statsforecast` counts steps, not clock hours. After a clock change the daily pattern sits one step off until the model has adapted. The validation days hold no clock change. The test days hold 2026-10-25. `approximation=True` makes the ARIMA search faster, but it printed 243 "possible convergence problem" warnings in six timed fits on train days and is not used.

## 63. Between two weekly fits the fitted model is applied to the newest prices with `forward`
- Date: 2026-11-25, proposal approved by the owner
- Decision: `fit` is called on the first scored day and then every 7th delivery day (`backtest.refit_every_days`, entry 56). It receives the `history_days` calendar days of prices that end at the price cut of that day. On every delivery day `predict` calls `forward(y, h)` of `statsforecast` with the window that ends at the price cut of that day. `h` is the number of market time units of D: 23, 24 or 25 hours, or 92, 96 or 100 quarter-hours. The installed source shows what `forward` keeps. For ARIMA it keeps the orders and passes the coefficients as fixed values. For ETS it keeps the form, the smoothing parameters and the initial state. For MSTL it decomposes the window again and keeps only the fitted trend model.
- Reason: PROJECT_CONTEXT §5 sets a weekly refit. The price of D-1 is known when D is forecast, and `forward` is the way to use it without estimating again. The `cross_validation` of the library does the same with a whole number as `refit`. Its documentation says: "If False, fits once and uses the forward method. If an integer n, refits every n windows. Models must implement the `forward` method when refit is not True." (https://nixtlaverse.nixtla.io/statsforecast/src/core/core.html, read 2026-11-25).
- Checks: On train days `forward` on the fit window gave exactly the result of `predict` for all three families, and a second fit on the same window gave the same forecast. So `predict` has one code path. Tests on synthetic frames: a 23-hour and a 25-hour day give 23 and 25 forecasts, and 92 and 100 on the 15-minute grid. A forecast between two fits changes when the last price before its cut changes, and stays the same when every value after the cuts changes. The price cut was moved on purpose once: 23 tests failed, 6 of them tests of the new models.
- Alternatives rejected: A new fit every day, which is 60 fits per zone where the weekly refit has 9. Forecasting up to 7 days ahead from the last fit, which would ignore the prices that arrive in between.
- Limits: MSTL decomposes every day anyway, so its weekly fit fixes the trend model only. The initial state of an ETS model belongs to the start of the fit window, and the window moves on by one day at a time. On train days of DE_LU, moving the start of the window by one hour changed one forecast by at most 0.29 EUR/MWh.

## 64. `mstl_182` is the statistical baseline, chosen from 15 settings on the validation days
- Date: 2026-11-25. The owner chose the three families before the session, approved the 15 settings and the rule before any full run, and approved the winner after the comparison
- Candidates: 15 settings, each an entry under `models` in the config. `ets_28`, `ets_56`, `ets_91`, `ets_182` and `ets_364` are `AutoETS` with a season of one day and the form `AZA`, on 28 to 364 days of history. `ets_auto_56` has the form `AZZ`, which leaves the season to the model. `mstl_28` to `mstl_364` are `MSTL` with seasons of one day and one week and the same five history lengths. `arima_28` is `AutoARIMA` with a season of one day and the default search. `arima_small_28`, `arima_small_56` and `arima_small_91` limit the search to `max_p=2, max_q=2, max_P=1, max_Q=1`. History lengths are whole weeks.
- Season lengths: Measured on train days before any run. On the last 364 train days of the hourly table the strength of the daily season is 0.46 to 0.80 in DE_LU, FR, ES, SE_3 and SE_4 and 0.20 to 0.21 in SE_1 and SE_2. The strength of the weekly season is 0.22 to 0.36. Strength is 1 minus the variance of the remainder over the variance of season plus remainder, from an MSTL decomposition. The 15-minute table gives 0.47 to 0.78, 0.22 to 0.23 and 0.23 to 0.38.
- Rule, fixed before the runs: The winner is the setting with the lowest mean relative MAE over the seven zones on the validation days of experiment H, among the settings whose run passes every check. Run time is reported and does not decide.
- Result: 60 validation days, 2026-06-23 to 2026-08-21, 1440 hours per zone. Every run passed every check. Milestone 1 approved DE_LU, FR and ES only. SE_1 to SE_4 were added afterwards (entries 1 and 59). SE_1 and SE_2 are near-duplicates (entry 48), so the mean counts the north of Sweden about twice. Run time is the sum of the seven day loops in seconds.

| Setting | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean | Run time |
|---|---|---|---|---|---|---|---|---|---|
| `mstl_182` | 0.7106 | 0.6521 | 0.7165 | 0.7317 | 0.6666 | 0.6596 | 0.6837 | 0.6887 | 565.9 |
| `mstl_364` | 0.7106 | 0.6520 | 0.7165 | 0.7373 | 0.6706 | 0.6596 | 0.6838 | 0.6901 | 1314.7 |
| `mstl_91` | 0.7133 | 0.6538 | 0.7161 | 0.7382 | 0.6647 | 0.6612 | 0.6839 | 0.6902 | 281.8 |
| `mstl_56` | 0.7358 | 0.6686 | 0.7208 | 0.7645 | 0.6931 | 0.6771 | 0.6900 | 0.7071 | 205.0 |
| `arima_28` | 0.7805 | 0.7380 | 0.8053 | 0.6925 | 0.6529 | 0.6711 | 0.6870 | 0.7182 | 5254.9 |
| `arima_small_28` | 0.7917 | 0.7353 | 0.8808 | 0.6527 | 0.6511 | 0.6806 | 0.6763 | 0.7241 | 923.4 |
| `arima_small_56` | 0.7844 | 0.7321 | 0.8697 | 0.6961 | 0.6434 | 0.6793 | 0.6830 | 0.7269 | 1529.5 |
| `arima_small_91` | 0.8106 | 0.7786 | 0.8601 | 0.6550 | 0.6599 | 0.6691 | 0.6804 | 0.7305 | 3143.9 |
| `mstl_28` | 0.7764 | 0.6997 | 0.7378 | 0.8319 | 0.7824 | 0.6920 | 0.7020 | 0.7460 | 104.0 |
| `ets_56` | 0.9255 | 0.7698 | 0.8481 | 0.6952 | 0.6586 | 0.6752 | 0.6868 | 0.7513 | 10.5 |
| `ets_28` | 0.9607 | 0.7739 | 0.8522 | 0.6903 | 0.6693 | 0.6712 | 0.6934 | 0.7587 | 5.7 |
| `ets_91` | 0.9894 | 0.7783 | 0.8419 | 0.6767 | 0.6539 | 0.6810 | 0.6960 | 0.7596 | 17.1 |
| `ets_182` | 0.9674 | 0.7925 | 0.8538 | 0.6754 | 0.6657 | 0.7064 | 0.7547 | 0.7737 | 34.0 |
| `ets_364` | 1.0155 | 0.8010 | 0.8646 | 0.6775 | 0.6668 | 0.6910 | 0.7520 | 0.7812 | 180.0 |
| `ets_auto_56` | 1.5910 | 1.5868 | 1.2686 | 0.7314 | 0.6902 | 0.8390 | 0.9348 | 1.0917 | 17.8 |

- Decision: `backtest.statistical_baseline` is `mstl_182`: `MSTL(season_length=[24, 168], trend_forecaster=AutoETS(model="AZN"))` on the hourly table, fitted on the 182 days before the delivery day. 15 settings were tried in all, and their 105 rows are in `reports/results/backtest_core.csv`. The 14 settings that lost never see the test days.
- What the numbers support: The three best settings are a tie. A bootstrap over the 60 days, 2000 resamples of whole days with seed 42, gives a difference to `mstl_182` of +0.0015 for `mstl_364` (95% interval -0.0032 to +0.0073) and +0.0014 for `mstl_91` (-0.0029 to +0.0056). `mstl_182` is first in the first 30 days and `mstl_91` in the last 30. MSTL against ARIMA is not settled on 60 days either: `arima_28` is +0.0286 (-0.0218 to +0.0797). `mstl_56` (+0.0047 to +0.0334) and `ets_56` (+0.0043 to +0.1306) are behind. Without SE_2 the order of the top three is the same. The zones disagree: an MSTL setting is best in DE_LU, FR, ES and SE_3, and an `arima_small` setting in SE_1, SE_2 and SE_4. SE_1 and SE_2 have the weakest daily season. One setting serves all zones (entry 59), so the rule decides.
- Checks: DE_LU was run twice in memory for `mstl_182`, `ets_56` and `arima_small_28`. Both runs gave the saved MAE to the last digit. The MAE and the relative MAE of all 105 rows were computed again from the forecast files without the harness metrics, with no difference. The lowest relative MAE of any setting in any zone is 0.6434. The published LightGBM range is 0.42 to 0.48 (PROJECT_CONTEXT §7), so no price-only setting raises a leakage alarm.
- Alternatives rejected: Choosing the family by its name in the Milestone 1 plan, without a comparison. Choosing `mstl_91`, which takes half the run time and is inside the noise of the winner: the rule was fixed before the runs, and changing it afterwards would be a choice made with the results in hand.
- Limits: The winner was picked among 15 settings on the same 60 days, so 0.6887 is somewhat optimistic. The 60 days are one summer. `ets_auto_56` chose no season and forecasts one flat value per day: on train days its AICc was lower without a season (18517 against 19324 in DE_LU), because the criterion scores one step ahead. ARIMA got no history above 91 days and the default search none above 28, because one fit on 56 days took 277 seconds. No history above 364 days was tried. The whole comparison took about 3 hours 50 minutes against an estimate of 2.3 hours, because the ARIMA runs were about 2.5 times slower than one timed fit suggested.
- Update, 2026-11-26: After the test run the owner asked why `mstl_364` was not chosen, and confirmed that `mstl_182` stays the baseline. `mstl_364` lost by the rule with 0.6901 against 0.6887. The two settings give the same relative MAE to three decimals in five zones, and the whole gap comes from SE_1 and SE_2. Every table of the comparison, with MAE, RMSE, run time and peak memory per setting, is in `docs/MODEL_NOTES.md` (entry 68).

## 65. A model is a config entry, with its own history length, and the backtest can run one experiment
- Date: 2026-11-25, proposal approved by the owner
- Decision: `--model` of the backtest takes any name under `models` in the config. The entry `naive` is the seasonal naive forecast, and every other entry names a `family` and is built as a `StatsModel` (entry 62). An entry may hold `history_days`. Without it the model receives `backtest.history_days`. The naive reference inside every run always receives `backtest.history_days`, so the `naive_mae` of a row equals the naive row of the same zone and split. `--experiment H` or `--experiment Q` runs one experiment, and without the option both run. Every model has one new check, "every forecast is finite". The two naive checks of entry 52 stay with the naive model only. `results.py` did not change.
- Reason: Entry 56 left the history length to the first model that trains. Each setting has its own model name, so its rows in `daily_core.csv` and its forecast files replace nothing. The candidates were compared on experiment H only, which needs a way to run H alone.
- Alternative rejected: One model name with the setting as a further key column of the results files. It would have changed the key of `daily_core.csv` and the path of the saved forecasts.
- Limit: `refit_every_days` stays one value for all models. It was not tuned.

## 66. Experiment Q runs the frozen setting only, with seasons of 96 and 672 quarter-hours
- Date: 2026-11-25, default approved by the owner before the runs
- Decision: `mstl_182` was scored on the validation days of experiment Q with the same config entry. Its `season_days` of 1 and 7 are 96 and 672 quarter-hours there. No other candidate was run on experiment Q.
- Result: 60 validation days, 5760 quarter-hours per zone, every check passed. The relative MAE is 0.6611 in DE_LU, 0.6528 in FR, 0.7160 in ES, 0.7267 in SE_1, 0.6682 in SE_2, 0.6617 in SE_3 and 0.6955 in SE_4, with a mean of 0.6831. The seven day loops took 10603 seconds in total, about 2 hours 57 minutes, and the peak memory was 219 MB. SE_1 to SE_4 were added after Milestone 1, and SE_1 and SE_2 are near-duplicates.
- Reason: One setting per model (entry 59), and the setting is chosen on experiment H (entry 64). A comparison of all 15 settings on the 15-minute table was not affordable: one `AutoARIMA` fit with a season of 96 took 1034 seconds on 28 days of DE_LU train prices.
- Alternative rejected: A second comparison on experiment Q with its own winner. It would give the statistical baseline two settings.
- Limits: The setting was not tuned on the 15-minute prices. The run takes about 19 times as long as on the hourly table (10603 against 566 seconds), because `forward` decomposes a window of 17472 values again on every delivery day.

## 67. `mstl_182` was scored on the test days once
- Date: 2026-11-25, approved by the owner after the comparison
- Decision: The frozen setting was committed first (`bdf41d5`). Then `mstl_182` was added to `backtest.test_models` (`31bfb35`), and `python -m epf.evaluation.backtest --model mstl_182 --split test` was run once, from 19:04 to 23:48 on 2026-11-25, for experiments H and Q. No other candidate has seen the test days. No setting, rule or metric was changed after the run.
- Result: 90 test days, 2026-08-22 to 2026-11-19, 2161 hours and 8644 quarter-hours per zone. Every check passed. Milestone 1 approved DE_LU, FR and ES only. SE_1 to SE_4 were added afterwards, and SE_1 and SE_2 are near-duplicates. MAE and RMSE are in EUR/MWh.

| Zone | H relative MAE | H MAE | H RMSE | Q relative MAE | Q MAE | Q RMSE |
|---|---|---|---|---|---|---|
| DE_LU | 0.4831 | 33.30 | 47.13 | 0.4901 | 33.94 | 48.18 |
| FR | 0.5151 | 32.64 | 45.32 | 0.5182 | 33.14 | 45.63 |
| ES | 0.6137 | 28.21 | 39.65 | 0.6181 | 28.69 | 40.35 |
| SE_1 | 0.6439 | 20.12 | 30.28 | 0.6496 | 20.77 | 31.03 |
| SE_2 | 0.6486 | 23.64 | 35.72 | 0.6466 | 24.03 | 35.92 |
| SE_3 | 0.5499 | 31.84 | 42.93 | 0.5512 | 32.15 | 43.44 |
| SE_4 | 0.5116 | 40.90 | 57.43 | 0.5101 | 41.15 | 57.95 |
| Mean | 0.5666 | | | 0.5691 | | |

- Cost: The 14 day loops took 17007 seconds, about 4 hours 43 minutes, of which about 17 minutes were experiment H. The peak memory was 249 MB.
- Checks after the run: The `naive_mae` of all 14 new rows equals the MAE of the saved naive test rows. `git diff` shows 14 added lines in `backtest_core.csv` and 1260 in `daily_core.csv`, and no removed line. Three DE_LU forecasts were made again from a table that ends at the price cut of the day: the first test day, the 25-hour day 2026-10-25 and 2026-10-29. Each equals the saved forecast exactly.
- Why the relative MAE is lower than on the validation days: The mean over the zones fell from 0.6887 to 0.5666 on experiment H. The MAE of `mstl_182` rose from 20.33 to 30.09, and the MAE of the naive forecast rose from 29.63 to 54.83. So the ratio is lower because the price of 7 days before was a much worse forecast in the autumn, not because the model became more accurate. The DE_LU value of 0.4831 is above the published per-hour LightGBM value of about 0.42 for that zone, and the Swedish values of 0.51 to 0.65 are above the published 0.43 to 0.48 (PROJECT_CONTEXT §7, another period). No value raises a leakage alarm.
- Limits: The test numbers are known from now on. They must not steer any later choice. The test days hold the clock change of 2026-10-25, after which the model sits one step off the local clock until it has adapted (entry 62). The error of those days was not looked at separately. The baseline uses no load, wind, solar or weather input.

## 68. The measured results of a model are collected in `docs/MODEL_NOTES.md`
- Date: 2026-11-26, asked for by the owner
- Decision: `docs/MODEL_NOTES.md` holds, per model, how it was measured, the settings tried, the result tables, the run times and the checks. Its first section is the statistical baseline: the season evidence and the timing on train days, the 15 settings, the rule, relative MAE, MAE and RMSE of every setting per zone, the time and memory of every run, the bootstrap, the runs on experiment Q and on the test days, and the estimates against the measured run times. The tables are built from `reports/results/backtest_core.csv` by a script, and the blocks of printed output are copied from the commands. A check compared every table cell with the results file.
- Reason: Before this file the measurements were spread over DECISIONS entries 62 to 67, README and the results files, and some existed only in the output of the session: the season tables, the timing before the runs, MAE and RMSE per setting, the peak memory and the time of each command. DATA_NOTES does the same job for the data.
- Alternative rejected: Putting everything into DECISIONS entry 64. That file holds decisions with their reasons, and an entry with ten tables would bury them.
- Limits: The scripts that made the season evidence, the timing and the checks are not in the repo, so those blocks cannot be rebuilt by a repo command. The file must be extended by hand when a model is added.

## 69. The feature builder reads the cut inputs of one delivery day
- Date: 2026-11-26, proposal approved by the owner
- Decision: `src/epf/features/builder.py` has `day_features(inputs, settings, holidays)`, which reads one `DayInputs` object and nothing else, and `build_features(table, days, ...)`, which calls `day_inputs` of `cutoff.py` for every delivery day and joins the days. No cut is written a second time. `day_inputs` receives the longest lag of the settings, 7 days, as its history length. The frame holds features only. The price of the delivery day is never in it, and the caller sets the target beside it, as the backtest does with the actual prices. The settings are the new key `features` in the config.
- Reason: CLAUDE.md asks that the leakage rule applies to every feature. With one path through `day_inputs` a wrong feature can read an old value, but it cannot read a value behind a cut.
- Tests: Synthetic tables whose values are a code of their own timestamp, so a feature value says which timestamp it read. No feature reads a timestamp after its cut, on days of 23, 24 and 25 hours, hourly and 15-minute. Changing every value behind the cuts changes no feature, and changing the last value before a cut changes one. Each cut was moved on purpose once and restored: the price cut failed 54 tests, the day-ahead cut 18, the actual load cut 19, the weather run cut 4 and the weather time cut 1.
- Check on the real tables: every cell of the 14 built frames, 21635852 in all, was compared with a plain pandas computation on the whole table that does not go through `day_inputs`. None differs.
- Alternative rejected: Computing every feature on the whole table at once and blanking what lies behind a cut. It is much faster, but the cuts would then exist in a second place, and a wrong mask leaks without an error (the reason of entry 51).
- Limits: The build takes 25 to 31 seconds per zone on the hourly table of 2880 days and about 4 seconds on the 15-minute table, 230 seconds for the whole command. A model that builds its training rows again at every weekly fit pays this each time. `builder.py` and `build.py` are files beyond the layout of the first plan.
- Update, 2026-11-26: Counted again on this day, the price cut fails 55 tests, not 54. The weather run cut now fails 5, because a test for a run one hour after the run hour was added. The day-ahead cut, the actual load cut and the weather time cut fail 18, 19 and 1 as before. The table is in `docs/MODEL_NOTES.md`.

## 70. Price features: lags of 1 to 7 days and four statistics of D-1
- Date: 2026-11-26, chosen by the owner
- Decision: `features.price_lag_days` is 1 to 7: the price at the same wall-clock time on each of the seven days before D. `features.price_day_stats` is mean, min, max and last: statistics over every market time unit of D-1, repeated on the rows of D. That is eleven price features.
- Evidence, train days only: D-1 is the strongest lag in every zone, with a correlation of 0.76 to 0.92 on the hourly table. D-7 rises again above D-4 to D-6 in DE_LU, FR, ES, SE_3 and SE_4, and not in SE_1 and SE_2. In a least-squares fit the R² of all seven lags is 0.001 to 0.006 above that of D-1, 2, 3 and 7, and 0.002 to 0.012 on the last 364 train days. The last price of D-1 adds 0.012 to 0.081, most in SE_1 and SE_2. The tables are in `docs/MODEL_NOTES.md`.
- Reason: The owner chose all seven lags. A tree model can leave a weak lag unused, and the lags are a list in the config.
- Alternatives rejected: D-1, 2, 3 and 7 with the same statistics, which I had recommended as the smaller set. The same with D-14, which adds 0.001 to 0.005. D-1 and D-7 alone, which gives up the last price of D-1.
- Limits: R² comes from a linear fit on the days it was fitted on. It says what a line can use, not what a tree can use. The lags were not chosen on validation days. One list serves all zones, although the weekly lag is weak in SE_1 and SE_2.

## 71. One feature list for all zones: total wind, and a solar feature that is empty in Sweden
- Date: 2026-11-26, proposal approved by the owner
- Decision: `features.forecasts` names each forecast feature and the day-ahead columns summed into it. `load_forecast` is the load forecast. `wind_forecast` is onshore plus offshore, where a zone uses the columns it has: both in DE_LU, onshore alone in the six other zones. `solar_forecast` is the solar forecast. A zone without any of the columns gets the feature with every value empty, so SE_1 to SE_4 have empty solar features. Every zone has the same columns in the same order. A sum is empty when one of its columns is empty at that time.
- Reason: The rule is that no feature exists for one zone only (entry 59). Offshore wind exists in DE_LU alone, so it is never a feature of its own. The solar forecast exists in three zones, and entry 59 already says that Sweden enters with one input fewer. One column list lets one model setting read every zone.
- Alternatives rejected: Only the columns that every zone has, which takes the solar forecast away from DE_LU, FR and ES. Onshore wind alone, which also drops the offshore wind of DE_LU.
- Limits: FR has offshore wind since 2022, but its forecast column was dropped by the coverage gate (entry 32), so the French wind feature is onshore only. SE_4 has the most solar of the Swedish zones and no solar feature.

## 72. Each forecast is given at the target time and at D-1 and D-7
- Date: 2026-11-26, proposal approved by the owner
- Decision: `features.forecast_lag_days` is 1 and 7. Each of the three forecast features comes at the target time and at the same wall-clock time one day and seven days before: nine forecast features.
- Evidence, train days only: On top of the price lags and the forecasts at the target time, the forecasts of D-1 and D-7 raise R² by 0.016 to 0.041 on the hourly table and by 0.025 to 0.057 on its last 364 days.
- Reason: The lagged price was set under the lagged forecast. With both, the model can see what has changed since then. All of these values lie under the day-ahead cut.
- Alternative rejected: The forecast at the target time only, which is three features and gives up the measured gain.
- Limit: Only the lags 1 and 7 were measured.

## 73. Actual load at D-2 is its own feature group
- Date: 2026-11-26, proposal approved by the owner
- Decision: The group `actual_load` holds the columns under the D-2 cut at `features.actual_load_lag_days`, which is 2: one feature, `actual_load_lag_2`. A lag of one day is always empty, because the inputs hold actual load through D-2 only. A test asks for that lag and gets empty values.
- Evidence, train days only: On top of the forecasts and their lags, actual load at D-2 raises R² by 0.0001 to 0.002 on the hourly table, and by about 0.01 at most on its last 364 days, in SE_3. D-7 adds at most 0.002 more.
- Reason: PROJECT_CONTEXT §5 lists actual load through D-2 as known, and §6 does not name it for LightGBM. As a group of its own it can be switched off, so the validation days can decide. The builder now uses the D-2 cut, so a moved cut fails feature tests.
- Alternative rejected: Leaving it out. The evidence is weak, but then no feature would exercise the D-2 cut.
- Limit: On train days the actual load of SE_1 and SE_2 reaches values far outside their load forecast: up to 4428 MW against a forecast maximum of 2204 in SE_1, and 8477 against 3608 in SE_2. The values stay as they are (entry 30).

## 74. Feature groups are switched in the config, one group per forecast
- Date: 2026-11-26, chosen by the owner
- Decision: `features.groups` lists the groups that are built: `price`, `calendar`, `load_forecast`, `wind_forecast`, `solar_forecast`, `actual_load` and `weather`. The builder makes only the listed groups, in a fixed order, and a group has the same values whatever else is built. An unknown group, an unknown statistic, a lag below one day, a forecast column that is not under the day-ahead cut and a wrong weather column are refused when the settings are read.
- Reason: RQ2 asks whether the extra inputs help. With one group per forecast the comparison can also drop one forecast at a time. The choice sits in the config and not in model code.
- Alternatives rejected: Four groups with the three forecasts as one, which I had recommended as fewer combinations to run. No switch in the builder, with the model dropping columns by name.
- Limit: Seven groups give many combinations. Which of them are run is a choice for the LightGBM step, on validation days.

## 75. One row per market time unit, built in memory, with a saved copy for inspection
- Date: 2026-11-26, chosen by the owner after a second round of evidence
- Decision: A feature frame has a UTC index and one row per market time unit: 24 rows a day on the hourly table and 96 on the 15-minute table, 23 or 25 and 92 or 100 on a clock-change day. The hour is a feature, and the 15-minute frame also has `quarter_hour`. The frame is built in memory from the cut inputs. `python -m epf.features.build` also saves `data/features/{experiment}/{ZONE}.parquet` (`paths.features`), which git ignores. The backtest never reads these files. The 24 hourly prices of D-1 are not features.
- Evidence, train days only, a least-squares stand-in fitted on the first 80% of the train days and scored on the last 20%: one fit over all market time units has a mean relative MAE of 0.4902 on the hourly table and 0.5188 on the 15-minute table. One fit per time of day has 0.4832 and 6.0653. Each of its 96 fits on the 15-minute table has about 200 rows. The hourly prices of D-1 raise the error to 0.4992 and 0.5410.
- Reason: The owner asked which shape gives the best forecasts with time left aside. This shape keeps both designs open: one model on the whole frame, or one model per hour by filtering the same frame on `hour`. It is the only shape that held on the 15-minute table. The owner chose the saved copy to look at the features.
- Alternatives rejected: One row per delivery day with a column per hour, which fixes one model per time of day. The same frame without a saved copy, which I had recommended, because a saved file is a second path beside the cuts.
- Limits: A least-squares fit is not LightGBM. A tree model on one frame can learn a different behaviour per hour by itself. The saved frames cover the validation and the test days too, so they are not train data as a whole. A saved frame holds the prices of those days as lags, like the processed tables do.

## 76. A lag follows the wall clock, as the seasonal naive forecast does
- Date: 2026-11-26, proposal approved by the owner
- Decision: Every lag of prices, forecasts and actual load calls `source_times` of `src/epf/models/naive.py`: the same wall-clock time in market time some days before, and a whole number of 24 hours before the target where that time is missing or double (entry 52). So `price_lag_7` equals the seasonal naive forecast, and a test asserts it on seven days around both clock changes, hourly and 15-minute. The statistics of D-1 cover every market time unit of that calendar day: 23, 24 or 25 hours.
- Reason: The daily price shape follows the local clock (entry 39). One rule for the naive forecast and for the features means the model and its reference read the same hour.
- Alternative rejected: A fixed number of 24 hours in UTC. It needs no special case, but in the days after a clock change every lag would sit one local hour off.
- Update, 2026-11-26: Six of the seven days of that test have a clock change on D, D-1 or D-7. The seventh, 2026-07-01, is a plain day.

## 77. Calendar features, empty values and no scaling
- Date: 2026-11-26
- Decision: The calendar group has `hour` (0 to 23 in market time, hour 2 twice on a 25-hour day), `quarter_hour` (0 to 3, only where the market time unit is shorter than an hour), `weekday` (0 is Monday) and `holiday` (1 on a nationwide holiday of the country of the zone, entry 46). No month and no year. Nothing is filled: a feature is empty where its source value is empty, lies before the start of the table or behind a cut, or where the zone lacks the column. No row is dropped. The mean, minimum and maximum of D-1 are empty when one price of D-1 is empty. No feature is scaled.
- Reason: A tree cannot extrapolate a year, and experiment Q has 265 train days, so a month would stand for a trend there. Entry 30 left the handling of gaps to the feature builder, and LightGBM reads an empty value as it is. Trees do not need scaling, and a scaler would have to be fitted on train days only.
- Alternative rejected: Dropping the rows of the first seven days, whose lags reach before the table. The training step can do that. The builder reports the counts.
- Check: The empty cells of the features at the target time equal what `config/approved_gaps.yaml` gives, in all 98 comparisons of zone, experiment and feature.

## 78. Weather features are built now, with a fourth cut by run time and by time
- Date: 2026-11-26, decided by the owner
- Decision: `cutoff.py` has a `WeatherRule` and `DayInputs` has a part `weather`. A weather row is handed over when its time is before 00:00 market time on D+1 and its model run started at or before `open_meteo.run_hour_utc` (00:00 UTC) on D-1. The run column stays in the part, so the run of every value can be read. `backtest.weather_run_column` names it, and the weather columns are `open_meteo.variables`. A weather table with another column, or without the run column or a rule, is refused. The group `weather` of the builder has four features: `temperature_2m`, `wind_speed_10m`, `wind_speed_100m` and `shortwave_radiation`.
- Reason: The owner chose to build weather on this day. PROJECT_CONTEXT §6 said "Weather later" and §10 placed it in weeks 9 to 11. Entry 25 stored the run time so that each value can be checked against the forecast origin, and this cut is that check.
- Evidence, train days from 2024-03-15, the least-squares stand-in of entry 75: the four weather values move the mean relative MAE from 0.4715 to 0.4674 for one fit and from 0.4510 to 0.4503 for a fit per hour. They help in FR, SE_3 and SE_4 and hurt slightly in DE_LU and SE_2.
- Alternatives rejected: Weather after M2, which I had recommended, because it widens the day and needs a change under `src/epf/evaluation/`. A cut by time only, which never reads the run column.
- Limits: Weather exists from delivery day 2024-03-15, so the features are empty on 45600 of the 69120 hours of the hourly frame. In the real table both conditions cut the same rows, because the hours of D+1 come from the run of D. That the run of 00:00 UTC is published before gate closure is taken from the Open-Meteo docs and not measured (entry 26). One point stands for a zone (entry 27). The measured gain is small.
- Update, 2026-11-26: In SE_3 the weather values help for one fit only, from 0.4735 to 0.4630. For a fit per hour SE_3 gets worse, from 0.4463 to 0.4527. The table is in `docs/MODEL_NOTES.md`.
- Update, 2026-11-27, approved by the owner: The sentence "They help in FR, SE_3 and SE_4" names too few zones. The weather values help in FR, ES, SE_1 and SE_4, both for one fit and for a fit per hour, and in SE_3 for one fit only (`docs/MODEL_NOTES.md`, "LightGBM features", section 3). The original text of the entry stays as it was written.

## 79. Radiation is taken one hour later, and weather stands on the four quarter-hours of its hour
- Date: 2026-11-26, proposal approved by the owner
- Decision: `features.weather_hour_before` lists `shortwave_radiation`, whose value is the mean of the hour before its timestamp. The delivery hour that starts at t takes the value stamped t plus one hour. For the last hour of D that value lies behind the weather cut, so the feature is empty there: one hour per day on the hourly frame and four quarter-hours on the 15-minute frame. The other weather values are taken at the start of the hour. On the 15-minute frame an hourly value stands on the four quarter-hours of its hour.
- Reason: This is the line-up that entry 33 left to the feature builder. The value for the hour 23:00 to 24:00 comes from the next model run, which is not known at the forecast origin.
- Evidence, 830 train days: the radiation of that hour is 0 W/m² on every day in six zones. In SE_1 it is above 0 on 28 days, at most 1.0 W/m².
- Alternatives rejected: Setting that hour to 0, which fills a value. No shift, which leaves radiation one hour late against the solar forecast and the price. Interpolating weather between two hours on the 15-minute grid, which needs the next hour and is more to defend than repeating a value (entry 22).

## 80. The backtest hands the weather table to every model
- Date: 2026-11-26, chosen by the owner
- Decision: `backtest_zone` in `backtest.py` reads `weather/{ZONE}.parquet` for a zone with a weather point, cut at the end of the scored split like the price table, and `run_days` passes it to `day_inputs`. Every model receives the cut weather in `inputs.weather`, also the naive reference. A zone without a weather point gets an empty weather part. A validation run reads no weather row of the test days.
- Reason: The owner chose to wire the backtest on the same day as the cut. The LightGBM model of the next step then finds the weather in its inputs, and the tests of the harness cover the weather cut as well.
- Check: With the owner's yes, a backtest was run in memory on the validation days and wrote nothing: the naive forecast on experiments H and Q and `mstl_182` on experiment H, for all seven zones. In all 21 runs the forecasts equal the saved forecast files exactly, the MAE equals the saved row to the last digit, and every check passed. No file under `reports/results/` or `data/forecasts/` changed.
- Alternative rejected: Changing `cutoff.py` only and wiring the backtest with the LightGBM model, which I had recommended, because it leaves the runs of the naive forecast and of `mstl_182` exactly as they were.
- Limits: The naive forecast and the statistical models ignore the weather. Each day now costs one more cut, so `wall_seconds` of a later run is not strictly comparable with the saved rows. The cost was not isolated: in the check the day loops of `mstl_182` took 98 to 104 seconds per zone against 60 to 95 in the saved rows, while other commands ran on the same machine.

## 81. The seven zones are shown alike
- Date: 2026-11-26, decided by the owner
- Decision: The seven core zones are shown alike in every document, table, figure and label. Nothing marks or describes SE_1 to SE_4 as added later. The existing text was rewritten to this rule on the same day: `CLAUDE.md`, `PROJECT_INSTRUCTIONS.md`, `README.md` with its results table, `docs/PROJECT_CONTEXT.md`, `docs/MODEL_NOTES.md`, the comment above `zones` in `config/config.yaml`, the Markdown cells of both EDA notebooks, and the sentences about Milestone 1 in `src/epf/data/coverage_gate.py` and `docs/coverage_gate.md`. The test fixtures no longer use a Swedish zone as their example of a zone in the group `extra`. No number was changed and no data changed. In the code only the wording of one sentence that the gate report writes changed. Two sentences were removed with their numbers by owner decision: the estimate in `docs/PROJECT_CONTEXT.md` §3.1 that the backtest of seven zones takes about 2.3 times the run of DE-LU, FR and ES, and the sentence in `notebooks/01_eda_drivers.ipynb` that the high-price rule gave a threshold of 137.24 for DE_LU, FR and ES alone. Both numbers stay in entries 59 and 45. The data limits are still stated with the Swedish results: SE4 has no usable solar forecast, and SE1 and SE2 are near-duplicates (entry 48). This replaces the rule of `CLAUDE.md` that the Swedish zones are marked wherever they are shown.
- Reason: The owner's instruction: "consider as sweden was there from the begining. dont treat the sweden added later stage at any moment for any further steps." Asked how far this goes, the owner chose to rewrite the existing text as well.
- Alternatives rejected: The rule for new work only, with the rule lines changed and the existing text left as it was. The rule for new work only, with the rule lines untouched.
- Limits: Entries 1 and 59 and the old rows of `docs/PROGRESS.md` stay as the dated record of when the zones entered the project. They are not changed. The README no longer says what Milestone 1 approved. `docs/coverage_gate.md` is the report of 24 Nov 2026, so its tables still list SE_1 to SE_4 in the group `extra` with a verdict (entry 61). The owner decided on 2026-11-26 to run the gate again in a later session with all seven zones as core zones, which will replace that report.

## 82. The holiday dates of a zone reach a model through `DayInputs`
- Date: 2026-11-26, decided by the owner while planning, before any code
- Decision: `DayInputs` in `cutoff.py` has a part `holidays`, a frozenset of calendar dates in market time. `backtest_zone` reads the holiday dates of the zone once with `zone_holidays`: the holiday categories of the country of the zone (entry 46), for every whole year from the first row of its table to the end of the scored split. `run_days` passes them to `day_inputs` on every day. Every model receives them, also the naive reference. The feature command `python -m epf.features.build` calls the same `zone_holidays`. The holiday dates are under no cut and under no history length, so the dates after D are handed over too.
- Reason: The backtest builds one model object for a run and uses it for every zone. With the dates in the inputs a model need not know its zone or its country, and the holiday feature of the LightGBM model comes the same way as every other input. A calendar is known years ahead. PROJECT_CONTEXT §5 lists the calendar and the holidays for D as known at the forecast origin.
- Alternative rejected by the owner: One model object per zone that keeps its holidays.
- Checks: Tests on synthetic tables assert that the inputs hold the dates they were given, that neither the delivery day nor the history length cuts them, and that one model object receives the holidays of each zone it is run on. The naive forecast and the statistical models read no holiday. No results row changed.
- Limit: The dates are not cut, so the leakage tests of the three table parts do not cover them. They are safe only because a holiday calendar holds nothing that is realised on D.

## 83. The results table and the firmness analysis are commands of the repo
- Date: 2026-11-26, decided by the owner: the table command while planning, the firmness command at Stop 3, the planned stop before the freeze. The guard for the test days was decided by the owner on 2026-11-27
- Decision: `python -m epf.evaluation.tables --experiment H --split validation` prints the relative MAE of every model per zone as a Markdown table. It reads `backtest_core.csv` through `results.read_rows`, which is a public function now, and it writes no file. The owner chose its shape: the rows are sorted by the mean over the zones, the lowest first, and there is one table per zone group. `python -m epf.evaluation.firmness --winner NAME --models NAME ...` prints how firm a choice between settings is: the MAE computed again from the forecast files, the mean by half of the days, the zones each model wins, a bootstrap over whole delivery days, the mean without one zone, and the relative MAE by hour of the day, by calendar week and on the worst days. It also only reads. With `--split test` it stops with one line unless every model of `--models` stands under `backtest.test_models`. Both commands have tests on synthetic results files.
- Reason: The tables and the checks behind `mstl_182` were made by scratch scripts that are not in the repo, so no repo command can rebuild those blocks (entry 68, Limits). A command with tests can be run again by an examiner, and every table of a document can be checked against it.
- Alternative rejected by the owner: A scratch script outside the repo, as before.
- Proposed, not yet decided by the owner: The firmness command has no `--group` option and prints its blocks for every zone group in turn. Its "worst days" are ranked by the absolute error summed over the market time units of a day. A tie in "zones won" goes to the model that stands higher in the table.
- Checks: 16 cells of the first printed table were compared with the results file by a script that imports no project code, and none differs. The firmness command was run on the saved rows of the statistical settings and of the LightGBM settings and compared with the output of the scratch script it replaces: 1096 and 927 numbers, none differs. A fresh reviewer ran both again with the same result.
- Limits: A model can have more than one run in the results file. Both commands then use the newest row by `run_started_utc` and name the model in a line. A model without a row for a zone gets an empty cell and an empty mean. The bootstrap draws days as if one day did not depend on the day before, so its intervals are likely too narrow. The firmness command reads the forecast files under `data/forecasts/`, which git ignores, so it runs only on a machine that has made the runs. The guard for the test days stops this command. It does not stop other code from reading the files (entry 58, Limit).

## 84. `lightgbm` 4.7.0 is pinned and used through its native API
- Date: 2026-11-26, package approved by the owner at Stop 1, the planned stop before the install, after a dry run
- Decision: `requirements.txt` pins `lightgbm` 4.7.0. The dry run printed `Would install lightgbm-4.7.0` and no other package: narwhals 2.29.0, numpy 2.5.5 and scipy 1.18.1 were already installed, and no pin moved. scikit-learn is not installed and stays out. So the model calls the native API only: `lightgbm.Dataset`, `lightgbm.train` and `Booster.predict`.
- Reason: PROJECT_CONTEXT §6 names `lightgbm` for model 3. The wheel requires only narwhals, numpy and scipy. Its scikit-learn classes need scikit-learn: on this install `LGBMRegressor()` raises "scikit-learn is required for lightgbm.sklearn". The native API has what the model needs: a pandas frame as input, the squared error, the absolute error and the quantile objective, and empty values in a feature.
- What was read before the first call: The installed version and the documentation of version 4.7.0 were read, and each call was tried on synthetic data. Four findings shaped the code. `predict` takes the columns by position and does not compare their names. A row with an empty target is not refused, and its target is stored as 0. A parameter key that LightGBM does not know is ignored without an error. A round count among the parameters wins over the `num_boost_round` argument. Targets are stored as 32-bit floats: for every cent from -500.00 to 4000.00 the largest change was 0.00012.
- Alternative rejected: scikit-learn with the `LGBMRegressor` wrapper. Only `lightgbm` was approved as a new package.
- Limits: `backtest.py` imports `lightgbm`, so every backtest command needs it, also a run of the naive forecast or of `mstl_182`. On 2026-11-26 at about 18:15 a Visual Studio installer replaced the Visual C++ runtime of the machine, and `import lightgbm` failed until the installer had finished. That was seen once in the session and was not looked into further. LightGBM states that results can differ between versions, compilers and systems, so the pin holds for this version on this machine.

## 85. A LightGBM fit builds its training rows from the cut inputs, on every day before the cut or on a moving window
- Date: 2026-11-26. The owner decided the window while planning. The moving window of an entry with `history_days` was approved by the owner at Stop 2, the planned stop before the first LightGBM run, together with the candidates
- Decision: `LgbmModel` in `src/epf/models/lgbm.py` is a model of the backtest, built from a config entry with the family `lgbm`. A fit for delivery day D receives the cut inputs of D and reads no file. It sets the three table parts of the inputs side by side again and builds one training row per market time unit of every training day. `build_features` cuts that table again for each training day with `day_inputs`, so a training row holds only what was known when its own day was forecast. The target of a row is the price of its market time unit. The last training day is D-1 by the calendar. `fit` is called on the first scored day and then every 7th delivery day (entry 56). Between two fits the trees stay as they are, and the forecast of a day applies them to the features of that day, which are built from its own inputs.
- The window: An entry without `history_days` trains on every delivery day before its own cut, from the first row of the table. In a validation run that includes the validation days that have already passed. No scored day is in the fit that forecasts it. An entry with `history_days` receives a moving window of that many days, as `mstl_182` does (entry 65). With 826 days the inputs of a fit on the hourly table hold 826 days, and the fit trains on 819 of them.
- Reason: The first form is the expanding window of PROJECT_CONTEXT §5 and entry 56. The model reads its inputs through the same cuts as every other model, so the leakage tests of the harness cover it. Building each training day from `day_inputs` again keeps the cuts in one place (entry 69).
- Alternative rejected by the owner: Training on the train days only. A fit for a test day in November would then hold no day after 2026-06-22.
- Proposed, not yet decided by the owner: The first days of a window are skipped. Training starts at the first day with a price plus the longest lag of the features, 7 days, because the lags of an earlier day reach before the window. A row without a price is dropped, because LightGBM would store its target as 0. An empty feature stays empty, and LightGBM reads it as a missing value. Nothing is filled or scaled. The model itself compares the feature names of a forecast with those of its fit, because LightGBM takes the columns by position.
- Checks: Two lines of the finished code were changed on purpose and restored. With the price cut moved to the end of the day the suite printed `63 failed, 702 passed`: 31 failures in `test_features.py`, 14 in `test_cutoff.py`, 8 in `test_lgbm.py`, 6 in `test_stats.py` and 4 in `test_backtest.py`. With the training days ending one day later it printed `3 failed, 762 passed`, all three in `tests/test_lgbm.py`. After the restore it printed `765 passed`. A fresh reviewer changed every value behind the cuts of one training day and found the rows of that day bit-identical. Two tests of that kind were added afterwards.
- Cost: One zone was timed before the candidates were planned: the first zone of the config on the validation days of experiment H, with all seven feature groups, 100 trees and all history, in memory. The 9 fits took 24.3 to 32.4 seconds each, and 24.0 to 32.1 seconds of each fit went into building the training rows: 65351 rows at the first fit and 66695 at the last, with 28 features. A forecast day took 0.030 seconds. The day loop took 241.2 seconds and the peak memory was 364 MB.
- Limits: The `wall_seconds` of a LightGBM row is almost all feature building, because every weekly fit builds the rows of all its training days again (entry 69, Limits). It says little about LightGBM itself. No built frame is kept between two fits or between two runs. `refit_every_days` was not tuned.

## 86. The parameters the model sets itself, the ten keys an entry may set, and calendar features as numbers
- Date: 2026-11-26, decided by the owner: the parameters and the keys before the model was written, the calendar features at Stop 2
- Decision: Every fit sets `seed` to the seed of the project (42, entry 57), `deterministic=true`, `force_col_wise=true` and `verbosity=-1`. It sets no `num_threads`, so LightGBM uses its default number of threads. `params` of a model entry may hold ten keys: `learning_rate`, `num_leaves`, `max_depth`, `min_data_in_leaf`, `feature_fraction`, `bagging_fraction`, `bagging_freq`, `lambda_l1`, `lambda_l2` and `max_bin`. Every other key is refused when the model is built: an alias of one of the ten, a round count, and a key that the model sets itself. The number of trees is the key `trees` of the entry and is handed over as the number of boosting rounds. The calendar features `hour`, `weekday`, `holiday` and `quarter_hour` go in as numbers.
- Reason: The LightGBM documentation names `deterministic` for the same result from the same rows and parameters, and asks for `force_col_wise` or `force_row_wise` with it. LightGBM ignores a key it does not know without an error, so a misspelt key would run the defaults without a word. A round count among the parameters would replace the trees of the entry. A fit without `verbosity` keeps the level of the fit before it, so the key is set every time. With aliases refused a parameter has one spelling in the config and in `model_params` of a results row.
- Alternative rejected by the owner: Calendar features as categories. That call was not among those verified for version 4.7.0, and it would have needed new code and a review before the runs.
- Proposed, not yet decided by the owner: Only `regression`, the squared error, and `regression_l1`, the absolute error, are accepted as objective names. `params` is a required key of an entry, written `params: {}` for the defaults. An unknown key of an entry is refused. `groups` must be a list of groups that `features.groups` builds. A fit has a fixed number of trees, with no early stopping and no validation set inside a fit. A refusal by LightGBM, for example for `num_leaves: 1`, becomes a `ValueError` that names the entry, so the command ends with one line.
- Checks: In the tests two fits on the same rows with the same seed give the same forecast. On the real tables a fresh fit for the first validation day of the first zone gave the saved forecast of the frozen setting to the last bit.
- Limits: LightGBM states the same result for one machine and one version of the library only. Determinism was measured on synthetic tables and on that one real day. As numbers, the hour and the weekday are split by their order. Whether categories forecast better was not measured.

## 87. Eleven LightGBM candidates and the rule, fixed before any run
- Date: 2026-11-26, approved by the owner at Stop 2, before any LightGBM run on the validation days
- Candidates, step 1: Eight entries under `models` in the config. All have the LightGBM defaults, a learning rate of 0.1 and 31 leaves per tree, with 100 trees and the squared error. Four train on all history, and each adds one kind of input: `lgbm_price` has price and calendar, `lgbm_fcst` adds the load, wind and solar forecast, `lgbm_load` adds actual load at D-2, and `lgbm_all` adds weather. `lgbm_load_826` and `lgbm_all_826` are the last two on a moving window of 826 days. `lgbm_load_364` and `lgbm_all_364` are the same on 364 days.
- Candidates, step 2: Three entries on the step-1 candidate with the lowest mean, with one change each. `_l1` has the absolute error as objective (`regression_l1`). `_slow` has 400 trees with a learning rate of 0.025. `_leaves15` has 15 leaves per tree. A quarter of the learning rate with four times the trees counts as one change.
- Rule, fixed before the runs, in the words of entry 64: The winner is the setting with the lowest mean relative MAE over the seven zones on the validation days of experiment H, among the settings whose run passes every check. Run time is reported and does not decide. All eleven candidates compete. A mean clearly below 0.42, the low end of the published range (PROJECT_CONTEXT §7), starts a search for leakage before a winner is named.
- Run time approved: An estimate of 3 hours 45 minutes, with a ceiling of 5 hours in total and 45 minutes per run.
- Reason: The first four candidates answer RQ2, because each adds one kind of input. Weather exists from 2024-03-15 only. On all history 1893 of the 2723 training days of the first fit have empty weather, so `lgbm_all` cannot show the value of weather alone. 826 days are 118 weeks, and the window of the first fit starts on 2024-03-19, inside the weather period. So the pair on 826 days is the fair weather comparison, and the pair on 364 days repeats it on one year. Step 2 changes one thing at a time, so each change can be read alone.
- The owner's answers: "Full list" for the candidates, "Approve the rule" for the rule, and "As numbers" for the calendar features (entry 86).
- Limits: The step-2 changes were tried on one step-1 setting only, so most combinations of inputs, window and parameters were never run. Three parameter changes are a small search. No candidate uses sampling or a penalty. All of it is judged on 60 days of one summer.

## 88. `lgbm_load_826_slow` is the frozen LightGBM model
- Date: 2026-11-26, freeze approved by the owner at Stop 3, after the comparison
- Decision: `backtest.lightgbm_model` in the config is `lgbm_load_826_slow` (commit `2853866`). It uses the feature groups price, calendar, load forecast, wind forecast, solar forecast and actual load, the squared error, 400 trees with a learning rate of 0.025, the other LightGBM defaults, and a moving window of 826 days. The ten candidates that lost stay in the config so that their rows can be reproduced. They never see the test days.
- Result: 60 validation days, 2026-06-23 to 2026-08-21, 1440 hours per zone. Each of the eleven runs ended with exit code 0 and passed its four checks in all seven zones. Each added 7 rows to `backtest_core.csv` and 420 to `daily_core.csv`, and no earlier line changed. The table is the one that `python -m epf.evaluation.tables --experiment H --split validation` prints, with the eleven candidates, `mstl_182` and `naive`. Run time is the sum of the seven day loops in seconds. SE_4 has no usable solar forecast, and the solar features of all four Swedish zones are empty (entry 71). SE_1 and SE_2 are near-duplicates (entry 48), so the mean counts the north of Sweden about twice.

| Setting | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean | Run time |
|---|---|---|---|---|---|---|---|---|---|
| `lgbm_load_826_slow` | 0.4909 | 0.5548 | 0.5707 | 0.6235 | 0.5122 | 0.4890 | 0.4797 | 0.5316 | 436.8 |
| `lgbm_load_826` | 0.5073 | 0.5625 | 0.5674 | 0.6271 | 0.5160 | 0.4881 | 0.4832 | 0.5359 | 524.0 |
| `lgbm_load_826_l1` | 0.5125 | 0.5498 | 0.5855 | 0.5816 | 0.5477 | 0.5018 | 0.4861 | 0.5379 | 257.9 |
| `lgbm_all` | 0.5725 | 0.5940 | 0.5813 | 0.5557 | 0.4891 | 0.5053 | 0.4884 | 0.5409 | 1642.6 |
| `lgbm_all_826` | 0.5229 | 0.5697 | 0.5803 | 0.6417 | 0.5084 | 0.4851 | 0.4927 | 0.5430 | 485.7 |
| `lgbm_fcst` | 0.5741 | 0.6002 | 0.5936 | 0.5776 | 0.5022 | 0.5236 | 0.5062 | 0.5539 | 1304.3 |
| `lgbm_load` | 0.5724 | 0.5962 | 0.5912 | 0.5834 | 0.4970 | 0.5254 | 0.5127 | 0.5540 | 1513.4 |
| `lgbm_load_826_leaves15` | 0.5362 | 0.5724 | 0.5900 | 0.6282 | 0.5411 | 0.5050 | 0.5193 | 0.5560 | 394.5 |
| `lgbm_load_364` | 0.5312 | 0.5559 | 0.5851 | 0.6734 | 0.5751 | 0.5002 | 0.5148 | 0.5622 | 157.9 |
| `lgbm_all_364` | 0.5410 | 0.5643 | 0.5816 | 0.6578 | 0.5871 | 0.5246 | 0.5024 | 0.5655 | 173.1 |
| `lgbm_price` | 0.7064 | 0.6547 | 0.7248 | 0.6277 | 0.5887 | 0.6617 | 0.6340 | 0.6569 | 1207.1 |
| `mstl_182` | 0.7106 | 0.6521 | 0.7165 | 0.7317 | 0.6666 | 0.6596 | 0.6837 | 0.6887 | 565.9 |
| `naive` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 2.1 |

- The winner by the rule of entry 87: `lgbm_load_826_slow` with a mean of 0.5316. The winner of step 1 was `lgbm_load_826` with 0.5359, so the three step-2 entries were built on it. `mstl_182` has 0.6887.
- What the numbers support: The differences below come from `python -m epf.evaluation.firmness`, a bootstrap over the 60 days with 2000 resamples of whole days and seed 42. A plus sign means that the first setting named is worse. The day-ahead forecasts carry the gain: `lgbm_fcst` against `lgbm_price` is -0.1037 (95% interval -0.1398 to -0.0714). A window of 826 days is better than one of 364 days: `lgbm_load_364` against `lgbm_load_826` is +0.0265 (+0.0096 to +0.0461). Clearly behind the winner are `lgbm_all_826` with +0.0116 (+0.0039 to +0.0196), `lgbm_load_826_leaves15` with +0.0245 (+0.0164 to +0.0322), both settings on 364 days, `lgbm_price` and `mstl_182` with +0.1588 (+0.1167 to +0.2062). Without SE_2 the winner stays first with 0.5348.
- What the numbers do not support: The top four are a tie inside the noise. Against the winner `lgbm_load_826` is +0.0044 (-0.0013 to +0.0093), `lgbm_load_826_l1` is +0.0059 (-0.0139 to +0.0229) and `lgbm_all` is +0.0093 (-0.0152 to +0.0349). The winner is first in the last 30 days with 0.5365. In the first 30 days `lgbm_load_826_l1` is first with 0.5273 against 0.5375. The winner is the best setting in DE_LU and SE_4 only, and `lgbm_all` is the best in SE_1 and SE_2. Actual load at D-2 adds nothing: `lgbm_load` against `lgbm_fcst` is +0.0001 (-0.0035 to +0.0034). Weather does not help on the same window: `lgbm_all_826` against `lgbm_load_826` is +0.0072 (-0.0022 to +0.0175), and `lgbm_all_364` against `lgbm_load_364` is +0.0037 (-0.0079 to +0.0144). On all history `lgbm_all` against `lgbm_load` is -0.0131 (-0.0308 to +0.0003), but that pair cannot separate weather from the years before 2024 (entry 87). The window of 826 days against all history is not settled: `lgbm_load` against `lgbm_load_826` is +0.0179 (-0.0065 to +0.0472). LightGBM on price and calendar alone is not clearly better than `mstl_182`: `lgbm_price` against `mstl_182` is -0.0329 (-0.0788 to +0.0131). So the freeze means that the rule picks this setting. It does not mean that the setting is shown to be better than the next three.
- Checks: The MAE and the relative MAE of all 84 pairs of model and zone were computed again from the forecast files, with no difference to the saved rows. The lowest value of any zone is 0.4797 and the mean is above the published range of 0.42 to 0.48, so nothing started a search for leakage. A fresh reviewer computed the table, the halves and the bootstrap lines again with code of its own and got the same numbers.
- Cost: The eleven commands took 8164 seconds in all, about 2 hours 16 minutes, against the estimate of 3 hours 45 minutes. The longest took 1648 seconds, under the ceiling of 45 minutes. The highest peak memory of a run was 419 MB. Other processes ran on the machine, so the times do not rank the settings: the command with 400 trees took 443 seconds, and the same setting with 100 trees took 530.
- Alternatives rejected: Another of the top four, although they are inside the noise of the winner. The rule was fixed before the runs, and changing it afterwards would be a choice made with the results in hand. A setting per zone, although the zones disagree. One setting serves all zones (entry 59).
- Limits: Eleven settings were compared on the same 60 days, so 0.5316 is somewhat optimistic. The 60 days are one summer. The bootstrap treats the days as independent, so its intervals are likely too narrow, and the tie at the top is rather wider than shown. The window of 826 days is a trade between zones: from `lgbm_load` to `lgbm_load_826` DE_LU improves from 0.5724 to 0.5073 and SE_1 gets worse from 0.5834 to 0.6271. SE_1 is the weakest zone of the winner with 0.6235. SE_2 has 0.5122, so on these 60 days the two near-duplicate zones do not give the same value. The winner has a daily MAE above the naive forecast on 70 of the 420 days of all zones: 15 in SE_1, 13 in FR and 12 in SE_2. The run times are noisy. On experiment Q the window of 826 days does not apply (entry 89).

## 89. Experiment Q runs the frozen LightGBM setting only
- Date: 2026-11-26, a step of the plan that the owner approved before the work. It was run after the freeze
- Decision: `lgbm_load_826_slow` was scored on the validation days of experiment Q with the same config entry. No other LightGBM candidate was run on experiment Q. The 15-minute frame has one feature more than the hourly frame, `quarter_hour` (entry 75).
- Result: 60 validation days, 5760 quarter-hours per zone, every check passed. The table is the one that `python -m epf.evaluation.tables --experiment Q --split validation` prints. The whole command took 220 seconds, and the peak memory was 301 MB. SE_4 has no usable solar forecast, and SE_1 and SE_2 are near-duplicates.

| Model | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|
| `lgbm_load_826_slow` | 0.5304 | 0.5784 | 0.6227 | 0.6911 | 0.6059 | 0.5040 | 0.5152 | 0.5782 |
| `mstl_182` | 0.6611 | 0.6528 | 0.7160 | 0.7267 | 0.6682 | 0.6617 | 0.6955 | 0.6831 |
| `naive` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

- Reason: One setting per model (entry 59), and the setting is chosen on experiment H (entry 87). The statistical baseline was handled the same way (entry 66).
- Alternative rejected: A second comparison on experiment Q with its own winner. It would give the LightGBM model two settings.
- Checks: A fresh reviewer computed the relative MAE again from the saved Q forecasts and got the saved rows in all seven zones. A fresh fit for the first Q day of the first zone gave the saved forecast exactly. Both results files only grew, by 7 and 420 lines.
- Limits: The window of 826 days never applies on experiment Q. The 15-minute table starts on 2025-10-01, so the model trains on all the 15-minute history there is: 258 training days at the first fit of the validation days and 314 at the last. The Q rows still carry `history_days` 826. The Q value is worse than the H value in every zone, and the mean is 0.5782 against 0.5316. The Q training rows hold no July or August of an earlier year. Whether that is the cause was not measured. The setting was not tuned on the 15-minute prices.

## 90. The frozen LightGBM setting was scored on the test days once
- Date: 2026-11-26, approved by the owner at Stop 4, the planned stop after the freeze
- Decision: The frozen setting was committed first (`2853866`), and then its validation rows on experiment Q (`62b28d6`). Then `lgbm_load_826_slow` was added to `backtest.test_models` (`2ee511a`), and `python -m epf.evaluation.backtest --model lgbm_load_826_slow --split test` was run once, for experiments H and Q. The run started at 16:23 UTC on 2026-11-26. The ten candidates that lost have not seen the test days. The frozen entry was not changed after the run. The run is not repeated without asking the owner.
- Result: 90 test days, 2026-08-22 to 2026-11-19, 2161 hours and 8644 quarter-hours per zone. Every check passed in all seven zones on both experiments. The two tables are those that `python -m epf.evaluation.tables` prints for the test days. SE_4 has no usable solar forecast, and SE_1 and SE_2 are near-duplicates. 7 of the 90 ES test days, 6 to 12 Nov 2026, have no wind and no solar forecast, and the ES values include them.

Experiment H:

| Model | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|
| `lgbm_load_826_slow` | 0.4048 | 0.4854 | 0.5155 | 0.4752 | 0.4296 | 0.5061 | 0.4846 | 0.4716 |
| `mstl_182` | 0.4831 | 0.5151 | 0.6137 | 0.6439 | 0.6486 | 0.5499 | 0.5116 | 0.5666 |
| `naive` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

Experiment Q:

| Model | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|
| `lgbm_load_826_slow` | 0.4028 | 0.4789 | 0.5245 | 0.4936 | 0.4440 | 0.5030 | 0.5079 | 0.4792 |
| `mstl_182` | 0.4901 | 0.5182 | 0.6181 | 0.6496 | 0.6466 | 0.5512 | 0.5101 | 0.5691 |
| `naive` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

- Cost: The whole command took 1179 seconds, about 20 minutes, under the approved ceiling of 60 minutes. The peak memory was 340 MB.
- Checks after the run: `backtest_core.csv` has 14 new lines and `daily_core.csv` has 1260, and no earlier line changed. The files now hold 252 and 16380 rows. The `naive_mae` of the 14 new rows equals the MAE of the saved naive test rows.
- Reading: The mean relative MAE is 0.4716 on H and 0.4792 on Q, against 0.5666 and 0.5691 for `mstl_182`. Both models have a lower relative MAE than on the validation days, for the reason of entry 67: the price of 7 days before was a much worse forecast in the autumn. On experiment H the mean MAE of the naive forecast rose from 29.63 to 54.83 EUR/MWh, and that of the LightGBM setting rose from 15.46 to 25.85. So the model did not become more accurate. The mean is inside the published range of 0.42 to 0.48 (PROJECT_CONTEXT §7, another period and other inputs). DE_LU is 0.4048 on H and 0.4028 on Q, a little below the published value of about 0.42 for that zone. PROJECT_CONTEXT §7 asks to check for leakage first when a number is much better than the range. The evidence against a leak is in entry 85: the tests that fail when a cut moves, and the checks of the training rows. No further search was made for this one value.
- Limits: The test numbers are known from now on. They must not steer any later choice. On experiment Q the window of 826 days does not apply on the test days either: the model trains on 318 days at the first fit and on 402 at the last. The test days hold the clock change of 2026-10-25, and the error of that day was not looked at separately. The solar features of the Swedish zones are empty, and SE_4 has the most solar of them. The quantile forecasts were not scored on the test days (entry 91).

## 91. Quantile forecasts of the frozen setting: five levels, one set of trees per level
- Date: 2026-11-26, design approved by the owner at Stop 4. The owner decided on 2026-11-27 to keep the repeated code and to record it as a limit
- Decision: `backtest.quantile_levels` in the config holds five levels: 0.05, 0.25, 0.50, 0.75 and 0.95. They give the median, an interval that should hold 50% of the prices and one that should hold 90%. `LgbmQuantileModel` in `lgbm.py` fits one set of trees per level with the LightGBM objective `quantile` and `alpha` set to the level. The features, the window, the trees and the learning rate are those of the frozen entry (entry 88). The training rows of a fit are built once and serve all five levels. Each level is fitted on its own, so the five values of a market time unit can cross. The command sorts them per market time unit before it scores them, and reports the share of market time units that sorting changed. `python -m epf.evaluation.quantiles --split validation` scores the validation days of experiments H and Q and writes its rows to a file of its own, `reports/results/quantile_core.csv`. The point rows and the `Model` protocol of the backtest stay as they are. The test days are refused: the name of the quantile model is not under `backtest.test_models`, and adding it needs another yes of the owner.
- Result: The command was run once. It started at 17:04 UTC on 2026-11-26 and took 1109 seconds, about 18 minutes, under the approved ceiling of 60 minutes. Every check passed in all seven zones on both experiments, and the file holds 14 rows. The point files did not change and still hold 252 and 16380 rows. The values below are read from `quantile_core.csv`. Mean pinball is the mean pinball loss over the five levels in EUR/MWh. The coverage is the share of actual prices inside the interval. The crossing share is the share of market time units that sorting changed. SE_4 has no usable solar forecast, and SE_1 and SE_2 are near-duplicates.

| Zone | H mean pinball | H coverage 50% | H coverage 90% | H crossing share | Q mean pinball | Q coverage 50% | Q coverage 90% | Q crossing share |
|---|---|---|---|---|---|---|---|---|
| DE_LU | 5.9865 | 0.3569 | 0.7361 | 0.3132 | 6.3174 | 0.3387 | 0.7372 | 0.3913 |
| FR | 6.5406 | 0.3660 | 0.6840 | 0.2021 | 6.9902 | 0.3234 | 0.6845 | 0.2931 |
| ES | 4.8508 | 0.3500 | 0.6896 | 0.2910 | 5.4789 | 0.3061 | 0.6392 | 0.3648 |
| SE_1 | 3.7212 | 0.4222 | 0.8035 | 0.0924 | 4.2227 | 0.3533 | 0.7913 | 0.1875 |
| SE_2 | 3.7210 | 0.3569 | 0.7493 | 0.1896 | 4.1038 | 0.3241 | 0.7785 | 0.2514 |
| SE_3 | 4.9996 | 0.4382 | 0.8069 | 0.1403 | 5.1431 | 0.3828 | 0.7599 | 0.3200 |
| SE_4 | 7.1718 | 0.4035 | 0.8069 | 0.1903 | 8.0063 | 0.3566 | 0.7387 | 0.3111 |
| Mean | 5.2845 | 0.3848 | 0.7538 | 0.2027 | 5.7518 | 0.3407 | 0.7328 | 0.3027 |

- Reading: The intervals are too narrow in every zone and on both experiments. The interval that should hold 50% of the prices holds 35.0% to 43.8% of them on H and 30.6% to 38.3% on Q. The interval that should hold 90% holds 68.4% to 80.7% on H and 63.9% to 79.1% on Q. Sorting changed about 20% of the hours on H and about 30% of the quarter-hours on Q, so the five separate fits cross often. As a sanity check, twice the pinball loss of level 0.5 is within 0.8 EUR/MWh of the point MAE of the frozen setting in every zone and experiment. A fresh reviewer found that the trees of level 0.5 equal an absolute-error fit of the same entry.
- Reason: Quantile regression for intervals is the method of PROJECT_CONTEXT §6, and the pinball loss and the coverage are the interval metrics of §7. One set of trees per level is what the LightGBM objective offers: one fit has one `alpha`. A file of its own keeps every saved point row as it is.
- Proposed, not yet decided by the owner: `model_params` of a quantile row says `objective: quantile` and holds the levels. The saved quantile forecasts are the sorted values. `crossing_share` counts a market time unit when sorting moved a value, and two equal values do not count. The columns are named `pinball_<level>`, `coverage_<p>` and `width_<p>`. The name of the quantile model is the frozen name plus `_quantiles`. A second run appends rows, as the backtest does.
- Limits: The intervals are reported as they are. They were not widened or calibrated, and a user of the 90% interval must know that it held about 75% of the prices on H. `quantiles.py` repeats about 70 lines of `backtest.py`: the day loop, the zone setup, the group loop, the run values, `run` and `main`. The owner chose to keep this and to leave `backtest.py` untouched. The guard is a test that compares every `DayInputs` of the quantile loop with those of `backtest_zone`. A change of the backtest loop that this test does not see could still make the two loops differ. The pinball loss is in EUR/MWh, so zones cannot be compared on it. The 60 days are one summer. On experiment Q the window of 826 days does not apply (entry 89). The quantile forecasts were not scored on the test days.
