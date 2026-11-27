# Forecasting Next Day Electricity Prices in Europe with Time Series Foundation Models

CS5998 Capstone, MSc Data Science & AI, University of Moratuwa. A A T Sampath (268490V).

Status: work in progress. Milestone 2 is in preparation. The pipeline commands are added to this file as they come to exist.

## What this project does

It forecasts next-day (day-ahead) electricity prices with prediction intervals. It compares statistical models, machine learning and time series foundation models on the same time-based backtest.

## Zones

Seven core zones run through the same pipeline, with the same analysis, the same models and one results table:

- DE-LU: Germany and Luxembourg.
- FR: France.
- ES: Spain.
- SE1, SE2, SE3 and SE4: Sweden, from north to south.

Each model has one setting for all zones, chosen on the validation days of all seven. Two limits apply to Sweden: the data has no usable solar forecast for the Swedish zones, and SE1 and SE2 have nearly the same price, so their results are near-duplicates.

## Setup

Python 3.12 is required. `entsoe-py` 1.0.0 does not install on older versions.

On Windows:

```
python3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

On Linux or macOS, use `.venv/bin/python` in the second command.

The second command also installs the project's own package, `src/epf`, in editable mode. It installs `torch` too, which runs the two foundation models. On Windows the wheel from PyPI is the CPU build.

Run the tests with `.venv\Scripts\python -m pytest`. They use no network and no data files, and take about 70 seconds.

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

Every model runs through one backtest. For each delivery day D it gets only what is known on D-1 before the 12:00 gate closure: prices through D-1, the day-ahead load, wind and solar forecast for D, and actual load through D-2 (DECISIONS entry 51). It also gets the weather forecast for D from the model run of D-1 (entry 78) and the holiday dates of the country of the zone (entry 82). It returns one forecast per market time unit of D.

Once the tables are built, this scores the seasonal naive forecast on the 60 validation days:

```
.venv\Scripts\python -m epf.evaluation.backtest --model naive --split validation
```

- `--model` takes a name under `models` in `config/config.yaml`.
- One run covers the hourly table (experiment H) and the 15-minute table (experiment Q) for all seven zones. `--experiment H` or `--experiment Q` runs one of the two.
- The seasonal naive forecast is the price at the same local time 7 days before (DECISIONS entry 52). It is the reference for relative MAE.
- The command prints its checks per zone and experiment and stops with an error when one fails.
- Results go to `reports/results/`, which is committed. Its three files cover all seven zones. `backtest_core.csv` holds one row per run, zone and experiment. Each row has the metrics, the config entry of the model, the seed, the run time, the peak memory and the hardware. The `features` section of the config is not in the row. `daily_core.csv` holds the losses per delivery day. `quantile_core.csv` holds the scores of the quantile forecasts (see "LightGBM" below).
- A run adds rows to `backtest_core.csv`, so a second run shows as a second set of rows.
- Forecasts per market time unit are saved under `data/forecasts/`, which git ignores.
- `--split test` scores the 90 test days. It works only for a model listed under `backtest.test_models` in the config: the naive forecast, `mstl_182`, the statistical baseline, and `lgbm_load_826_slow`, the LightGBM model (DECISIONS entries 50, 58, 67 and 90). Each of the three test runs was done once, on 24, 25 and 26 Nov 2026. None of them is run again.

MAE and RMSE are in EUR/MWh. Price levels differ several-fold between zones, so zones are compared on relative MAE only.

This prints the relative MAE of every model per zone as a Markdown table:

```
.venv\Scripts\python -m epf.evaluation.tables --experiment H --split validation
```

- It reads the saved rows of `backtest_core.csv`, runs no model and writes no file. It takes about 2 seconds.
- The models are sorted by their mean over the seven zones, the lowest first. `--experiment Q` prints the table of the 15-minute experiment.
- When a model has more than one run, the newest row is used, and a line under the table names the model.
- The numbers of the result tables of this file are those that this command prints (DECISIONS entry 83).

### Statistical baseline

The statistical baseline is `mstl_182`: MSTL from `statsforecast` with a daily and a weekly season, fitted on the prices of the 182 days before the delivery day. It reads the price history only, with no load, wind, solar or weather input.

- It was chosen from 15 settings: AutoARIMA, AutoETS and MSTL with several history lengths. All 15 ran on the 60 validation days of experiment H for all seven zones, and the setting with the lowest mean relative MAE won. The rule was fixed before the runs. The rows of all 15 are in `backtest_core.csv`. Every table, the run times and the checks are in [docs/MODEL_NOTES.md](docs/MODEL_NOTES.md), and the reasons are in DECISIONS entry 64.
- The three best settings, MSTL on 91, 182 and 364 days, lie within 0.0015 of each other. That is inside the noise of 60 days.
- The model is fitted every 7 days. On the days between, the fitted model is applied to the newest prices and nothing is estimated again (DECISIONS entry 63).
- No transform is used and every ETS form is additive, because prices go negative (DECISIONS entry 62).
- `mstl_182` takes about 10 minutes on experiment H and about 3 hours on experiment Q for the validation days.

Relative MAE of `mstl_182` against the seasonal naive forecast. SE1 and SE2 are near-duplicates.

| Zone | Validation, H | Validation, Q | Test, H | Test, Q |
|---|---|---|---|---|
| DE_LU | 0.7106 | 0.6611 | 0.4831 | 0.4901 |
| FR | 0.6521 | 0.6528 | 0.5151 | 0.5182 |
| ES | 0.7165 | 0.7160 | 0.6137 | 0.6181 |
| SE_1 | 0.7317 | 0.7267 | 0.6439 | 0.6496 |
| SE_2 | 0.6666 | 0.6682 | 0.6486 | 0.6466 |
| SE_3 | 0.6596 | 0.6617 | 0.5499 | 0.5512 |
| SE_4 | 0.6837 | 0.6955 | 0.5116 | 0.5101 |
| Mean | 0.6887 | 0.6831 | 0.5666 | 0.5691 |

The test values are lower than the validation values because the naive forecast was much worse on the test days. Its mean MAE on experiment H rose from 29.63 to 54.83 EUR/MWh, and that of `mstl_182` from 20.33 to 30.09 (DECISIONS entry 67).

## Features for LightGBM

The LightGBM model reads the features below. The backtest builds them in memory at every fit. This command builds the same frames for all days, to look at them. Once the tables are built:

```
.venv\Scripts\python -m epf.features.build
```

- It builds one frame per zone and experiment, with one row per market time unit: 28 features on the hourly table and 29 on the 15-minute table.
- Each delivery day is built from inputs cut to that day, by the same code as the backtest (DECISIONS entry 69). The price of the delivery day is never in the frame.
- The feature groups are switched in `features.groups` of `config/config.yaml`:

| Group | Features |
|---|---|
| `price` | The price at the same local time 1 to 7 days before, and the mean, minimum, maximum and last price of D-1 |
| `calendar` | Hour, weekday and holiday in market time, and the quarter of the hour on the 15-minute table |
| `load_forecast`, `wind_forecast`, `solar_forecast` | Each day-ahead forecast at the target time and 1 and 7 days before. The wind forecast is onshore plus offshore |
| `actual_load` | Actual load 2 days before |
| `weather` | Temperature, wind speed at 10 m and 100 m and solar radiation, from the weather forecast run of D-1 |

- All seven zones have the same columns. SE1 to SE4 have no solar forecast, so their solar features are empty.
- Nothing is filled and no row is dropped. A feature is empty where its source is empty.
- Weather forecasts exist from delivery day 2024-03-15 only, so the weather features are empty before that day.
- The command prints the rows and the empty cells per feature and zone. It takes about 4 minutes and saves a copy under `data/features/`, which git ignores. The backtest never reads these files.

The numbers behind the choice of the features and the checks of the built frames are in [docs/MODEL_NOTES.md](docs/MODEL_NOTES.md), "LightGBM features". The reasons are in DECISIONS entries 69 to 80.

## LightGBM

The LightGBM model is `lgbm_load_826_slow`. The config names it under `backtest.lightgbm_model`. It runs through the same backtest as the other models:

```
.venv\Scripts\python -m epf.evaluation.backtest --model lgbm_load_826_slow --split validation
```

- It uses the feature groups `price`, `calendar`, `load_forecast`, `wind_forecast`, `solar_forecast` and `actual_load`. It has 400 trees with a learning rate of 0.025 and is fitted on the squared error.
- It is fitted every 7 days on a moving window of the last 826 days (819 training days, since the lags read the first 7). On the days between, the trees stay and are applied to the features of the day.
- The 15-minute table starts on 2025-10-01, so on experiment Q the window never fills. The model trains on all the 15-minute history there (DECISIONS entry 89).
- Every fit builds its training rows from the inputs of its delivery day, and each training day is cut again as if it were forecast (DECISIONS entry 85). So a training row holds only what was known when its own day was forecast.
- `lightgbm` 4.7.0 is used through its native API, `lightgbm.train` and `lightgbm.Dataset`. scikit-learn is not installed (DECISIONS entry 84).
- The run takes about 7 minutes on experiment H and about 4 minutes on experiment Q for the validation days. Almost all of that time builds features, not trees.

How it was chosen:

- 11 settings ran on the 60 validation days of experiment H for all seven zones. They differ in the feature groups, in the window (all history, 826 or 364 days) and in three parameter changes. The setting with the lowest mean relative MAE won. The rule was fixed before the runs (DECISIONS entries 87 and 88).
- The four best settings lie within 0.0093 of each other. That is inside the noise of 60 days, so the rule picked the winner and the numbers do not prove it better than the next three.
- The day-ahead load, wind and solar forecasts carry the gain: they move the mean from 0.6569 to 0.5539. Actual load two days before did not lower the mean. The weather features did not lower it on the windows of 826 and 364 days. On all history they did, but 1893 of the 2723 training days of the first fit have no weather there, so that pair cannot show the value of weather alone.
- The rows of all 11 settings are in `backtest_core.csv`. Every table, the run times and the checks are in [docs/MODEL_NOTES.md](docs/MODEL_NOTES.md), "LightGBM".

Relative MAE on the 60 validation days. The naive forecast is the reference, so its value is 1.

| Experiment | Model | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|---|
| H | `lgbm_load_826_slow` | 0.4909 | 0.5548 | 0.5707 | 0.6235 | 0.5122 | 0.4890 | 0.4797 | 0.5316 |
| H | `mstl_182` | 0.7106 | 0.6521 | 0.7165 | 0.7317 | 0.6666 | 0.6596 | 0.6837 | 0.6887 |
| H | `naive` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Q | `lgbm_load_826_slow` | 0.5304 | 0.5784 | 0.6227 | 0.6911 | 0.6059 | 0.5040 | 0.5152 | 0.5782 |
| Q | `mstl_182` | 0.6611 | 0.6528 | 0.7160 | 0.7267 | 0.6682 | 0.6617 | 0.6955 | 0.6831 |
| Q | `naive` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

Relative MAE on the 90 test days. The LightGBM test run was done once, on 26 Nov 2026 (DECISIONS entry 90).

| Experiment | Model | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|---|
| H | `lgbm_load_826_slow` | 0.4048 | 0.4854 | 0.5155 | 0.4752 | 0.4296 | 0.5061 | 0.4846 | 0.4716 |
| H | `mstl_182` | 0.4831 | 0.5151 | 0.6137 | 0.6439 | 0.6486 | 0.5499 | 0.5116 | 0.5666 |
| H | `naive` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Q | `lgbm_load_826_slow` | 0.4028 | 0.4789 | 0.5245 | 0.4936 | 0.4440 | 0.5030 | 0.5079 | 0.4792 |
| Q | `mstl_182` | 0.4901 | 0.5182 | 0.6181 | 0.6496 | 0.6466 | 0.5512 | 0.5101 | 0.5691 |
| Q | `naive` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

- The test values are lower than the validation values because the naive forecast was much worse on the test days. On experiment H its mean MAE rose from 29.63 to 54.83 EUR/MWh, and that of the LightGBM model from 15.46 to 25.85.
- DE_LU on the test days is a little below a published value of about 0.42 for that zone (arXiv 2611.16657, per-hour LightGBM on 2025 hourly data). That value comes from another period and other inputs. The mean of the seven zones is inside the range of 0.42 to 0.48 that the same study gives for DE_LU and the four Swedish zones (DECISIONS entry 90).
- SE4 has no usable solar forecast, and the solar features of all four Swedish zones are empty. SE1 and SE2 are near-duplicates.
- 7 of the 90 ES test days, 6 to 12 Nov 2026, have no wind and no solar forecast. The ES test values include these days.

This prints how firm the choice between the settings is:

```
.venv\Scripts\python -m epf.evaluation.firmness --winner lgbm_load_826_slow --models lgbm_load_826_slow lgbm_load_826 lgbm_load_826_l1 lgbm_all lgbm_all_826 lgbm_fcst lgbm_load lgbm_load_826_leaves15 lgbm_load_364 lgbm_all_364 lgbm_price mstl_182 --without SE_2
```

- It prints the MAE computed again from the saved forecasts, the mean by half of the days, the zones each setting wins, a bootstrap over whole delivery days, the mean without one zone, the relative MAE by hour and by week, the days on which the winner is worse than the naive forecast, and the share of its error in its 6 worst days.
- It only reads: the saved rows, the processed tables and the forecasts under `data/forecasts/`. So the backtest of every named setting must have run on the machine first. It takes about 5 seconds and writes no file.
- It reads the validation days. It refuses the test days unless every named model is listed under `backtest.test_models` (DECISIONS entry 83).

### Quantile forecasts

The same setting also gives prediction intervals:

```
.venv\Scripts\python -m epf.evaluation.quantiles --split validation
```

- It fits one set of trees per level, for the levels 0.05, 0.25, 0.50, 0.75 and 0.95 (`backtest.quantile_levels`). The features, the window and the parameters are those of `lgbm_load_826_slow`.
- The levels are fitted apart, so their values can cross. The command sorts the five values of each market time unit before it scores them, and reports the share of market time units that sorting changed.
- It adds one row per zone and experiment to `reports/results/quantile_core.csv`: the pinball loss per level, the coverage and the width of the 50% and the 90% interval, and the crossing share. A second run adds a second set of rows.
- It scores the validation days only and takes about 18 minutes. The test days are refused (DECISIONS entry 91).

Means over the seven zones on the 60 validation days:

| Experiment | Mean pinball loss, EUR/MWh | Coverage of the 50% interval | Coverage of the 90% interval | Crossing share |
|---|---|---|---|---|
| H | 5.2845 | 0.3848 | 0.7538 | 0.2027 |
| Q | 5.7518 | 0.3407 | 0.7328 | 0.3027 |

The intervals are too narrow in every zone and on both experiments: the 90% interval holds about 75% of the prices on H and about 73% on Q. They are reported as they are and were not widened. The values per zone are in DECISIONS entry 91.

## Zero-shot foundation models

Chronos-2 (`amazon/chronos-2`) and TimesFM 2.5 (`google/timesfm-2.5-200m-pytorch`) run zero-shot through the same backtest. Nothing is fitted on the prices of the project. The frozen settings are `chronos2_84` and `timesfm25_84`. The config names them under `backtest.chronos2_model` and `backtest.timesfm25_model`.

```
.venv\Scripts\python -m epf.evaluation.backtest --model chronos2_84 --split validation
.venv\Scripts\python -m epf.evaluation.backtest --model timesfm25_84 --split validation
```

- Both read the price history only: the prices of the last 84 days before the delivery day. That is 2016 hours on experiment H and 8064 quarter-hours on experiment Q. They use no calendar and no load, wind, solar or weather input, and each zone is forecast alone.
- The forecast has one value per market time unit of the delivery day. It is the median of the model, its 0.5 quantile (DECISIONS entry 95).
- The model ID and the pinned Hugging Face revision of each model are in `config/config.yaml` under `foundation_models`, and they are copied into every results row. The first run downloads the weights, 478 MB and 925 MB, to the Hugging Face cache of the user, so it needs the network.
- TimesFM runs with `infer_is_positive: false`. With true it would cut a forecast at 0, and prices go negative (DECISIONS entry 96).
- Both run on the CPU. On the validation days `chronos2_84` takes about 1 minute on experiment H and about 3 minutes on experiment Q, and `timesfm25_84` about 3 and about 7 minutes.

How they were chosen:

- Four context lengths ran per model: 14, 28, 56 and 84 days, as the entries `chronos2_14` to `chronos2_84` and `timesfm25_14` to `timesfm25_84`. All eight ran on the 60 validation days of experiment H for all seven zones. For each model the setting with the lowest mean relative MAE won. The rule was fixed and committed before the runs (DECISIONS entries 97 and 98).
- For both models the three longer contexts are a tie inside the noise of 60 days, and 14 days are clearly worse. Both winners are the longest candidate. A longer context was not tried, because 84 days are the most that fits Chronos-2 on the 15-minute table.
- The rows of all eight settings are in `backtest_core.csv`. Every table, the run times and the checks are in [docs/MODEL_NOTES.md](docs/MODEL_NOTES.md), "Chronos-2 zero-shot" and "TimesFM 2.5 zero-shot".

Relative MAE on the 60 validation days, from the table command. The naive forecast is the reference, so its value is 1.

| Experiment | Model | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|---|
| H | `lgbm_load_826_slow` | 0.4909 | 0.5548 | 0.5707 | 0.6235 | 0.5122 | 0.4890 | 0.4797 | 0.5316 |
| H | `chronos2_84` | 0.5874 | 0.5071 | 0.5463 | 0.6217 | 0.5893 | 0.5335 | 0.5006 | 0.5551 |
| H | `timesfm25_84` | 0.6398 | 0.6308 | 0.6763 | 0.6796 | 0.6525 | 0.5787 | 0.5508 | 0.6298 |
| H | `mstl_182` | 0.7106 | 0.6521 | 0.7165 | 0.7317 | 0.6666 | 0.6596 | 0.6837 | 0.6887 |
| H | `naive` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Q | `lgbm_load_826_slow` | 0.5304 | 0.5784 | 0.6227 | 0.6911 | 0.6059 | 0.5040 | 0.5152 | 0.5782 |
| Q | `chronos2_84` | 0.6147 | 0.5272 | 0.5860 | 0.6436 | 0.6478 | 0.5550 | 0.5115 | 0.5837 |
| Q | `timesfm25_84` | 0.6820 | 0.6716 | 0.6992 | 0.6544 | 0.6268 | 0.6172 | 0.5568 | 0.6440 |
| Q | `mstl_182` | 0.6611 | 0.6528 | 0.7160 | 0.7267 | 0.6682 | 0.6617 | 0.6955 | 0.6831 |
| Q | `naive` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

- Chronos-2 and TimesFM read the same input as `mstl_182`, the price history, and both are clearly ahead of it on experiment H.
- Chronos-2 is clearly ahead of TimesFM, in all seven zones on experiment H.
- Chronos-2 against the LightGBM model is not settled on these 60 days. LightGBM also reads the load, wind and solar forecasts and is ahead in the mean, but the bootstrap interval of the difference holds zero. Chronos-2 is lower in FR, ES and SE_1 on experiment H.
- SE1 and SE2 are near-duplicates.
- Neither zero-shot model has been scored on the test days. `--split test` is refused for all eight settings.

This prints how firm each choice is:

```
.venv\Scripts\python -m epf.evaluation.firmness --winner chronos2_84 --models chronos2_84 chronos2_56 chronos2_28 chronos2_14 lgbm_load_826_slow mstl_182 --without SE_2
.venv\Scripts\python -m epf.evaluation.firmness --winner timesfm25_84 --models timesfm25_84 timesfm25_56 timesfm25_28 timesfm25_14 chronos2_84 mstl_182 --without SE_2
```

## Environment

- Python 3.12.10, venv + pip, pinned `requirements.txt`.
- Hardware: laptop, Lenovo 21RVCTO1WW, AMD Ryzen AI 9 HX PRO 370 with 12 cores and 24 threads, 59.6 GB RAM, AMD Radeon 890M integrated graphics, Windows 11 (10.0.26200). The backtest runs on the CPU. No GPU run has been made yet.
- Chronos-2 and TimesFM 2.5 run on `torch` 2.15.0+cpu with 12 threads, through `chronos-forecasting` 2.3.2 and `timesfm` 3.0.2. `torch.compile` is off for TimesFM, because torch finds no C++ compiler on this laptop. The peak memory of a run was about 1 GB for Chronos-2 and about 2.2 GB for TimesFM.
- Every backtest command imports `lightgbm` 4.7.0, also a run of the naive forecast. On 26 Nov 2026 `import lightgbm` failed on this machine while an installer was replacing the Microsoft Visual C++ runtime, and worked again when the installer had finished.
- The backtest reads its peak memory on Windows only. On Linux or macOS the `peak_memory_mb` column stays empty (DECISIONS entry 55). The backtest has not been run on such a machine yet.

## Project documents

- [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md): scope, forecast protocol, models, plan.
- [docs/DECISIONS.md](docs/DECISIONS.md): numbered decisions with reasons.
- [docs/DATA_NOTES.md](docs/DATA_NOTES.md): how the data is obtained and prepared.
- [docs/MODEL_NOTES.md](docs/MODEL_NOTES.md): the measured results of each model, with settings, tables, run times and checks.
- [docs/PROGRESS.md](docs/PROGRESS.md): one row per working day.
