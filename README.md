# Forecasting Next Day Electricity Prices in Europe with Time Series Foundation Models

CS5998 Capstone, MSc Data Science & AI, University of Moratuwa. A A T Sampath (268490V).

Status: work in progress. Milestone 2 is in preparation. The pipeline commands are added to this file as they come to exist.

## What this project does

It forecasts next-day (day-ahead) electricity prices with prediction intervals. It compares statistical models, machine learning and time series foundation models on the same time-based backtest.

## Zones

- Core zones, approved in Milestone 1: DE-LU, FR, ES.
- Extra zones: SE1, SE2, SE3, SE4 (all of Sweden). They were added on 19 Nov 2026 and are not part of the approved Milestone 1 scope. They run through the same pipeline with no zone-specific tuning and are reported in their own table.

## Setup

Python 3.12 is required. `entsoe-py` 1.0.0 does not install on older versions.

On Windows:

```
python3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

On Linux or macOS, use `.venv/bin/python` in the second command.

The second command also installs the project's own package, `src/epf`, in editable mode.

Run the tests with `.venv\Scripts\python -m pytest`. They use no network and no data files.

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
| Coverage gate report | `.venv\Scripts\python scripts/check_coverage.py` | reads the saved price and forecast files, writes `docs/coverage_gate.md` |

- Raw files are saved under `data/raw/`, one Parquet file per dataset, zone and year. Git ignores this folder.
- Each command prints counts of missing and repeated values. It changes no value.
- A finished year is read from disk on the next run. A run that stops can be started again and resumes from the saved files.
- Run one ENTSO-E command at a time. They share one cache manifest.
- The weather download uses about 6900 of the 10000 calls per day that Open-Meteo allows for free use.

The measured results of each run are in [docs/DATA_NOTES.md](docs/DATA_NOTES.md).

## Environment

- Python 3.12.10, venv + pip, pinned `requirements.txt`.
- Hardware: to be added.

## Project documents

- [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md): scope, forecast protocol, models, plan.
- [docs/DECISIONS.md](docs/DECISIONS.md): numbered decisions with reasons.
- [docs/DATA_NOTES.md](docs/DATA_NOTES.md): how the data is obtained and prepared.
- [docs/PROGRESS.md](docs/PROGRESS.md): one row per working day.
