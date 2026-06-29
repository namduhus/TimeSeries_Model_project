# Battery Data Column Definitions

## 1. 목적

이 문서는 CALCE `CS2_35` 원본 Excel 데이터와 cycle-level 전처리 및 라벨링 단계에서 사용하는 컬럼을 정의한 문서입니다.

02 전처리 산출물은 다음 파일을 기준으로 합니다.

```text
data/processed/csv/battery_cycles.csv
data/processed/paraquet/battery_cycles.parquet
```

## 2. 원본 Excel 컬럼

원본 측정 데이터는 각 Excel 파일의 `Channel_1-008` 시트에 있습니다.

| Column | Description | Usage |
| --- | --- | --- |
| `Data_Point` | 측정 row의 순번입니다. | row 수 집계와 원본 추적에 사용합니다. |
| `Test_Time(s)` | 파일 내 테스트 시작 후 누적 시간입니다. | cycle 시작 및 종료 시간 집계에 사용합니다. |
| `Date_Time` | Excel serial date 형식의 측정 시각입니다. | 실제 측정 시각 분석 확장에 사용합니다. |
| `Step_Time(s)` | 현재 step 안에서의 경과 시간입니다. | step별 충전 및 방전 시간 계산에 사용합니다. |
| `Step_Index` | 충전, 방전, 휴지 등 시험 step 번호입니다. | phase duration 계산에 사용합니다. |
| `Cycle_Index` | 파일 내부의 cycle 번호입니다. | cycle-level 집계의 기준입니다. |
| `Current(A)` | 측정 전류입니다. | 충전 및 방전 구간과 평균 전류 계산에 사용합니다. |
| `Voltage(V)` | 측정 전압입니다. | 평균, 최소, 최대 전압과 방전 cutoff 판정에 사용합니다. |
| `Charge_Capacity(Ah)` | 파일 내부의 누적 충전 capacity입니다. | cycle별 충전 capacity 차이와 품질 확인에 사용합니다. |
| `Discharge_Capacity(Ah)` | 파일 내부의 누적 방전 capacity입니다. | cycle별 `capacity_ah` 산출에 사용합니다. |
| `Charge_Energy(Wh)` | 누적 충전 에너지입니다. | 에너지 기반 분석 확장에 사용합니다. |
| `Discharge_Energy(Wh)` | 누적 방전 에너지입니다. | 에너지 기반 분석 확장에 사용합니다. |
| `dV/dt(V/s)` | 전압 변화율입니다. | knee point 및 충방전 특성 분석 확장에 사용합니다. |
| `Internal_Resistance(Ohm)` | 내부저항입니다. | 내부저항 기반 열화 feature 확장에 사용합니다. |
| `Is_FC_Data` | fast charge 관련 플래그로 추정되는 값입니다. | 현재 1차 전처리에서는 사용하지 않습니다. |
| `AC_Impedance(Ohm)` | AC impedance입니다. | impedance 기반 분석 확장에 사용합니다. |
| `ACI_Phase_Angle(Deg)` | AC impedance phase angle입니다. | impedance 기반 분석 확장에 사용합니다. |

## 3. 02 전처리 필수 원본 컬럼

현재 cycle-level 전처리에서 직접 읽는 컬럼은 다음과 같습니다.

```text
Data_Point
Test_Time(s)
Step_Time(s)
Step_Index
Cycle_Index
Current(A)
Voltage(V)
Charge_Capacity(Ah)
Discharge_Capacity(Ah)
```

충전은 `Current(A) > 0.1`, 방전은 `Current(A) < -0.1`을 기준으로 구분합니다.

## 4. 02 Cycle-Level 전처리 컬럼

`battery_cycles`는 원본 25개 파일 중 시트 내용이 중복된 1개 파일을 제외한 24개 파일에서 생성한 886개 cycle로 구성됩니다.

| Column | Type | Description | Source or Formula |
| --- | --- | --- | --- |
| `cell_id` | string | 배터리 셀 ID입니다. | 설정값 `CS2_35` |
| `cycle` | integer | 중복 제거 후 생성한 global cycle입니다. | 파일 날짜와 `local_cycle` 순서로 1부터 재생성합니다. |
| `source_file` | string | 해당 cycle의 원본 Excel 파일명입니다. | 원본 파일명 |
| `source_fingerprint` | string | 원본 시트 값으로 생성한 내용 fingerprint입니다. | `Channel_1-008` 값의 SHA-256 fingerprint |
| `file_order` | integer | 파일명 날짜 기준 순서입니다. | 파싱한 파일 날짜 순서 |
| `file_date` | datetime | 파일명에서 파싱한 실험 날짜입니다. | 파일명 월/일/연도 |
| `local_cycle` | integer | 원본 파일 내부 cycle 번호입니다. | `Cycle_Index` |
| `row_count` | integer | cycle에 포함된 측정 row 수입니다. | `Data_Point` 개수 |
| `test_time_min` | float | cycle의 파일 내 최소 테스트 시간입니다. | `Test_Time(s)` 최소값 |
| `test_time_max` | float | cycle의 파일 내 최대 테스트 시간입니다. | `Test_Time(s)` 최대값 |
| `capacity_ah` | float | 해당 cycle에서 방전된 capacity입니다. | 파일 내부 `discharge_capacity_max.diff()` |
| `voltage_mean` | float | cycle의 평균 전압입니다. | `Voltage(V)` 평균 |
| `voltage_min` | float | cycle의 최소 전압입니다. | `Voltage(V)` 최소값 |
| `voltage_max` | float | cycle의 최대 전압입니다. | `Voltage(V)` 최대값 |
| `current_mean` | float | cycle 전체 row의 평균 전류입니다. | `Current(A)` 평균 |
| `charge_current_mean` | float | 충전 구간의 평균 전류입니다. | `Current(A) > 0.1`인 row의 평균 |
| `discharge_current_mean` | float | 방전 구간의 평균 전류입니다. | `Current(A) < -0.1`인 row의 평균 |
| `charge_duration_sec` | float | cycle의 충전 step 시간 합계입니다. | 충전 `Step_Index`별 `Step_Time(s)` 최대값의 합 |
| `discharge_duration_sec` | float | cycle의 방전 step 시간 합계입니다. | 방전 `Step_Index`별 `Step_Time(s)` 최대값의 합 |
| `charge_capacity_max` | float | cycle까지 누적된 최대 충전 capacity입니다. | `Charge_Capacity(Ah)` 최대값 |
| `discharge_capacity_max` | float | cycle까지 누적된 최대 방전 capacity입니다. | `Discharge_Capacity(Ah)` 최대값 |
| `charge_duration_median` | float | 직전 10개 cycle 충전시간의 중앙값입니다. | `charge_duration_sec.shift(1).rolling(10).median()` |
| `discharge_duration_median` | float | 직전 10개 cycle 방전시간의 중앙값입니다. | `discharge_duration_sec.shift(1).rolling(10).median()` |
| `charge_duration_ratio` | float | 과거 기준 대비 현재 충전시간 비율입니다. | `charge_duration_sec / charge_duration_median` |
| `discharge_duration_ratio` | float | 과거 기준 대비 현재 방전시간 비율입니다. | `discharge_duration_sec / discharge_duration_median` |
| `reached_discharge_cutoff` | boolean | 완전 방전 cutoff 도달 여부입니다. | `voltage_min <= 2.8` |
| `has_valid_measurement` | boolean | capacity와 방전시간의 기본 유효성 여부입니다. | `0 < capacity_ah <= 2.0` 및 방전시간 존재 |
| `is_protocol_anomaly` | boolean | 비표준 충방전 시험 cycle 후보 여부입니다. | cutoff 미도달 또는 duration ratio가 0.75 미만인 경우 |
| `cycle_type` | string | cycle 품질 분류입니다. | `standard_full_cycle`, `nonstandard_cycle`, `invalid` |
| `is_modeling_cycle` | boolean | SoH 및 모델링에 사용할 cycle 여부입니다. | `cycle_type == "standard_full_cycle"` |

## 5. Cycle 품질 분류

현재 분류 결과는 다음과 같습니다.

| cycle_type | row_count | Usage |
| --- | ---: | --- |
| `standard_full_cycle` | 868 | SoH, EOL, RUL 및 forecasting에 사용합니다. |
| `nonstandard_cycle` | 14 | 원본 추적용으로 유지하고 모델링에서는 제외합니다. |
| `invalid` | 4 | 원본 추적용으로 유지하고 모델링에서는 제외합니다. |

`cycle_type`은 원본 삭제 기준이 아니라 분석 목적별 사용 여부를 구분하는 품질 플래그입니다.

## 6. 03 이후 라벨 컬럼

다음 컬럼은 02 전처리 파일에 포함되지 않으며, 03 라벨링 단계에서 `is_modeling_cycle == True`인 cycle을 기준으로 생성합니다.

| Column | Type | Description | Formula |
| --- | --- | --- | --- |
| `initial_capacity` | float | SoH 계산 기준 capacity입니다. | 초기 안정 cycle의 `capacity_ah` 평균 |
| `soh` | float | 초기 capacity 대비 현재 capacity 비율입니다. | `capacity_ah / initial_capacity` |
| `eol_threshold` | float | EOL 판정 기준입니다. | 기본값 `0.80` |
| `eol_cycle` | integer | SoH가 처음 0.80 미만이 된 global cycle입니다. | 모델링 cycle에서 최초 임계치 미만 cycle |
| `rul` | float | EOL까지 남은 global cycle 수입니다. | `eol_cycle - cycle` |
| `rul_clipped` | float | EOL 이후 음수를 0으로 제한한 RUL입니다. | `max(eol_cycle - cycle, 0)` |
| `post_eol` | boolean | EOL 이후 cycle 여부입니다. | `cycle > eol_cycle` |
| `life_stage` | string | EOL 전후 수명 구간입니다. | `pre_eol`, `eol`, `post_eol` |

`RUL`은 시계열 모델이 직접 예측하는 target이 아니라 predicted capacity에서 파생한 predicted SoH의 threshold crossing으로 계산하는 결과입니다.

## 7. 파일 사용 기준

CSV 파일은 사람이 직접 열어 값과 컬럼을 확인하기 위한 파일입니다.

Parquet 파일은 분석, 모델링, 대시보드 파이프라인에서 사용하는 파일입니다.

두 형식은 동일한 전처리 결과를 저장하며 row 수와 컬럼명이 일치해야 합니다.

이 문서는 배터리 열화 예지보전 프로젝트의 데이터 컬럼 정의를 정리한 Markdown 파일입니다.
