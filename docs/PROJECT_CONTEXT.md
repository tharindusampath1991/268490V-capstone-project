# PROJECT_CONTEXT — CS5998 Capstone

Owner: A A T Sampath (268490V) · Last updated: 2026-11-27

## 0. Snapshot

| Item | Value |
|---|---|
| Module | CS5998 Capstone, MSc Data Science & AI, University of Moratuwa. 6 credits, individual |
| Title | Forecasting Next Day Electricity Prices in Europe with Time Series Foundation Models |
| Repo | https://github.com/tharindusampath1991/268490V-capstone-project (public) |
| Status on 19 Nov 2026 | M1 approved as submitted. ENTSO-E token in hand. No code yet. Roughly week 6 of 12 |
| Status on 24 Nov 2026 | Data pipeline built through preprocessing for all 7 zones: downloads, cleaning, validation and the modelling tables. `DATA_END` is frozen at 2026-11-19 (§4). EDA 1 is done: prices of the seven core zones on train days, six figures and `notebooks/01_eda_prices.ipynb`. EDA 2 is done: the price against the load, wind and solar forecast, the 15-minute prices, the high-price period and holidays for the seven core zones, and one section that compares the Swedish zones with each other, seven figures and `notebooks/01_eda_drivers.ipynb`. The backtest harness, the metrics and the seasonal naive forecast are done, with the leakage tests. The naive forecast is scored on the validation and the test days for all 7 zones on experiments H and Q, by owner decision (DECISIONS entry 50). The results of all seven zones are in `backtest_core.csv` and `daily_core.csv` under `reports/results/`. SARIMA or ETS is not started (§9) |
| Status on 25 Nov 2026 | The statistical baseline is done for all 7 zones. `statsforecast` 2.1.1 is pinned. AutoARIMA, AutoETS and MSTL run through the same backtest from `src/epf/models/stats.py`, on the price history only. 15 settings were compared on the validation days of experiment H, and by a rule fixed before the runs the winner is `mstl_182`: MSTL with a daily and a weekly season on 182 days of history (DECISIONS entries 62 to 65). Its mean relative MAE over the seven zones is 0.6887 on validation. The three best settings are a tie inside the noise. `mstl_182` was also scored on experiment Q validation (0.6831, entry 66) and once on the test days by owner decision: 0.5666 on H and 0.5691 on Q (entry 67). The lower test values come from a naive forecast that was much worse in the autumn. All rows are in `backtest_core.csv` and `daily_core.csv`. On 26 Nov 2026 I confirmed that `mstl_182` stays the baseline, and every measurement of the comparison, with the run times, was collected in `docs/MODEL_NOTES.md` (entry 68). LightGBM is not started (§9) |
| Status on 26 Nov 2026 | The LightGBM feature builder is done for all 7 zones on experiments H and Q, one day early. `src/epf/features/builder.py` builds each delivery day from inputs cut by `cutoff.py`, and `python -m epf.features.build` builds, prints and saves the frames: 28 features on the hourly table and 29 on the 15-minute table, in seven groups switched in the config (DECISIONS entries 69 to 80). I chose the features after measurements on train days, which are in `docs/MODEL_NOTES.md`. By my decision of the same day weather features are built too, with a fourth cut by run time in `cutoff.py`, and the backtest hands the weather table to every model (entries 78 and 80) |
| Status on 26 Nov 2026, LightGBM | LightGBM is done for all 7 zones on experiments H and Q, two days early. `lightgbm` 4.7.0 is pinned and used through its native API, without scikit-learn (DECISIONS entry 84). `src/epf/models/lgbm.py` runs through the same backtest and builds the training rows of every fit from the cut inputs (entry 85). 11 settings were compared on the validation days of experiment H, and by a rule fixed before the runs the winner is `lgbm_load_826_slow`: the price, calendar, load, wind and solar forecast features and actual load at D-2, with 400 trees at a learning rate of 0.025, on a moving window of 826 days (entries 86 to 88). Its mean relative MAE over the seven zones is 0.5316 on validation, against 0.6887 for `mstl_182`. The four best settings are a tie inside the noise. It was also scored on experiment Q validation (0.5782, entry 89) and once on the test days by owner decision: 0.4716 on H and 0.4792 on Q (entry 90). Quantile forecasts at five levels were scored on the validation days, and their intervals are too narrow in every zone (entry 91). The results table and the firmness analysis are commands of the repo (entry 83). All rows are in `backtest_core.csv`, `daily_core.csv` and `quantile_core.csv`, and the measurements are in `docs/MODEL_NOTES.md`. The documents were finished on 27 Nov 2026. Chronos-2 and TimesFM 2.5 are not started (§9) |
| Status on 27 Nov 2026 | Chronos-2 and TimesFM 2.5 zero-shot are done for all 7 zones on experiments H and Q, two days early. `torch` 2.15.0 in its CPU build, `chronos-forecasting` 2.3.2 and `timesfm` 3.0.2 are pinned, and the two model revisions are pinned in the config under `foundation_models` (DECISIONS entries 92 and 93). `src/epf/models/chronos2.py` and `timesfm25.py` run through the same backtest. They read the price history only and fit nothing. A context is given in days, and the point forecast of both is the median (entries 94 to 96). Four context lengths per model, 14, 28, 56 and 84 days, were compared on the validation days of experiment H by a rule fixed before the runs. The frozen settings are `chronos2_84` and `timesfm25_84` (entries 97 and 98). Mean relative MAE over the seven zones on validation: Chronos-2 0.5551 on H and 0.5837 on Q, TimesFM 0.6298 and 0.6440, against 0.5316 and 0.5782 for `lgbm_load_826_slow` and 0.6887 and 0.6831 for `mstl_182` (entry 99). The three longer contexts of each model are a tie inside the noise, and Chronos-2 against LightGBM is not settled on these 60 days. Neither model has been scored on the test days. That waits for my yes. Entries 92 to 100 are proposed and wait for my decision. The measurements are in `docs/MODEL_NOTES.md`. Comparison tables and plots and the architecture diagram are next (§9) |
| Next deadline | M2 Technical Checkpoint, assumed Thu 3 Dec 2026 (confirm, §11) |
| Grading | M1 25% · M2 25% · M3 50%. A viva can be called at any milestone |
| AI tools | Allowed. I must understand, justify and explain every decision and result |
| Zones | Seven core zones: DE-LU, FR, ES and SE1–SE4 (all of Sweden). All seven get the same analysis, tuning and reporting (§1, §3.1) |

## 1. Locked scope

- Problem: prediction of next-day (day-ahead) prices, with prediction intervals.
- Data: multivariate time series of prices, load, generation forecasts, weather.
- Techniques: statistical models, machine learning, deep learning foundation models.
- System: forecasting pipeline with a dashboard, plus an experimental comparison.
- Core zones: DE-LU, FR, ES, SE1, SE2, SE3, SE4. Seven zones in total. Rules:
  - Shown alike: README, results and report show the seven zones alike. Nothing marks or describes SE1–SE4 as added later (DECISIONS entry 81).
  - Same pipeline, one config entry per zone. Every analysis, model and results table covers all seven zones: preprocessing, EDA, baselines, LightGBM and the foundation models.
  - Coverage: the day-1 coverage check measured the series of every zone (§3.1).
  - Tuning: hyperparameters, history length and context lengths are chosen on the validation days of all seven zones. One setting per model for all zones, no setting per zone. No features that exist for one zone only.
  - Never cut: work on every zone has the same standing (§9). A delay in one zone delays M2.
  - Results: one table for all seven zones.
  - SE4 has no usable solar forecast, and SE1 and SE2 give near-duplicate results (§3.1). State both with the Swedish results.
- Research questions:
  - RQ1: How accurate are zero-shot foundation models versus seasonal naive, SARIMA/ETS and LightGBM?
  - RQ2: Do extra inputs (load, wind, solar forecasts, calendar) improve forecasts?
  - RQ3: Does fine-tuning a foundation model on local data help, and at what time and compute cost?
- Out of scope: intraday and balancing markets, beating professional trading forecasts, external LLM APIs, zones beyond the seven core zones, extra models.
- Success: the pipeline works end to end and the comparison is fair and repeatable, even if foundation models do not win.

## 2. Milestones mapped to artefacts

### M2 checklist (week 8, 25%)

| Guide requirement | Artefact | Done when |
|---|---|---|
| Data preprocessing completed | `src/epf/data/`, `docs/DATA_NOTES.md` | One command rebuilds clean tables for all 7 core zones, and validation checks pass |
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
- In the processed tables `actual_load` stands at its own delivery time, and `shortwave_radiation` is the mean of the hour before its timestamp. The feature builder applies the D-2 cut to the first and takes the second one hour later, so that it lines up with the delivery hour. The last hour of a day then has no radiation value (DECISIONS entries 33, 73 and 79).
- Energy-Charts now has `/v2` endpoints and lists FR, ES and SE1–SE4 as price zones, all in EUR/MWh. Check the endpoint catalogue before coding.
- `entsoe-py` 1.0.0: `query_day_ahead_prices` returns hourly values before 1 Oct 2025 and 15-min values after, in one series. Its `resolution` argument is deprecated. Load and wind/solar forecast queries are split by month, so a full pull is several hundred requests.
- ENTSO-E request URLs carry the token. Never print or log a raw request error.
- Sweden specifics are in §3.1.

### 3.1 Sweden (SE1–SE4) data check of 19 Nov 2026

Verdict: the Swedish data is usable for M2, and the day-1 coverage check confirmed it for each zone.

| Check | Finding |
|---|---|
| Prices | ENTSO-E areas `SE_1` to `SE_4`, EUR/MWh. Energy-Charts lists SE1–SE4 for the cross-check |
| 15-min switch | Same as DE-LU, FR and ES: delivery day 1 Oct 2025, all SDAC bidding zones |
| Auction and time zone | Same 12:00 CET day-ahead auction, CET/CEST. No protocol change |
| Load forecast, wind forecast | On ENTSO-E for all four. A Nov 2026 preprint (arXiv 2611.16657, public code) used both for SE1–SE4 over 2018–2025 |
| Solar forecast | Too sparse on ENTSO-E for Sweden; that study dropped it. Matters little in SE1–SE3, more in SE4 (see profiles) |
| Hydro | Reservoir inputs added nothing at the day-ahead horizon in that study. No hydro features needed |
| Holidays | `holidays` 0.109 covers Sweden, one calendar for all four zones. `public` gives 13 days in 2026. `de_facto` adds Julafton, Midsommarafton and Nyårsafton |
| Regime change | Nordic flow-based market coupling from delivery day 30 Oct 2024. Note it in the EDA |
| Cost (estimate) | No code of their own, since zones are config-driven. About 6–8 hours for their checks, EDA and tables |

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
- SE1 and SE2 are likely to give near-duplicate results: similar mix and almost the same mean price. EDA 2 measured it: their prices are identical in 98.61% of the train hours before 2024-10-30 and in 3.41% from that day (DECISIONS entry 48). Report them as two zones, but not as two independent pieces of evidence.
- SE4 has the most solar and no usable solar forecast. State it as a limitation.

The day-1 coverage check measured the series of all seven zones. `SE_1` to `SE_4` passed its rule in the runs of 21, 23 and 24 Nov 2026 (`docs/coverage_gate.md`). The Swedish solar forecast is marked drop, as expected. The columns marked drop are listed in the config under `coverage_gate.drop_columns` and are left out of the processed tables (DECISIONS entry 32).

Day-1 gate: `python scripts/check_coverage.py` (all 7 zones, 2019 onward, token from `.env`). It caches the raw downloads under `data/raw/entsoe/` and writes `docs/coverage_gate.md`, which is committed. The logic lives in `src/epf/data/coverage_gate.py` and has unit tests on synthetic data. It has run against the live API four times, last on 24 Nov 2026 for the frozen period 2019-01-01 to 2026-11-19. Rules:
- Prices: at least 99% of market time units present in every year. Days with gaps are counted.
- Load forecast and wind forecast: present on at least 95% of hours in every year.
- A forecast column below 95% is dropped for that zone and logged. Expected for Swedish solar.
- The gate gives a verdict only to a zone in the group `extra`. Such a zone is judged on its own, and one that fails on prices, load forecast or wind forecast leaves M2 and is retried in M3.
- Core zones are measured by the same rules but never cut. A forecast column below 95% is kept only by a logged decision. So far that is the ES wind forecast (DECISIONS entry 19).
- All seven zones are core zones, so a new gate run would give no zone a verdict. `docs/coverage_gate.md` is the report of 24 Nov 2026. It stays as the record of the measured coverage and is not written again. `DATA_END` is frozen, so the coverage cannot change.

The preprint is a reference and sanity range only. Do not copy its code. Cite it if its numbers are used.

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
- Weather cut, since 26 Nov 2026: a weather value is handed over when it stands before the end of D and its model run started at or before 00:00 UTC on D-1 (DECISIONS entry 78).
- Holidays, since 26 Nov 2026: the backtest hands the holiday dates of the country of the zone to every model in `DayInputs.holidays`. They are under no cut, because a calendar is known years ahead (DECISIONS entry 82).
- Refit default: statistical models and LightGBM refit weekly on an expanding window, foundation models run zero-shot daily. Cadence is configurable and logged.
- Windows of the frozen settings: the default is `backtest.history_days: null`, every day from the first row of the table. A model entry may set its own `history_days` and then gets a moving window of that many days. `mstl_182` is fitted on the last 182 days. `lgbm_load_826_slow` is fitted on the last 826 days on experiment H (819 training days, since the lags read the first 7). The 15-minute table starts on 2025-10-01 and is shorter than 826 days, so on experiment Q that setting trains on all the 15-minute history (DECISIONS entries 64, 85 and 89). Both refit every 7 days.
- Context of the zero-shot settings, since 27 Nov 2026: `chronos2_84` and `timesfm25_84` are not fitted. For each delivery day they read the last 84 days of prices before the price cut, counted in market time units: 2016 hours or 8064 quarter-hours (DECISIONS entries 94 and 98).

## 6. Models

| # | Model | Library | Notes | Stage |
|---|---|---|---|---|
| 1 | Seasonal naive, same local MTU on D-7 | Own code | Reference for relative MAE | M2 must |
| 2 | SARIMA or ETS | `statsforecast` | Fit on a trailing window. If SARIMA is too slow at 15-min, use ETS or MSTL. M1 wording allows either. Done on 25 Nov 2026: ARIMA, ETS and MSTL were compared, and the baseline is MSTL on 182 days, `mstl_182` (DECISIONS entry 64, `docs/MODEL_NOTES.md`) | M2 must |
| 3 | LightGBM | `lightgbm` | Lagged prices, calendar, day-ahead load/wind/solar forecasts. Weather later. Quantile regression for intervals. The feature builder is done since 26 Nov 2026 (DECISIONS entries 69 to 80, `docs/MODEL_NOTES.md`). It also builds actual load at D-2 and, by my decision of that day, the weather features. Done on 26 Nov 2026: 11 settings were compared on the validation days, and the frozen model is `lgbm_load_826_slow`, with the price, calendar, forecast and actual load features, without weather, on a moving window of 826 days (DECISIONS entries 84 to 90). Quantile forecasts at five levels are scored on the validation days, and their intervals are too narrow (entry 91). The numbers are in `docs/MODEL_NOTES.md` | M2 must (point), should (quantiles) |
| 4 | Chronos-2 zero-shot | `chronos-forecasting`, `amazon/chronos-2` | Univariate first. Done on 27 Nov 2026: the price history only, the 0.5 quantile as the point forecast, four context lengths compared on the validation days. The frozen setting is `chronos2_84`, with 84 days of context (DECISIONS entries 92 to 99, `docs/MODEL_NOTES.md`). Not scored on the test days | M2 should |
| 5 | TimesFM 2.5 zero-shot | `timesfm[torch]`, `google/timesfm-2.5-200m-pytorch` | Set `infer_is_positive=False` because prices go negative. Done on 27 Nov 2026: the price history only, with `infer_is_positive: false` in the config and refused otherwise (entry 96). The frozen setting is `timesfm25_84`, with 84 days of context (entries 92 to 99, `docs/MODEL_NOTES.md`). Not scored on the test days | M2 should |
| 6 | Chronos-2 with covariates | Same | Past and known-future covariates | M3 |
| 7 | Chronos-2 LoRA fine-tune | Same | Optional. Report time and compute cost for RQ3 | M3 optional |

For foundation models: pin the Hugging Face revision, treat context length as a hyperparameter chosen on validation, record run time and peak memory, verify context and horizon limits on the model card before coding.

All seven zones run every model. Hyperparameters, history length and context lengths are chosen on the validation days of all seven zones, one setting per model (§1).

## 7. Evaluation

- Point: MAE, RMSE, relative MAE = MAE of model / MAE of seasonal naive on the same set.
- Intervals: quantile (pinball) loss and empirical coverage.
- Significance: Diebold-Mariano test on daily losses (M3).
- Cost: wall-clock time, peak memory, hardware.
- Error slices: spikes, negative prices, weekends, holidays, hour of day (M3).
- Reported per zone and per experiment (H, Q), all seven zones in one table.
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
│   ├── features/             # holiday_calendar.py, builder.py (the LightGBM features of one delivery day,
│   │                         # DECISIONS entry 69), build.py (the command that builds every zone)
│   ├── models/               # naive.py, stats.py (ARIMA, ETS and MSTL, DECISIONS entries 62 and 63),
│   │                         # lgbm.py (LightGBM and its quantile forecasts, entries 85, 86 and 91),
│   │                         # chronos2.py and timesfm25.py (the two zero-shot models, entries 93 to 96),
│   │                         # zero_shot.py (what both share: the context and the entry checks, entry 94)
│   ├── evaluation/           # backtest.py, metrics.py, cutoff.py (the leakage rule, DECISIONS entry 51,
│   │                         # with the weather cut of entry 78 and the holiday dates of entry 82),
│   │                         # results.py (results files with the reader read_rows, run time, memory,
│   │                         # hardware, entries 54 and 55), tables.py (the results table) and
│   │                         # firmness.py (how firm a choice between settings is, entry 83),
│   │                         # quantiles.py (the quantile forecasts of the frozen LightGBM setting, entry 91)
│   ├── seed.py               # the one seed helper (entry 57)
│   └── dashboard/            # Streamlit app (M3)
├── scripts/                  # check_coverage.py (day-1 gate)
├── notebooks/                # EDA only
├── reports/figures/  reports/results/   # results: backtest_core.csv, daily_core.csv, quantile_core.csv
├── docs/                     # PROJECT_CONTEXT.md, DECISIONS.md, DATA_NOTES.md, MODEL_NOTES.md, PROGRESS.md, architecture.md
└── tests/
```

- Zones come from config. Adding a zone is a config entry, never a code change. No zone names in code.
- Each model setting is an entry under `models` in the config, and `--model` of the backtest takes its name. An entry may hold its own `history_days`. `backtest.statistical_baseline` names the frozen statistical model, `mstl_182`. The 14 candidates that lost stay in the config so that their rows can be reproduced (DECISIONS entries 64 and 65).
- `backtest.lightgbm_model` names the frozen LightGBM model, `lgbm_load_826_slow`, and `backtest.quantile_levels` holds the five levels of its quantile forecasts. The 10 LightGBM candidates that lost stay in the config too (DECISIONS entries 87, 88 and 91). `backtest.test_models` lists the three models that have been scored on the test days: `naive`, `mstl_182` and `lgbm_load_826_slow`.
- The config section `foundation_models` has one part per zero-shot family, `chronos2` and `timesfm25`: the model ID, the pinned Hugging Face revision and the fixed options. A model entry of such a family holds one setting, `context_days`. `backtest.chronos2_model` and `backtest.timesfm25_model` name the frozen settings, `chronos2_84` and `timesfm25_84`. The six candidates that lost stay in the config (DECISIONS entries 93, 97 and 98). No zero-shot setting stands under `backtest.test_models`.
- `torch`, `chronos` and `timesfm` are imported only when a zero-shot model loads its weights. The weights go to the Hugging Face cache of the user, outside the repo.
- Three commands stand beside the backtest under `src/epf/evaluation/`. `python -m epf.evaluation.tables` prints the results table from `backtest_core.csv`, and `python -m epf.evaluation.firmness` prints how firm a choice between settings is. Both only read. They read the results files through `results.read_rows`, and the firmness command also reads the forecast files and the processed tables (entry 83). `python -m epf.evaluation.quantiles` scores the quantile forecasts of the frozen LightGBM setting on the validation days and writes `reports/results/quantile_core.csv` (entry 91). It refuses the test days.
- The LightGBM features are set under `features` in the config: the groups that are built, the lags in days and the columns summed into each forecast feature. A results row holds the entry of the model and not this section, so a test in `tests/test_config.py` pins the section to the values of the LightGBM freeze (entry 88, Limits). `python -m epf.features.build` saves a copy of the frames under `data/features/`, which git ignores and the backtest never reads (DECISIONS entries 74 and 75).
- Config marks each zone as `core` or `extra`. All seven zones are `core` and no zone is `extra`. A run processes core zones before extra zones, should a zone be marked `extra`.
- Tooling: Claude Code in the repo writes and runs code. The Claude Project is for planning, review, report and viva prep.
- `docs/PROJECT_CONTEXT.md` is the master copy of this file. Re-upload it to the Project when it changes.
- Commits: a plain subject without type prefixes, under 72 characters, starting with a verb. A short body only when the reason is not obvious. Written the way I would write it by hand (CLAUDE.md, Commits).
- `docs/PROGRESS.md`: one row per day with date, done, next, blockers.
- `docs/DECISIONS.md`: numbered entries with decision, reason, alternative rejected, date.
- `docs/MODEL_NOTES.md`: the measured results of each model, one section per model: how it was measured, the settings tried, the result tables, the run times and the checks. It holds numbers, and DECISIONS holds the reasons (entry 68). Add a section when a model has run.

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

Status on 24 Nov 2026: the rows up to Tue 24 Nov are done. The Sun 22 Nov row, the Mon 23 Nov row (EDA 1) and the Tue 24 Nov row (EDA 2) all closed on Tue 24 Nov. The row of Wed 25 Nov (backtest harness, metrics, seasonal naive end to end) also closed on Tue 24 Nov, one day early. The dates above are the original targets and have not been moved. SARIMA or ETS through the harness, the row of Thu 26 Nov, is next.

Status on 25 Nov 2026: the row of Thu 26 Nov closed on Wed 25 Nov, one day early. The statistical baseline is `mstl_182`, chosen from 15 settings of ARIMA, ETS and MSTL on the validation days of all seven zones, and scored once on the test days (DECISIONS entries 62 to 67). It was also run on experiment Q, so the cut "statistical baseline on experiment Q" was not needed. LightGBM features, the row of Fri 27 Nov, is next.

Status on 26 Nov 2026: the row of Fri 27 Nov closed on Thu 26 Nov, one day early. The feature builder with its cutoff tests covers all seven zones on experiments H and Q (DECISIONS entries 69 to 80). On the same day I decided to build the weather features now, so "weather features" in the cut order below now means their use in LightGBM, not their code. LightGBM training, the row of Sat 28 Nov, came next on the same day.

Status on 26 Nov 2026, LightGBM: the row of Sat 28 Nov also closed on Thu 26 Nov, two days early, quantiles included. `lightgbm` 4.7.0 is installed and pinned. The frozen model is `lgbm_load_826_slow`, chosen from 11 settings on the validation days of all seven zones, scored on experiment Q and once on the test days (DECISIONS entries 82 to 90). Its quantile forecasts are scored on the validation days, so the cut "LightGBM quantiles" was not needed. Their intervals are too narrow and were not widened (entry 91). Weather features were in three of the 11 settings and are not in the frozen one, so the cut "weather features" was not needed either. The documents of this work were finished on Fri 27 Nov. Chronos-2 and TimesFM 2.5 zero-shot, the row of Sun 29 Nov, is next.

Status on 27 Nov 2026: the row of Sun 29 Nov closed on Fri 27 Nov, two days early. Both models run zero-shot through the same backtest on the price history only. The frozen settings are `chronos2_84` and `timesfm25_84`, each chosen from four context lengths on the validation days of all seven zones and scored on experiment Q (DECISIONS entries 92 to 100, proposed). TimesFM ran, so the cut "TimesFM zero-shot" was not needed. Neither model has been scored on the test days, which waits for my yes. Comparison tables and plots and the architecture diagram, the row of Mon 30 Nov, is next.

All seven zones are on every row through config, and both EDA parts cover all seven (DECISIONS entry 60).

Cut order if behind (first cut first): TimesFM zero-shot, LightGBM quantiles, statistical baseline on experiment Q, weather features. Never cut, for all 7 zones: preprocessing, EDA, naive + one statistical baseline + LightGBM. Also never cut: diagram, video. No zone is in the cut order.

## 10. After M2 (weeks 9–12)

- All seven zones go through all M3 work with one setting per model. Anything cut from M2 is picked up here.
- Weeks 9–11: Chronos-2 with covariates, optional LoRA fine-tune, weather features (built on 26 Nov 2026. LightGBM tried them and its frozen setting does not use them, DECISIONS entry 88. Their use in Chronos-2 is still open), intervals (the LightGBM quantile forecasts of 26 Nov 2026 are too narrow, entry 91), Diebold-Mariano tests, error analysis, Streamlit dashboard with cheapest hours, daily update job.
- Week 12: final report, reproducibility checklist, code clean-up.

## 11. Open items (fill in)

- [ ] Exact M2 date and submission channel:
- [x] M1 feedback: approved as submitted, no scope changes
- [x] ENTSO-E token: in hand
- [ ] Laptop: OS, CPU, RAM, GPU:
- [x] Python version and env tool: 3.12, venv + pip. `entsoe-py` 1.0.0 needs Python 3.12 or newer (DECISIONS entry 2)
- [ ] Hours available on weekdays and weekends:
- [x] Where code is written and run: Claude Code in the repo, Claude Project for planning and review

## 12. Demo video outline (max 6 min)

| Time | Content |
|---|---|
| 0:00–0:30 | Problem, the seven zones, scope |
| 0:30–1:30 | Architecture diagram and repo tour |
| 1:30–2:30 | Data pipeline run, cleaning rules, leakage rule |
| 2:30–3:30 | EDA highlights |
| 3:30–5:00 | Baseline vs LightGBM vs zero-shot results, one forecast plot. All seven zones in one table |
| 5:00–5:45 | What failed, trade-offs, next steps |
