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
