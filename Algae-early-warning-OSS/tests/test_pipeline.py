"""F9 E2E·재현성 테스트 — 픽스처 원자료 → 타깃 → 피처 → 모델 (§12).

디스크·네트워크 없이 합성 원자료로 전 파이프라인이 동작하고, 고정 시드에서
동일 결과를 내는지 검증한다.
"""

import numpy as np
import pandas as pd

from src.features import build_features, feature_columns
from src.loading import load_sites, normalize
from src.modeling import _inner_time_val, prep_X, train_lgbm
from src.target import build_targets

# 마스터에 존재하는 실제 지점 코드(clean_algae 통과용)
_CYANO = [100, 300, 1500, 2000, 800, 50, 1200, 3000, 90, 1100, 40, 2500, 60, 1300, 80, 1400]


def _fixture_records() -> list[dict]:
    dates = pd.date_range("2023-05-01", periods=len(_CYANO), freq="7D")
    recs = []
    for code in ["1003G20", "3012A07"]:
        for d, c in zip(dates, _CYANO):
            recs.append({
                "SWMN_CODE": code, "RIVER_LKMH_SE": "호소", "SWMN_NM": "X", "SWMN_DETAIL_NM": "Y",
                "CHCK_DE": d.strftime("%Y.%m.%d"), "IEM_WTRTP": str(20 + c % 10),
                "IEM_PH": "8.0", "IEM_CHLA": str(c / 50), "IEM_BGALAGE_CELL_CO": str(c),
            })
    return recs


def _dataset() -> pd.DataFrame:
    df = normalize(_fixture_records())
    sites = load_sites()
    tg = build_targets(df, sites)
    ft = build_features(df, sites)
    return tg.merge(ft, on=["site_code", "date"], how="inner")


def test_e2e_pipeline_runs():
    ds = _dataset()
    assert len(ds) > 0
    assert ds["target"].isin([0, 1]).all()
    assert ds["target"].nunique() == 2  # 임계 교차 → 두 클래스 존재
    feats = feature_columns(ds)
    X, y = prep_X(ds, feats), ds["target"].to_numpy()
    tr, val = _inner_time_val(ds["date"].to_numpy(), np.arange(len(ds)))
    model = train_lgbm(X, y, tr, val)
    p = model.predict(X)
    assert ((p >= 0) & (p <= 1)).all()


def test_reproducibility_fixed_seed():
    ds = _dataset()
    feats = feature_columns(ds)
    X, y = prep_X(ds, feats), ds["target"].to_numpy()
    tr, val = _inner_time_val(ds["date"].to_numpy(), np.arange(len(ds)))
    p1 = train_lgbm(X, y, tr, val).predict(X)
    p2 = train_lgbm(X, y, tr, val).predict(X)
    assert np.array_equal(p1, p2)  # deterministic=True + 고정 시드
