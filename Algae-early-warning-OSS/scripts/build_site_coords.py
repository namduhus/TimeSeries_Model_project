"""조류 지점 좌표 확정 + 최근접 ASOS 관측소 매칭 (§16 Q5).

물환경 수질측정망 GeoJSON(코드·위경도)에서 조류 지점 좌표를 정밀 매칭하고,
누락분은 같은 중권역/대권역의 확보 지점 좌표로 상속(근사)한다. 그 뒤 haversine으로
각 조류 지점을 최근접 ASOS(reference/kma_stations.csv)에 매칭한다.

기상 매칭엔 관측소가 성겨(≈97개) 근사 좌표로도 최근접이 거의 불변이다. 좌표 출처는
coord_source(precise/inherited/coarse)로 표기한다.

산출(커밋): reference/algae_site_coords.csv, reference/site_station_map.csv

사용:
    uv run python scripts/build_site_coords.py [--geojson-dir <경로>]
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SITES_CSV = REPO_ROOT / "reference" / "algae_sites.csv"
KMA_CSV = REPO_ROOT / "reference" / "kma_stations.csv"
COORDS_OUT = REPO_ROOT / "reference" / "algae_site_coords.csv"
MAP_OUT = REPO_ROOT / "reference" / "site_station_map.csv"
DEFAULT_GEOJSON_DIR = "/Users/namduhus/Downloads/기후에너지환경부_물환경 수질측정망 정보(JSON)_20251231"

BIG_RIVER = {"한강", "낙동강", "금강", "영산강"}


def _core(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", str(s))
    s = re.sub(r"[0-9]", "", s)
    return re.sub(r"(댐|호|지|제|보|취수장|광역|시범|표층|혼합|상류|하류|중류)", "", s).strip()


def load_network(geojson_dir: str) -> tuple[dict, dict, dict]:
    """수질측정망 GeoJSON → (코드→좌표, 조사명→좌표, 이름키→좌표)."""
    files = sorted(glob.glob(f"{geojson_dir}/**/*.geojson", recursive=True))
    if not files:
        raise SystemExit(f"GeoJSON 없음: {geojson_dir} (수질측정망 JSON 다운로드 필요)")
    by_code, by_ptnm, by_name = {}, {}, {}
    for fp in files:
        for ft in json.loads(Path(fp).read_text(encoding="utf-8")).get("features", []):
            p = ft["properties"]
            code, nm = str(p.get("ptNo")), str(p.get("ptNm"))
            coord = (p.get("Y"), p.get("X"), nm)
            by_code.setdefault(code, coord)
            by_ptnm.setdefault(nm, coord)
            keys = {_core(nm)} | {x for paren in re.findall(r"\((.*?)\)", nm) for x in (paren, _core(paren))}
            for k in keys:
                if k:
                    by_name.setdefault(k, coord)
    return by_code, by_ptnm, by_name


def match_precise(sites: pd.DataFrame, by_code, by_ptnm, by_name) -> pd.DataFrame:
    """코드/조사위치/지점명(괄호) 순으로 정밀 좌표 매칭."""
    lat, lon, src = [], [], []
    for _, r in sites.iterrows():
        code, sn, sv = r["site_code"], str(r["site_name"]), str(r["survey_location"])
        coord = None
        if code in by_code:
            coord = by_code[code]
        elif sv in by_ptnm:
            coord = by_ptnm[sv]
        elif sn not in BIG_RIVER and (sn in by_name or _core(sn) in by_name):
            coord = by_name.get(sn) or by_name.get(_core(sn))
        lat.append(coord[0] if coord else np.nan)
        lon.append(coord[1] if coord else np.nan)
        src.append("precise" if coord else None)
    out = sites.copy()
    out["lat"], out["lon"], out["coord_source"] = lat, lon, src
    return out


def inherit_missing(df: pd.DataFrame) -> pd.DataFrame:
    """누락 좌표를 같은 중권역(→대권역) 확보 지점 평균으로 상속."""
    df = df.copy()
    for level, tag in [("mid_basin", "inherited"), ("major_basin", "coarse")]:
        centroid = df[df["lat"].notna()].groupby(level)[["lat", "lon"]].mean()
        need = df["lat"].isna()
        for idx in df[need].index:
            key = df.at[idx, level]
            if key in centroid.index:
                df.at[idx, "lat"] = centroid.at[key, "lat"]
                df.at[idx, "lon"] = centroid.at[key, "lon"]
                df.at[idx, "coord_source"] = tag
    return df


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def match_nearest_station(coords: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    st_lat = stations["lat"].to_numpy()
    st_lon = stations["lon"].to_numpy()
    rows = []
    for _, r in coords.iterrows():
        d = haversine(r["lat"], r["lon"], st_lat, st_lon)
        j = int(np.argmin(d))
        rows.append({"site_code": r["site_code"], "site_name": r["site_name"],
                     "stn_id": int(stations.iloc[j]["stn_id"]), "stn_name": stations.iloc[j]["name_ko"],
                     "dist_km": round(float(d[j]), 1), "coord_source": r["coord_source"]})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson-dir", default=DEFAULT_GEOJSON_DIR)
    args = ap.parse_args()

    sites = pd.read_csv(SITES_CSV, dtype="string")
    stations = pd.read_csv(KMA_CSV)
    by_code, by_ptnm, by_name = load_network(args.geojson_dir)

    coords = inherit_missing(match_precise(sites, by_code, by_ptnm, by_name))
    coords.to_csv(COORDS_OUT, index=False)
    print("좌표 출처:", coords["coord_source"].value_counts(dropna=False).to_dict())

    mapping = match_nearest_station(coords, stations)
    mapping.to_csv(MAP_OUT, index=False)
    print(f"매칭 지점: {len(mapping)} | 사용 관측소: {mapping['stn_id'].nunique()} | "
          f"거리 중앙 {mapping['dist_km'].median():.1f}km, 최대 {mapping['dist_km'].max():.1f}km")
    print("\n스팟체크:")
    for code in ["3012A07", "1017G20", "1018G01", "1003G20", "2018G20", "4002G10"]:
        row = mapping[mapping["site_code"] == code]
        if len(row):
            r = row.iloc[0]
            print(f"  {code} {r['site_name']} → {r['stn_name']}({r['stn_id']}) {r['dist_km']}km [{r['coord_source']}]")
    print(f"\n[저장] {COORDS_OUT.relative_to(REPO_ROOT)}, {MAP_OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
