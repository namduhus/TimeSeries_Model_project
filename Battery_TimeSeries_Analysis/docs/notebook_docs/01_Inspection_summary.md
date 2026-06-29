# 01 Raw Data Inspection Summary

## 1. Inspection Target

이 문서는 `notebooks/01_raw_data_inspection.ipynb`에서 확인한 CALCE `CS2_35` 원본 데이터 점검 결과를 정리한 문서입니다.

점검 대상 원본 폴더는 다음과 같습니다.

```text
data/raw/calce/CS2/CS2_35/
```

## 2. Raw File Check

`CS2_35` 원본 폴더에서 Excel 파일 25개를 확인했습니다.

노트북에서는 `sorted()` 기준 첫 번째 파일을 샘플로 사용했습니다.

샘플 파일은 다음과 같습니다.

```text
CS2_35_10_15_10.xlsx
```

주의할 점은 `sorted()`가 문자열 정렬이므로 실제 실험 날짜순 정렬과 다를 수 있다는 점입니다. 전체 전처리 단계에서는 파일명에서 날짜를 파싱해 시간순으로 정렬하는 방식이 필요합니다.

## 3. Sheet Check

샘플 Excel 파일의 시트는 다음과 같습니다.

```text
Info
Channel_1-008
```

실제 측정 데이터는 `Channel_1-008` 시트에 있습니다.

샘플 시트의 데이터 크기는 다음과 같습니다.

```text
rows: 17139
columns: 17
```

## 4. Raw Column Check

샘플 파일에서 확인한 원본 컬럼은 다음과 같습니다.

```text
Data_Point
Test_Time(s)
Date_Time
Step_Time(s)
Step_Index
Cycle_Index
Current(A)
Voltage(V)
Charge_Capacity(Ah)
Discharge_Capacity(Ah)
Charge_Energy(Wh)
Discharge_Energy(Wh)
dV/dt(V/s)
Internal_Resistance(Ohm)
Is_FC_Data
AC_Impedance(Ohm)
ACI_Phase_Angle(Deg)
```

1차 전처리에 필요한 핵심 컬럼은 모두 존재했습니다.

핵심 컬럼은 다음과 같습니다.

```text
Cycle_Index
Test_Time(s)
Step_Time(s)
Current(A)
Voltage(V)
Charge_Capacity(Ah)
Discharge_Capacity(Ah)
```

핵심 컬럼의 결측치는 확인되지 않았습니다.

데이터 타입은 `Cycle_Index`가 정수형이고, 나머지 핵심 수치 컬럼은 실수형입니다.

## 5. Cycle-Level Summary Check

샘플 파일을 `Cycle_Index` 기준으로 집계했을 때 cycle 수는 50개입니다.

cycle-level 요약에서 확인한 주요 값은 다음과 같습니다.

| Column | Meaning |
| --- | --- |
| `row_count` | cycle별 row 수입니다. |
| `test_time_min` | cycle별 최소 누적 테스트 시간입니다. |
| `test_time_max` | cycle별 최대 누적 테스트 시간입니다. |
| `voltage_mean` | cycle별 평균 전압입니다. |
| `voltage_min` | cycle별 최소 전압입니다. |
| `voltage_max` | cycle별 최대 전압입니다. |
| `current_mean` | cycle별 평균 전류입니다. |
| `charge_capacity_max` | cycle별 최대 충전 capacity입니다. |
| `discharge_capacity_max` | cycle별 최대 방전 capacity입니다. |

## 6. Capacity Interpretation

중요한 확인 결과는 `Discharge_Capacity(Ah)`가 cycle마다 reset되는 값이 아니라, 샘플 파일 안에서 누적 증가하는 값이라는 점입니다.

샘플 결과 일부는 다음과 같습니다.

| Cycle_Index | discharge_capacity_max | discharge_capacity_diff |
| --- | ---: | ---: |
| 1 | 1.041556 | 1.041556 |
| 2 | 2.085898 | 1.044342 |
| 3 | 3.133029 | 1.047132 |
| 4 | 4.180907 | 1.047877 |
| 5 | 5.228866 | 1.047960 |
| 6 | 6.276477 | 1.047611 |
| 7 | 7.324014 | 1.047537 |
| 8 | 8.371716 | 1.047702 |
| 9 | 9.419002 | 1.047286 |
| 10 | 10.465630 | 1.046629 |

따라서 1차 전처리에서 `capacity_ah`는 `discharge_capacity_max`를 그대로 사용하지 않고, cycle 간 차분값으로 계산해야 합니다.

계산 방향은 다음과 같습니다.

```text
capacity_ah = discharge_capacity_max.diff()
```

첫 번째 cycle은 이전 cycle이 없으므로, 첫 번째 `discharge_capacity_max`를 그대로 사용할 수 있습니다.

