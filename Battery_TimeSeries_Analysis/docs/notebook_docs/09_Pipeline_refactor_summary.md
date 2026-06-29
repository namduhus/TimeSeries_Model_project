# 09 Pipeline Refactor Summary

## 1. 작업 목적

이 문서는 notebook에서 검증한 최종 예지보전 평가 흐름을 `src/battery_pdm/` 코드로 옮긴 내용을 정리한 문서입니다.

09번의 목적은 notebook에만 있던 실험 로직을 재사용 가능한 Python pipeline으로 분리해, 대시보드와 재실행 가능한 프로젝트 구조의 기반을 만드는 것입니다.

## 2. 구현 범위

이번 단계에서는 전체 모델을 모두 pipeline화하지 않고, 08번에서 최종 후보로 선정한 조합만 우선 코드화했습니다.

```text
target: capacity_raw
model: RandomForestRegressor
decision rule: SoH 0.80 미만 5-cycle sustained EOL
```

TimesFM, Chronos-Bolt, NHITS, PatchTST의 재실행 pipeline화는 이번 단계의 범위에서 제외했습니다. 해당 모델들은 추가 개선 및 대시보드 확장 단계에서 별도로 정리합니다.

## 3. 추가된 코드

추가된 파일은 다음과 같습니다.

```text
src/battery_pdm/__init__.py
src/battery_pdm/pipeline.py
src/battery_pdm/run_final_evaluation.py
```

`pipeline.py`에는 데이터 로드, lag/rolling feature 생성, RandomForest recursive forecast, capacity metric 계산, EOL/RUL 평가, artifact 저장 함수가 포함되어 있습니다.

`run_final_evaluation.py`는 pipeline 실행 진입점입니다.

## 4. 실행 방법

`src/battery_pdm/` 폴더에서 다음 명령으로 실행합니다.

```bash
uv run python run_final_evaluation.py
```

프로젝트 루트인 `Battery_TimeSeries_Analysis/`에서 실행할 경우에는 다음 명령을 사용할 수 있습니다.

```bash
uv run python src/battery_pdm/run_final_evaluation.py
```

실행 시 07번에서 만든 rolling scenario를 읽고, 08번에서 확정한 최종 후보 모델로 forecast 및 RUL 평가 artifact를 다시 생성합니다.

## 5. 입력 파일

Pipeline 입력 파일은 다음과 같습니다.

```text
data/processed/paraquet/battery_cycles_labeled.parquet
outputs/csv/evaluation/rolling_scenarios.csv
```

`battery_cycles_labeled.parquet`에서는 `is_modeling_cycle == True`인 868개 cycle만 사용합니다.

`rolling_scenarios.csv`는 07번에서 생성한 15개 rolling 평가 시나리오를 그대로 사용합니다.

## 6. 출력 파일

Pipeline 실행 결과는 notebook 산출물과 구분하기 위해 `final/` 폴더에 저장합니다.

```text
outputs/csv/evaluation/final/final_rf_forecasts.csv
outputs/csv/evaluation/final/final_rf_forecast_metrics.csv
outputs/csv/evaluation/final/final_rf_forecast_leaderboard.csv
outputs/csv/evaluation/final/final_rf_rul_predictions.csv
outputs/csv/evaluation/final/final_rf_rul_metrics.csv
outputs/csv/evaluation/final/final_rf_decision_leaderboard.csv
outputs/parquet/evaluation/final/final_rf_forecasts.parquet
outputs/parquet/evaluation/final/final_rf_rul_predictions.parquet
```

CSV는 사람이 확인하기 위한 파일이며, Parquet은 대시보드와 후속 pipeline에서 읽기 위한 파일입니다.

## 7. 검증 결과

Pipeline 실행 결과는 다음과 같습니다.

```text
scenarios: (15, 18)
forecasts: (312, 17)
forecast_metrics: (15, 13)
rul_predictions: (15, 22)
rul_metrics: (1, 18)
```

추가 검증 결과는 다음과 같습니다.

```text
forecast 결측치: 0
음수 예측값: 0
중복 forecast: 0
CSV/Parquet row 수 일치: True
```

## 8. 최종 성능

최종 pipeline의 EOL/RUL 의사결정 성능은 08번의 `capacity_raw + RandomForestRegressor` 결과와 일치합니다.

| Target | Model | TP | FN | FP | TN | EOL Detection Rate | RUL MAE | RUL Bias |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `capacity_raw` | `RandomForestRegressor` | 2 | 1 | 0 | 12 | 66.67% | 4.0 cycles | -4.0 cycles |

탐지한 EOL crossing scenario는 다음과 같습니다.

| Scenario | Forecast Origin | True RUL | Predicted EOL Cycle | Predicted RUL | RUL Error |
| --- | ---: | ---: | ---: | ---: | ---: |
| `eol_o516_lead30_h34` | 516 | 30 | 541 | 25 | -5 |
| `eol_o526_lead20_h24` | 526 | 20 | 543 | 17 | -3 |

Pre-EOL scenario에서는 false positive가 발생하지 않았습니다.
