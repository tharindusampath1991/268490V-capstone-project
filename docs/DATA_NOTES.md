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
- Observed on 2026-11-20 with numpy 2.5.5 and pandas 2.3.3: `pd.Timedelta(days=1)` raises a DeprecationWarning about the 'generic' NumPy timedelta unit, which "will raise an error in the future". `query_day_ahead_prices` calls `pd.Timedelta(days=1)`. numpy is therefore pinned to 2.5.5 in `requirements.txt` (DECISIONS entry 3). Project code uses `datetime.timedelta` for day steps.

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

Check on 2026-11-23 at 01:27 market time, delivery days up to 2026-11-22. The coverage gate downloaded the 2026 price files again.

- DE_LU and FR now have delivery day 2026-11-22. DE_LU still has no price for 2026-11-20 and 2026-11-21, and FR has none for 2026-11-21. These days are therefore holes with later data after them. The note of 2026-11-22 above took them for days that were only late.
- DE_LU, raw answers at 01:50: ENTSO-E holds two price series per day, marked sequence 1 and sequence 2. The client asks for sequence 1 (see "ENTSO-E client behaviour"). Sequence 1 exists for 2026-11-19 and 2026-11-22 and is absent for 2026-11-20 and 2026-11-21. Sequence 2 exists for all four days.
- Sequence 2 is a different auction and cannot replace sequence 1. From 2026-11-12 to 2026-11-22 both exist on 9 days. On those days no quarter-hour has the same price in both, and the largest difference within a day lies between 15.28 and 124.99 EUR/MWh.
- FR, raw answer at 01:50: there is no price series for 2026-11-21.
- Energy-Charts, asked at the same time: it has 96 DE-LU prices on 2026-11-20 and on 2026-11-21, with day means of 214.51 and 187.88 EUR/MWh. Its DE-LU day means for 2026-11-19 and 2026-11-22, 224.83 and 204.08, equal those of ENTSO-E sequence 1. It has no FR price for 2026-11-21.
- So the DE_LU prices of the two days exist, but ENTSO-E had not published them in the series this project uses. Energy-Charts values are not used to fill ENTSO-E (DECISIONS entry 7). The three zone-days stay missing in the raw data.
- The last delivery day before the holes that is complete in all zones is 2026-11-19.
- No price in the period of the cross-check changed between 2026-11-22 and 2026-11-23, so the cross-check was not run again.

Before the switch the client resamples each answer to hourly values with `resample('h').first()` (read from the source). A missing hour inside an answer can therefore arrive as a row with an empty price. The check counts an empty price as missing.

## Raw ENTSO-E cache

Built on 2026-11-20 in `src/epf/data/entsoe_cache.py`. The price, forecast, actual load and weather downloads, the coverage gate and the Energy-Charts cross-check use it.

The same code serves three cache folders, each with its own `manifest.json`:

- `data/raw/entsoe/` for prices, load forecast, wind and solar forecast and actual load (DECISIONS entry 5).
- `data/raw/open_meteo/` for the weather forecasts.
- `data/raw/energy_charts/` for the cross-check prices.

Only one download per cache folder may run at a time: each run reads the manifest, downloads, then writes the manifest, so two runs at once would lose entries. The four ENTSO-E datasets and the coverage gate share the first folder.

- One Parquet file per dataset, zone and year: `{dataset}/{ZONE}_{YEAR}.parquet` under the cache folder.
- `manifest.json` in the cache folder has one entry per saved file: query start, query end, download time, row count and `entsoe-py` version. All times are in UTC. The version field has no meaning in the Open-Meteo and Energy-Charts manifests.
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

## Actual load

Read from the installed `entsoe-py` 1.0.0 source on 2026-11-22. Code: `src/epf/data/download_actual_load.py` (DECISIONS entry 24).

- `EntsoePandasClient.query_load` asks for document type A65 with process type A16 (realised). It returns one column, `Actual Load`, in local time, and includes the end timestamp. It costs one request per month.
- The project stores the frame as the client returns it, with the index in UTC and cut to [start, end), as the dataset `actual_load`.
- Leakage rule: actual load is measured after delivery. A forecast for delivery day D may use it through day D-2 only (PROJECT_CONTEXT §5). The download does not apply this cut. The feature builder must.

Full pull with `python -m epf.data.download_actual_load` on 2026-11-22, from 10:45 to 11:58 market time, delivery days 2019-01-01 to 2026-11-21:

- 56 files, one per zone and year, 961826 rows. 714 monthly requests by the client's month split. The run took 73 minutes, and the client retried one request on its own after a connection error.
- No repeated timestamp in any file. Every file passes `check_utc_index`.
- Hours without any value: none in DE_LU and in SE_1 to SE_4. FR has 8, 2, 9, 21, 5, 0, 3 and 0 in the years 2019 to 2026. ES has 35 in 2025 and none in the other years.
- All seven zones have actual load up to 2026-11-21 with no missing hour in 2026.
- Most common step per file: the same pattern as the load forecast. DE_LU is 15-minute in all years, FR is hourly to 2024 and 15-minute from 2025, ES is hourly to 2021 and 15-minute from 2022, the Swedish zones are hourly to 2025 and 15-minute in 2026.
- Unlike the forecasts, the actual load has hours that are partly filled. FR has 2 such hours, both on 2025-12-10 (14:00 and 18:00 UTC, with 2 and 3 values). ES has 6: 2023-11-21 19:00, 2024-10-11 00:00, 2025-04-28 10:00, 2026-06-11 08:00, 2026-10-25 00:00 and 2026-11-17 05:00 UTC, each with 2 or 3 values. `align_to_hours` leaves these 8 hours empty (DECISIONS entry 22). The coverage count above treats them as present, because it counts an hour with any value.

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

The first full run was on 2026-11-20. It took 4 hours 19 minutes, and the client retried 5 requests on its own. The run was repeated on 2026-11-21 with the rules of DECISIONS entry 19. That run took 28 minutes, because only the 2026 files were downloaded again. The numbers in the first list below are from the second run, delivery days 2019-01-01 to 2026-11-20. `docs/coverage_gate.md` now holds a third run, described after that list.

- All four Swedish zones pass. In every year their prices are at 100%, the load forecast is at 99.73% or more and the wind forecast at 99.07% or more.
- The four Swedish zones have the same coverage shares in every year. In the 2024 files the timestamps are the same in all four zones and the values differ: the mean load forecast is 1276, 1822, 9530 and 2510 MW for SE_1 to SE_4.
- Swedish `Solar` forecast: no data in 2019 and 2020, 8.22% of hours in 2021, and 99.07% or more from 2022. It is marked drop, because the rule needs 95% in every year.
- FR `Wind Offshore`: no data before 2023, 40.29% in 2023, and 99.99% or more from 2024. Marked drop for the same reason.
- ES `Wind Onshore`: 99.73% or more from 2019 to 2025, and 93.83% in 2026. In the files of 2026-11-20 the gap was 20 whole days, 480 hours, in 9 blocks: 2 Feb, 13 to 17 Feb, 20 Feb, 16 to 17 Mar, 27 Mar, 30 Mar, 11 Jun, 16 Jun and 6 to 12 Nov. The column is kept by decision (entry 19). The days stay missing in the raw data.
- ES `Solar` is at 97.22% in 2026.
- DE_LU prices: on 2026-11-21 at 05:41 market time ENTSO-E had no DE_LU price for delivery day 2026-11-20, while FR had all 96 values. Delivery day 2026-11-19 was complete for both. At the time this was read as a DE_LU day that arrives later than in other zones. The check of 2026-11-23 under "Raw price format" showed that the day is a hole: later days are present and this one is not. `DATA_END` must be a day that is complete in all zones.
- No dataset in any zone has a repeated timestamp.
- DE_LU forecasts are 15-minute in all years. In the other zones some years are hourly and some are 15-minute.

Third run on 2026-11-23, delivery days 2019-01-01 to 2026-11-22. It took 23 minutes, because the 21 price and forecast files of 2026 were downloaded again.

- All four Swedish zones pass again. Their lowest yearly shares are 100% for prices, 99.73% for the load forecast and 99.08% for the wind forecast.
- No gate verdict and no keep or drop mark changed against the second run.
- DE_LU prices are at 99.39% in 2026 and FR prices at 99.69%. These are the missing days described under "Raw price format".
- ES `Wind Onshore` is at 93.87% in 2026 and stays "keep by decision". ES `Solar` is at 97.24%.
- No dataset in any zone has a repeated timestamp.

## Weather forecasts

Read from the Open-Meteo docs on 2026-11-22 (Single Runs API, ECMWF API, pricing and licence pages) and checked against live answers. Code: `src/epf/data/download_weather.py` (DECISIONS entries 25 to 28).

What the docs state:

- The Single Runs API returns one model run per request. `run=` is the initialisation time in UTC, for example `2026-11-15T00:00`. It is not the time the forecast was published.
- A 00 UTC run of a global model is "generally accessible from approximately 04–06 UTC onwards". This project did not measure it.
- ECMWF IFS HRES at 9 km is archived from March 14, 2024, described as "IFS Cycle 49R1 hindcasts". All other models are archived from 2 April 2026. The model has hourly steps up to 90 hours.
- `shortwave_radiation` is the mean over the hour before the timestamp. Temperature and wind speed are values at the timestamp.
- Free use is limited to 600 calls per minute, 5000 per hour and 10000 per day. The data licence is CC BY 4.0, with the credit "Weather data by Open-Meteo.com".

What the live answers showed:

- Times are in UTC without an offset, and the answer says so (`utc_offset_seconds` 0). The first step is the run time. `forecast_hours=48` returned 48 hourly steps.
- Units in the answer: °C, m/s (asked with `wind_speed_unit=ms`) and W/m². The radiation of the first step of a run is empty.
- The run of 2024-03-14 00:00 UTC was answered. The run of 2024-03-13 was refused with HTTP 400, "The requested model run is not available".
- The request for Kassel (51.32, 9.50) was answered from the grid cell at 51.35325, 9.422382, elevation 158 m.

What is stored: for delivery day D, the hours of D from the 00:00 UTC run of D-1, with the run time in the column `run`. Files are `data/raw/open_meteo/weather_forecast/{ZONE}_{YEAR}.parquet`.

Full download with `python -m epf.data.download_weather` on 2026-11-22, from 10:58 to 15:29 market time, delivery days 2024-03-15 to 2026-11-21:

- The first attempt stopped after one minute with a connection error. A test of 49 requests had one connection reset by the remote host, and the same request then worked. The downloader now asks again after a dropped connection (DECISIONS entry 28). It does not count how often that happened.
- 21 files, one per zone and year, 164976 rows. Each zone has 982 runs and 23568 rows. That is 6874 requests answered with data, one second apart. The run took 4 hours 31 minutes.
- Every run is the 00:00 UTC run. The hours of a delivery day start 22 to 46 hours after their run.
- Every hour of every delivery day has a row in every zone. No repeated timestamp.
- `temperature_2m` and `wind_speed_10m` are empty for the 24 hours of delivery day 2026-06-24, from the run of 2026-06-23, in all seven zones. `wind_speed_100m` and `shortwave_radiation` have values on that day. The empty values stay empty.
- No other value is missing.
- While `data.end` is not set, a run on a later day downloads the 2026 file of each zone again, which was 325 requests per zone on 2026-11-22. One full download uses about 6900 of the 10000 calls per day.

## Time handling

Built on 2026-11-22 in `src/epf/data/resolution.py` (DECISIONS entries 20 to 22). The functions work in UTC, where every hour has four quarter-hours and a clock-change day is 23 or 25 hours long. They fill no gap and write no file.

- `check_utc_index` refuses an index that is not a time index in UTC, is not sorted or repeats a timestamp. The functions below call it first. The raw price and forecast files of 2026-11-22 pass it in all seven zones.
- Experiment H uses `hourly_prices`: the hourly prices before 2025-10-01 unchanged, then the mean of the four quarter-hour prices of each hour. An hour with fewer than four prices stays empty.
- Experiment Q uses `quarter_hour_prices`: the 15-minute prices from 2025-10-01, unchanged.
- Covariates to the hourly grid, `align_to_hours`, per column and hour: one value at minute 0 is kept, four quarter-hour values give their mean, anything else stays empty.
- Covariates to the 15-minute grid, `align_to_quarter_hours`, per column and hour: one value at minute 0 is repeated on the four quarter-hours, every other value stays at its own time. Nothing is interpolated.
- Limit of both alignment functions: they count values, not rows. An hour whose only value is at minute 0 counts as an hourly value, also when the file has empty rows for the other three quarter-hours. A column cannot show the difference, because an hourly column beside a 15-minute column looks the same. Measured on 2026-11-23 over the raw load forecast, wind and solar forecast and actual load files of all seven zones, 2019 to 2026: no hour has one value at minute 0 next to other rows in the same hour. Every hour with one value has one row. So the case does not occur in this data.

Run over the raw files of 2026-11-22, delivery days 2019-01-01 to 2026-11-21. The period has 69168 hours, and 40036 quarter-hours from 2025-10-01.

- Prices: ES and SE_1 to SE_4 give 69168 hourly values and 40036 15-minute values. DE_LU gives 69120 and 39844, FR gives 69144 and 39940. The difference is the newest days that ENTSO-E had not published (see "Raw price format"). No hour came out empty.
- DE_LU on single days, as raw, hourly and 15-minute values: 2025-03-30 has 23, 23 and 0. 2025-09-30 has 24, 24 and 0. 2025-10-01 has 96, 24 and 96. 2025-10-26 and 2026-10-25 have 100, 25 and 100. 2026-03-29 has 92, 23 and 92.
- Forecasts: in every zone and column, every hour with data holds either one value at minute 0 or four values. No hour holds two or three. On this data the aligned hourly value is therefore equal to the plain hourly mean that the coverage gate uses. The largest difference is 0.0.
- The rule works per hour because files change resolution. The FR load forecast, for example, has 52585 hours with one value and 16583 hours with four.
- On the 15-minute grid from 2025-10-01, DE_LU and ES have 15-minute forecasts throughout, so no value is repeated. FR and the Swedish zones are hourly for part of that period. The FR `Solar` forecast has 32804 raw values there and 39932 after repetition. The Swedish load forecast has 35473 and 39940.

## Preprocessing

Code: `src/epf/data/clean.py`, `src/epf/data/validate.py` and `src/epf/data/build_dataset.py` (DECISIONS entries 29 to 35). One command rebuilds the tables from the raw cache:

    .venv\Scripts\python -m epf.data.build_dataset

It cleans the raw files, writes the tables under `data/processed/` and validates them. `python -m epf.data.clean` and `python -m epf.data.validate` run the first and the last step alone. All three stop with a message when `data.end` is not set.

### Period and splits

`DATA_END` was frozen on 2026-11-24 at delivery day 2026-11-19 (DECISIONS entry 29). ENTSO-E was asked six times between 2026-11-23 02:55 and 2026-11-24 04:38 market time. It had no DE_LU price for 2026-11-20 and 2026-11-21 and no FR price for 2026-11-21 each time, while it published the delivery days 22, 23 and 24 November.

| Split | Delivery days | Count |
|---|---|---|
| Train, experiment H | 2019-01-01 to 2026-06-22 | 2730 |
| Train, experiment Q | 2025-10-01 to 2026-06-22 | 265 |
| Train, weather sub-experiment | 2024-03-15 to 2026-06-22 | 830 |
| Validation | 2026-06-23 to 2026-08-21 | 60 |
| Test | 2026-08-22 to 2026-11-19 | 90 |

The 25-hour day 2026-10-25 lies in the test set.

### Download to `DATA_END`

On 2026-11-24, with `data.end` set, the 2026 file of every dataset and zone was downloaded again. The files of earlier years were read from the cache.

- Prices: 7 files in 236 seconds. Each has 31008 of 31008 values, with no price at an unexpected time and no repeated timestamp.
- Load forecast and wind and solar forecast: 14 files in 958 seconds. Missing hours in 2026: ES 480 for `Wind Onshore` and 216 for `Solar`, FR 25 for `Solar` and `Wind Onshore` and 1 for `Wind Offshore`, each Swedish zone 72 for `Wind Onshore` and `Solar`. No repeated timestamp.
- Actual load: 7 files in 420 seconds. No hour of 2026 is without a value.
- Weather: 7 files in 5095 seconds, 323 runs and 7752 rows per zone. `temperature_2m` and `wind_speed_10m` are empty for the 24 hours of 2026-06-24 in every zone. Nothing else is missing.
- Every 2026 entry in the three manifests now has the query end 2026-11-19 23:00 UTC: 28 in `entsoe`, 7 in `open_meteo` and 7 in `energy_charts`.
- Price cross-check, run again for all seven zones. DE_LU, FR and SE_4: 24 zone-years and 297009 compared prices. No pair differs by more than 0.01 EUR/MWh and neither source has a timestamp the other lacks. `docs/price_crosscheck.md` did not change, because it already covered 2019-01-01 to 2026-11-19. The results for ES, SE_1, SE_2 and SE_3 are in the local file only (DECISIONS entry 12).
- Coverage gate, run again: `docs/coverage_gate.md` now covers 2019-01-01 to 2026-11-19. SE_1 to SE_4 pass. No verdict and no keep or drop mark changed. ES `Wind Onshore` is at 93.81% in 2026.
- One value changed against the files of 2026-11-22: the ES actual load for the hour 2026-11-17 05:00 UTC now has all four quarter-hour values. It had three.

### Cleaning rules

The owner approved these rules on 2026-11-23 (DECISIONS entries 30 and 31). No rule fills, clips or removes a value inside the period. Negative prices and spikes stay. No statistic is computed from validation or test data.

| Rule | What the cleaning step does |
|---|---|
| Index | Refuses a file whose index is not UTC, not sorted or repeats a timestamp. No raw file repeats one |
| Period | Removes rows outside 2019-01-01 to 2026-11-19. Weather starts on 2024-03-15 |
| Grid | Refuses a value at a time that is not on the time grid of its dataset |
| Prices | Refuses a zone that does not have exactly one price per market time unit |
| Dropped columns | Leaves out FR `Wind Offshore` and the `Solar` forecast of SE_1 to SE_4, the columns the gate marks drop (`coverage_gate.drop_columns`) |
| Names | Renames `Forecasted Load`, `Wind Onshore`, `Wind Offshore`, `Solar` and `Actual Load` to `load_forecast`, `wind_onshore_forecast`, `wind_offshore_forecast`, `solar_forecast` and `actual_load` |
| Gaps | Leaves every empty or missing value empty |

Counts from `python -m epf.data.clean` on 2026-11-24, in values that are not empty:

- Outside the period: 0 in every dataset and zone, because the raw files now end on `DATA_END`.
- Dropped columns: 51501 values of FR `Wind Offshore` and 69048 values of `Solar` in each Swedish zone.
- Prices kept: 99003 per zone, one for each market time unit of the period.

### Tables

`build_dataset` writes 21 Parquet files, about 23 MB in total, in 3 seconds. Every table has a UTC index and one row per time step, also where all values are empty.

| Table | File | Time step | First delivery day | Rows per zone |
|---|---|---|---|---|
| Experiment H | `data/processed/hourly/{ZONE}.parquet` | 1 hour | 2019-01-01 | 69120 |
| Experiment Q | `data/processed/quarter_hour/{ZONE}.parquet` | 15 minutes | 2025-10-01 | 39844 |
| Weather | `data/processed/weather/{ZONE}.parquet` | 1 hour | 2024-03-15 | 23520 |

- Columns of the H and Q tables: `price` in EUR/MWh, then `load_forecast`, `wind_onshore_forecast`, `wind_offshore_forecast`, `solar_forecast` and `actual_load` in MW. DE_LU has all six. FR and ES have no `wind_offshore_forecast`. The Swedish zones have neither `wind_offshore_forecast` nor `solar_forecast`.
- Experiment H: `hourly_prices` and `align_to_hours`. From 2025-10-01 the price of an hour is the mean of its four quarter-hour prices.
- Experiment Q: `quarter_hour_prices` and `align_to_quarter_hours`. An hourly forecast value is repeated on its four quarter-hours.
- Weather columns: `temperature_2m`, `wind_speed_10m`, `wind_speed_100m`, `shortwave_radiation` and `run`, as downloaded. `run` is the start time of the model run. Weather is not put on the 15-minute grid.
- `actual_load` stands at its own delivery time. A forecast for delivery day D may use it through D-2 only (PROJECT_CONTEXT §5). The feature builder must apply that cut.
- `shortwave_radiation` is the mean of the hour before its timestamp. The ENTSO-E values apply from their timestamp on. The feature builder must line them up.

### Gaps that stay empty

Counts from the build of 2026-11-24. 48 of the 99 table columns have at least one empty value. `price` has none in any zone or table. `config/approved_gaps.yaml` holds the count of every column, and the validation fails when a built table differs (DECISIONS entry 34).

| Zone | Column | Hourly table: empty hours (train, validation, test) | 15-minute table: empty quarter-hours (train, validation, test) |
|---|---|---|---|
| DE_LU | `load_forecast` | 50 (50, 0, 0) | 0 |
| DE_LU | `solar_forecast` | 3 (3, 0, 0) | 4 (4, 0, 0) |
| DE_LU | `wind_onshore_forecast` | 3 (3, 0, 0) | 4 (4, 0, 0) |
| FR | `solar_forecast` | 377 (376, 0, 1) | 104 (100, 0, 4) |
| FR | `wind_onshore_forecast` | 351 (350, 0, 1) | 104 (100, 0, 4) |
| FR | `actual_load` | 50 (50, 0, 0) | 15 (15, 0, 0) |
| ES | `load_forecast` | 1 (1, 0, 0) | 0 |
| ES | `solar_forecast` | 337 (169, 0, 168) | 864 (192, 0, 672) |
| ES | `wind_onshore_forecast` | 553 (385, 0, 168) | 1920 (1248, 0, 672) |
| ES | `actual_load` | 40 (39, 0, 1) | 3 (1, 0, 2) |
| SE_1 to SE_4, each | `load_forecast` | 24 (24, 0, 0) | 96 (96, 0, 0) |
| SE_1 to SE_4, each | `wind_onshore_forecast` | 216 (192, 24, 0) | 480 (384, 96, 0) |

In the weather table of every zone, `temperature_2m` and `wind_speed_10m` are empty for the 24 hours of 2026-06-24, which lies in the validation set.

What the gaps are:

- ES `wind_onshore_forecast`: 24 delivery days, 23 of them without any value. 20 are the days of 2026 named under "Coverage gate results". The other four are 2020-01-05, 2022-10-30, 2024-06-02 and 2025-03-31.
- ES `solar_forecast`: 15 delivery days: 2022-10-30, 2024-12-07 to 2024-12-11, 2026-06-11, 2026-06-16 and 2026-11-06 to 2026-11-12.
- So 7 of the 90 ES test days, 6 to 12 November 2026, have no wind and no solar forecast. Results for ES that use these inputs must say so.
- FR `solar_forecast` and `wind_onshore_forecast`: 23 and 22 delivery days from 2019 to 2026. The one empty hour in the test set is on the clock-change day 2026-10-25.
- DE_LU `solar_forecast` and `wind_onshore_forecast`: one hour on each of the clock-change days 2023-10-29, 2024-10-27 and 2025-10-26. DE_LU `load_forecast`: 2022-02-22 and 2022-03-24 without any value, and one hour on 2023-10-29 and on 2024-10-27.
- Swedish `wind_onshore_forecast`: the same 9 whole days in all four zones: 2019-04-15, 2022-08-17, 2022-11-20, 2025-05-12, 2025-11-01, 2025-11-02, 2026-03-11, 2026-04-29 and 2026-06-26. The last one lies in the validation set. Swedish `load_forecast`: 2025-12-04.
- `actual_load`: FR has 48 hours without a value and 2 partly filled hours. ES has 35 hours without a value, on 2025-04-28 and 2025-04-29, and 5 partly filled hours. A partly filled hour is empty in the hourly table (DECISIONS entry 22). In the 15-minute table its values stay at their own time. The one in the test set is 2026-10-25 00:00 UTC.
- The counts of ES `actual_load` were 41 and 4 when the rules were approved on 2026-11-23. The download to `DATA_END` brought the missing value of 2026-11-17 05:00 UTC. The validation stopped the first build on that difference, and the owner approved 40 and 3 on 2026-11-24.

### Validation

`validate.py` checks every table. A failed check ends the command with an error.

| Check | Rule |
|---|---|
| Index | Exactly the time steps of the period, in UTC, each once |
| Day length | Every delivery day has 24, 23 or 25 hours, or 96, 92 or 100 quarter-hours, as its date requires |
| End | No time step after delivery day 2026-11-19 |
| Columns | The columns listed for the zone in `config/approved_gaps.yaml` |
| Gaps | Per column exactly the approved number of empty values |

Result of 2026-11-24: all 21 tables pass. The tests use synthetic frames for a 23-hour day (2026-03-29), the 25-hour day 2026-10-25, the switch day 2025-10-01 and the `DATA_END` cutoff.
