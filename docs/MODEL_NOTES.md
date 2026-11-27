# Model notes

Measured results of the models: what was run, on which days, with which settings, what came out and what it cost. The reasons for each choice are in [DECISIONS.md](DECISIONS.md). This file holds the numbers.

Every number here comes from `reports/results/backtest_core.csv` or from the printed output of a command named beside it. Blocks in a fixed-width font are printed output, copied as it was.

SE_1 and SE_2 are near-duplicates (DECISIONS entry 48), so seven zones are not seven independent results. MAE and RMSE are in EUR/MWh. Zones differ several-fold in price level, so zones are compared on relative MAE only.

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

60 validation days, 1440 hours per zone, runs of 25 Nov 2026. Every run passed every check. The rows are sorted by the mean.

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

`mstl_182` with the same config entry, where the seasons are 96 and 672 quarter-hours. No other setting ran on experiment Q (entry 66). Every check passed.

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

Run once, on 25 Nov 2026 from 19:04:39 to 23:48:15 local time, from commit `31bfb35`, after the frozen setting was committed and the owner said yes (entry 67). 90 test days. Every check passed in all 14 runs. No other candidate has seen the test days.

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

Built on 26 Nov 2026 (DECISIONS entries 69 to 80). Everything in this section was measured and written before a LightGBM model was trained, and its text speaks of that moment. The trained models are in the section "LightGBM" below. This section holds what was measured to choose the features, and the checks of the built frames. Every measurement that chose a feature reads train delivery days only.

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
- The four weather values move the mean by 0.004 for one fit and by 0.001 for a fit per hour. They help in four zones both for one fit and for a fit per hour: in FR from 0.4417 to 0.4337 and from 0.4391 to 0.4305, in ES from 0.5174 to 0.5170 and from 0.5004 to 0.4971, in SE_1 from 0.4861 to 0.4844 and from 0.4703 to 0.4698, and in SE_4 from 0.5395 to 0.5222 and from 0.4891 to 0.4844. They hurt slightly in DE_LU and SE_2. In SE_3 they help for one fit, from 0.4735 to 0.4630, and not for a fit per hour, where SE_3 gets worse from 0.4463 to 0.4527.
- The radiation of the hour 23:00 to 24:00 is 0 on every train day in six zones, and at most 1.0 W/m2 in SE_1.
- Limit: a least-squares fit is not LightGBM. A tree model on one frame can learn a different behaviour per hour. These relative MAE values are on train days and are not results of a model of this project.

### 4. The built frames

`python -m epf.features.build` on 26 Nov 2026. The command took 230 seconds.

| Experiment | Rows per zone | Delivery days | Features | Seconds per zone |
|---|---|---|---|---|
| H | 69120 | 2880 | 28 | 24.8 to 31.2 |
| Q | 39844 | 415 | 29 | 3.6 to 4.5 |

Empty cells per feature and zone, experiment H, counted on the saved frames.

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

- Tests: 628 passed on 26 Nov 2026, before the LightGBM model was added. 130 of them were new with the feature builder: 17 for the weather cut, 9 for the weather in the backtest, 97 for the builder and 7 for the command.
- Every cell of the 14 saved frames was compared with a plain pandas computation on the whole table, which does not call the builder and does not go through `day_inputs`: 21635852 cells, 0 different, 0 empty in one of the two only. The largest difference is 1.1e-13.
- Each frame stands on exactly the time steps of its table, has no repeated timestamp and no infinite value, and ends with the last time step of 2026-11-19.
- The empty cells of the features at the target time equal what `config/approved_gaps.yaml` gives: 98 comparisons of zone, experiment and feature, 0 not equal.
- Value ranges on train days: 12 range rules on 14 frames, none broken. Hours are 0 to 23, quarter-hours 0 to 3, weekdays 0 to 6, and no load, wind, solar, wind speed or radiation value is below zero. Every price lag lies inside the price range of the train days.
- One thing stands out on train days: the actual load of SE_1 reaches 4428 MW where its load forecast never exceeds 2204, and that of SE_2 reaches 8477 against 3608. The values stay as they are.

Each cut was moved on purpose once, the tests were run, and the code was put back. The table was counted again on 2026-11-26, after the test for a weather run one hour after the run hour was added. This time each change was made in memory, no file was changed, and the whole suite of 628 tests was run. Every failed test is in one of the five test files that have a test that calls `day_inputs`: `tests/test_backtest.py`, `tests/test_cutoff.py`, `tests/test_features.py`, `tests/test_features_build.py` and `tests/test_stats.py`. Together these five files held 228 of the 628 tests. "Feature tests" are the failed tests of `tests/test_features.py` and `tests/test_features_build.py`. The changes behind the last two rows were chosen for this count: `skipna=True` instead of `skipna=False` in the sum of the forecast columns, and one comment line with a zone key added to the text read from `src/epf/features/builder.py`.

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

## LightGBM

Trained, compared, frozen and scored on 26 Nov 2026 (DECISIONS entries 82 to 91). The model is `src/epf/models/lgbm.py`. It reads the features of the section before this one and runs through the same backtest as the naive forecast and the statistical models. The results rows are in `reports/results/backtest_core.csv` (252 rows now), the losses per delivery day in `daily_core.csv` (16380 rows) and the quantile scores in `quantile_core.csv` (14 rows).

Two limits of the Swedish data hold for every table of this section. SE_4 has no usable solar forecast, and the three solar features are empty in SE_1 to SE_4. SE_1 and SE_2 are near-duplicates (DECISIONS entry 48), so the seven zones are not seven independent results.

### In short

- The LightGBM model is `lgbm_load_826_slow`: 400 trees with a learning rate of 0.025, grown on the squared error. It uses the price lags, the calendar, the load, wind and solar forecast and the actual load of D-2. That is 24 features on the hourly frame and 25 on the 15-minute frame. It uses no weather.
- On experiment H each weekly fit trains on a moving window: the 819 delivery days before the delivery day, which is `history_days: 826` minus the 7 days that the lags read. On experiment Q the 15-minute table is shorter than the window, and a fit trains on all of it: 258 to 314 days on the validation days (section 10).
- It was chosen from eleven settings. All eleven ran on the 60 validation days of experiment H for all seven zones. The rule was fixed before the runs: the lowest mean relative MAE over the seven zones wins (DECISIONS entries 87 and 88).
- The four best settings are a tie inside the noise of 60 days: 0.5316, 0.5359, 0.5379 and 0.5409. `lgbm_load_826_slow` won by the rule, not by a clear margin.
- Mean relative MAE over the seven zones: 0.5316 on validation H, 0.5782 on validation Q, 0.4716 on test H and 0.4792 on test Q. `mstl_182` has 0.6887, 0.6831, 0.5666 and 0.5691 on the same days.
- The load, wind and solar forecasts are what helps: they lower the mean from 0.6569 to 0.5539 against the price and the calendar alone. The actual load adds nothing. Weather is not settled.
- Quantile forecasts at five levels were added for the validation days. Their intervals are too narrow in every zone: the 90% interval holds 75% of the prices on experiment H and 73% on experiment Q. Nothing was recalibrated.
- Time: the eleven validation runs took 8164 seconds, which is 2 hours 16 minutes. The run on experiment Q took 220 seconds, the one test run 1179 seconds and the quantile run 1109 seconds.

### 1. How a fit builds its rows, and what the model sets

**The library.** `lightgbm` 4.7.0, pinned in `requirements.txt`. The model calls the native API, `lightgbm.train` on a `lightgbm.Dataset`. scikit-learn is not installed (DECISIONS entry 84).

**What a fit receives.** The backtest hands the model the inputs of delivery day D and nothing else. `day_inputs` of `src/epf/evaluation/cutoff.py` has cut them: prices through the end of D-1, the day-ahead forecasts through the end of D, the actual load through the end of D-2, and weather from runs that started at or before 00:00 UTC on D-1. The holiday dates of the country of the zone come with the inputs, so the model does not know its zone (entry 82). The model reads no file.

**The training rows** (entry 85).

- `known_table` sets the three table parts of the inputs side by side again. The result is one table that runs to the end of D. Its price is empty from 00:00 on D, and its actual load is empty from 00:00 on D-1.
- `training_days` lists the delivery days from the first day with a price plus 7 days, to D-1. The first 7 days are skipped because the longest lag reads them.
- `build_features` builds every training day T from that table. It cuts the table again with `day_inputs`, as if T were forecast on its own day. So a training row of T holds the prices through T-1, the forecasts through T and the actual load through T-2.
- There is one training row per market time unit of every training day. Its target is the price of that market time unit.
- A row without a price is dropped, because LightGBM would store its target as 0. An empty feature stays empty, and LightGBM handles it as a missing value. Nothing is filled and nothing is scaled.

**The window.** An entry with `history_days` receives that many days before D, as a moving window. The first 7 of them only feed the lags. So on the hourly table `history_days: 826` trains on 819 delivery days at every fit, and `history_days: 364` on 357. The 15-minute table is shorter than 826 days (section 10). An entry without `history_days` receives every day of its table. On experiment H it trains on 2723 delivery days at the first fit of the validation days and on 2779 at the last. A fit also trains on validation days that have already passed, up to the day before its own delivery day. No scored day is in the fit that forecasts it.

**Fit and forecast.** As for every model, a fit is made on the first scored day and then every 7th delivery day. That is 9 fits per zone on the validation days and 13 on the test days. Between two fits the trees stay as they are. The forecast of a day applies them to the features of that day, built from its own inputs.

**What the model sets itself** (entry 86).

- The objective of the entry: `regression` for the squared error or `regression_l1` for the absolute error. No other name is accepted.
- The number of trees of the entry, handed over as `num_boost_round`. It is fixed. There is no early stopping and no validation set inside a fit.
- `seed`: 42, the seed of the project.
- `deterministic: True` and `force_col_wise: True`, which the LightGBM docs name for the same result from the same rows and parameters.
- `verbosity: -1`, so a fit prints nothing.
- No `num_threads`. LightGBM uses its default number of threads.

**The ten allowed keys.** Under `params` an entry may set `learning_rate`, `num_leaves`, `max_depth`, `min_data_in_leaf`, `feature_fraction`, `bagging_fraction`, `bagging_freq`, `lambda_l1`, `lambda_l2` and `max_bin`. Every other key is refused before a fit: an alias of one of the ten, a round count, and a key that the model sets itself. An entry must hold `family`, `groups`, `objective`, `trees` and `params`, and may hold `history_days`. An unknown key of the entry is refused too. A value under `params` must be a number. An empty value, a list, a text, or true and false are refused when the model is built (added on 27 Nov 2026 after the final review).

**Calendar features as numbers.** `hour`, `weekday`, `holiday` and `quarter_hour` go in as numbers, not as categories.

**Two guards.** Before every forecast the model compares the feature names with those of the fit, in name and in order. At a fit, a refusal by LightGBM, for example for `num_leaves: 1`, becomes an error that names the config entry.

### 2. What the code relies on in `lightgbm` 4.7.0

Checked on 26 Nov 2026 before the model was written, against the installed package and the documentation of version 4.7.0. The runs used made-up data.

| Fact | Evidence | What the code does with it |
|---|---|---|
| The native API works without scikit-learn | `lightgbm.train` returned a `Booster`. `LGBMRegressor()` raised "scikit-learn is required" | Only `lightgbm.train`, `lightgbm.Dataset` and `Booster.predict` are called |
| `Booster.predict` takes the columns by their position. Names and order are not checked by default | Two swapped columns gave other numbers with no message. Renamed columns in the same order gave the same numbers | The model compares the names itself before every forecast |
| A missing label is stored as 0 | A fit with 3 empty labels equalled a fit with those labels set to 0.0, with no warning | Rows without a price are dropped before the fit |
| An unknown parameter key is ignored | `num_leafs: 4` left 31 leaves. With `verbosity: -1` no line was printed | Only the ten allowed keys pass |
| A round count among the parameters beats the number of trees | `num_boost_round=7` with `num_iterations: 3` gave 3 trees and no warning | Round counts and their aliases are refused |
| The level of a quantile fit is `alpha` | Default 0.9, no alias, one level per fit | The quantile model sets `alpha` for each level (section 12) |
| A feature that is empty in every row gets no split | The forecasts equalled those of a model trained without the column | The empty solar features of SE_1 to SE_4 need no special case |
| `verbosity` carries over to the next fit of the process | A fit without the key printed nothing after a quiet fit | The key is set in every fit |

Determinism, as measured: 13 settings were each fitted three times in one process, on 20000 rows with 28 columns. Every setting gave the same forecasts to the last bit on all three fits. The number of threads, `deterministic` and the histogram method did not change one bit. The seed changed a result only with `feature_fraction` or bagging switched on.

Determinism, as the docs state it: `deterministic` "should ensure the stable results when using the same data and the same parameters", and the docs ask for `force_col_wise` or `force_row_wise` with it. They also say that results "are expected to be different" between LightGBM versions, compilers and systems. So the same numbers are promised for one machine and one version only.

### 3. Timing of one zone before the plan

One whole zone was timed before the runs were planned, as the notes on `mstl_182` advise. The first zone of the config, validation days of experiment H, all seven feature groups, 100 trees, default parameters, all history. In memory, nothing written:

```
experiment H, first zone of the config, history_days None
entry: groups 7, trees 100, default parameters
checks all pass: True
fits: 9, seconds per fit: 26.9, 28.6, 32.4, 26.2, 25.5, 24.5, 24.3, 24.7, 25.8
  of which building the training rows: 26.6, 28.3, 32.1, 25.9, 25.2, 24.3, 24.0, 24.5, 25.4
  training rows and features at the first and the last fit: (65351, 28), (66695, 28)
forecast days: 60, seconds per forecast day: mean 0.030, max 0.042
sum of the fits 239.0 s, sum of the forecasts 1.8 s
day loop of the model (wall_seconds of the row): 241.2 s
backtest_zone in total, with reading and the naive reference: 242.0 s
peak memory: 364 MB
```

What it shows:

- A fit takes 24.3 to 32.4 seconds. Building the training rows takes 24.0 to 32.1 seconds of it. Growing the 100 trees takes the rest, about 0.3 seconds.
- A forecast takes 0.030 seconds per day.
- So `wall_seconds` of a LightGBM row is almost all feature building. It includes the rebuild of the training rows at every weekly fit: 9 times per zone on the validation days.
- This is why `wall_seconds` does not rank the settings by the cost of their trees. It follows the number of training days.
- The estimate from this zone was 241.2 seconds times seven zones, about 28 minutes for a setting on all history.

### 4. The eleven settings

Step 1 has eight settings with the defaults of LightGBM: a learning rate of 0.1 and 31 leaves. They differ in the feature groups and in the history. Step 2 has three settings. Each is the best setting of step 1, `lgbm_load_826`, with one change.

| Name | Step | Feature groups | Features on the hourly frame | History days | Training days per fit | Objective | Trees | Parameters |
|---|---|---|---|---|---|---|---|---|
| `lgbm_price` | 1 | price, calendar | 14 | all | 2723 to 2779 | `regression` | 100 | defaults |
| `lgbm_fcst` | 1 | price, calendar, load, wind and solar forecast | 23 | all | 2723 to 2779 | `regression` | 100 | defaults |
| `lgbm_load` | 1 | as `lgbm_fcst`, and actual load | 24 | all | 2723 to 2779 | `regression` | 100 | defaults |
| `lgbm_all` | 1 | as `lgbm_load`, and weather | 28 | all | 2723 to 2779 | `regression` | 100 | defaults |
| `lgbm_load_826` | 1 | as `lgbm_load` | 24 | 826 | 819 | `regression` | 100 | defaults |
| `lgbm_all_826` | 1 | as `lgbm_all` | 28 | 826 | 819 | `regression` | 100 | defaults |
| `lgbm_load_364` | 1 | as `lgbm_load` | 24 | 364 | 357 | `regression` | 100 | defaults |
| `lgbm_all_364` | 1 | as `lgbm_all` | 28 | 364 | 357 | `regression` | 100 | defaults |
| `lgbm_load_826_l1` | 2 | as `lgbm_load` | 24 | 826 | 819 | `regression_l1` | 100 | defaults |
| `lgbm_load_826_slow` | 2 | as `lgbm_load` | 24 | 826 | 819 | `regression` | 400 | `learning_rate: 0.025` |
| `lgbm_load_826_leaves15` | 2 | as `lgbm_load` | 24 | 826 | 819 | `regression` | 100 | `num_leaves: 15` |

- Each setting is an entry under `models` in `config/config.yaml`, and that entry is copied into every results row. The `features` section of the config is not copied (section 14).
- The weather table starts on 2024-03-15. A window of 826 days before the first validation day starts on 2024-03-19, so it lies inside the weather period. 826 days are 118 weeks.
- In `lgbm_load_826_slow` a quarter of the learning rate with four times the trees counts as one change.
- The owner approved the settings and the rule on 26 Nov 2026, before any full run (entry 87).

### 5. The rule

Fixed before the runs, in the words of the rule for the statistical baseline: the winner is the setting with the lowest mean relative MAE over the seven zones on the validation days of experiment H, among the settings whose run passes every check. Run time is reported and does not decide. All eleven settings compete. A mean clearly below 0.42 would start a search for leakage before anything else.

### 6. Validation results, experiment H

60 validation days, 1440 hours per zone, runs of 26 Nov 2026 on the machine of the statistical baseline. Python 3.12.10, `lightgbm` 4.7.0, seed 42. Every run passed every check.

Relative MAE, as `python -m epf.evaluation.tables --experiment H --split validation` prints it. The rows are sorted by the mean. The command prints every model of the results file. The other 14 statistical settings are left out here. They are in section 7 of the statistical baseline.

| Model | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|
| lgbm_load_826_slow | 0.4909 | 0.5548 | 0.5707 | 0.6235 | 0.5122 | 0.4890 | 0.4797 | 0.5316 |
| lgbm_load_826 | 0.5073 | 0.5625 | 0.5674 | 0.6271 | 0.5160 | 0.4881 | 0.4832 | 0.5359 |
| lgbm_load_826_l1 | 0.5125 | 0.5498 | 0.5855 | 0.5816 | 0.5477 | 0.5018 | 0.4861 | 0.5379 |
| lgbm_all | 0.5725 | 0.5940 | 0.5813 | 0.5557 | 0.4891 | 0.5053 | 0.4884 | 0.5409 |
| lgbm_all_826 | 0.5229 | 0.5697 | 0.5803 | 0.6417 | 0.5084 | 0.4851 | 0.4927 | 0.5430 |
| lgbm_fcst | 0.5741 | 0.6002 | 0.5936 | 0.5776 | 0.5022 | 0.5236 | 0.5062 | 0.5539 |
| lgbm_load | 0.5724 | 0.5962 | 0.5912 | 0.5834 | 0.4970 | 0.5254 | 0.5127 | 0.5540 |
| lgbm_load_826_leaves15 | 0.5362 | 0.5724 | 0.5900 | 0.6282 | 0.5411 | 0.5050 | 0.5193 | 0.5560 |
| lgbm_load_364 | 0.5312 | 0.5559 | 0.5851 | 0.6734 | 0.5751 | 0.5002 | 0.5148 | 0.5622 |
| lgbm_all_364 | 0.5410 | 0.5643 | 0.5816 | 0.6578 | 0.5871 | 0.5246 | 0.5024 | 0.5655 |
| lgbm_price | 0.7064 | 0.6547 | 0.7248 | 0.6277 | 0.5887 | 0.6617 | 0.6340 | 0.6569 |
| mstl_182 | 0.7106 | 0.6521 | 0.7165 | 0.7317 | 0.6666 | 0.6596 | 0.6837 | 0.6887 |
| naive | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

MAE in EUR/MWh:

| Setting | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|
| `lgbm_load_826_slow` | 17.17 | 18.92 | 13.86 | 11.50 | 10.23 | 14.65 | 21.93 | 15.46 |
| `lgbm_load_826` | 17.74 | 19.18 | 13.77 | 11.56 | 10.31 | 14.62 | 22.09 | 15.61 |
| `lgbm_load_826_l1` | 17.93 | 18.75 | 14.21 | 10.72 | 10.94 | 15.03 | 22.23 | 15.69 |
| `lgbm_all` | 20.02 | 20.25 | 14.11 | 10.25 | 9.77 | 15.14 | 22.33 | 15.98 |
| `lgbm_all_826` | 18.29 | 19.42 | 14.09 | 11.83 | 10.16 | 14.53 | 22.52 | 15.83 |
| `lgbm_fcst` | 20.08 | 20.46 | 14.41 | 10.65 | 10.03 | 15.69 | 23.14 | 16.35 |
| `lgbm_load` | 20.02 | 20.32 | 14.35 | 10.76 | 9.93 | 15.74 | 23.44 | 16.37 |
| `lgbm_load_826_leaves15` | 18.76 | 19.52 | 14.32 | 11.58 | 10.81 | 15.13 | 23.74 | 16.27 |
| `lgbm_load_364` | 18.58 | 18.95 | 14.20 | 12.42 | 11.49 | 14.98 | 23.54 | 16.31 |
| `lgbm_all_364` | 18.92 | 19.24 | 14.12 | 12.13 | 11.73 | 15.72 | 22.97 | 16.40 |
| `lgbm_price` | 24.71 | 22.32 | 17.60 | 11.57 | 11.76 | 19.82 | 28.99 | 19.54 |
| `mstl_182` | 24.86 | 22.23 | 17.39 | 13.49 | 13.32 | 19.76 | 31.26 | 20.33 |
| naive | 34.98 | 34.09 | 24.28 | 18.44 | 19.98 | 29.96 | 45.72 | 29.63 |

RMSE in EUR/MWh:

| Setting | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|
| `lgbm_load_826_slow` | 27.20 | 26.03 | 18.87 | 19.68 | 16.85 | 20.43 | 31.40 | 22.92 |
| `lgbm_load_826` | 27.91 | 26.23 | 18.81 | 19.83 | 16.95 | 20.43 | 31.73 | 23.13 |
| `lgbm_load_826_l1` | 33.03 | 26.52 | 20.23 | 19.00 | 18.58 | 21.47 | 33.55 | 24.62 |
| `lgbm_all` | 31.48 | 26.95 | 20.20 | 18.17 | 16.01 | 21.07 | 31.67 | 23.65 |
| `lgbm_all_826` | 27.21 | 26.45 | 19.26 | 20.44 | 16.49 | 20.39 | 31.99 | 23.18 |
| `lgbm_fcst` | 31.78 | 27.42 | 20.50 | 18.36 | 16.84 | 21.71 | 32.31 | 24.13 |
| `lgbm_load` | 32.32 | 27.11 | 20.41 | 18.52 | 16.89 | 21.69 | 32.64 | 24.23 |
| `lgbm_load_826_leaves15` | 28.46 | 26.75 | 19.67 | 19.83 | 17.98 | 21.02 | 33.33 | 23.86 |
| `lgbm_load_364` | 31.23 | 26.53 | 19.51 | 20.73 | 17.86 | 20.42 | 33.63 | 24.27 |
| `lgbm_all_364` | 30.98 | 26.41 | 19.31 | 19.61 | 18.24 | 21.28 | 32.01 | 23.98 |
| `lgbm_price` | 39.18 | 31.18 | 25.63 | 19.31 | 18.91 | 26.52 | 40.92 | 28.81 |
| `mstl_182` | 40.28 | 29.48 | 23.29 | 21.75 | 21.17 | 26.38 | 43.56 | 29.42 |
| naive | 58.01 | 47.38 | 34.17 | 28.91 | 30.30 | 41.87 | 64.82 | 43.64 |

Time and memory. "Day loop" is `wall_seconds` of the results file, as in the statistical baseline. "Day loops per fit" is the sum of the day loops divided by the 63 fits of a run, with the forecasts in it. Peak memory is the highest value of the seven zones. "Command, start to end" is the wall clock of the whole command, from the log of the run.

| Setting | History days | Trees | Run started (UTC) | Day loops, sum (s) | Fastest zone (s) | Slowest zone (s) | Day loops per fit (s) | Peak memory (MB) | Command, start to end (s) |
|---|---|---|---|---|---|---|---|---|---|
| `lgbm_load_826_slow` | 826 | 400 | 15:44:14 | 436.8 | 58.9 | 66.1 | 6.93 | 315 | 443 |
| `lgbm_load_826` | 826 | 100 | 13:44:35 | 524.0 | 40.1 | 141.6 | 8.32 | 303 | 530 |
| `lgbm_load_826_l1` | 826 | 100 | 15:39:50 | 257.9 | 31.0 | 57.2 | 4.09 | 329 | 263 |
| `lgbm_all` | all | 100 | 15:09:05 | 1642.6 | 174.1 | 293.0 | 26.07 | 419 | 1648 |
| `lgbm_all_826` | 826 | 100 | 13:53:26 | 485.7 | 60.0 | 80.0 | 7.71 | 316 | 492 |
| `lgbm_fcst` | all | 100 | 14:21:53 | 1304.3 | 176.1 | 196.7 | 20.70 | 408 | 1311 |
| `lgbm_load` | all | 100 | 14:43:44 | 1513.4 | 174.2 | 244.0 | 24.02 | 416 | 1520 |
| `lgbm_load_826_leaves15` | 826 | 100 | 15:51:38 | 394.5 | 46.7 | 64.8 | 6.26 | 310 | 400 |
| `lgbm_load_364` | 364 | 100 | 13:38:32 | 157.9 | 14.9 | 38.5 | 2.51 | 288 | 163 |
| `lgbm_all_364` | 364 | 100 | 13:41:36 | 173.1 | 15.4 | 41.4 | 2.75 | 293 | 181 |
| `lgbm_price` | all | 100 | 14:01:39 | 1207.1 | 112.5 | 356.7 | 19.16 | 362 | 1213 |

What it shows:

- By the rule the winner is `lgbm_load_826_slow`, with a mean of 0.5316. The best setting of step 1 is `lgbm_load_826` with 0.5359.
- The owner froze `lgbm_load_826_slow` on 26 Nov 2026. It stands under `backtest.lightgbm_model` in the config (entry 88).
- Every LightGBM setting has a lower mean than `mstl_182`. The winner is ahead of `mstl_182` in every zone.
- The winner is best in SE_4 with 0.4797 and worst in SE_1 with 0.6235. Its mean MAE is 15.46 EUR/MWh, against 20.33 for `mstl_182` and 29.63 for the naive forecast.
- `lgbm_load_826_l1` is grown on the absolute error. Its mean MAE is close to the winner, 15.69 against 15.46, and its mean RMSE is higher, 24.62 against 22.92.
- The day loops of the eleven settings sum to 8097 seconds. The eleven commands took 8164 seconds.
- The run times are noisy, because other processes ran on the machine. They do not rank the settings: the setting with 400 trees took 443 seconds and the same setting with 100 trees 530 seconds.
- The day loops follow the number of training days: 1207 to 1643 seconds on all history, 258 to 524 seconds on 826 days and 158 to 173 seconds on 364 days.

### 7. How firm the choice is

Printed by `python -m epf.evaluation.firmness`, which lives in the repo with tests (entry 83). It reads `backtest_core.csv`, `daily_core.csv` and the saved forecasts and writes nothing. The bootstrap draws whole validation days with replacement, 2000 times with seed 42, and computes the mean relative MAE over the seven zones for each draw. The command for this output is in section 15.

```
Experiment H, validation days 2026-06-23 to 2026-08-21, zones ['DE_LU', 'FR', 'ES', 'SE_1', 'SE_2', 'SE_3', 'SE_4']

1. Recompute from the forecast files, without the harness metrics
   84 model and zone pairs. Largest relative difference of MAE and relative MAE to the saved rows: 0.0e+00
   forecasts outside the validation days or not 1440 per zone: 0. Actual prices that differ from the processed table: 0. Empty forecasts: 0
   (these three counts are over the files of the given models and of naive)
   mean of the daily MAE values, weighted by their market time units, against the pooled MAE, largest relative difference: 3.6e-16. Days per model and zone: [60]
   largest difference of one daily MAE in the daily file to the forecast files: 0.0e+00 EUR/MWh

2. Mean relative MAE over the 7 zones, by half of the days
                        first 30 days  last 30 days  all 60 days
lgbm_load_826_slow             0.5375        0.5365       0.5316
lgbm_load_826                  0.5378        0.5462       0.5359
lgbm_load_826_l1               0.5273        0.5545       0.5379
lgbm_all                       0.5386        0.5509       0.5409
lgbm_all_826                   0.5436        0.5536       0.5430
lgbm_fcst                      0.5500        0.5674       0.5539
lgbm_load                      0.5504        0.5669       0.5540
lgbm_load_826_leaves15         0.5571        0.5674       0.5560
lgbm_load_364                  0.5850        0.5493       0.5622
lgbm_all_364                   0.5801        0.5605       0.5655
lgbm_price                     0.6824        0.6422       0.6569
mstl_182                       0.7135        0.6694       0.6887

3. How often is each model the best of the 12 in a zone, and its median and mean over the zones
                        zones won  median over zones   mean
lgbm_load_826_slow              2             0.5122 0.5316
lgbm_load_826                   1             0.5160 0.5359
lgbm_load_826_l1                1             0.5477 0.5379
lgbm_all                        2             0.5557 0.5409
lgbm_all_826                    1             0.5229 0.5430
lgbm_fcst                       0             0.5741 0.5539
lgbm_load                       0             0.5724 0.5540
lgbm_load_826_leaves15          0             0.5411 0.5560
lgbm_load_364                   0             0.5559 0.5622
lgbm_all_364                    0             0.5643 0.5655
lgbm_price                      0             0.6547 0.6569
mstl_182                        0             0.6837 0.6887
   best model per zone: {'DE_LU': 'lgbm_load_826_slow', 'FR': 'lgbm_load_826_l1', 'ES': 'lgbm_load_826', 'SE_1': 'lgbm_all', 'SE_2': 'lgbm_all', 'SE_3': 'lgbm_all_826', 'SE_4': 'lgbm_load_826_slow'}

4. Bootstrap over the 60 days (2000 resamples of whole days, seed 42):
   difference in mean relative MAE over the 7 zones, other model minus lgbm_load_826_slow
   lgbm_load_826           mean +0.0044   95% interval -0.0013 to +0.0093   share of resamples where lgbm_load_826_slow is better: 95.1%
   lgbm_load_826_l1        mean +0.0059   95% interval -0.0139 to +0.0229   share of resamples where lgbm_load_826_slow is better: 74.5%
   lgbm_all                mean +0.0093   95% interval -0.0152 to +0.0349   share of resamples where lgbm_load_826_slow is better: 76.3%
   lgbm_all_826            mean +0.0116   95% interval +0.0039 to +0.0196   share of resamples where lgbm_load_826_slow is better: 99.9%
   lgbm_fcst               mean +0.0223   95% interval -0.0036 to +0.0523   share of resamples where lgbm_load_826_slow is better: 94.7%
   lgbm_load               mean +0.0223   95% interval -0.0036 to +0.0537   share of resamples where lgbm_load_826_slow is better: 94.9%
   lgbm_load_826_leaves15  mean +0.0245   95% interval +0.0164 to +0.0322   share of resamples where lgbm_load_826_slow is better: 100.0%
   lgbm_load_364           mean +0.0309   95% interval +0.0135 to +0.0498   share of resamples where lgbm_load_826_slow is better: 100.0%
   lgbm_all_364            mean +0.0346   95% interval +0.0188 to +0.0512   share of resamples where lgbm_load_826_slow is better: 100.0%
   lgbm_price              mean +0.1260   95% interval +0.0887 to +0.1702   share of resamples where lgbm_load_826_slow is better: 100.0%
   mstl_182                mean +0.1588   95% interval +0.1167 to +0.2062   share of resamples where lgbm_load_826_slow is better: 100.0%

5. Mean relative MAE over the 6 zones without SE_2
lgbm_load_826_slow       0.5348
lgbm_load_826_l1         0.5362
lgbm_load_826            0.5393
lgbm_all_826             0.5487
lgbm_all                 0.5495
lgbm_load_826_leaves15   0.5585
lgbm_load_364            0.5601
lgbm_all_364             0.5620
lgbm_fcst                0.5626
lgbm_load                0.5635
lgbm_price               0.6682
mstl_182                 0.6924

6a. Relative MAE by hour of the day (Europe/Berlin), mean over the 7 zones
      lgbm_load_826_slow  lgbm_load_826  lgbm_load_826_l1  lgbm_all  lgbm_all_826  lgbm_fcst  lgbm_load  lgbm_load_826_leaves15  lgbm_load_364  lgbm_all_364  lgbm_price  mstl_182
hour
0                 0.5150         0.5224            0.4781    0.5133        0.5188     0.5184     0.5178                  0.5511         0.5200        0.5269      0.4538    0.4327
1                 0.5220         0.5244            0.4695    0.5327        0.5120     0.5290     0.5330                  0.5467         0.5251        0.5371      0.4738    0.4939
2                 0.5103         0.5210            0.4697    0.5095        0.5038     0.5175     0.5170                  0.5217         0.5131        0.5232      0.4965    0.5307
3                 0.4925         0.4969            0.4597    0.5013        0.4889     0.5108     0.5073                  0.5051         0.4788        0.4949      0.5116    0.5457
4                 0.4847         0.4849            0.4703    0.5028        0.4916     0.5125     0.5111                  0.5058         0.4969        0.5081      0.5174    0.5625
5                 0.4923         0.4884            0.4762    0.5091        0.4917     0.5015     0.5068                  0.5139         0.5144        0.5212      0.5434    0.5663
6                 0.5329         0.5340            0.5021    0.5208        0.5285     0.5137     0.5165                  0.5531         0.5639        0.5567      0.5748    0.5614
7                 0.5202         0.5314            0.5174    0.5241        0.5366     0.5096     0.5123                  0.5405         0.5637        0.5835      0.6162    0.6097
8                 0.5096         0.5232            0.5271    0.5211        0.5386     0.5145     0.5098                  0.5349         0.5681        0.5741      0.6316    0.6252
9                 0.5179         0.5256            0.5362    0.5234        0.5383     0.5290     0.5241                  0.5430         0.5497        0.5539      0.6860    0.6706
10                0.5549         0.5520            0.5597    0.5705        0.5756     0.5909     0.5855                  0.5759         0.5970        0.6016      0.7288    0.7670
11                0.5555         0.5570            0.5629    0.5887        0.5830     0.6076     0.6113                  0.5872         0.6051        0.6063      0.7479    0.8101
12                0.5873         0.5938            0.5889    0.6237        0.6107     0.6685     0.6649                  0.6275         0.6409        0.6386      0.8074    0.8833
13                0.5888         0.5932            0.5967    0.6443        0.6096     0.6956     0.6987                  0.6379         0.6470        0.6359      0.8509    0.9127
14                0.5661         0.5613            0.5721    0.6241        0.5854     0.6851     0.6842                  0.6242         0.6212        0.6205      0.8340    0.8891
15                0.5517         0.5521            0.5608    0.6080        0.5820     0.6411     0.6381                  0.5930         0.5968        0.6056      0.7800    0.8246
16                0.5453         0.5490            0.5539    0.5792        0.5619     0.5994     0.6041                  0.5712         0.5864        0.5809      0.7313    0.7661
17                0.5203         0.5329            0.5348    0.5303        0.5332     0.5395     0.5470                  0.5376         0.5519        0.5423      0.6911    0.7292
18                0.5066         0.5100            0.5233    0.4795        0.5055     0.4946     0.4990                  0.5152         0.5403        0.5361      0.6531    0.6940
19                0.5182         0.5243            0.5503    0.5070        0.5242     0.5116     0.5116                  0.5273         0.5390        0.5434      0.6511    0.7271
20                0.5339         0.5451            0.5636    0.5040        0.5393     0.5278     0.5233                  0.5438         0.5561        0.5553      0.6502    0.7342
21                0.5674         0.5690            0.6291    0.5375        0.5727     0.5414     0.5396                  0.5951         0.5852        0.5878      0.6720    0.7397
22                0.5910         0.5894            0.6165    0.5813        0.5855     0.5869     0.5854                  0.6160         0.6115        0.6270      0.6994    0.7526
23                0.6378         0.6409            0.6061    0.6526        0.6587     0.6471     0.6555                  0.6586         0.6506        0.6840      0.7434    0.7776

6b. Relative MAE of lgbm_load_826_slow by hour of the day (Europe/Berlin) and zone
      DE_LU     FR     ES   SE_1   SE_2   SE_3   SE_4   mean
hour
0    0.6135 0.7010 0.6077 0.4194 0.4243 0.4220 0.4170 0.5150
1    0.6117 0.7470 0.5331 0.4449 0.4705 0.4159 0.4311 0.5220
2    0.6291 0.6277 0.5438 0.4655 0.4623 0.4190 0.4247 0.5103
3    0.6126 0.5309 0.5040 0.5048 0.4589 0.4037 0.4326 0.4925
4    0.5427 0.5607 0.4547 0.5431 0.4269 0.4369 0.4280 0.4847
5    0.5127 0.6142 0.4428 0.5853 0.4536 0.4200 0.4178 0.4923
6    0.5997 0.6517 0.5038 0.6190 0.4836 0.4455 0.4273 0.5329
7    0.5336 0.6661 0.4382 0.6429 0.4888 0.4325 0.4390 0.5202
8    0.4982 0.6474 0.4290 0.6044 0.5016 0.4158 0.4707 0.5096
9    0.5199 0.5511 0.5035 0.6115 0.4572 0.4711 0.5111 0.5179
10   0.6057 0.5512 0.5900 0.6322 0.4709 0.4467 0.5872 0.5549
11   0.5369 0.5406 0.6345 0.6393 0.5006 0.4682 0.5685 0.5555
12   0.5228 0.5483 0.6894 0.6644 0.6002 0.5394 0.5469 0.5873
13   0.4890 0.5002 0.7050 0.6803 0.6169 0.5757 0.5549 0.5888
14   0.4303 0.4903 0.6909 0.6939 0.6003 0.5458 0.5109 0.5661
15   0.4437 0.4905 0.6922 0.7015 0.5633 0.4837 0.4870 0.5517
16   0.4322 0.4646 0.6242 0.6623 0.5492 0.5289 0.5555 0.5453
17   0.4163 0.4717 0.6119 0.6381 0.5561 0.5205 0.4272 0.5203
18   0.3957 0.4741 0.5600 0.6422 0.5454 0.4527 0.4760 0.5066
19   0.3658 0.5138 0.4682 0.6612 0.5426 0.5561 0.5197 0.5182
20   0.4015 0.5743 0.5288 0.6495 0.5312 0.5638 0.4884 0.5339
21   0.4738 0.6043 0.6608 0.6769 0.5080 0.5718 0.4762 0.5674
22   0.6097 0.6045 0.5793 0.6985 0.5111 0.6065 0.5276 0.5910
23   0.8059 0.7207 0.5780 0.7421 0.5373 0.5642 0.5165 0.6378

6c. Mean relative MAE over the 7 zones by calendar week (Monday to Sunday)
            days  lgbm_load_826_slow  lgbm_load_826  lgbm_load_826_l1  lgbm_all  lgbm_all_826  lgbm_fcst  lgbm_load  lgbm_load_826_leaves15  lgbm_load_364  lgbm_all_364  lgbm_price  mstl_182
week from
2026-06-22     6              0.6621         0.6783            0.6790    0.7408        0.6644     0.7544     0.7653                  0.6775         0.6882        0.6911      0.8606    0.9158
2026-06-29     7              0.5974         0.5886            0.5476    0.5402        0.5858     0.5655     0.5700                  0.6135         0.6659        0.6289      0.7510    0.8159
2026-07-06     7              0.3495         0.3502            0.3660    0.3717        0.3592     0.3815     0.3742                  0.3703         0.3953        0.3922      0.4929    0.5112
2026-07-13     7              0.6023         0.6059            0.5828    0.5870        0.6239     0.6080     0.6037                  0.6249         0.6682        0.7058      0.7093    0.7895
2026-07-20     7              0.6420         0.6467            0.6438    0.6686        0.6824     0.6767     0.6759                  0.6858         0.6810        0.7065      0.9047    0.8905
2026-07-27     7              0.5809         0.5821            0.5547    0.5760        0.5976     0.5949     0.5975                  0.6112         0.6114        0.6030      0.7521    0.8294
2026-08-03     7              0.5356         0.5542            0.5330    0.5306        0.5242     0.5533     0.5467                  0.5504         0.5771        0.5806      0.6941    0.7632
2026-08-10     7              0.4741         0.4877            0.4861    0.5045        0.4873     0.5194     0.5164                  0.5063         0.4536        0.4753      0.5181    0.4999
2026-08-17     5              0.5285         0.5342            0.5955    0.5437        0.5625     0.5489     0.5535                  0.5533         0.5567        0.5741      0.5627    0.6011

6d. Days of lgbm_load_826_slow: delivery days with a daily MAE above naive, and the share of its summed absolute error in its 6 worst days
       days above naive  of days share in the 6 worst days
DE_LU                 7       60                     21.9%
FR                   13       60                     18.9%
ES                    8       60                     18.7%
SE_1                 15       60                     40.2%
SE_2                 12       60                     35.7%
SE_3                  7       60                     22.9%
SE_4                  8       60                     22.0%
   daily MAE above naive on 70 of the 420 days of all zones
```

The same command with two models gives the bootstrap line of one pair. Eight pairs, each "other model minus the model named first":

```
   difference in mean relative MAE over the 7 zones, other model minus lgbm_load_826
   lgbm_all_826  mean +0.0072   95% interval -0.0022 to +0.0175   share of resamples where lgbm_load_826 is better: 92.6%
   difference in mean relative MAE over the 7 zones, other model minus lgbm_load_364
   lgbm_all_364  mean +0.0037   95% interval -0.0079 to +0.0144   share of resamples where lgbm_load_364 is better: 75.0%
   difference in mean relative MAE over the 7 zones, other model minus lgbm_load
   lgbm_all  mean -0.0131   95% interval -0.0308 to +0.0003   share of resamples where lgbm_load is better: 3.1%
   difference in mean relative MAE over the 7 zones, other model minus lgbm_fcst
   lgbm_load  mean +0.0001   95% interval -0.0035 to +0.0034   share of resamples where lgbm_fcst is better: 51.1%
   difference in mean relative MAE over the 7 zones, other model minus lgbm_price
   lgbm_fcst  mean -0.1037   95% interval -0.1398 to -0.0714   share of resamples where lgbm_price is better: 0.0%
   difference in mean relative MAE over the 7 zones, other model minus lgbm_load_826
   lgbm_load  mean +0.0179   95% interval -0.0065 to +0.0472   share of resamples where lgbm_load_826 is better: 91.4%
   difference in mean relative MAE over the 7 zones, other model minus lgbm_load_826
   lgbm_load_364  mean +0.0265   95% interval +0.0096 to +0.0461   share of resamples where lgbm_load_826 is better: 99.9%
   difference in mean relative MAE over the 7 zones, other model minus mstl_182
   lgbm_price  mean -0.0329   95% interval -0.0788 to +0.0131   share of resamples where mstl_182 is better: 8.1%
```

What it shows:

- The first place is not firm. `lgbm_load_826` is behind the winner by 0.0044, and its interval holds zero: -0.0013 to +0.0093. The intervals of `lgbm_load_826_l1` and `lgbm_all` hold zero too. So the four best settings are a tie.
- The intervals of `lgbm_fcst` and `lgbm_load` also reach just below zero, with -0.0036. `lgbm_all_826`, `lgbm_load_826_leaves15`, the two settings on 364 days, `lgbm_price` and `mstl_182` are behind the winner.
- The halves disagree about the first place. `lgbm_load_826_l1` is first in the first 30 days, with 0.5273 against 0.5375. The winner is first in the last 30 days, with 0.5365.
- The winner's mean over all 60 days, 0.5316, is below its mean in both halves, 0.5375 and 0.5365. This is arithmetic, not an error. In each zone the 60-day ratio lies between the two half ratios, nearer to the half with the larger naive error. That half is not the same in every zone.
- The zones disagree. The winner is best in DE_LU and SE_4 only. `lgbm_all` is best in SE_1 and SE_2, `lgbm_load_826_l1` in FR, `lgbm_load_826` in ES and `lgbm_all_826` in SE_3.
- Without SE_2 the winner stays first with 0.5348. `lgbm_load_826_l1` is then second with 0.5362.
- By hour of the day the winner is best at hour 4 with 0.4847 and worst at hour 23 with 0.6378. At hour 0 the two settings that read prices only are ahead of the winner: `mstl_182` has 0.4327 and `lgbm_price` 0.4538, against 0.5150. The cause was not looked into.
- By week the winner lies between 0.3495 and 0.6621.
- The winner is worse than the naive forecast on 70 of the 420 zone-days: 15 in SE_1, 13 in FR and 12 in SE_2. In SE_1 and SE_2 the 6 worst days hold 40.2% and 35.7% of the summed absolute error. In the other zones they hold 18.7% to 22.9%.

### 8. What the comparison says about the inputs and the history

This is the answer to RQ2 for LightGBM on the validation days of experiment H. The differences are those of the pair lines of section 7. Each is the mean over the 2000 resamples, not the difference of the two table values. The two differ by up to 0.0011 in this table.

| Question | Settings compared | Mean relative MAE | Difference | 95% interval | Reading |
|---|---|---|---|---|---|
| Do the load, wind and solar forecasts help? | `lgbm_fcst` against `lgbm_price` | 0.5539 against 0.6569 | -0.1037 | -0.1398 to -0.0714 | Yes, clearly, and in every zone |
| Does the actual load of D-2 help on top? | `lgbm_load` against `lgbm_fcst` | 0.5540 against 0.5539 | +0.0001 | -0.0035 to +0.0034 | No |
| Does weather help, on 826 days? | `lgbm_all_826` against `lgbm_load_826` | 0.5430 against 0.5359 | +0.0072 | -0.0022 to +0.0175 | Not settled. The mean is worse with weather |
| Does weather help, on 364 days? | `lgbm_all_364` against `lgbm_load_364` | 0.5655 against 0.5622 | +0.0037 | -0.0079 to +0.0144 | Not settled |
| Does weather help, on all history? | `lgbm_all` against `lgbm_load` | 0.5409 against 0.5540 | -0.0131 | -0.0308 to +0.0003 | Not settled. The mean is better with weather |
| Are 364 days enough? | `lgbm_load_364` against `lgbm_load_826` | 0.5622 against 0.5359 | +0.0265 | +0.0096 to +0.0461 | No. 364 days are worse |
| Is all history worse than 826 days? | `lgbm_load` against `lgbm_load_826` | 0.5540 against 0.5359 | +0.0179 | -0.0065 to +0.0472 | Not settled |
| Does LightGBM beat `mstl_182` on prices alone? | `lgbm_price` against `mstl_182` | 0.6569 against 0.6887 | -0.0329 | -0.0788 to +0.0131 | Not settled |

- The gain of LightGBM over the statistical baseline comes from the forecast inputs. With the price and the calendar alone it is not clearly ahead of `mstl_182`.
- The frozen setting keeps the actual load, although it adds nothing. The best setting of step 1 had it, and step 2 changed one thing at a time.
- **The limit of the weather comparison on all history.** Weather exists from 2024-03-15 only. On all history 1893 of the 2723 training days of the first fit have empty weather features. A tree can split on whether a weather value is empty, and that marks the days from 2024-03-15. So the gain of `lgbm_all` over `lgbm_load` cannot be told apart from a model that treats the recent years on their own. This is reasoning from how LightGBM treats an empty value. It was not measured. On 826 and on 364 days, where every training day lies in the weather period, the mean is worse with weather.
- **The window is a trade between zones.** From `lgbm_load` to `lgbm_load_826` DE_LU improves from 0.5724 to 0.5073, and FR, ES, SE_3 and SE_4 improve too. SE_1 gets worse from 0.5834 to 0.6271, and SE_2 from 0.4970 to 0.5160. One window serves all zones (PROJECT_CONTEXT §1).
- The Swedish zones have no solar feature with a value, so "the forecasts" are the load and the wind forecast there. In SE_1 and SE_2 the results differ on these days, 0.6235 against 0.5122 for the winner, although their prices were identical in almost every hour before 2024-10-30 (entry 48).

### 9. Checks

The saved numbers against the forecast files. This is the first block of the output in section 7, printed on 26 Nov 2026 and again on 27 Nov 2026 with the same numbers:

- The MAE and the relative MAE of the 84 model and zone pairs were computed again from the forecast files, without the metric code of the backtest. The largest relative difference to the saved rows is 0.0e+00.
- No forecast lies outside the validation days, every zone has 1440 forecasts per setting, no forecast is empty, and every actual price equals the processed table.
- The daily losses of `daily_core.csv` agree with the forecast files: the largest difference of one daily MAE is 0.0e+00 EUR/MWh.

The rows:

- Each of the twelve validation runs printed 28 passed checks, 4 for each of the seven zones. After each of them the results files had 7 and 420 new rows and no removed line.
- The `naive_mae` of all 98 LightGBM rows equals the MAE of the saved naive row of the same experiment, split and zone.

The cuts, moved on purpose on 26 Nov 2026 with the finished model. Each change was made, the tests were run, and the code was put back. The suite had 765 tests then:

| Change | Failed tests | Where |
|---|---|---|
| Price cut: end of D-1 to end of D | 63 | `tests/test_features.py` 31, `tests/test_cutoff.py` 14, `tests/test_lgbm.py` 8, `tests/test_stats.py` 6, `tests/test_backtest.py` 4 |
| Training days of a fit end one day later | 3 | all in `tests/test_lgbm.py` |

Recomputed by a reviewer's own code, not by the code of the repo:

- The eleven config entries equal the approved values. Both results files only grew: 77 and 4620 lines were added and none was changed.
- The printed table of section 6 has 0 cells that differ from the results file. The relative MAE from the forecast files agrees with the rows within 3.6e-15.
- The halves, the means and the bootstrap lines of section 7 came out the same at seed 42, and stayed stable at two other seeds.
- On a training day T the values behind the cuts of T were changed. The training rows of T stayed the same to the last bit. Weather from a run after T-1 left the temperature of T empty.
- A fresh fit for the first validation day of DE_LU on experiment H gave the saved forecast to the last bit: 24 hours, largest difference 0.0. The same holds for the first validation day of DE_LU on experiment Q.
- The final review of 27 Nov 2026 made the forecasts of two more validation days again from the real tables: 2026-07-07, a day with a fit, and 2026-07-10, a day between two fits. It did so for `lgbm_load_826_slow` in DE_LU and SE_2 on experiment H and in DE_LU on experiment Q, for `lgbm_all_826` in DE_LU on experiment H, and for the quantile model in DE_LU on experiment H. All 10 forecasts equal the saved files to the last bit.
- In the same 10 cases every value behind the cuts of the day was replaced by noise, and the forecast was made again. It did not change by one bit. As a control, noise in the price of D-1 of the fit day, which the rule allows, changed all 10.
- The firmness command was first a script outside the repo. On the 15 statistical settings it gave the halves, the zones won, the bootstrap lines and the means without SE_2 of section 8 of the statistical baseline to the printed digits. The command of the repo then gave the output of that script again, for the statistical settings and for the LightGBM settings: 1096 and 927 numbers were compared, and 0 differ.

Leakage:

- The lowest relative MAE of any LightGBM setting in any zone on the validation days is 0.4797. No value is below 0.42, the published value for per-hour LightGBM in DE_LU (PROJECT_CONTEXT §7).
- No forecast equals its actual price (a reviewer's own code).

### 10. Experiment Q, validation

`lgbm_load_826_slow` with the same config entry, on the 15-minute table. No other LightGBM setting ran on experiment Q (entry 89). Run of 26 Nov 2026, started 16:11:34 UTC. Every check passed. The command took 220 seconds.

| Model | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|
| lgbm_load_826_slow | 0.5304 | 0.5784 | 0.6227 | 0.6911 | 0.6059 | 0.5040 | 0.5152 | 0.5782 |
| mstl_182 | 0.6611 | 0.6528 | 0.7160 | 0.7267 | 0.6682 | 0.6617 | 0.6955 | 0.6831 |
| naive | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

| Zone | Relative MAE | MAE | RMSE | Naive MAE | Day loop (s) | Peak memory (MB) | Market time units |
|---|---|---|---|---|---|---|---|
| DE_LU | 0.5304 | 18.73 | 34.39 | 35.31 | 30.5 | 281 | 5760 |
| FR | 0.5784 | 20.14 | 28.56 | 34.83 | 26.8 | 285 | 5760 |
| ES | 0.6227 | 15.28 | 20.89 | 24.53 | 26.7 | 292 | 5760 |
| SE_1 | 0.6911 | 13.00 | 21.58 | 18.81 | 33.5 | 292 | 5760 |
| SE_2 | 0.6059 | 12.31 | 19.42 | 20.32 | 35.7 | 296 | 5760 |
| SE_3 | 0.5040 | 15.31 | 21.29 | 30.37 | 31.1 | 299 | 5760 |
| SE_4 | 0.5152 | 23.88 | 34.66 | 46.36 | 30.9 | 301 | 5760 |
| Mean | 0.5782 | 16.95 | 25.83 | 30.08 |  |  |  |

For comparison, `lgbm_load_826_slow` on experiment H validation:

| Zone | Relative MAE | MAE | RMSE | Naive MAE | Day loop (s) | Peak memory (MB) | Market time units |
|---|---|---|---|---|---|---|---|
| DE_LU | 0.4909 | 17.17 | 27.20 | 34.98 | 63.1 | 285 | 1440 |
| FR | 0.5548 | 18.92 | 26.03 | 34.09 | 64.6 | 297 | 1440 |
| ES | 0.5707 | 13.86 | 18.87 | 24.28 | 60.5 | 302 | 1440 |
| SE_1 | 0.6235 | 11.50 | 19.68 | 18.44 | 60.3 | 306 | 1440 |
| SE_2 | 0.5122 | 10.23 | 16.85 | 19.98 | 58.9 | 307 | 1440 |
| SE_3 | 0.4890 | 14.65 | 20.43 | 29.96 | 63.2 | 312 | 1440 |
| SE_4 | 0.4797 | 21.93 | 31.40 | 45.72 | 66.1 | 315 | 1440 |
| Mean | 0.5316 | 15.46 | 22.92 | 29.63 |  |  |  |

- The day loops sum to 215.3 seconds on experiment Q and to 436.8 seconds on experiment H.
- **The 826-day window never applies on experiment Q.** The 15-minute table starts on 2025-10-01. The model trains on 258 delivery days at the first fit of the validation days and on 314 at the last. The whole table holds 415 delivery days, so no fit reaches 826 days, on the test days either. The Q rows still carry `history_days` 826, the value of the entry.
- The Q values are worse than the H values in every zone: 0.5782 against 0.5316 in the mean. The cause was not measured. The Q training rows hold no July and no August of an earlier year, and the model has about a third of the training days.
- `mstl_182` has 0.6831 on these days. LightGBM is ahead of it in every zone.
- The setting was chosen on the hourly table and was not tuned on the 15-minute table.

### 11. Test run

Run once, on 26 Nov 2026, started 16:23:58 UTC, from commit `2ee511a`, after the frozen setting was committed and the owner said yes (entry 90). 90 test days, experiments H and Q. Every check passed in all 14 runs: 56 passed checks. The command took 1179 seconds. No other LightGBM setting has seen the test days.

Relative MAE on the test days, as `python -m epf.evaluation.tables --experiment H --split test` prints it, and the same command with `--experiment Q`. Experiment H:

| Model | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|
| lgbm_load_826_slow | 0.4048 | 0.4854 | 0.5155 | 0.4752 | 0.4296 | 0.5061 | 0.4846 | 0.4716 |
| mstl_182 | 0.4831 | 0.5151 | 0.6137 | 0.6439 | 0.6486 | 0.5499 | 0.5116 | 0.5666 |
| naive | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

Experiment Q:

| Model | DE_LU | FR | ES | SE_1 | SE_2 | SE_3 | SE_4 | Mean |
|---|---|---|---|---|---|---|---|---|
| lgbm_load_826_slow | 0.4028 | 0.4789 | 0.5245 | 0.4936 | 0.4440 | 0.5030 | 0.5079 | 0.4792 |
| mstl_182 | 0.4901 | 0.5182 | 0.6181 | 0.6496 | 0.6466 | 0.5512 | 0.5101 | 0.5691 |
| naive | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

`lgbm_load_826_slow`, experiment H:

| Zone | Relative MAE | MAE | RMSE | Naive MAE | Day loop (s) | Peak memory (MB) | Market time units |
|---|---|---|---|---|---|---|---|
| DE_LU | 0.4048 | 27.90 | 38.50 | 68.92 | 100.6 | 285 | 2161 |
| FR | 0.4854 | 30.76 | 41.13 | 63.37 | 100.6 | 296 | 2161 |
| ES | 0.5155 | 23.70 | 33.25 | 45.97 | 100.5 | 303 | 2161 |
| SE_1 | 0.4752 | 14.85 | 24.74 | 31.25 | 91.5 | 305 | 2161 |
| SE_2 | 0.4296 | 15.66 | 27.45 | 36.44 | 99.9 | 311 | 2161 |
| SE_3 | 0.5061 | 29.31 | 40.07 | 57.91 | 101.5 | 312 | 2161 |
| SE_4 | 0.4846 | 38.74 | 55.16 | 79.95 | 99.8 | 314 | 2161 |
| Mean | 0.4716 | 25.85 | 37.19 | 54.83 |  |  |  |

`lgbm_load_826_slow`, experiment Q:

| Zone | Relative MAE | MAE | RMSE | Naive MAE | Day loop (s) | Peak memory (MB) | Market time units |
|---|---|---|---|---|---|---|---|
| DE_LU | 0.4028 | 27.89 | 39.15 | 69.26 | 64.2 | 333 | 8644 |
| FR | 0.4789 | 30.63 | 40.87 | 63.96 | 71.0 | 333 | 8644 |
| ES | 0.5245 | 24.34 | 34.95 | 46.42 | 70.5 | 334 | 8644 |
| SE_1 | 0.4936 | 15.78 | 25.25 | 31.98 | 68.7 | 334 | 8644 |
| SE_2 | 0.4440 | 16.50 | 28.12 | 37.16 | 63.5 | 334 | 8644 |
| SE_3 | 0.5030 | 29.34 | 40.69 | 58.33 | 60.7 | 338 | 8644 |
| SE_4 | 0.5079 | 40.97 | 58.01 | 80.67 | 73.8 | 340 | 8644 |
| Mean | 0.4792 | 26.49 | 38.15 | 55.39 |  |  |  |

- The day loops sum to 694.5 seconds on H and 472.2 seconds on Q, 1166.7 seconds in all. The peak memory was 340 MB.
- After the run `backtest_core.csv` had 14 new rows and `daily_core.csv` 1260, and no line was removed.
- The `naive_mae` of the 14 new rows equals the MAE of the saved naive test rows.
- 7 of the 90 ES test days, 6 to 12 November 2026, have no wind and no solar forecast. The model uses these inputs, so its ES features are empty there.

**Why the test values are lower than the validation values.** It is the same as for `mstl_182`. On experiment H the mean relative MAE fell from 0.5316 to 0.4716. The model did not get more accurate: its mean MAE rose from 15.46 to 25.85. The naive forecast got much worse: its mean MAE rose from 29.63 to 54.83. So the ratio fell because the price of 7 days before was a poor forecast in the autumn.

**DE_LU against the published value.** DE_LU has 0.4048 on H and 0.4028 on Q. That is below the published 0.42 for per-hour LightGBM in that zone (PROJECT_CONTEXT §7). The gap is less than 0.02, and the published value is for another period and other inputs. On the validation days DE_LU had 0.4909. The final review of 27 Nov 2026 looked for a leak behind this value. It used its own code and read the saved files only:

- The 14 test rows were computed again from the saved forecast files. The largest relative difference to the saved rows is 0.0e+00, and each daily MAE equals `daily_core.csv`.
- No forecast equals its actual price in any zone.
- In DE_LU on experiment H `mstl_182` has the lower daily MAE on 34 of the 90 test days.
- From validation to test the naive MAE of DE_LU on H rose from 34.98 to 68.92 EUR/MWh, and the LightGBM MAE from 17.17 to 27.90.
- `mstl_182`, which reads prices only, fell from 0.7106 to 0.4831 in relative MAE in DE_LU on H.

No fit was repeated on a test day, so no test forecast was made a second time. The reading of these numbers: a fall of this size needs no leak to explain it, because a model that reads prices only fell further. This is a reading, not a proof. The mean of the seven zones, 0.4716, lies inside the published range of 0.42 to 0.48. The Swedish values are 0.43 to 0.51 on H, against the published 0.43 to 0.48.

The test run must not be run again without asking. The test numbers are known from now on, and they must not steer any later choice.

### 12. Quantile forecasts

**The design** (entry 91).

- Five levels: 0.05, 0.25, 0.5, 0.75 and 0.95, under `backtest.quantile_levels` in the config. The levels 0.25 and 0.75 give the 50% interval, 0.05 and 0.95 the 90% interval.
- One set of trees per level, `LgbmQuantileModel` in `src/epf/models/lgbm.py`. Each is grown with the objective `quantile` and `alpha` set to the level. Everything else is the frozen entry: the same features, the same 400 trees and learning rate, the same training rows, the same window and the same weekly fits.
- Each level is fitted on its own, so the five values of a market time unit can cross. They are sorted before they are scored. `crossing_share` is the share of market time units in which sorting moved a value.
- The command is `python -m epf.evaluation.quantiles --split validation`. It writes `reports/results/quantile_core.csv` and saves the sorted forecasts under `data/forecasts/`. It never opens the results files of the backtest.
- The model is named `lgbm_load_826_slow_quantiles`. That name is not under `backtest.test_models`, so the test days are refused. Quantiles on the test days need another yes of the owner.

**The scores.** With e as the actual price minus the forecast of a level q, the pinball loss is the mean of the larger of q times e and (q - 1) times e. Lower is better. Coverage is the share of actual prices inside an interval, and a price on a bound counts as inside. Width is the mean distance between the two bounds.

Run once on the validation days of experiments H and Q, started on 26 Nov 2026 at 17:04:56 UTC. Every check passed: 70 passed checks, 5 for each zone and experiment. The command took 1109 seconds. Pinball losses and widths are in EUR/MWh.

Experiment H:

| Zone | Pinball 0.05 | Pinball 0.25 | Pinball 0.5 | Pinball 0.75 | Pinball 0.95 | Mean pinball | Coverage 50% | Width 50% | Coverage 90% | Width 90% | Crossing share | Day loop (s) | Peak memory (MB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DE_LU | 2.43 | 6.66 | 8.91 | 7.90 | 4.03 | 5.9865 | 0.3569 | 21.21 | 0.7361 | 66.11 | 0.3132 | 111.5 | 322 |
| FR | 3.39 | 8.02 | 9.29 | 8.00 | 4.01 | 6.5406 | 0.3660 | 23.16 | 0.6840 | 68.86 | 0.2021 | 113.6 | 331 |
| ES | 2.77 | 5.88 | 6.96 | 5.83 | 2.81 | 4.8508 | 0.3500 | 17.83 | 0.6896 | 59.75 | 0.2910 | 112.2 | 336 |
| SE_1 | 1.18 | 3.92 | 5.38 | 5.16 | 2.97 | 3.7212 | 0.4222 | 11.80 | 0.8035 | 30.08 | 0.0924 | 99.1 | 340 |
| SE_2 | 0.98 | 3.83 | 5.40 | 5.03 | 3.36 | 3.7210 | 0.3569 | 10.96 | 0.7493 | 27.21 | 0.1896 | 103.5 | 344 |
| SE_3 | 1.93 | 5.93 | 7.42 | 6.69 | 3.03 | 4.9996 | 0.4382 | 19.73 | 0.8069 | 53.90 | 0.1403 | 83.8 | 344 |
| SE_4 | 3.46 | 8.82 | 10.76 | 8.77 | 4.05 | 7.1718 | 0.4035 | 28.71 | 0.8069 | 83.72 | 0.1903 | 83.4 | 344 |
| Mean | 2.30 | 6.15 | 7.73 | 6.77 | 3.46 | 5.2845 | 0.3848 | 19.06 | 0.7538 | 55.66 | 0.2027 |  |  |

Experiment Q:

| Zone | Pinball 0.05 | Pinball 0.25 | Pinball 0.5 | Pinball 0.75 | Pinball 0.95 | Mean pinball | Coverage 50% | Width 50% | Coverage 90% | Width 90% | Crossing share | Day loop (s) | Peak memory (MB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DE_LU | 2.49 | 6.64 | 9.10 | 8.52 | 4.83 | 6.3174 | 0.3387 | 19.34 | 0.7372 | 64.82 | 0.3913 | 62.1 | 359 |
| FR | 3.59 | 8.35 | 10.04 | 8.61 | 4.37 | 6.9902 | 0.3234 | 21.16 | 0.6845 | 66.96 | 0.2931 | 67.4 | 359 |
| ES | 2.91 | 6.63 | 7.81 | 6.64 | 3.39 | 5.4789 | 0.3061 | 17.34 | 0.6392 | 60.67 | 0.3648 | 64.7 | 359 |
| SE_1 | 1.20 | 4.24 | 6.27 | 6.10 | 3.30 | 4.2227 | 0.3533 | 12.78 | 0.7913 | 35.76 | 0.1875 | 52.5 | 359 |
| SE_2 | 1.04 | 4.13 | 6.14 | 6.01 | 3.20 | 4.1038 | 0.3241 | 13.00 | 0.7785 | 37.22 | 0.2514 | 52.1 | 359 |
| SE_3 | 2.40 | 6.13 | 7.54 | 6.48 | 3.17 | 5.1431 | 0.3828 | 17.26 | 0.7599 | 52.62 | 0.3200 | 51.9 | 360 |
| SE_4 | 3.79 | 9.82 | 11.61 | 9.70 | 5.12 | 8.0063 | 0.3566 | 25.57 | 0.7387 | 76.51 | 0.3111 | 46.3 | 360 |
| Mean | 2.49 | 6.56 | 8.36 | 7.44 | 3.91 | 5.7518 | 0.3407 | 18.06 | 0.7328 | 56.37 | 0.3027 |  |  |

Twice the pinball loss at the level 0.5 is the MAE of the median forecast. It is set beside the MAE of the point forecast of `lgbm_load_826_slow`, in EUR/MWh:

| Zone | Twice pinball 0.5, H | Point MAE, H | Difference, H | Twice pinball 0.5, Q | Point MAE, Q | Difference, Q |
|---|---|---|---|---|---|---|
| DE_LU | 17.8237 | 17.1695 | +0.6542 | 18.2015 | 18.7285 | -0.5270 |
| FR | 18.5883 | 18.9155 | -0.3272 | 20.0759 | 20.1444 | -0.0686 |
| ES | 13.9204 | 13.8554 | +0.0651 | 15.6293 | 15.2757 | +0.3537 |
| SE_1 | 10.7567 | 11.4968 | -0.7401 | 12.5490 | 12.9993 | -0.4504 |
| SE_2 | 10.8070 | 10.2315 | +0.5754 | 12.2817 | 12.3111 | -0.0294 |
| SE_3 | 14.8318 | 14.6502 | +0.1815 | 15.0737 | 15.3067 | -0.2330 |
| SE_4 | 21.5203 | 21.9330 | -0.4128 | 23.2196 | 23.8834 | -0.6639 |

What it shows:

- **The intervals are too narrow in every zone and in both experiments.** The 50% interval holds 35% to 44% of the prices on H and 31% to 38% on Q. The 90% interval holds 68% to 81% on H and 64% to 79% on Q. In the mean the 90% interval holds 75% on H and 73% on Q.
- Nothing was recalibrated. The intervals are reported as the model gives them.
- Crossing is common. Sorting changed 9% to 31% of the hours on H and 19% to 39% of the quarter-hours on Q.
- The check on the median: twice the pinball loss at 0.5 is set beside the point MAE in the table above. The largest difference is 0.74 EUR/MWh on H and 0.66 on Q. The two need not be equal, because the point forecast is grown on the squared error. A reviewer's own code found that the trees of the level 0.5 equal a `regression_l1` fit of the same entry.
- The day loops sum to 707.0 seconds on H and 397.0 seconds on Q. The peak memory was 360 MB.

### 13. Run time: estimate against measured

The owner approved an estimate and a ceiling before the eleven validation runs, before the test run and before the quantile run. For the run on experiment Q no estimate is recorded. It ran under the ceiling of 45 minutes per run. The estimate for a setting on all history came from the one timed zone of section 3.

| Part | Estimate | Ceiling | Measured, command start to end |
|---|---|---|---|
| The eleven validation runs, experiment H | 3 hours 45 minutes | 5 hours in all, 45 minutes per run | 8164 seconds, which is 2 hours 16 minutes. The longest run took 1648 seconds |
| One setting on all history | about 28 minutes | 45 minutes | 1213 to 1648 seconds, which is 20 to 27 minutes |
| `lgbm_load_826_slow` on experiment Q, validation | none recorded | 45 minutes | 220 seconds |
| `lgbm_load_826_slow` on the test days, H and Q | 20 minutes | 60 minutes | 1179 seconds, which is 20 minutes |
| Quantiles on the validation days, H and Q | 30 minutes | 60 minutes | 1109 seconds, which is 18 minutes |

- The eleven runs took 60% of the estimated time.
- The estimate for a setting on all history, made from one whole timed zone, held.
- Other processes ran on the machine during the runs, so the times are noisy.

### 14. Limits

- The winner was picked among eleven settings on the same 60 days of one summer, so its validation value of 0.5316 is somewhat optimistic.
- The four best settings cannot be told apart on 60 days.
- The bootstrap treats the days as independent. Errors of neighbouring days are related, so its intervals are likely too narrow.
- Three parameter changes were tried, each alone. No grid was searched, and the calendar features were not tried as categories.
- The window of 826 days is a trade between zones: better in DE_LU, worse in SE_1 and SE_2 (section 8).
- On experiment Q the window never applies, the setting was not tuned there, and the training rows start in October 2025 (section 10).
- The weather comparison is not settled, and on all history it cannot separate weather from the recent years (section 8). The frozen setting uses no weather.
- The quantile intervals are too narrow and are not recalibrated. In the mean 20% of the hours and 30% of the quarter-hours had crossed values that were sorted.
- The load forecast and the wind and solar forecast are taken as known before the gate closure. For wind and solar this is an assumption (PROJECT_CONTEXT §5). The gain from 0.6569 to 0.5539 rests on these inputs.
- SE_4 has no usable solar forecast, and the solar features are empty in all four Swedish zones. SE_1 and SE_2 are near-duplicates, so the seven zones are not seven independent results.
- 7 of the 90 ES test days have no wind and no solar forecast.
- Determinism was measured on made-up tables and on real validation days. A fresh fit gave the saved forecast to the last bit on the first validation day of DE_LU on experiments H and Q, and in the final review on 2026-07-07 and 2026-07-10 (section 9). LightGBM states it for one machine and one version only.
- On 26 Nov 2026 at about 18:15 local time (12:45 UTC) a Visual Studio installer replaced the Visual C++ runtime of the machine, and `import lightgbm` failed until it had finished. The determinism runs of section 2 were made before that, the backtest runs after it. Every backtest command imports `lightgbm` now, also for the naive forecast and `mstl_182`.
- `wall_seconds` measures feature building, not the cost of the trees, and the run times are noisy.
- The checks of section 9 were made on the validation days. For the test days there are the checks of the run and the row counts of section 11. The final review of 27 Nov 2026 also computed the 14 test rows and every daily MAE again from the saved forecast files, with its own code and with no difference. No fit was repeated on a test day.
- A results row holds the config entry of the model in `model_params`. It does not hold the feature settings under `features` in the config: the price lags, the forecast lags and the columns summed into each forecast feature. A test in `tests/test_config.py` pins that section to the values of the freeze.
- `src/epf/evaluation/quantiles.py` repeats about 70 lines of `backtest.py`: the day loop and the set-up of a run. The owner kept it so. A test compares the inputs that the quantile loop hands over with those of the backtest.
- The test numbers are known from now on. They must not steer any later choice.

### 15. How to run it again

```
.venv\Scripts\python -m epf.data.build_dataset
.venv\Scripts\python -m epf.evaluation.backtest --model lgbm_load_826_slow --split validation --experiment H
.venv\Scripts\python -m epf.evaluation.backtest --model lgbm_load_826_slow --split validation --experiment Q
.venv\Scripts\python -m epf.evaluation.tables --experiment H --split validation
.venv\Scripts\python -m epf.evaluation.firmness --winner lgbm_load_826_slow --models lgbm_load_826_slow lgbm_load_826 lgbm_load_826_l1 lgbm_all lgbm_all_826 lgbm_fcst lgbm_load lgbm_load_826_leaves15 lgbm_load_364 lgbm_all_364 lgbm_price mstl_182 --without SE_2
.venv\Scripts\python -m epf.evaluation.firmness --winner lgbm_load_826 --models lgbm_load_826 lgbm_all_826
.venv\Scripts\python -m epf.evaluation.quantiles --split validation
```

- Any of the eleven names of section 4 can stand in place of `lgbm_load_826_slow` in the backtest command. A run adds rows to `backtest_core.csv` and replaces the rows of the same model, experiment, split and zone in `daily_core.csv`. The table and the firmness command use the newest row of a model and zone.
- The table command takes `--experiment H` or `Q` and `--split validation` or `test`. It only reads the results file, so it may be run for the test days.
- The sixth line is one pair of section 7. The model named first is the one the other is compared with.
- The quantile command adds 14 rows to `quantile_core.csv` at every run and writes its forecast files again. Do not run it again without asking (CLAUDE.md, Commands).
- Do not run `--model lgbm_load_826_slow --split test` again without asking. The test run was done once, and the ten other LightGBM settings are refused there.
- Do not run the quantile command with `--split test`. It is refused.
- Do not run the firmness command with `--split test`. It was run on the validation days only, and it refuses the test days unless every named model stands under `backtest.test_models`.
- The timing of section 3, the counts of training days, the moved cuts and the reviewers' recomputes of section 9 were made with scripts outside the repo. Their printed output is in this file.

The commits behind the numbers of this section, of 26 and 27 Nov 2026:

| Commit | What it holds |
|---|---|
| `00fbf74` | the holiday dates of a zone handed to every model through `DayInputs` |
| `972595d` | the command that prints the results table |
| `91d5eed` | `lightgbm` 4.7.0 pinned |
| `24c1294` | `src/epf/models/lgbm.py` and its tests |
| `8171bc7` | LightGBM errors as clean refusals, tests of the training day cuts |
| `b0c0103` | the eight settings of step 1 in the config |
| `05a6ab7` | the validation rows of the eight settings, experiment H |
| `be06db3` | the three settings of step 2 in the config |
| `5d5a95e` | the validation rows of the three settings, experiment H |
| `2853866` | `backtest.lightgbm_model: lgbm_load_826_slow` |
| `62b28d6` | the validation rows of `lgbm_load_826_slow`, experiment Q |
| `2ee511a` | `lgbm_load_826_slow` added to `backtest.test_models` |
| `96d48ee` | the test rows of `lgbm_load_826_slow` |
| `4ad9a9c` | the firmness command |
| `bbb2211` | the quantile model and the quantile command |
| `8cbafbc` | the quantile rows |
