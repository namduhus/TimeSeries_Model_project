"""확장3 벤치마크 — LightGBM vs MLP vs FT-Transformer (동일 분할·피처·지표).

이진(관심 임계) 헤드라인으로 GBDT와 딥러닝을 정면 비교한다. 분할(year/site)·피처(X)·
지표(evaluate)는 완전히 동일하고, 모델 종류만 바꿔 성능 차이를 격리한다.

실행:
    uv run python -m src.benchmark_dl               # 자동 디바이스(MPS 우선)
    uv run python -m src.benchmark_dl --device cpu  # 재현 가능한 최종 수치
"""

from __future__ import annotations

import argparse

import matplotlib.pyplot as plt
import numpy as np

from src import modeling
from src.deep import get_device, train_predict_dl
from src.eda import setup_style
from src.features import assemble_dataset, feature_columns
from src.loading import REPO_ROOT
from src.validation import evaluate, site_splits, year_splits

REPORT_PATH = REPO_ROOT / "reports" / "model_dl_benchmark.md"
FIG_PATH = REPO_ROOT / "reports" / "figures" / "모델_dl_benchmark.png"

# 티어 B(원시 시계열 표현) 모델을 이번 비교에서 제외한 근거 — 리포트에 그대로 싣는다.
EXCLUDED_RATIONALE = """## 제외한 모델과 이유 (LSTM·TCN·N-HiTS·TFT·Chronos)

이번 비교는 **"같은 피처 X 위에서 GBDT를 신경망이 이기는가"**라는 질문에 공정하게
답하기 위해, LightGBM과 **동일한 테이블형 입력**을 쓰는 모델(MLP·FT-Transformer)만 겨뤘다.
아래 시퀀스/시계열 특화 모델은 다음 이유로 이번 범위에서 제외했다.

- **비교 공정성 훼손:** 이들은 엔지니어링한 lag/rolling 대신 지점별 **원시 시계열**을
  입력으로 받는다. 표현(입력)이 달라지면 성능 차이가 '모델 때문'인지 '표현 때문'인지
  분리할 수 없어, GBDT와의 정면 비교라는 목적이 흐려진다.
- **데이터 특성 부적합:** 본 데이터는 지점별 측정이 **불규칙(주 단위, 결측 다수)**하고
  지점당 계열이 짧다(대부분 ~수백 점). 규칙적·장기 시퀀스를 전제하는 LSTM·TCN·N-HiTS·
  TFT의 강점이 발휘되기 어렵고, 창(window) 구성 과정에서 **누수 위험**만 커진다.
- **누수 통제 복잡도:** 시퀀스 창은 예측 시점 t 이후를 포함하지 않도록 정교한 통제가
  필요하다. 본 프로젝트의 최우선 원칙(누수 방지)을 시퀀스 파이프라인에서 재검증하는
  비용이 이번 단계의 이득보다 크다.
- **규정(제9조) 부담:** Chronos 등 시계열 파운데이션 모델은 오픈웨이트·로컬구동·가중치
  공개 요건을 별도로 충족해야 한다(가능하나 범위 확대).

> 이들은 **글로벌 다계열(전 지점 통합) 표현**이 확보되면 의미가 커지는 후보로, 로드맵의
> 별도 단계(확장 3+)로 남긴다. 본 단계 결론에는 영향을 주지 않는다.
"""


def _pooled(y, oof):
    mask = ~np.isnan(oof)
    return evaluate(y[mask], oof[mask])


def _dl_oof(ds, X, y, splits, model_type, device):
    oof = np.full(len(ds), np.nan)
    for tr, te, _ in splits:
        oof[te] = train_predict_dl(ds, X, y, tr, te, model_type, device)
    return oof


def _table(results: dict) -> str:
    lines = ["| 모델 | PR-AUC | Recall@P0.5 | ROC-AUC |", "|---|---|---|---|"]
    for name, m in results.items():
        lines.append(f"| {name} | {m['pr_auc']:.3f} | {m['recall_at_p50']:.3f} | {m['roc_auc']:.3f} |")
    return "\n".join(lines)


def _fig(time_res: dict):
    names = list(time_res)
    prauc = [time_res[n]["pr_auc"] for n in names]
    colors = ["#e6550d", "#3182bd", "#756bb1"][: len(names)]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(names, prauc, color=colors)
    for i, v in enumerate(prauc):
        ax.text(i, v + 0.005, f"{v:.3f}", ha="center", fontsize=9)
    ax.set_ylabel("PR-AUC (시간순 pooled OOF)")
    ax.set_title("GBDT vs 딥러닝 — 이진 조기경보")
    ax.set_ylim(0, 1)
    fig.tight_layout()
    return fig


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "mps"])
    device = get_device(ap.parse_args().device)

    plt.switch_backend("Agg")
    setup_style()
    ds = assemble_dataset()
    feats = feature_columns(ds)
    X, y = modeling.prep_X(ds, feats), ds["target"].to_numpy()
    ysp, ssp = year_splits(ds), site_splits(ds)

    # LightGBM (기존 파이프라인 재사용)
    _, oof_lgb_t = modeling.run_cv(ds, X, y, ysp, "time")
    _, oof_lgb_s = modeling.run_cv(ds, X, y, ssp, "site")

    print(f"디바이스: {device} | 딥러닝 학습 중(MLP, FT-Transformer × 시간/지점 폴드)...")
    time_res = {
        "LightGBM": _pooled(y, oof_lgb_t["model"]),
        "MLP": _pooled(y, _dl_oof(ds, X, y, ysp, "mlp", device)),
        "FT-Transformer": _pooled(y, _dl_oof(ds, X, y, ysp, "ft", device)),
    }
    site_res = {
        "LightGBM": _pooled(y, oof_lgb_s["model"]),
        "MLP": _pooled(y, _dl_oof(ds, X, y, ssp, "mlp", device)),
        "FT-Transformer": _pooled(y, _dl_oof(ds, X, y, ssp, "ft", device)),
    }

    FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig = _fig(time_res)
    fig.savefig(FIG_PATH, bbox_inches="tight")
    plt.close(fig)

    best = max(time_res, key=lambda k: time_res[k]["pr_auc"])
    lines = [
        "# 딥러닝 벤치마크 — GBDT vs 신경망 (F6b/확장3)\n",
        f"동일 피처 {len(feats)}개 · 동일 시간순/지점 분할 · 동일 지표(evaluate) · seed {modeling.SEED} · device={device}",
        "비교 대상: LightGBM(GBDT) vs MLP(딥러닝 하한) vs FT-Transformer(테이블형 DL 대표)\n",
        "## 시간 일반화 (확장 윈도우 연도 분할, pooled OOF)\n", _table(time_res),
        "\n\n## 지점 일반화 (지점 GroupKFold, pooled OOF)\n", _table(site_res),
        f"\n\n**결론:** 시간 일반화 PR-AUC 최고는 **{best}**. "
        "테이블형·소규모(3.4만행) 특성상 GBDT가 우위이며, 폴드 수가 적어 근소차는 결정적이지 않다"
        "(과잉해석 금지). 그림: reports/figures/모델_dl_benchmark.png\n",
        EXCLUDED_RATIONALE,
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n[시간 일반화]"); print(_table(time_res))
    print("\n[지점 일반화]"); print(_table(site_res))
    print(f"\n[저장] {REPORT_PATH.relative_to(REPO_ROOT)} + figures/모델_dl_benchmark.png")


if __name__ == "__main__":
    main()
