"""F4 Feature Engineering — 예측 시점 t까지의 정보로만 피처 생성 (누수 안전).

각 (지점, 측정일 t)에서 t 시점까지 알 수 있는 정보만으로 피처를 만들고,
`src/target.py`의 타깃과 (site_code, date)로 조인해 모델링 데이터셋을 만든다.

누수 방지(§8.3, 최우선 원칙):
- 모든 시계열 피처는 `groupby('site') → date 정렬 → shift(k)` 순.
- rolling 은 **`shift(1)` 이후** 계산해 현재값을 배제(과거만 반영).
- 현재 측정치(t)는 예측 시점에 알 수 있으므로 피처로 사용(타깃은 t+1).
- `days_since_prev`(과거 간격)만 피처. 다음 측정까지 간격(horizon)은 미래이므로 금지.
- 라벨 생성 측정치(t+1)는 절대 피처로 재사용하지 않는다(target.py가 분리).

기상 외생변수는 지점↔ASOS 좌표 매칭 확보 후 별도 합류(컬럼 추가만, 구조 불변).

실행:
    uv run python -m src.features      # data/interim/dataset.csv 저장 + 요약
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.loading import REPO_ROOT, clean_algae, load_algae, load_sites, load_weather
from src.target import build_targets

# 현재값(t 시점, 알 수 있음)
CURRENT_COLS = ["cyano_cells", "water_temp", "ph", "dissolved_oxygen",
                "transparency", "turbidity", "chlorophyll_a"]
LAG_COLS = ["cyano_cells", "water_temp", "chlorophyll_a"]   # 과거값 lag 대상
ROLL_COLS = ["cyano_cells", "water_temp"]                    # rolling 대상
DELTA_COLS = ["cyano_cells", "water_temp"]                   # 직전 대비 변화
STATIC_COLS = ["major_basin", "station_type"]               # 정적 범주형(+ site_code)

DEFAULT_LAGS = (1, 2, 3, 4)
DEFAULT_ROLL_WINDOWS = (3, 5)
OUTPUT_PATH = REPO_ROOT / "data" / "interim" / "dataset.csv"

# 기상(외생변수) — 매칭된 ASOS의 과거 집계. 미래(t+1~) 실측 금지: 창은 t로 끝난다.
SITE_STATION_MAP = REPO_ROOT / "reference" / "site_station_map.csv"
WEATHER_WINDOWS = (7, 14)  # t 기준 과거 일수


def _prepare(df: pd.DataFrame, sites: pd.DataFrame) -> pd.DataFrame:
    """테스트더미 제거 + 지점 메타 결합 + (site, date) 유일·정렬."""
    df = clean_algae(df, sites)
    df = df.merge(sites[["site_code", "station_type", "major_basin"]], on="site_code", how="left")
    df = df.dropna(subset=["date"]).drop_duplicates(["site_code", "date"])
    return df.sort_values(["site_code", "date"]).reset_index(drop=True)


def build_features(
    df: pd.DataFrame,
    sites: pd.DataFrame | None = None,
    lags: tuple[int, ...] = DEFAULT_LAGS,
    roll_windows: tuple[int, ...] = DEFAULT_ROLL_WINDOWS,
) -> pd.DataFrame:
    """표준 조류 DataFrame → (site_code, date) 키의 피처 테이블 (전 측정 시점)."""
    if sites is None:
        sites = load_sites()
    d = _prepare(df, sites)
    site = d["site_code"]
    g = d.groupby("site_code", sort=False)

    feat = pd.DataFrame({"site_code": d["site_code"], "date": d["date"]}, index=d.index)

    # 현재값
    for c in CURRENT_COLS:
        feat[f"cur_{c}"] = d[c]

    # lag
    for c in LAG_COLS:
        for k in lags:
            feat[f"{c}_lag{k}"] = g[c].shift(k)

    # rolling — shift(1) 이후(과거만)
    for c in ROLL_COLS:
        shifted = g[c].shift(1)
        gr = shifted.groupby(site)
        for w in roll_windows:
            feat[f"{c}_rollmean{w}"] = gr.rolling(w, min_periods=1).mean().reset_index(level=0, drop=True)
            feat[f"{c}_rollmax{w}"] = gr.rolling(w, min_periods=1).max().reset_index(level=0, drop=True)
            feat[f"{c}_rollstd{w}"] = gr.rolling(w, min_periods=2).std().reset_index(level=0, drop=True)

    # delta (현재 - 직전, 둘 다 t까지 정보)
    for c in DELTA_COLS:
        feat[f"{c}_delta1"] = d[c] - g[c].shift(1)

    # 계절 (t의 날짜)
    feat["month"] = d["date"].dt.month
    feat["weekofyear"] = d["date"].dt.isocalendar().week.astype("int16")
    doy = d["date"].dt.dayofyear
    feat["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    feat["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    feat["is_algae_season"] = d["date"].dt.month.isin([5, 6, 7, 8, 9, 10]).astype("int8")

    # 경과일수(과거 간격)
    feat["days_since_prev"] = g["date"].diff().dt.days

    # 정적 범주형
    for c in STATIC_COLS:
        feat[c] = d[c]

    return feat


def build_weather_features(windows: tuple[int, ...] = WEATHER_WINDOWS) -> pd.DataFrame:
    """(station_id, date)별 과거 기상 집계 — 각 일자 d로 끝나는 trailing 창(미래 미포함)."""
    w = load_weather().sort_values(["station_id", "date"]).copy()
    w["station_id"] = w["station_id"].astype("int64")
    w["precip0"] = w["precip"].fillna(0.0)  # 무강수 결측 → 0
    g = w.groupby("station_id", sort=False)
    out = w[["station_id", "date"]].copy()
    for win in windows:
        out[f"wx_temp_avg_{win}"] = g["temp_avg"].transform(lambda s: s.rolling(win, min_periods=1).mean())
        out[f"wx_temp_max_{win}"] = g["temp_max"].transform(lambda s: s.rolling(win, min_periods=1).max())
        out[f"wx_precip_{win}"] = g["precip0"].transform(lambda s: s.rolling(win, min_periods=1).sum())
        out[f"wx_sunshine_{win}"] = g["sunshine_hours"].transform(lambda s: s.rolling(win, min_periods=1).sum())
    return out


def add_weather(ds: pd.DataFrame, windows: tuple[int, ...] = WEATHER_WINDOWS) -> pd.DataFrame:
    """지점→최근접 ASOS 매핑으로 과거 기상 집계를 (stn, date) 정확 조인."""
    smap = pd.read_csv(SITE_STATION_MAP, dtype={"site_code": "string"})
    stn = dict(zip(smap["site_code"], smap["stn_id"].astype("int64")))
    ds = ds.copy()
    ds["_stn"] = ds["site_code"].map(stn).astype("Int64")
    wx = build_weather_features(windows)
    ds = ds.merge(wx, left_on=["_stn", "date"], right_on=["station_id", "date"], how="left")
    return ds.drop(columns=["_stn", "station_id"])


def assemble_dataset(
    lags: tuple[int, ...] = DEFAULT_LAGS,
    roll_windows: tuple[int, ...] = DEFAULT_ROLL_WINDOWS,
    with_weather: bool = False,
) -> pd.DataFrame:
    """피처(t) ⨝ 타깃(다음 측정) → 모델링 데이터셋 (유효 예측점만).

    with_weather=True 면 매칭된 ASOS의 과거 기상 집계를 추가(ablation용).
    """
    algae, sites = load_algae(), load_sites()
    feats = build_features(algae, sites, lags, roll_windows)
    targets = build_targets(algae, sites)
    ds = targets.merge(feats, on=["site_code", "date"], how="inner")
    if with_weather:
        ds = add_weather(ds)
    front = ["site_code", "date", "target", "label_date", "horizon_days", "label_cyano"]
    return ds[front + [c for c in ds.columns if c not in front]]


def feature_columns(ds: pd.DataFrame) -> list[str]:
    """모델 입력 피처 컬럼 (키·타깃·provenance 제외)."""
    exclude = {"site_code", "date", "target", "label_date", "horizon_days", "label_cyano"}
    return [c for c in ds.columns if c not in exclude]


def main() -> None:
    ds = assemble_dataset()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ds.to_csv(OUTPUT_PATH, index=False)
    feats = feature_columns(ds)
    n, pos = len(ds), int(ds["target"].sum())
    print(f"데이터셋: {n:,}행 × 피처 {len(feats)}개 | 지점 {ds['site_code'].nunique()}")
    print(f"양성률: {pos / n * 100:.2f}% ({pos:,})")
    print(f"기간: {ds['date'].min().date()} ~ {ds['date'].max().date()}")
    print(f"피처 예시: {feats[:8]} ...")
    print(f"[저장] {OUTPUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
