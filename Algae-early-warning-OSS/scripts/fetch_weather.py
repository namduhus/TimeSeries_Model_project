"""기상청 지상(종관, ASOS) 일자료 취득 스크립트 (F1 외생변수).

data.go.kr 기상청_지상(ASOS) 일자료 조회서비스에서 지정 관측소·연도의 일 단위
관측자료를 내려받아 `data/raw/weather/asos_{stnId}_{year}.json` 으로 캐시한다.

- ASOS 는 지점(stnIds)·기간(startDt~endDt)을 지정해야 하므로 관측소 목록을 인자로 받는다.
- 조류 지점 ↔ 관측소 매칭은 F2 이후 결정(§16 Q5)이므로, 여기서는 관측소를 명시적으로 지정한다.
- 이 단계에서는 원자료를 그대로 저장한다(정규화는 src/loading.py).

사용:
    uv run python scripts/fetch_weather.py --start-year 2020 --end-year 2024 --stations 108 105 143
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "weather"
ENDPOINT = "https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"

PAGE_SIZE = 500
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_SEC = 3.0


def _service_key() -> str:
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY")
    if not key:
        raise SystemExit(
            "DATA_GO_KR_SERVICE_KEY 가 설정되지 않았습니다. .env(.env.example 참고)에 디코딩 인증키를 넣으세요."
        )
    return key


def _request_page(service_key: str, stn: str, start_dt: str, end_dt: str, page_no: int) -> dict:
    params = {
        "serviceKey": service_key,
        "pageNo": page_no,
        "numOfRows": PAGE_SIZE,
        "dataType": "JSON",
        "dataCd": "ASOS",
        "dateCd": "DAY",
        "startDt": start_dt,
        "endDt": end_dt,
        "stnIds": stn,
    }
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(ENDPOINT, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            try:
                payload = resp.json()
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"JSON 아님(에러 응답 추정): {resp.text[:300]}") from exc
            header = payload.get("response", {}).get("header", {})
            code = header.get("resultCode")
            if code == "03":  # NO_DATA — 해당 지점·기간 자료 없음(정상: 예: 신설 관측소 이전 연도)
                return {}
            if code not in ("00", None):
                raise RuntimeError(f"API 오류 resultCode={code} msg={header.get('resultMsg')}")
            return payload.get("response", {}).get("body", {}) or {}
        except Exception as exc:  # noqa: BLE001 — 네트워크/응답 전반 재시도
            last_err = exc
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_SEC * attempt)
    raise RuntimeError(f"stn={stn} {start_dt}~{end_dt} p{page_no} 요청 실패: {last_err}")


def _items(body: dict) -> list[dict]:
    item = (body.get("items") or {}).get("item")
    if item is None:
        return []
    return item if isinstance(item, list) else [item]


def fetch_station_year(service_key: str, stn: str, year: int) -> list[dict]:
    start_dt, end_dt = f"{year}0101", f"{year}1231"
    first = _request_page(service_key, stn, start_dt, end_dt, 1)
    total = int(first.get("totalCount") or 0)
    rows = _items(first)
    if total <= len(rows):
        return rows
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    for page_no in range(2, pages + 1):
        rows.extend(_items(_request_page(service_key, stn, start_dt, end_dt, page_no)))
        time.sleep(0.3)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="기상청 ASOS 일자료 취득")
    ap.add_argument("--start-year", type=int, required=True)
    ap.add_argument("--end-year", type=int, required=True)
    ap.add_argument("--stations", nargs="+", required=True, help="ASOS 관측소 지점번호 (예: 108 105 143)")
    ap.add_argument("--force", action="store_true", help="캐시가 있어도 다시 받기")
    args = ap.parse_args()

    service_key = _service_key()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for stn in args.stations:
        for year in range(args.start_year, args.end_year + 1):
            out = RAW_DIR / f"asos_{stn}_{year}.json"
            if out.exists() and not args.force:
                print(f"skip {out.name} (cached)")
                continue
            rows = fetch_station_year(service_key, stn, year)
            out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"saved {out.name}: {len(rows)} rows")
            time.sleep(0.3)


if __name__ == "__main__":
    main()
