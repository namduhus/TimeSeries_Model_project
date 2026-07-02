"""F5 Target Building — 다음 측정 기반 이진 조기경보 라벨 생성.

각 (지점, 측정일 t)에 대해 **다음 측정치**의 유해남조류 세포수가 임계를 초과하는지를
라벨로 만든다. 프로젝트 최우선 원칙(§8.3 누수 방지)을 코드로 강제한다:

- 라벨은 미래(다음 측정, label_date > t)에서만 만든다.
- 예측 시야(horizon)가 목표 창[min_gap, max_gap] 밖인 샘플은 유효 샘플에서 제외한다
  (불규칙 샘플링 통제, F2: 91%가 5~8일 주간).
- `label_cyano`/`label_date`/`horizon_days`는 라벨 생성 근거(provenance)일 뿐 **피처가 아니다.**
  특히 horizon_days는 예측 시점 t에 알 수 없는 미래 정보이므로 피처로 쓰면 누수다.

확정 파라미터(F2 근거, §6·§16): threshold=1000 cells/mL(관심), 창=4~10일.

실행:
    uv run python -m src.target        # 타깃 분포 요약 출력 + data/interim/targets.csv 저장
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.loading import REPO_ROOT, clean_algae, load_algae, load_sites

DEFAULT_THRESHOLD = 1000        # cells/mL (관심 단계)
DEFAULT_MIN_GAP = 4             # 예측 시야 하한(일)
DEFAULT_MAX_GAP = 10            # 예측 시야 상한(일)
OUTPUT_PATH = REPO_ROOT / "data" / "interim" / "targets.csv"

LABEL_COLUMNS = ["site_code", "date", "label_date", "horizon_days", "label_cyano", "target"]


def build_targets(
    df: pd.DataFrame,
    sites: pd.DataFrame | None = None,
    threshold: int = DEFAULT_THRESHOLD,
    min_gap_days: int = DEFAULT_MIN_GAP,
    max_gap_days: int = DEFAULT_MAX_GAP,
) -> pd.DataFrame:
    """표준 조류 DataFrame → 유효 예측점별 이진 라벨 테이블.

    반환 컬럼: site_code, date(예측시점 t), label_date, horizon_days, label_cyano, target(0/1).
    유효 샘플 = 다음 측정이 존재하고, horizon_days ∈ [min_gap, max_gap], label_cyano 비결측.
    """
    clean = clean_algae(df, sites)
    clean = clean.dropna(subset=["date"]).drop_duplicates(["site_code", "date"])
    clean = clean.sort_values(["site_code", "date"])

    grp = clean.groupby("site_code", sort=False)
    clean["label_date"] = grp["date"].shift(-1)       # 다음 측정일(미래)
    clean["label_cyano"] = grp["cyano_cells"].shift(-1)  # 다음 측정의 세포수 → 라벨 원천
    clean["horizon_days"] = (clean["label_date"] - clean["date"]).dt.days

    valid = (
        clean["label_cyano"].notna()
        & clean["horizon_days"].between(min_gap_days, max_gap_days)
    )
    out = clean.loc[valid, ["site_code", "date", "label_date", "horizon_days", "label_cyano"]].copy()
    out["target"] = (out["label_cyano"] >= threshold).astype("int8")
    return out.reset_index(drop=True)


def main() -> None:
    targets = build_targets(load_algae(), load_sites())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    targets.to_csv(OUTPUT_PATH, index=False)

    n = len(targets)
    pos = int(targets["target"].sum())
    print(f"유효 샘플: {n:,} | 지점: {targets['site_code'].nunique()}")
    print(f"양성(초과): {pos:,} ({pos / n * 100:.2f}%) | 음성: {n - pos:,}")
    print(f"horizon(일): 중앙 {targets['horizon_days'].median():.0f}, "
          f"범위 {targets['horizon_days'].min():.0f}~{targets['horizon_days'].max():.0f}")
    print(f"기간: {targets['date'].min().date()} ~ {targets['date'].max().date()}")
    print(f"[저장] {OUTPUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
