# CLAUDE.md — 268490V capstone

Individual MSc capstone (CS5998, University of Moratuwa): next-day electricity price forecasting for seven core zones, comparing statistical, ML and time series foundation models. Graded on what is built and justified. I must be able to explain every line in a viva.

Scope, forecast protocol, models, plan: @docs/PROJECT_CONTEXT.md

## Hard rules
- Scope is locked (M1 approved). No new models, zones, targets or dependencies beyond PROJECT_CONTEXT §1 and §6 without asking.
- Never fabricate data, metrics or outputs. Report only what a command actually printed. If a run fails, say so.
- The leakage rule (PROJECT_CONTEXT §5) applies to every feature and model input. If unsure, leave it out and flag it.
- Time-based splits only. Tune on validation. The test set is touched only by the final backtest.
- Never commit raw data, `.env`, tokens or model caches. The token is read from `ENTSOE_API_TOKEN` in `.env`. Never print it. ENTSO-E request URLs contain it, so never print or log a raw request error either.
- All seven zones are core zones: DE-LU, FR, ES and the Swedish zones SE1–SE4. Every analysis, model and results table covers all seven. No zone is cut first.
- One setting per model, chosen on the validation days of all seven zones. No tuning and no feature for one zone only.
- The seven zones are shown alike. Nothing marks or describes SE1–SE4 as added later, and no text says which zones Milestone 1 approved (DECISIONS entry 81).
- No external LLM API calls in the pipeline.
- Do not commit or push unless I say so. I review the diff first.
- No backdated commits. No rewriting pushed history.

## How to work
- Small steps: one logical change, then stop for review.
- Plain, readable code over clever code. Type hints, short functions, docstrings that state inputs, outputs and time zone.
- After each change, three lines: what changed, why this way, what I should verify.
- When a choice has a real alternative, propose an entry for `docs/DECISIONS.md`: decision, reason, alternative rejected.
- Before calling `chronos-forecasting`, `timesfm`, `entsoe-py` or `statsforecast`, check the installed version and its current docs. Do not write calls from memory.
- Until M2 is submitted, work only on the M2 checklist (PROJECT_CONTEXT §2).

## Conventions
- Python 3.12, venv + pip, pinned `requirements.txt`. `entsoe-py` 1.0.0 needs Python 3.12 or newer.
- Config in `config/config.yaml`. No hard-coded dates, zones or paths. Adding a zone is a config entry only. Seeds set through one helper.
- UTC internally. Europe/Berlin only to define delivery days and for display.
- Pipeline code in `src/epf/`, runnable from the CLI. Notebooks for EDA only.
- Data in `data/raw/` and `data/processed/` as Parquet, both gitignored.
- Every experiment appends config and metrics to `reports/results/`. Figures are saved by scripts to `reports/figures/`.
- Tests with pytest: clock-change days, resolution switch, leakage cutoff.

## Commands
Fill in as they come to exist.
- Setup: `python3.12 -m venv .venv`, then `.venv\Scripts\python -m pip install -r requirements.txt`
- Tests: `.venv\Scripts\python -m pytest` (about 50 seconds)
- Download prices: `.venv\Scripts\python -m epf.data.download_prices` (first full run: about 80 minutes)
- Download forecasts: `.venv\Scripts\python -m epf.data.download_forecasts` (load forecast and wind and solar forecast. Current year only: about 20 minutes. Run one ENTSO-E download at a time, they share one cache manifest)
- Download actual load: `.venv\Scripts\python -m epf.data.download_actual_load` (first full run: about 75 minutes)
- Download weather: `.venv\Scripts\python -m epf.data.download_weather` (first full run: about 4.5 hours and about 6900 of the 10000 Open-Meteo calls allowed per day)
- Price cross-check: `.venv\Scripts\python -m epf.data.crosscheck_prices` (after the price download, about 30 minutes)
- Coverage gate: `.venv\Scripts\python scripts/check_coverage.py` (first full run: about 4 hours, writes `docs/coverage_gate.md`. Do not run it again without asking: the report of 24 Nov 2026 is the record of the measured coverage, and a new run would give no zone a verdict, because core zones are not gated)
- Build data: `.venv\Scripts\python -m epf.data.build_dataset` (about 3 seconds once the raw files are saved. Cleans, writes `data/processed/` and validates. `-m epf.data.clean` and `-m epf.data.validate` run one step alone)
- Price figures: `.venv\Scripts\python -m epf.eda.price_figures` (about 10 seconds, after the build. All seven core zones, hourly table, train days only. Prints the numbers and writes six PNG files to `reports/figures/`)
- EDA notebook: `.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks\01_eda_prices.ipynb` (about 16 seconds. It calls the figure functions and writes no PNG file)
- Driver figures: `.venv\Scripts\python -m epf.eda.driver_figures` (about 13 seconds, after the build. EDA 2: the price against the load, wind and solar forecast, 15-minute prices, the high-price period and holidays, for all seven core zones. The solar figure holds DE_LU, FR and ES only, since Sweden has no solar forecast. The last figure compares SE_1 to SE_4 with each other. Train days only. Prints the numbers and writes seven PNG files to `reports/figures/`)
- EDA 2 notebook: `.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks\01_eda_drivers.ipynb` (about 19 seconds. It calls the figure functions and writes no PNG file)
- Backtest: `.venv\Scripts\python -m epf.evaluation.backtest --model naive --split validation` (after the build. `--model` takes a name under `models` in the config. All 7 core zones, experiments H and Q, or one of them with `--experiment H` or `--experiment Q`. Prints the checks, adds rows to `reports/results/backtest_core.csv`, writes `daily_core.csv`, and saves the forecasts under `data/forecasts/`. The day loops of the naive run took about 3 seconds in total. `mstl_182`, the frozen statistical baseline, took about 10 minutes on H and about 3 hours on Q for the validation days. An ARIMA candidate took 15 to 88 minutes on H alone. `--split test` works only for a model listed under `backtest.test_models`. The naive test run was done once on 24 Nov 2026 and the `mstl_182` test run once on 25 Nov 2026, in about 4 hours 45 minutes. Do not run either again without asking. A zone with a weather point also has its weather table cut and handed to the model)
- Features: `.venv\Scripts\python -m epf.features.build` (about 4 minutes, after the build. The LightGBM features of all 7 core zones for experiments H and Q, each delivery day built from inputs cut by `cutoff.py`. The groups and lags are under `features` in the config. Prints the rows and the empty cells per feature and zone and writes `data/features/`, which git ignores. The backtest never reads those files)

## Commits
- No type prefixes such as `feat:`, `docs:` or `data:`. They read as machine-written. Start the subject with a capital letter and a verb, for example "Add price downloader".
- Subject under 72 characters, describing the actual change.
- Write it the way I would by hand: short and plain. Add a body of one to three short sentences only when the reason is not obvious.
- No bullet lists, headings, templates, trailers or generated-by lines in a commit message.

## End of session
Update `docs/PROGRESS.md` (date, done, next, blockers) and list proposed DECISIONS.md entries.
