# 03 SoH and RUL Labeling Summary

## 1. 라벨링 목적

이 문서는 `notebooks/03_soh_rul_labeling.ipynb`에서 수행한 SoH(State of Health), EOL(End of Life), RUL(Remaining Useful Life) 라벨링 결과를 정리한 문서입니다.

입력 파일은 02 cycle-level 전처리 결과입니다.

```text
data/processed/csv/battery_cycles.csv
data/processed/paraquet/battery_cycles.parquet
```

입력 데이터 크기는 다음과 같습니다.

```text
rows: 886
columns: 30
```

## 2. 모델링 Cycle 기준

03에서는 capacity와 방전시간만으로 유효 cycle을 다시 계산하지 않습니다.

02 전처리에서 생성한 `is_modeling_cycle`을 공식 라벨링 기준으로 사용합니다.

| cycle_type | row_count | SoH/RUL 라벨 사용 여부 |
| --- | ---: | --- |
| `standard_full_cycle` | 868 | 사용합니다. |
| `nonstandard_cycle` | 14 | 제외합니다. |
| `invalid` | 4 | 제외합니다. |

전체 886개 cycle 중 868개는 modeling cycle이며 18개는 제외 cycle입니다.

제외 cycle은 원본 추적을 위해 결과 파일에 유지하지만 `soh`, `rul`, `rul_clipped`는 결측으로 저장합니다.

## 3. Initial Capacity

초기 capacity는 최초 5개 modeling cycle의 `capacity_ah` 평균으로 계산했습니다.

```text
initial_capacity: 1.1364220858837624 Ah
```

초기 여러 cycle의 평균을 사용해 첫 cycle 하나의 측정 노이즈에 대한 민감도를 줄였습니다.

## 4. SoH 계산

SoH는 초기 capacity 대비 현재 capacity 비율입니다.

```text
soh = capacity_ah / initial_capacity
```

SoH는 `is_modeling_cycle == True`인 cycle에만 계산했습니다.

```text
soh_min: 0.26719221094505163
soh_max: 1.001793340193135
```

초기 SoH는 약 1.0이며 마지막 modeling cycle인 cycle 886에서는 약 0.2672입니다.

## 5. 지속 EOL 판정

EOL threshold는 SoH 80%입니다.

```text
eol_threshold: 0.80
```

SoH가 처음 80% 미만으로 내려간 cycle은 127입니다.

```text
first_below_cycle: 127
```

그러나 cycle 127 이후 SoH가 다시 약 90% 수준으로 회복되므로, cycle 127을 실제 EOL로 확정하지 않았습니다.

일시적인 급락을 EOL로 잘못 판단하지 않도록 다음 지속 조건을 적용했습니다.

```text
SoH < 0.80 for 5 consecutive modeling cycles
```

이 조건을 처음 만족하는 구간은 cycle 546부터 550까지입니다.

```text
eol_confirmation_cycles: 5
eol_cycle: 546
is_censored: False
```

따라서 `CS2_35`는 관측 구간 안에서 지속 EOL 기준에 도달한 데이터입니다.

## 6. RUL 계산

원본 분석용 RUL은 global cycle 기준으로 계산했습니다.

```text
rul = eol_cycle - cycle
```

EOL 이후 음수를 제거한 예지보전용 RUL도 함께 생성했습니다.

```text
rul_clipped = max(rul, 0)
```

예시는 다음과 같습니다.

| cycle | soh | rul | rul_clipped |
| ---: | ---: | ---: | ---: |
| 1 | 1.001793 | 545 | 545 |
| 127 | 0.793909 | 419 | 419 |
| 546 | 0.799180 | 0 | 0 |
| 886 | 0.267192 | -340 | 0 |

`rul`은 EOL 이후 열화 진행 정도를 분석하기 위해 음수 값을 유지합니다. 정비 의사결정과 대시보드에서는 음수가 없는 `rul_clipped`를 사용합니다.

RUL은 모델의 직접 target이 아니라 predicted capacity에서 파생한 predicted SoH의 EOL threshold crossing으로 계산하는 결과입니다.

## 7. 추가된 라벨 컬럼

03에서 추가한 컬럼은 다음과 같습니다.

```text
initial_capacity
soh
eol_threshold
eol_confirmation_cycles
eol_cycle
is_censored
rul
rul_clipped
```

02의 30개 컬럼에 8개 라벨 컬럼을 추가해 최종 38개 컬럼을 생성했습니다.

## 8. 검증 결과

다음 항목을 검증했습니다.

- modeling cycle 수가 868개인지 확인했습니다.
- 제외 cycle 수가 18개인지 확인했습니다.
- 제외 cycle의 SoH와 RUL이 모두 결측인지 확인했습니다.
- initial capacity가 약 1.1364Ah인지 확인했습니다.
- cycle 127이 일시적인 최초 threshold crossing인지 확인했습니다.
- 지속 EOL cycle이 546인지 확인했습니다.
- cycle 546의 RUL과 `rul_clipped`가 0인지 확인했습니다.
- EOL 이후 모든 modeling cycle의 `rul_clipped`가 0인지 확인했습니다.
- `rul_clipped`에 음수가 없는지 확인했습니다.

## 9. 저장 결과

사람이 확인할 CSV 파일은 다음 위치에 저장했습니다.

```text
data/processed/csv/battery_cycles_labeled.csv
```

파이프라인용 Parquet 파일은 다음 위치에 저장했습니다.

```text
data/processed/paraquet/battery_cycles_labeled.parquet
```

저장 결과는 다음과 같습니다.

```text
csv shape: (886, 38)
parquet shape: (886, 38)
```

CSV와 Parquet의 row 수와 컬럼명이 동일하며 SoH 값도 일치하는 것을 확인했습니다.
