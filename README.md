# Forecasting Next Day Electricity Prices in Europe with Time Series Foundation Models

CS5998 Capstone, MSc Data Science & AI, University of Moratuwa. A A T Sampath (268490V).

Status: work in progress. Milestone 2 is in preparation. The pipeline commands are added to this file as they come to exist.

## What this project does

It forecasts next-day (day-ahead) electricity prices with prediction intervals. It compares statistical models, machine learning and time series foundation models on the same time-based backtest.

## Zones

Seven core zones run through the same pipeline, with the same analysis, the same models and one results table:

- DE-LU, FR and ES. Milestone 1 approved these three.
- SE1, SE2, SE3 and SE4, all of Sweden. They are not part of the approved Milestone 1 scope. I added them on 19 Nov 2026 and made them core zones on 24 Nov 2026 ([docs/DECISIONS.md](docs/DECISIONS.md), entries 1 and 59).

Each model has one setting for all zones, chosen on the validation days of all seven. Two limits apply to Sweden: the data has no usable solar forecast for the Swedish zones, and SE1 and SE2 have nearly the same price, so their results are near-duplicates.

## Setup

Python 3.12 is required. `entsoe-py` 1.0.0 does not install on older versions.

On Windows:

```
python3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

On Linux or macOS, use `.venv/bin/python` in the second command.

The second command also installs the project's own package, `src/epf`, in editable mode.

Run the tests with `.venv\Scripts\python -m pytest`. They use no network and no data files, and take about 40 seconds.

## ENTSO-E token

The ENTSO-E Transparency Platform API is free but needs registration and a security token.

1. Copy `.env.example` to `.env`.
2. Put the token after `ENTSOE_API_TOKEN=`.

`.env` is ignored by git. Never commit or print the token.

## Data sources

| Source | Use | Access and licence |
|---|---|---|
| ENTSO-E Transparency Platform | Day-ahead prices, load forecast, wind and solar forecast, actual load. Primary source | Free API with a security token |
| Energy-Charts API (Fraunhofer ISE) | Prices, as a cross-check | Free, no key. CC BY 4.0 from Bundesnetzagentur \| SMARD.de for DE-LU, FR and SE4. Private and internal use only for ES, SE1, SE2 and SE3, so their cross-check results are not published |
| Open-Meteo | Archived weather forecast runs of ECMWF IFS HRES, from 14 March 2024 (Single Runs API) | Free for non-commercial use, no key, CC BY 4.0. Weather data by [Open-Meteo.com](https://open-meteo.com/) |
| Python `holidays` | Public holidays per country | Open source |

Raw data is never committed. Only the scripts that download and prepare it are.

## Data downloads

Run these from the repo root once the token is in place. On Linux or macOS, use `.venv/bin/python`.

| Step | Command | First full run |
|---|---|---|
| Day-ahead prices | `.venv\Scripts\python -m epf.data.download_prices` | about 80 minutes |
| Load forecast, wind and solar forecast | `.venv\Scripts\python -m epf.data.download_forecasts` | about 4 hours, measured as part of the coverage gate |
| Actual load | `.venv\Scripts\python -m epf.data.download_actual_load` | about 75 minutes |
| Weather forecasts | `.venv\Scripts\python -m epf.data.download_weather` | about 4.5 hours |
| Price cross-check against Energy-Charts | `.venv\Scripts\python -m epf.data.crosscheck_prices` | about 30 minutes, after the price download |
| Coverage gate report | `.venv\Scripts\python scripts/check_coverage.py` | about 4 hours on an empty cache. It downloads the price and forecast files that are not saved yet, so it needs the token. Writes `docs/coverage_gate.md` |

- Raw files are saved under `data/raw/`, one Parquet file per dataset, zone and year. Git ignores this folder.
- Each command prints counts of missing and repeated values. It changes no value.
- A finished year is read from disk on the next run. A run that stops can be started again and resumes from the saved files.
- Run one ENTSO-E command at a time. They share one cache manifest.
- The weather download uses about 6900 of the 10000 calls per day that Open-Meteo allows for free use.

The measured results of each run are in [docs/DATA_NOTES.md](docs/DATA_NOTES.md).

## Build the data

The data period is frozen: delivery days 2019-01-01 to 2026-11-19 (`data.end` in `config/config.yaml`). Validation is 2026-06-23 to 2026-08-21 and test is 2026-08-22 to 2026-11-19. The download commands above stop at that day.

Once the raw files are saved, one command builds the modelling tables:

```
.venv\Scripts\python -m epf.data.build_dataset
```

- It cleans the raw files, writes three tables per zone under `data/processed/` and validates them. It takes about 3 seconds.
- `hourly/{ZONE}.parquet` is the hourly table, `quarter_hour/{ZONE}.parquet` the 15-minute table from 2025-10-01, and `weather/{ZONE}.parquet` the weather forecasts from 2024-03-15.
- No value is filled. A gap in a forecast stays empty, and prices have no gap.
- The command ends with an error when a table differs from `config/approved_gaps.yaml`, which holds the approved columns and gaps.
- `.venv\Scripts\python -m epf.data.clean` and `.venv\Scripts\python -m epf.data.validate` run the first and the last step alone.

The rules and the counts are in [docs/DATA_NOTES.md](docs/DATA_NOTES.md), "Preprocessing".

## Exploratory data analysis

EDA 1 covers the prices of all seven core zones on the hourly table. It uses the train delivery days only, 2019-01-01 to 2026-06-22. No validation or test day is read.

Once the tables are built, one command writes the figures:

```
.venv\Scripts\python -m epf.eda.price_figures
```

- It prints the numbers behind each figure and writes six PNG files to `reports/figures/`: the price distribution, the price by hour of day, by weekday, by year and month, spike hours and negative prices. It takes about 10 seconds.
- A figure with one panel per zone starts a new row after four zones. A figure with several panels per zone has one row per zone.
- Hours, weekdays and months are counted in market time (Europe/Berlin).
- An hour is a spike when its price is above the mean plus 3 standard deviations of the 28 days before it (DECISIONS entry 38).

The notebook [notebooks/01_eda_prices.ipynb](notebooks/01_eda_prices.ipynb) calls the same functions, shows each figure and states one finding under it. It is committed with its outputs. To run it again from the command line:

```
.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks\01_eda_prices.ipynb
```

EDA 2 compares the price with its day-ahead inputs, again on the train delivery days only. For all seven core zones it covers the price against the load and wind forecast, the 15-minute prices inside the hour, the high-price period of 2021 and 2022, and holidays against working days. The solar forecast is compared for DE_LU, FR and ES only, because the Swedish zones have none in the data. Its last figure compares the four Swedish zones SE_1 to SE_4 with each other, from north to south.

```
.venv\Scripts\python -m epf.eda.driver_figures
```

- It prints the numbers behind each figure and writes seven PNG files named `eda2_*.png` to `reports/figures/`. It takes about 13 seconds.
- Residual load is the load forecast minus the wind and the solar forecast (DECISIONS entry 42). The price of a day is never compared with the actual load of that day.
- Nothing is filled. An hour with an empty input is left out of that comparison, and the command prints how many hours it left out.
- A holiday is a nationwide public holiday from the `holidays` package (DECISIONS entry 46). Regional holidays count as working days, and the command prints how many days that is.

The notebook [notebooks/01_eda_drivers.ipynb](notebooks/01_eda_drivers.ipynb) calls the same functions and states one finding under each figure. It is committed with its outputs. To run it again from the command line:

```
.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks\01_eda_drivers.ipynb
```

## Backtest

Every model runs through one backtest. For each delivery day D it gets only what is known on D-1 before the 12:00 gate closure: prices through D-1, the day-ahead load, wind and solar forecast for D, and actual load through D-2 (DECISIONS entry 51). It returns one forecast per market time unit of D.

Once the tables are built, this scores the seasonal naive forecast on the 60 validation days:

```
.venv\Scripts\python -m epf.evaluation.backtest --model naive --split validation
```

- `--model` takes a name under `models` in `config/config.yaml`.
- One run covers the hourly table (experiment H) and the 15-minute table (experiment Q) for all seven zones. `--experiment H` or `--experiment Q` runs one of the two.
- The seasonal naive forecast is the price at the same local time 7 days before (DECISIONS entry 52). It is the reference for relative MAE.
- The command prints its checks per zone and experiment and stops with an error when one fails.
- Results go to `reports/results/`, which is committed. `backtest_core.csv` holds one row per run, zone and experiment for all seven zones. Each row has the metrics, the model settings, the seed, the run time, the peak memory and the hardware. `daily_core.csv` holds the losses per delivery day.
- SE1 to SE4 are in the same files as DE-LU, FR and ES. Milestone 1 did not approve them, and every results table in the report will say so.
- A run adds rows to `backtest_core.csv`, so a second run shows as a second set of rows.
- Forecasts per market time unit are saved under `data/forecasts/`, which git ignores.
- `--split test` scores the 90 test days. It works only for a model listed under `backtest.test_models` in the config: the naive forecast and `mstl_182`, the statistical baseline (DECISIONS entries 50, 58 and 67). Each of the two test runs was done once, on 24 and on 25 Nov 2026.

MAE and RMSE are in EUR/MWh. Price levels differ several-fold between zones, so zones are compared on relative MAE only.

### Statistical baseline

The statistical baseline is `mstl_182`: MSTL from `statsforecast` with a daily and a weekly season, fitted on the prices of the 182 days before the delivery day. It reads the price history only, with no load, wind, solar or weather input.

- It was chosen from 15 settings: AutoARIMA, AutoETS and MSTL with several history lengths. All 15 ran on the 60 validation days of experiment H for all seven zones, and the setting with the lowest mean relative MAE won. The rule was fixed before the runs. The rows of all 15 are in `backtest_core.csv`. Every table, the run times and the checks are in [docs/MODEL_NOTES.md](docs/MODEL_NOTES.md), and the reasons are in DECISIONS entry 64.
- The three best settings, MSTL on 91, 182 and 364 days, lie within 0.0015 of each other. That is inside the noise of 60 days.
- The model is fitted every 7 days. On the days between, the fitted model is applied to the newest prices and nothing is estimated again (DECISIONS entry 63).
- No transform is used and every ETS form is additive, because prices go negative (DECISIONS entry 62).
- `mstl_182` takes about 10 minutes on experiment H and about 3 hours on experiment Q for the validation days.

Relative MAE of `mstl_182` against the seasonal naive forecast. Milestone 1 approved DE-LU, FR and ES only. SE1 to SE4 were added afterwards, and SE1 and SE2 are near-duplicates.

| Zone | Validation, H | Validation, Q | Test, H | Test, Q |
|---|---|---|---|---|
| DE_LU | 0.7106 | 0.6611 | 0.4831 | 0.4901 |
| FR | 0.6521 | 0.6528 | 0.5151 | 0.5182 |
| ES | 0.7165 | 0.7160 | 0.6137 | 0.6181 |
| SE_1 (added after M1) | 0.7317 | 0.7267 | 0.6439 | 0.6496 |
| SE_2 (added after M1) | 0.6666 | 0.6682 | 0.6486 | 0.6466 |
| SE_3 (added after M1) | 0.6596 | 0.6617 | 0.5499 | 0.5512 |
| SE_4 (added after M1) | 0.6837 | 0.6955 | 0.5116 | 0.5101 |
| Mean | 0.6887 | 0.6831 | 0.5666 | 0.5691 |

The test values are lower than the validation values because the naive forecast was much worse on the test days. Its mean MAE on experiment H rose from 29.63 to 54.83 EUR/MWh, and that of `mstl_182` from 20.33 to 30.09 (DECISIONS entry 67).

## Environment

- Python 3.12.10, venv + pip, pinned `requirements.txt`.
- Hardware: laptop, Lenovo 21RVCTO1WW, AMD Ryzen AI 9 HX PRO 370 with 12 cores and 24 threads, 59.6 GB RAM, AMD Radeon 890M integrated graphics, Windows 11 (10.0.26200). The backtest runs on the CPU. No GPU run has been made yet.
- The backtest reads its peak memory on Windows only. On Linux or macOS the `peak_memory_mb` column stays empty (DECISIONS entry 55). The backtest has not been run on such a machine yet.

## Project documents

- [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md): scope, forecast protocol, models, plan.
- [docs/DECISIONS.md](docs/DECISIONS.md): numbered decisions with reasons.
- [docs/DATA_NOTES.md](docs/DATA_NOTES.md): how the data is obtained and prepared.
- [docs/MODEL_NOTES.md](docs/MODEL_NOTES.md): the measured results of each model, with settings, tables, run times and checks.
- [docs/PROGRESS.md](docs/PROGRESS.md): one row per working day.
