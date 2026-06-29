# Battery Predictive Maintenance Project Guide

## 1. Project Goal

이 프로젝트는 CALCE 공개 Li-ion 배터리 열화 데이터를 사용해 배터리 상태를 시계열로 분석하고, 예지보전 관점에서 SoH(State of Health), capacity fade, RUL(Remaining Useful Life)을 해석하는 프로젝트입니다.

최종 목표는 단순히 다음 값을 예측하는 것이 아니라, 배터리 셀의 열화 패턴을 분석하고 정비 의사결정에 필요한 정보를 대시보드로 제공하는 것입니다.

핵심 질문은 다음과 같습니다.

- 배터리 capacity가 cycle이 증가하면서 어떻게 감소합니까?
- 현재 SoH는 어느 수준입니까?
- SoH 80% 임계점까지 얼마나 남았습니까?
- 셀별 열화 속도와 knee point는 어떻게 다릅니까?
- 여러 시계열 모델 또는 baseline이 열화 패턴을 얼마나 잘 설명합니까?

## 2. Folder Structure

```text
Battery_TimeSeries_Analysis/
├── app/
├── docs/
├── data/
│   ├── processed/
│   └── raw/
│       └── calce/
├── outputs/
├── notebooks/
├── reports/
└── src/
    └── battery_pdm/
```

### `app/`

Streamlit 대시보드 코드를 둡니다.

대시보드는 모델을 실시간으로 학습하거나 대형 모델을 직접 로드하지 않고, `outputs/`에 저장된 분석 결과와 예측 결과를 읽어서 시각화합니다.

현재 구현 파일은 다음과 같습니다.

```text
app/streamlit_app.py
```

대시보드에서 보여줄 항목:

- 셀 ID 선택
- cycle별 capacity/SoH 추세
- EOL threshold 80% 표시
- RUL 추정값
- normal/warning/critical 위험 등급
- 모델별 성능 비교표

### `data/raw/`

다운로드한 원본 데이터를 그대로 보관하는 폴더입니다.

이 폴더의 파일은 직접 수정하지 않습니다. 컬럼명 변경, 결측치 처리, cycle 요약 같은 작업은 모두 `data/processed/`에 새 파일로 저장합니다.

추천 구조:

```text
data/raw/
└── calce/
    ├── CS2/
    │   ├── CS2_33/
    │   ├── CS2_34/
    │   ├── CS2_35/
    │   ├── CS2_36/
    │   ├── CS2_37/
    │   └── CS2_38/
    └── CX2/
        ├── CX2_16/
        ├── CX2_33/
        ├── CX2_35/
        └── CX2_36/
```

처음에는 모든 데이터를 받을 필요 없이 `CS2_35` 하나만 넣고 parser를 검증합니다.

### `data/processed/`

모델과 대시보드가 바로 사용할 수 있도록 정제된 데이터를 저장합니다.

현재 구조는 다음과 같습니다.

```text
data/processed/
├── csv/
│   └── battery_cycles.csv
└── paraquet/
    ├── battery_cycles.parquet
    ├── battery_cycles_labeled.parquet
    └── battery_cycles_analysis.parquet
```

`battery_cycles.csv`와 `battery_cycles.parquet`은 CALCE 원본 로그를 cycle 단위로 요약한 동일한 전처리 결과입니다.

현재 `CS2_35` 원본 파일 25개 중 시트 내용이 중복된 파일 1개를 전처리에서 제외하며, 24개 고유 파일에서 886개 cycle을 생성합니다.

02 전처리의 핵심 컬럼은 다음과 같습니다.

```text
cell_id
cycle
source_file
local_cycle
capacity_ah
voltage_mean
voltage_min
voltage_max
charge_current_mean
discharge_current_mean
charge_duration_sec
discharge_duration_sec
cycle_type
is_modeling_cycle
```

공식 분석과 모델링에는 `cycle_type == "standard_full_cycle"`인 868개 cycle만 사용합니다. 비표준 및 invalid cycle은 원본 추적을 위해 파일에 유지합니다.

### `docs/`

프로젝트 설계, 데이터 정의, 모델링 전략, 실험 기록을 Markdown으로 정리하는 폴더입니다.

예상 문서:

```text
docs/project_structure.md
docs/data_plan.md
docs/data_columns.md
docs/notebook_docs/
```

### `notebooks/`

탐색적 데이터 분석용 Jupyter Notebook을 둡니다.

Notebook은 데이터를 이해하고 시각적으로 확인하기 위한 공간입니다. 재사용 가능한 핵심 코드는 `src/battery_pdm/`로 옮깁니다.


### `outputs/`

모델 예측 결과, 성능 지표, 차트 이미지, 대시보드용 artifact를 저장합니다.


최종 대시보드용 artifact는 다음 위치에 저장합니다.

```text
outputs/csv/evaluation/final/
├── final_rf_forecasts.csv
├── final_rf_forecast_metrics.csv
├── final_rf_forecast_leaderboard.csv
├── final_rf_rul_predictions.csv
├── final_rf_rul_metrics.csv
└── final_rf_decision_leaderboard.csv

outputs/parquet/evaluation/final/
├── final_rf_forecasts.parquet
└── final_rf_rul_predictions.parquet
```

최종 forecast artifact의 핵심 컬럼:

```text
cell_id
scenario_id
scenario_type
cycle
forecast_origin
model_name
target_name
y_true_capacity
y_pred_capacity
y_true_soh
y_pred_soh
true_eol_cycle
true_rul
```

### `reports/`

최종 분석 리포트와 포트폴리오용 결과 요약을 저장합니다.


### `src/battery_pdm/`

재사용 가능한 Python 코드를 둡니다.

현재 구현 모듈:

```text
src/battery_pdm/
├── __init__.py
├── pipeline.py
└── run_final_evaluation.py
```

역할:

- labeled cycle 데이터 로딩
- rolling scenario 로딩
- lag/rolling feature 생성
- 최종 RandomForest forecast 실행
- capacity metric 계산
- EOL/RUL 의사결정 평가
- 대시보드용 final artifact 저장


## 3. Analysis Outputs

이 프로젝트에서 우선 생성할 분석 결과는 다음과 같습니다.

### Capacity Fade Analysis

- cycle별 capacity 감소 추세
- 셀별 capacity fade 속도 비교
- 초기 capacity와 최종 capacity 비교

### SoH Analysis

- cycle별 SoH 추세
- SoH 90%, 85%, 80% 도달 시점
- 정상 열화와 급격한 열화 구간 비교

### RUL Analysis

- 현재 cycle 기준 남은 수명
- 셀별 RUL 분포
- EOL threshold 기준 위험 등급

### Knee Point Analysis

- capacity fade가 급격해지는 지점 탐지
- knee point 전후 열화 속도 비교

## 4. Modeling Usage

이 프로젝트의 중심은 시계열 분석이지만, 예지보전 의사결정을 위해 예측 모델도 사용합니다.

### Target Variables

CALCE 데이터셋은 공식 benchmark target을 지정하지 않으므로, 이 프로젝트에서는 cycle-level 방전 capacity를 기본 열화 신호로 사용합니다.

직접 예측하는 primary target은 다음과 같습니다.

```text
capacity_ah
```

`capacity_ah`는 원본 `Discharge_Capacity(Ah)`의 cycle별 증가분으로 만든 실제 물리량입니다.

파일 내용 중복을 제거한 뒤 `is_modeling_cycle == True`인 표준 완전 충방전 cycle을 공식 target sequence로 사용합니다.

정규화 평가값은 다음과 같습니다.

```text
predicted_soh = predicted_capacity_ah / initial_capacity
```

`soh`는 서로 다른 정격용량의 CS2/CX2 셀을 공통 척도로 비교하고, EOL 80% 기준을 적용하기 위해 사용합니다.

예지보전 파생 결과는 다음과 같습니다.

```text
predicted_eol_cycle
predicted_rul
risk_level
```

`RUL`은 모델이 직접 예측하는 target이 아니라, predicted SoH가 0.80 이하에 처음 도달하는 cycle에서 계산하는 파생값입니다.

기존 SoH 직접 예측 baseline은 target 선택 검증을 위한 보조 실험으로 유지하며, 공식 모델 비교는 `capacity_ah` 직접 예측 결과를 기준으로 수행합니다.

### Baseline Models

먼저 구현할 모델:

- Persistence
- Moving Average
- Linear Trend

이 모델들은 대형 의존성 없이 빠르게 동작하므로, 전체 파이프라인 검증에 사용합니다.

### Foundation Models

추가 비교 모델:

- TimesFM 2.5 200M
- Chronos 또는 Chronos-Bolt

사용 방식:

```text
input: observed capacity_ah trajectory
output: future capacity_ah trajectory with uncertainty interval
derived output: predicted SoH, EOL cycle, RUL, risk level
```

### Deep Learning Forecasting Models

추가 비교 모델:

- NHITS
- PatchTST
- TFT

이 모델들은 여러 셀의 panel time series를 학습하는 비교군으로 사용합니다.

단일 셀의 긴 horizon 결과는 모델의 최종 성능으로 단정하지 않습니다. 주 평가는 EOL 이전 및 EOL 근처의 10, 20, 30-cycle rolling forecast로 수행하고, 긴 Post-EOL 예측은 stress test로 구분합니다.

## 5. Dashboard Usage

대시보드는 다음 artifact를 읽습니다.

```text
data/processed/paraquet/battery_cycles_labeled.parquet
outputs/csv/evaluation/final/final_rf_forecasts.csv
outputs/csv/evaluation/final/final_rf_rul_predictions.csv
outputs/csv/evaluation/final/final_rf_decision_leaderboard.csv
```

대시보드에서 보여줄 정보:

- 선택한 셀의 capacity/SoH history
- 최종 RandomForest forecast curve
- EOL threshold
- estimated RUL
- risk level
- decision leaderboard
- scenario별 event status

위험 등급은 기본적으로 다음 기준을 사용합니다.

```text
normal: SoH >= 0.90
warning: 0.80 <= SoH < 0.90
critical: SoH < 0.80
```

대시보드는 다음 명령으로 실행합니다.

```bash
uv run streamlit run app/streamlit_app.py
```

대시보드는 모델을 실시간으로 재학습하지 않고, `src/battery_pdm/run_final_evaluation.py`가 생성한 final artifact를 읽는 read-only visualization layer입니다.

## 6. Initial Work Order

추천 작업 순서:

1. CALCE에서 `CS2_35` 원본 데이터 다운로드
2. `data/raw/calce/CS2/CS2_35/`에 원본 그대로 저장
3. notebook에서 원본 파일 구조 확인
4. 원본 시트 내용 fingerprint로 중복 파일 검사
5. cycle-level `battery_cycles.parquet` 생성
6. 표준, 비표준, invalid cycle 품질 검증
7. `is_modeling_cycle` 기준으로 SoH/EOL/RUL 라벨 재생성
8. 짧은 horizon rolling baseline 결과 생성
9. TimesFM, Chronos, NeuralForecast 모델 비교
10. forecast와 metric artifact 생성
11. Streamlit 대시보드 구현

데이터 출처와 사용 방식은 `docs/data_plan.md`에 정리되어 있으며, 컬럼 정의는 `docs/data_columns.md`에 정리되어 있습니다.

이 문서는 배터리 열화 예지보전 프로젝트의 폴더 구조와 실행 흐름을 정리한 Markdown 파일입니다.
