# Battery Data Plan

## 1. 데이터 출처

기본 데이터셋은 CALCE Battery Data입니다.

```text
https://calce.umd.edu/battery-data
```

이 프로젝트에서는 Li-ion 배터리 cycle aging 데이터 중 `CS2` 계열을 우선 사용합니다.

## 2. 데이터셋 범위

### 1차 대상: CS2

우선순위는 다음과 같습니다.

```text
CS2_35
CS2_33
CS2_34
CS2_36
CS2_37
CS2_38
```

첫 구현은 `CS2_35` 하나로 원본 구조, 중복 탐지, cycle-level 집계, SoH/EOL/RUL 라벨과 모델 실행 흐름을 검증합니다.

이후 동일한 시험 조건의 CS2 셀을 추가해 NHITS와 PatchTST를 panel time series로 학습하고, 특정 셀을 test로 남기는 cross-cell 평가를 구성합니다.

### 2차 대상: CX2

`CX2`는 CS2 기반 파이프라인이 안정화된 뒤 일반화 검증용으로 사용합니다.

사용 목적은 다음과 같습니다.

- 정격용량이 다른 셀에서 SoH 정규화가 동작하는지 확인합니다.
- CS2에서 만든 전처리와 모델 adapter가 다른 셀 계열에도 적용되는지 확인합니다.
- cross-family 평가를 구성합니다.

## 3. CS2_35 원본 현황

`data/raw/calce/CS2/CS2_35/`에는 원본 Excel 파일 25개가 있습니다.

실제 측정 데이터는 각 파일의 `Channel_1-008` 시트에 있습니다.

25개 파일을 시트 값 기준으로 비교한 결과 다음 파일이 완전히 중복됩니다.

```text
CS2_35_2_10_11.xlsx == CS2_35_2_4_11.xlsx
```

raw 파일은 데이터 계보 보존을 위해 삭제하지 않으며, 중복 파일은 전처리에서만 제외합니다.

따라서 현재 `CS2_35` 전처리는 24개 고유 파일과 886개 global cycle을 사용합니다.

## 4. 원본 데이터 활용 흐름

CALCE 원본 Excel은 모델에 직접 입력하지 않습니다.

현재 파이프라인은 다음 순서로 데이터를 변환합니다.

```text
CALCE raw Excel 25 files
  -> validate sheets and required columns
  -> fingerprint Channel_1-008 values
  -> exclude 1 duplicate source from processing
  -> separate charge/discharge steps by current threshold
  -> aggregate row-level measurements by Cycle_Index
  -> calculate per-cycle capacity from cumulative discharge capacity
  -> classify standard, nonstandard, and invalid cycles
  -> save battery_cycles.csv and battery_cycles.parquet
  -> calculate SoH, EOL, and RUL from modeling cycles
  -> run forecasting and evaluation
  -> save dashboard artifacts
```

## 5. Cycle-Level 집계 기준

원본 `Discharge_Capacity(Ah)`는 파일 내부에서 누적되므로 cycle별 방전 capacity는 다음과 같이 계산합니다.

```text
capacity_ah = discharge_capacity_max.diff()
```

충전과 방전 phase는 다음 기준으로 구분합니다.

```text
charge:    Current(A) > 0.1
discharge: Current(A) < -0.1
```

`Step_Time(s)`는 step마다 다시 시작하므로 각 `Step_Index`의 최대 시간을 합산해 cycle duration을 계산합니다.

생성하는 주요 값은 다음과 같습니다.

- cycle별 capacity입니다.
- 평균, 최소, 최대 voltage입니다.
- 전체, 충전, 방전 평균 current입니다.
- 충전 및 방전 duration입니다.
- 원본 파일명과 local cycle입니다.
- 데이터 내용 fingerprint입니다.
- cycle 품질과 모델링 사용 여부입니다.

## 6. 데이터 품질 기준

파일 품질 검사는 다음 항목을 포함합니다.

- 필수 시트와 컬럼 존재 여부를 확인합니다.
- 시트 값 fingerprint로 중복 파일을 탐지합니다.
- global cycle이 중복 없이 연속적인지 확인합니다.
- CSV와 Parquet의 shape과 컬럼이 동일한지 확인합니다.

cycle 품질 기준은 다음과 같습니다.

```text
valid capacity: 0 < capacity_ah <= 2.0
discharge cutoff: voltage_min <= 2.8V
duration ratio minimum: 0.75
duration baseline: previous 10 cycles only
```

현재 분류 결과는 다음과 같습니다.

| cycle_type | row_count | Usage |
| --- | ---: | --- |
| `standard_full_cycle` | 868 | 공식 분석 및 모델링에 사용합니다. |
| `nonstandard_cycle` | 14 | 원본 추적용으로 유지하고 모델링에서는 제외합니다. |
| `invalid` | 4 | 원본 추적용으로 유지하고 모델링에서는 제외합니다. |

## 7. 저장 방식

사람이 확인할 CSV는 다음 위치에 저장합니다.

```text
data/processed/csv/battery_cycles.csv
```

파이프라인용 Parquet은 다음 위치에 저장합니다.

```text
data/processed/paraquet/battery_cycles.parquet
```

현재 두 파일의 shape은 `(886, 30)`입니다.

CSV는 표 검토와 문서 작성에 사용하고, Parquet은 dtype 보존과 반복적인 모델 파이프라인 로딩에 사용합니다.

## 8. SoH, EOL, RUL 라벨 계획

SoH와 수명 라벨은 `is_modeling_cycle == True`인 868개 cycle을 기준으로 다시 계산합니다.

```text
initial_capacity = mean of initial stable modeling cycles
soh = capacity_ah / initial_capacity
eol_threshold = 0.80
rul = eol_cycle - cycle
rul_clipped = max(rul, 0)
```

원본 global cycle은 삭제하거나 다시 압축하지 않습니다. 제외 cycle이 있어도 실제 실험 순서를 유지해 EOL과 RUL을 계산합니다.

## 9. Forecasting 데이터 사용 계획

직접 예측하는 primary target은 `capacity_ah`입니다.

```text
predicted_soh = predicted_capacity_ah / initial_capacity
predicted_rul = predicted_eol_cycle - forecast_start_cycle
```

예측 모델은 다음 그룹으로 비교합니다.

- Persistence, Moving Average, Linear Trend baseline입니다.
- Ridge와 RandomForest 전통 ML 모델입니다.
- TimesFM과 Chronos-Bolt foundation model입니다.
- NHITS와 PatchTST 학습형 시계열 모델입니다.

주 평가는 EOL 이전 및 EOL 근처의 짧은 horizon에서 수행합니다. 10, 20, 30-cycle rolling forecast를 우선하며, 긴 Post-EOL 예측은 장기 stress test로 구분합니다.

## 10. 확장 계획

CS2_35 파이프라인이 재검증된 뒤 다음 순서로 확장합니다.

1. 동일 전처리 규칙으로 다른 CS2 셀을 추가합니다.
2. 셀마다 파일 중복과 시험 protocol 차이를 검사합니다.
3. 여러 셀을 panel 형태로 학습합니다.
4. leave-one-cell-out 평가로 일반화 성능을 측정합니다.
5. 전압, 전류, duration과 내부저항 feature를 비교합니다.
6. CX2를 외부 검증 데이터로 추가합니다.

이 문서는 배터리 열화 예지보전 프로젝트의 데이터 출처와 활용 계획을 정리한 Markdown 파일입니다.
