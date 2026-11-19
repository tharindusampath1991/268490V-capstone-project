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
- Python 3.11, venv + pip, pinned `requirements.txt` (confirm, PROJECT_CONTEXT §11).
- Config in `config/config.yaml`. No hard-coded dates, zones or paths. Adding a zone is a config entry only. Seeds set through one helper.
- UTC internally. Europe/Berlin only to define delivery days and for display.
- Pipeline code in `src/epf/`, runnable from the CLI. Notebooks for EDA only.
- Data in `data/raw/` and `data/processed/` as Parquet, both gitignored.
- Every experiment appends config and metrics to `reports/results/`. Figures are saved by scripts to `reports/figures/`.
- Tests with pytest: clock-change days, resolution switch, leakage cutoff.

## Commands
Fill in as they come to exist.
- Setup:
- Tests:
- Build data:
- Backtest:

## Commits
Conventional Commits prefixes: `feat`, `fix`, `data`, `exp`, `docs`, `test`, `chore`. Subject under 72 characters, imperative, describing the actual change. Body says why when it is not obvious.

## End of session
Update `docs/PROGRESS.md` (date, done, next, blockers) and list proposed DECISIONS.md entries.
