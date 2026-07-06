"""확장4 — 기상청 단기예보 조회 (대시보드 **표시용**, 모델 입력 아님).

지점 좌표(lat/lon)를 기상청 격자(nx, ny)로 변환해 단기예보(getVilageFcst)를 호출하고,
일별 최저/최고기온·강수확률 요약을 돌려준다. 예보는 참고 정보로만 보여주며 예측 모델에는
넣지 않는다 — 과거·완벽예보 기상 모두 유의미한 lift 가 없었기 때문(reports/weather_ablation.md).
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta

import pandas as pd
import requests
from dotenv import load_dotenv

from src.loading import REPO_ROOT

ENDPOINT = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
BASE_TIMES = ["2300", "2000", "1700", "1400", "1100", "0800", "0500", "0200"]  # 발표시각(내림차순)


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """기상청 단기예보 격자 변환(LCC DFS). 서울(37.5665,126.9780)→(60,127) 기준."""
    RE, GRID = 6371.00877, 5.0
    SLAT1, SLAT2, OLON, OLAT, XO, YO = 30.0, 60.0, 126.0, 38.0, 43, 136
    d = math.pi / 180.0
    re = RE / GRID
    sn = math.log(math.cos(SLAT1 * d) / math.cos(SLAT2 * d)) / math.log(
        math.tan(math.pi * 0.25 + SLAT2 * d * 0.5) / math.tan(math.pi * 0.25 + SLAT1 * d * 0.5))
    sf = (math.tan(math.pi * 0.25 + SLAT1 * d * 0.5) ** sn) * math.cos(SLAT1 * d) / sn
    ro = re * sf / (math.tan(math.pi * 0.25 + OLAT * d * 0.5) ** sn)
    ra = re * sf / (math.tan(math.pi * 0.25 + lat * d * 0.5) ** sn)
    theta = lon * d - OLON * d
    theta = (theta + math.pi) % (2 * math.pi) - math.pi  # [-π, π]
    theta *= sn
    nx = int(ra * math.sin(theta) + XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny


def _base_datetime(now: datetime) -> tuple[str, str]:
    """가장 최근 발표시각(발표 +10분 여유). 이른 새벽이면 전일 2300."""
    for t in BASE_TIMES:
        issued = now.replace(hour=int(t[:2]), minute=int(t[2:]), second=0, microsecond=0)
        if now >= issued + timedelta(minutes=10):
            return issued.strftime("%Y%m%d"), t
    return (now - timedelta(days=1)).strftime("%Y%m%d"), "2300"


def _summarize(items: list[dict]) -> pd.DataFrame:
    """예보 item → 일별 최저/최고기온·최대 강수확률."""
    df = pd.DataFrame(items)
    df = df[df["category"].isin(["TMX", "TMN", "POP"])].copy()
    df["v"] = pd.to_numeric(df["fcstValue"], errors="coerce")
    rows = []
    for d, g in df.groupby("fcstDate"):
        rows.append({
            "날짜": f"{d[4:6]}/{d[6:]}",
            "최저(℃)": g.loc[g["category"] == "TMN", "v"].min(),
            "최고(℃)": g.loc[g["category"] == "TMX", "v"].max(),
            "강수확률(%)": g.loc[g["category"] == "POP", "v"].max(),
        })
    return pd.DataFrame(rows).sort_values("날짜").reset_index(drop=True)


def fetch_forecast(lat: float, lon: float, now: datetime | None = None) -> pd.DataFrame:
    """지점 좌표의 단기예보(향후 ~3일) 요약. 실패 시 예외 발생(호출부에서 graceful 처리)."""
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY")
    if not key:
        raise RuntimeError("DATA_GO_KR_SERVICE_KEY 미설정(.env)")
    nx, ny = latlon_to_grid(lat, lon)
    base_date, base_time = _base_datetime(now or datetime.now())
    params = {
        "serviceKey": key, "pageNo": 1, "numOfRows": 1000, "dataType": "JSON",
        "base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny,
    }
    resp = requests.get(ENDPOINT, params=params, timeout=10)
    resp.raise_for_status()
    payload = resp.json()["response"]
    if payload["header"]["resultCode"] != "00":
        raise RuntimeError(f"기상청 API 오류: {payload['header']['resultMsg']}")
    return _summarize(payload["body"]["items"]["item"])
