"""F9 로더 단위 테스트 — 정규화 스키마·날짜·텍스트 센티널·정렬·파일 파싱 (§12)."""

import pandas as pd
import pytest

from src.loading import (
    STANDARD_COLUMNS,
    WEATHER_STANDARD_COLUMNS,
    clean_algae,
    load_algae_file,
    load_sites,
    normalize,
    normalize_weather,
)


def test_normalize_schema_dates_and_sentinel():
    recs = [
        {"SWMN_CODE": "3012A07", "RIVER_LKMH_SE": "하천", "SWMN_NM": "세종보",
         "SWMN_DETAIL_NM": "연기", "DETAIL_ADRES": "보 상류", "CHCK_DE": "2023.08.07",
         "IEM_WTRTP": "29.9", "IEM_PH": "8.2", "IEM_TRP": None, "IEM_TUR": "11.7",
         "IEM_CHLA": "73.0", "IEM_BGALAGE_CELL_CO": "0", "IEM_MIB2": "정량한계미만"},
        {"SWMN_CODE": "3012A07", "RIVER_LKMH_SE": "하천", "SWMN_NM": "세종보",
         "SWMN_DETAIL_NM": "연기", "CHCK_DE": "2023.07.31", "IEM_WTRTP": "28.0",
         "IEM_BGALAGE_CELL_CO": "1500"},
    ]
    df = normalize(recs)
    assert list(df.columns) == STANDARD_COLUMNS
    assert str(df["date"].dtype).startswith("datetime")
    assert df["date"].iloc[0] < df["date"].iloc[1]           # (site,date) 정렬
    assert pd.api.types.is_float_dtype(df["mib_2"])           # 텍스트 센티널 누수 없음
    assert df["mib_2"].isna().all()                           # "정량한계미만" → NaN
    assert df["transparency"].isna().all()                    # 빈값 → NaN
    assert df["cyano_cells"].tolist() == [1500.0, 0.0]


def test_normalize_weather_schema_and_empty_precip():
    recs = [{"stnId": "108", "stnNm": "서울", "tm": "2023-08-01", "avgTa": "29.9",
             "minTa": "25.5", "maxTa": "34.2", "sumRn": "", "avgWs": "1.9",
             "avgRhm": "71.6", "sumSsHr": "10.3", "sumGsr": "21.25",
             "avgTca": "4.1", "avgTs": "30.8"}]
    w = normalize_weather(recs)
    assert list(w.columns) == WEATHER_STANDARD_COLUMNS
    assert str(w["date"].dtype).startswith("datetime")        # tm YYYY-MM-DD 파싱
    assert w["precip"].isna().all()                           # 무강수 빈값 → NaN
    assert w["temp_avg"].iloc[0] == 29.9


def test_clean_algae_drops_test_dummies():
    df = normalize([
        {"SWMN_CODE": "9999A99", "CHCK_DE": "2023.08.01", "IEM_BGALAGE_CELL_CO": "5000"},
        {"SWMN_CODE": "3012A07", "CHCK_DE": "2023.08.01", "IEM_BGALAGE_CELL_CO": "10"},
    ])
    out = clean_algae(df, load_sites())
    assert set(out["site_code"].dropna()) == {"3012A07"}


def test_load_sites_master():
    s = load_sites()
    assert len(s) == 88
    assert {"site_code", "station_type", "major_basin"}.issubset(s.columns)


def test_file_loader_parses_multiheader_format(tmp_path):
    """물환경정보시스템 다운로드 형식(타이틀+헤더+데이터, 23열)을 표준 스키마로."""
    data_h = ["하천", "한강", "이천", "2026.06.01", 19.5, 8.3, 11.5, 1.8, 0.9, 8.7,
              0, 0, 0, 0, 0, None, None, None, None, None, None, None, None]
    data_l = ["호소", "충주호", "청풍교", "2026.06.05", 24.0, 8.0, 9.0, 3.0, 5.0, 2.0,
              100, 100, 0, 0, 0, None, None, None, None, None, None, None, None]
    rows = [
        ["조류모니터링_일자료"] + [None] * 22,
        ["분류", "지점명", "채수위치", "조사일"] + [f"h{i}" for i in range(19)],
        data_h, data_l,
    ]
    p = tmp_path / "past_wq.xlsx"
    pd.DataFrame(rows).to_excel(p, header=False, index=False, sheet_name="조류모니터링_일자료")

    df = load_algae_file(p)
    assert list(df.columns) == STANDARD_COLUMNS               # 이성질체 제거·표준 정렬
    assert len(df) == 2                                       # 하천+호소만(헤더행 제외)
    assert set(df["water_body_type"]) == {"하천", "호소"}
    assert df.loc[df["site_name"] == "한강", "water_temp"].iloc[0] == 19.5
    assert df.loc[df["site_name"] == "충주호", "cyano_cells"].iloc[0] == 100.0
