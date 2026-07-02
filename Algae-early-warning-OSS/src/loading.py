"""조류경보제 측정자료 로딩·표준 스키마 정규화 (F1).

`scripts/fetch_algae.py` 가 저장한 원자료(JSON, 필드명 UPPER_SNAKE)를 읽어
읽기 쉬운 표준 스키마의 pandas DataFrame 으로 변환한다.

원칙(§8.3 누수 방지 전제):
- 이 단계는 순수 로딩·정규화만 수행한다. **리샘플링·보간·집계·라벨 생성 금지.**
- 결측/텍스트 센티널(예: "정량한계미만")은 숫자 컬럼에서 NaN 으로 강제변환한다.
- (site_code, date) 오름차순 정렬만 적용하고 중복 제거는 하지 않는다(중복 점검은 F2 Audit).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "algae"
WEATHER_RAW_DIR = REPO_ROOT / "data" / "raw" / "weather"
SITES_CSV = REPO_ROOT / "reference" / "algae_sites.csv"  # 지점 마스터(코드·구분·권역)

# 원자료(JSON) 필드명 → 표준 컬럼명. 좌측은 algaePreMeasure JSON 응답의 키.
FIELD_MAP: dict[str, str] = {
    "SWMN_CODE": "site_code",            # 측정지점 코드 (예: 3012A07)
    "SWMN_NM": "site_name",              # 지점명 (예: 세종보)
    "SWMN_DETAIL_NM": "site_detail_name",  # 상세 지점명
    "RIVER_LKMH_SE": "water_body_type",  # 수계 구분 (하천/호소)
    "DETAIL_ADRES": "detail_address",    # 상세 위치
    "CHCK_DE": "date",                   # 측정일자 (YYYY.MM.DD)
    "IEM_WTRTP": "water_temp",           # 수온 (℃)
    "IEM_PH": "ph",                      # pH
    "IEM_DOC": "dissolved_oxygen",       # 용존산소 DO (mg/L) — 파일 'DO(㎎/L)'와 값 일치 확인
    "IEM_TRP": "transparency",           # 투명도 (m)
    "IEM_TUR": "turbidity",              # 탁도 (NTU)
    "IEM_CHLA": "chlorophyll_a",         # 클로로필-a (mg/m³)
    "IEM_BGALAGE_CELL_CO": "cyano_cells",          # 유해남조류 세포수 (cells/mL) — 타깃 원천
    "IEM_BGALAGE_MICROSTS": "cyano_microcystis",   # Microcystis 속
    "IEM_BGALAGE_ANBA": "cyano_anabaena",          # Anabaena(Dolichospermum) 속
    "IEM_BGALAGE_OSRTRIA": "cyano_oscillatoria",   # Oscillatoria 속
    "IEM_BGALAGE_APZO": "cyano_aphanizomenon",     # Aphanizomenon 속
    "IEM_GEOSM": "geosmin",              # 지오스민 (ng/L)
    "IEM_MIB2": "mib_2",                 # 2-MIB (ng/L)
    "IEM_MICROSTLR": "microcystin_lr",   # 마이크로시스틴-LR (µg/L)
}

ID_COLS: list[str] = [
    "site_code", "site_name", "site_detail_name", "water_body_type", "detail_address",
]
DATE_COL = "date"
NUMERIC_COLS: list[str] = [
    "water_temp", "ph", "dissolved_oxygen", "transparency", "turbidity", "chlorophyll_a",
    "cyano_cells", "cyano_microcystis", "cyano_anabaena", "cyano_oscillatoria",
    "cyano_aphanizomenon", "geosmin", "mib_2", "microcystin_lr",
]
STANDARD_COLUMNS: list[str] = ID_COLS + [DATE_COL] + NUMERIC_COLS


def normalize(records: list[dict]) -> pd.DataFrame:
    """원자료 dict 리스트 → 표준 스키마 DataFrame (정렬 포함, 리샘플링 없음)."""
    df = pd.DataFrame(records).rename(columns=FIELD_MAP)
    # 원자료에 없는 컬럼도 표준 스키마로 채워 스키마를 안정화(누락 → NaN)
    df = df.reindex(columns=STANDARD_COLUMNS)

    df[DATE_COL] = pd.to_datetime(df[DATE_COL], format="%Y.%m.%d", errors="coerce")
    for col in NUMERIC_COLS:
        # 빈값·"정량한계미만" 등 텍스트 센티널 → NaN
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ID_COLS:
        df[col] = df[col].astype("string")

    return df.sort_values(["site_code", DATE_COL]).reset_index(drop=True)


def load_algae(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """data/raw/algae/*.json 을 모두 읽어 표준 스키마 DataFrame 으로 반환."""
    files = sorted(raw_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(
            f"원자료가 없습니다: {raw_dir}. 먼저 scripts/fetch_algae.py 로 취득하세요."
        )
    records: list[dict] = []
    for path in files:
        records.extend(json.loads(path.read_text(encoding="utf-8")))
    return normalize(records)


# 물환경정보시스템 '과거수질자료(조류모니터링_일자료)' 다운로드 파일의 열 순서(위치 기반).
# 다중 헤더라 헤더명 대신 위치로 매핑한다. 뒤쪽 마이크로시스틴 이성질체는 표준 스키마에 없어 버려짐.
FILE_COLUMNS: list[str] = [
    "water_body_type", "site_name", "site_detail_name", "date",
    "water_temp", "ph", "dissolved_oxygen", "transparency", "turbidity", "chlorophyll_a",
    "cyano_cells", "cyano_microcystis", "cyano_anabaena", "cyano_oscillatoria",
    "cyano_aphanizomenon", "geosmin", "mib_2", "microcystin_lr",
    "mc_rr", "mc_la", "mc_yr", "mc_lf", "mc_ly",
]


def load_algae_file(path: Path) -> pd.DataFrame:
    """물환경정보시스템 다운로드 파일(xlsx) → API 로더와 동일한 표준 스키마 DataFrame.

    API(algaePreMeasure)와 동일 원천이라 값이 수렴함을 교차검증하는 용도(§12). 파일에는
    지점코드가 없어 site_code/detail_address 는 NA 로 채운다(식별은 site_name+site_detail_name).
    """
    raw = pd.read_excel(path, sheet_name=0, header=None, dtype=str)
    raw.columns = FILE_COLUMNS
    df = raw[raw["water_body_type"].isin(["하천", "호소"])].copy()  # 타이틀·헤더 행 제거
    df = df.reindex(columns=STANDARD_COLUMNS)  # 표준 스키마 정렬(이성질체 제거, 없는 컬럼 NA)

    df["date"] = pd.to_datetime(df["date"], format="%Y.%m.%d", errors="coerce")
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ID_COLS:
        df[col] = df[col].astype("string")

    return df.sort_values(["site_name", "site_detail_name", "date"]).reset_index(drop=True)


def load_sites(path: Path = SITES_CSV) -> pd.DataFrame:
    """지점 마스터 로드. 컬럼: station_type, site_code, site_name, survey_location,
    address, agency, major_basin, mid_basin.

    조류경보제 대상 실지점 88개의 화이트리스트로, API 원자료의 테스트 더미 코드
    (예: 5555A44, 9999A99)를 걸러내고 구분·권역 메타데이터를 붙이는 데 쓴다.
    """
    return pd.read_csv(path, dtype="string")


def clean_algae(df: pd.DataFrame, sites: pd.DataFrame | None = None) -> pd.DataFrame:
    """지점 마스터 화이트리스트로 테스트 더미 코드(5555/9999 계열 등)를 제거한다."""
    if sites is None:
        sites = load_sites()
    return df[df["site_code"].isin(set(sites["site_code"]))].copy()


# ---------------------------------------------------------------------------
# 기상 (기상청 ASOS 일자료) — 외생변수
# ---------------------------------------------------------------------------
# ASOS 응답 필드 중 조류 예측 외생변수로 쓸 부분집합만 표준화한다(전체 50여 개 중).
WEATHER_FIELD_MAP: dict[str, str] = {
    "stnId": "station_id",       # 관측소 지점번호
    "stnNm": "station_name",     # 관측소명
    "tm": "date",                # 관측일자 (YYYY-MM-DD)
    "avgTa": "temp_avg",         # 평균기온 (℃)
    "minTa": "temp_min",         # 최저기온 (℃)
    "maxTa": "temp_max",         # 최고기온 (℃)
    "sumRn": "precip",           # 일강수량 (mm) — 빈값은 사실상 무강수(≈0), F4에서 처리
    "avgWs": "wind_avg",         # 평균풍속 (m/s)
    "maxWs": "wind_max",         # 최대풍속 (m/s)
    "avgRhm": "humidity_avg",    # 평균 상대습도 (%)
    "sumSsHr": "sunshine_hours", # 합계 일조시간 (hr)
    "sumGsr": "solar_radiation", # 합계 일사량 (MJ/m²)
    "avgTca": "cloud_avg",       # 평균 전운량 (1/10)
    "avgTs": "surface_temp_avg", # 평균 지면온도 (℃)
}

WEATHER_ID_COLS: list[str] = ["station_id", "station_name"]
WEATHER_NUMERIC_COLS: list[str] = [
    "temp_avg", "temp_min", "temp_max", "precip", "wind_avg", "wind_max",
    "humidity_avg", "sunshine_hours", "solar_radiation", "cloud_avg", "surface_temp_avg",
]
WEATHER_STANDARD_COLUMNS: list[str] = WEATHER_ID_COLS + [DATE_COL] + WEATHER_NUMERIC_COLS


def normalize_weather(records: list[dict]) -> pd.DataFrame:
    """ASOS 원자료 dict 리스트 → 표준 기상 스키마 DataFrame (정렬 포함, 리샘플링 없음)."""
    df = pd.DataFrame(records).rename(columns=WEATHER_FIELD_MAP)
    df = df.reindex(columns=WEATHER_STANDARD_COLUMNS)

    df[DATE_COL] = pd.to_datetime(df[DATE_COL], format="%Y-%m-%d", errors="coerce")
    for col in WEATHER_NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")  # 빈값 → NaN
    for col in WEATHER_ID_COLS:
        df[col] = df[col].astype("string")

    return df.sort_values(["station_id", DATE_COL]).reset_index(drop=True)


def load_weather(raw_dir: Path = WEATHER_RAW_DIR) -> pd.DataFrame:
    """data/raw/weather/asos_*.json 을 모두 읽어 표준 기상 스키마 DataFrame 으로 반환."""
    files = sorted(raw_dir.glob("asos_*.json"))
    if not files:
        raise FileNotFoundError(
            f"기상 원자료가 없습니다: {raw_dir}. 먼저 scripts/fetch_weather.py 로 취득하세요."
        )
    records: list[dict] = []
    for path in files:
        records.extend(json.loads(path.read_text(encoding="utf-8")))
    return normalize_weather(records)


if __name__ == "__main__":
    frame = load_algae()
    print(f"rows={len(frame)}  sites={frame['site_code'].nunique()}")
    print(f"date range: {frame['date'].min()} ~ {frame['date'].max()}")
    print(frame.head(10).to_string())
