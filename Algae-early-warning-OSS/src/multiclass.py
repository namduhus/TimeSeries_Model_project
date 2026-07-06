"""F6b 다중분류(경보 단계) — 누적 이진(ordinal)으로 정상/관심/경계이상 예측.

확장2. 기존 이진 파이프라인(F6)을 임계 2개(1,000·10,000)로 재사용한다:
각 폴드에서 이진 모델 2개를 학습해 P(≥관심)·P(≥경계이상)를 얻고, 단조성 보정 후
단계를 도출한다. 데이터·피처(F1~F4)와 누수 방어(시간순/지점 분할)는 이진과 완전 동일.

이진(관심) 헤드라인 모델(src.modeling)은 그대로 두고, 이 모듈은 확장 산출물만 만든다:
    uv run python -m src.multiclass   # reports/model_multiclass.md + figures/모델_혼동행렬.png
"""

from __future__ import annotations

import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.eda import setup_style
from src.features import assemble_dataset, feature_columns
from src.loading import REPO_ROOT
from src.modeling import MODEL_PATH, _git_commit, _inner_time_val, load_model, prep_X, train_lgbm, train_production
from src.target import STAGE_NAMES, STAGE_THRESHOLDS, alert_stage
from src.validation import (
    confusion_stage,
    evaluate_stages,
    persistence_stage,
    site_splits,
    year_splits,
)

import matplotlib.pyplot as plt

FIG_DIR = REPO_ROOT / "reports" / "figures"
REPORT_PATH = REPO_ROOT / "reports" / "model_multiclass.md"
STAGE_MODEL_PATH = REPO_ROOT / "models" / "algae_lgbm_ge10000.txt"  # 경계이상(≥10k) production
STAGE_CARD_PATH = REPO_ROOT / "models" / "stage_model_card.json"
TAU = 0.5  # 각 임계 확률 컷(운영 시 단계별 recall 목표로 튜닝 가능)


def cumulative_stage(p_low: np.ndarray, p_high: np.ndarray, tau: float = TAU) -> np.ndarray:
    """두 누적 이진 확률 → 단계(0/1/2). 단조성(P(≥경계) ≤ P(≥관심)) 보정 후 임계 적용."""
    p_high = np.minimum(p_high, p_low)              # 논리적 단조성 강제
    return (p_low >= tau).astype("int8") + (p_high >= tau).astype("int8")


# --- 단계 예측 모델 게시·서빙 (대시보드/제9조) ---
def save_stage_model(ds, X, feats, model_path=STAGE_MODEL_PATH, card_path=STAGE_CARD_PATH) -> lgb.Booster:
    """경계이상(≥10,000) production 모델을 게시. 관심(≥1,000)은 기존 algae_lgbm.txt 재사용.

    두 모델 + cumulative_stage 로 3단계(정상/관심/경계이상)를 서빙한다.
    """
    y_high = (ds["label_cyano"].to_numpy() >= STAGE_THRESHOLDS[1]).astype("int8")
    booster = train_production(X, y_high, ds["date"].to_numpy())
    model_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(model_path))

    card = {
        "task": "경보 단계 예측(정상/관심/경계이상) — 누적 이진",
        "stage_names": list(STAGE_NAMES),
        "stage_thresholds_cells_per_ml": list(STAGE_THRESHOLDS),
        "tau": TAU,
        "models": {
            "ge_1000_관심": MODEL_PATH.name,          # 기존 게시 이진 모델 재사용
            "ge_10000_경계이상": model_path.name,
        },
        "rule": "stage = (p_ge1000>=tau) + (p_ge10000>=tau); 단조성 보정 p_high=min(p_high,p_low)",
        "features": feats,
        "lightgbm_version": lgb.__version__,
        "git_commit": _git_commit(),
        "license": "MIT",
    }
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return booster


def load_stage_models():
    """서빙용 로드 — (관심 booster, 경계이상 booster, 카드). 관심=게시된 algae_lgbm.txt."""
    booster_low, _ = load_model()                                    # ≥1,000 (관심)
    booster_high = lgb.Booster(model_file=str(STAGE_MODEL_PATH))     # ≥10,000 (경계이상)
    card = json.loads(STAGE_CARD_PATH.read_text(encoding="utf-8"))
    return booster_low, booster_high, card


def predict_stage(X, booster_low, booster_high, tau: float = TAU):
    """피처행 → (단계, p_관심, p_경계이상). 단조성 보정된 확률 반환."""
    p_low = booster_low.predict(X)
    p_high = np.minimum(booster_high.predict(X), p_low)
    stage = (p_low >= tau).astype("int8") + (p_high >= tau).astype("int8")
    return stage, p_low, p_high


def run_stage_cv(ds: pd.DataFrame, X: pd.DataFrame, splits, axis: str):
    """폴드별 누적 이진 2개 학습 → 단계 OOF 예측 + persistence 베이스라인."""
    dates = ds["date"].to_numpy()
    label_cyano = ds["label_cyano"].to_numpy()
    y_low = (label_cyano >= STAGE_THRESHOLDS[0]).astype("int8")
    y_high = (label_cyano >= STAGE_THRESHOLDS[1]).astype("int8")
    stage_true = alert_stage(label_cyano)

    oof_true = np.full(len(ds), -1, dtype="int8")
    oof_model = np.full(len(ds), -1, dtype="int8")
    oof_base = np.full(len(ds), -1, dtype="int8")
    for tr, te, _ in splits:
        itr, ival = _inner_time_val(dates, tr)
        m_low = train_lgbm(X, y_low, itr, ival)
        m_high = train_lgbm(X, y_high, itr, ival)
        p_low = m_low.predict(X.iloc[te], num_iteration=m_low.best_iteration)
        p_high = m_high.predict(X.iloc[te], num_iteration=m_high.best_iteration)
        oof_model[te] = cumulative_stage(p_low, p_high)
        oof_base[te] = persistence_stage(ds, te)
        oof_true[te] = stage_true[te]

    seen = oof_true >= 0
    return oof_true[seen], oof_model[seen], oof_base[seen]


def _fmt_stage_table(model_m: dict, base_m: dict) -> str:
    lines = ["| 방법 | Accuracy | macro-F1 | QWK | " + " | ".join(f"recall:{s}" for s in STAGE_NAMES) + " |",
             "|---|---|---|---|" + "---|" * len(STAGE_NAMES)]
    for name, m in [("누적 이진(LightGBM)", model_m), ("persistence(현 단계 유지)", base_m)]:
        rec = " | ".join(f"{m['recall_per_stage'][s]:.3f}" for s in STAGE_NAMES)
        lines.append(f"| {name} | {m['accuracy']:.3f} | {m['macro_f1']:.3f} | {m['qwk']:.3f} | {rec} |")
    return "\n".join(lines)


def fig_confusion(cm: np.ndarray):
    fig, ax = plt.subplots(figsize=(5, 4.5))
    im = ax.imshow(cm, cmap="Oranges")
    ax.set_xticks(range(len(STAGE_NAMES)), STAGE_NAMES)
    ax.set_yticks(range(len(STAGE_NAMES)), STAGE_NAMES)
    ax.set_xlabel("예측"); ax.set_ylabel("실제")
    ax.set_title("혼동행렬 (시간순 OOF) — 경보 단계")
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, f"{cm[i, j]:,}", ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    return fig


def main() -> None:
    plt.switch_backend("Agg")
    setup_style()
    ds = assemble_dataset()
    feats = feature_columns(ds)
    X = prep_X(ds, feats)

    yt, ym, yb = run_stage_cv(ds, X, year_splits(ds), "time")
    model_m, base_m = evaluate_stages(yt, ym), evaluate_stages(yt, yb)
    st, sm, _ = run_stage_cv(ds, X, site_splits(ds), "site")
    site_m = evaluate_stages(st, sm)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    cm = confusion_stage(yt, ym)
    fig = fig_confusion(cm)
    fig.savefig(FIG_DIR / "모델_혼동행렬.png", bbox_inches="tight")
    plt.close(fig)

    dist = pd.Series(alert_stage(ds["label_cyano"].to_numpy())).value_counts().sort_index()
    lines = [
        "# 다중분류 평가 리포트 — 경보 단계 (F6b, 확장2)\n",
        f"단계 정의(cells/mL): 정상<{STAGE_THRESHOLDS[0]:,} · 관심 {STAGE_THRESHOLDS[0]:,}~{STAGE_THRESHOLDS[1]:,} · 경계이상 ≥{STAGE_THRESHOLDS[1]:,}",
        f"방식: 누적 이진 2개(P≥관심, P≥경계이상) + 단조성 보정, 컷 τ={TAU}\n",
        "## 단계 분포 (라벨=다음 측정)",
        " / ".join(f"{STAGE_NAMES[i]} {int(dist.get(i, 0)):,}" for i in range(len(STAGE_NAMES))) + "\n",
        "## 시간 일반화 (확장 윈도우 연도 분할, pooled OOF)\n", _fmt_stage_table(model_m, base_m),
        "\n\n## 지점 일반화 (지점 GroupKFold, pooled OOF)\n",
        f"- accuracy {site_m['accuracy']:.3f} | macro-F1 {site_m['macro_f1']:.3f} | QWK {site_m['qwk']:.3f}",
        f"- 경계이상 recall {site_m['recall_per_stage'][STAGE_NAMES[-1]]:.3f}\n",
        "혼동행렬: reports/figures/모델_혼동행렬.png\n",
        f"> 참고: 경계이상은 희소({int(dist.get(2, 0)):,}건)해 지표 분산이 크다. recall·표본수 병기로 해석.",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    # 단계 서빙용 경계이상(≥10k) production 모델 게시 (대시보드/제9조)
    save_stage_model(ds, X, feats)

    print("[시간 일반화 · 단계]"); print(_fmt_stage_table(model_m, base_m))
    print(f"\n[저장] {REPORT_PATH.relative_to(REPO_ROOT)} + figures/모델_혼동행렬.png")
    print(f"[저장] {STAGE_MODEL_PATH.relative_to(REPO_ROOT)} + {STAGE_CARD_PATH.name} (단계 서빙 모델)")


if __name__ == "__main__":
    main()
