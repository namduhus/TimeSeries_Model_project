"""F6 Modeling + 평가 오케스트레이션 (LightGBM, 시간순/지점 CV).

베이스라인(persistence·계절) 대비 LightGBM 의 lift 를 시간 일반화·지점 일반화 축에서
평가하고, PR 커브·연도별 지표·피처 중요도 그림과 reports/model_eval.md 를 만든다.

누수 방지: 피처는 인과적(F4), 분할은 시간순/지점(F7). test 에 fitting하는 전처리 없음.
재현성(§9): 고정 시드 + LightGBM deterministic.

실행:
    uv run python -m src.modeling      # reports/model_eval.md + reports/figures/모델*.png
"""

from __future__ import annotations

import json
import subprocess

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve, roc_curve

from src.eda import setup_style
from src.features import assemble_dataset, feature_columns
from src.loading import REPO_ROOT
from src.target import DEFAULT_THRESHOLD
from src.validation import (
    evaluate,
    persistence_score,
    seasonal_score,
    site_splits,
    year_splits,
)

import matplotlib.pyplot as plt

SEED = 42
CATEGORICAL = ["site_code", "major_basin", "station_type"]
FIG_DIR = REPO_ROOT / "reports" / "figures"
REPORT_PATH = REPO_ROOT / "reports" / "model_eval.md"
MODEL_DIR = REPO_ROOT / "models"
MODEL_PATH = MODEL_DIR / "algae_lgbm.txt"
CARD_PATH = MODEL_DIR / "model_card.json"

LGB_PARAMS = dict(
    objective="binary",
    metric="auc",
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=30,
    feature_fraction=0.8,
    bagging_fraction=0.8,
    bagging_freq=1,
    seed=SEED,
    deterministic=True,
    force_col_wise=True,
    verbose=-1,
)


def prep_X(ds: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """피처 프레임 — 범주형은 category dtype(전체 기준으로 고정해 폴드 간 일관)."""
    X = ds[feature_cols].copy()
    for c in CATEGORICAL:
        if c in X.columns:
            X[c] = X[c].astype("category")
    return X


def _inner_time_val(dates: np.ndarray, train_pos: np.ndarray, frac: float = 0.2):
    """train 을 시간순 정렬해 마지막 frac 을 early-stopping 검증셋으로."""
    order = np.argsort(dates[train_pos], kind="stable")
    tp = train_pos[order]
    cut = max(1, int(len(tp) * (1 - frac)))
    return tp[:cut], tp[cut:]


def train_lgbm(X: pd.DataFrame, y: np.ndarray, tr: np.ndarray, val: np.ndarray) -> lgb.Booster:
    cats = [c for c in CATEGORICAL if c in X.columns]
    pos = int(y[tr].sum())
    params = {**LGB_PARAMS, "scale_pos_weight": (len(tr) - pos) / max(pos, 1)}
    dtr = lgb.Dataset(X.iloc[tr], y[tr], categorical_feature=cats, free_raw_data=False)
    dval = lgb.Dataset(X.iloc[val], y[val], reference=dtr, free_raw_data=False)
    return lgb.train(
        params, dtr, num_boost_round=1000, valid_sets=[dval],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
    )


def run_cv(ds: pd.DataFrame, X: pd.DataFrame, y: np.ndarray, splits, axis: str) -> tuple[pd.DataFrame, dict]:
    """폴드별 모델·베이스라인 평가 + pooled OOF 예측 반환."""
    dates = ds["date"].to_numpy()
    rows = []
    oof = {"y": np.full(len(ds), np.nan), "model": np.full(len(ds), np.nan),
           "persistence": np.full(len(ds), np.nan), "seasonal": np.full(len(ds), np.nan)}
    for tr, te, label in splits:
        itr, ival = _inner_time_val(dates, tr)
        model = train_lgbm(X, y, itr, ival)
        pred = model.predict(X.iloc[te], num_iteration=model.best_iteration)
        scores = {"model": pred, "persistence": persistence_score(ds, te),
                  "seasonal": seasonal_score(ds, tr, te)}
        for method, sc in scores.items():
            m = evaluate(y[te], sc)
            rows.append({"axis": axis, "fold": label, "method": method, **m})
            oof[method][te] = sc
        oof["y"][te] = y[te]
    return pd.DataFrame(rows), oof


def _fmt_table(res: pd.DataFrame) -> str:
    """method×지표 평균 표(markdown)."""
    agg = res.groupby("method")[["pr_auc", "recall_at_p50", "roc_auc"]].mean().round(3)
    agg = agg.reindex(["model", "persistence", "seasonal"])
    lines = ["| method | PR-AUC | Recall@P0.5 | ROC-AUC |", "|---|---|---|---|"]
    names = {"model": "LightGBM", "persistence": "persistence", "seasonal": "계절규칙"}
    for m, r in agg.iterrows():
        lines.append(f"| {names[m]} | {r['pr_auc']:.3f} | {r['recall_at_p50']:.3f} | {r['roc_auc']:.3f} |")
    return "\n".join(lines)


def fig_pr_curve(oof: dict):
    fig, ax = plt.subplots(figsize=(6, 5))
    mask = ~np.isnan(oof["y"])
    yt = oof["y"][mask]
    for method, color, lbl in [("model", "#e6550d", "LightGBM"),
                               ("persistence", "#3182bd", "persistence"),
                               ("seasonal", "#74c476", "계절규칙")]:
        sc = np.nan_to_num(oof[method][mask], nan=0.0)
        prec, rec, _ = precision_recall_curve(yt, sc)
        ax.plot(rec, prec, color=color, label=lbl)
    ax.axhline(yt.mean(), ls=":", color="gray", label=f"무작위({yt.mean():.2f})")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_title("PR 커브 (시간순 OOF) — 모델 vs 베이스라인")
    ax.legend(); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    fig.tight_layout()
    return fig


def fig_yearly(res: pd.DataFrame):
    piv = res[res["method"].isin(["model", "persistence"])].pivot(index="fold", columns="method", values="pr_auc")
    fig, ax = plt.subplots(figsize=(7, 4))
    piv.plot(kind="bar", ax=ax, color={"model": "#e6550d", "persistence": "#3182bd"})
    ax.set_title("연도별 PR-AUC — 모델 vs persistence")
    ax.set_xlabel("test 연도"); ax.set_ylabel("PR-AUC"); ax.legend(title="")
    fig.tight_layout()
    return fig


def fig_importance(model: lgb.Booster, top: int = 15):
    imp = pd.Series(model.feature_importance("gain"), index=model.feature_name()).sort_values()[-top:]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.barh(imp.index, imp.values, color="#756bb1")
    ax.set_title(f"피처 중요도 (gain) 상위 {top}")
    fig.tight_layout()
    return fig


def _git_commit() -> str | None:
    """게시 모델의 재현 추적용 짧은 커밋 해시(비저장소·오류 시 None)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def train_production(X: pd.DataFrame, y: np.ndarray, dates: np.ndarray) -> lgb.Booster:
    """게시용 production 모델 — 시간순 inner-val 로 best_iteration 을 찾은 뒤 **전체 데이터**로 재학습.

    CV 지표(리포트)는 OOF 기준이고, 이 모델은 실제 '다음 +7일' 예측에 쓸 전량 학습본이다.
    """
    all_pos = np.arange(len(y))
    itr, ival = _inner_time_val(dates, all_pos)
    tuned = train_lgbm(X, y, itr, ival)
    best = max(tuned.best_iteration or tuned.num_trees(), 1)

    cats = [c for c in CATEGORICAL if c in X.columns]
    pos = int(y.sum())
    params = {**LGB_PARAMS, "scale_pos_weight": (len(y) - pos) / max(pos, 1)}
    dall = lgb.Dataset(X, y, categorical_feature=cats, free_raw_data=False)
    return lgb.train(params, dall, num_boost_round=best, callbacks=[lgb.log_evaluation(0)])


def save_production_model(
    ds: pd.DataFrame, X: pd.DataFrame, y: np.ndarray, feats: list[str], cv_metrics: dict,
    model_path=MODEL_PATH, card_path=CARD_PATH,
) -> lgb.Booster:
    """전량 학습 모델을 LightGBM 네이티브 .txt 로 저장하고 모델 카드(JSON)를 남긴다.

    가중치 공개(대회 제9조)와 제9조④ 모델 정보서의 근거 자료로 쓰인다.
    """
    booster = train_production(X, y, ds["date"].to_numpy())
    model_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(model_path))

    card = {
        "model": "LightGBM Booster (objective=binary)",
        "task": "다음 측정(≈+7일) 유해남조류 세포수 관심단계 임계 초과 이진 예측",
        "target_threshold_cells_per_ml": DEFAULT_THRESHOLD,
        "features": feats,
        "categorical_features": [c for c in CATEGORICAL if c in X.columns],
        "params": {**LGB_PARAMS, "num_boost_round": booster.num_trees()},
        "seed": SEED,
        "n_train_rows": int(len(ds)),
        "date_range": [str(ds["date"].min().date()), str(ds["date"].max().date())],
        "positive_rate": round(float(y.mean()), 4),
        "cv_metrics_time_pooled": {k: round(float(v), 4) for k, v in cv_metrics.items()},
        "lightgbm_version": lgb.__version__,
        "git_commit": _git_commit(),
        "license": "MIT",
        "data_source": "국립환경과학원 조류경보제(공공누리 제1유형) + 기상청 ASOS 일자료",
    }
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return booster


def load_model(model_path=MODEL_PATH, card_path=CARD_PATH) -> tuple[lgb.Booster, dict]:
    """게시된 가중치·모델 카드를 로드(재현·서빙용)."""
    booster = lgb.Booster(model_file=str(model_path))
    card = json.loads(card_path.read_text(encoding="utf-8"))
    return booster, card


def main() -> None:
    plt.switch_backend("Agg")
    setup_style()
    ds = assemble_dataset()
    feats = feature_columns(ds)
    X, y = prep_X(ds, feats), ds["target"].to_numpy()

    ysp = year_splits(ds)
    ssp = site_splits(ds)
    print(f"시간 폴드: {[s[2] for s in ysp]} | 지점 폴드: {len(ssp)}")
    res_time, oof_time = run_cv(ds, X, y, ysp, "time")
    res_site, _ = run_cv(ds, X, y, ssp, "site")

    # 피처 중요도용 최종 모델(마지막 시간 폴드: 최신 이전 전부로 학습)
    tr_all, val_all = _inner_time_val(ds["date"].to_numpy(), ysp[-1][0])
    final = train_lgbm(X, y, tr_all, val_all)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for name, fig in [("모델_pr_curve", fig_pr_curve(oof_time)),
                      ("모델_yearly_prauc", fig_yearly(res_time)),
                      ("모델_feature_importance", fig_importance(final))]:
        fig.savefig(FIG_DIR / f"{name}.png", bbox_inches="tight")
        plt.close(fig)

    # 리포트
    pooled = {m: evaluate(oof_time["y"][~np.isnan(oof_time["y"])],
                          oof_time[m][~np.isnan(oof_time["y"])]) for m in ["model", "persistence", "seasonal"]}
    lines = ["# 모델 평가 리포트 (F6+F7)\n",
             f"데이터셋 {len(ds):,}행 × 피처 {len(feats)} | 양성률 {y.mean()*100:.1f}% | seed {SEED}\n",
             "## 시간 일반화 (확장 윈도우 연도 분할, 평균)\n", _fmt_table(res_time),
             "\n\n## 지점 일반화 (지점 GroupKFold, 평균)\n", _fmt_table(res_site),
             "\n\n## 시간순 pooled OOF\n",
             f"- LightGBM PR-AUC **{pooled['model']['pr_auc']:.3f}** / persistence {pooled['persistence']['pr_auc']:.3f} / 계절 {pooled['seasonal']['pr_auc']:.3f}",
             f"- LightGBM Recall@P0.5 **{pooled['model']['recall_at_p50']:.3f}** / persistence {pooled['persistence']['recall_at_p50']:.3f}\n",
             "그림: reports/figures/모델_pr_curve.png, 모델_yearly_prauc.png, 모델_feature_importance.png\n"]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    # 게시용 production 모델(전량 학습) 저장 — 가중치 공개(제9조)
    save_production_model(ds, X, y, feats, pooled["model"])

    print("\n[시간 일반화]"); print(_fmt_table(res_time))
    print("\n[지점 일반화]"); print(_fmt_table(res_site))
    print(f"\n[저장] {REPORT_PATH.relative_to(REPO_ROOT)} + figures/모델_*.png")
    print(f"[저장] {MODEL_PATH.relative_to(REPO_ROOT)} + {CARD_PATH.name} (게시 모델·카드)")


if __name__ == "__main__":
    main()
