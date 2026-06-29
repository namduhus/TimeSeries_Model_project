# 07 Rolling Backtest and RUL Evaluation Summary

## 1. 작업 목적

이 문서는 `notebooks/07_rolling_backtest_and_rul_evaluation.ipynb`에서 수행한 rolling capacity forecast, EOL 탐지, RUL 계산 및 정비 의사결정 평가 결과를 정리한 문서입니다.

07번에서는 05번과 06번의 긴 terminal split을 보완하기 위해 여러 forecast origin에서 10, 20, 30 cycle의 단기 예측을 반복했습니다.

직접 예측 대상은 다음과 같습니다.

```text
capacity_ah
```

SoH와 RUL은 capacity 예측 결과에서 다음 순서로 파생했습니다.

```text
predicted_soh = predicted_capacity_ah / initial_capacity
predicted_eol = predicted SoH < 0.80 for 5 consecutive cycles
predicted_rul = predicted_eol_cycle - forecast_origin
```

## 2. 입력 데이터와 공통 기준

입력 파일은 다음과 같습니다.

```text
data/processed/paraquet/battery_cycles_analysis.parquet
```

`is_modeling_cycle == True`인 868개 표준 full cycle만 사용했습니다.

공통 기준은 다음과 같습니다.

```text
cell_id: CS2_35
initial_capacity: 1.1364220858837624 Ah
EOL threshold: SoH 0.80
EOL confirmation: 5 consecutive modeling cycles
true EOL cycle: 546
```

모든 모델은 동일한 forecast origin, test cycle, 실제 capacity와 실제 SoH를 사용했습니다.

## 3. Rolling 평가 시나리오

총 15개 평가 시나리오를 구성했습니다.

| Scenario Type | Forecast Origins | Horizon | Fold Count | Purpose |
| --- | --- | --- | ---: | --- |
| `pre_eol_rolling` | 182, 292, 403, 515 | 10, 20, 30 | 12 | EOL 이전 단기 capacity 예측과 오탐 여부를 평가합니다. |
| `eol_crossing` | 516, 526, 536 | 34, 24, 14 | 3 | 실제 EOL과 확인 구간인 cycle 546-550을 포함해 EOL 및 RUL을 평가합니다. |

EOL crossing 시나리오의 실제 RUL은 다음과 같습니다.

| Forecast Origin | True RUL | Test Cycles | Actual Forecast Horizon |
| ---: | ---: | --- | ---: |
| 516 | 30 | 517-550 | 34 |
| 526 | 20 | 527-550 | 24 |
| 536 | 10 | 537-550 | 14 |

실제 forecast horizon이 RUL보다 4 cycle 긴 이유는 cycle 546에서 시작된 EOL을 cycle 550까지 5개 연속 관측으로 확인하기 위해서입니다.

전체 test row 수는 모델당 312개이며, 9개 모델의 통합 forecast는 2,808개입니다.

## 4. 평가 모델

| Model Family | Models |
| --- | --- |
| `baseline` | `Persistence`, `MovingAverage`, `LinearTrend` |
| `machine_learning` | `RidgeRegression`, `RandomForestRegressor` |
| `foundation_model` | `TimesFM_2p5_200M`, `ChronosBolt_Base` |
| `deep_learning` | `NHITS`, `PatchTST` |

Baseline과 전통 ML은 point forecast를 생성하는 deterministic 모델입니다. TimesFM, Chronos-Bolt, NHITS, PatchTST는 p10, p50, p90 quantile을 함께 생성합니다.

## 5. Pre-EOL Rolling Capacity 결과

12개 Pre-EOL rolling fold의 평균 capacity 성능은 다음과 같습니다.

| Rank | Model | Model Family | Capacity MAE | Capacity RMSE | sMAPE |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | `TimesFM_2p5_200M` | `foundation_model` | 0.008939 | 0.015955 | 0.963789 |
| 2 | `Persistence` | `baseline` | 0.009601 | 0.016454 | 1.030501 |
| 3 | `ChronosBolt_Base` | `foundation_model` | 0.011195 | 0.017207 | 1.196115 |
| 4 | `RandomForestRegressor` | `machine_learning` | 0.013498 | 0.020633 | 1.422243 |
| 5 | `LinearTrend` | `baseline` | 0.013674 | 0.020786 | 1.439263 |
| 6 | `MovingAverage` | `baseline` | 0.014043 | 0.021036 | 1.472411 |
| 7 | `PatchTST` | `deep_learning` | 0.014716 | 0.022179 | 1.541582 |
| 8 | `NHITS` | `deep_learning` | 0.015542 | 0.025435 | 1.627308 |
| 9 | `RidgeRegression` | `machine_learning` | 0.024443 | 0.032537 | 2.537006 |

Pre-EOL 단기 rolling 평가에서는 TimesFM이 가장 낮은 평균 capacity MAE를 기록했습니다. Persistence가 근접한 2위이므로 짧은 horizon에서 마지막 값을 유지하는 단순 기준 모델도 강한 성능을 보였습니다.

06번의 긴 Pre-EOL terminal split에서는 NHITS가 1위였지만, 07번의 여러 단기 rolling fold에서는 TimesFM이 1위입니다. 따라서 모델 순위는 평가 horizon과 forecast origin에 따라 달라집니다.

## 6. EOL Crossing Capacity 결과

3개 EOL crossing fold의 평균 capacity 성능은 다음과 같습니다.

| Rank | Model | Model Family | Capacity MAE | Capacity RMSE | sMAPE |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | `RidgeRegression` | `machine_learning` | 0.006926 | 0.011836 | 0.762187 |
| 2 | `RandomForestRegressor` | `machine_learning` | 0.009203 | 0.012958 | 1.009672 |
| 3 | `ChronosBolt_Base` | `foundation_model` | 0.010546 | 0.014586 | 1.155312 |
| 4 | `MovingAverage` | `baseline` | 0.011673 | 0.016153 | 1.277101 |
| 5 | `NHITS` | `deep_learning` | 0.013052 | 0.019029 | 1.424719 |
| 6 | `PatchTST` | `deep_learning` | 0.013422 | 0.015869 | 1.478798 |
| 7 | `TimesFM_2p5_200M` | `foundation_model` | 0.014367 | 0.018470 | 1.565494 |
| 8 | `LinearTrend` | `baseline` | 0.022543 | 0.024266 | 2.486246 |
| 9 | `Persistence` | `baseline` | 0.045413 | 0.047277 | 5.182393 |

EOL 근처 capacity MAE는 Ridge가 가장 낮습니다. 그러나 capacity 오차가 낮다고 해서 predicted SoH가 80% 아래로 5개 cycle 연속 하락하는 EOL 이벤트를 탐지하는 것은 아닙니다.

따라서 capacity accuracy와 EOL/RUL decision quality를 별도 지표로 평가해야 합니다.

## 7. Quantile 진단

p10-p90의 명목상 범위는 중앙 80% 예측 구간입니다.

| Scenario Type | Model | Coverage | Mean Interval Width |
| --- | --- | ---: | ---: |
| `pre_eol_rolling` | `TimesFM_2p5_200M` | 93.75% | 0.051184 Ah |
| `pre_eol_rolling` | `ChronosBolt_Base` | 82.08% | 0.034936 Ah |
| `pre_eol_rolling` | `PatchTST` | 50.42% | 0.018713 Ah |
| `pre_eol_rolling` | `NHITS` | 23.75% | 0.007344 Ah |
| `eol_crossing` | `TimesFM_2p5_200M` | 98.61% | 0.057855 Ah |
| `eol_crossing` | `ChronosBolt_Base` | 95.83% | 0.055277 Ah |
| `eol_crossing` | `PatchTST` | 94.44% | 0.052720 Ah |
| `eol_crossing` | `NHITS` | 25.00% | 0.015033 Ah |

TimesFM은 두 시나리오에서 가장 넓은 예측 구간과 높은 coverage를 기록했습니다. Chronos-Bolt도 비교적 높은 coverage를 보였습니다.

NHITS는 interval 폭이 매우 좁고 coverage가 낮아 uncertainty를 과소평가했습니다. PatchTST는 Pre-EOL coverage가 낮지만 EOL crossing 구간에서는 interval이 넓어지면서 coverage가 높아졌습니다.

높은 coverage만으로 quantile 품질이 우수하다고 단정할 수 없습니다. Interval 폭과 coverage를 함께 확인해야 하며, 후속 단계에서 rolling residual 기반 calibration이 필요합니다.

## 8. EOL 및 RUL 계산 방법

각 모델의 predicted capacity를 initial capacity로 나누어 predicted SoH를 계산했습니다.

```text
predicted_soh = predicted_capacity_ah / initial_capacity
```

Predicted SoH가 0.80 미만인 상태가 5개 forecast cycle 연속 유지되면 첫 cycle을 predicted EOL cycle로 정의했습니다.

```text
predicted_rul = predicted_eol_cycle - forecast_origin
```

EOL 이벤트 상태는 다음과 같이 구분했습니다.

| Event Status | Definition |
| --- | --- |
| `true_positive` | 실제 EOL 확인 구간을 포함하고 q50 예측도 EOL을 탐지한 경우입니다. |
| `false_negative` | 실제 EOL 확인 구간을 포함하지만 q50 예측이 EOL을 탐지하지 못한 경우입니다. |
| `false_positive` | 실제 EOL 확인 구간이 없지만 q50 예측이 EOL을 탐지한 경우입니다. |
| `true_negative` | 실제 EOL 확인 구간이 없고 q50 예측도 EOL을 탐지하지 않은 경우입니다. |

Forecast horizon 안에서 EOL이 탐지되지 않으면 해당 RUL 예측은 censored로 처리했습니다.

## 9. EOL 및 RUL 평가 결과

중앙값인 q50 또는 deterministic point forecast 기준 결과는 다음과 같습니다.

| Model | TP | FN | FP | TN | EOL Detection Rate | RUL MAE on Detected | RUL Bias |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `PatchTST` | 1 | 2 | 0 | 12 | 33.33% | 19 cycles | -19 cycles |
| `LinearTrend` | 1 | 2 | 0 | 12 | 33.33% | 27 cycles | -27 cycles |
| `Persistence` | 1 | 2 | 0 | 12 | 33.33% | 29 cycles | -29 cycles |
| `ChronosBolt_Base` | 0 | 3 | 0 | 12 | 0.00% | 계산 불가 | 계산 불가 |
| `MovingAverage` | 0 | 3 | 0 | 12 | 0.00% | 계산 불가 | 계산 불가 |
| `NHITS` | 0 | 3 | 0 | 12 | 0.00% | 계산 불가 | 계산 불가 |
| `RandomForestRegressor` | 0 | 3 | 0 | 12 | 0.00% | 계산 불가 | 계산 불가 |
| `RidgeRegression` | 0 | 3 | 0 | 12 | 0.00% | 계산 불가 | 계산 불가 |
| `TimesFM_2p5_200M` | 0 | 3 | 0 | 12 | 0.00% | 계산 불가 | 계산 불가 |

모든 모델의 Pre-EOL false alarm rate는 q50 기준 0%입니다.

Q50에서 탐지된 세 건은 모두 forecast origin 516 시나리오입니다.

| Model | True RUL | Predicted RUL | RUL Error |
| --- | ---: | ---: | ---: |
| `PatchTST` | 30 | 11 | -19 |
| `LinearTrend` | 30 | 3 | -27 |
| `Persistence` | 30 | 1 | -29 |

음수 RUL bias는 실제보다 EOL이 더 가깝다고 판단한 조기 경보입니다. 탐지된 모델 중 PatchTST의 RUL 오차가 가장 작지만, 한 개 시나리오에서만 탐지했으므로 일반적인 우수성으로 해석할 수 없습니다.

Ridge는 EOL crossing capacity MAE가 가장 낮지만 q50 EOL 탐지율은 0%입니다. 이는 point-wise capacity 정확도와 threshold crossing 탐지 성능이 서로 다르다는 점을 보여줍니다.

## 10. Probabilistic EOL 결과

EOL crossing 시나리오에서 quantile별 탐지율은 다음과 같습니다.

| Model | q10 Detection Rate | q50 Detection Rate | q90 Detection Rate |
| --- | ---: | ---: | ---: |
| `TimesFM_2p5_200M` | 100.00% | 0.00% | 0.00% |
| `ChronosBolt_Base` | 100.00% | 0.00% | 0.00% |
| `PatchTST` | 100.00% | 33.33% | 0.00% |
| `NHITS` | 0.00% | 0.00% | 0.00% |

TimesFM과 Chronos-Bolt는 보수적인 하단 capacity quantile인 q10에서는 EOL을 탐지했지만 중앙값인 q50에서는 탐지하지 못했습니다.

모든 probabilistic 모델의 q90이 EOL을 탐지하지 못했기 때문에 q10-q90 RUL interval은 완성되지 않았습니다. 따라서 현재 결과에서 RUL interval coverage는 계산할 수 없습니다.

## 11. Risk Level 결과

Forecast origin의 point SoH를 다음 기준으로 분류했습니다.

```text
normal:   SoH >= 0.90
warning:  0.80 <= SoH < 0.90
critical: SoH < 0.80
```

Origin 516은 SoH 0.712309로 `critical`이며, 나머지 14개 시나리오는 모두 `warning`입니다.

다만 cycle 516의 capacity 급락은 이후 다시 회복되는 일시적 측정 변동입니다. 실제 지속 EOL은 cycle 546에서 시작하므로 cycle 516의 `critical` 등급을 확정 EOL 상태로 해석해서는 안 됩니다.

현재 risk level은 단일 origin SoH 기반 상태 분류입니다. 최종 대시보드에서는 최근 연속 관측, capacity slope, EOL 예측과 uncertainty를 함께 사용해 위험 등급을 결정해야 합니다.

## 12. 출력 파일

평가 시나리오는 다음 위치에 저장했습니다.

```text
outputs/csv/evaluation/rolling_scenarios.csv
```

Baseline 및 전통 ML 결과는 다음 위치에 저장했습니다.

```text
outputs/csv/evaluation/rolling_baseline_ml_forecasts.csv
outputs/csv/evaluation/rolling_baseline_ml_metrics.csv
outputs/csv/evaluation/rolling_baseline_ml_leaderboard.csv
outputs/parquet/evaluation/rolling_baseline_ml_forecasts.parquet
```

Foundation model 및 deep learning 결과는 다음 위치에 저장했습니다.

```text
outputs/csv/evaluation/rolling_probabilistic_forecasts.csv
outputs/csv/evaluation/rolling_probabilistic_metrics.csv
outputs/csv/evaluation/rolling_quantile_diagnostics.csv
outputs/parquet/evaluation/rolling_probabilistic_forecasts.parquet
```

9개 모델의 통합 결과는 다음 위치에 저장했습니다.

```text
outputs/csv/evaluation/rolling_model_forecasts_all.csv
outputs/csv/evaluation/rolling_model_metrics_all.csv
outputs/csv/evaluation/rolling_model_leaderboard.csv
outputs/parquet/evaluation/rolling_model_forecasts_all.parquet
```

EOL, RUL 및 risk 결과는 다음 위치에 저장했습니다.

```text
outputs/csv/evaluation/rolling_rul_predictions.csv
outputs/csv/evaluation/rolling_rul_metrics.csv
outputs/csv/evaluation/rolling_decision_leaderboard.csv
outputs/csv/evaluation/rolling_risk_summary.csv
outputs/parquet/evaluation/rolling_rul_predictions.parquet
```

주요 결과 크기는 다음과 같습니다.

```text
rolling scenarios: 15 rows, 18 columns
baseline and ML forecasts: 1,560 rows, 28 columns
probabilistic forecasts: 1,248 rows, 28 columns
all model forecasts: 2,808 rows, 28 columns
RUL predictions: 135 rows, 31 columns
RUL metrics: 9 rows, 22 columns
decision leaderboard: 9 rows, 24 columns
risk summary: 15 rows, 8 columns
```

## 13. 검증 결과

다음 항목을 확인했습니다.

- 15개 rolling 시나리오가 생성됐습니다.
- 각 모델이 312개 forecast row를 생성했습니다.
- 9개 모델의 통합 forecast는 2,808개입니다.
- `scenario_id`, `model_name`, `cycle` 조합에 중복이 없습니다.
- 모든 모델이 동일한 test cycle과 실제 capacity를 사용합니다.
- 모든 point forecast는 0 이상입니다.
- Probabilistic 모델의 p10, p50, p90 순서가 유지됩니다.
- RUL prediction은 `15 scenarios x 9 models = 135 rows`입니다.
- 실제 EOL event row는 `3 scenarios x 9 models = 27 rows`입니다.
- Pre-EOL non-event row는 `12 scenarios x 9 models = 108 rows`입니다.
- Predicted EOL cycle은 forecast origin 이후이며 forecast end cycle을 넘지 않습니다.
- RUL prediction CSV와 Parquet의 shape, 컬럼 순서 및 저장 값이 일치합니다.
- 노트북의 07-1부터 07-4까지 모든 검증 셀이 통과했습니다.

## 14. 결과 해석과 한계

이번 rolling 평가에서 TimesFM은 Pre-EOL 단기 capacity MAE가 가장 낮고, Ridge는 EOL crossing capacity MAE가 가장 낮습니다. 그러나 q50 EOL 탐지에서는 PatchTST, LinearTrend, Persistence만 한 건을 탐지했습니다.

현재 RUL 결과에는 다음 제한이 있습니다.

1. `CS2_35` 단일 셀만 사용했습니다.
2. 실제 EOL crossing 시나리오가 3개뿐입니다.
3. Q50에서 탐지된 결과가 모두 cycle 516의 일시적 capacity 급락 영향을 받았습니다.
4. 탐지하지 못한 모델의 RUL MAE는 결측이므로 탐지된 모델과 단순 비교할 수 없습니다.
5. 모든 probabilistic 모델에서 q90 EOL이 검출되지 않아 RUL interval을 평가할 수 없습니다.
6. 현재 risk level은 단일 시점 SoH만 사용하므로 일시적 이상값에 민감합니다.

따라서 현재 결과는 최종 모델 선정 결과가 아니라 개선 전 rolling benchmark입니다.
