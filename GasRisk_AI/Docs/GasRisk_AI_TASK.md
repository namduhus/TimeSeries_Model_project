# GasRisk AI 개발 TASK 정리

## 0. 현재 데이터 확보 상태

현재 확보한 데이터는 **1~5번, 8번, 10번** 중심이며, **6번, 7번, 9번, 11~18번은 제외**한 상태이다.

| 번호 | 데이터 | 상태 | 활용 방향 |
| :---: | :--- | :---: | :--- |
| 1 | 한국가스안전공사_가스사고 현황(월별 원인별) | 확보 | 시계열 예측 Target, 사고 추세 분석 |
| 2 | 한국가스안전공사_가스사고 신고 접수 현황 | 확보 | 신고 패턴 분석, 위험도 보정 Feature |
| 3 | 한국가스안전공사_국내 가스시설 현황 | 확보 | 지역별 시설 밀도, 위험 노출도 산출 |
| 4 | 한국가스안전공사_전국 LPG 충전소 현황 | 확보 | LPG 충전소 공간 Feature, GIS 위험지도 |
| 5 | 한국가스안전공사_전국 도시가스/CNG 충전소 현황 | 확보 | CNG 충전소 공간 Feature, GIS 위험지도 |
| 6 | 수소충전소 현황 | 제외 | 추후 신에너지 시설 위험도 확장 가능 |
| 7 | 도시가스특정사용시설 통계 | 제외 | 추후 고사용량 시설 밀도 Feature 확장 가능 |
| 8 | 기상청 기상자료 | 확보 | 기온, 강수, 습도, 풍속 기반 외생변수 |
| 9 | 노후건물정보 | 제외 | 건축물대장으로 일부 대체 |
| 10 | 국토교통부 건축물대장 | 확보 | 건물 사용연수, 용도, 노후도 Feature |
| 11~18 | 상권, 인구, 사고연감, 예방사례집, 점검통계 등 | 제외 | 추후 LLM/RAG 및 보정 Feature로 확장 가능 |

---

## 1. MVP 목표 재정의

### 1.1 제품 목표

**GasRisk AI는 한국가스안전공사의 사고·신고·시설 공공데이터와 기상·건축물 데이터를 결합하여 지역별 가스 사고 위험도를 예측하고, 시민이 사진과 신고 문장을 입력하면 AI가 위험 의심 요소와 신고서 초안을 생성하는 Web 기반 서비스이다.**

### 1.2 현재 데이터 기준 MVP 범위

현재 확보 데이터 기준으로는 다음 범위까지 구현한다.

| 구분 | 구현 범위 |
| :--- | :--- |
| 지역 위험 예측 | 사고·신고 이력 기반 다음 달 위험도 예측 |
| 시설 위험 반영 | 국내 가스시설, LPG 충전소, CNG 충전소 밀도 반영 |
| 기상 위험 반영 | 평균기온, 최저기온, 최고기온, 강수량, 습도, 풍속 반영 |
| 건축물 취약성 반영 | 건축물대장 기반 건물 노후도, 용도 분포 반영 |
| AI 신고 지원 | OpenAI Vision + LLM 기반 사진 분석 및 신고서 초안 생성 |
| Web 시연 | 시민용 Web + 관리자 Dashboard 형태로 시연 |

---

## 2. 최종 산출물

| 산출물 | 설명 | 파일/화면 예시 |
| :--- | :--- | :--- |
| 데이터 인벤토리 | 확보 데이터별 파일명, 컬럼, 시간·지역 단위 정리 | `docs/data_inventory.md` |
| 정제 데이터 | 원천 데이터를 표준 컬럼명과 지역/월 기준으로 정리 | `data/processed/*.csv` |
| 지역-월 통합 데이터셋 | 모델 입력용 최종 패널 데이터 | `gasrisk_region_month_dataset.csv` |
| EDA 결과 | 사고·신고·기상·시설·건축물 관계 분석 | `notebooks/01_eda.ipynb`, `reports/eda_summary.md` |
| 시계열 예측 결과 | TimesFM 기반 다음 달 사고·신고 예측값 | `forecast_results.csv` |
| 위험점수 결과 | 지역별 GasRisk Score 및 위험등급 | `gasrisk_score_results.csv` |
| Backend API | 위험도, 예측, 이미지 분석, 신고서 생성 API | FastAPI |
| Frontend Web | 위험지도, 지역 상세, 사진 점검, 신고 도우미 | React/Vue/Next |
| 발표용 데모 | 실제 데이터 기반 Web 시연 플로우 | 데모 시나리오 문서 |

---

## 3. 전체 개발 순서

가장 안전한 개발 순서는 다음과 같다.

```text
1단계: 데이터 인벤토리 정리
2단계: 데이터 전처리 및 지역/월 단위 정규화
3단계: 지역-월 통합 데이터셋 구축
4단계: EDA 및 문제 검증
5단계: Rule-based GasRisk Score 먼저 산출
6단계: Web 대시보드 기본 구현
7단계: TimesFM 예측값 추가
8단계: OpenAI Vision/LLM 신고 지원 기능 추가
9단계: 관리자 리포트 및 발표용 데모 정리
```

처음부터 TimesFM에 의존하기보다, **Rule-based Score로 Web MVP를 먼저 띄운 뒤 TimesFM 예측값을 붙이는 방식**이 안정적이다.

---

# Phase 1. 데이터 인벤토리 정리

## 목적

가져온 데이터의 파일명, 컬럼, 시간 단위, 지역 단위, 결측 여부를 먼저 파악한다.

## TASK

| ID | Task | 설명 | 우선순위 | 산출물 |
| :--- | :--- | :--- | :---: | :--- |
| T1-1 | 데이터 파일 목록 정리 | 확보한 데이터 파일명, 형식, 출처, 업데이트 기준 정리 | P0 | `docs/data_inventory.md` |
| T1-2 | 컬럼 스키마 확인 | 각 데이터의 컬럼명, 데이터 타입, 결측률 확인 | P0 | `data/schema_summary.csv` |
| T1-3 | 시간 단위 확인 | 월별/일별/연도별/현재시점 데이터 구분 | P0 | 인벤토리 표 |
| T1-4 | 지역 단위 확인 | 시도, 시군구, 주소, 좌표, 지사 단위 구분 | P0 | 인벤토리 표 |
| T1-5 | 데이터 활용 가능성 판정 | 모델링에 바로 쓸 수 있는 데이터와 보조 데이터 분류 | P0 | 활용 가능성 컬럼 |

## 데이터 인벤토리 작성 항목

| 항목 | 설명 |
| :--- | :--- |
| 파일명 | 실제 저장된 파일명 |
| 제공기관 | 한국가스안전공사, 기상청, 국토교통부 등 |
| 데이터셋명 | 공공데이터포털 기준 데이터명 |
| 파일 형식 | CSV, XLSX, JSON 등 |
| 주요 컬럼 | 모델링에 필요한 주요 컬럼 |
| 날짜 컬럼 | 사고일자, 신고일자, 기준월 등 |
| 지역 컬럼 | 시도, 시군구, 주소, 관할지사 등 |
| 좌표 컬럼 | 위도, 경도 존재 여부 |
| 모델링 활용 여부 | Target, Feature, GIS, LLM 등 |

---

# Phase 2. 데이터 전처리

## 2.1 공통 전처리

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T2-1 | 컬럼명 표준화 | 한글 컬럼명을 영문 snake_case로 변환 | P0 |
| T2-2 | 날짜 컬럼 정규화 | 사고일자, 신고일자, 기준월을 `YYYY-MM` 형식으로 변환 | P0 |
| T2-3 | 지역명 정규화 | 시도/시군구명을 행정구역 표준명으로 통일 | P0 |
| T2-4 | 주소 파싱 | 주소가 있는 경우 시도/시군구 추출 | P0 |
| T2-5 | 결측치 처리 | 사고·신고 건수 결측은 0, 시설 정보 결측은 별도 플래그 처리 | P0 |
| T2-6 | 중복 제거 | 동일 사고, 동일 신고, 동일 시설 중복 제거 | P0 |

## 2.2 데이터별 전처리

### 2.2.1 가스사고 현황 월별 원인별

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T2-7 | 사고 월 생성 | 사고 발생 기준 `year_month` 생성 | P0 |
| T2-8 | 사고 유형 분리 | LPG, 도시가스, 고압가스 등 가스 종류 컬럼 정리 | P0 |
| T2-9 | 원인별 사고 건수 집계 | 사용자부주의, 시설미비, 제품불량 등 원인별 집계 | P1 |
| T2-10 | 지역-월 사고 건수 생성 | `region_code + year_month` 기준 사고 건수 산출 | P0 |

### 2.2.2 가스사고 신고 접수 현황

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T2-11 | 신고일자 정규화 | 접수일자 기준 `year_month` 생성 | P0 |
| T2-12 | 사고 발생주소 파싱 | 주소에서 시도/시군구 추출 | P0 |
| T2-13 | 신고 건수 집계 | 지역-월 단위 신고 건수 생성 | P0 |
| T2-14 | 신고 증가율 계산 | 최근 3개월 신고 증가율 Feature 생성 | P1 |

### 2.2.3 국내 가스시설 현황

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T2-15 | 시설 종류 분류 | LPG, 도시가스, 고압가스, 시공업소 등 분류 | P0 |
| T2-16 | 지역별 시설 수 집계 | 시도/시군구별 시설 수 생성 | P0 |
| T2-17 | 시설 밀도 계산 | 지역 면적 또는 건축물 수 대비 시설 밀도 계산 | P1 |

### 2.2.4 LPG / CNG 충전소 현황

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T2-18 | 좌표 컬럼 정리 | 위도/경도 좌표 표준화 | P0 |
| T2-19 | 주소 기반 지역 매핑 | 주소에서 시도/시군구 추출 | P0 |
| T2-20 | 충전소 개수 집계 | 지역별 LPG, CNG 충전소 수 계산 | P0 |
| T2-21 | GIS용 GeoJSON 생성 | 지도 시각화를 위한 충전소 위치 데이터 생성 | P1 |

### 2.2.5 기상청 기상자료

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T2-22 | 관측소-지역 매핑 | 기상 관측소를 시군구 또는 시도에 매핑 | P0 |
| T2-23 | 월별 기상 집계 | 평균기온, 최저기온, 최고기온, 강수량, 습도, 풍속 집계 | P0 |
| T2-24 | 기상위험지수 생성 | `weather_risk_index` 생성 | P1 |

### 2.2.6 건축물대장

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T2-25 | 사용승인일 정리 | 사용승인일 또는 건축연도 추출 | P0 |
| T2-26 | 노후건축물 여부 생성 | 20년 이상, 30년 이상 건축물 플래그 생성 | P0 |
| T2-27 | 건물 용도 분류 | 단독주택, 공동주택, 근린생활시설, 숙박, 공장 등 분류 | P1 |
| T2-28 | 지역별 노후도 집계 | 지역별 평균 건축연수, 30년 이상 건물 비율 계산 | P0 |

---

# Phase 3. 지역-월 통합 데이터셋 구축

## 목적

모델 입력으로 사용할 최종 테이블을 만든다.

## 기준 단위

```text
region_code + year_month
```

## TASK

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T3-1 | 기준 지역 목록 생성 | 분석 대상 시도/시군구 마스터 생성 | P0 |
| T3-2 | 기준 월 목록 생성 | 사고 데이터 기간 기준 월 목록 생성 | P0 |
| T3-3 | 사고 데이터 병합 | 지역-월 사고 건수 병합 | P0 |
| T3-4 | 신고 데이터 병합 | 지역-월 신고 건수 병합 | P0 |
| T3-5 | 시설 데이터 병합 | 지역별 시설 수 및 밀도 병합 | P0 |
| T3-6 | 충전소 데이터 병합 | LPG/CNG 충전소 수 및 밀도 병합 | P0 |
| T3-7 | 기상 데이터 병합 | 지역-월 기상 Feature 병합 | P0 |
| T3-8 | 건축물 데이터 병합 | 지역별 노후건물 비율 병합 | P0 |
| T3-9 | 결측 월 보정 | 사고/신고가 없는 월은 0으로 보정 | P0 |
| T3-10 | 최종 학습 테이블 저장 | `gasrisk_region_month_dataset.csv` 생성 | P0 |

## 최종 통합 테이블 핵심 컬럼

| 컬럼명 | 설명 |
| :--- | :--- |
| `region_code` | 행정구역 코드 |
| `region_name` | 지역명 |
| `year_month` | 기준 월 |
| `gas_accident_count` | 해당 월 가스 사고 건수 |
| `gas_report_count` | 해당 월 신고 접수 건수 |
| `lpg_accident_count` | LPG 사고 건수 |
| `citygas_accident_count` | 도시가스 사고 건수 |
| `facility_count_total` | 가스시설 총량 |
| `facility_density` | 면적 또는 건축물 수 대비 가스시설 밀도 |
| `lpg_station_count` | 지역 내 LPG 충전소 수 |
| `cng_station_count` | 지역 내 도시가스/CNG 충전소 수 |
| `total_gas_station_count` | LPG + CNG 충전소 총합 |
| `gas_station_density` | 면적 또는 건축물 수 대비 가스충전소 밀도 |
| `avg_temp_month` | 월평균 기온 |
| `min_temp_month` | 해당 월 최저기온 |
| `max_temp_month` | 해당 월 최고기온 |
| `rainfall_total_month` | 월 누적 강수량 |
| `avg_humidity_month` | 월평균 습도 |
| `avg_wind_speed_month` | 월평균 풍속 |
| `weather_risk_index` | 기상 위험 종합지수 |
| `building_age_avg` | 지역별 평균 건축연수 |
| `old_building_ratio` | 30년 이상 노후건축물 비율 |
| `predicted_accident_count` | TimesFM 기반 다음 달 사고 예측 건수 |
| `predicted_report_count` | TimesFM 기반 다음 달 신고 예측 건수 |
| `risk_score` | 최종 GasRisk Score |
| `risk_level` | 낮음 / 주의 / 위험 / 고위험 |

---

# Phase 4. EDA 및 문제 검증

## 목적

“가스 사고 위험 예측이 가능한 문제인가?”를 데이터로 확인한다.

## TASK

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T4-1 | 사고 건수 추세 분석 | 월별 전체 사고 추세 확인 | P0 |
| T4-2 | 지역별 사고 분포 분석 | 사고가 많은 지역과 적은 지역 확인 | P0 |
| T4-3 | 신고와 사고 관계 분석 | 신고 증가가 사고 위험과 관련 있는지 확인 | P0 |
| T4-4 | 기상 변수와 사고 관계 분석 | 한파, 폭염, 강수와 사고 발생 관계 확인 | P1 |
| T4-5 | 시설 밀도와 사고 관계 분석 | 시설 수가 많은 지역의 사고 위험 확인 | P1 |
| T4-6 | 건축물 노후도와 사고 관계 분석 | 노후도와 사고/신고 관계 확인 | P1 |
| T4-7 | 데이터 희소성 분석 | 지역-월 단위에서 사고 0건 비율 확인 | P0 |
| T4-8 | 예측 가능성 판단 | 시계열 예측이 유효한지 베이스라인으로 검증 | P0 |

## 산출물

```text
notebooks/01_eda.ipynb
reports/eda_summary.md
```

---

# Phase 5. 시계열 예측 모델링

## 목표

TimesFM으로 다음 달 지역별 사고 건수와 신고 건수를 예측한다.

## TASK

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T5-1 | 지역별 사고 시계열 생성 | `region_code`별 `gas_accident_count` 시계열 생성 | P0 |
| T5-2 | 지역별 신고 시계열 생성 | `region_code`별 `gas_report_count` 시계열 생성 | P0 |
| T5-3 | Naive baseline 구축 | 직전 월 값 기반 예측 | P0 |
| T5-4 | Moving Average baseline 구축 | 최근 3개월/6개월 평균 기반 예측 | P0 |
| T5-5 | Prophet baseline 구축 | 계절성 있는 베이스라인 모델 | P1 |
| T5-6 | TimesFM 예측 실행 | 다음 1개월 또는 3개월 예측 | P0 |
| T5-7 | 예측 성능 평가 | MAE, RMSE, Direction Accuracy 계산 | P0 |
| T5-8 | 예측 결과 저장 | `forecast_results.csv` 생성 | P0 |

## 예측 Target

가스 사고는 희소 이벤트일 가능성이 높기 때문에, 사고 건수만 예측하지 않고 신고 건수도 함께 예측한다.

```text
1. gas_accident_count
2. gas_report_count
```

## 평가 지표

| 지표 | 설명 |
| :--- | :--- |
| MAE | 예측 사고·신고 건수의 평균 절대 오차 |
| RMSE | 큰 오차에 민감한 예측 성능 지표 |
| MAPE | 실제값 대비 예측 오차율 |
| Direction Accuracy | 사고·신고 증가/감소 방향을 맞춘 비율 |

---

# Phase 6. GasRisk Score 산출

## 목표

TimesFM 예측값과 시설·기상·건축물 Feature를 결합해 지역별 위험점수를 만든다.

## TASK

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T6-1 | Rule-based Score 설계 | MVP용 위험점수 산식 정의 | P0 |
| T6-2 | Feature 정규화 | MinMax 또는 percentile 기반 정규화 | P0 |
| T6-3 | GasRisk Score 계산 | 0~100 점수 산출 | P0 |
| T6-4 | 위험등급 구간 설정 | 낮음/주의/위험/고위험 구간 정의 | P0 |
| T6-5 | Top Risk Factors 생성 | 위험점수에 기여한 상위 변수 추출 | P0 |
| T6-6 | LightGBM 모델 실험 | 데이터가 충분할 경우 위험도 보정 모델 학습 | P1 |
| T6-7 | SHAP/Feature Importance 계산 | 관리자 리포트용 설명 변수 생성 | P1 |
| T6-8 | 최종 결과 저장 | `gasrisk_score_results.csv` 생성 | P0 |

## 초기 MVP 위험점수 산식

현재 제외 데이터가 있으므로 상권·인구·점검 커버리지는 초기 산식에서 제외한다.

```text
GasRiskScore =
  0.25 * predicted_accident_score
+ 0.20 * predicted_report_score
+ 0.15 * report_increase_score
+ 0.15 * facility_density_score
+ 0.10 * gas_station_density_score
+ 0.10 * weather_risk_score
+ 0.05 * old_building_score
```

## 위험등급 기준

| GasRisk Score | 위험등급 | 설명 |
| :---: | :--- | :--- |
| 0~30 | 낮음 | 일반적인 수준의 위험 |
| 31~60 | 주의 | 일부 위험 요인 상승 |
| 61~80 | 위험 | 사고·신고 증가 가능성과 취약 요인이 복합적으로 존재 |
| 81~100 | 고위험 | 선제 점검 및 즉각적인 안내가 필요한 지역 |

---

# Phase 7. OpenAI Vision + LLM 기능

## 목표

시민이 사진과 신고 문장을 입력하면 AI가 위험 의심 요소와 신고서 초안을 생성한다.

## TASK

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T7-1 | Vision 프롬프트 설계 | 계량기, 배관, 밸브, LPG/CNG 시설 분석 프롬프트 작성 | P0 |
| T7-2 | 이미지 분석 API 구현 | 사진 업로드 후 OpenAI Vision 호출 | P0 |
| T7-3 | 분석 결과 JSON 스키마 정의 | 시설유형, 위험의심요소, 주변환경, 긴급도 | P0 |
| T7-4 | 신고 문장 구조화 프롬프트 설계 | 위치, 시간, 냄새, 시설유형, 긴급도 추출 | P0 |
| T7-5 | 신고서 초안 생성 | Vision 결과 + 사용자 설명 기반 신고서 생성 | P0 |
| T7-6 | 안전 고지 문구 삽입 | AI 판정이 아니라 위험 의심 분석임을 명시 | P0 |
| T7-7 | 관리자 리포트 프롬프트 설계 | GasRisk Score 기반 위험 원인 설명 생성 | P1 |

## Vision 출력 JSON 예시

```json
{
  "facility_type": "가스 계량기",
  "suspected_risk_factors": [
    "배관 연결부 노후 의심",
    "주변 장애물 존재"
  ],
  "environment": "실외",
  "urgency_level": "주의",
  "recommended_actions": [
    "화기 사용을 중단하세요",
    "환기 가능한 경우 환기하세요",
    "전문기관 점검을 요청하세요"
  ],
  "disclaimer": "본 결과는 AI가 사진에서 식별한 위험 의심 요소입니다. 실제 안전 여부는 전문기관 점검이 필요합니다."
}
```

---

# Phase 8. Backend 개발

## 추천 구조

```text
backend/
  app/
    main.py
    api/
      risk.py
      forecast.py
      vision.py
      report.py
      admin.py
    services/
      risk_service.py
      forecast_service.py
      openai_service.py
    schemas/
      risk_schema.py
      report_schema.py
    db/
      session.py
      models.py
  data/
  pyproject.toml
```

## TASK

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T8-1 | FastAPI 프로젝트 생성 | 기본 API 서버 구성 | P0 |
| T8-2 | 데이터 로딩 서비스 구현 | CSV 또는 DB에서 위험도 결과 로딩 | P0 |
| T8-3 | 지역별 위험도 API | `/api/risk/regions` | P0 |
| T8-4 | 지역 상세 API | `/api/risk/region/{region_id}` | P0 |
| T8-5 | 예측 그래프 API | `/api/forecast/{region_id}` | P0 |
| T8-6 | 이미지 분석 API | `/api/image/analyze` | P0 |
| T8-7 | 신고서 생성 API | `/api/report/draft` | P0 |
| T8-8 | 관리자 랭킹 API | `/api/admin/ranking` | P0 |
| T8-9 | 관리자 리포트 API | `/api/admin/report` | P1 |
| T8-10 | CORS/환경변수 설정 | Web 연동 및 OpenAI Key 관리 | P0 |

---

# Phase 9. Frontend Web 개발

## 화면 구성

| 화면 | 사용자 | 우선순위 | 설명 |
| :--- | :--- | :---: | :--- |
| 메인 대시보드 | 시민/관리자 | P0 | 현재 지역 위험도, 빠른 실행 버튼 |
| 위험지도 | 시민/관리자 | P0 | 지역별 위험등급 지도 시각화 |
| 지역 상세 페이지 | 시민/관리자 | P0 | 사고/신고 추세, 예측값, 위험 원인 |
| 사진 자가점검 페이지 | 시민 | P0 | 사진 업로드, AI 분석 결과 표시 |
| AI 신고 도우미 | 시민 | P0 | 자연어 신고 입력, 신고서 초안 생성 |
| 관리자 대시보드 | 지자체/관리자 | P1 | 위험지역 TOP 10, 점검 우선순위 |
| 관리자 리포트 페이지 | 지자체/관리자 | P1 | LLM 기반 월간 위험 분석 리포트 |

## TASK

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T9-1 | Frontend 프로젝트 생성 | React/Vue/Next 중 선택 | P0 |
| T9-2 | 레이아웃 구성 | Header, Sidebar, Main Panel | P0 |
| T9-3 | 위험지도 구현 | 지도에 지역별 위험등급 표시 | P0 |
| T9-4 | 위험도 카드 구현 | 현재 지역 위험점수, 등급 표시 | P0 |
| T9-5 | 시계열 그래프 구현 | 사고/신고 추세 및 예측값 시각화 | P0 |
| T9-6 | 사진 업로드 UI 구현 | 이미지 업로드 및 미리보기 | P0 |
| T9-7 | Vision 분석 결과 UI | 위험 의심 요소, 행동요령 표시 | P0 |
| T9-8 | 신고 문장 입력 UI | 자연어 상황 설명 입력 | P0 |
| T9-9 | 신고서 초안 UI | 생성된 신고서 복사 기능 | P0 |
| T9-10 | 관리자 랭킹 테이블 | 위험지역 TOP 10 표시 | P1 |
| T9-11 | 발표용 데모 시나리오 UI 정리 | 클릭 흐름 최소화 | P0 |

---

# Phase 10. 발표용 데모 구성

## 데모 흐름

```text
1. 메인 화면 접속
2. 특정 지역 선택
3. 지역 위험도 확인
4. 사고/신고 예측 그래프 확인
5. 위험 원인 요약 확인
6. 가스 계량기 또는 배관 사진 업로드
7. AI 위험 의심 요소 분석 결과 확인
8. 신고 문장 입력
9. 신고서 초안 생성
10. 관리자 화면에서 위험지역 TOP 10 확인
```

## TASK

| ID | Task | 설명 | 우선순위 |
| :--- | :--- | :--- | :---: |
| T10-1 | 데모 지역 선정 | 데이터가 풍부하고 위험도가 잘 나오는 지역 선택 | P0 |
| T10-2 | 샘플 이미지 준비 | 계량기, 배관, LPG 용기 이미지 3~5장 준비 | P0 |
| T10-3 | 샘플 신고 문장 준비 | 발표 중 입력할 문장 준비 | P0 |
| T10-4 | 데모용 예측 결과 고정 | 발표 중 API 불안정 방지를 위해 일부 결과 캐싱 | P0 |
| T10-5 | 발표 시나리오 문서화 | 3분/5분 시연 흐름 정리 | P0 |

---

# 11. 이번 주 바로 해야 할 P0 작업

| 순서 | Task | 결과물 |
| :---: | :--- | :--- |
| 1 | 데이터 파일 목록과 컬럼 확인 | `data_inventory.md` |
| 2 | 지역명/날짜 컬럼 정규화 | 전처리 스크립트 |
| 3 | 사고·신고 데이터 지역-월 집계 | `accident_report_monthly.csv` |
| 4 | 시설·충전소 데이터 지역 집계 | `facility_region.csv` |
| 5 | 기상자료 월별 집계 | `weather_region_monthly.csv` |
| 6 | 건축물대장 노후도 집계 | `building_region.csv` |
| 7 | 지역-월 통합 테이블 생성 | `gasrisk_region_month_dataset.csv` |
| 8 | EDA 노트북 작성 | `01_eda.ipynb` |
| 9 | Rule-based GasRisk Score 먼저 산출 | `gasrisk_score_results.csv` |
| 10 | Web에 올릴 결과 JSON 생성 | `risk_regions.json` |

---

# 12. 권장 프로젝트 디렉터리 구조

```text
gasrisk-ai/
  README.md
  docs/
    data_inventory.md
    task_plan.md
    api_spec.md
  data/
    raw/
    interim/
    processed/
    outputs/
  notebooks/
    01_eda.ipynb
    02_forecasting_timesfm.ipynb
    03_risk_score.ipynb
  backend/
    app/
      main.py
      api/
      services/
      schemas/
      db/
    pyproject.toml
  frontend/
    src/
  scripts/
    preprocess/
    modeling/
    export/
```

---

# 13. 최종 요약

현재 확보한 데이터만으로도 GasRisk AI MVP는 충분히 구현 가능하다.

초기 버전은 **사고·신고 이력 + 가스시설 밀도 + LPG/CNG 충전소 공간정보 + 기상자료 + 건축물대장 기반 노후도**를 결합하여 `GasRisk Score`를 산출한다.

개발은 다음 순서로 진행하는 것이 가장 안전하다.

```text
데이터 인벤토리
→ 전처리
→ 지역-월 통합 데이터셋
→ EDA
→ Rule-based GasRisk Score
→ Web 대시보드
→ TimesFM 예측
→ OpenAI Vision/LLM 신고 지원
→ 발표용 데모 정리
```
