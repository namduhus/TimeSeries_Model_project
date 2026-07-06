# 유해남조류(녹조) 조기경보 — 오픈소스 시계열 예측 파이프라인

공개 데이터만으로 **다음 측정 시점(≈ +7일)에 유해남조류 세포수가 관심 단계(1,000 cells/mL)를 초과할지**를 예측하는, 누수 없이 재현 가능한 이진 조기경보 파이프라인.

> 관(官)의 조류경보제 예측 로직은 비공개다. 이 프로젝트는 공개 데이터·공개 코드로 재현·확장·검증 가능한 **의사결정 지원 도구**를 지향한다. (공식 경보 대체 아님)

## 핵심 결과 (시간순 CV, 베이스라인 대비)

| 방법 | PR-AUC | Recall@P0.5 | ROC-AUC |
|---|---|---|---|
| **LightGBM** | **0.807** | **0.905** | 0.962 |
| persistence(현재 상태 유지) | 0.751 | 0.835 | 0.919 |
| 계절 규칙 | 0.263 | 0.000 | 0.745 |

정밀도 50%에서 초과 이벤트의 **약 90%를 일주일 앞서 포착**. 학습에 없던 지점 일반화도 양호(PR-AUC 0.785). 전 과정 누수 방지를 코드·테스트로 강제.

## 데이터

| 소스 | 내용 | 라이선스 |
|---|---|---|
| 국립환경과학원 조류경보제 조회서비스 (data.go.kr 15126738) | 수온·pH·DO·탁도·클로로필·유해남조류 세포수(속별) 등 | 공공누리 제1유형(출처표시) |
| 물환경정보시스템 파일(water.nier.go.kr) | 위와 동일 원천(교차검증용) | 공공데이터 |
| 기상청 지상(ASOS) 일자료 (data.go.kr) | 기온·강수·풍속·일사 등 (외생변수, 확장) | 공공데이터 |

- **인증키:** `.env.example`를 `.env`로 복사 후 `DATA_GO_KR_SERVICE_KEY`(공공데이터포털 디코딩 키) 입력. data.go.kr 계정 키 하나가 활용신청한 전 서비스에 공통.
- **원자료는 저장소에 포함하지 않는다**(`data/` gitignore). 아래 취득 스크립트로 재생성.

## 설치

```bash
uv sync            # 의존성 설치 (Python 3.13+)
cp .env.example .env   # 인증키 입력
```

## 재현 (파이프라인)

```bash
# 1) 데이터 취득 (조류 전 지점·전월)
uv run python scripts/fetch_algae.py --start-year 2015 --end-year 2026

# 2) F2 데이터 감사 → reports/f2_audit.md
uv run python -m src.audit

# 3) F3 EDA → reports/figures/ (또는 notebooks/eda_algae.ipynb)
uv run python -m src.eda

# 4) F5 타깃 생성 → data/interim/targets.csv
uv run python -m src.target

# 5) F4 피처 → data/interim/dataset.csv
uv run python -m src.features

# 6) F6+F7 모델·검증 → reports/model_eval.md, reports/figures/모델_*.png
#    + 게시용 모델 저장 → models/algae_lgbm.txt, models/model_card.json
uv run python -m src.modeling

# 7) F8 해석·예측 리포트 → reports/figures/shap_*.png, reports/predictions_sample.csv
uv run python -m src.reporting

# 8) F6b 다중분류(경보 단계) → reports/model_multiclass.md, figures/모델_혼동행렬.png
#    + 단계 서빙 모델 게시 → models/algae_lgbm_ge10000.txt, stage_model_card.json
uv run python -m src.multiclass

# 9) 확장3 딥러닝 벤치마크(GBDT vs MLP·FT-Transformer) → reports/model_dl_benchmark.md
uv run python -m src.benchmark_dl --device cpu   # 재현용 CPU (개발 속도는 --device mps)
```

## 대시보드 (확장4)

지점·기준일을 고르면 게시된 LightGBM 단계 모델로 다음 측정 시점의 경보 단계(정상/관심/경계이상)를 예측한다.

```bash
uv run streamlit run app.py    # 사전: 위 6·8단계로 models/ 게시 모델 생성
```

통합 서사: `notebooks/results.ipynb` (EDA→평가→SHAP→예측).

## 게시 모델 사용

전체 데이터로 학습한 예측 모델 가중치와 메타데이터(`model_card.json`: 피처·파라미터·CV지표·데이터출처)를 `models/`에 공개한다. 재학습 없이 로드해 예측할 수 있다.

```python
from src.modeling import load_model, prep_X
from src.features import assemble_dataset

booster, card = load_model()                 # models/algae_lgbm.txt + model_card.json
X = prep_X(assemble_dataset(), card["features"])
proba = booster.predict(X)                    # 다음 측정 시점 임계 초과 확률
```

## 저장소 구조

```
src/
├─ loading.py     # F1 로딩·정규화 (조류 API/파일, 기상 ASOS, 지점 마스터)
├─ audit.py       # F2 데이터 감사
├─ eda.py         # F3 탐색적 분석(그림)
├─ target.py      # F5 타깃 생성 (누수 안전)
├─ features.py    # F4 피처 엔지니어링 (누수 안전)
├─ validation.py  # F7 시간순/지점 분할·지표·베이스라인
├─ modeling.py    # F6 LightGBM 학습·CV + 게시용 모델 저장·로드
├─ multiclass.py  # F6b 다중분류(경보 단계) — 누적 이진
├─ reporting.py   # F8 SHAP 해석·예측 리포트
├─ ablation.py    # 기상 피처 유무 성능 비교
├─ deep.py        # 확장3 딥러닝(MLP·FT-Transformer, 누수통제·MPS/CPU)
├─ benchmark_dl.py # 확장3 GBDT vs 딥러닝 동일조건 비교
└─ forecast.py    # 확장4 기상청 단기예보 조회(대시보드 표시용, 모델 입력 아님)
app.py            # 확장4 Streamlit 대시보드 (지점 선택 → 단계 예측 + 예보 참고)
scripts/          # 취득: fetch_algae.py, fetch_weather.py, build_site_coords.py
reference/        # 지점 마스터·좌표·ASOS 매핑 (커밋: algae_sites, algae_site_coords, kma_stations, site_station_map)
models/           # 게시 모델 가중치·카드 (algae_lgbm.txt, algae_lgbm_ge10000.txt, *_card.json)
tests/            # 단위·누수 회귀 테스트
notebooks/        # EDA·결과 노트북
reports/          # 감사·평가·라이선스 리포트, 그림
data/             # 원자료(gitignore, 스크립트로 재생성)
docs/PRD/         # 제품 요구사항
```

## 테스트

```bash
uv run pytest      # 로더·타깃·피처·검증·다중분류·딥러닝·예보 (누수 회귀·게시모델 round-trip 포함)
```

## 방법론 — 누수 방지 (최우선 원칙)

- 라벨은 다음 측정(미래)에서만 생성, 라벨 측정치는 피처로 재사용 금지.
- 모든 lag/rolling은 `groupby(site)→시간정렬→shift`, rolling은 `shift(1)` 이후(과거만).
- 예측 시야(horizon) 4~10일 밖 샘플 제외(불규칙 샘플링 통제).
- 검증은 **연도 확장 시간순 분할 + 지점 GroupKFold**, 무작위 KFold 금지.
- **누수 회귀 테스트**: 미래 행을 변조해도 현재 시점 피처가 불변임을 검증.

## 라이선스

MIT (`LICENSE`). 서드파티 고지 `THIRD_PARTY_NOTICES`, 의존성 스캔 `reports/license_report.md`. 모든 런타임 의존성 permissive, 강한 카피레프트 없음.

## 로드맵

- ✅ **기상 외생변수(ASOS) 결합·ablation** — 과거 실측 기상은 유의미한 lift 없음(수온이 신호를 이미 포함). → `reports/weather_ablation.md`
- ✅ **다중분류(경보 단계: 정상/관심/경계이상)** — 누적 이진 방식. 상위 단계 recall에서 persistence 대비 우위(경계이상 0.786 vs 0.602). → `reports/model_multiclass.md`
- ✅ **딥러닝 벤치마크(GBDT vs MLP·FT-Transformer)** — 동일 피처·분할·지표 공정 비교. 테이블형·소규모 특성상 LightGBM 우위(시간 일반화는 FT-Transformer가 근소차, 지점 일반화는 격차). → `reports/model_dl_benchmark.md`
- ✅ **Streamlit 대시보드** — 지점·기준일 선택 → 단계(정상/관심/경계이상) 예측 + 최근 추세. 과거 검증/최신 예측 모드. → `app.py`
- ✅ **기상청 단기예보 연동(표시용)** — 최신 예측 모드에 향후 예보(기온·강수확률) 참고 표시. **모델 입력 아님**(과거·완벽예보 기상 무익, ablation 근거). → `src/forecast.py`
- 글로벌 다계열 시퀀스 모델(LSTM·N-HiTS·Chronos) — 원시 시계열 표현(제외 사유는 벤치마크 리포트 참조)
