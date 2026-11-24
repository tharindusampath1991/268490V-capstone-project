# PROJECT_CONTEXT — CS5998 Capstone

Owner: A A T Sampath (268490V) · Last updated: 2026-11-24

## 0. Snapshot

| Item | Value |
|---|---|
| Module | CS5998 Capstone, MSc Data Science & AI, University of Moratuwa. 6 credits, individual |
| Title | Forecasting Next Day Electricity Prices in Europe with Time Series Foundation Models |
| Repo | https://github.com/tharindusampath1991/268490V-capstone-project (public) |
| Status on 19 Nov 2026 | M1 approved as submitted. ENTSO-E token in hand. No code yet. Roughly week 6 of 12 |
| Status on 24 Nov 2026 | Data pipeline built through preprocessing for all 7 zones: downloads, cleaning, validation and the modelling tables. `DATA_END` is frozen at 2026-11-19 (§4). EDA 1 is done: prices of the core zones on train days, six figures and `notebooks/01_eda_prices.ipynb`. EDA 2 is done: the price against the load, wind and solar forecast, the 15-minute prices, the high-price period and holidays for the core zones, and one section on the Swedish zones, seven figures and `notebooks/01_eda_drivers.ipynb`. The backtest harness is not started (§9) |
| Next deadline | M2 Technical Checkpoint, assumed Thu 3 Dec 2026 (confirm, §11) |
| Grading | M1 25% · M2 25% · M3 50%. A viva can be called at any milestone |
| AI tools | Allowed. I must understand, justify and explain every decision and result |
| Scope change | 19 Nov 2026: SE1–SE4 (all of Sweden) added as extra zones in M2, my decision (§1, §3.1) |

## 1. Locked scope (from Milestone 1)

- Problem: prediction of next-day (day-ahead) prices, with prediction intervals.
- Data: multivariate time series of prices, load, generation forecasts, weather.
- Techniques: statistical models, machine learning, deep learning foundation models.
- System: forecasting pipeline with a dashboard, plus an experimental comparison.
- Core zones (approved in M1): DE-LU, FR, ES.
- Extra zones (added 19 Nov 2026 by my decision, not in the approved M1 scope): SE1, SE2, SE3, SE4, all of Sweden. Part of M2 alongside the core zones. Seven zones in total. Rules:
  - Same pipeline, added as config entries. Covered by preprocessing, baselines, LightGBM and zero-shot runs. EDA for Sweden is one combined north–south section, not four.
  - Gate: each zone stays in M2 only if it passes the day-1 coverage check (§3.1).
  - No Sweden-specific tuning or features. Hyperparameters and context lengths are chosen on the core zones and applied unchanged.
  - Core first: core zones always run and are reported first. Swedish work is the first thing cut if any core M2 item is at risk, in this order: experiment Q for Sweden, then SE1 and SE2, then SE4, then SE3. Cut items move to M3.
  - Always labelled as an addition to the approved scope in README, results and report. Sweden gets its own results table. Core results stay complete without it.
- Research questions:
  - RQ1: How accurate are zero-shot foundation models versus seasonal naive, SARIMA/ETS and LightGBM?
  - RQ2: Do extra inputs (load, wind, solar forecasts, calendar) improve forecasts?
  - RQ3: Does fine-tuning a foundation model on local data help, and at what time and compute cost?
- Out of scope: intraday and balancing markets, beating professional trading forecasts, external LLM APIs, zones beyond the three core zones and SE1–SE4, extra models.
- Success: the pipeline works end to end and the comparison is fair and repeatable, even if foundation models do not win.

## 2. Milestones mapped to artefacts

### M2 checklist (week 8, 25%)

| Guide requirement | Artefact | Done when |
|---|---|---|
| Data preprocessing completed | `src/epf/data/`, `docs/DATA_NOTES.md` | One command rebuilds clean tables for the 3 core zones and SE1–SE4, and validation checks pass |
| Exploratory Data Analysis | `notebooks/01_eda_*.ipynb`, `reports/figures/` | Covers seasonality, spikes, negative prices, price vs drivers, hourly vs 15-min |
| Baseline + improved method | Seasonal naive, SARIMA/ETS, LightGBM | All run through the same backtest, results table committed |
| System architecture diagram | `docs/architecture.md` (Mermaid) + PNG | Diagram matches the actual code |
| Code or system link | Repo URL, README with run steps | A fresh clone runs |
| Demo video, max 6 min | Link in README | Follows the outline in §12 |

Should-have for M2 (in the M1 plan for weeks 5–8): Chronos-2 and TimesFM 2.5 zero-shot.

### M3 (week 12, 50%)
- Final report, about 25–30 pages, with a short reflection on limitations and trade-offs.
- Code and/or system link.
- Reproducibility checklist (Appendix A). No draft review stage.

### Appendix A mapped to repo habits (do these from day 1)

| Checklist item | Where it lives |
|---|---|
| Dependencies listed | Pinned `requirements.txt` |
| Hardware specified | README "Environment" section: laptop CPU/RAM, Colab GPU type |
| Random seeds | `config/config.yaml`, set in one helper, reported in results |
| Data availability | README: sources, licences, ENTSO-E token steps, download commands |
| Splits defined | Absolute dates in config and `docs/DECISIONS.md` |
| Preprocessing described | `docs/DATA_NOTES.md` |
| Hyperparameters | Config files, copied into each results row |
| Architecture described or cited | Model IDs and pinned Hugging Face revisions, LightGBM params |

## 3. Data

| Source | Use | Access |
|---|---|---|
| ENTSO-E Transparency Platform | Day-ahead prices, actual load, day-ahead load forecast, day-ahead wind and solar forecast | Free API, needs registration and a security token. Python client: `entsoe-py` (area keys `DE_LU`, `FR`, `ES`, `SE_1`, `SE_2`, `SE_3`, `SE_4`) |
| Energy-Charts API (Fraunhofer ISE) | Prices and generation, backup and cross-check | Free, no key. The licence differs by zone: CC BY 4.0 for DE-LU, FR and SE4, private and internal use only for ES, SE1, SE2 and SE3 (checked 2026-11-20, DECISIONS entry 12) |
| Open-Meteo | Archived forecast runs of temperature, wind speed at 10 m and 100 m, and solar radiation. Single Runs API, ECMWF IFS HRES, the 00:00 UTC run of D-1 (DECISIONS entries 25 and 26) | Free for non-commercial use, no key, CC BY 4.0 |
| Python `holidays` | Public holidays per country. Sweden: `public` plus `de_facto` categories | Open source |

Raw data is never committed. Only the scripts that download and prepare it.

Known traps:
- Resolution switch: hourly until 30 Sep 2025, 15-min from delivery day 1 Oct 2025. ENTSO-E can return more than one resolution for the same period. Select explicitly and assert exactly one value per MTU.
- Covariate resolution differs by zone and variable. Align explicitly and log the rule.
- Clock-change days have 23 or 25 hours (92 or 100 quarter-hours). 25 Oct 2026 falls inside the test window.
- Negative prices are real. No log transform, no MAPE.
- 2022 crisis is a different regime inside the hourly training data.
- Weather must be forecasts with a known issue time, not reanalysis or measured weather. Archived ECMWF runs in Open-Meteo start on 14 March 2024, so the first delivery day with weather is 2024-03-15. Availability of the 00:00 UTC run before gate closure is taken from the Open-Meteo docs, not measured (DECISIONS entry 26).
- Energy-Charts forecast coverage outside Germany is unverified. ENTSO-E is the primary source for prices and covariates, Energy-Charts the cross-check.
- Weather uses one point per zone, set in the config: Kassel, Paris, Madrid, Luleå, Sundsvall, Stockholm and Malmö (DECISIONS entry 27). One point cannot stand for a whole zone. State it as a limitation, most of all for DE-LU.
- Run one ENTSO-E download at a time. The downloads share one cache manifest.
- ENTSO-E can lack a price day while later days are present. On 23 Nov 2026 DE_LU had no price for 20 and 21 Nov and FR none for 21 Nov, although both had 22 Nov (DATA_NOTES, "Raw price format"). `DATA_END` must be a day that is complete in all zones. Energy-Charts values are never used to fill ENTSO-E (DECISIONS entry 7). The three zone-days were still missing on 24 Nov 2026, so `DATA_END` was frozen at 2026-11-19 and no price was filled (DECISIONS entry 29).
- ENTSO-E can add a value days later. The ES actual load of 2026-11-17 05:00 UTC had three quarter-hour values on 22 Nov 2026 and four on 24 Nov. The reference is the raw files downloaded on 24 Nov 2026 together with `config/approved_gaps.yaml`. The build stops when a count differs (DECISIONS entry 34).
- Gaps stay empty in the processed tables. Nothing is filled (DECISIONS entry 30). 7 of the 90 ES test days, 6 to 12 Nov 2026, have no wind and no solar forecast. Say so with every ES result that uses these inputs.
- In the processed tables `actual_load` stands at its own delivery time, and `shortwave_radiation` is the mean of the hour before its timestamp. The feature builder must apply the D-2 cut to the first and line up the second with the delivery hour (DECISIONS entry 33).
- Energy-Charts now has `/v2` endpoints and lists FR, ES and SE1–SE4 as price zones, all in EUR/MWh. Check the endpoint catalogue before coding.
- `entsoe-py` 1.0.0: `query_day_ahead_prices` returns hourly values before 1 Oct 2025 and 15-min values after, in one series. Its `resolution` argument is deprecated. Load and wind/solar forecast queries are split by month, so a full pull is several hundred requests.
- ENTSO-E request URLs carry the token. Never print or log a raw request error.
- Sweden specifics are in §3.1.

### 3.1 Sweden (SE1–SE4) feasibility (checked 19 Nov 2026)

Verdict: feasible for M2 on data grounds, subject to the day-1 gate per zone. The real cost is time: seven zones instead of the approved three.

| Check | Finding |
|---|---|
| Prices | ENTSO-E areas `SE_1` to `SE_4`, EUR/MWh. Energy-Charts lists SE1–SE4 for the cross-check |
| 15-min switch | Same as the core zones: delivery day 1 Oct 2025, all SDAC bidding zones |
| Auction and time zone | Same 12:00 CET day-ahead auction, CET/CEST. No protocol change |
| Load forecast, wind forecast | On ENTSO-E for all four. A Nov 2026 preprint (arXiv 2611.16657, public code) used both for SE1–SE4 over 2018–2025 |
| Solar forecast | Too sparse on ENTSO-E for Sweden; that study dropped it. Matters little in SE1–SE3, more in SE4 (see profiles) |
| Hydro | Reservoir inputs added nothing at the day-ahead horizon in that study. No new features needed |
| Holidays | `holidays` 0.109 covers Sweden, one calendar for all four zones. `public` gives 13 days in 2026. `de_facto` adds Julafton, Midsommarafton and Nyårsafton |
| Regime change | Nordic flow-based market coupling from delivery day 30 Oct 2024. Note it in the EDA |
| Cost (estimate) | No new code if zones are config-driven. About 6–8 hours extra for checks, EDA and tables. Backtest run time is about 2.3 times the core-only run |

Zone profiles from the same preprint: 2024 generation shares, and 2025 hourly results for its per-hour LightGBM. Reference values, not my results.

| Zone | Main generation | Solar | Mean price 2025, EUR/MWh | Relative MAE vs D-7 naive | Loss without load, wind, solar forecasts |
|---|---|---|---|---|---|
| SE1 | Hydro 69%, wind 31% | 0% | 16.7 | 0.46 | 0.03 |
| SE2 | Hydro 66%, wind 32% | 0% | 16.5 | 0.43 | 0.07 |
| SE3 | Nuclear 65%, hydro 15%, wind 13% | 1% | 46.2 | 0.47 | 0.08 |
| SE4 | Wind 64%, hydro 16% | 8% | 60.4 | 0.48 | 0.08 |
| DE-LU | Thermal 47%, wind 32% | 14% | 89.3 | 0.42 | 0.13 |

What this means:
- North (SE1, SE2) and south (SE3, SE4) differ in price level by a factor of about three. Compare zones on relative MAE, never on MAE in EUR.
- SE1 and SE2 are likely to give near-duplicate results: similar mix and almost the same mean price. Check in the EDA how often their prices are identical. They are cut first for that reason.
- SE4 has the most solar and no usable solar forecast. State it as a limitation.

Coverage of the `SE_1` to `SE_4` series was measured by the gate. All four zones passed in the runs of 21, 23 and 24 Nov 2026 and stay in M2 (`docs/coverage_gate.md`). The Swedish solar forecast is marked drop, as expected. The columns marked drop are listed in the config under `coverage_gate.drop_columns` and are left out of the processed tables (DECISIONS entry 32).

Day-1 gate: `python scripts/check_coverage.py` (all 7 zones, 2019 onward, token from `.env`). It caches the raw downloads under `data/raw/entsoe/` and writes `docs/coverage_gate.md`, which is committed. The logic lives in `src/epf/data/coverage_gate.py` and has unit tests on synthetic data. It has run against the live API four times, last on 24 Nov 2026 for the frozen period 2019-01-01 to 2026-11-19. Rules:
- Prices: at least 99% of market time units present in every year. Days with gaps are counted.
- Load forecast and wind forecast: present on at least 95% of hours in every year.
- A forecast column below 95% is dropped for that zone and logged. Expected for Swedish solar.
- Each Swedish zone is judged on its own. A zone that fails on prices, load forecast or wind forecast leaves M2 and is retried in M3.
- Core zones are measured by the same rules but never cut. A forecast column below 95% is kept only by a logged decision. So far that is the ES wind forecast (DECISIONS entry 19).

The preprint is a reference and sanity range only. Do not copy its code. Cite it if its numbers are used.

Log the Sweden addition as the first entry in `docs/DECISIONS.md`: decision, reason, alternatives rejected (SE3 only; Sweden after M2), risks (M1 was approved with 3 zones; seven zones with 14 days to M2).

## 4. Experiments and splits

- `DATA_END` is 2026-11-19. It was frozen on 24 Nov 2026 (DECISIONS entry 29). Never move it.
- Experiment H (hourly): 2019-01-01 to `DATA_END`. After 1 Oct 2025 the hourly price is the mean of the four quarter-hours (DECISIONS entry 21).
- Experiment Q (15-min): 2025-10-01 to `DATA_END`.
- Weather sub-experiment: from delivery day 2024-03-15 only.
- Split by time: test = last 90 days, validation = the 60 days before, train = the rest. The absolute dates are in the config and in DECISIONS entry 29. Never move them.

| Split | Delivery days | Count |
|---|---|---|
| Train, experiment H | 2019-01-01 to 2026-06-22 | 2730 |
| Train, experiment Q | 2025-10-01 to 2026-06-22 | 265 |
| Train, weather sub-experiment | 2024-03-15 to 2026-06-22 | 830 |
| Validation | 2026-06-23 to 2026-08-21 | 60 |
| Test | 2026-08-22 to 2026-11-19 | 90 |

- Modelling tables: `python -m epf.data.build_dataset` writes three Parquet tables per zone under `data/processed/` and validates them (DATA_NOTES, "Preprocessing"). `hourly/{ZONE}.parquet` is experiment H with 69120 rows, `quarter_hour/{ZONE}.parquet` is experiment Q with 39844 rows, and `weather/{ZONE}.parquet` has 23520 hourly rows with the run time of each forecast. The index is UTC. Calendar features and lags are not in these tables.
- The frozen snapshot is for experiments. The daily update job and dashboard use live data and are separate.

## 5. Forecast protocol and leakage rule

- Delivery day D runs 00:00–24:00 CET/CEST (Europe/Berlin, same offset in FR, ES and SE): 24 hourly or 96 quarter-hour MTUs.
- Forecast origin: day D-1, before the 12:00 CET gate closure. One forecast per zone per day.
- Known at origin:
  - Prices through the end of D-1 (cleared on D-2).
  - Calendar and holidays for D.
  - Day-ahead load forecast for D.
  - Day-ahead wind and solar forecast for D (see caveat).
  - Weather forecast runs issued before the origin.
  - Actual load and generation through D-2 only (conservative default).
- Not allowed: anything realised on D, measured weather for D, actuals from D-1 afternoon, scalers or statistics fitted on validation or test data.
- Caveat to document: ENTSO-E defines the day-ahead wind and solar forecast as the last one submitted before 18:00 on D-1, so the published value can postdate the 12:00 gate closure. The load forecast is due before gate closure under Regulation 543/2013 (verify). Check actual publication times per zone if the API exposes them. Otherwise state pre-noon availability as an assumption, as published studies do (arXiv 2611.16657 assumes it at 11:00 on D-1). RQ2's with/without comparison makes the dependency visible.
- Guard: the harness hands each model only data at or before the cutoff. A unit test asserts no feature timestamp is later than the cutoff.
- Refit default: statistical models and LightGBM refit weekly on an expanding window, foundation models run zero-shot daily. Cadence is configurable and logged.

## 6. Models

| # | Model | Library | Notes | Stage |
|---|---|---|---|---|
| 1 | Seasonal naive, same local MTU on D-7 | Own code | Reference for relative MAE | M2 must |
| 2 | SARIMA or ETS | `statsforecast` | Fit on a trailing window. If SARIMA is too slow at 15-min, use ETS or MSTL. M1 wording allows either | M2 must |
| 3 | LightGBM | `lightgbm` | Lagged prices, calendar, day-ahead load/wind/solar forecasts. Weather later. Quantile regression for intervals | M2 must (point), should (quantiles) |
| 4 | Chronos-2 zero-shot | `chronos-forecasting`, `amazon/chronos-2` | Univariate first | M2 should |
| 5 | TimesFM 2.5 zero-shot | `timesfm[torch]`, `google/timesfm-2.5-200m-pytorch` | Set `infer_is_positive=False` because prices go negative | M2 should |
| 6 | Chronos-2 with covariates | Same | Past and known-future covariates | M3 |
| 7 | Chronos-2 LoRA fine-tune | Same | Optional. Report time and compute cost for RQ3 | M3 optional |

For foundation models: pin the Hugging Face revision, treat context length as a hyperparameter chosen on validation, record run time and peak memory, verify context and horizon limits on the model card before coding.

The Swedish zones run every model with the hyperparameters and context lengths chosen on the core zones.

## 7. Evaluation

- Point: MAE, RMSE, relative MAE = MAE of model / MAE of seasonal naive on the same set.
- Intervals: quantile (pinball) loss and empirical coverage.
- Significance: Diebold-Mariano test on daily losses (M3).
- Cost: wall-clock time, peak memory, hardware.
- Error slices: spikes, negative prices, weekends, holidays, hour of day (M3).
- Reported per zone and per experiment (H, Q). Core zones in the main table, Swedish zones in their own table, flagged as extra.
- Compare zones on relative MAE, not MAE in EUR. Price levels differ several-fold between zones.
- Sanity range: a published 2025 hourly benchmark puts per-hour LightGBM at a relative MAE of about 0.42 for DE-LU and 0.43–0.48 for SE1–SE4 against the D-7 naive (arXiv 2611.16657, table in §3.1). Different test period and inputs, so ballpark only. If my numbers are much better, check for leakage first.

## 8. Repo layout and conventions

```
268490V-capstone-project/
├── CLAUDE.md                 # Claude Code instructions, imports docs/PROJECT_CONTEXT.md
├── README.md
├── requirements.txt          # pinned
├── .gitignore                # data/, .env, model caches
├── .env.example              # ENTSOE_API_TOKEN=
├── config/config.yaml        # zones, DATA_END, splits, seeds, model revisions
├── config/approved_gaps.yaml # approved columns and empty values of the processed tables
├── src/epf/
│   ├── data/                 # download_*.py, market_time.py, resolution.py, clean.py, validate.py, build_dataset.py, splits.py
│   ├── eda/                  # price_stats.py, price_plots.py, price_figures.py (DECISIONS entry 37),
│   │                         # driver_stats.py, spread_stats.py, driver_plots.py, driver_figures.py (entry 49)
│   ├── features/             # holiday_calendar.py
│   ├── models/               # naive.py, stats.py, lgbm.py, chronos2.py, timesfm25.py
│   ├── evaluation/           # backtest.py, metrics.py
│   └── dashboard/            # Streamlit app (M3)
├── scripts/                  # check_coverage.py (day-1 gate)
├── notebooks/                # EDA only
├── reports/figures/  reports/results/
├── docs/                     # PROJECT_CONTEXT.md, DECISIONS.md, DATA_NOTES.md, PROGRESS.md, architecture.md
└── tests/
```

- Zones come from config. Adding a zone is a config entry, never a code change. No zone names in code.
- Config marks each zone as `core` or `extra`. Every run processes core zones first, so Swedish zones never block core results.
- Tooling: Claude Code in the repo writes and runs code. The Claude Project is for planning, review, report and viva prep.
- `docs/PROJECT_CONTEXT.md` is the master copy of this file. Re-upload it to the Project when it changes.
- Commits: a plain subject without type prefixes, under 72 characters, starting with a verb. A short body only when the reason is not obvious. Written the way I would write it by hand (CLAUDE.md, Commits).
- `docs/PROGRESS.md`: one row per day with date, done, next, blockers.
- `docs/DECISIONS.md`: numbered entries with decision, reason, alternative rejected, date.

## 9. Plan to M2 (assumes submission Thu 3 Dec 2026)

| Date | Target | Commit-worthy output |
|---|---|---|
| Thu 19 Nov | Scaffold. Token smoke test. Coverage gate for 7 zones (§3.1) | Structure, CLAUDE.md, requirements, config, README stub, docs files, coverage table |
| Fri 20 Nov | Price ingestion, 7 zones, 2019 to now | ENTSO-E price downloader, raw to Parquet, Energy-Charts cross-check |
| Sat 21 Nov | Time handling and covariate ingestion | UTC index, clock-change tests, resolution split, covariate downloaders |
| Sun 22 Nov | Cleaning, validation, modelling tables. Freeze `DATA_END` | `clean.py`, `validate.py`, `build_dataset.py`, DATA_NOTES |
| Mon 23 Nov | EDA 1: distributions, daily and weekly patterns, spikes, negatives | Notebook and figures |
| Tue 24 Nov | EDA 2: price vs load, wind, solar. Hourly vs 15-min. 2022 regime. One Sweden north–south section | Notebook and figures |
| Wed 25 Nov | Backtest harness, metrics, seasonal naive end to end | `backtest.py`, `metrics.py`, leakage test, first results |
| Thu 26 Nov | SARIMA/ETS through the harness | `stats.py`, results |
| Fri 27 Nov | LightGBM features | Feature builder with cutoff test |
| Sat 28 Nov | LightGBM training, validation tuning, quantiles | `lgbm.py`, results |
| Sun 29 Nov | Chronos-2 and TimesFM 2.5 zero-shot | Wrappers, results |
| Mon 30 Nov | Comparison tables and plots. Architecture diagram | `reports/`, `docs/architecture.md` |
| Tue 1 Dec | README run steps, fresh-clone run, demo script | README, clean-up |
| Wed 2 Dec | Record demo. Buffer | Video link |
| Thu 3 Dec | Submit | |

Status on 24 Nov 2026: the rows up to Tue 24 Nov are done. The Sun 22 Nov row, the Mon 23 Nov row (EDA 1) and the Tue 24 Nov row (EDA 2) all closed on Tue 24 Nov. The dates above are the original targets and have not been moved. The backtest harness, the row of Wed 25 Nov, is next.

The Swedish zones ride along on every row through config. They get no day of their own, only one EDA section.

Cut order if behind (first cut first): Swedish work in the order given in §1, then TimesFM zero-shot, LightGBM quantiles, statistical baseline on experiment Q, weather features. Never cut: preprocessing for the 3 core zones, EDA, naive + one statistical baseline + LightGBM, diagram, video.

## 10. After M2 (weeks 9–12)

- The Swedish zones follow the core zones through all M3 work with no zone-specific tuning, and are reported as extra zones. Anything cut from M2 is picked up here.
- Weeks 9–11: Chronos-2 with covariates, optional LoRA fine-tune, weather features, intervals, Diebold-Mariano tests, error analysis, Streamlit dashboard with cheapest hours, daily update job.
- Week 12: final report, reproducibility checklist, code clean-up.

## 11. Open items (fill in)

- [ ] Exact M2 date and submission channel:
- [x] M1 feedback: approved as submitted, no scope changes
- [x] ENTSO-E token: in hand
- [ ] Laptop: OS, CPU, RAM, GPU:
- [x] Python version and env tool: 3.12, venv + pip. `entsoe-py` 1.0.0 needs Python 3.12 or newer (DECISIONS entry 2)
- [ ] Hours available on weekdays and weekends:
- [x] Swedish zones: all four (SE1, SE2, SE3, SE4), in M2
- [ ] Tell the supervisor about the Sweden addition, if one is assigned:
- [x] Where code is written and run: Claude Code in the repo, Claude Project for planning and review

## 12. Demo video outline (max 6 min)

| Time | Content |
|---|---|
| 0:00–0:30 | Problem, core zones plus the four Swedish zones as extras, scope |
| 0:30–1:30 | Architecture diagram and repo tour |
| 1:30–2:30 | Data pipeline run, cleaning rules, leakage rule |
| 2:30–3:30 | EDA highlights |
| 3:30–5:00 | Baseline vs LightGBM vs zero-shot results, one forecast plot. Sweden on one slide as the extra zones |
| 5:00–5:45 | What failed, trade-offs, next steps |
