"""확장2 다중분류(경보 단계) 테스트 — 단계 라벨·단조성·순서지표·픽스처 E2E."""

import json

import numpy as np
import pandas as pd

from src.features import build_features, feature_columns
from src.loading import load_sites, normalize
from src.modeling import _inner_time_val, prep_X, train_lgbm
from src.multiclass import cumulative_stage, predict_stage, run_stage_cv, save_stage_model
from src.target import STAGE_THRESHOLDS, alert_stage, build_targets
from src.validation import evaluate_stages, persistence_stage

# 세 단계를 모두 포함하도록 임계(1k·10k)를 넘나드는 세포수
_CYANO = [100, 5000, 20000, 300, 15000, 800, 12000, 50, 1100, 40, 25000, 60, 1300, 80, 40000, 90]


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
    tg = build_targets(df, sites)
    ft = build_features(df, sites)
    return tg.merge(ft, on=["site_code", "date"], how="inner")


def test_alert_stage_cutoffs():
    s = alert_stage([999, 1000, 9999, 10000, 1_000_000])
    assert list(s) == [0, 1, 1, 2, 2]


def test_cumulative_stage_monotonic_clip():
    # P(≥경계) > P(≥관심) 는 논리 위반 → 보정되어 단계가 관심을 넘지 않음
    p_low = np.array([0.1, 0.9, 0.9, 0.4])
    p_high = np.array([0.8, 0.1, 0.95, 0.3])  # 0번은 low<high(모순)
    stage = cumulative_stage(p_low, p_high, tau=0.5)
    assert list(stage) == [0, 1, 2, 0]  # 0번: high가 low로 clip돼 정상


def test_evaluate_stages_perfect():
    y = np.array([0, 1, 2, 0, 1, 2])
    m = evaluate_stages(y, y.copy())
    assert m["accuracy"] == 1.0 and m["macro_f1"] == 1.0 and m["qwk"] == 1.0
    assert all(v == 1.0 for v in m["recall_per_stage"].values())


def test_persistence_stage_uses_current():
    ds = _dataset()
    te = np.arange(len(ds))
    base = persistence_stage(ds, te)
    assert set(np.unique(base)).issubset({0, 1, 2})
    assert np.array_equal(base, alert_stage(ds["cur_cyano_cells"].to_numpy()))


def test_stage_cv_runs_on_fixture():
    ds = _dataset()
    X = prep_X(ds, feature_columns(ds))
    # 픽스처(단일 연도)는 연도 CV 불가 → inner split 로 누적 이진 2개 학습·도출만 검증
    tr, val = _inner_time_val(ds["date"].to_numpy(), np.arange(len(ds)))
    lc = ds["label_cyano"].to_numpy()
    y_low = (lc >= STAGE_THRESHOLDS[0]).astype("int8")
    y_high = (lc >= STAGE_THRESHOLDS[1]).astype("int8")
    p_low = train_lgbm(X, y_low, tr, val).predict(X)
    p_high = train_lgbm(X, y_high, tr, val).predict(X)
    stage = cumulative_stage(p_low, p_high)
    assert set(np.unique(stage)).issubset({0, 1, 2})
    assert (np.minimum(p_high, p_low) <= p_low).all()  # 단조성


def test_save_stage_model_and_predict(tmp_path):
    """경계이상 모델 게시 → 로드 → 단계 예측(정상/관심/경계이상)이 유효한지."""
    ds = _dataset()
    feats = feature_columns(ds)
    X = prep_X(ds, feats)
    mp, cp = tmp_path / "ge10000.txt", tmp_path / "stage_card.json"

    high = save_stage_model(ds, X, feats, model_path=mp, card_path=cp)
    low = train_lgbm(X, (ds["label_cyano"].to_numpy() >= STAGE_THRESHOLDS[0]).astype("int8"),
                     *_inner_time_val(ds["date"].to_numpy(), np.arange(len(ds))))
    stage, p_low, p_high = predict_stage(X, low, high)

    assert mp.exists() and cp.exists()
    assert set(np.unique(stage)).issubset({0, 1, 2})
    assert (p_high <= p_low + 1e-9).all()               # 단조성 보정 확인
    card = json.loads(cp.read_text(encoding="utf-8"))
    assert card["stage_thresholds_cells_per_ml"] == list(STAGE_THRESHOLDS)
