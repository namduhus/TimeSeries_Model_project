"""F4 피처 단위·누수 회귀 테스트 (§8.3, §12).

핵심: 시점 t의 피처는 t까지의 정보로만 결정된다 — 미래 행을 바꿔도 t행 피처는 불변.
"""

import numpy as np
import pandas as pd
import pytest

from src.features import assemble_dataset, build_features, feature_columns


def _sites(codes: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        "site_code": pd.Series(codes, dtype="string"),
        "station_type": pd.Series(["호소"] * len(codes), dtype="string"),
        "major_basin": pd.Series(["한강"] * len(codes), dtype="string"),
    })


def _series(code: str, dates, cyano, temp) -> pd.DataFrame:
    n = len(dates)
    return pd.DataFrame({
        "site_code": pd.Series([code] * n, dtype="string"),
        "date": pd.to_datetime(dates),
        "cyano_cells": np.asarray(cyano, dtype="float"),
        "water_temp": np.asarray(temp, dtype="float"),
        "ph": np.nan, "dissolved_oxygen": np.nan,
        "transparency": np.nan, "turbidity": np.nan,
        "chlorophyll_a": np.arange(n, dtype="float"),
    })


def test_lag_matches_previous_value():
    dates = pd.date_range("2023-06-01", periods=5, freq="7D")
    df = _series("X", dates, cyano=[100, 200, 300, 400, 500], temp=[20, 21, 22, 23, 24])
    feat = build_features(df, _sites(["X"])).sort_values("date").reset_index(drop=True)
    # lag1 은 직전 행의 현재값
    assert feat["cyano_cells_lag1"].tolist()[1:] == [100, 200, 300, 400]
    assert np.isnan(feat["cyano_cells_lag1"].iloc[0])


def test_rolling_excludes_current_value():
    dates = pd.date_range("2023-06-01", periods=5, freq="7D")
    df = _series("X", dates, cyano=[10, 20, 30, 40, 50], temp=[1, 2, 3, 4, 5])
    feat = build_features(df, _sites(["X"]), roll_windows=(2,)).sort_values("date").reset_index(drop=True)
    # rollmean2(shift1) at idx3 = mean(과거 2개: idx1,idx2 = 20,30) = 25, 현재(40) 배제
    assert feat["cyano_cells_rollmean2"].iloc[3] == pytest.approx(25.0)


def test_days_since_prev():
    dates = ["2023-06-01", "2023-06-08", "2023-06-18"]  # 7일, 10일 간격
    df = _series("X", dates, cyano=[1, 2, 3], temp=[1, 2, 3])
    feat = build_features(df, _sites(["X"])).sort_values("date").reset_index(drop=True)
    assert feat["days_since_prev"].tolist()[1:] == [7, 10]
    assert np.isnan(feat["days_since_prev"].iloc[0])


def test_no_future_leakage():
    """t 이후 행을 임의 변조해도 t행 피처는 변하지 않아야 한다(§8.3 누수 가드)."""
    dates = pd.date_range("2023-06-01", periods=8, freq="7D")
    df = _series("X", dates, cyano=[100, 200, 300, 1500, 50, 80, 2000, 90],
                 temp=[18, 19, 20, 25, 21, 22, 28, 20])
    sites = _sites(["X"])
    feat1 = build_features(df, sites).set_index("date").sort_index()

    t = dates[3]
    df2 = df.copy()
    future = df2["date"] > t
    df2.loc[future, "cyano_cells"] = 999999      # 미래 대량 변조
    df2.loc[future, "water_temp"] = -99
    feat2 = build_features(df2, sites).set_index("date").sort_index()

    pd.testing.assert_series_equal(feat1.loc[t], feat2.loc[t])


def test_dummy_and_target_join():
    from src.loading import load_algae, load_sites
    try:
        algae = load_algae()
    except FileNotFoundError:
        pytest.skip("원자료 없음")
    ds = assemble_dataset()
    # 조인 결과에 타깃·키·피처가 모두 존재
    assert {"site_code", "date", "target"}.issubset(ds.columns)
    assert len(feature_columns(ds)) >= 20
    assert (ds["label_date"] > ds["date"]).all()          # 타깃은 미래
    assert ds["horizon_days"].between(4, 10).all()
    assert 0.05 < ds["target"].mean() < 0.20               # F2 근거 ~10%
    # 현재 세포수 피처가 존재(persistence 신호)
    assert "cur_cyano_cells" in ds.columns
