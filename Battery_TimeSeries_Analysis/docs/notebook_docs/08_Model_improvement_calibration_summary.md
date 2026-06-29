# 08 Model Improvement and Calibration Summary

## 1. 작업 목적

이 문서는 `notebooks/08_model_improvement_calibration.ipynb`에서 수행한 target 개선, smoothing target 비교, rolling forecast 재평가, EOL/RUL 의사결정 평가 결과를 정리한 문서입니다.

08번의 핵심 질문은 다음과 같습니다.

```text
raw capacity_ah를 그대로 예측하는 것보다,
노이즈와 일시적 capacity drop을 완화한 capacity trend를 예측하면
EOL/RUL 판단이 더 좋아지는가?
```

07번까지는 여러 모델을 같은 rolling scenario에서 비교했습니다. 08번에서는 모델을 더 늘리기보다 예측 target 자체를 바꾸었을 때 예지보전 의사결정 품질이 개선되는지 확인했습니다.

## 2. 입력 데이터와 공통 기준

입력 파일은 다음과 같습니다.

```text
data/processed/paraquet/battery_cycles_labeled.parquet
outputs/csv/evaluation/rolling_scenarios.csv
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

Rolling scenario는 07번에서 생성한 15개 scenario를 그대로 사용했습니다.

| Scenario Type | Scenario Count | Purpose |
| --- | ---: | --- |
| `pre_eol_rolling` | 12 | EOL 이전 단기 capacity 예측과 오탐 여부를 확인합니다. |
| `eol_crossing` | 3 | 실제 EOL 및 RUL 탐지 성능을 확인합니다. |

## 3. 비교한 Target

08번에서는 다음 3개 target을 비교했습니다.

| Target Name | Description | Purpose |
| --- | --- | --- |
| `capacity_raw` | 원본 `capacity_ah`입니다. | 기존 예측 기준이며, EOL/RUL 판단의 기준 target입니다. |
| `capacity_ewm_span_9` | 과거 값만 사용하는 EWM smoothing target입니다. | 일시적 drop을 완화하고 추세를 안정화하기 위한 target입니다. |
| `capacity_roll_median_7` | 과거 7개 cycle의 trailing rolling median target입니다. | 단일 cycle 이상치에 덜 민감한 target입니다. |

Smoothing 계산에서는 미래 cycle 정보를 사용하지 않았습니다. `center=True` rolling은 사용하지 않았으며, 모든 smoothing은 forecast origin 이전 정보만 활용할 수 있는 causal 방식으로 구성했습니다.

## 4. Cycle 516 Drop 분석

Cycle 516에서 raw capacity는 다음과 같이 급락했습니다.

```text
cycle: 516
capacity_ah: 0.809484 Ah
SoH: 0.712309
```

이 값만 보면 SoH 80% 미만이므로 `critical` 상태로 보입니다. 그러나 이후 capacity가 다시 회복되며, 실제 sustained EOL은 cycle 546부터 5개 cycle 연속으로 확인됩니다.

따라서 cycle 516은 확정 EOL이라기보다 일시적 capacity drop 또는 측정 변동으로 해석해야 합니다. 이 구간이 Persistence와 일부 threshold 기반 판단을 과도하게 이른 EOL 경보로 유도했습니다.

## 5. Rolling Forecast 결과

08-4에서는 3개 target과 4개 ML 계열 모델을 조합해 rolling forecast를 수행했습니다.

사용한 모델은 다음과 같습니다.

```text
Persistence
MovingAverage
RidgeRegression
RandomForestRegressor
```

저장된 산출물은 다음과 같습니다.

```text
outputs/csv/evaluation/improvement/target_improvement_rolling_forecasts.csv
outputs/csv/evaluation/improvement/target_improvement_rolling_metrics.csv
outputs/csv/evaluation/improvement/target_improvement_rolling_leaderboard.csv
outputs/parquet/evaluation/improvement/target_improvement_rolling_forecasts.parquet
```

산출물 크기는 다음과 같습니다.

```text
target_improvement_rolling_forecasts: 3744 rows, 19 columns
target_improvement_rolling_metrics: 180 rows, 16 columns
target_improvement_rolling_leaderboard: 24 rows, 10 columns
```

Forecast 결과에는 결측치, 음수 예측값, 중복 forecast가 없음을 확인했습니다.

## 6. Pre-EOL Rolling 결과

Pre-EOL rolling에서는 `capacity_roll_median_7` target이 target 기준 오차를 가장 낮췄습니다.

| Target | Model | Target MAE | Raw Capacity MAE |
| --- | --- | ---: | ---: |
| `capacity_roll_median_7` | `Persistence` | 0.004127 | 0.010044 |
| `capacity_roll_median_7` | `RandomForestRegressor` | 0.005055 | 0.010152 |
| `capacity_roll_median_7` | `MovingAverage` | 0.007203 | 0.011807 |
| `capacity_ewm_span_9` | `Persistence` | 0.009249 | 0.012357 |
| `capacity_raw` | `Persistence` | 0.009601 | 0.009601 |

Smoothing target은 target 자체의 단기 추세 예측에는 도움이 되었습니다. 특히 rolling median target은 일시적 drop과 노이즈를 줄이기 때문에 target MAE가 낮게 나왔습니다.

다만 raw capacity 기준으로 비교하면 `capacity_raw + Persistence`가 가장 낮은 MAE를 기록했습니다. 이는 smoothed target 예측값을 raw capacity 관측값과 직접 비교하면 smoothing으로 인해 실제 raw 변동을 따라가지 못하는 구간이 생기기 때문입니다.

## 7. EOL Crossing Capacity 결과

EOL crossing 구간에서 raw capacity 기준 가장 좋은 조합은 `capacity_raw + RandomForestRegressor`입니다.

| Target | Model | Target MAE | Raw Capacity MAE |
| --- | --- | ---: | ---: |
| `capacity_raw` | `RandomForestRegressor` | 0.007790 | 0.007790 |
| `capacity_ewm_span_9` | `RandomForestRegressor` | 0.008281 | 0.011488 |
| `capacity_raw` | `MovingAverage` | 0.011643 | 0.011643 |
| `capacity_ewm_span_9` | `MovingAverage` | 0.009824 | 0.012503 |
| `capacity_roll_median_7` | `RandomForestRegressor` | 0.010779 | 0.014429 |

EOL crossing에서는 smoothing target이 target 기준으로는 안정적인 예측을 만들 수 있지만, raw capacity 기준 EOL threshold와 비교할 때는 오히려 신호를 약하게 만들었습니다.

## 8. EOL/RUL 의사결정 평가

08-5에서는 forecast 결과를 다시 SoH로 변환하고, 80% threshold 및 5-cycle sustained 기준으로 predicted EOL과 predicted RUL을 계산했습니다.

저장된 산출물은 다음과 같습니다.

```text
outputs/csv/evaluation/improvement/target_improvement_rul_predictions.csv
outputs/csv/evaluation/improvement/target_improvement_rul_metrics.csv
outputs/csv/evaluation/improvement/target_improvement_decision_leaderboard.csv
outputs/parquet/evaluation/improvement/target_improvement_rul_predictions.parquet
```

산출물 크기는 다음과 같습니다.

```text
target_improvement_rul_predictions: 180 rows, 22 columns
target_improvement_rul_metrics: 12 rows, 18 columns
target_improvement_decision_leaderboard: 12 rows, 18 columns
```

가장 좋은 결과는 `capacity_raw + RandomForestRegressor`입니다.

| Target | Model | TP | FN | FP | TN | EOL Detection Rate | RUL MAE | RUL Bias |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `capacity_raw` | `RandomForestRegressor` | 2 | 1 | 0 | 12 | 66.67% | 4.0 cycles | -4.0 cycles |
| `capacity_raw` | `Persistence` | 1 | 2 | 0 | 12 | 33.33% | 29.0 cycles | -29.0 cycles |
| `capacity_ewm_span_9` | `RandomForestRegressor` | 0 | 3 | 0 | 12 | 0.00% | 계산 불가 | 계산 불가 |
| `capacity_roll_median_7` | `RandomForestRegressor` | 0 | 3 | 0 | 12 | 0.00% | 계산 불가 | 계산 불가 |

`capacity_raw + RandomForestRegressor`가 탐지한 EOL crossing 시나리오는 다음과 같습니다.

| Scenario | Forecast Origin | True RUL | Predicted EOL Cycle | Predicted RUL | RUL Error |
| --- | ---: | ---: | ---: | ---: | ---: |
| `eol_o516_lead30_h34` | 516 | 30 | 541 | 25 | -5 |
| `eol_o526_lead20_h24` | 526 | 20 | 543 | 17 | -3 |

두 건 모두 실제 EOL보다 약간 이른 경보입니다. 예지보전 관점에서는 늦게 탐지하는 것보다 조기 경보가 더 유용할 수 있으나, 너무 이른 경보는 불필요한 정비 의사결정을 유발할 수 있으므로 RUL bias를 함께 봐야 합니다.

## 9. Smoothing Target 해석

Smoothing target은 Pre-EOL trend 예측 안정성에는 도움이 되었습니다. 하지만 EOL/RUL 탐지에는 도움이 되지 않았습니다.

이유는 다음과 같습니다.

1. EWM과 rolling median은 일시적 drop을 완화합니다.
2. 동시에 실제 EOL 근처에서 threshold 아래로 내려가는 신호도 완화합니다.
3. 80% threshold를 5개 cycle 연속으로 넘는 sustained EOL 기준에서는 smoothing target이 EOL 탐지를 늦추거나 놓치게 만들 수 있습니다.

따라서 smoothing target은 dashboard에서 trend reference로 보여주는 용도에는 적합하지만, 현재 EOL/RUL 의사결정 target으로는 raw capacity가 더 적합합니다.

## 10. 최종 결론

08번 실험의 결론은 다음과 같습니다.

```text
최종 EOL/RUL 판단 target은 capacity_raw를 유지합니다.
개선 후보 모델은 RandomForestRegressor입니다.
```

`capacity_raw + RandomForestRegressor`는 07번의 기존 ML rolling 평가보다 EOL/RUL 판단 품질이 개선되었습니다. 특히 EOL crossing 3개 중 2개를 탐지했고, 탐지된 2개 scenario의 RUL MAE는 4 cycle입니다.

반면 smoothing target은 trend 안정화에는 유용하지만, EOL/RUL 탐지 기준으로는 최종 target으로 채택하지 않습니다.
