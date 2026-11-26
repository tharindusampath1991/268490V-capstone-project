# Model notes

Measured results of the models: what was run, on which days, with which settings, what came out and what it cost. The reasons for each choice are in [DECISIONS.md](DECISIONS.md). This file holds the numbers.

Every number here comes from `reports/results/backtest_core.csv` or from the printed output of a command named beside it. Blocks in a fixed-width font are printed output, copied as it was.

Milestone 1 approved DE_LU, FR and ES only. SE_1 to SE_4 were added on 19 Nov 2026 and made core zones on 24 Nov 2026 (DECISIONS entries 1 and 59). SE_1 and SE_2 are near-duplicates (entry 48), so seven zones are not seven independent results. MAE and RMSE are in EUR/MWh. Zones differ several-fold in price level, so zones are compared on relative MAE only.

## Statistical baseline: `mstl_182`

### In short

- The statistical baseline is `mstl_182`: `MSTL(season_length=[24, 168], trend_forecaster=AutoETS(model="AZN"))` from `statsforecast` 2.1.1, fitted on the prices of the 182 days before the delivery day. It reads the price history only.
- It was chosen on 25 Nov 2026 from 15 settings of AutoARIMA, AutoETS and MSTL. All 15 ran on the 60 validation days of experiment H for all seven zones. The rule was fixed before the runs: the lowest mean relative MAE over the seven zones wins.
- The three best settings, MSTL on 91, 182 and 364 days, are a tie inside the noise of 60 days. `mstl_182` won by the rule, not by a clear margin.
- The owner approved the frozen setting on 25 Nov 2026 and confirmed on 26 Nov 2026, after the test run, that `mstl_182` stays the baseline.
- Mean relative MAE over the seven zones: 0.6887 on validation H, 0.6831 on validation Q, 0.5666 on test H and 0.5691 on test Q.
- Time: the 14 queued validation commands took 3 hours 47 minutes. The validation run on experiment Q took 2 hours 57 minutes. The one test run took 4 hours 44 minutes.

### 1. How a forecast is measured

**The backtest.** Every model runs through `python -m epf.evaluation.backtest`. For each delivery day D and zone it makes one forecast per market time unit of D. The model receives prices only up to 00:00 Europe/Berlin on D, so through the end of D-1 (DECISIONS entry 51). The statistical models read nothing but these prices.

**The days.**

| Split | Delivery days | Days | Hours per zone (H) | Quarter-hours per zone (Q) |
|---|---|---|---|---|
| Train | 2019-01-01 to 2026-06-22 (H), 2025-10-01 to 2026-06-22 (Q) | 2730 and 265 | | |
| Validation | 2026-06-23 to 2026-08-21 | 60 | 1440 | 5760 |
| Test | 2026-08-22 to 2026-11-19 | 90 | 2161 | 8644 |

The test days hold the 25-hour day 2026-10-25. The validation days hold no clock change.

**Fit and forecast.** A model is fitted on the first scored day and then every 7th delivery day. That is 9 fits per zone on the validation days, so 63 fits and 420 forecasts in one run of seven zones, and 13 fits per zone on the test days. The fit uses the `history_days` calendar days of prices that end at the price cut. On every day the forecast applies the fitted model to the window that ends at that day's price cut, with `forward` (entry 63).

**The metrics.** With e as the actual price minus the forecast:

- MAE is the mean of |e| over all market time units of one zone, experiment and split.
- RMSE is the root of the mean of e².
- Relative MAE is the MAE of the model divided by the MAE of the seasonal naive forecast on the same market time units. The naive forecast is the price at the same local time 7 days before (entries 52 and 53). A value below 1 beats the naive forecast.
- "Mean" in a table is the plain mean of the seven zone values.

**The checks of every run.** The number of scored days, the number of market time units, no empty forecast, and every forecast is a finite number. A run with a failed check writes nothing.

**Time and memory.** "Day loop" is `wall_seconds` of the results file: the time around the loop over the delivery days of one zone, with the cuts, the fits and the forecasts, and without reading the table or writing results. "Command, start to end" is the wall clock of the whole command, read from the log of the run queue. It also holds the naive reference, the reading and the writing. Peak memory is the highest working set of the process (entry 55).

**The machine.** All runs were made on one laptop. The results rows name it as `AMD64 Family 26 Model 36 Stepping 0, AuthenticAMD | 12 cores, 24 threads | 59.6 GB RAM | Windows 11`. Python 3.12.10, `statsforecast` 2.1.1, seed 42. No GPU is used.

**Where the results are.** `reports/results/backtest_core.csv` holds 154 rows: one per run, zone and experiment. `reports/results/daily_core.csv` holds the losses per delivery day. The forecasts per market time unit are under `data/forecasts/{model}/{experiment}/{split}/{ZONE}.parquet`, which git ignores.

### 2. Season lengths, measured on train days

Measured on 25 Nov 2026 before any model ran, on train days only. Autocorrelation at chosen lags, an MSTL decomposition, and an ADF test. Strength is 1 minus the variance of the remainder over the variance of the component plus the remainder.

```
===== experiment H: train days, season lengths 24 and 168 =====
train period 2018-12-31 23:00:00+00:00 to 2026-06-22 21:00:00+00:00 UTC, step 0 days 01:00:00
zone     rows empty gaps    <=0       min       max
DE_LU   65519     0    0   2537   -500.00    936.28
FR      65519     0    0   2146   -496.86   2987.78
ES      65519     0    0   2430    -15.00    700.00
SE_1    65519     0    0   1846    -74.11    590.00
SE_2    65519     0    0   2159    -60.04    590.00
SE_3    65519     0    0   1718    -60.04    799.97
SE_4    65519     0    0   1666    -60.04    799.97

autocorrelation, all train days
zone       12     23     24     25     48    144    167    168    169    192    336   five highest local peaks (lag)
DE_LU   0.817  0.868  0.877  0.859  0.802  0.774  0.781  0.793  0.779  0.758  0.741   [24, 12, 48, 168, 144]
FR      0.890  0.915  0.921  0.911  0.877  0.855  0.859  0.866  0.857  0.835  0.806   [24, 12, 48, 168, 72]
ES      0.828  0.904  0.914  0.899  0.862  0.814  0.811  0.822  0.811  0.797  0.773   [24, 48, 72, 12, 168]
SE_1    0.791  0.782  0.781  0.770  0.658  0.551  0.540  0.544  0.541  0.515  0.422   [23, 47, 72, 96, 120]
SE_2    0.781  0.764  0.763  0.752  0.637  0.537  0.522  0.526  0.523  0.500  0.404   [23, 47, 72, 96, 120]
SE_3    0.632  0.770  0.782  0.759  0.639  0.608  0.627  0.641  0.624  0.586  0.556   [24, 168, 48, 10, 144]
SE_4    0.679  0.767  0.780  0.754  0.641  0.595  0.601  0.618  0.601  0.576  0.536   [24, 11, 48, 168, 72]

autocorrelation, last 364 train days
zone       12     23     24     25     48    144    167    168    169    192    336   five highest local peaks (lag)
DE_LU   0.198  0.615  0.659  0.591  0.498  0.471  0.448  0.490  0.441  0.460  0.462   [24, 48, 168, 144, 336]
FR      0.395  0.675  0.709  0.655  0.557  0.469  0.423  0.458  0.417  0.402  0.385   [24, 48, 72, 144, 120]
ES      0.171  0.784  0.825  0.770  0.717  0.616  0.587  0.629  0.583  0.582  0.571   [24, 48, 72, 96, 168]
SE_1    0.772  0.717  0.714  0.697  0.524  0.433  0.405  0.409  0.403  0.388  0.383   [23, 48, 72, 96, 120]
SE_2    0.763  0.704  0.701  0.684  0.511  0.425  0.396  0.400  0.395  0.384  0.381   [23, 48, 72, 96, 120]
SE_3    0.607  0.657  0.672  0.631  0.448  0.426  0.437  0.462  0.437  0.409  0.436   [24, 11, 168, 48, 336]
SE_4    0.485  0.625  0.648  0.599  0.442  0.417  0.434  0.465  0.433  0.413  0.429   [24, 12, 168, 48, 336]

MSTL with periods 24 and 168, and ADF with 168 lags, last 364 train days
zone    strength 24  strength 168  trend  ADF stat       p
DE_LU         0.672         0.333  0.369     -4.94  0.0000
FR            0.615         0.266  0.580     -4.05  0.0012
ES            0.797         0.343  0.707     -3.54  0.0071
SE_1          0.214         0.230  0.710     -3.43  0.0101
SE_2          0.201         0.219  0.699     -3.39  0.0111
SE_3          0.463         0.358  0.617     -3.51  0.0077
SE_4          0.539         0.357  0.543     -3.76  0.0034

===== experiment Q: train days, season lengths 96 and 672 =====
train period 2025-09-30 22:00:00+00:00 to 2026-06-22 21:45:00+00:00 UTC, step 0 days 00:15:00
zone     rows empty gaps    <=0       min       max
DE_LU   25440     0    0   1603   -499.99    544.75
FR      25440     0    0   2409   -498.65    291.10
ES      25440     0    0   3486    -10.00    250.00
SE_1    25440     0    0    432    -94.59    417.76
SE_2    25440     0    0    742    -11.68    471.97
SE_3    25440     0    0    529    -14.49    518.28
SE_4    25440     0    0    585    -15.59    519.08

autocorrelation, all train days
zone       48     95     96     97    192    576    671    672    673    768   1344   five highest local peaks (lag)
DE_LU   0.176  0.625  0.640  0.619  0.486  0.457  0.446  0.461  0.445  0.431  0.422   [96, 192, 672, 576, 768]
FR      0.405  0.674  0.687  0.668  0.547  0.448  0.414  0.426  0.412  0.371  0.346   [96, 192, 288, 480, 576]
ES      0.265  0.816  0.820  0.812  0.717  0.578  0.579  0.584  0.578  0.544  0.532   [96, 192, 288, 384, 672]
SE_1    0.744  0.693  0.695  0.687  0.495  0.399  0.370  0.374  0.370  0.347  0.359   [25, 29, 92, 96, 73]
SE_2    0.737  0.681  0.684  0.676  0.488  0.397  0.365  0.368  0.364  0.348  0.353   [29, 92, 96, 73, 79]
SE_3    0.539  0.628  0.633  0.621  0.399  0.367  0.399  0.405  0.399  0.354  0.388   [96, 44, 40, 31, 672]
SE_4    0.416  0.605  0.611  0.598  0.397  0.361  0.404  0.411  0.404  0.366  0.386   [96, 44, 672, 192, 1344]

last 364 train days: skipped, the train set of experiment Q is shorter

MSTL with periods 96 and 672, and ADF with 672 lags, last 265 train days
zone    strength 96  strength 672  trend  ADF stat       p
DE_LU         0.660         0.343  0.353     -4.35  0.0004
FR            0.592         0.251  0.571     -3.36  0.0125
ES            0.780         0.316  0.731     -2.93  0.0421
SE_1          0.234         0.245  0.694     -2.98  0.0369
SE_2          0.221         0.229  0.686     -2.98  0.0364
SE_3          0.471         0.375  0.573     -3.05  0.0307
SE_4          0.534         0.367  0.488     -3.39  0.0114
```

What it shows:

- No zone has a gap or an empty price. Prices at or below zero occur in every zone, so no transform that needs positive prices can be used.
- The daily season is clear in DE_LU, FR, ES, SE_3 and SE_4: strength 0.46 to 0.80, with the autocorrelation peaking at lag 24 or 96.
- The daily season is weak in SE_1 and SE_2: strength 0.20 to 0.23. On the hourly table the autocorrelation at lag 24 is not above lag 23.
- The weekly season is weaker everywhere: strength 0.22 to 0.38.
- The ADF test rejects a unit root at the 5% level in every zone on these windows.

So season lengths of 24 and 168 hours, and 96 and 672 quarter-hours, are backed for five zones and weak for the two northern Swedish zones. One setting serves all zones (entry 59).

### 3. Timing before the runs

One fit and one forecast between two fits per candidate, on train days, to size the comparison. "forward" is the forecast on the window one day later.

DE_LU, both experiments, 25 Nov 2026:

```
first call of the session (ets, 28 days): 0.12 s

===== DE_LU experiment H, 65519 train values, season 24 =====
family days values    fit s forward s   fc min   fc max nan  form
ets      28    672     0.08      0.00   156.01   156.01   0  ETS(A,N,N)
ets      56   1344     0.17      0.00   156.01   156.01   0  ETS(A,N,N)
ets      91   2184     0.27      0.00   156.01   156.01   0  ETS(A,N,N)
ets     182   4368     0.56      0.00   156.01   156.01   0  ETS(A,N,N)
ets     364   8736     2.12      0.00   156.01   156.01   0  ETS(A,N,N)
mstl     28    672     0.14      0.13    45.19   213.74   0  trend ETS(A,N,N)
mstl     56   1344     0.27      0.26    58.82   215.75   0  trend ETS(A,N,N)
mstl     91   2184     0.44      0.43    63.46   220.04   0  trend ETS(A,N,N)
mstl    182   4368     0.89      0.86    63.48   221.41   0  trend ETS(A,N,N)
mstl    364   8736     1.78      1.74    63.49   221.41   0  trend ETS(A,N,N)
arima    28    672    39.34      0.01    21.88   211.86   0  ARIMA(3,0,1)(0,1,1)[24] coef ['ar1', 'ar2', 'ar3', 'ma1', 'sma1']
arima    56   1344   277.39      0.07    20.13   212.37   0  ARIMA(1,0,4)(2,1,0)[24] coef ['ar1', 'ma1', 'ma2', 'ma3', 'ma4', 'sar1', 'sar2']
arima    91   2184   313.25      0.06    21.89   215.27   0  ARIMA(1,0,4)(2,1,0)[24] coef ['ar1', 'ma1', 'ma2', 'ma3', 'ma4', 'sar1', 'sar2']
arima: a fit took more than 300 s, longer histories are not timed

===== DE_LU experiment Q, 25440 train values, season 96 =====
family days values    fit s forward s   fc min   fc max nan  form
mstl     28   2688     2.12      2.25    42.84   231.03   0  trend ETS(A,N,N)
mstl     56   5376     4.27      4.20    58.00   237.74   0  trend ETS(A,Ad,N)
mstl     91   8736     6.91      6.79    63.36   243.04   0  trend ETS(A,Ad,N)
mstl    182  17472    13.68     13.36    63.36   244.27   0  trend ETS(A,Ad,N)
ets      28   2688     1.62      0.00   126.59   144.47   0  ETS(A,Ad,N)
ets      56   5376     3.15      0.00   126.30   144.42   0  ETS(A,Ad,N)
arima    28   2688  1034.24      0.99    18.78   251.54   0  ARIMA(0,0,0)(1,1,0)[96] coef ['sar1']
arima: a fit took more than 300 s, longer histories are not timed
```

Second round: ETS with fixed forms, the default ARIMA search in two more zones, and three faster ARIMA searches. "small" is `max_p=2, max_q=2, max_P=1, max_Q=1`, where the defaults are 5, 5, 2 and 2:

```
setting                      zone   days    fit s    fwd s   fc min   fc max nan  form
ets ANN                      DE_LU    28     0.00     0.00   156.01   156.01   0  ETS(A,N,N) aicc 8762
ets ANN                      DE_LU    56     0.00     0.00   156.01   156.01   0  ETS(A,N,N) aicc 18517
ets ANN                      DE_LU    91     0.00     0.00   156.01   156.01   0  ETS(A,N,N) aicc 31057
ets ANN                      DE_LU   182     0.00     0.00   156.01   156.01   0  ETS(A,N,N) aicc 63374
ets ANN                      DE_LU   364     0.01     0.00   156.01   156.01   0  ETS(A,N,N) aicc 133374
ets ANA                      DE_LU    28     0.03     0.00    56.57   221.06   0  ETS(A,N,A) aicc 9091
ets ANA                      DE_LU    56     0.05     0.00    53.92   221.93   0  ETS(A,N,A) aicc 19324
ets ANA                      DE_LU    91     0.08     0.00    57.64   239.10   0  ETS(A,N,A) aicc 32230
ets ANA                      DE_LU   182     0.17     0.00    32.35   246.94   0  ETS(A,N,A) aicc 65798
ets ANA                      DE_LU   364     0.67     0.00    24.49   244.82   0  ETS(A,N,A) aicc 136269
ets AZA                      DE_LU    28     0.08     0.00    56.57   221.06   0  ETS(A,N,A) aicc 9091
ets AZA                      DE_LU    56     0.16     0.00    53.92   221.93   0  ETS(A,N,A) aicc 19324
ets AZA                      DE_LU    91     0.25     0.00    57.64   239.10   0  ETS(A,N,A) aicc 32230
ets AZA                      DE_LU   182     0.53     0.00    32.35   246.94   0  ETS(A,N,A) aicc 65798
ets AZA                      DE_LU   364     2.05     0.00    24.49   244.82   0  ETS(A,N,A) aicc 136269
ets AZZ                      DE_LU    28     0.09     0.00   156.01   156.01   0  ETS(A,N,N) aicc 8762
ets AZZ                      DE_LU    56     0.17     0.00   156.01   156.01   0  ETS(A,N,N) aicc 18517
ets AZZ                      DE_LU    91     0.28     0.00   156.01   156.01   0  ETS(A,N,N) aicc 31057
ets AZZ                      DE_LU   182     0.56     0.00   156.01   156.01   0  ETS(A,N,N) aicc 63374
ets AZZ                      DE_LU   364     2.12     0.00   156.01   156.01   0  ETS(A,N,N) aicc 133374
ets AZZ                      FR       56     0.18     0.00   143.56   143.56   0  ETS(A,N,N) aicc 17927
ets AZA                      FR       56     0.16     0.00    47.57   171.63   0  ETS(A,N,A) aicc 18642
ets AZZ                      SE_1     56     0.18     0.00     5.54     5.54   0  ETS(A,N,N) aicc 15740
ets AZA                      SE_1     56     0.17     0.00    -4.02    15.17   0  ETS(A,N,A) aicc 16798
arima default                FR       28    34.39     0.02    16.74   150.12   0  ARIMA(1,0,1)(0,1,2)[24]
arima default                SE_1     28    26.80     0.01     4.69     6.92   0  ARIMA(1,1,1)(2,0,0)[24]
arima approximation          DE_LU    28     2.00     0.01    21.65   203.44   0  ARIMA(5,0,2)(1,1,1)[24]
arima approximation          DE_LU    56    29.47     0.04    18.22   211.05   0  ARIMA(4,0,1)(2,1,0)[24]
arima approximation          DE_LU    91    71.53     0.06    24.06   217.42   0  ARIMA(4,0,2)(2,1,0)[24]
arima small                  DE_LU    28     7.16     0.01    18.60   209.67   0  ARIMA(2,0,2)(0,1,1)[24]
arima small                  DE_LU    56    21.14     0.01    18.89   220.11   0  ARIMA(2,0,2)(1,1,0)[24]
arima small                  DE_LU    91    33.88     0.02    20.13   222.14   0  ARIMA(2,0,2)(1,1,0)[24]
arima small approximation    DE_LU    28     0.75     0.01    15.86   199.76   0  ARIMA(2,0,2)(1,1,1)[24]
arima small approximation    DE_LU    56     1.00     0.01    18.83   220.21   0  ARIMA(1,0,2)(1,1,0)[24]
arima small approximation    DE_LU    91     1.85     0.02    20.13   222.14   0  ARIMA(2,0,2)(1,1,0)[24]
```

ETS with the form `AZA` and a season of 96 on the 15-minute train prices of DE_LU:

```
  28 days   2688 values  fit    1.61 s  forward  0.00 s  ETS(A,Ad,A)  forecast 42.52 to 236.99
  56 days   5376 values  fit    3.24 s  forward  0.00 s  ETS(A,Ad,A)  forecast 38.82 to 229.74
  91 days   8736 values  fit    4.94 s  forward  0.00 s  ETS(A,Ad,A)  forecast 39.03 to 229.80
 182 days  17472 values  fit    9.88 s  forward  0.00 s  ETS(A,Ad,A)  forecast 38.40 to 229.76
```

What it shows:

- Fully automatic ETS (`AZZ`) chooses no season: `ETS(A,N,N)` in DE_LU, FR and SE_1. Its forecast is one flat value for the whole day. Its AICc is lower than with a season (18517 against 19324 in DE_LU at 56 days), because the criterion scores one step ahead. So the ETS candidates fix the additive season (`AZA`), and one `AZZ` setting stays in the comparison as the record of this.
- The default ARIMA search takes 27 to 39 seconds per fit on 28 days and 277 seconds on 56 days. So the default search runs on 28 days only, and a smaller search runs on 28, 56 and 91 days.
- `approximation=True` is faster but printed 243 "possible convergence problem" warnings in these six fits. It is not used.
- On the 15-minute table one default ARIMA fit took 1034 seconds. A comparison of all settings on experiment Q was not affordable.

### 4. What `forward` does between two fits

Read from the installed source of `statsforecast` 2.1.1:

- ARIMA: the orders stay, and the coefficients are passed as fixed values.
- ETS: the form, the smoothing parameters and the initial state stay.
- MSTL: the window is decomposed again, and only the fitted trend model stays.

Checked on DE_LU train days, 56 days of history. The columns are the largest absolute difference between two forecasts:

```
1. forward on the fit window against predict, and forward on later windows (largest absolute difference)
model         fwd=predict  refit=fit   +24 h vs +25 h, shifted back  +24 h same start
ets AZA          0.00e+00   0.00e+00                         0.2912            0.2449
mstl             0.00e+00   0.00e+00                         1.7109            2.2978
arima small      0.00e+00   0.00e+00                         0.0000            0.0000

2. ETS with a season of 96 on the 15-minute prices, 28 train days
ANA: ETS(A,N,A), forecast min 22.88 max 215.16, distinct values 96
AZA: ETS(A,Ad,A), forecast min 42.91 max 236.96, distinct values 96
AZZ: ETS(A,Ad,N), forecast min 126.44 max 144.45, distinct values 81
```

- `forward` on the fit window gives exactly the forecast of `predict`, so the model has one code path.
- A second fit on the same window gives the same forecast.
- The last two columns show how much a forecast moves when the window starts one hour earlier, or at the same point as the fit.

### 5. The 15 settings

| Name | Model | History days |
|---|---|---|
| `ets_28`, `ets_56`, `ets_91`, `ets_182`, `ets_364` | `AutoETS(season_length=24, model="AZA")` | 28, 56, 91, 182, 364 |
| `ets_auto_56` | `AutoETS(season_length=24, model="AZZ")` | 56 |
| `mstl_28`, `mstl_56`, `mstl_91`, `mstl_182`, `mstl_364` | `MSTL(season_length=[24, 168], trend_forecaster=AutoETS(model="AZN"))` | 28, 56, 91, 182, 364 |
| `arima_28` | `AutoARIMA(season_length=24)`, default search | 28 |
| `arima_small_28`, `arima_small_56`, `arima_small_91` | `AutoARIMA(season_length=24, max_p=2, max_q=2, max_P=1, max_Q=1)` | 28, 56, 91 |

- Each setting is an entry under `models` in `config/config.yaml`, and its settings are copied into every results row.
- History lengths are whole weeks. No history above 364 days was tried, and ARIMA none above 91.
- No Box-Cox argument is set. Every ETS form has an additive error, so no multiplicative form can be chosen (entry 62).
- The owner approved the 15 settings and the rule on 25 Nov 2026, before any full run.

### 6. The rule

Fixed before the runs: the winner is the setting with the lowest mean relative MAE over the seven zones on the validation days of experiment H, among the settings whose run passes every check. Run time is reported and does not decide.

### 7. Validation results, experiment H

60 validation days, 1440 hours per zone, runs of 25 Nov 2026. Every run passed every check. The rows are sorted by the mean. SE_1 to SE_4 were added after Milestone 1, which approved DE_LU, FR and ES only.

Relative MAE:

| Setting | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean | Mean without SE_2 |
|---|---|---|---|---|---|---|---|---|---|
| `mstl_182` | 0.7106 | 0.6521 | 0.7165 | 0.7317 | 0.6666 | 0.6596 | 0.6837 | 0.6887 | 0.6924 |
| `mstl_364` | 0.7106 | 0.6520 | 0.7165 | 0.7373 | 0.6706 | 0.6596 | 0.6838 | 0.6901 | 0.6933 |
| `mstl_91` | 0.7133 | 0.6538 | 0.7161 | 0.7382 | 0.6647 | 0.6612 | 0.6839 | 0.6902 | 0.6944 |
| `mstl_56` | 0.7358 | 0.6686 | 0.7208 | 0.7645 | 0.6931 | 0.6771 | 0.6900 | 0.7071 | 0.7095 |
| `arima_28` | 0.7805 | 0.7380 | 0.8053 | 0.6925 | 0.6529 | 0.6711 | 0.6870 | 0.7182 | 0.7291 |
| `arima_small_28` | 0.7917 | 0.7353 | 0.8808 | 0.6527 | 0.6511 | 0.6806 | 0.6763 | 0.7241 | 0.7362 |
| `arima_small_56` | 0.7844 | 0.7321 | 0.8697 | 0.6961 | 0.6434 | 0.6793 | 0.6830 | 0.7269 | 0.7408 |
| `arima_small_91` | 0.8106 | 0.7786 | 0.8601 | 0.6550 | 0.6599 | 0.6691 | 0.6804 | 0.7305 | 0.7423 |
| `mstl_28` | 0.7764 | 0.6997 | 0.7378 | 0.8319 | 0.7824 | 0.6920 | 0.7020 | 0.7460 | 0.7400 |
| `ets_56` | 0.9255 | 0.7698 | 0.8481 | 0.6952 | 0.6586 | 0.6752 | 0.6868 | 0.7513 | 0.7667 |
| `ets_28` | 0.9607 | 0.7739 | 0.8522 | 0.6903 | 0.6693 | 0.6712 | 0.6934 | 0.7587 | 0.7736 |
| `ets_91` | 0.9894 | 0.7783 | 0.8419 | 0.6767 | 0.6539 | 0.6810 | 0.6960 | 0.7596 | 0.7772 |
| `ets_182` | 0.9674 | 0.7925 | 0.8538 | 0.6754 | 0.6657 | 0.7064 | 0.7547 | 0.7737 | 0.7917 |
| `ets_364` | 1.0155 | 0.8010 | 0.8646 | 0.6775 | 0.6668 | 0.6910 | 0.7520 | 0.7812 | 0.8003 |
| naive | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `ets_auto_56` | 1.5910 | 1.5868 | 1.2686 | 0.7314 | 0.6902 | 0.8390 | 0.9348 | 1.0917 | 1.1586 |

MAE in EUR/MWh:

| Setting | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 |
|---|---|---|---|---|---|---|---|
| `mstl_182` | 24.86 | 22.23 | 17.39 | 13.49 | 13.32 | 19.76 | 31.26 |
| `mstl_364` | 24.86 | 22.23 | 17.39 | 13.60 | 13.40 | 19.76 | 31.26 |
| `mstl_91` | 24.95 | 22.29 | 17.38 | 13.61 | 13.28 | 19.81 | 31.27 |
| `mstl_56` | 25.74 | 22.79 | 17.50 | 14.10 | 13.85 | 20.29 | 31.55 |
| `arima_28` | 27.30 | 25.16 | 19.55 | 12.77 | 13.04 | 20.11 | 31.41 |
| `arima_small_28` | 27.69 | 25.07 | 21.38 | 12.03 | 13.01 | 20.39 | 30.92 |
| `arima_small_56` | 27.44 | 24.96 | 21.11 | 12.84 | 12.85 | 20.35 | 31.23 |
| `arima_small_91` | 28.35 | 26.54 | 20.88 | 12.08 | 13.18 | 20.05 | 31.11 |
| `mstl_28` | 27.15 | 23.85 | 17.91 | 15.34 | 15.63 | 20.73 | 32.10 |
| `ets_56` | 32.37 | 26.24 | 20.59 | 12.82 | 13.16 | 20.23 | 31.40 |
| `ets_28` | 33.60 | 26.38 | 20.69 | 12.73 | 13.37 | 20.11 | 31.70 |
| `ets_91` | 34.61 | 26.54 | 20.44 | 12.48 | 13.06 | 20.40 | 31.82 |
| `ets_182` | 33.84 | 27.02 | 20.73 | 12.45 | 13.30 | 21.16 | 34.50 |
| `ets_364` | 35.52 | 27.31 | 20.99 | 12.49 | 13.32 | 20.70 | 34.38 |
| naive | 34.98 | 34.09 | 24.28 | 18.44 | 19.98 | 29.96 | 45.72 |
| `ets_auto_56` | 55.65 | 54.10 | 30.80 | 13.49 | 13.79 | 25.14 | 42.74 |

RMSE in EUR/MWh:

| Setting | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 |
|---|---|---|---|---|---|---|---|
| `mstl_182` | 40.28 | 29.48 | 23.29 | 21.75 | 21.17 | 26.38 | 43.56 |
| `mstl_364` | 40.28 | 29.48 | 23.29 | 21.51 | 21.23 | 26.38 | 43.57 |
| `mstl_91` | 40.41 | 29.54 | 23.28 | 21.87 | 20.94 | 26.45 | 43.63 |
| `mstl_56` | 41.32 | 30.12 | 23.36 | 22.17 | 21.67 | 27.01 | 44.12 |
| `arima_28` | 43.66 | 34.67 | 26.66 | 21.48 | 20.89 | 28.12 | 45.58 |
| `arima_small_28` | 43.50 | 35.37 | 29.53 | 20.39 | 20.65 | 28.47 | 45.96 |
| `arima_small_56` | 44.22 | 34.51 | 29.34 | 21.47 | 20.74 | 29.17 | 46.82 |
| `arima_small_91` | 45.43 | 36.70 | 30.32 | 20.35 | 20.76 | 28.54 | 46.62 |
| `mstl_28` | 42.86 | 31.41 | 24.02 | 24.11 | 24.11 | 27.55 | 44.65 |
| `ets_56` | 47.66 | 34.33 | 27.41 | 20.99 | 20.58 | 27.11 | 43.35 |
| `ets_28` | 47.78 | 33.99 | 27.40 | 20.86 | 20.56 | 26.84 | 43.33 |
| `ets_91` | 51.70 | 34.31 | 27.21 | 20.37 | 20.13 | 27.14 | 44.27 |
| `ets_182` | 49.46 | 35.92 | 28.42 | 20.45 | 20.60 | 28.10 | 47.96 |
| `ets_364` | 52.37 | 36.11 | 28.84 | 20.31 | 20.82 | 27.74 | 47.92 |
| naive | 58.01 | 47.38 | 34.17 | 28.91 | 30.30 | 41.87 | 64.82 |
| `ets_auto_56` | 79.84 | 74.00 | 49.56 | 22.81 | 22.56 | 35.27 | 61.29 |

Time and memory. "Day loops per fit" is the sum of the day loops divided by the 63 fits of a run, with the forecasts in it. The naive row is the run of 24 Nov 2026.

| Setting | History days | Run started (UTC) | Day loops, sum (s) | Fastest zone (s) | Slowest zone (s) | Day loops per fit (s) | Peak memory (MB) | Command, start to end (min) |
|---|---|---|---|---|---|---|---|---|
| `mstl_182` | 182 | 06:53:20 | 565.9 | 60.4 | 94.9 | 8.98 | 248 | 9.5 |
| `mstl_364` | 364 | 07:02:50 | 1314.7 | 175.1 | 190.7 | 20.87 | 247 | 22.0 |
| `mstl_91` | 91 | 06:48:34 | 281.8 | 30.1 | 47.7 | 4.47 | 247 | 4.8 |
| `mstl_56` | 56 | 06:45:04 | 205.0 | 28.3 | 29.7 | 3.25 | 246 | 3.5 |
| `arima_28` | 28 | 08:58:21 | 5254.9 | 369.4 | 1577.9 | 83.41 | 241 | 87.6 |
| `arima_small_28` | 28 | 07:24:50 | 923.4 | 55.1 | 177.0 | 14.66 | 248 | 15.5 |
| `arima_small_56` | 56 | 07:40:18 | 1529.5 | 96.1 | 323.5 | 24.28 | 243 | 25.6 |
| `arima_small_91` | 91 | 08:05:52 | 3143.9 | 188.5 | 685.2 | 49.90 | 243 | 52.5 |
| `mstl_28` | 28 | 06:43:15 | 104.0 | 14.1 | 15.5 | 1.65 | 249 | 1.8 |
| `ets_56` | 56 | 06:38:37 | 10.5 | 1.4 | 1.5 | 0.17 | 248 | 0.2 |
| `ets_28` | 28 | 06:38:18 | 5.7 | 0.8 | 0.8 | 0.09 | 245 | not recorded |
| `ets_91` | 91 | 06:38:51 | 17.1 | 2.4 | 2.5 | 0.27 | 246 | 0.3 |
| `ets_182` | 182 | 06:39:11 | 34.0 | 4.8 | 5.1 | 0.54 | 247 | 0.6 |
| `ets_364` | 364 | 06:39:49 | 180.0 | 18.5 | 34.5 | 2.86 | 250 | 3.1 |
| naive | all | 14:52:26 | 2.1 | 0.2 | 0.3 | 0.03 | 155 | not recorded |
| `ets_auto_56` | 56 | 06:42:53 | 17.8 | 1.6 | 2.8 | 0.28 | 245 | 0.4 |

- The 14 queued commands ran from 12:08:35 to 15:55:56 local time, 227.3 minutes in all. `ets_28` ran before the queue as a first check and its command time was not recorded.
- The day loops of the 15 settings sum to 13588 seconds.
- ARIMA is slow and uneven: the day loop of `arima_28` took 369 seconds in its fastest zone and 1578 in its slowest.

By the rule the winner is `mstl_182`.

### 8. How firm the choice is

Printed by a script that reads `daily_core.csv` and the saved forecasts. The bootstrap draws whole validation days with replacement, 2000 times with seed 42, and computes the mean relative MAE over the seven zones for each draw.

```
1. Recompute from the forecast files, without the harness metrics
   105 model and zone pairs. Largest relative difference of MAE and relative MAE to the saved rows: 0.0e+00
   forecasts outside the validation days or not 1440 per zone: 0. Actual prices that differ from the processed table: 0
   mean of the 60 daily MAE values against the pooled MAE, largest relative difference: 2.7e-16. Days per model and zone: [60]

2. Are mstl_182 and mstl_364 really different runs?
   DE_LU  largest forecast difference 182 vs 364:    0.0605   182 vs 91:    4.0931
   FR     largest forecast difference 182 vs 364:    0.0268   182 vs 91:    4.6421
   ES     largest forecast difference 182 vs 364:    0.0270   182 vs 91:    2.2135
   SE_1   largest forecast difference 182 vs 364:   16.0993   182 vs 91:    4.1303
   SE_2   largest forecast difference 182 vs 364:    4.9758   182 vs 91:   12.0279
   SE_3   largest forecast difference 182 vs 364:    0.0357   182 vs 91:    2.8175
   SE_4   largest forecast difference 182 vs 364:    0.0562   182 vs 91:    3.2752

3. Mean relative MAE over the seven zones, by half of the validation days
                first 30 days  last 30 days  all 60 days
mstl_182               0.7135        0.6694       0.6887
mstl_364               0.7142        0.6715       0.6901
mstl_91                0.7171        0.6690       0.6902
mstl_56                0.7335        0.6877       0.7071
arima_28               0.7534        0.6891       0.7182
arima_small_28         0.7659        0.6910       0.7241
arima_small_56         0.7694        0.6925       0.7269
arima_small_91         0.7748        0.6975       0.7305
mstl_28                0.7898        0.7113       0.7460
ets_56                 0.7797        0.7265       0.7513
ets_28                 0.7880        0.7351       0.7587
ets_91                 0.7991        0.7222       0.7596
ets_182                0.8097        0.7420       0.7737
ets_364                0.8170        0.7484       0.7812
ets_auto_56            1.0766        1.1421       1.0917

4. How often is each setting the best of the 15 in a zone, and its rank by the median over zones
                zones won  median over zones    mean
mstl_182              2.0             0.6837  0.6887
mstl_364              1.0             0.6838  0.6901
mstl_91               1.0             0.6839  0.6902
mstl_56               0.0             0.6931  0.7071
arima_28              0.0             0.6925  0.7182
arima_small_28        2.0             0.6806  0.7241
arima_small_56        1.0             0.6961  0.7269
arima_small_91        0.0             0.6804  0.7305
mstl_28               0.0             0.7378  0.7460
ets_56                0.0             0.6952  0.7513
ets_28                0.0             0.6934  0.7587
ets_91                0.0             0.6960  0.7596
ets_182               0.0             0.7547  0.7737
ets_364               0.0             0.7520  0.7812
ets_auto_56           0.0             0.9348  1.0917
   best setting per zone: {'DE_LU': 'mstl_182', 'FR': 'mstl_364', 'ES': 'mstl_91', 'SE_1': 'arima_small_28', 'SE_2': 'arima_small_56', 'SE_3': 'mstl_182', 'SE_4': 'arima_small_28'}

5. Bootstrap over the 60 validation days (2000 resamples of whole days, seed 42):
   difference in mean relative MAE over the seven zones, other setting minus mstl_182
   mstl_364        mean +0.0015   95% interval -0.0032 to +0.0073   share of resamples where mstl_182 is better: 69.0%
   mstl_91         mean +0.0014   95% interval -0.0029 to +0.0056   share of resamples where mstl_182 is better: 74.3%
   mstl_56         mean +0.0185   95% interval +0.0047 to +0.0334   share of resamples where mstl_182 is better: 99.7%
   arima_28        mean +0.0286   95% interval -0.0218 to +0.0797   share of resamples where mstl_182 is better: 87.2%
   arima_small_28  mean +0.0350   95% interval -0.0148 to +0.0877   share of resamples where mstl_182 is better: 91.4%
   ets_56          mean +0.0638   95% interval +0.0043 to +0.1306   share of resamples where mstl_182 is better: 98.7%
```

- The top three are a tie. The intervals of `mstl_364` and `mstl_91` against `mstl_182` both hold zero. `mstl_182` is first in the first 30 days, and `mstl_91` is first in the last 30 days.
- MSTL against ARIMA is not settled on 60 days: the interval of `arima_28` holds zero. `mstl_56` and `ets_56` are behind `mstl_182`.
- The zones disagree. An MSTL setting is best in DE_LU, FR, ES and SE_3. An `arima_small` setting is best in SE_1, SE_2 and SE_4. SE_1 and SE_2 are the zones with the weakest daily season.
- Without SE_2 the order of the top three is the same: 0.6924, 0.6933 and 0.6944.

**Why not `mstl_364`.** Its mean is 0.6901 against 0.6887, so it lost by the rule with a gap of 0.0014. In DE_LU, FR, ES, SE_3 and SE_4 the two settings give the same relative MAE to three decimals, and their forecasts differ by at most 0.06 EUR/MWh there. The whole gap comes from SE_1 and SE_2, where `mstl_364` is worse by 0.0056 and 0.0040. Why the longer history hurts in those two zones was not looked into. `mstl_364` also takes 1315 seconds against 566, and on experiment Q it would get only 265 to 324 days, because the 15-minute table starts on 2025-10-01. Neither of these two points decided the choice.

### 9. Checks of the comparison

The same numbers on a second run. DE_LU was run twice in memory for one setting of each family, and nothing was written:

```
model            zone              MAE run 1            MAE run 2            MAE saved  largest forecast difference  run 1 = saved
mstl_182         DE_LU    24.855428051361589   24.855428051361589   24.855428051361589                    0.000e+00           True
ets_56           DE_LU    32.369763008777653   32.369763008777653   32.369763008777653                    0.000e+00           True
arima_small_28   DE_LU    27.690873353919272   27.690873353919272   27.690873353919272                    0.000e+00           True
```

Further checks, all on 25 Nov 2026:

- The MAE and the relative MAE of all 105 rows were computed again from the forecast files, without the metric code of the backtest. The largest relative difference to the saved rows is 0.0e+00 (first block of the output above).
- No forecast lies outside the validation days, every zone has 1440 forecasts per setting, and every actual price equals the processed table.
- The `naive_mae` of every row equals the saved naive row of its zone.
- Leakage. The lowest relative MAE of any setting in any zone is 0.6434. The published per-hour LightGBM values are about 0.42 to 0.48 (PROJECT_CONTEXT §7). A price-only model that beat them would be a leakage alarm. None comes near.
- The tests move the price cut on purpose: with the cut one day too late, 23 tests failed, 6 of them tests of the statistical models.

### 10. Experiment Q, validation

`mstl_182` with the same config entry, where the seasons are 96 and 672 quarter-hours. No other setting ran on experiment Q (entry 66). Every check passed. SE_1 to SE_4 were added after Milestone 1.

| Zone | Relative MAE | MAE | RMSE | Naive MAE | Day loop (s) | Peak memory (MB) | Market time units |
|---|---|---|---|---|---|---|---|
| DE_LU | 0.6611 | 23.35 | 40.14 | 35.31 | 1483.7 | 216 | 5760 |
| FR | 0.6528 | 22.74 | 30.78 | 34.83 | 1489.4 | 219 | 5760 |
| ES | 0.7160 | 17.56 | 23.79 | 24.53 | 1341.1 | 219 | 5760 |
| SE_1 | 0.7267 | 13.67 | 21.68 | 18.81 | 1491.2 | 219 | 5760 |
| SE_2 | 0.6682 | 13.58 | 21.41 | 20.32 | 1509.3 | 219 | 5760 |
| SE_3 | 0.6617 | 20.10 | 27.09 | 30.37 | 1797.7 | 219 | 5760 |
| SE_4 | 0.6955 | 32.24 | 45.17 | 46.36 | 1490.9 | 219 | 5760 |
| Mean | 0.6831 | 20.46 | 30.01 | 30.08 |  |  |  |

- The day loops sum to 10603 seconds, 176.7 minutes. The command ran from 16:06:29 to 19:03:16 local time on 25 Nov 2026.
- That is about 19 times the 566 seconds of experiment H, because `forward` decomposes a window of 17472 values again on every delivery day.

For comparison, `mstl_182` on experiment H validation:

| Zone | Relative MAE | MAE | RMSE | Naive MAE | Day loop (s) | Peak memory (MB) | Market time units |
|---|---|---|---|---|---|---|---|
| DE_LU | 0.7106 | 24.86 | 40.28 | 34.98 | 94.7 | 221 | 1440 |
| FR | 0.6521 | 22.23 | 29.48 | 34.09 | 94.9 | 234 | 1440 |
| ES | 0.7165 | 17.39 | 23.29 | 24.28 | 94.8 | 239 | 1440 |
| SE_1 | 0.7317 | 13.49 | 21.75 | 18.44 | 86.1 | 242 | 1440 |
| SE_2 | 0.6666 | 13.32 | 21.17 | 19.98 | 60.4 | 244 | 1440 |
| SE_3 | 0.6596 | 19.76 | 26.38 | 29.96 | 69.6 | 246 | 1440 |
| SE_4 | 0.6837 | 31.26 | 43.56 | 45.72 | 65.4 | 248 | 1440 |
| Mean | 0.6887 | 20.33 | 29.42 | 29.63 |  |  |  |

### 11. Test run

Run once, on 25 Nov 2026 from 19:04:39 to 23:48:15 local time, from commit `31bfb35`, after the frozen setting was committed and the owner said yes (entry 67). 90 test days. Every check passed in all 14 runs. No other candidate has seen the test days. SE_1 to SE_4 were added after Milestone 1.

Experiment H:

| Zone | Relative MAE | MAE | RMSE | Naive MAE | Day loop (s) | Peak memory (MB) | Market time units |
|---|---|---|---|---|---|---|---|
| DE_LU | 0.4831 | 33.30 | 47.13 | 68.92 | 156.1 | 222 | 2161 |
| FR | 0.5151 | 32.64 | 45.32 | 63.37 | 153.2 | 236 | 2161 |
| ES | 0.6137 | 28.21 | 39.65 | 45.97 | 153.0 | 241 | 2161 |
| SE_1 | 0.6439 | 20.12 | 30.28 | 31.25 | 148.6 | 241 | 2161 |
| SE_2 | 0.6486 | 23.64 | 35.72 | 36.44 | 145.5 | 241 | 2161 |
| SE_3 | 0.5499 | 31.84 | 42.93 | 57.91 | 144.3 | 244 | 2161 |
| SE_4 | 0.5116 | 40.90 | 57.43 | 79.95 | 146.9 | 248 | 2161 |
| Mean | 0.5666 | 30.09 | 42.64 | 54.83 |  |  |  |

Experiment Q:

| Zone | Relative MAE | MAE | RMSE | Naive MAE | Day loop (s) | Peak memory (MB) | Market time units |
|---|---|---|---|---|---|---|---|
| DE_LU | 0.4901 | 33.94 | 48.18 | 69.26 | 2491.8 | 249 | 8644 |
| FR | 0.5182 | 33.14 | 45.63 | 63.96 | 2212.9 | 249 | 8644 |
| ES | 0.6181 | 28.69 | 40.35 | 46.42 | 2246.0 | 249 | 8644 |
| SE_1 | 0.6496 | 20.77 | 31.03 | 31.98 | 2323.1 | 249 | 8644 |
| SE_2 | 0.6466 | 24.03 | 35.92 | 37.16 | 2080.7 | 249 | 8644 |
| SE_3 | 0.5512 | 32.15 | 43.44 | 58.33 | 2304.4 | 249 | 8644 |
| SE_4 | 0.5101 | 41.15 | 57.95 | 80.67 | 2300.9 | 249 | 8644 |
| Mean | 0.5691 | 30.55 | 43.21 | 55.39 |  |  |  |

- The day loops sum to 1048 seconds on H and 15960 seconds on Q, 17007 seconds in all. The command took 283.6 minutes.
- The peak memory was 249 MB.

Checks after the run:

- The `naive_mae` of all 14 new rows equals the MAE of the saved naive test rows.
- `git diff` showed 14 added lines in `backtest_core.csv` and 1260 in `daily_core.csv`, and no removed line.
- Three DE_LU forecasts were made again from a table that holds no row from the price cut of the day on:

```
   fit day 2026-08-22, delivery day 2026-08-22: 24 hours, last price seen 2026-08-21 21:00:00+00:00, largest difference to the saved forecast 0.00e+00
   fit day 2026-10-24, delivery day 2026-10-25: 25 hours, last price seen 2026-10-24 21:00:00+00:00, largest difference to the saved forecast 0.00e+00
   fit day 2026-10-24, delivery day 2026-10-29: 24 hours, last price seen 2026-10-28 22:00:00+00:00, largest difference to the saved forecast 0.00e+00
```

**Why the test values are lower than the validation values.** On experiment H the mean relative MAE fell from 0.6887 to 0.5666. The model did not get more accurate: its mean MAE rose from 20.33 to 30.09. The naive forecast got much worse: its mean MAE rose from 29.63 to 54.83. So the ratio fell because the price of 7 days before was a poor forecast in the autumn. The DE_LU value of 0.4831 is above the published LightGBM value of about 0.42 for that zone, and the Swedish values of 0.51 to 0.65 are above the published 0.43 to 0.48. These published values are for another period.

### 12. Run time: estimate against measured

The estimates came from the single timed fits of section 3.

| Part | Estimate | Measured, command start to end |
|---|---|---|
| ETS settings | about 4 minutes for 6 | 4.6 minutes for 5. `ets_28` was not recorded, and its day loops took 5.7 seconds |
| 5 MSTL settings | about 32 minutes | 41.6 minutes |
| `arima_28` | about 35 minutes | 87.6 minutes |
| 3 `arima_small` settings | about 66 minutes | 93.6 minutes |
| All 14 queued commands | about 2.3 hours for all 15 | 227.3 minutes, which is 3 hours 47 minutes |
| `mstl_182` on experiment Q, validation | about 2 hours, later about 2.5 hours | 176.8 minutes |
| `mstl_182` on the test days, H and Q | about 3.5 hours, later about 4.6 hours | 283.6 minutes |

- The ARIMA estimates were too low by a factor of 1.4 to 2.5. One timed fit on one zone and one window does not stand for 63 fits: the search takes a different time on every window.
- The MSTL estimates were too low by a factor of about 1.3.
- For the next models, time one whole zone before estimating a run.

### 13. Limits

- The winner was picked among 15 settings on the same 60 days, so its validation value of 0.6887 is somewhat optimistic. The 60 days are one summer.
- The top three settings cannot be told apart on 60 days.
- The models count steps, not clock hours. After the clock change of 2026-10-25 the daily pattern sits one step off until the model has adapted. The error of those days was not looked at separately.
- The setting was chosen on the hourly table and not tuned on the 15-minute table.
- The baseline uses no load, wind, solar or weather input.
- The forms that the models chose in each fit, such as the ARIMA orders, were not saved.
- The test numbers are known from now on. They must not steer any later choice.

### 14. How to run it again

```
.venv\Scripts\python -m epf.data.build_dataset
.venv\Scripts\python -m epf.evaluation.backtest --model mstl_182 --split validation --experiment H
.venv\Scripts\python -m epf.evaluation.backtest --model mstl_182 --split validation --experiment Q
```

- Any of the 15 names of section 5 can stand in place of `mstl_182`. A run adds rows to `backtest_core.csv` and replaces the rows of the same model, experiment, split and zone in `daily_core.csv`.
- Do not run `--split test` again. The test run of `mstl_182` was done once, and the 14 other settings are refused there.
- The season evidence, the timing and the checks of sections 2, 3, 4, 8 and 9 were made with scripts outside the repo. Their printed output is in this file.

The commits of 25 Nov 2026:

| Commit | What it holds |
|---|---|
| `6776034` | `statsforecast` 2.1.1 pinned |
| `6f7424b` | `--experiment`, a history length per model entry, the finite check |
| `c98dd38` | `src/epf/models/stats.py` and its tests |
| `2a4e95a` | the 15 settings in the config |
| `9cb1983` | the validation rows of the 15 settings, experiment H |
| `bdf41d5` | `backtest.statistical_baseline: mstl_182` |
| `8ce11f9` | the validation rows of `mstl_182`, experiment Q |
| `31bfb35` | `mstl_182` added to `backtest.test_models` |
| `ab6d1ec` | the test rows of `mstl_182` |
| `59ff2fb` | DECISIONS entries 62 to 67, README, PROJECT_CONTEXT, PROGRESS |

## LightGBM features

Built on 26 Nov 2026 (DECISIONS entries 69 to 80). No LightGBM model has run yet. This section holds what was measured to choose the features, and the checks of the built frames. Every measurement that chose a feature reads train delivery days only.

### In short

- `python -m epf.features.build` builds one frame per zone and experiment: one row per market time unit, 28 features on the hourly table and 29 on the 15-minute table.
- Each delivery day is built from inputs cut to that day by `day_inputs` of `src/epf/evaluation/cutoff.py`. The price of the delivery day is never in the frame.
- Every zone has the same columns. The Swedish zones have no solar forecast, so their three solar features are empty.
- The hourly frames have 69120 rows per zone and the 15-minute frames 39844. All 21635852 cells equal a plain pandas computation on the whole table.
- Weather exists from delivery day 2024-03-15 only.

### 1. The features

| Group | Features | Read from | Known through |
|---|---|---|---|
| `price` | `price_lag_1` to `price_lag_7` | The price at the same wall-clock time 1 to 7 days before | End of D-1 |
| `price` | `price_d1_mean`, `price_d1_min`, `price_d1_max`, `price_d1_last` | Every price of D-1. One number per day, repeated on its rows | End of D-1 |
| `calendar` | `hour`, `weekday`, `holiday`, and `quarter_hour` on the 15-minute frame | The delivery day in market time. `holiday` is a nationwide holiday of the country of the zone | Known in advance |
| `load_forecast` | `load_forecast`, `load_forecast_lag_1`, `load_forecast_lag_7` | The day-ahead load forecast at the target time and 1 and 7 days before | End of D |
| `wind_forecast` | `wind_forecast`, `wind_forecast_lag_1`, `wind_forecast_lag_7` | Onshore plus offshore wind forecast. Offshore exists in DE_LU only | End of D |
| `solar_forecast` | `solar_forecast`, `solar_forecast_lag_1`, `solar_forecast_lag_7` | The day-ahead solar forecast. Empty in SE_1 to SE_4 | End of D |
| `actual_load` | `actual_load_lag_2` | Actual load at the same wall-clock time 2 days before | End of D-2 |
| `weather` | `temperature_2m`, `wind_speed_10m`, `wind_speed_100m`, `shortwave_radiation` | The weather forecast of the hour, from the 00:00 UTC run of D-1 | End of D, and run of D-1 |

- A lag follows the wall clock in market time, as the seasonal naive forecast does. `price_lag_7` equals that forecast (entry 76).
- `shortwave_radiation` is taken one hour later than its timestamp, and the last hour of every day is empty (entry 79).
- Nothing is filled and no row is dropped (entry 77).
- The groups are switched in `features.groups` of the config (entry 74).

### 2. Price lags and inputs, measured on train days

The owner chose the features after seeing these numbers. A lag is the value at the same wall-clock time k days before. R2 is from a least-squares fit with an intercept, fitted and scored on the same rows. "fc" is the load, wind and solar forecast.

```
===== train tables: rows and empty values per column =====
hourly       DE_LU  rows 65519  steps ['0 days 01:00:00']  last 2026-06-22 21:00:00+00:00  empty: price 0, load_forecast 50, wind_onshore_forecast 3, wind_offshore_forecast 0, solar_forecast 3, actual_load 0
hourly       FR     rows 65519  steps ['0 days 01:00:00']  last 2026-06-22 21:00:00+00:00  empty: price 0, load_forecast 0, wind_onshore_forecast 350, solar_forecast 376, actual_load 50
hourly       ES     rows 65519  steps ['0 days 01:00:00']  last 2026-06-22 21:00:00+00:00  empty: price 0, load_forecast 1, wind_onshore_forecast 385, solar_forecast 169, actual_load 39
hourly       SE_1   rows 65519  steps ['0 days 01:00:00']  last 2026-06-22 21:00:00+00:00  empty: price 0, load_forecast 24, wind_onshore_forecast 192, actual_load 0
hourly       SE_2   rows 65519  steps ['0 days 01:00:00']  last 2026-06-22 21:00:00+00:00  empty: price 0, load_forecast 24, wind_onshore_forecast 192, actual_load 0
hourly       SE_3   rows 65519  steps ['0 days 01:00:00']  last 2026-06-22 21:00:00+00:00  empty: price 0, load_forecast 24, wind_onshore_forecast 192, actual_load 0
hourly       SE_4   rows 65519  steps ['0 days 01:00:00']  last 2026-06-22 21:00:00+00:00  empty: price 0, load_forecast 24, wind_onshore_forecast 192, actual_load 0
quarter_hour DE_LU  rows 25440  steps ['0 days 00:15:00']  last 2026-06-22 21:45:00+00:00  empty: price 0, load_forecast 0, wind_onshore_forecast 4, wind_offshore_forecast 0, solar_forecast 4, actual_load 0
quarter_hour FR     rows 25440  steps ['0 days 00:15:00']  last 2026-06-22 21:45:00+00:00  empty: price 0, load_forecast 0, wind_onshore_forecast 100, solar_forecast 100, actual_load 15
quarter_hour ES     rows 25440  steps ['0 days 00:15:00']  last 2026-06-22 21:45:00+00:00  empty: price 0, load_forecast 0, wind_onshore_forecast 1248, solar_forecast 192, actual_load 1
quarter_hour SE_1   rows 25440  steps ['0 days 00:15:00']  last 2026-06-22 21:45:00+00:00  empty: price 0, load_forecast 96, wind_onshore_forecast 384, actual_load 0
quarter_hour SE_2   rows 25440  steps ['0 days 00:15:00']  last 2026-06-22 21:45:00+00:00  empty: price 0, load_forecast 96, wind_onshore_forecast 384, actual_load 0
quarter_hour SE_3   rows 25440  steps ['0 days 00:15:00']  last 2026-06-22 21:45:00+00:00  empty: price 0, load_forecast 96, wind_onshore_forecast 384, actual_load 0
quarter_hour SE_4   rows 25440  steps ['0 days 00:15:00']  last 2026-06-22 21:45:00+00:00  empty: price 0, load_forecast 96, wind_onshore_forecast 384, actual_load 0

===== experiment H, all train days: 2018-12-31 23:00:00+00:00 to 2026-06-22 21:00:00+00:00 UTC, 65519 rows per zone =====

1. correlation of the price with the price at the same wall-clock time k days before
zone       D-1    D-2    D-3    D-4    D-5    D-6    D-7    D-8   D-14   D-21   D-28
DE_LU    0.878  0.802  0.774  0.757  0.757  0.775  0.794  0.759  0.742  0.691  0.660
FR       0.921  0.877  0.858  0.847  0.843  0.855  0.866  0.836  0.807  0.764  0.744
ES       0.914  0.863  0.840  0.819  0.805  0.814  0.823  0.798  0.774  0.764  0.748
SE_1     0.781  0.658  0.599  0.568  0.553  0.551  0.544  0.516  0.423  0.327  0.221
SE_2     0.763  0.637  0.580  0.551  0.546  0.537  0.527  0.500  0.405  0.330  0.234
SE_3     0.782  0.639  0.602  0.590  0.582  0.608  0.641  0.586  0.557  0.446  0.386
SE_4     0.780  0.642  0.598  0.585  0.579  0.596  0.618  0.576  0.537  0.454  0.370

2. R2 of the price on nested sets of day lags (same rows for every set of a zone)
zone              D-1         D-1,2       D-1,2,3       D-1,2,7     D-1,2,3,7        D-1..7  D-1,2,3,7,14     D-1..7,14    rows
DE_LU          0.7702        0.7746        0.7842        0.8032        0.8062        0.8085        0.8114        0.8129   65183
FR             0.8482        0.8538        0.8591        0.8722        0.8734        0.8754        0.8750        0.8765   65183
ES             0.8349        0.8395        0.8453        0.8546        0.8561        0.8575        0.8579        0.8590   65183
SE_1           0.6096        0.6156        0.6226        0.6304        0.6335        0.6376        0.6347        0.6383   65183
SE_2           0.5822        0.5894        0.5974        0.6040        0.6081        0.6139        0.6094        0.6145   65183
SE_3           0.6117        0.6137        0.6311        0.6554        0.6621        0.6662        0.6662        0.6694   65183
SE_4           0.6079        0.6108        0.6249        0.6447        0.6504        0.6551        0.6550        0.6584   65183

3. D-1 summaries: correlation with the price, and R2 when added to D-1,2,3,7
zone     corr mean D-1   corr min D-1   corr max D-1  corr last D-1   R2 base   +mean  +min,max   +last  +all 4
DE_LU            0.839          0.711          0.810          0.849    0.8062  0.8104    0.8113  0.8325  0.8378
FR               0.910          0.852          0.842          0.907    0.8734  0.8792    0.8764  0.8875  0.8879
ES               0.876          0.803          0.842          0.871    0.8561  0.8594    0.8619  0.8683  0.8721
SE_1             0.795          0.756          0.714          0.829    0.6335  0.6594    0.6572  0.7109  0.7126
SE_2             0.782          0.744          0.696          0.816    0.6081  0.6376    0.6356  0.6889  0.6897
SE_3             0.718          0.544          0.676          0.672    0.6621  0.6690    0.6693  0.6916  0.6971
SE_4             0.726          0.547          0.685          0.678    0.6504  0.6596    0.6606  0.6872  0.6893

4. inputs: R2 when added to the price lags D-1,2,3,7 (rows where every input has a value)
   fc = load forecast, total wind forecast and, where the zone has one, solar forecast, at the target time
   fc lags = the same forecasts at D-1 and D-7. load D-2, D-7 = actual load at the same wall-clock time
zone    solar  R2 lags  +load fc  +wind fc     +fc  +fc,fc lags  +fc,load D-2  +fc,load D-2,D-7  corr(load fc, load D-2)    rows
DE_LU     yes   0.8060    0.8102    0.8378  0.8545       0.8951        0.8617            0.8628                    0.579   65030
FR        yes   0.8735    0.8755    0.8823  0.8868       0.9058        0.8976            0.8989                    0.862   63776
ES        yes   0.8573    0.8600    0.8774  0.8836       0.9176        0.8906            0.8914                    0.659   63881
SE_1       no   0.6334    0.6360    0.6589  0.6682       0.6844        0.6687            0.6688                    0.786   64559
SE_2       no   0.6075    0.6107    0.6534  0.6628       0.6898        0.6651            0.6660                    0.769   64559
SE_3       no   0.6584    0.6638    0.6937  0.7057       0.7394        0.7195            0.7222                    0.893   64559
SE_4       no   0.6437    0.6478    0.6810  0.6904       0.7269        0.7050            0.7065                    0.849   64559

===== experiment H, last 364 train days: 2025-06-23 21:00:00+00:00 to 2026-06-22 21:00:00+00:00 UTC, 8737 rows per zone =====

1. correlation of the price with the price at the same wall-clock time k days before
zone       D-1    D-2    D-3    D-4    D-5    D-6    D-7    D-8   D-14   D-21   D-28
DE_LU    0.661  0.502  0.441  0.429  0.450  0.482  0.503  0.476  0.483  0.479  0.401
FR       0.712  0.561  0.494  0.452  0.476  0.478  0.468  0.414  0.401  0.394  0.260
ES       0.829  0.723  0.669  0.640  0.619  0.630  0.646  0.602  0.599  0.510  0.457
SE_1     0.716  0.526  0.489  0.475  0.456  0.436  0.412  0.392  0.390  0.334  0.172
SE_2     0.702  0.513  0.486  0.468  0.449  0.429  0.403  0.388  0.388  0.322  0.166
SE_3     0.674  0.451  0.388  0.380  0.392  0.433  0.470  0.417  0.450  0.358  0.303
SE_4     0.652  0.446  0.375  0.366  0.382  0.427  0.477  0.424  0.447  0.391  0.323

2. R2 of the price on nested sets of day lags (same rows for every set of a zone)
zone              D-1         D-1,2       D-1,2,3       D-1,2,7     D-1,2,3,7        D-1..7  D-1,2,3,7,14     D-1..7,14    rows
DE_LU          0.4356        0.4440        0.4529        0.4838        0.4876        0.5000        0.5083        0.5163    8401
FR             0.5039        0.5106        0.5183        0.5283        0.5329        0.5450        0.5390        0.5499    8401
ES             0.6831        0.6872        0.6932        0.7098        0.7113        0.7134        0.7160        0.7176    8401
SE_1           0.5043        0.5046        0.5265        0.5166        0.5323        0.5384        0.5438        0.5478    8401
SE_2           0.4854        0.4862        0.5111        0.4982        0.5166        0.5227        0.5277        0.5317    8401
SE_3           0.4450        0.4450        0.4584        0.4867        0.4931        0.5000        0.5125        0.5167    8401
SE_4           0.4177        0.4184        0.4269        0.4676        0.4709        0.4783        0.4884        0.4928    8401

3. D-1 summaries: correlation with the price, and R2 when added to D-1,2,3,7
zone     corr mean D-1   corr min D-1   corr max D-1  corr last D-1   R2 base   +mean  +min,max   +last  +all 4
DE_LU            0.309          0.192          0.212          0.293    0.4876  0.4880    0.4905  0.5180  0.5283
FR               0.511          0.328          0.438          0.443    0.5329  0.5361    0.5448  0.5653  0.5671
ES               0.521          0.387          0.463          0.504    0.7113  0.7121    0.7207  0.7242  0.7420
SE_1             0.718          0.706          0.648          0.804    0.5323  0.5539    0.5614  0.6582  0.6766
SE_2             0.709          0.707          0.623          0.799    0.5166  0.5396    0.5544  0.6498  0.6690
SE_3             0.578          0.548          0.488          0.636    0.4931  0.4987    0.5001  0.5580  0.5728
SE_4             0.501          0.433          0.420          0.534    0.4709  0.4743    0.4748  0.5218  0.5356

4. inputs: R2 when added to the price lags D-1,2,3,7 (rows where every input has a value)
   fc = load forecast, total wind forecast and, where the zone has one, solar forecast, at the target time
   fc lags = the same forecasts at D-1 and D-7. load D-2, D-7 = actual load at the same wall-clock time
zone    solar  R2 lags  +load fc  +wind fc     +fc  +fc,fc lags  +fc,load D-2  +fc,load D-2,D-7  corr(load fc, load D-2)    rows
DE_LU     yes   0.4874    0.4999    0.5884  0.7612       0.7965        0.7703            0.7720                    0.616    8398
FR        yes   0.5342    0.5513    0.5946  0.6906       0.7432        0.7226            0.7234                    0.870    8316
ES        yes   0.7000    0.7063    0.7594  0.8475       0.8792        0.8529            0.8550                    0.636    7656
SE_1       no   0.5410    0.5550    0.5990  0.6277       0.6527        0.6292            0.6301                    0.744    8065
SE_2       no   0.5242    0.5508    0.6383  0.6949       0.7343        0.6954            0.6963                    0.641    8065
SE_3       no   0.4971    0.5263    0.5974  0.6521       0.6839        0.6774            0.6774                    0.901    8065
SE_4       no   0.4734    0.4917    0.5572  0.6074       0.6645        0.6291            0.6292                    0.852    8065

===== experiment Q, all train days: 2025-09-30 22:00:00+00:00 to 2026-06-22 21:45:00+00:00 UTC, 25440 rows per zone =====

1. correlation of the price with the price at the same wall-clock time k days before
zone       D-1    D-2    D-3    D-4    D-5    D-6    D-7    D-8   D-14   D-21   D-28
DE_LU    0.644  0.490  0.418  0.405  0.443  0.474  0.480  0.450  0.450  0.460  0.375
FR       0.691  0.551  0.489  0.442  0.468  0.459  0.438  0.382  0.361  0.367  0.227
ES       0.825  0.724  0.672  0.631  0.598  0.595  0.605  0.568  0.566  0.449  0.373
SE_1     0.697  0.498  0.474  0.458  0.434  0.405  0.380  0.353  0.371  0.293  0.091
SE_2     0.685  0.490  0.477  0.457  0.431  0.402  0.373  0.355  0.364  0.284  0.085
SE_3     0.635  0.402  0.346  0.340  0.345  0.376  0.417  0.365  0.415  0.321  0.238
SE_4     0.615  0.401  0.329  0.314  0.337  0.372  0.425  0.380  0.414  0.372  0.293

2. R2 of the price on nested sets of day lags (same rows for every set of a zone)
zone              D-1         D-1,2       D-1,2,3       D-1,2,7     D-1,2,3,7        D-1..7  D-1,2,3,7,14     D-1..7,14    rows
DE_LU          0.4136        0.4296        0.4378        0.4612        0.4654        0.4807        0.4848        0.4956   24096
FR             0.4763        0.4887        0.4975        0.5013        0.5072        0.5198        0.5133        0.5249   24096
ES             0.6874        0.6938        0.6986        0.7086        0.7099        0.7107        0.7148        0.7156   24096
SE_1           0.4731        0.4733        0.5014        0.4844        0.5060        0.5114        0.5229        0.5260   24096
SE_2           0.4553        0.4559        0.4872        0.4666        0.4910        0.4967        0.5062        0.5096   24096
SE_3           0.4191        0.4198        0.4379        0.4524        0.4631        0.4677        0.4843        0.4869   24096
SE_4           0.3883        0.3908        0.4011        0.4303        0.4356        0.4411        0.4537        0.4568   24096

3. D-1 summaries: correlation with the price, and R2 when added to D-1,2,3,7
zone     corr mean D-1   corr min D-1   corr max D-1  corr last D-1   R2 base   +mean  +min,max   +last  +all 4
DE_LU            0.308          0.191          0.198          0.301    0.4654  0.4658    0.4673  0.4956  0.5051
FR               0.513          0.318          0.363          0.459    0.5072  0.5120    0.5108  0.5511  0.5535
ES               0.558          0.427          0.463          0.534    0.7099  0.7112    0.7162  0.7253  0.7433
SE_1             0.694          0.677          0.616          0.794    0.5060  0.5255    0.5415  0.6441  0.6720
SE_2             0.686          0.685          0.590          0.787    0.4910  0.5113    0.5352  0.6325  0.6594
SE_3             0.533          0.521          0.402          0.618    0.4631  0.4703    0.4808  0.5446  0.5640
SE_4             0.460          0.415          0.346          0.505    0.4356  0.4404    0.4437  0.4893  0.5073

4. inputs: R2 when added to the price lags D-1,2,3,7 (rows where every input has a value)
   fc = load forecast, total wind forecast and, where the zone has one, solar forecast, at the target time
   fc lags = the same forecasts at D-1 and D-7. load D-2, D-7 = actual load at the same wall-clock time
zone    solar  R2 lags  +load fc  +wind fc     +fc  +fc,fc lags  +fc,load D-2  +fc,load D-2,D-7  corr(load fc, load D-2)    rows
DE_LU     yes   0.4650    0.4779    0.5673  0.7348       0.7754        0.7488            0.7519                    0.614   24084
FR        yes   0.5090    0.5305    0.5681  0.6688       0.7158        0.6986            0.6992                    0.860   23766
ES        yes   0.6973    0.7024    0.7588  0.8365       0.8704        0.8424            0.8450                    0.661   21119
SE_1       no   0.5136    0.5259    0.6009  0.6212       0.6429        0.6228            0.6245                    0.721   22752
SE_2       no   0.4973    0.5221    0.6594  0.6975       0.7336        0.6981            0.6989                    0.582   22752
SE_3       no   0.4661    0.4993    0.5859  0.6353       0.6652        0.6654            0.6656                    0.875   22752
SE_4       no   0.4360    0.4579    0.5229  0.5752       0.6291        0.5959            0.5959                    0.819   22752
```

What it shows:

- D-1 is the strongest lag in every zone. D-7 rises again above D-4 to D-6 in DE_LU, FR, ES, SE_3 and SE_4. In SE_1 and SE_2 it does not.
- The lags D-1, 2, 3 and 7 reach an R2 within 0.001 to 0.006 of all seven lags on the hourly table, and within 0.002 to 0.012 on its last 364 days.
- The last price of D-1 adds the most of the four statistics: 0.012 to 0.081 on the hourly table. It matters most in SE_1 and SE_2, the zones with the weakest daily season.
- The forecasts at the target time add more on the recent days than on all train days. The forecasts of D-1 and D-7 add 0.016 to 0.041 on top.

Actual load at D-2 on top of the forecasts and their lags:

```
H, all train days: R2 on price lags D-1,2,3,7 plus
zone     fc + fc lags  + load D-2  + load D-2, D-7    rows
DE_LU          0.8951      0.8953           0.8957   65198
FR             0.9058      0.9065           0.9065   63944
ES             0.9175      0.9176           0.9176   64049
SE_1           0.6844      0.6845           0.6845   64727
SE_2           0.6898      0.6902           0.6902   64727
SE_3           0.7393      0.7402           0.7402   64727
SE_4           0.7268      0.7290           0.7290   64727

H, last 364 train days: R2 on price lags D-1,2,3,7 plus
zone     fc + fc lags  + load D-2  + load D-2, D-7    rows
DE_LU          0.7930      0.7958           0.7960    8566
FR             0.7441      0.7473           0.7476    8484
ES             0.8804      0.8805           0.8805    7824
SE_1           0.6556      0.6565           0.6582    8233
SE_2           0.7351      0.7354           0.7363    8233
SE_3           0.6862      0.6967           0.6971    8233
SE_4           0.6679      0.6748           0.6748    8233

Q, all train days: R2 on price lags D-1,2,3,7 plus
zone     fc + fc lags  + load D-2  + load D-2, D-7    rows
DE_LU          0.7722      0.7753           0.7757   24756
FR             0.7164      0.7197           0.7199   24438
ES             0.8713      0.8713           0.8713   21791
SE_1           0.6477      0.6486           0.6507   23424
SE_2           0.7369      0.7374           0.7384   23424
SE_3           0.6569      0.6714           0.6721   23424
SE_4           0.6272      0.6364           0.6364   23424
```

- Actual load adds 0.0001 to 0.002 on all train days of the hourly table and about 0.01 at most on its last 364 days, in SE_3. It is built as a group of its own, so the validation days can decide (entry 73).

### 3. Frame shape and weather, measured on train days

A least-squares stand-in for the model, since no LightGBM model is trained yet. It is fitted on the first 80% of the train days and scored on the last 20% of the train days. "per time" is one fit per time of day: 24 on the hourly table and 96 on the 15-minute table. "profile" is the 24 hourly prices of D-1.

```
===== experiment H: frame shape =====
MAE on the last 20% of the train days, EUR/MWh
       fit days  score days  fit rows per time  naive  pooled  pooled + profile  per time  per time + profile
DE_LU      2167         542               2166  34.05   14.58             14.98     14.17               14.50
FR         2137         535               2123  33.55   15.21             16.07     15.93               16.77
ES         2132         533               2131  29.13   12.74             13.30     12.88               13.46
SE_1       2151         538               2151  25.65   13.44             13.65     12.94               13.26
SE_2       2151         538               2151  26.18   12.92             13.16     12.28               12.55
SE_3       2151         538               2151  34.56   19.17             18.75     19.16               18.98
SE_4       2151         538               2151  38.84   20.98             21.04     20.24               20.23
the same as relative MAE against the D-7 price
       pooled  pooled + profile  per time  per time + profile
DE_LU  0.4284            0.4400    0.4163              0.4258
FR     0.4534            0.4788    0.4748              0.4999
ES     0.4375            0.4565    0.4422              0.4623
SE_1   0.5240            0.5323    0.5045              0.5169
SE_2   0.4934            0.5026    0.4690              0.4796
SE_3   0.5548            0.5427    0.5543              0.5491
SE_4   0.5402            0.5415    0.5211              0.5207
mean   0.4902            0.4992    0.4832              0.4935

===== experiment Q: frame shape =====
MAE on the last 20% of the train days, EUR/MWh
       fit days  score days  fit rows per time  naive  pooled  pooled + profile  per time  per time + profile
DE_LU       205          52                204  36.35   16.44             20.20     41.51               51.57
FR          203          51                202  42.82   18.87             19.98   1651.34             1455.08
ES          181          46                181  19.73   13.60             14.31     14.27               16.55
SE_1        194          49                194  44.21   20.59             19.19     20.80               21.05
SE_2        194          49                194  44.27   20.01             19.48     18.77               20.30
SE_3        194          49                194  37.00   19.92             19.20     20.78               20.80
SE_4        194          49                194  39.49   23.42             25.52     22.57               24.83
the same as relative MAE against the D-7 price
       pooled  pooled + profile  per time  per time + profile
DE_LU  0.4523            0.5558    1.1421              1.4190
FR     0.4406            0.4667   38.5641             33.9810
ES     0.6897            0.7257    0.7233              0.8388
SE_1   0.4657            0.4340    0.4706              0.4760
SE_2   0.4519            0.4401    0.4240              0.4586
SE_3   0.5384            0.5188    0.5615              0.5622
SE_4   0.5930            0.6462    0.5717              0.6287
mean   0.5188            0.5410    6.0653              5.4806


########## weather, train days from 2024-03-15 ##########

===== experiment H with weather: temperature, wind at 10 m and 100 m, radiation =====
MAE on the last 20% of the train days, EUR/MWh
       fit days  score days  fit rows per time  naive  pooled  pooled + weather  per time  per time + weather
DE_LU       661         166                660  35.85   14.98             15.16     14.24               14.35
FR          659         165                658  39.30   17.36             17.04     17.25               16.92
ES          624         156                623  26.07   13.49             13.48     13.05               12.96
SE_1        648         162                648  37.50   18.23             18.17     17.64               17.62
SE_2        648         162                648  37.54   15.93             16.09     15.57               15.65
SE_3        648         162                648  34.68   16.42             16.06     15.48               15.70
SE_4        648         162                648  37.99   20.49             19.84     18.58               18.40
the same as relative MAE against the D-7 price
       pooled  pooled + weather  per time  per time + weather
DE_LU  0.4179            0.4230    0.3973              0.4004
FR     0.4417            0.4337    0.4391              0.4305
ES     0.5174            0.5170    0.5004              0.4971
SE_1   0.4861            0.4844    0.4703              0.4698
SE_2   0.4243            0.4287    0.4146              0.4168
SE_3   0.4735            0.4630    0.4463              0.4527
SE_4   0.5395            0.5222    0.4891              0.4844
mean   0.4715            0.4674    0.4510              0.4503

shortwave_radiation stamped 00:00 market time, the mean of the hour 23:00 to 24:00, W/m2
       hours  above 0  mean  max  mean of all hours
DE_LU  830.0      0.0  0.00  0.0             147.08
FR     830.0      0.0  0.00  0.0             152.69
ES     830.0      0.0  0.00  0.0             206.83
SE_1   830.0     28.0  0.03  1.0             115.41
SE_2   830.0      0.0  0.00  0.0             124.08
SE_3   830.0      0.0  0.00  0.0             130.63
SE_4   830.0      0.0  0.00  0.0             141.91
```

What it shows:

- On the hourly table a fit per hour is ahead by 0.007 in the mean. It is better in five zones and worse in FR and ES.
- On the 15-minute table a fit per time of day breaks: each fit has about 200 rows.
- The hourly prices of D-1 make the mean worse in both experiments, so they are not features.
- The four weather values move the mean by 0.004 for one fit and by 0.001 for a fit per hour. They help in FR and SE_4 and hurt slightly in DE_LU and SE_2. In SE_3 they help for one fit, from 0.4735 to 0.4630, and not for a fit per hour, where SE_3 gets worse from 0.4463 to 0.4527.
- The radiation of the hour 23:00 to 24:00 is 0 on every train day in six zones, and at most 1.0 W/m2 in SE_1.
- Limit: a least-squares fit is not LightGBM. A tree model on one frame can learn a different behaviour per hour. These relative MAE values are on train days and are not results of a model of this project.

### 4. The built frames

`python -m epf.features.build` on 26 Nov 2026. The command took 230 seconds.

| Experiment | Rows per zone | Delivery days | Features | Seconds per zone |
|---|---|---|---|---|
| H | 69120 | 2880 | 28 | 24.8 to 31.2 |
| Q | 39844 | 415 | 29 | 3.6 to 4.5 |

Empty cells per feature and zone, experiment H, counted on the saved frames. SE_1 to SE_4 were added after Milestone 1, which approved DE_LU, FR and ES only.

| Feature | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 |
|---|---|---|---|---|---|---|---|
| `price_lag_1` | 24 | 24 | 24 | 24 | 24 | 24 | 24 |
| `price_lag_2` | 48 | 48 | 48 | 48 | 48 | 48 | 48 |
| `price_lag_3` | 72 | 72 | 72 | 72 | 72 | 72 | 72 |
| `price_lag_4` | 96 | 96 | 96 | 96 | 96 | 96 | 96 |
| `price_lag_5` | 120 | 120 | 120 | 120 | 120 | 120 | 120 |
| `price_lag_6` | 144 | 144 | 144 | 144 | 144 | 144 | 144 |
| `price_lag_7` | 168 | 168 | 168 | 168 | 168 | 168 | 168 |
| `price_d1_mean` | 24 | 24 | 24 | 24 | 24 | 24 | 24 |
| `price_d1_min` | 24 | 24 | 24 | 24 | 24 | 24 | 24 |
| `price_d1_max` | 24 | 24 | 24 | 24 | 24 | 24 | 24 |
| `price_d1_last` | 24 | 24 | 24 | 24 | 24 | 24 | 24 |
| `hour` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `weekday` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `holiday` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `load_forecast` | 50 | 0 | 1 | 24 | 24 | 24 | 24 |
| `load_forecast_lag_1` | 74 | 24 | 24 | 48 | 48 | 48 | 48 |
| `load_forecast_lag_7` | 218 | 168 | 168 | 192 | 192 | 192 | 192 |
| `wind_forecast` | 3 | 351 | 553 | 216 | 216 | 216 | 216 |
| `wind_forecast_lag_1` | 27 | 375 | 576 | 240 | 240 | 240 | 240 |
| `wind_forecast_lag_7` | 171 | 519 | 720 | 384 | 384 | 384 | 384 |
| `solar_forecast` | 3 | 377 | 337 | 69120 | 69120 | 69120 | 69120 |
| `solar_forecast_lag_1` | 27 | 401 | 360 | 69120 | 69120 | 69120 | 69120 |
| `solar_forecast_lag_7` | 171 | 542 | 504 | 69120 | 69120 | 69120 | 69120 |
| `actual_load_lag_2` | 48 | 96 | 87 | 48 | 48 | 48 | 48 |
| `temperature_2m` | 45624 | 45624 | 45624 | 45624 | 45624 | 45624 | 45624 |
| `wind_speed_10m` | 45624 | 45624 | 45624 | 45624 | 45624 | 45624 | 45624 |
| `wind_speed_100m` | 45600 | 45600 | 45600 | 45600 | 45600 | 45600 | 45600 |
| `shortwave_radiation` | 46580 | 46580 | 46580 | 46580 | 46580 | 46580 | 46580 |

Empty cells per feature and zone, experiment Q:

| Feature | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 |
|---|---|---|---|---|---|---|---|
| `price_lag_1` | 96 | 96 | 96 | 96 | 96 | 96 | 96 |
| `price_lag_2` | 192 | 192 | 192 | 192 | 192 | 192 | 192 |
| `price_lag_3` | 288 | 288 | 288 | 288 | 288 | 288 | 288 |
| `price_lag_4` | 384 | 384 | 384 | 384 | 384 | 384 | 384 |
| `price_lag_5` | 480 | 480 | 480 | 480 | 480 | 480 | 480 |
| `price_lag_6` | 576 | 576 | 576 | 576 | 576 | 576 | 576 |
| `price_lag_7` | 672 | 672 | 672 | 672 | 672 | 672 | 672 |
| `price_d1_mean` | 96 | 96 | 96 | 96 | 96 | 96 | 96 |
| `price_d1_min` | 96 | 96 | 96 | 96 | 96 | 96 | 96 |
| `price_d1_max` | 96 | 96 | 96 | 96 | 96 | 96 | 96 |
| `price_d1_last` | 96 | 96 | 96 | 96 | 96 | 96 | 96 |
| `hour` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `quarter_hour` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `weekday` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `holiday` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `load_forecast` | 0 | 0 | 0 | 96 | 96 | 96 | 96 |
| `load_forecast_lag_1` | 96 | 96 | 96 | 192 | 192 | 192 | 192 |
| `load_forecast_lag_7` | 672 | 672 | 672 | 768 | 768 | 768 | 768 |
| `wind_forecast` | 4 | 104 | 1920 | 480 | 480 | 480 | 480 |
| `wind_forecast_lag_1` | 100 | 200 | 2016 | 576 | 576 | 576 | 576 |
| `wind_forecast_lag_7` | 676 | 776 | 2592 | 1152 | 1152 | 1152 | 1152 |
| `solar_forecast` | 4 | 104 | 864 | 39844 | 39844 | 39844 | 39844 |
| `solar_forecast_lag_1` | 100 | 200 | 960 | 39844 | 39844 | 39844 | 39844 |
| `solar_forecast_lag_7` | 676 | 776 | 1536 | 39844 | 39844 | 39844 | 39844 |
| `actual_load_lag_2` | 192 | 207 | 193 | 192 | 192 | 192 | 192 |
| `temperature_2m` | 96 | 96 | 96 | 96 | 96 | 96 | 96 |
| `wind_speed_10m` | 96 | 96 | 96 | 96 | 96 | 96 | 96 |
| `wind_speed_100m` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `shortwave_radiation` | 1660 | 1660 | 1660 | 1660 | 1660 | 1660 | 1660 |

Where the empty cells come from:

- A price lag of k days is empty on the first k days of a table: 24 hours or 96 quarter-hours per day.
- A forecast feature is empty where the processed table has a gap (DATA_NOTES, "Gaps that stay empty"), and its lags are empty one day and seven days later.
- The solar features of SE_1 to SE_4 are empty in every row.
- On the hourly frame the weather features are empty on the 45600 hours before 2024-03-15. `temperature_2m` and `wind_speed_10m` are also empty on the 24 hours of 2026-06-24. `shortwave_radiation` is also empty in the last hour of each of the 980 days with weather.
- The frames cover the validation and the test days too. Only counts were read there.

### 5. Checks

- Tests: 628 pass. 130 of them are new: 17 for the weather cut, 9 for the weather in the backtest, 97 for the builder and 7 for the command.
- Every cell of the 14 saved frames was compared with a plain pandas computation on the whole table, which does not call the builder and does not go through `day_inputs`: 21635852 cells, 0 different, 0 empty in one of the two only. The largest difference is 1.1e-13.
- Each frame stands on exactly the time steps of its table, has no repeated timestamp and no infinite value, and ends with the last time step of 2026-11-19.
- The empty cells of the features at the target time equal what `config/approved_gaps.yaml` gives: 98 comparisons of zone, experiment and feature, 0 not equal.
- Value ranges on train days: 12 range rules on 14 frames, none broken. Hours are 0 to 23, quarter-hours 0 to 3, weekdays 0 to 6, and no load, wind, solar, wind speed or radiation value is below zero. Every price lag lies inside the price range of the train days.
- One thing stands out on train days: the actual load of SE_1 reaches 4428 MW where its load forecast never exceeds 2204, and that of SE_2 reaches 8477 against 3608. The values stay as they are.

Each cut was moved on purpose once, the tests were run, and the code was put back. The table was counted again on 2026-11-26, after the test for a weather run one hour after the run hour was added. This time each change was made in memory, no file was changed, and the whole suite of 628 tests was run. Every failed test is in one of the five test files whose tests call `day_inputs`, which hold 228 tests: `tests/test_backtest.py`, `tests/test_cutoff.py`, `tests/test_features.py`, `tests/test_features_build.py` and `tests/test_stats.py`. "Feature tests" are the failed tests of `tests/test_features.py` and `tests/test_features_build.py`.

| Change | Failed tests | Of them feature tests |
|---|---|---|
| Price cut: end of D-1 to end of D | 55 | 31 |
| Day-ahead cut: end of D to end of D+1 | 18 | 2 |
| Actual load cut: end of D-2 to end of D-1 | 19 | 3 |
| Weather run cut: run of D-1 to run of D | 5 | 1 |
| Weather time cut: end of D to end of D+1 | 1 | 0 |
| Builder: every lag one day too short | 46 | 46 |
| Builder: radiation not moved by one hour | 3 | 3 |
| Builder: an empty wind column skipped in the sum | 2 | 2 |
| Builder: a zone name in the code | 1 | 1 |

- The weather time cut fails one test only. In a table like the real one the hours of D+1 come from the run of D, so the run cut removes them as well.

### 6. Limits

- No model has been trained. The evidence is linear and partly fitted and scored on the same rows.
- The features were not chosen on validation days. Which groups LightGBM uses is decided there.
- One feature list serves all seven zones. The weekly lag is weak in SE_1 and SE_2, and the Swedish zones have no solar feature.
- The French wind feature is onshore only, because the offshore forecast was dropped by the coverage gate (entry 32).
- 7 of the 90 ES test days, 6 to 12 November 2026, have no wind and no solar forecast, so those features are empty there.
- Weather has 830 train days, one point per zone, and a publication time taken from the Open-Meteo docs.
- The build takes about 28 seconds per zone on the hourly table. A model that builds its training rows at every weekly fit pays this each time.

### 7. How to run it again

```
.venv\Scripts\python -m epf.data.build_dataset
.venv\Scripts\python -m epf.features.build
```

- The second command prints the rows and the empty cells per feature and zone and writes `data/features/{experiment}/{ZONE}.parquet`, which git ignores.
- The evidence of sections 2 and 3, the cell comparison and the moved cuts were made with scripts outside the repo. Their printed output is in this file.
