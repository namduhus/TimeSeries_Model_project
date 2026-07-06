"""확장3 딥러닝 테스트 — 폴드 내 전처리 누수 없음·예측 유효성·CPU 재현성."""

import numpy as np
import pandas as pd
import torch

from src.deep import _fit_transform_num, get_device, train_predict_dl
from src.features import build_features, feature_columns
from src.loading import load_sites, normalize
from src.modeling import CATEGORICAL, _inner_time_val, prep_X
from src.target import build_targets

_CYANO = [100, 5000, 20000, 300, 1500, 800, 1200, 50, 1100, 40, 2500, 60, 1300, 80, 4000, 90]


def _dataset() -> pd.DataFrame:
    dates = pd.date_range("2023-05-01", periods=len(_CYANO), freq="7D")
    recs = []
    for code in ["1003G20", "3012A07"]:
        for d, c in zip(dates, _CYANO):
            recs.append({
                "SWMN_CODE": code, "RIVER_LKMH_SE": "호소", "SWMN_NM": "X", "SWMN_DETAIL_NM": "Y",
                "CHCK_DE": d.strftime("%Y.%m.%d"), "IEM_WTRTP": str(20 + c % 10),
                "IEM_PH": "8.0", "IEM_CHLA": str(c / 50), "IEM_BGALAGE_CELL_CO": str(c),
            })
    df = normalize(recs)
    sites = load_sites()
    return build_targets(df, sites).merge(build_features(df, sites), on=["site_code", "date"], how="inner")


def test_scaler_fits_on_train_only():
    """test 행을 변조해도 train 에서 fit 한 스케일링 결과가 불변 → 누수 없음."""
    ds = _dataset()
    X = prep_X(ds, feature_columns(ds))
    num_cols = [c for c in X.columns if c not in CATEGORICAL]
    n = len(X)
    fit_idx = np.arange(n // 2)          # 앞 절반만 fit
    Xn_a = _fit_transform_num(X, num_cols, fit_idx)

    X2 = X.copy()
    X2[num_cols] = X2[num_cols].astype("float64")            # int 컬럼 오버플로 방지
    X2.iloc[n // 2:, [X2.columns.get_loc(c) for c in num_cols]] = 9e9  # 뒷 절반(비-fit) 오염
    Xn_b = _fit_transform_num(X2, num_cols, fit_idx)
    # fit 대상(앞 절반)의 변환값은 완전히 동일해야 한다
    assert np.allclose(Xn_a[fit_idx], Xn_b[fit_idx])


def test_train_predict_dl_valid_proba():
    ds = _dataset()
    X, y = prep_X(ds, feature_columns(ds)), ds["target"].to_numpy()
    tr, te = _inner_time_val(ds["date"].to_numpy(), np.arange(len(ds)))
    for mt in ("mlp", "ft"):
        p = train_predict_dl(ds, X, y, tr, te, mt, torch.device("cpu"))
        assert p.shape == (len(te),)
        assert ((p >= 0) & (p <= 1)).all()


def test_cpu_reproducible():
    ds = _dataset()
    X, y = prep_X(ds, feature_columns(ds)), ds["target"].to_numpy()
    tr, te = _inner_time_val(ds["date"].to_numpy(), np.arange(len(ds)))
    p1 = train_predict_dl(ds, X, y, tr, te, "mlp", torch.device("cpu"))
    p2 = train_predict_dl(ds, X, y, tr, te, "mlp", torch.device("cpu"))
    assert np.allclose(p1, p2)  # 시드 고정 + CPU → 결정적


def test_get_device_cpu_override():
    assert get_device("cpu").type == "cpu"
