"""조류경보제 측정결과(algaePreMeasure) 원자료 취득 스크립트 (F1).

공공데이터포털 국립환경과학원 조류경보제 조회서비스에서 연도×월 단위로 전 지점
측정자료를 내려받아 `data/raw/algae/algae_{year}_{mm}.json` 으로 캐시한다.

- `ptNoList`(지점) 파라미터를 생략하면 해당 연·월의 전 지점이 반환된다.
- 이 단계에서는 원자료를 그대로 저장한다(리샘플링·보간·정규화 금지 — 정규화는 src/loading.py).

사용:
    uv run python scripts/fetch_algae.py --start-year 2020 --end-year 2024
    uv run python scripts/fetch_algae.py --start-year 2023 --end-year 2023 --months 07 08 09 --force
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "algae"
ENDPOINT = "https://apis.data.go.kr/1480523/nieragainstalgae/algaePreMeasure"
OPERATION = "algaePreMeasure"

ALL_MONTHS = [f"{m:02d}" for m in range(1, 13)]
PAGE_SIZE = 1000
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


def _request_page(service_key: str, year: int, month: str, page_no: int) -> dict:
    """단일 페이지를 요청해 envelope(dict)를 반환. 재시도 포함."""
    params = {
        "serviceKey": service_key,  # 디코딩 키 → requests 가 URL 인코딩
        "pageNo": page_no,
        "numOfRows": PAGE_SIZE,
        "resultType": "json",
        "wmyrList": year,
        "wmodList": month,
    }
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(ENDPOINT, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            try:
                payload = resp.json()
            except json.JSONDecodeError as exc:
                # 키 오류·쿼터 초과 시 XML 에러가 오는 경우
                raise RuntimeError(f"JSON 아님(에러 응답 추정): {resp.text[:300]}") from exc
            body = payload.get(OPERATION, {})
            header = body.get("header", {})
            if header.get("code") not in ("00", None):
                raise RuntimeError(f"API 오류 code={header.get('code')} msg={header.get('message')}")
            return body
        except Exception as exc:  # noqa: BLE001 — 네트워크/응답 전반 재시도
            last_err = exc
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_SEC * attempt)
    raise RuntimeError(f"{year}-{month} p{page_no} 요청 실패: {last_err}")


def _as_list(item) -> list[dict]:
    """item 이 dict 하나면 list 로, 없으면 빈 list 로 정규화."""
    if item is None:
        return []
    return item if isinstance(item, list) else [item]


def fetch_month(service_key: str, year: int, month: str) -> list[dict]:
    """해당 연·월 전 지점 측정자료(원자료 dict 리스트) 수집."""
    first = _request_page(service_key, year, month, 1)
    total = int(first.get("totalCount") or 0)
    rows = _as_list(first.get("item"))
    if total <= len(rows):
        return rows
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    for page_no in range(2, pages + 1):
        body = _request_page(service_key, year, month, page_no)
        rows.extend(_as_list(body.get("item")))
        time.sleep(0.3)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="조류경보제 측정결과 원자료 취득")
    ap.add_argument("--start-year", type=int, required=True)
    ap.add_argument("--end-year", type=int, required=True)
    ap.add_argument("--months", nargs="+", default=ALL_MONTHS, help="예: 07 08 09 (기본: 전월)")
    ap.add_argument("--force", action="store_true", help="캐시가 있어도 다시 받기")
    args = ap.parse_args()

    service_key = _service_key()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for year in range(args.start_year, args.end_year + 1):
        for month in args.months:
            out = RAW_DIR / f"algae_{year}_{month}.json"
            if out.exists() and not args.force:
                print(f"skip {out.name} (cached)")
                continue
            rows = fetch_month(service_key, year, month)
            out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"saved {out.name}: {len(rows)} rows")
            time.sleep(0.3)


if __name__ == "__main__":
    main()
