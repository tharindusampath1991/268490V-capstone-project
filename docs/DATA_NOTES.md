# Data notes

How the data is obtained, cleaned and validated. This file grows as each pipeline step is built.

## ENTSO-E client behaviour

Read from the installed `entsoe-py` 1.0.0 source on 2026-11-20. Only the points under "Smoke test" below are confirmed against a real response.

Smoke test on 2026-11-20: DE_LU, delivery day 2026-11-18, through `call_entsoe` and `fetch_prices`.

- The token was accepted. Every request returned HTTP 200.
- The client returned a float series with no name and a Europe/Berlin index. It had 97 values, from 2026-11-18 00:00 to 2026-11-19 00:00, so the end timestamp is included.
- `fetch_prices` returned 96 rows with a UTC index, from 2026-11-17 23:00 to 2026-11-18 22:45. `check_prices` found 0 missing, 0 unexpected and 0 repeated timestamps.
- One price query cost 2 requests. The second request asks for the next page of documents and gets the "no data" answer with HTTP 200.

- `EntsoePandasClient.query_day_ahead_prices` returns one series per call. It keeps hourly values before 2025-10-01 and 15-minute values from that date. The switch is defined in Europe/Amsterdam time. The `resolution` argument is deprecated and has no effect.
- Before the switch, the client merges every resolution it received and keeps the first value in each hour. From the switch, it keeps all values without resampling. Duplicate timestamps within a year block are collapsed to the last valid value. The returned series carries no resolution marker.
- For DE_LU the client requests auction sequence 1 only.
- The returned index is in the zone's local time zone: Europe/Berlin for DE_LU, Europe/Paris for FR, Europe/Madrid for ES, Europe/Stockholm for SE_1 to SE_4.
- The end timestamp of a query is included in the result.
- A price query is split into blocks of at most one year, and each block is fetched 100 documents at a time. The client also pads each query by one day at both ends. One zone and year therefore costs several requests.
- Load forecast and wind and solar forecast queries are split into one request per month.
- The client makes up to 3 attempts, 60 seconds apart, and only for connection errors and HTTP 527 or 599. It has no timeout unless one is passed.
- The client masks the token in the messages of HTTP and connection errors. The exception object still holds the request, and the request URL contains the token.
- The production type names in the library are Solar, Wind Offshore and Wind Onshore. The live test under "Forecast downloads" confirmed these names for DE_LU and SE_3.
- Observed on 2026-11-20 with numpy 2.5.5 and pandas 2.3.3: `pd.Timedelta(days=1)` raises a DeprecationWarning about the 'generic' NumPy timedelta unit, which "will raise an error in the future". `query_day_ahead_prices` calls `pd.Timedelta(days=1)`. numpy is not pinned in `requirements.txt`. Project code uses `datetime.timedelta` for day steps.

## Raw price format

Decided on 2026-11-20 (DECISIONS entry 10): the raw price files hold the pandas client output, with the index in UTC.

The client hides which resolution each value came from (second bullet above), so the project checks the result itself:

- The index has no duplicate timestamps.
- Each delivery day has the expected number of values: 24 hourly values before the switch and 96 quarter-hour values from it. Clock-change days have 23 or 25 hours, and 92 or 100 quarter-hours.

The checks are in `check_prices` in `src/epf/data/download_prices.py`. The downloader prints these counts per zone and year: expected and missing market time units, delivery days with gaps, prices at unexpected times and repeated timestamps. It reports the counts and does not change the data.

First full run on 2026-11-20, delivery days 2019-01-01 to 2026-11-19, 7 zones:

- 56 files, one per zone and year. The run took 82 minutes. The client retried three requests on its own (HTTP 599 twice, one connection error).
- Every zone and year had all expected values: 8760 or 8784 in the hourly years, 15387 in 2025 and 31008 in 2026.
- No missing value, no price at an unexpected time and no repeated timestamp in any zone or year.

Refresh on 2026-11-22 at 10:13 market time, delivery days 2019-01-01 to 2026-11-21:

- Only the seven 2026 files were downloaded again. The run took 6 minutes.
- Every zone has all expected values in 2019 to 2025. No file has a price at an unexpected time or a repeated timestamp.
- ES and SE_1 to SE_4 are complete to 2026-11-21, with 31200 values in 2026.
- DE_LU has no price for delivery days 2026-11-20 and 2026-11-21, which is 192 values. FR has none for 2026-11-21, which is 96 values. Asked one day at a time at 10:20, ENTSO-E returned 96 prices for DE_LU on 2026-11-19 and for FR on 2026-11-20, and none for the later days. These days were not yet available through the client. They are the newest days, not gaps inside the history.
- On this data the last delivery day that is complete in all zones is 2026-11-19.
- No price in the period of the cross-check changed. The 2026 files before and after the refresh hold the same values up to delivery day 2026-11-19, and these still equal the saved Energy-Charts prices in all seven zones. The cross-check was therefore not run again.

Before the switch the client resamples each answer to hourly values with `resample('h').first()` (read from the source). A missing hour inside an answer can therefore arrive as a row with an empty price. The check counts an empty price as missing.

## Raw ENTSO-E cache

Built on 2026-11-20 in `src/epf/data/entsoe_cache.py`. The price download, the coverage gate and the Energy-Charts cross-check use it.

- One Parquet file per dataset, zone and year: `{dataset}/{ZONE}_{YEAR}.parquet` under the cache folder. The cache folder is `data/raw/entsoe/` (DECISIONS entry 5).
- `manifest.json` in the cache folder has one entry per saved file: query start, query end, download time, row count and `entsoe-py` version. All times are in UTC.
- A saved file is reused only when the manifest shows the same query start and end. A partial year is downloaded again when the requested end moves.
- An empty answer is never saved. It is asked again on the next run.
- A saved file that was deleted by hand is downloaded again.

## Forecast downloads

Read from the installed `entsoe-py` 1.0.0 source on 2026-11-20. Code: `src/epf/data/download_forecasts.py`.

- `query_load_forecast` uses process type A01 (day ahead) by default and returns one column, `Forecasted Load`.
- `query_wind_and_solar_forecast` uses process type A01 by default and returns one column per production type. Its parser drops repeated timestamps within a series and keeps the first value.
- Both queries cost one request per month. Both return local time and include the end timestamp.
- The project stores each forecast frame as the client returns it, with the index in UTC and cut to [start, end). Repeated timestamps are kept in the raw file. The coverage gate counts them.

Live test on 2026-11-20, delivery days 2026-11-01 to 2026-11-03, 4 requests, all HTTP 200:

- DE_LU load forecast: column `Forecasted Load`, 15-minute values, 288 rows, every hour present.
- DE_LU wind and solar forecast: columns `Solar`, `Wind Offshore` and `Wind Onshore`, 15-minute values.
- SE_3 load forecast: column `Forecasted Load`, 15-minute values.
- SE_3 wind and solar forecast: columns `Solar` and `Wind Onshore`, 15-minute values. So a Swedish solar forecast exists for these days. Its coverage over all years is a result of the coverage gate.
- No repeated timestamp in these four answers.

The command `python -m epf.data.download_forecasts` downloads both datasets for all zones through the cache, core zones first. It prints one line per zone, dataset, year and column: rows in the file, the most common step, expected hours, missing hours and repeated timestamps. It changes no value. The check behind it is `hourly_coverage`, the same one the coverage gate uses.

First run on 2026-11-22 at 10:23 market time, delivery days 2019-01-01 to 2026-11-21:

- 112 files, 56 per dataset. The 14 files of 2026 were downloaded again, which is 154 monthly requests by the client's month split. The other 98 were read from the cache. The run took 22 minutes.
- No repeated timestamp in any file.
- The load forecast has no missing hour in 2026 in any zone, up to 2026-11-21.
- Missing hours in the 2026 wind and solar files: ES 480 for `Wind Onshore` and 216 for `Solar`, FR 25 for `Solar` and `Wind Onshore` and 1 for `Wind Offshore`, each Swedish zone 72 for `Wind Onshore` and `Solar`. The 480 ES hours are the 20 days of DECISIONS entry 19.
- Unit, read from the raw answers for DE_LU and FR on delivery day 2026-11-10: ENTSO-E states `MAW` (megawatt) for the actual load, the load forecast and the wind and solar forecast.
- Most common step per file. DE_LU: 15-minute in all years. FR load forecast: hourly to 2024, 15-minute from 2025. FR wind and solar: hourly to 2025, 15-minute in 2026. ES: hourly to 2021, 15-minute from 2022. SE_1 to SE_4: hourly to 2025, 15-minute in 2026. A file that changes resolution inside the year shows the more common step, for example ES 2022 and the Swedish zones in 2025.

## Energy-Charts price cross-check

Checked against the live API and its endpoint catalogue (`https://api.energy-charts.info/openapi.json`) on 2026-11-20. Code: `src/epf/data/download_energy_charts.py` and `src/epf/data/crosscheck_prices.py`.

- Endpoint: `/v2/price` with the parameters `bzn`, `start` and `end`. A day such as `2026-11-18` is read in the zone's local time. With `start` equal to `end` the API returned the 96 values of that day, so the end day is included.
- Each record has a timestamp with its UTC offset and the value `day_ahead_price`. The unit is `EUR / MWh`.
- A full year in one request works. DE-LU 2019 returned 8760 records and DE-LU 2025 returned 15387, hourly before 2025-10-01 and 15-minute from then.
- Licence, as stated in the `license` field of each answer:
  - DE-LU, FR and SE4: CC BY 4.0 from Bundesnetzagentur | SMARD.de.
  - ES, SE1, SE2 and SE3: "for private and internal use only". External use of the data "in its raw or derived form" is prohibited.
- All zones are free to query. The cross-check downloads all seven zones (DECISIONS entry 12). Each saved file has a column `open_licence`, which is true when the answer stated CC BY 4.0. Results for DE_LU, FR and SE_4 go into `docs/price_crosscheck.md`. Results for ES, SE_1, SE_2 and SE_3 go only into `data/local/price_crosscheck_restricted.md`, which git ignores.
- Rate limit, from the catalogue: 2 price requests per minute per client. A request over the limit gets HTTP 429 with a `Retry-After` header. Observed: a 429 on the sixth request when requests were 6 seconds apart. The code waits 31 seconds before each request and honours `Retry-After` once.
- Energy-Charts answers are saved under `data/raw/energy_charts/prices/` through the same cache code. The manifest field `entsoe_py_version` has no meaning for these files.

Result of the full run on 2026-11-20, delivery days 2019-01-01 to 2026-11-19 (`docs/price_crosscheck.md`):

- DE_LU, FR and SE_4: every ENTSO-E timestamp had an Energy-Charts price, in all 8 years. No pair differed by more than 0.01 EUR/MWh, and the largest difference was 0.00. Neither source had a timestamp the other lacked.
- ES, SE_1, SE_2 and SE_3 were checked in the same run. Their results are in the local file only.
- An exact match suggests that both sources draw on the same upstream data. The check therefore mainly confirms the zone mapping, the time alignment and the handling of the 15-minute switch in this pipeline. It is not an independent measurement of the prices.
- The run needed 56 requests at 2 per minute, about 30 minutes in total.

## Coverage gate results

The first full run was on 2026-11-20. It took 4 hours 19 minutes, and the client retried 5 requests on its own. The run was repeated on 2026-11-21 with the rules of DECISIONS entry 19. That run took 28 minutes, because only the 2026 files were downloaded again. The numbers below are from the second run, delivery days 2019-01-01 to 2026-11-20 (`docs/coverage_gate.md`).

- All four Swedish zones pass. In every year their prices are at 100%, the load forecast is at 99.73% or more and the wind forecast at 99.07% or more.
- The four Swedish zones have the same coverage shares in every year. In the 2024 files the timestamps are the same in all four zones and the values differ: the mean load forecast is 1276, 1822, 9530 and 2510 MW for SE_1 to SE_4.
- Swedish `Solar` forecast: no data in 2019 and 2020, 8.22% of hours in 2021, and 99.07% or more from 2022. It is marked drop, because the rule needs 95% in every year.
- FR `Wind Offshore`: no data before 2023, 40.29% in 2023, and 99.99% or more from 2024. Marked drop for the same reason.
- ES `Wind Onshore`: 99.73% or more from 2019 to 2025, and 93.83% in 2026. In the files of 2026-11-20 the gap was 20 whole days, 480 hours, in 9 blocks: 2 Feb, 13 to 17 Feb, 20 Feb, 16 to 17 Mar, 27 Mar, 30 Mar, 11 Jun, 16 Jun and 6 to 12 Nov. The column is kept by decision (entry 19). The days stay missing in the raw data.
- ES `Solar` is at 97.22% in 2026.
- DE_LU prices: on 2026-11-21 at 05:41 market time ENTSO-E had no DE_LU price for delivery day 2026-11-20, while FR had all 96 values. Delivery day 2026-11-19 was complete for both. So the newest DE_LU day can arrive later than in other zones. `DATA_END` must be a day that is complete in all zones.
- No dataset in any zone has a repeated timestamp.
- DE_LU forecasts are 15-minute in all years. In the other zones some years are hourly and some are 15-minute.

## Time handling

Built on 2026-11-22 in `src/epf/data/resolution.py` (DECISIONS entries 20 to 22). The functions work in UTC, where every hour has four quarter-hours and a clock-change day is 23 or 25 hours long. They fill no gap and write no file.

- `check_utc_index` refuses an index that is not a time index in UTC, is not sorted or repeats a timestamp. The functions below call it first. The raw price and forecast files of 2026-11-22 pass it in all seven zones.
- Experiment H uses `hourly_prices`: the hourly prices before 2025-10-01 unchanged, then the mean of the four quarter-hour prices of each hour. An hour with fewer than four prices stays empty.
- Experiment Q uses `quarter_hour_prices`: the 15-minute prices from 2025-10-01, unchanged.
- Covariates to the hourly grid, `align_to_hours`, per column and hour: one value at minute 0 is kept, four quarter-hour values give their mean, anything else stays empty.
- Covariates to the 15-minute grid, `align_to_quarter_hours`, per column and hour: one value at minute 0 is repeated on the four quarter-hours, every other value stays at its own time. Nothing is interpolated.

Run over the raw files of 2026-11-22, delivery days 2019-01-01 to 2026-11-21. The period has 69168 hours, and 40036 quarter-hours from 2025-10-01.

- Prices: ES and SE_1 to SE_4 give 69168 hourly values and 40036 15-minute values. DE_LU gives 69120 and 39844, FR gives 69144 and 39940. The difference is the newest days that ENTSO-E had not published (see "Raw price format"). No hour came out empty.
- DE_LU on single days, as raw, hourly and 15-minute values: 2025-03-30 has 23, 23 and 0. 2025-09-30 has 24, 24 and 0. 2025-10-01 has 96, 24 and 96. 2025-10-26 and 2026-10-25 have 100, 25 and 100. 2026-03-29 has 92, 23 and 92.
- Forecasts: in every zone and column, every hour with data holds either one value at minute 0 or four values. No hour holds two or three. On this data the aligned hourly value is therefore equal to the plain hourly mean that the coverage gate uses. The largest difference is 0.0.
- The rule works per hour because files change resolution. The FR load forecast, for example, has 52585 hours with one value and 16583 hours with four.
- On the 15-minute grid from 2025-10-01, DE_LU and ES have 15-minute forecasts throughout, so no value is repeated. FR and the Swedish zones are hourly for part of that period. The FR `Solar` forecast has 32804 raw values there and 39932 after repetition. The Swedish load forecast has 35473 and 39940.
