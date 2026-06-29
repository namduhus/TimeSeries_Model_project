# 05 Capacity Ah Baseline Forecasting Summary

## 1. 작업 목적

이 문서는 `notebooks/05_capacity_ah_baseline_forecasting.ipynb`에서 수행한 배터리 capacity baseline 예측 결과를 정리한 문서입니다.

직접 예측 대상은 `capacity_ah`입니다. SoH는 별도 모델로 예측하지 않고 다음 식으로 파생합니다.

```text
predicted_soh = predicted_capacity_ah / initial_capacity
```

사용한 초기 capacity는 다음과 같습니다.

```text
initial_capacity: 1.1364220858837624 Ah
```

## 2. 입력 데이터

입력 파일은 다음과 같습니다.

```text
data/processed/paraquet/battery_cycles_analysis.parquet
```

입력 데이터와 모델링 데이터의 크기는 다음과 같습니다.

```text
전체 데이터: 886 rows, 40 columns
모델링 데이터: 868 rows
제외 데이터: 18 rows
```

`is_modeling_cycle == True`인 표준 full cycle만 모델 학습과 평가에 사용했습니다. 제외된 18개 cycle은 비표준 cycle 또는 유효하지 않은 cycle입니다.

## 3. Baseline 모델

모든 모델 결과에는 `model_family = baseline`을 기록했습니다.

| Model | Description |
| --- | --- |
| `Persistence` | 마지막 학습 capacity를 예측 구간 전체에 반복하는 기준 모델입니다. |
| `MovingAverage` | 최근 20개 capacity 평균을 예측 구간 전체에 반복하는 기준 모델입니다. |
| `LinearTrend` | 최근 20개 capacity에 선형 추세를 적합한 후 미래 구간으로 외삽하는 기준 모델입니다. |

물리적으로 capacity는 음수가 될 수 없으므로 예측값은 0 이상으로 제한했습니다. 이번 실행에서는 제한 전 예측값에도 음수가 없었습니다.

세 baseline은 point forecast만 생성하는 deterministic 모델입니다. 따라서 05번의 개별 artifact에는 p10, p50, p90 uncertainty 컬럼이 없습니다. 06번 통합 artifact에서는 baseline의 q50을 point forecast와 동일하게 기록하고, 지원하지 않는 q10과 q90은 결측값으로 유지합니다.

## 4. 실험 구성

| Experiment | Source Rows | Train Rows | Test Rows | Train Cycles | Test Cycles |
| --- | ---: | ---: | ---: | --- | --- |
| `pre_eol_70_split` | 541 | 378 | 163 | 1-381 | 382-545 |
| `post_eol_75_split` | 868 | 651 | 217 | 1-657 | 659-886 |

`pre_eol_70_split`은 EOL 이전 cycle만 사용합니다. 테스트 구간은 sustained EOL cycle인 546 직전까지이므로 EOL 이전 열화 추세 예측을 평가합니다.

`post_eol_75_split`은 전체 모델링 cycle을 75% 시점에서 분할합니다. cycle 658은 모델링 제외 cycle이므로 테스트는 cycle 659부터 시작합니다. 테스트 217개는 모두 Post-EOL 구간입니다.

`post_eol_75_split`의 학습 구간은 EOL cycle 546 이후 데이터도 포함합니다. 따라서 이 실험은 EOL 진입 시점을 미리 예측하는 실험이 아니라, 이미 관측한 Post-EOL 열화 추세를 장기간 외삽하는 stress test입니다.

## 5. Pre-EOL 결과

| Model | Capacity MAE | Capacity RMSE | Capacity sMAPE | SoH MAE | SoH RMSE | SoH sMAPE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `MovingAverage` | 0.028366 | 0.040093 | 2.970140 | 0.024961 | 0.035280 | 2.970140 |
| `Persistence` | 0.028659 | 0.040455 | 2.999884 | 0.025218 | 0.035598 | 2.999884 |
| `LinearTrend` | 0.050528 | 0.065454 | 5.183008 | 0.044462 | 0.057597 | 5.183008 |

Pre-EOL에서는 `MovingAverage`가 가장 낮은 capacity MAE를 기록했습니다. `Persistence`와의 MAE 차이는 약 0.000293 Ah로 매우 작으므로 두 모델의 성능은 유사합니다.

`LinearTrend`는 최근 20개 cycle의 국소 기울기를 163개 cycle 전체에 외삽하면서 오차가 증가했습니다.

## 6. Post-EOL Stress Test 결과

| Model | Capacity MAE | Capacity RMSE | Capacity sMAPE | SoH MAE | SoH RMSE | SoH sMAPE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `LinearTrend` | 0.030896 | 0.036043 | 6.016708 | 0.027187 | 0.031716 | 6.016708 |
| `Persistence` | 0.212946 | 0.257113 | 32.591385 | 0.187382 | 0.226248 | 32.591385 |
| `MovingAverage` | 0.255115 | 0.292993 | 37.393852 | 0.224490 | 0.257820 | 37.393852 |

Post-EOL에서는 `LinearTrend`가 가장 낮은 오차를 기록했습니다. 학습 종료 직전의 열화 기울기가 이후 장기 감소 추세와 비교적 잘 맞았기 때문으로 해석할 수 있습니다.

다만 이 결과는 단일 셀의 특정 분할에서 얻은 결과이며, 학습 데이터에 이미 Post-EOL cycle이 포함되어 있습니다. 따라서 일반적인 EOL 사전 예측 성능이나 다른 배터리 셀에 대한 일반화 성능으로 해석할 수 없습니다.

## 7. Capacity와 SoH의 관계

`CS2_35`에서는 하나의 고정된 초기 capacity를 사용하므로 capacity와 SoH는 상수배 관계입니다.

```text
soh = capacity_ah / initial_capacity
```

따라서 capacity 예측에서 파생한 SoH의 모델 순위는 capacity 기준 모델 순위와 같습니다. MAE와 RMSE는 각각 Ah 단위와 비율 단위로 다르지만, 스케일에 영향을 받지 않는 sMAPE는 capacity와 SoH에서 같은 값입니다.

05번에서는 RUL을 직접 예측하지 않습니다. 이후 단계에서 예측 SoH가 0.80 임계치에 도달하는 cycle을 이용해 RUL을 계산합니다.

## 8. 출력 파일

사람이 직접 확인할 CSV는 `outputs/csv/baseline/`에 저장하고, 파이프라인에서 사용할 Parquet은 `outputs/parquet/baseline/`에 저장했습니다.

Pre-EOL 결과는 다음 파일로 저장했습니다.

```text
outputs/csv/baseline/baseline_capacity_forecasts_pre_eol.csv
outputs/csv/baseline/baseline_capacity_metrics_pre_eol.csv
outputs/parquet/baseline/baseline_capacity_forecasts_pre_eol.parquet
```

Post-EOL 결과는 다음 파일로 저장했습니다.

```text
outputs/csv/baseline/baseline_capacity_forecasts_post_eol.csv
outputs/csv/baseline/baseline_capacity_metrics_post_eol.csv
outputs/parquet/baseline/baseline_capacity_forecasts_post_eol.parquet
```

통합 결과는 다음 파일로 저장했습니다.

```text
outputs/csv/baseline/baseline_capacity_forecasts_all.csv
outputs/csv/baseline/baseline_capacity_metrics_all.csv
outputs/parquet/baseline/baseline_capacity_forecasts_all.parquet
```

통합 결과의 크기는 다음과 같습니다.

```text
forecast: 1,140 rows, 14 columns
metrics: 6 rows, 12 columns
```

## 9. 검증 결과

다음 항목을 확인했습니다.

- Pre-EOL forecast는 `163 test rows x 3 models = 489 rows`입니다.
- Post-EOL forecast는 `217 test rows x 3 models = 651 rows`입니다.
- 통합 forecast는 1,140개이며 중복된 `experiment_name`, `model_name`, `cycle` 조합이 없습니다.
- `y_pred_capacity`에는 음수와 결측값이 없습니다.
- `y_pred_soh`는 `y_pred_capacity / initial_capacity`와 일치합니다.
- 통합 CSV와 Parquet의 shape, 컬럼 순서가 동일합니다.
- 두 실험과 세 baseline 모델이 모두 포함되어 있습니다.
- capacity와 파생 SoH 시각화가 Pre-EOL 및 Post-EOL 실험에서 모두 실행됐습니다.

통합 forecast에서 deterministic baseline의 p10과 p90은 지원하지 않는 값이므로 결측 상태가 정상입니다. 이 결측값은 데이터 오류로 처리하지 않습니다.

## 10. 06번 모델 비교 결과와의 관계

06번에서는 동일한 `capacity_ah` target과 실험 분할을 Ridge, RandomForest, TimesFM, Chronos-Bolt, NHITS, PatchTST에 적용했습니다.

Pre-EOL 전체 비교에서는 `NHITS`가 capacity MAE 0.020932로 가장 우수했으며, 05번 최고 baseline인 MovingAverage의 MAE 0.028366보다 약 26.2% 낮았습니다.

Post-EOL stress test에서는 05번의 `LinearTrend`가 capacity MAE 0.030896으로 전체 모델 중 가장 우수했습니다. 이 결과는 복잡한 모델이 항상 단순 baseline보다 우수하지 않으며, 최근 열화 기울기가 장기 감소 추세와 잘 맞는 구간에서는 LinearTrend가 강한 기준 모델이라는 점을 보여줍니다.

따라서 05번 baseline 결과는 단순한 예비 실험이 아니라 이후 모델이 실제로 개선됐는지 판단하기 위한 공식 비교 기준입니다.
