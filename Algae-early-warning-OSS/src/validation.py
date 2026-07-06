"""F7 Validation — 시간순/지점 분할, 불균형 지표, 베이스라인.

누수 방지(§8.3): 무작위 KFold 금지. 시간 일반화는 **확장 윈도우 연도 분할**
(train = test 연도 이전 전부), 지점 일반화는 **지점 GroupKFold**로 평가한다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold

from src.target import STAGE_NAMES, alert_stage

Split = tuple[np.ndarray, np.ndarray, object]  # (train_pos, test_pos, label)


def year_splits(ds: pd.DataFrame, start_test_year: int = 2022, min_test: int = 100) -> list[Split]:
    """확장 윈도우: 각 test 연도에 대해 train = 그 이전 연도 전부."""
    yr = ds["date"].dt.year.to_numpy()
    splits: list[Split] = []
    for ty in range(start_test_year, int(yr.max()) + 1):
        tr = np.where(yr < ty)[0]
        te = np.where(yr == ty)[0]
        if len(tr) and len(te) >= min_test:
            splits.append((tr, te, ty))
    return splits


def site_splits(ds: pd.DataFrame, n_folds: int = 5) -> list[Split]:
    """지점 GroupKFold — 학습에 없던 지점으로 일반화 평가."""
    gkf = GroupKFold(n_splits=n_folds)
    return [(tr, te, i + 1) for i, (tr, te) in enumerate(gkf.split(ds, ds["target"], ds["site_code"]))]


def recall_at_precision(precision: np.ndarray, recall: np.ndarray, target: float = 0.5) -> float:
    """정밀도 ≥ target 을 만족하는 지점에서의 최대 재현율."""
    mask = precision >= target
    return float(recall[mask].max()) if mask.any() else 0.0


def evaluate(y_true: np.ndarray, y_score: np.ndarray) -> dict:
    y_true = np.asarray(y_true)
    y_score = np.nan_to_num(np.asarray(y_score, dtype="float"), nan=0.0)
    out = {"n": int(len(y_true)), "pos": int(y_true.sum())}
    if len(np.unique(y_true)) < 2:
        return {**out, "pr_auc": np.nan, "roc_auc": np.nan, "recall_at_p50": np.nan}
    prec, rec, _ = precision_recall_curve(y_true, y_score)
    return {
        **out,
        "pr_auc": float(average_precision_score(y_true, y_score)),
        "roc_auc": float(roc_auc_score(y_true, y_score)),
        "recall_at_p50": recall_at_precision(prec, rec, 0.5),
    }


# --- 베이스라인 점수 ---
def persistence_score(ds: pd.DataFrame, test_pos: np.ndarray) -> np.ndarray:
    """현재 세포수로 다음 초과를 예측(현재 상태 유지). 결측은 0점."""
    return np.nan_to_num(ds["cur_cyano_cells"].to_numpy()[test_pos], nan=0.0)


def seasonal_score(ds: pd.DataFrame, train_pos: np.ndarray, test_pos: np.ndarray) -> np.ndarray:
    """train 의 월별 과거 초과율을 test 월에 매핑(train 으로만 fit → 누수 없음)."""
    month = ds["date"].dt.month.to_numpy()
    y = ds["target"].to_numpy()
    rate = pd.Series(y[train_pos]).groupby(month[train_pos]).mean()
    glob = float(y[train_pos].mean())
    return pd.Series(month[test_pos]).map(rate).fillna(glob).to_numpy()


# --- 다중분류(경보 단계, 확장2) 지표·베이스라인 ---
N_STAGES = len(STAGE_NAMES)


def evaluate_stages(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """순서형 단계 예측 지표 — 단계별 recall + macro-F1 + QWK + accuracy.

    희소·순서 특성상 accuracy 단독은 부적절. QWK(이차가중 kappa)는 '한 칸 오차'를
    '두 칸 오차'보다 덜 벌해 순서 예측에 적합하다.
    """
    y_true = np.asarray(y_true); y_pred = np.asarray(y_pred)
    labels = list(range(N_STAGES))
    rec = recall_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    qwk = (cohen_kappa_score(y_true, y_pred, labels=labels, weights="quadratic")
           if len(np.unique(y_true)) > 1 else float("nan"))
    return {
        "n": int(len(y_true)),
        "accuracy": float((y_true == y_pred).mean()),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "qwk": float(qwk),
        "recall_per_stage": {STAGE_NAMES[i]: float(rec[i]) for i in labels},
    }


def confusion_stage(y_true: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
    """행=실제, 열=예측 (단계 0..N-1)."""
    return confusion_matrix(y_true, y_pred, labels=list(range(N_STAGES)))


def persistence_stage(ds: pd.DataFrame, test_pos: np.ndarray) -> np.ndarray:
    """현재 세포수의 단계를 다음 단계로 예측(현 상태 유지) — 단계 베이스라인."""
    cur = np.nan_to_num(ds["cur_cyano_cells"].to_numpy()[test_pos], nan=0.0)
    return alert_stage(cur)
