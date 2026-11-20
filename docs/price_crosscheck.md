## Price cross-check: ENTSO-E against Energy-Charts

ENTSO-E is the only source of prices in this project (DECISIONS entries 7 and 12). Energy-Charts prices are compared timestamp by timestamp. They are never used to correct or fill ENTSO-E values.

Two prices count as different when they are more than 0.01 EUR/MWh apart. max_abs_diff is in EUR/MWh. The last two columns count timestamps that only one source has.

Energy-Charts data: CC BY 4.0, Bundesnetzagentur | SMARD.de, through the Energy-Charts API of Fraunhofer ISE (api.energy-charts.info).

Checked locally, results not published: ES, SE_1, SE_2, SE_3. Energy-Charts provides the prices of these zones for private and internal use only.

### Result by zone and year

| zone | year | compared | mismatches | max_abs_diff | only_entsoe | only_energy_charts |
|---|---|---|---|---|---|---|
| DE_LU | 2019 | 8760 | 0 | 0.00 | 0 | 0 |
| DE_LU | 2020 | 8784 | 0 | 0.00 | 0 | 0 |
| DE_LU | 2021 | 8760 | 0 | 0.00 | 0 | 0 |
| DE_LU | 2022 | 8760 | 0 | 0.00 | 0 | 0 |
| DE_LU | 2023 | 8760 | 0 | 0.00 | 0 | 0 |
| DE_LU | 2024 | 8784 | 0 | 0.00 | 0 | 0 |
| DE_LU | 2025 | 15387 | 0 | 0.00 | 0 | 0 |
| DE_LU | 2026 | 31008 | 0 | 0.00 | 0 | 0 |
| FR | 2019 | 8760 | 0 | 0.00 | 0 | 0 |
| FR | 2020 | 8784 | 0 | 0.00 | 0 | 0 |
| FR | 2021 | 8760 | 0 | 0.00 | 0 | 0 |
| FR | 2022 | 8760 | 0 | 0.00 | 0 | 0 |
| FR | 2023 | 8760 | 0 | 0.00 | 0 | 0 |
| FR | 2024 | 8784 | 0 | 0.00 | 0 | 0 |
| FR | 2025 | 15387 | 0 | 0.00 | 0 | 0 |
| FR | 2026 | 31008 | 0 | 0.00 | 0 | 0 |
| SE_4 | 2019 | 8760 | 0 | 0.00 | 0 | 0 |
| SE_4 | 2020 | 8784 | 0 | 0.00 | 0 | 0 |
| SE_4 | 2021 | 8760 | 0 | 0.00 | 0 | 0 |
| SE_4 | 2022 | 8760 | 0 | 0.00 | 0 | 0 |
| SE_4 | 2023 | 8760 | 0 | 0.00 | 0 | 0 |
| SE_4 | 2024 | 8784 | 0 | 0.00 | 0 | 0 |
| SE_4 | 2025 | 15387 | 0 | 0.00 | 0 | 0 |
| SE_4 | 2026 | 31008 | 0 | 0.00 | 0 | 0 |
