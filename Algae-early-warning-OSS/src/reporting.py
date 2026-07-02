"""F8 Reporting — 예측 해석(SHAP) + 위험 랭킹 리포트.

LightGBM 내장 SHAP(`pred_contrib=True`)로 예측 근거를 설명한다(외부 shap 패키지 불필요).
마지막 시간 폴드(train ≤ 직전연도 → test 최신연도)로 학습·설명해 실사용 예측을 모사한다.

산출: reports/figures/shap_bar.png, shap_beeswarm.png + reports/predictions_sample.csv

실행:
    uv run python -m src.reporting
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.eda import setup_style
from src.features import assemble_dataset, feature_columns
from src.loading import REPO_ROOT
from src.modeling import CATEGORICAL, _inner_time_val, train_lgbm
from src.validation import year_splits

FIG_DIR = REPO_ROOT / "reports" / "figures"
PRED_PATH = REPO_ROOT / "reports" / "predictions_sample.csv"


def prep_coded(ds: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    """범주형을 정수 코드로(전체 기준 일관) — pred_contrib 이 수치 행렬을 요구."""
    X = ds[feats].copy()
    for c in CATEGORICAL:
        if c in X.columns:
            X[c] = X[c].astype("category").cat.codes.astype("int32")
    return X


def fit_last_fold(ds: pd.DataFrame, feats: list[str]):
    """최신 연도를 test 로 하는 마지막 시간 폴드 학습."""
    X = prep_coded(ds, feats)
    y = ds["target"].to_numpy()
    tr, te, test_year = year_splits(ds)[-1]
    itr, ival = _inner_time_val(ds["date"].to_numpy(), tr)
    model = train_lgbm(X, y, itr, ival)
    return model, X, te, test_year


def shap_contribs(model, X_te: pd.DataFrame) -> np.ndarray:
    """행×피처 SHAP 기여(마지막 열=base 는 제외)."""
    contrib = model.predict(X_te, pred_contrib=True, num_iteration=model.best_iteration)
    return np.asarray(contrib)[:, :-1]


def fig_shap_bar(shap_vals: np.ndarray, feats: list[str], top: int = 15):
    mean_abs = np.abs(shap_vals).mean(axis=0)
    order = np.argsort(mean_abs)[-top:]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.barh([feats[i] for i in order], mean_abs[order], color="#3182bd")
    ax.set_title(f"SHAP 평균 기여도 |SHAP| 상위 {top}")
    ax.set_xlabel("평균 |SHAP| (초과 위험 log-odds 기여)")
    fig.tight_layout()
    return fig


def fig_shap_beeswarm(shap_vals: np.ndarray, X_te: pd.DataFrame, feats: list[str], top: int = 12):
    order = np.argsort(np.abs(shap_vals).mean(axis=0))[-top:]
    rng = np.random.default_rng(0)
    n = len(shap_vals)
    sel = rng.choice(n, size=min(2500, n), replace=False)
    fig, ax = plt.subplots(figsize=(8, 6))
    sc = None
    for row, fidx in enumerate(order):
        sv = shap_vals[sel, fidx]
        fv = X_te.iloc[sel, fidx].to_numpy(dtype="float")
        lo, hi = np.nanpercentile(fv, [5, 95])
        cval = np.clip((fv - lo) / (hi - lo + 1e-9), 0, 1)
        yj = row + (rng.random(len(sv)) - 0.5) * 0.6
        sc = ax.scatter(sv, yj, c=cval, cmap="coolwarm", s=6, alpha=0.5, vmin=0, vmax=1)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([feats[i] for i in order])
    ax.axvline(0, color="gray", lw=0.8)
    ax.set_xlabel("SHAP value  (오른쪽 → 초과 위험 증가)")
    ax.set_title("SHAP 요약 (색: 피처값 높음=빨강 / 낮음=파랑)")
    cb = fig.colorbar(sc, ax=ax, fraction=0.03, pad=0.02)
    cb.set_ticks([0, 1]); cb.set_ticklabels(["낮음", "높음"])
    fig.tight_layout()
    return fig


def risk_table(ds, model, X, te, feats, shap_vals, k: int = 15) -> pd.DataFrame:
    """test 예측을 확률 내림차순으로 — 확률·실제·상위 기여 피처."""
    prob = model.predict(X.iloc[te], num_iteration=model.best_iteration)
    top_feats = []
    for i in range(len(te)):
        idx = np.argsort(np.abs(shap_vals[i]))[::-1][:3]
        top_feats.append(", ".join(f"{feats[j]}({'+' if shap_vals[i, j] > 0 else '-'})" for j in idx))
    out = ds.iloc[te][["site_code", "date", "target"]].copy()
    out["prob"] = prob.round(3)
    out["top_features"] = top_feats
    return out.sort_values("prob", ascending=False).head(k).reset_index(drop=True)


def main() -> None:
    plt.switch_backend("Agg")
    setup_style()
    ds = assemble_dataset()
    feats = feature_columns(ds)
    model, X, te, test_year = fit_last_fold(ds, feats)
    shap_vals = shap_contribs(model, X.iloc[te])
    print(f"해석 대상: test {test_year} — {len(te):,}건")

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig_shap_bar(shap_vals, feats).savefig(FIG_DIR / "shap_bar.png", bbox_inches="tight")
    fig_shap_beeswarm(shap_vals, X.iloc[te], feats).savefig(FIG_DIR / "shap_beeswarm.png", bbox_inches="tight")
    plt.close("all")

    risk = risk_table(ds, model, X, te, feats, shap_vals)
    PRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    risk.to_csv(PRED_PATH, index=False)
    print(f"\n=== {test_year} 위험 상위 예측 ===")
    print(risk.to_string(index=False))
    print(f"\n[저장] figures/shap_bar.png, shap_beeswarm.png + {PRED_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
