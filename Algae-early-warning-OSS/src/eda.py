"""F3 EDA — 조류 중심 탐색적 분석(그림 생성).

F2 감사(수치)를 넘어 F4 피처 설계에 필요한 구조를 시각화한다:
분포·계절성·지점/권역 차이·자기상관(lag)·수질변수 상관·연도 추세.
외생변수(기상) 상관은 좌표/매칭 확보 후 별도 추가한다.

각 그림 함수는 matplotlib Figure 를 반환하며(노트북에서 그대로 표시 가능),
main()은 reports/figures/*.png 로 저장한다.

실행:
    uv run python -m src.eda        # reports/figures/ 에 PNG 저장 + 요약 출력
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.loading import REPO_ROOT, clean_algae, load_algae, load_sites

FIG_DIR = REPO_ROOT / "reports" / "figures"
THRESHOLD = 1000  # 관심 단계 (cells/mL) cells = 유해나조류 세포 개수(독성/냄새를 유발하는 남조류4속의 합계)
WQ_COLS = ["water_temp", "ph", "dissolved_oxygen", "transparency", "turbidity", "chlorophyll_a"]


def setup_style() -> None:
    """한글 폰트·기본 스타일. (macOS: AppleGothic)"""
    matplotlib.rcParams["font.family"] = "AppleGothic"
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["figure.dpi"] = 110
    matplotlib.rcParams["axes.grid"] = True
    matplotlib.rcParams["grid.alpha"] = 0.3


def load_clean() -> pd.DataFrame:
    """정제(테스트더미 제거) + 지점 메타(구분·권역) 결합."""
    df = clean_algae(load_algae())
    sites = load_sites()[["site_code", "station_type", "major_basin"]]
    df = df.merge(sites, on="site_code", how="left")
    df["month"] = df["date"].dt.month
    df["year"] = df["date"].dt.year
    df["exceed"] = (df["cyano_cells"] >= THRESHOLD).astype("float")
    return df


def fig_cyano_distribution(df: pd.DataFrame):
    cc = df["cyano_cells"].dropna()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(np.log10(cc + 1), bins=60, color="#2b8cbe", edgecolor="white")
    for thr, c in [(1000, "orange"), (10000, "red")]:
        ax.axvline(np.log10(thr + 1), color=c, ls="--", label=f"임계 {thr:,}")
    zero_pct = (cc == 0).mean() * 100
    ax.set_title(f"유해남조류 세포수 분포 (log10, +1)  |  0 비율 {zero_pct:.0f}%")
    ax.set_xlabel("log10(cells/mL + 1)")
    ax.set_ylabel("측정 수")
    ax.legend()
    fig.tight_layout()
    return fig


def fig_monthly_seasonality(df: pd.DataFrame):
    g = df.groupby("month")
    rate = g["exceed"].mean() * 100
    med = g["cyano_cells"].median()
    fig, ax1 = plt.subplots(figsize=(7, 4))
    ax1.bar(rate.index, rate.values, color="#74c476", label="초과율(≥1,000)")
    ax1.set_xlabel("월")
    ax1.set_ylabel("초과율 (%)", color="#2ca25f")
    ax1.set_xticks(range(1, 13))
    ax2 = ax1.twinx()
    ax2.plot(med.index, med.values, "o-", color="#d95f0e", label="세포수 중앙값")
    ax2.set_ylabel("세포수 중앙값 (cells/mL)", color="#d95f0e")
    ax2.grid(False)
    ax1.set_title("월별 계절성 — 초과율 & 세포수 중앙값")
    fig.tight_layout()
    return fig


def fig_basin_exceedance(df: pd.DataFrame):
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11, 4))
    basin = df.groupby("major_basin")["exceed"].mean().mul(100).sort_values()
    axL.barh(basin.index, basin.values, color="#3182bd")
    axL.set_title("대권역별 초과율 (%)")
    axL.set_xlabel("초과율 (%)")

    site = df.groupby(["site_code"]).agg(
        name=("site_name", "first"), rate=("exceed", "mean"), n=("exceed", "size")
    )
    site = site[site["n"] >= 100].sort_values("rate", ascending=False).head(12)
    labels = site["name"] + " (" + site.index + ")"
    axR.barh(labels[::-1], site["rate"].values[::-1] * 100, color="#de2d26")
    axR.set_title("초과율 상위 지점 (측정≥100)")
    axR.set_xlabel("초과율 (%)")
    fig.tight_layout()
    return fig


def fig_persistence_autocorr(df: pd.DataFrame):
    """지속성/자기상관: 현재 vs 다음 측정 세포수 + lag별 상관."""
    d = df.dropna(subset=["date"]).drop_duplicates(["site_code", "date"]).sort_values(["site_code", "date"])
    grp = d.groupby("site_code", sort=False)["cyano_cells"]
    nxt = grp.shift(-1)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11, 4))
    m = d["cyano_cells"].notna() & nxt.notna()
    x = np.log10(d.loc[m, "cyano_cells"] + 1)
    y = np.log10(nxt[m] + 1)
    samp = np.random.default_rng(0).choice(len(x), size=min(4000, len(x)), replace=False)
    axL.scatter(x.iloc[samp], y.iloc[samp], s=6, alpha=0.25, color="#2b8cbe")
    axL.axvline(np.log10(1001), color="orange", ls="--")
    axL.axhline(np.log10(1001), color="orange", ls="--")
    axL.set_title("지속성: 현재 vs 다음 측정 (log10)")
    axL.set_xlabel("현재 log10(cells+1)")
    axL.set_ylabel("다음 log10(cells+1)")

    lags = range(1, 6)
    corrs = []
    for k in lags:
        lagged = grp.shift(k)
        mm = d["cyano_cells"].notna() & lagged.notna()
        corrs.append(d.loc[mm, "cyano_cells"].corr(lagged[mm], method="spearman"))
    axR.bar(list(lags), corrs, color="#756bb1")
    axR.set_title("lag별 자기상관 (Spearman)")
    axR.set_xlabel("lag (측정 스텝 전)")
    axR.set_ylabel("Spearman ρ")
    axR.set_ylim(0, 1)
    fig.tight_layout()
    return fig


def fig_waterquality_corr(df: pd.DataFrame):
    cols = WQ_COLS + ["cyano_cells"]
    corr = df[cols].corr(method="spearman")
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=45, ha="right")
    ax.set_yticklabels(cols)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)
    ax.set_title("수질변수 상관 (Spearman)")
    fig.colorbar(im, fraction=0.046, pad=0.04)
    fig.tight_layout()
    return fig


def fig_yearly_trend(df: pd.DataFrame):
    g = df.groupby("year")
    rate = g["exceed"].mean() * 100
    n = g.size()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(rate.index, rate.values, "o-", color="#e6550d")
    ax.set_title("연도별 초과율 (≥1,000)")
    ax.set_xlabel("연도")
    ax.set_ylabel("초과율 (%)")
    for xi, yi, ni in zip(rate.index, rate.values, n.values):
        ax.annotate(f"n={ni}", (xi, yi), fontsize=7, xytext=(0, 5), textcoords="offset points", ha="center")
    fig.tight_layout()
    return fig


FIGURES = {
    "01_cyano_distribution": fig_cyano_distribution,
    "02_monthly_seasonality": fig_monthly_seasonality,
    "03_basin_exceedance": fig_basin_exceedance,
    "04_persistence_autocorr": fig_persistence_autocorr,
    "05_waterquality_corr": fig_waterquality_corr,
    "06_yearly_trend": fig_yearly_trend,
}


def main() -> None:
    plt.switch_backend("Agg")
    setup_style()
    df = load_clean()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for name, fn in FIGURES.items():
        fig = fn(df)
        fig.savefig(FIG_DIR / f"{name}.png", bbox_inches="tight")
        plt.close(fig)
        print(f"[저장] reports/figures/{name}.png")

    # 요약 (F4 설계 근거)
    d = df.dropna(subset=["date"]).drop_duplicates(["site_code", "date"]).sort_values(["site_code", "date"])
    lag1 = d.groupby("site_code")["cyano_cells"].shift(1)
    rho1 = d["cyano_cells"].corr(lag1, method="spearman")
    print(f"\n요약: 행 {len(df):,} | 지점 {df['site_code'].nunique()} | "
          f"lag1 자기상관 ρ={rho1:.2f} | 8월 초과율 {df[df['month']==8]['exceed'].mean()*100:.0f}%")


if __name__ == "__main__":
    main()
