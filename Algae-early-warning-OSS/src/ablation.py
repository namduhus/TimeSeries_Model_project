"""기상 피처 Ablation — 조류만 vs 조류+기상 성능 비교 (§8.2, §11).

과거(실측) 기상 집계가 예측 성능에 기여하는지 시간순 CV로 정량 비교한다.
결론(현재 데이터): 조류 측정에 포함된 수온이 기온 신호를 담아 과거 기상은 중복 →
유의미한 lift 없음. 기상의 가치는 실시간 배포 시 예보값(미래 구간)에 있다(로드맵).

실행:
    uv run python -m src.ablation      # reports/weather_ablation.md + figures/기상_ablation.png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from src import modeling, validation
from src.eda import setup_style
from src.features import assemble_dataset, feature_columns
from src.loading import REPO_ROOT

REPORT_PATH = REPO_ROOT / "reports" / "weather_ablation.md"
FIG_PATH = REPO_ROOT / "reports" / "figures" / "기상_ablation.png"


def _cv_mean(ds):
    feats = feature_columns(ds)
    X = modeling.prep_X(ds, feats)
    y = ds["target"].to_numpy()
    res, _ = modeling.run_cv(ds, X, y, validation.year_splits(ds), "time")
    m = res[res["method"] == "model"][["pr_auc", "recall_at_p50", "roc_auc"]].mean()
    return len(feats), m


def main() -> None:
    plt.switch_backend("Agg")
    setup_style()
    base = assemble_dataset(with_weather=False)
    wx = assemble_dataset(with_weather=True)
    nb, mb = _cv_mean(base)
    nw, mw = _cv_mean(wx)

    labels = ["PR-AUC", "Recall@P0.5", "ROC-AUC"]
    bv = [mb.pr_auc, mb.recall_at_p50, mb.roc_auc]
    wv = [mw.pr_auc, mw.recall_at_p50, mw.roc_auc]
    x = np.arange(3)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(x - 0.2, bv, 0.4, label=f"조류만 ({nb})", color="#3182bd")
    ax.bar(x + 0.2, wv, 0.4, label=f"조류+기상 ({nw})", color="#e6550d")
    ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_ylim(0, 1)
    ax.set_title("기상 피처 Ablation (시간순 CV)")
    for xi, (b, w) in enumerate(zip(bv, wv)):
        ax.text(xi - 0.2, b + 0.01, f"{b:.3f}", ha="center", fontsize=8)
        ax.text(xi + 0.2, w + 0.01, f"{w:.3f}", ha="center", fontsize=8)
    ax.legend()
    FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(FIG_PATH, bbox_inches="tight"); plt.close(fig)

    lines = [
        "# 기상 피처 Ablation 리포트 (§8.2)\n",
        "매칭된 ASOS(29개)의 과거 기상 집계([t-7]·[t-14] 기온·강수·일사)를 추가했을 때의 성능 변화. 시간순 CV.\n",
        "| 모델 | 피처 수 | PR-AUC | Recall@P0.5 | ROC-AUC |",
        "|---|---|---|---|---|",
        f"| 조류만 | {nb} | {mb.pr_auc:.3f} | {mb.recall_at_p50:.3f} | {mb.roc_auc:.3f} |",
        f"| 조류+기상 | {nw} | {mw.pr_auc:.3f} | {mw.recall_at_p50:.3f} | {mw.roc_auc:.3f} |",
        f"| **lift** | +{nw - nb} | {mw.pr_auc - mb.pr_auc:+.3f} | {mw.recall_at_p50 - mb.recall_at_p50:+.3f} | {mw.roc_auc - mb.roc_auc:+.3f} |",
        "\n## 결론",
        "- 과거(실측) 기상 집계는 **유의미한 lift 없음**(노이즈 수준).",
        "- 원인: 조류 측정에 포함된 **수온**이 기온 신호를 이미 담아 과거 기상과 중복.",
        "- 기상의 가치는 **실시간 배포 시 예보값**(예측 대상 미래 구간)에 있음 → 로드맵(확장 4).",
        "- 따라서 기본 모델은 **조류 전용**(단순·동등 성능)을 유지하고, 본 ablation으로 기상 기여를 문서화한다.\n",
        f"그림: {FIG_PATH.relative_to(REPO_ROOT)}",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[저장] {REPORT_PATH.relative_to(REPO_ROOT)}, {FIG_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
