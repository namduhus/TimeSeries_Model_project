# 04 Capacity Fade Analysis Summary

## 1. 분석 목적

이 문서는 `notebooks/04_capacity_fade_analysis.ipynb`에서 수행한 capacity fade, SoH, RUL과 EOL 전후 열화 속도 분석 결과를 정리한 문서입니다.

입력 파일은 03 SoH/RUL 라벨링 결과입니다.

```text
data/processed/csv/battery_cycles_labeled.csv
data/processed/paraquet/battery_cycles_labeled.parquet
```

입력 데이터 크기는 다음과 같습니다.

```text
rows: 886
columns: 38
```

## 2. 분석 대상 Cycle

공식 capacity와 SoH 분석에는 `is_modeling_cycle == True`인 cycle만 사용했습니다.

| 구분 | row_count | Usage |
| --- | ---: | --- |
| modeling cycle | 868 | capacity, SoH, RUL과 slope 분석에 사용합니다. |
| excluded cycle | 18 | 그래프에서 별도 표시하고 분석 계산에서는 제외합니다. |

제외 cycle은 `nonstandard_cycle` 14개와 `invalid` 4개로 구성됩니다.

## 3. EOL 상태

EOL threshold는 SoH 80%이며, 5개 modeling cycle 연속 임계치 미만 조건을 사용합니다.

```text
eol_threshold: 0.80
eol_confirmation_cycles: 5
eol_cycle: 546
is_censored: False
```

단순 최초 threshold crossing은 cycle 127이지만 이후 SoH가 회복되므로 EOL로 사용하지 않습니다.

`CS2_35`는 관측 구간 안에서 지속 EOL 기준에 도달했으므로 censored 데이터가 아닙니다.

## 4. RUL 사용 기준

03에서 생성한 RUL은 다음과 같습니다.

```text
rul = eol_cycle - cycle
rul_clipped = max(rul, 0)
```

04에서는 RUL을 다시 계산하지 않고 라벨링 결과를 그대로 사용했습니다.

modeling cycle 기준 범위는 다음과 같습니다.

```text
rul_min: -340
rul_max: 545
rul_clipped_min: 0
rul_clipped_max: 545
```

`rul`은 EOL 이후 열화 진행 분석을 위해 음수를 유지하고, 예지보전 의사결정과 대시보드에는 `rul_clipped`를 사용합니다.

## 5. Life Stage 분류

04에서 다음 분석 컬럼을 추가했습니다.

| Column | Description |
| --- | --- |
| `post_eol` | modeling cycle 중 `cycle > 546`인 경우 `True`입니다. 제외 cycle은 결측입니다. |
| `life_stage` | `pre_eol`, `eol`, `post_eol`, `excluded` 중 하나의 분석 구간입니다. |

구간 기준은 다음과 같습니다.

```text
excluded: is_modeling_cycle == False
pre_eol:  is_modeling_cycle == True and cycle < 546
eol:      is_modeling_cycle == True and cycle == 546
post_eol: is_modeling_cycle == True and cycle > 546
```

구간별 row 수는 다음과 같습니다.

| life_stage | row_count |
| --- | ---: |
| `pre_eol` | 541 |
| `eol` | 1 |
| `post_eol` | 326 |
| `excluded` | 18 |

## 6. Capacity Fade 결과

첫 번째와 마지막 modeling cycle의 capacity는 다음과 같습니다.

```text
first_capacity: 1.138460077286744 Ah
last_capacity: 0.3036431296940698 Ah
capacity_fade_ah: -0.8348169475926741 Ah
capacity_fade_percent: -73.32860978158031%
```

마지막 modeling cycle의 capacity는 첫 modeling cycle보다 약 73.33% 감소했습니다.

SoH 범위는 다음과 같습니다.

```text
soh_min: 0.26719221094505163
soh_max: 1.001793340193135
```

## 7. EOL 전후 열화 기울기

global cycle에 대한 capacity의 단순 선형 기울기를 life stage별로 계산했습니다.

```text
pre_eol_slope:  -0.00026242876062504124 Ah/cycle
post_eol_slope: -0.001741625925232276 Ah/cycle
post_to_pre_slope_ratio: 6.636566514600565
```

전체 구간의 선형 요약 기준으로 Post-EOL capacity 감소 속도는 Pre-EOL보다 약 6.64배 큽니다.

이 비율은 각 구간을 하나의 직선으로 요약한 기술 통계이며, 국소적인 열화 속도나 인과 효과를 의미하지 않습니다.

## 8. 시각화

다음 그래프를 생성했습니다.

- life stage별 capacity fade 그래프입니다.
- SoH 80% threshold와 지속 EOL cycle 그래프입니다.
- 원본 RUL과 음수를 제거한 `rul_clipped` 비교 그래프입니다.
- excluded cycle은 capacity 그래프에 별도 marker로 표시했습니다.

## 9. 검증 결과

다음 항목을 검증했습니다.

- 입력 shape이 `(886, 38)`인지 확인했습니다.
- modeling cycle이 868개인지 확인했습니다.
- excluded cycle이 18개인지 확인했습니다.
- EOL cycle이 546인지 확인했습니다.
- life stage 수가 `541/1/326/18`인지 확인했습니다.
- excluded cycle의 `post_eol`이 결측인지 확인했습니다.
- Post-EOL modeling cycle의 `post_eol`이 모두 `True`인지 확인했습니다.
- `rul_clipped`에 음수가 없는지 확인했습니다.
- Post-EOL의 `rul_clipped`가 모두 0인지 확인했습니다.
- Post-EOL slope의 절댓값이 Pre-EOL보다 큰지 확인했습니다.

## 10. 저장 결과

사람이 확인할 CSV 파일은 다음 위치에 저장했습니다.

```text
data/processed/csv/battery_cycles_analysis.csv
```

파이프라인용 Parquet 파일은 다음 위치에 저장했습니다.

```text
data/processed/paraquet/battery_cycles_analysis.parquet
```

저장 결과는 다음과 같습니다.

```text
csv shape: (886, 40)
parquet shape: (886, 40)
```

CSV와 Parquet의 row 수와 컬럼명이 동일하며 SoH 값도 일치하는 것을 확인했습니다.

