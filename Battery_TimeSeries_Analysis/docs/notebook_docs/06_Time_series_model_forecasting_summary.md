# 06 Time Series Model Forecasting Summary

## 1. 작업 목적

이 문서는 `notebooks/06_time_series_model_forecasting.ipynb`에서 수행한 전통 머신러닝, 시계열 foundation model, deep learning 모델의 capacity 예측 결과를 정리한 문서입니다.

직접 예측 대상은 다음과 같습니다.

```text
capacity_ah
```

SoH는 각 모델의 capacity 예측값에서 다음 식으로 파생합니다.

```text
predicted_soh = predicted_capacity_ah / initial_capacity
```

RUL은 06번에서 직접 예측하지 않습니다. 후속 단계에서 predicted SoH가 0.80 이하에 처음 도달하는 cycle을 이용해 EOL cycle과 RUL을 계산합니다.

## 2. 입력 데이터와 공통 실험

입력 데이터는 다음 파일입니다.

```text
data/processed/paraquet/battery_cycles_analysis.parquet
```

`is_modeling_cycle == True`인 868개 표준 full cycle만 사용했습니다. 모든 모델은 05번 baseline과 동일한 test cycle과 실제 capacity를 사용합니다.

| Experiment | Train Rows | Test Rows | Train Cycles | Test Cycles | Purpose |
| --- | ---: | ---: | --- | --- | --- |
| `pre_eol_70_split` | 378 | 163 | 1-381 | 382-545 | EOL 이전 장기 예측입니다. |
| `post_eol_75_split` | 651 | 217 | 1-657 | 659-886 | Post-EOL 장기 열화 stress test입니다. |

`post_eol_75_split`의 학습 데이터에는 실제 EOL cycle인 546 이후 관측값이 포함됩니다. 따라서 이 실험은 EOL 진입을 사전에 맞히는 실험이 아니라 이미 관측된 Post-EOL 추세를 장기간 외삽하는 실험입니다.

## 3. 모델 구성

### 3.1 Baseline

| Model | Model Family | Usage |
| --- | --- | --- |
| `Persistence` | `baseline` | 마지막 capacity를 반복합니다. |
| `MovingAverage` | `baseline` | 최근 20개 capacity 평균을 반복합니다. |
| `LinearTrend` | `baseline` | 최근 20개 capacity의 선형 기울기를 외삽합니다. |

### 3.2 Machine Learning

| Model | Model Family | Usage |
| --- | --- | --- |
| `RidgeRegression` | `machine_learning` | lag와 rolling feature를 사용한 선형 회귀 모델입니다. |
| `RandomForestRegressor` | `machine_learning` | lag와 rolling feature를 사용한 tree ensemble 모델입니다. |

사용한 feature는 다음과 같습니다.

```text
cycle
lag_1
lag_3
lag_5
rolling_mean_5
rolling_mean_10
rolling_std_5
rolling_slope_5
```

두 모델은 test 실제값을 다음 step 입력으로 사용하지 않고 이전 예측값을 다시 feature에 넣는 recursive forecast를 수행합니다.

### 3.3 Foundation Model

| Model | Model Family | Usage |
| --- | --- | --- |
| `TimesFM_2p5_200M` | `foundation_model` | TimesFM 2.5 200M의 zero-shot point 및 quantile 예측입니다. |
| `ChronosBolt_Base` | `foundation_model` | Chronos-Bolt Base의 zero-shot quantile 예측입니다. |

TimesFM과 Chronos-Bolt에는 관측된 train capacity trajectory만 전달했으며 배터리 데이터로 별도 fine-tuning하지 않았습니다.

### 3.4 Deep Learning

| Model | Model Family | Usage |
| --- | --- | --- |
| `NHITS` | `deep_learning` | 각 실험 horizon에 맞춰 학습한 direct multi-horizon 모델입니다. |
| `PatchTST` | `deep_learning` | Patch 기반 Transformer 구조의 direct multi-horizon 모델입니다. |

두 모델은 `input_size=32`, `max_steps=300`, `MQLoss(level=[80])` 설정으로 학습했습니다. p10, p50, p90은 각각 `lo-80`, `median`, `hi-80` 출력에서 생성했습니다.

## 4. 공통 Forecast Schema

통합 forecast는 20개 컬럼으로 구성됩니다.

```text
experiment_name
cell_id
model_family
primary_target
model_name
cycle
y_true_capacity
y_pred_capacity_raw
y_pred_capacity
y_true_soh
y_pred_soh
initial_capacity
train_end_cycle
horizon_index
y_pred_capacity_q10
y_pred_capacity_q50
y_pred_capacity_q90
y_pred_soh_q10
y_pred_soh_q50
y_pred_soh_q90
```

Baseline과 전통 ML은 deterministic 모델이므로 q50을 point forecast와 동일하게 기록하고 q10과 q90은 결측값으로 유지합니다. TimesFM, Chronos-Bolt, NHITS, PatchTST는 p10, p50, p90을 모두 저장합니다.

## 5. Pre-EOL Leaderboard

| Rank | Model | Model Family | Capacity MAE | Capacity RMSE | Capacity sMAPE |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | `NHITS` | `deep_learning` | 0.020932 | 0.028294 | 2.204793 |
| 2 | `PatchTST` | `deep_learning` | 0.021095 | 0.030103 | 2.223976 |
| 3 | `ChronosBolt_Base` | `foundation_model` | 0.023762 | 0.032068 | 2.498919 |
| 4 | `MovingAverage` | `baseline` | 0.028366 | 0.040093 | 2.970140 |
| 5 | `RidgeRegression` | `machine_learning` | 0.028597 | 0.033449 | 3.022726 |
| 6 | `Persistence` | `baseline` | 0.028659 | 0.040455 | 2.999884 |
| 7 | `TimesFM_2p5_200M` | `foundation_model` | 0.029407 | 0.041170 | 3.075939 |
| 8 | `RandomForestRegressor` | `machine_learning` | 0.029467 | 0.041368 | 3.081939 |
| 9 | `LinearTrend` | `baseline` | 0.050528 | 0.065454 | 5.183008 |

Pre-EOL에서는 NHITS가 전체 1위이며, 05번의 최고 baseline인 MovingAverage보다 capacity MAE가 약 26.2% 낮습니다. PatchTST와 Chronos-Bolt도 baseline보다 낮은 MAE를 기록했습니다.

TimesFM은 zero-shot 상태에서 Persistence 및 RandomForest와 유사한 수준이지만 최고 baseline을 개선하지 못했습니다.

## 6. Post-EOL Stress Test Leaderboard

| Rank | Model | Model Family | Capacity MAE | Capacity RMSE | Capacity sMAPE |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | `LinearTrend` | `baseline` | 0.030896 | 0.036043 | 6.016708 |
| 2 | `RidgeRegression` | `machine_learning` | 0.171519 | 0.206790 | 27.658039 |
| 3 | `NHITS` | `deep_learning` | 0.173413 | 0.211322 | 27.905235 |
| 4 | `PatchTST` | `deep_learning` | 0.207087 | 0.242335 | 31.990008 |
| 5 | `Persistence` | `baseline` | 0.212946 | 0.257113 | 32.591385 |
| 6 | `TimesFM_2p5_200M` | `foundation_model` | 0.217453 | 0.254551 | 33.176390 |
| 7 | `ChronosBolt_Base` | `foundation_model` | 0.233072 | 0.271167 | 34.945976 |
| 8 | `RandomForestRegressor` | `machine_learning` | 0.236162 | 0.276644 | 35.270356 |
| 9 | `MovingAverage` | `baseline` | 0.255115 | 0.292993 | 37.393852 |

Post-EOL에서는 LinearTrend가 다른 모델보다 크게 낮은 오차를 기록했습니다. 학습 종료 직전 20개 cycle의 열화 기울기가 이후 장기 감소 추세와 잘 맞았기 때문으로 해석할 수 있습니다.

학습 모델 중에서는 Ridge가 가장 우수하고 NHITS가 근접한 결과를 보였습니다. Foundation model과 tree model은 급격한 장기 capacity 감소를 충분히 외삽하지 못했습니다.

## 7. Quantile Coverage

p10-p90은 명목상 중앙 80% 예측 구간입니다.

| Experiment | Model | Coverage | Mean Interval Width |
| --- | --- | ---: | ---: |
| `pre_eol_70_split` | `TimesFM_2p5_200M` | 55.83% | 0.073964 Ah |
| `pre_eol_70_split` | `ChronosBolt_Base` | 52.76% | 0.042965 Ah |
| `pre_eol_70_split` | `NHITS` | 11.04% | 0.006150 Ah |
| `pre_eol_70_split` | `PatchTST` | 36.81% | 0.017975 Ah |
| `post_eol_75_split` | `TimesFM_2p5_200M` | 0.46% | 0.195360 Ah |
| `post_eol_75_split` | `ChronosBolt_Base` | 0.00% | 0.077980 Ah |
| `post_eol_75_split` | `NHITS` | 0.00% | 0.038066 Ah |
| `post_eol_75_split` | `PatchTST` | 0.00% | 0.087582 Ah |

모든 모델의 coverage가 명목 수준인 80%보다 낮습니다. Post-EOL에서는 Chronos-Bolt, NHITS, PatchTST의 모든 실제 capacity가 p10보다 낮았으며 TimesFM도 실제값의 99.54%가 p10보다 낮았습니다.

이는 모델이 실제 열화보다 높은 capacity를 예측하고 uncertainty interval도 급격한 열화를 포함하지 못했다는 의미입니다. 현재 quantile은 정비 위험 판단에 바로 사용할 수 없으며 rolling residual을 이용한 conformal calibration이 필요합니다.

## 8. 출력 파일

전통 ML 결과는 다음 위치에 저장했습니다.

```text
outputs/csv/ml/ml_capacity_forecasts.csv
outputs/csv/ml/ml_capacity_metrics.csv
outputs/parquet/ml/ml_capacity_forecasts.parquet
```

시계열 모델별 결과는 다음 위치에 저장했습니다.

```text
outputs/csv/time_series/timesfm_capacity_forecasts.csv
outputs/csv/time_series/timesfm_capacity_metrics.csv
outputs/csv/time_series/chronos_capacity_forecasts.csv
outputs/csv/time_series/chronos_capacity_metrics.csv
outputs/csv/time_series/neuralforecast_capacity_forecasts.csv
outputs/csv/time_series/neuralforecast_capacity_metrics.csv

outputs/parquet/time_series/timesfm_capacity_forecasts.parquet
outputs/parquet/time_series/chronos_capacity_forecasts.parquet
outputs/parquet/time_series/neuralforecast_capacity_forecasts.parquet
```

전체 통합 결과는 다음 위치에 저장했습니다.

```text
outputs/csv/model_capacity_forecasts_all.csv
outputs/csv/model_capacity_metrics_all.csv
outputs/parquet/model_capacity_forecasts_all.parquet
```

## 9. 최종 검증

최종 결과의 크기는 다음과 같습니다.

```text
forecast: 3,420 rows, 20 columns
metrics: 18 rows, 12 columns
```

다음 항목을 확인했습니다.

- 9개 모델이 각 380개 forecast row를 생성했습니다.
- Pre-EOL 결과는 1,467개이며 Post-EOL 결과는 1,953개입니다.
- `experiment_name`, `model_name`, `cycle` 조합에 중복이 없습니다.
- 모든 point forecast는 0 이상입니다.
- 확률 예측 모델의 p10, p50, p90 순서가 유지됩니다.
- 모든 모델이 동일한 test cycle과 실제 capacity를 사용합니다.
- Chronos와 TimesFM은 `foundation_model`로 분류했습니다.
- NHITS와 PatchTST는 `deep_learning`으로 분류했습니다.
- 통합 CSV와 Parquet의 shape 및 컬럼 구성이 일치합니다.
- Deterministic 모델의 q10과 q90 결측값은 의도된 값입니다.

## 10. 한계와 개선 계획

현재 결과는 `CS2_35` 단일 셀과 두 개의 긴 terminal split에 기반합니다. 이 결과만으로 다른 셀에 대한 일반화 성능이나 실제 정비 시점의 단기 성능을 판단할 수 없습니다.

