# CLAUDE.md — 268490V capstone

Individual MSc capstone (CS5998, University of Moratuwa): next-day electricity price forecasting for DE-LU, FR and ES, plus the four Swedish zones SE1–SE4 as extra zones, comparing statistical, ML and time series foundation models. Graded on what is built and justified. I must be able to explain every line in a viva.

Scope, forecast protocol, models, plan: @docs/PROJECT_CONTEXT.md

## Hard rules
- Scope is locked (M1 approved). No new models, zones, targets or dependencies beyond PROJECT_CONTEXT §1 and §6 without asking.
- Never fabricate data, metrics or outputs. Report only what a command actually printed. If a run fails, say so.
- The leakage rule (PROJECT_CONTEXT §5) applies to every feature and model input. If unsure, leave it out and flag it.
- Time-based splits only. Tune on validation. The test set is touched only by the final backtest.
- Never commit raw data, `.env`, tokens or model caches. The token is read from `ENTSOE_API_TOKEN` in `.env`. Never print it. ENTSO-E request URLs contain it, so never print or log a raw request error either.
- The Swedish zones (SE1–SE4) get no zone-specific tuning or features. Core zones always run first. Swedish work is the first thing cut if a core M2 item is at risk, in the order given in PROJECT_CONTEXT §1.
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
- Tests: `.venv\Scripts\python -m pytest`
- Download prices: `.venv\Scripts\python -m epf.data.download_prices` (first full run: about 80 minutes)
- Price cross-check: `.venv\Scripts\python -m epf.data.crosscheck_prices` (after the price download, about 30 minutes)
- Coverage gate: `.venv\Scripts\python scripts/check_coverage.py` (first full run: about 4 hours, writes `docs/coverage_gate.md`)
- Build data:
- Backtest:

## Commits
- No type prefixes such as `feat:`, `docs:` or `data:`. They read as machine-written. Start the subject with a capital letter and a verb, for example "Add price downloader".
- Subject under 72 characters, describing the actual change.
- Write it the way I would by hand: short and plain. Add a body of one to three short sentences only when the reason is not obvious.
- No bullet lists, headings, templates, trailers or generated-by lines in a commit message.

## End of session
Update `docs/PROGRESS.md` (date, done, next, blockers) and list proposed DECISIONS.md entries.
