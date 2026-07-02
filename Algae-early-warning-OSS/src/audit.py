"""F2 Data Audit — 조류 원자료의 커버리지·측정 간격·결측·타깃 분포 점검.

불규칙 샘플링 실태와 타깃 불균형을 정량화해 §16 결정(지점 범위·임계값)과
타깃 프레이밍(다음 측정 vs 고정 +7일) 근거를 만든다. 원자료는 변형하지 않고 읽기만 한다.

실행:
    uv run python -m src.audit           # reports/f2_audit.md 생성 + 요약 출력
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.loading import NUMERIC_COLS, REPO_ROOT, load_algae, load_sites

REPORT_PATH = REPO_ROOT / "reports" / "f2_audit.md"

# 조류경보제(상수원 구간) 유해남조류 세포수 경보 기준(cells/mL) + 세부
THRESHOLDS = [1000, 10000, 100000, 1000000]
GAP_BINS = [0, 2, 4, 8, 14, 31, 100000]
GAP_LABELS = ["≤2일", "3-4일", "5-8일(주간)", "9-14일", "15-31일", ">31일"]


def split_known(df: pd.DataFrame, sites: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """마스터 화이트리스트로 실지점/테스트더미를 분리. (정제 df, 더미코드 리스트) 반환."""
    master = set(sites["site_code"])
    dummies = sorted(set(df["site_code"].dropna()) - master)
    clean = df[df["site_code"].isin(master)].merge(
        sites[["site_code", "station_type", "major_basin"]], on="site_code", how="left"
    )
    return clean, dummies


def compute(df: pd.DataFrame, sites: pd.DataFrame) -> dict:
    clean, dummies = split_known(df, sites)

    # 측정 간격(연속 측정 사이 일수)
    u = clean.drop_duplicates(["site_code", "date"]).sort_values(["site_code", "date"])
    gaps = u.groupby("site_code")["date"].diff().dt.days.dropna()
    gap_buckets = (
        pd.cut(gaps, GAP_BINS, labels=GAP_LABELS)
        .value_counts(normalize=True)
        .reindex(GAP_LABELS)
        .mul(100).round(1)
    )

    cc = clean["cyano_cells"].dropna()
    exceed = {thr: (float((cc >= thr).mean()) * 100, int((cc >= thr).sum())) for thr in THRESHOLDS}

    # 월별 측정 수 / 초과(≥1000) 비율 — 계절성
    by_month = clean.groupby(clean["date"].dt.month)
    monthly = pd.DataFrame({
        "measurements": by_month.size(),
        "exceed_1000_pct": by_month["cyano_cells"].apply(lambda s: float((s.dropna() >= 1000).mean()) * 100),
    }).round(1)

    return {
        "rows_raw": len(df),
        "date_min": df["date"].min(),
        "date_max": df["date"].max(),
        "dummies": dummies,
        "dummy_rows": int(df["site_code"].isin(dummies).sum()),
        "rows_clean": len(clean),
        "sites_with_data": clean["site_code"].nunique(),
        "sites_master": len(sites),
        "coverage_by_type": sites.assign(has_data=sites["site_code"].isin(clean["site_code"]))
            .groupby("station_type")["has_data"].agg(["sum", "count"]),
        "rows_per_site": clean.groupby("site_code").size().describe(),
        "dup_site_date": int(clean.duplicated(["site_code", "date"]).sum()),
        "gap_median": float(gaps.median()),
        "gap_mean": float(gaps.mean()),
        "gap_buckets": gap_buckets,
        "cc_missing_pct": float(clean["cyano_cells"].isna().mean()) * 100,
        "all_nan_rows": int(clean[NUMERIC_COLS].isna().all(axis=1).sum()),
        "cc_quantiles": cc.quantile([0.5, 0.9, 0.95, 0.99]),
        "cc_max": float(cc.max()),
        "exceed": exceed,
        "monthly": monthly,
        "type_pos": clean.groupby("station_type")["cyano_cells"].apply(
            lambda s: float((s.dropna() > 0).mean()) * 100
        ),
    }


def format_report(s: dict) -> str:
    L = []
    L.append("# F2 데이터 감사 리포트 (조류경보제 측정결과)\n")
    L.append(f"- 원자료: **{s['rows_raw']:,}행**, {s['date_min'].date()} ~ {s['date_max'].date()}")
    L.append(f"- 테스트 더미 {len(s['dummies'])}종 {s['dummy_rows']}행 제거 → 정제 **{s['rows_clean']:,}행**")
    L.append(f"- 데이터 보유 지점: **{s['sites_with_data']}/{s['sites_master']}** | 중복(site,date): {s['dup_site_date']}행\n")

    L.append("## 지점 커버리지 (구분별)")
    L.append("| 구분 | 데이터보유/전체 |")
    L.append("|---|---|")
    for st, r in s["coverage_by_type"].iterrows():
        L.append(f"| {st} | {int(r['sum'])}/{int(r['count'])} |")
    rps = s["rows_per_site"]
    L.append(f"\n지점당 측정 수: 중앙값 {rps['50%']:.0f} (min {rps['min']:.0f}, max {rps['max']:.0f})\n")

    L.append("## 측정 간격 (불규칙 샘플링 실태)")
    L.append(f"- 중앙값 **{s['gap_median']:.0f}일**, 평균 {s['gap_mean']:.1f}일")
    L.append("| 간격 | 비율(%) |")
    L.append("|---|---|")
    for lbl, v in s["gap_buckets"].items():
        L.append(f"| {lbl} | {v} |")
    L.append("")

    L.append("## 타깃 (유해남조류 세포수, cells/mL)")
    L.append(f"- 결측률 {s['cc_missing_pct']:.1f}% | 전측정치 결측 행 {s['all_nan_rows']:,}")
    q = s["cc_quantiles"]
    L.append(f"- 분위: 중앙 {q[0.5]:.0f} / 90% {q[0.9]:.0f} / 95% {q[0.95]:.0f} / 99% {q[0.99]:.0f} / max {s['cc_max']:,.0f}")
    L.append("\n| 임계(cells/mL) | 초과율 | 건수 |")
    L.append("|---|---|---|")
    labels = {1000: "관심", 10000: "경계", 100000: "", 1000000: "대발생"}
    for thr, (pct, n) in s["exceed"].items():
        tag = f" ({labels[thr]})" if labels.get(thr) else ""
        L.append(f"| ≥ {thr:,}{tag} | {pct:.2f}% | {n:,} |")

    L.append("\n## 계절성 (월별)")
    L.append("| 월 | 측정수 | ≥1000 초과율(%) |")
    L.append("|---|---|---|")
    for m, r in s["monthly"].iterrows():
        L.append(f"| {m} | {int(r['measurements']):,} | {r['exceed_1000_pct']} |")

    L.append("\n## 구분별 세포수>0 비율")
    for st, v in s["type_pos"].items():
        L.append(f"- {st}: {v:.1f}%")

    return "\n".join(L) + "\n"


def main() -> None:
    stats = compute(load_algae(), load_sites())
    report = format_report(stats)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[저장] {REPORT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
