"""F5 타깃 생성 단위·누수 테스트 (§12).

핵심 불변식: 라벨은 항상 미래(다음 측정)에서 오고, 예측 시야(horizon) 창을 벗어난
샘플은 제외되며, 테스트 더미 코드는 걸러진다.
"""

import pandas as pd
import pytest

from src.target import build_targets


def _sites(codes: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"site_code": pd.Series(codes, dtype="string")})


def _algae(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """rows: (site_code, 'YYYY-MM-DD', cyano_cells)"""
    return pd.DataFrame({
        "site_code": pd.Series([r[0] for r in rows], dtype="string"),
        "date": pd.to_datetime([r[1] for r in rows]),
        "cyano_cells": [r[2] for r in rows],
    })


def test_labeling_uses_next_measurement():
    df = _algae([
        ("X", "2023-08-01", 500),
        ("X", "2023-08-08", 1500),
        ("X", "2023-08-15", 800),
        ("X", "2023-08-22", 2000),
    ])
    out = build_targets(df, _sites(["X"]), threshold=1000, min_gap_days=4, max_gap_days=10)
    # 마지막 행은 다음 측정이 없어 제외
    assert list(out["target"]) == [1, 0, 1]
    # 라벨은 '다음' 측정치
    assert list(out["label_cyano"]) == [1500, 800, 2000]


def test_label_is_always_future():
    df = _algae([("X", "2023-08-01", 500), ("X", "2023-08-08", 1500)])
    out = build_targets(df, _sites(["X"]))
    assert (out["label_date"] > out["date"]).all()


def test_horizon_window_filters_out_of_range():
    # 2일(너무 촘촘) · 30일(너무 김) → 모두 창[4,10] 밖
    df = _algae([
        ("X", "2023-08-01", 100),
        ("X", "2023-08-03", 5000),
        ("X", "2023-09-02", 100),
    ])
    out = build_targets(df, _sites(["X"]), min_gap_days=4, max_gap_days=10)
    assert out.empty


def test_horizon_all_within_window():
    df = _algae([("X", "2023-08-01", 100), ("X", "2023-08-08", 100), ("X", "2023-08-15", 100)])
    out = build_targets(df, _sites(["X"]), min_gap_days=4, max_gap_days=10)
    assert out["horizon_days"].between(4, 10).all()


def test_test_dummy_codes_removed():
    df = _algae([("9999A99", "2023-08-01", 100), ("9999A99", "2023-08-08", 5000)])
    out = build_targets(df, _sites(["X"]))  # 9999A99는 마스터에 없음
    assert out.empty


def test_threshold_boundary_inclusive():
    # 임계 정확히 1000 → 초과(≥)로 양성
    df = _algae([("X", "2023-08-01", 0), ("X", "2023-08-08", 1000)])
    out = build_targets(df, _sites(["X"]), threshold=1000)
    assert list(out["target"]) == [1]


def test_real_data_sanity():
    from src.loading import load_algae, load_sites
    try:
        df = load_algae()
    except FileNotFoundError:
        pytest.skip("원자료 없음 — scripts/fetch_algae.py 필요")
    out = build_targets(df, load_sites())
    assert (out["label_date"] > out["date"]).all()
    assert out["horizon_days"].between(4, 10).all()
    assert 0.05 < out["target"].mean() < 0.20  # F2 근거 ~11.6%
