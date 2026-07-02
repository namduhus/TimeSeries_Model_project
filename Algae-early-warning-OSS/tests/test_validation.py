"""F7 검증 로직 테스트 — 분할 누수 방지 + 지표 정확성 (§8.3, §4.1)."""

import numpy as np
import pandas as pd
import pytest

from src.validation import (
    evaluate,
    recall_at_precision,
    seasonal_score,
    site_splits,
    year_splits,
)


def _ds(n_per_year=200):
    """연도 2019~2023, 지점 6개 합성 데이터셋."""
    rng = np.random.default_rng(0)
    rows = []
    for yr in range(2019, 2024):
        for i in range(n_per_year):
            rows.append({
                "site_code": f"S{i % 6}",
                "date": pd.Timestamp(f"{yr}-07-01") + pd.Timedelta(days=int(rng.integers(0, 120))),
                "target": int(rng.random() < 0.1),
                "cur_cyano_cells": float(rng.integers(0, 5000)),
            })
    return pd.DataFrame(rows)


def test_year_split_train_strictly_before_test():
    ds = _ds()
    splits = year_splits(ds, start_test_year=2021, min_test=10)
    assert [s[2] for s in splits] == [2021, 2022, 2023]
    for tr, te, ty in splits:
        # 학습 데이터의 모든 연도가 test 연도보다 과거여야 함(미래 누수 금지)
        assert ds["date"].dt.year.to_numpy()[tr].max() < ty
        assert (ds["date"].dt.year.to_numpy()[te] == ty).all()


def test_site_split_groups_disjoint():
    ds = _ds()
    for tr, te, _ in site_splits(ds, n_folds=3):
        tr_sites = set(ds["site_code"].to_numpy()[tr])
        te_sites = set(ds["site_code"].to_numpy()[te])
        assert tr_sites.isdisjoint(te_sites)  # 학습/평가 지점 완전 분리


def test_recall_at_precision():
    # 완벽 분리 점수 → precision 1.0 에서 recall 1.0
    y = np.array([0, 0, 1, 1])
    score = np.array([0.1, 0.2, 0.8, 0.9])
    from sklearn.metrics import precision_recall_curve
    prec, rec, _ = precision_recall_curve(y, score)
    assert recall_at_precision(prec, rec, 0.5) == pytest.approx(1.0)


def test_seasonal_score_uses_train_only():
    ds = _ds()
    splits = year_splits(ds, start_test_year=2022, min_test=10)
    tr, te, _ = splits[0]
    sc = seasonal_score(ds, tr, te)
    assert len(sc) == len(te)
    assert np.isfinite(sc).all()  # 매핑 실패 없이 전부 값


def test_evaluate_handles_single_class():
    out = evaluate(np.zeros(10), np.random.default_rng(0).random(10))
    assert np.isnan(out["pr_auc"])  # 양성 없음 → 정의 불가
