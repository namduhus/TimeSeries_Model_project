# 10 Streamlit Dashboard Summary

## 1. 작업 목적

이 문서는 `app/streamlit_app.py`로 구현한 Streamlit 대시보드의 목적, 입력 artifact, 화면 구성, 실행 방법을 정리한 문서입니다.

10번의 목적은 notebook과 pipeline에서 생성한 최종 예지보전 결과를 포트폴리오용 대시보드로 보여주는 것입니다.

대시보드는 모델을 실시간으로 학습하거나 예측하지 않습니다. 이미 저장된 artifact를 읽어 빠르게 시각화하는 방식으로 구성했습니다.

## 2. 구현 파일

대시보드 구현 파일은 다음과 같습니다.

```text
app/streamlit_app.py
```

대시보드는 프로젝트 루트를 자동으로 찾고, `data/`와 `outputs/` 아래의 artifact를 읽습니다.

## 3. 입력 Artifact

대시보드는 다음 파일을 사용합니다.

```text
data/processed/paraquet/battery_cycles_labeled.parquet
outputs/csv/evaluation/final/final_rf_forecasts.csv
outputs/csv/evaluation/final/final_rf_rul_predictions.csv
outputs/csv/evaluation/final/final_rf_decision_leaderboard.csv
```

각 파일의 역할은 다음과 같습니다.

| File | Role |
| --- | --- |
| `battery_cycles_labeled.parquet` | cycle별 capacity, SoH, EOL, RUL 라벨을 제공합니다. |
| `final_rf_forecasts.csv` | 최종 RandomForest 모델의 rolling forecast 결과를 제공합니다. |
| `final_rf_rul_predictions.csv` | scenario별 predicted EOL, predicted RUL, event status를 제공합니다. |
| `final_rf_decision_leaderboard.csv` | 최종 모델의 TP, FN, FP, TN, EOL detection rate, RUL MAE를 제공합니다. |

## 4. 화면 구성

대시보드는 다음 영역으로 구성했습니다.

### Sidebar

Sidebar에서는 다음 값을 선택합니다.

| Control | Description |
| --- | --- |
| `Cell ID` | 분석할 배터리 셀을 선택합니다. 현재는 `CS2_35`를 사용합니다. |
| `Scenario` | rolling forecast scenario를 선택합니다. |
| `Train history window` | forecast 차트에서 예측 시작점 이전의 과거 cycle을 몇 개까지 보여줄지 정합니다. |

`Train history window`는 시각화 범위 조절용입니다. 이 값은 모델 학습이나 예측 결과를 변경하지 않습니다.

### Top KPI

상단 KPI는 다음 정보를 보여줍니다.

```text
Cell
Latest Cycle
Latest SoH
True EOL
Predicted RUL
EOL Detection
```

선택한 scenario의 forecast origin 기준 SoH, risk level, event status도 함께 표시합니다.

### Overview Tab

Overview 탭에서는 전체 capacity fade 흐름을 보여줍니다.

표시 항목은 다음과 같습니다.

```text
Observed capacity
80% EOL threshold
True sustained EOL cycle
최근 cycle table
```

### Forecast Tab

Forecast 탭에서는 선택한 rolling scenario의 예측 결과를 보여줍니다.

표시 항목은 다음과 같습니다.

```text
Train history
Actual future capacity
RandomForest predicted capacity
80% EOL threshold
Forecast origin
True sustained EOL
Predicted EOL
```

Scenario별 true RUL, predicted RUL, predicted EOL, RUL error도 KPI로 제공합니다.

### Decision Tables Tab

Decision Tables 탭에서는 scenario별 RUL 판단 결과와 최종 leaderboard를 보여줍니다.

RUL decision table에는 다음 항목이 포함됩니다.

```text
scenario_id
scenario_type
forecast_origin
origin_soh
origin_risk_level
true_rul
predicted_rul
event_status
rul_error
abs_rul_error
```

Decision leaderboard에는 다음 항목이 포함됩니다.

```text
TP
FN
FP
TN
EOL Detection Rate
False Alarm Rate
RUL MAE
RUL Bias
```

## 5. 실행 방법

프로젝트 루트인 `Battery_TimeSeries_Analysis/`에서 다음 명령으로 실행합니다.

```bash
uv run streamlit run app/streamlit_app.py
```

실행 후 기본 접속 주소는 다음과 같습니다.

```text
http://localhost:8501
```

## 6. 검증 결과

대시보드 구현 후 다음 검증을 수행했습니다.

```text
py_compile: 통과
Streamlit AppTest: exception_count 0
HTTP response: 200 OK
```

Streamlit AppTest에서는 title 1개와 metric 11개가 렌더링되는 것을 확인했습니다.

## 7. 설계 판단

대시보드에서 모델을 실시간으로 실행하지 않는 이유는 다음과 같습니다.

1. TimesFM, Chronos, NeuralForecast 계열 모델은 실행 시간이 길고 환경 의존성이 큽니다.
2. 포트폴리오 데모에서는 빠르고 안정적인 화면 로딩이 중요합니다.
3. 이미 pipeline에서 검증된 artifact를 읽는 방식이 재현성과 운영 안정성에 더 적합합니다.

따라서 대시보드는 `final/` artifact를 읽는 read-only visualization layer로 정의했습니다.

## 8. 현재 한계와 후속 작업

현재 대시보드는 `CS2_35` 단일 셀과 최종 후보 모델인 `capacity_raw + RandomForestRegressor` 결과를 중심으로 구성되어 있습니다.

후속 작업으로는 다음을 고려할 수 있습니다.

| Future Work | Description |
| --- | --- |
| Multi-cell support | CS2/CX2의 다른 셀을 추가해 셀 간 열화 패턴을 비교합니다. |
| Model comparison view | TimesFM, Chronos-Bolt, NHITS, PatchTST 결과를 dashboard에서 함께 비교합니다. |
| Uncertainty band | q10, q50, q90 forecast artifact를 연결해 uncertainty band를 표시합니다. |
| Screenshot report | 포트폴리오 README 또는 reports에 대시보드 화면 캡처를 추가합니다. |

이 문서는 10번 Streamlit dashboard 구현 결과를 정리한 Markdown 파일입니다.
