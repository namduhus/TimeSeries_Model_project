# 02 Cycle-Level Preprocessing Summary

## 1. 전처리 목적

이 문서는 `notebooks/02_cycle_level_preprocessing.ipynb`에서 수행한 `CS2_35` cycle-level 전처리 결과를 정리한 문서입니다.

전처리 대상 원본 폴더는 다음과 같습니다.

```text
data/raw/calce/CS2/CS2_35/
```

전처리의 목적은 row-level 측정값을 cycle-level 테이블로 집계하고, 중복 원본과 비표준 시험 cycle을 구분해 모델링 가능한 capacity trajectory를 만드는 것입니다.

## 2. 원본 파일 로딩

`CS2_35` 원본 Excel 파일 25개를 확인했습니다.

파일명에서 날짜를 파싱해 실험 날짜순으로 정렬했습니다.

```text
first: CS2_35_8_17_10.xlsx
last:  CS2_35_2_10_11.xlsx
```

모든 파일에 `Channel_1-008` 시트가 존재하며, 필수 컬럼 누락은 확인되지 않았습니다.

## 3. 중복 원본 탐지

Excel 파일의 바이너리 해시가 아니라 `Channel_1-008` 시트의 실제 값으로 fingerprint를 생성했습니다.

다음 두 파일의 시트 데이터가 완전히 동일한 것으로 확인됐습니다.

```text
duplicate_file: CS2_35_2_10_11.xlsx
duplicate_of:   CS2_35_2_4_11.xlsx
```

두 파일은 각각 5,983행과 17개 컬럼으로 구성되며 모든 셀 값이 동일합니다. 따라서 `CS2_35_2_10_11.xlsx`는 raw 폴더에서 삭제하지 않고 전처리 대상에서만 제외했습니다.

중복 파일을 제외한 실제 처리 파일 수는 24개입니다.

## 4. Cycle-Level 집계

각 Excel 파일의 row-level 데이터를 `Cycle_Index` 기준으로 집계했습니다.

충전과 방전 구간은 다음 전류 임계치를 적용해 구분했습니다.

```text
charge:    Current(A) > 0.1
discharge: Current(A) < -0.1
```

`Step_Time(s)`는 각 `Step_Index`에서 다시 시작하므로, step별 최대 시간을 계산한 뒤 cycle 단위로 합산했습니다.

```text
phase_duration = sum(max Step_Time(s) by Step_Index)
```

중복 파일을 제외하고 파일 날짜와 local cycle 순서로 결합한 뒤 global `cycle`을 다시 생성했습니다.

최종 cycle-level 데이터 크기는 다음과 같습니다.

```text
rows: 886
columns: 30
cycle_min: 1
cycle_max: 886
raw_source_file_count: 25
processed_source_file_count: 24
duplicate_source_file_count: 1
```

## 5. Capacity 계산

원본 `Discharge_Capacity(Ah)`는 각 파일 내부에서 누적되는 값입니다.

따라서 `capacity_ah`는 파일 내부의 cycle별 `discharge_capacity_max` 차분으로 계산했습니다.

```text
capacity_ah = discharge_capacity_max.diff()
```

각 파일의 첫 cycle은 이전 cycle이 없으므로 해당 cycle의 `discharge_capacity_max`를 그대로 사용했습니다.

전체 capacity 요약은 다음과 같습니다.

```text
capacity_min: 0.0
capacity_max: 1.138460077286744
capacity_mean: 0.8769209524633441
```

## 6. Cycle 품질 분류

단순히 `capacity_ah > 0`인지 확인하는 방식 대신 측정값 유효성, 전압 cutoff, 충전 및 방전 duration을 함께 사용했습니다.

측정값 유효성 기준은 다음과 같습니다.

```text
0 < capacity_ah <= 2.0
discharge_duration_sec is not null
```

정상적인 완전 방전 여부는 다음 기준으로 확인했습니다.

```text
voltage_min <= 2.8V
```

duration 기준값은 미래 cycle을 사용하지 않도록 직전 10개 cycle의 중앙값으로 계산했습니다.

```text
duration_median = duration.shift(1).rolling(10).median()
duration_ratio = duration / duration_median
```

주변 기준 대비 duration 비율이 0.75 미만이거나 방전 cutoff에 도달하지 않은 cycle은 비표준 시험 cycle 후보로 분류했습니다.

최종 `cycle_type` 분류 결과는 다음과 같습니다.

| cycle_type | row_count | 모델링 사용 여부 |
| --- | ---: | --- |
| `standard_full_cycle` | 868 | 사용합니다. |
| `nonstandard_cycle` | 14 | 제외합니다. |
| `invalid` | 4 | 제외합니다. |

`is_modeling_cycle`은 `cycle_type == "standard_full_cycle"`인 경우에만 `True`입니다.

모델링에서 제외되는 global cycle은 다음과 같습니다.

```text
98, 105, 365, 474, 604, 649, 658, 702, 708,
716, 726, 738, 790, 836, 857, 861, 862, 867
```

이 중 `capacity_ah == 0`인 invalid cycle은 다음과 같습니다.

| cycle | source_file | local_cycle | capacity_ah |
| ---: | --- | ---: | ---: |
| 98 | `CS2_35_9_7_10.xlsx` | 45 | 0.0 |
| 474 | `CS2_35_11_24_10.xlsx` | 9 | 0.0 |
| 649 | `CS2_35_12_23_10.xlsx` | 25 | 0.0 |
| 836 | `CS2_35_1_28_11.xlsx` | 37 | 0.0 |

## 7. 최종 컬럼

최종 cycle-level 테이블은 다음 30개 컬럼으로 구성됩니다.

```text
cell_id
cycle
source_file
source_fingerprint
file_order
file_date
local_cycle
row_count
test_time_min
test_time_max
capacity_ah
voltage_mean
voltage_min
voltage_max
current_mean
charge_current_mean
discharge_current_mean
charge_duration_sec
discharge_duration_sec
charge_capacity_max
discharge_capacity_max
charge_duration_median
discharge_duration_median
charge_duration_ratio
discharge_duration_ratio
reached_discharge_cutoff
has_valid_measurement
is_protocol_anomaly
cycle_type
is_modeling_cycle
```

## 8. 저장 결과

사람이 확인하기 위한 CSV 파일은 다음 위치에 저장했습니다.

```text
data/processed/csv/battery_cycles.csv
```

파이프라인에서 사용할 Parquet 파일은 다음 위치에 저장했습니다.

```text
data/processed/paraquet/battery_cycles.parquet
```

두 파일을 다시 읽어 검증한 결과는 다음과 같습니다.

```text
csv shape: (886, 30)
parquet shape: (886, 30)
```

CSV와 Parquet의 row 수와 컬럼명이 동일하며, global cycle이 1부터 886까지 중복 없이 연속적인 것을 확인했습니다.

