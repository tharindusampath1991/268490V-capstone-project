## ENTSO-E coverage gate

Delivery days 2019-01-01 to 2026-11-19. Core zones come first, then the zones in the group "extra".

A zone passes when prices reach 99% and the load forecast and at least one wind column reach 95%, in every year. The gate table shows the lowest yearly share. The gate decides the extra zones only. Core zones are never cut, so their shares are shown without a verdict.

### Gate result

| zone | group | prices_min | load_fc_min | wind_fc_min | gate |
|---|---|---|---|---|---|
| DE_LU | core | 100.00% | 99.45% | 100.00% | not gated (core) |
| FR | core | 100.00% | 100.00% | 98.41% | not gated (core) |
| ES | core | 100.00% | 99.99% | 93.81% | not gated (core) |
| SE_1 | extra | 100.00% | 99.73% | 99.07% | PASS |
| SE_2 | extra | 100.00% | 99.73% | 99.07% | PASS |
| SE_3 | extra | 100.00% | 99.73% | 99.07% | PASS |
| SE_4 | extra | 100.00% | 99.73% | 99.07% | PASS |

### Forecast columns

A column below 95% in any year is marked drop for that zone. "keep by decision" marks a column that is below the threshold and is kept by a logged decision (docs/DECISIONS.md). Its missing days are handled in the cleaning step.

| zone | dataset | column | min_share | use |
|---|---|---|---|---|
| DE_LU | load_forecast | Forecasted Load | 99.45% | keep |
| DE_LU | wind_solar_forecast | Solar | 99.99% | keep |
| DE_LU | wind_solar_forecast | Wind Offshore | 100.00% | keep |
| DE_LU | wind_solar_forecast | Wind Onshore | 99.99% | keep |
| FR | load_forecast | Forecasted Load | 100.00% | keep |
| FR | wind_solar_forecast | Solar | 98.35% | keep |
| FR | wind_solar_forecast | Wind Onshore | 98.41% | keep |
| FR | wind_solar_forecast | Wind Offshore | 0.00% | drop |
| ES | load_forecast | Forecasted Load | 99.99% | keep |
| ES | wind_solar_forecast | Solar | 97.21% | keep |
| ES | wind_solar_forecast | Wind Onshore | 93.81% | keep by decision |
| SE_1 | load_forecast | Forecasted Load | 99.73% | keep |
| SE_1 | wind_solar_forecast | Wind Onshore | 99.07% | keep |
| SE_1 | wind_solar_forecast | Solar | 0.00% | drop |
| SE_2 | load_forecast | Forecasted Load | 99.73% | keep |
| SE_2 | wind_solar_forecast | Wind Onshore | 99.07% | keep |
| SE_2 | wind_solar_forecast | Solar | 0.00% | drop |
| SE_3 | load_forecast | Forecasted Load | 99.73% | keep |
| SE_3 | wind_solar_forecast | Wind Onshore | 99.07% | keep |
| SE_3 | wind_solar_forecast | Solar | 0.00% | drop |
| SE_4 | load_forecast | Forecasted Load | 99.73% | keep |
| SE_4 | wind_solar_forecast | Wind Onshore | 99.07% | keep |
| SE_4 | wind_solar_forecast | Solar | 0.00% | drop |

### Share of expected time steps present, by year

| zone | dataset | column | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|
| DE_LU | prices | price | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| DE_LU | load_forecast | Forecasted Load | 100.00% | 100.00% | 100.00% | 99.45% | 99.99% | 99.99% | 100.00% | 100.00% |
| DE_LU | wind_solar_forecast | Solar | 100.00% | 100.00% | 100.00% | 100.00% | 99.99% | 99.99% | 99.99% | 100.00% |
| DE_LU | wind_solar_forecast | Wind Offshore | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| DE_LU | wind_solar_forecast | Wind Onshore | 100.00% | 100.00% | 100.00% | 100.00% | 99.99% | 99.99% | 99.99% | 100.00% |
| FR | prices | price | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| FR | load_forecast | Forecasted Load | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| FR | wind_solar_forecast | Solar | 99.17% | 98.35% | 99.16% | 99.62% | 99.71% | 99.99% | 99.99% | 99.68% |
| FR | wind_solar_forecast | Wind Offshore | - | - | - | - | 40.29% | 100.00% | 100.00% | 99.99% |
| FR | wind_solar_forecast | Wind Onshore | 99.51% | 98.41% | 98.95% | 99.73% | 99.71% | 99.99% | 99.99% | 99.68% |
| ES | prices | price | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| ES | load_forecast | Forecasted Load | 100.00% | 100.00% | 100.00% | 99.99% | 100.00% | 100.00% | 100.00% | 100.00% |
| ES | wind_solar_forecast | Solar | 100.00% | 100.00% | 100.00% | 99.99% | 100.00% | 98.63% | 100.00% | 97.21% |
| ES | wind_solar_forecast | Wind Onshore | 100.00% | 99.73% | 100.00% | 99.99% | 100.00% | 99.73% | 99.73% | 93.81% |
| SE_1 | prices | price | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| SE_1 | load_forecast | Forecasted Load | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 99.73% | 100.00% |
| SE_1 | wind_solar_forecast | Solar | - | - | 8.22% | 99.45% | 100.00% | 100.00% | 99.18% | 99.07% |
| SE_1 | wind_solar_forecast | Wind Onshore | 99.73% | 100.00% | 100.00% | 99.45% | 100.00% | 100.00% | 99.18% | 99.07% |
| SE_2 | prices | price | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| SE_2 | load_forecast | Forecasted Load | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 99.73% | 100.00% |
| SE_2 | wind_solar_forecast | Solar | - | - | 8.22% | 99.45% | 100.00% | 100.00% | 99.18% | 99.07% |
| SE_2 | wind_solar_forecast | Wind Onshore | 99.73% | 100.00% | 100.00% | 99.45% | 100.00% | 100.00% | 99.18% | 99.07% |
| SE_3 | prices | price | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| SE_3 | load_forecast | Forecasted Load | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 99.73% | 100.00% |
| SE_3 | wind_solar_forecast | Solar | - | - | 8.22% | 99.45% | 100.00% | 100.00% | 99.18% | 99.07% |
| SE_3 | wind_solar_forecast | Wind Onshore | 99.73% | 100.00% | 100.00% | 99.45% | 100.00% | 100.00% | 99.18% | 99.07% |
| SE_4 | prices | price | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| SE_4 | load_forecast | Forecasted Load | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 99.73% | 100.00% |
| SE_4 | wind_solar_forecast | Solar | - | - | 8.22% | 99.45% | 100.00% | 100.00% | 99.18% | 99.07% |
| SE_4 | wind_solar_forecast | Wind Onshore | 99.73% | 100.00% | 100.00% | 99.45% | 100.00% | 100.00% | 99.18% | 99.07% |

### Native resolution

| zone | dataset | column | resolution |
|---|---|---|---|
| DE_LU | prices | price | 15min, 60min |
| DE_LU | load_forecast | Forecasted Load | 15min |
| DE_LU | wind_solar_forecast | Solar | 15min |
| DE_LU | wind_solar_forecast | Wind Offshore | 15min |
| DE_LU | wind_solar_forecast | Wind Onshore | 15min |
| FR | prices | price | 15min, 60min |
| FR | load_forecast | Forecasted Load | 15min, 60min |
| FR | wind_solar_forecast | Solar | 15min, 60min |
| FR | wind_solar_forecast | Wind Onshore | 15min, 60min |
| FR | wind_solar_forecast | Wind Offshore | 15min, 60min |
| ES | prices | price | 15min, 60min |
| ES | load_forecast | Forecasted Load | 15min, 60min |
| ES | wind_solar_forecast | Solar | 15min, 60min |
| ES | wind_solar_forecast | Wind Onshore | 15min, 60min |
| SE_1 | prices | price | 15min, 60min |
| SE_1 | load_forecast | Forecasted Load | 15min, 60min |
| SE_1 | wind_solar_forecast | Wind Onshore | 15min, 60min |
| SE_1 | wind_solar_forecast | Solar | 15min, 60min |
| SE_2 | prices | price | 15min, 60min |
| SE_2 | load_forecast | Forecasted Load | 15min, 60min |
| SE_2 | wind_solar_forecast | Wind Onshore | 15min, 60min |
| SE_2 | wind_solar_forecast | Solar | 15min, 60min |
| SE_3 | prices | price | 15min, 60min |
| SE_3 | load_forecast | Forecasted Load | 15min, 60min |
| SE_3 | wind_solar_forecast | Wind Onshore | 15min, 60min |
| SE_3 | wind_solar_forecast | Solar | 15min, 60min |
| SE_4 | prices | price | 15min, 60min |
| SE_4 | load_forecast | Forecasted Load | 15min, 60min |
| SE_4 | wind_solar_forecast | Wind Onshore | 15min, 60min |
| SE_4 | wind_solar_forecast | Solar | 15min, 60min |

### Delivery days with at least one missing price

| zone | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| DE_LU | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| FR | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ES | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SE_1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SE_2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SE_3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SE_4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### Repeated timestamps, summed over the years

| zone | dataset | duplicates |
|---|---|---|
| DE_LU | prices | 0 |
| DE_LU | load_forecast | 0 |
| DE_LU | wind_solar_forecast | 0 |
| FR | prices | 0 |
| FR | load_forecast | 0 |
| FR | wind_solar_forecast | 0 |
| ES | prices | 0 |
| ES | load_forecast | 0 |
| ES | wind_solar_forecast | 0 |
| SE_1 | prices | 0 |
| SE_1 | load_forecast | 0 |
| SE_1 | wind_solar_forecast | 0 |
| SE_2 | prices | 0 |
| SE_2 | load_forecast | 0 |
| SE_2 | wind_solar_forecast | 0 |
| SE_3 | prices | 0 |
| SE_3 | load_forecast | 0 |
| SE_3 | wind_solar_forecast | 0 |
| SE_4 | prices | 0 |
| SE_4 | load_forecast | 0 |
| SE_4 | wind_solar_forecast | 0 |
