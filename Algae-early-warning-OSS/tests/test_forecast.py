"""확장4 — 기상청 예보 헬퍼 테스트 (격자 변환·요약, 네트워크 불필요)."""

from src.forecast import _summarize, latlon_to_grid


def test_grid_conversion_seoul():
    # 기상청 공식 기준점: 서울(37.5665, 126.9780) → 격자 (60, 127)
    assert latlon_to_grid(37.5665, 126.9780) == (60, 127)


def test_grid_conversion_stable():
    # 동일 입력 → 동일 격자(정수)
    assert latlon_to_grid(37.003672, 128.179714) == latlon_to_grid(37.003672, 128.179714)


def test_summarize_daily():
    items = [
        {"fcstDate": "20260707", "category": "TMN", "fcstValue": "23"},
        {"fcstDate": "20260707", "category": "TMX", "fcstValue": "30"},
        {"fcstDate": "20260707", "category": "POP", "fcstValue": "60"},
        {"fcstDate": "20260707", "category": "SKY", "fcstValue": "1"},   # 무시 대상
        {"fcstDate": "20260708", "category": "POP", "fcstValue": "70"},
    ]
    df = _summarize(items)
    assert list(df["날짜"]) == ["07/07", "07/08"]
    row = df[df["날짜"] == "07/07"].iloc[0]
    assert row["최저(℃)"] == 23 and row["최고(℃)"] == 30 and row["강수확률(%)"] == 60
