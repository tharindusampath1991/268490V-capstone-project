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
| ENTSO-E Transparency Platform | Day-ahead prices, load forecast, wind and solar forecast. Primary source | Free API with a security token |
| Energy-Charts API (Fraunhofer ISE) | Prices, as a cross-check | Free, no key. CC BY 4.0 from Bundesnetzagentur \| SMARD.de for DE-LU, FR and SE4. Private and internal use only for ES, SE1, SE2 and SE3, so their cross-check results are not published |
| Open-Meteo | Archived weather forecasts | Free for non-commercial use, no key, CC BY 4.0 |
| Python `holidays` | Public holidays per country | Open source |

Raw data is never committed. Only the scripts that download and prepare it are.

## Environment

- Python 3.12.10, venv + pip, pinned `requirements.txt`.
- Hardware: to be added.

## Project documents

- [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md): scope, forecast protocol, models, plan.
- [docs/DECISIONS.md](docs/DECISIONS.md): numbered decisions with reasons.
- [docs/DATA_NOTES.md](docs/DATA_NOTES.md): how the data is obtained and prepared.
- [docs/PROGRESS.md](docs/PROGRESS.md): one row per working day.
