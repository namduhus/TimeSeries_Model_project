"""확장4 대시보드 — 녹조 조기경보 (Streamlit).

두 모드:
- **과거 검증:** 과거의 유효 예측점을 골라 예측 vs 실제 다음 측정을 비교(모델 신뢰성 확인).
- **최신 예측:** 지점별 **가장 최근 측정**으로 다음 측정 시점(≈+7일, 아직 모르는) 단계를 예측.

게시된 LightGBM 단계 모델(누적 이진)을 사용하며, 피처는 저장된 데이터에서 자동 생성한다.

실행:
    uv run streamlit run app.py
    # 사전: models/ 게시 모델(uv run python -m src.modeling; uv run python -m src.multiclass)
    # 최신 데이터: uv run python scripts/fetch_algae.py --start-year 2015 --end-year 2026
"""

from __future__ import annotations

from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from src.eda import setup_style
from src.features import assemble_dataset, build_features
from src.forecast import fetch_forecast
from src.loading import REPO_ROOT, load_algae, load_sites
from src.modeling import prep_X
from src.multiclass import load_stage_models, predict_stage
from src.target import STAGE_NAMES, STAGE_THRESHOLDS, alert_stage

STAGE_COLORS = {"정상": "#2ca02c", "관심": "#f0a020", "경계이상": "#d62728"}


@st.cache_resource
def _models():
    return load_stage_models()


@st.cache_data
def _backtest():
    """과거 검증용 — 라벨(다음 측정)이 있는 유효 예측점."""
    return assemble_dataset()


@st.cache_data
def _history():
    """최신 예측·추세용 — 전 측정점의 피처(최신 측정 포함, 라벨 불필요)."""
    return build_features(load_algae(), load_sites()).sort_values("date")


@st.cache_data
def _coords():
    """지점 좌표 — 기상 예보 조회용(site_code → (lat, lon))."""
    df = pd.read_csv(REPO_ROOT / "reference" / "algae_site_coords.csv", dtype={"site_code": "string"})
    return {r.site_code: (r.lat, r.lon) for r in df.dropna(subset=["lat", "lon"]).itertuples()}


def _stage_card(name: str):
    st.markdown(
        f"<div style='background:{STAGE_COLORS[name]};color:white;padding:1.2rem;"
        f"border-radius:.6rem;text-align:center;font-size:1.6rem;font-weight:700'>"
        f"예측: {name}</div>",
        unsafe_allow_html=True,
    )


def _trend_fig(hist_site: pd.DataFrame):
    recent = hist_site.tail(24)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(recent["date"], recent["cur_cyano_cells"], marker="o", color="#1f77b4")
    ax.axhline(STAGE_THRESHOLDS[0], ls="--", color="#f0a020", label=f"관심 {STAGE_THRESHOLDS[0]:,}")
    ax.axhline(STAGE_THRESHOLDS[1], ls="--", color="#d62728", label=f"경계 {STAGE_THRESHOLDS[1]:,}")
    ax.set_yscale("log")
    ax.set_ylabel("유해남조류 세포수 (cells/mL, log)")
    ax.set_title("최근 측정 추세")
    ax.legend(fontsize=8)
    fig.autofmt_xdate()
    return fig


def main() -> None:
    st.set_page_config(page_title="녹조 조기경보", page_icon="🌊", layout="wide")
    setup_style()
    st.title("🌊 유해남조류(녹조) 조기경보")
    st.caption("다음 측정 시점(≈ +7일)의 경보 단계를 공개 데이터·오픈소스 모델로 예측 "
               "— 의사결정 지원용이며 공식 조류경보 대체 아님")

    try:
        lo, hi, card = _models()
    except FileNotFoundError:
        st.error("게시 모델이 없습니다. 먼저: "
                 "`uv run python -m src.modeling` → `uv run python -m src.multiclass`")
        st.stop()
    feats = card["features"]
    sites = load_sites()
    name_map = dict(zip(sites["site_code"], sites["site_name"]))
    hist = _history()

    with st.sidebar:
        st.header("입력")
        mode = st.radio("모드", ["과거 검증", "최신 예측"],
                        help="과거 검증: 예측 vs 실제 비교 · 최신 예측: 최신 측정으로 다음 단계 예측")
        codes = sorted(hist["site_code"].unique())
        site = st.selectbox("지점", codes,
                            format_func=lambda c: f"{name_map.get(c, '?')} ({c})")

    hist_site = hist[hist["site_code"] == site]

    if mode == "과거 검증":
        bt = _backtest()
        site_bt = bt[bt["site_code"] == site].sort_values("date")
        if site_bt.empty:
            st.warning("이 지점은 라벨이 있는 과거 예측점이 없습니다. '최신 예측' 모드를 사용하세요.")
            st.stop()
        dates = site_bt["date"].dt.date.tolist()
        with st.sidebar:
            date = st.select_slider("예측 기준일 (t)", options=dates, value=dates[-1])
            st.caption(f"유효 예측점 {len(dates)}개 · τ={card['tau']}")
        row = site_bt[site_bt["date"].dt.date == date]
        actual = row["label_cyano"].iloc[0]
    else:  # 최신 예측
        row = hist_site.tail(1)
        date = row["date"].iloc[0].date()
        days_ago = (datetime.now().date() - date).days
        actual = None
        with st.sidebar:
            st.caption(f"최신 측정일 {date} ({days_ago}일 전) · τ={card['tau']}")
            st.info(f"이 지점 **최신 측정({date})** 기준 다음 측정 시점(≈+7일)의 예측입니다. "
                    "달력상 '오늘'이 아니라 **마지막 실측에 앵커링**됩니다 "
                    "(조류는 주 단위 측정). 더 최신 측정 반영: `scripts/fetch_algae.py`")

    stage, p_low, p_high = predict_stage(prep_X(row, feats), lo, hi)
    stage_name = STAGE_NAMES[int(stage[0])]

    left, right = st.columns([1, 2])
    with left:
        st.subheader(f"{name_map.get(site, site)} · {date}")
        _stage_card(stage_name)
        st.write("")
        st.metric(f"P(관심 이상, ≥{STAGE_THRESHOLDS[0]:,})", f"{p_low[0]:.1%}")
        st.metric(f"P(경계이상, ≥{STAGE_THRESHOLDS[1]:,})", f"{p_high[0]:.1%}")
        if actual is not None and pd.notna(actual):
            act = STAGE_NAMES[int(alert_stage([actual])[0])]
            hit = "✅ 일치" if act == stage_name else "⚠️ 불일치"
            st.info(f"실제 다음 측정: **{actual:,.0f} cells/mL → {act}**  ({hit})")
        elif mode == "최신 예측":
            st.caption(f"↑ 최신 측정({date}, {days_ago}일 전) 기준 다음 측정(≈+7일) 예측 · 실측 아직 없음")
    with right:
        st.pyplot(_trend_fig(hist_site))

    if mode == "최신 예측":
        coords = _coords()
        if site in coords:
            st.subheader("참고: 기상청 단기예보")
            try:
                fc = fetch_forecast(*coords[site])
                st.dataframe(fc, hide_index=True, use_container_width=True)
                st.caption("⚠️ **모델 입력 아님** — 과거·완벽예보 기상 모두 예측 성능에 유의미한 기여가 "
                           "없어(reports/weather_ablation.md) 참고 정보로만 표시.")
            except Exception as e:  # 네트워크·키·서비스 미활성화 등
                st.caption(f"기상 예보 조회 불가: {e}")

    with st.expander("이 예측은 어떻게 나오나요?"):
        st.markdown(
            f"- **모델:** LightGBM 누적 이진 2개 — P(≥{STAGE_THRESHOLDS[0]:,}) · "
            f"P(≥{STAGE_THRESHOLDS[1]:,}), 단조성 보정 후 단계 도출 (`{card['rule']}`)\n"
            f"- **입력:** 기준일 t까지 정보로 만든 {len(feats)}개 피처(누수 없음)\n"
            "- **게시 가중치:** `models/algae_lgbm.txt`, `models/algae_lgbm_ge10000.txt` (MIT)\n"
            "- 정확도가 아닌 **단계별 recall** 중심으로 검증(`reports/model_multiclass.md`)"
        )


if __name__ == "__main__":
    main()
