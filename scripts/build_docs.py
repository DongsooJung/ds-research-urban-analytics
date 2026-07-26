#!/usr/bin/env python3
"""
GitHub Pages용 대시보드 빌드 (자동 갱신 파이프라인)

서울 실시간 도시데이터를 순차+재시도로 수집해 docs/data.json + docs/index.html을 생성한다.
GitHub Actions에서 SEOUL_API_KEY 시크릿으로 주기 실행된다.

사용:
    SEOUL_API_KEY=... python scripts/build_docs.py
"""
from __future__ import annotations

import os
import sys
import time
import json
import argparse
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd  # noqa: E402

from seoul_citydata.areas import ALL_AREAS  # noqa: E402
from seoul_citydata.mobility import (  # noqa: E402
    MobilityAPIError,
    build_mobility_dashboard_data,
    fetch_bike_status,
    fetch_parking_status,
)
from seoul_citydata.movement import (  # noqa: E402
    MovementDataError,
    fetch_movement_dashboard_data,
)
from seoul_citydata.parser import to_record  # noqa: E402
from seoul_citydata.population import (  # noqa: E402
    PopulationAPIError,
    build_population_dashboard_data,
    fetch_population_code_mappings,
    fetch_population_rows,
)
from seoul_citydata.subway import (  # noqa: E402
    MONITORED_STATIONS,
    build_subway_dashboard_data,
    fetch_many_station_arrivals,
)
from seoul_citydata.viz import write_pages_dashboard  # noqa: E402

BASE = "http://openapi.seoul.go.kr:8088"


def fetch(area: str, key: str, tries: int = 3, timeout: float = 15.0):
    url = f"{BASE}/{key}/json/citydata/1/5/{urllib.parse.quote(area)}"
    for t in range(tries):
        try:
            raw = urllib.request.urlopen(url, timeout=timeout).read().decode("utf-8")
            if raw.lstrip().startswith("<"):
                return None  # XML 오류(키 무효 등)
            d = json.loads(raw)
            if "CITYDATA" in d:
                return d
        except Exception:
            time.sleep(0.5 * (t + 1))
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pages 대시보드 빌드")
    ap.add_argument("--docs", default="docs", help="출력 디렉토리")
    ap.add_argument("--generated-at", default="", help="생성 시각 라벨(UTC 등)")
    ap.add_argument("--min-areas", type=int, default=40,
                    help="기존 대시보드를 교체할 최소 성공 지역 수")
    args = ap.parse_args(argv)
    existing_dashboard: dict = {}
    existing_data_path = Path(args.docs, "data.json")
    if existing_data_path.exists():
        try:
            existing_dashboard = json.loads(
                existing_data_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            existing_dashboard = {}

    key = os.environ.get("SEOUL_API_KEY")
    if not key or key == "sample":
        print("::error::SEOUL_API_KEY 미설정(또는 sample). 실데이터 수집 불가.")
        return 2

    subway_key = os.environ.get("SEOUL_SUBWAY_API_KEY")
    if not subway_key or subway_key == "sample":
        print("::error::SEOUL_SUBWAY_API_KEY 미설정(또는 sample). 실시간 지하철 수집 불가.")
        return 2

    records = []
    city_responses = []
    ok = 0
    for i, area in enumerate(ALL_AREAS, 1):
        d = fetch(area, key)
        if d:
            records.append(to_record(d))
            city_responses.append(d)
            ok += 1
        print(f"[{i}/{len(ALL_AREAS)}] {'OK ' if d else 'skip'} {area} (누적 {ok})", flush=True)

    unique_areas = len({r.get("area") for r in records if r.get("area")})
    if unique_areas < args.min_areas:
        print(
            f"::error::수집 품질 검증 실패: 고유 지역 {unique_areas}개 "
            f"(최소 {args.min_areas}개 필요). 기존 대시보드를 보존합니다."
        )
        return 1

    print(f"[subway] {len(MONITORED_STATIONS)}개 주요역 도착정보 수집 중...", flush=True)
    subway_responses = fetch_many_station_arrivals(MONITORED_STATIONS, subway_key)
    subway_ok = sum(1 for station in MONITORED_STATIONS if subway_responses.get(station))
    min_subway_stations = 6
    if subway_ok < min_subway_stations:
        print(
            f"::error::지하철 수집 품질 검증 실패: {subway_ok}/{len(MONITORED_STATIONS)}개 역 "
            f"(최소 {min_subway_stations}개 필요). 기존 대시보드를 보존합니다."
        )
        return 1
    subway_data = build_subway_dashboard_data(subway_responses)

    print("[mobility] 서울 전역 따릉이·시영주차장 실시간 정보 수집 중...", flush=True)
    try:
        bike_rows = fetch_bike_status(key)
        parking_rows = fetch_parking_status(key)
    except MobilityAPIError as exc:
        print(f"::error::시민 이동정보 수집 실패: {exc}. 기존 대시보드를 보존합니다.")
        return 1
    min_bike_stations = 500
    min_parking_lots = 20
    if len(bike_rows) < min_bike_stations or len(parking_rows) < min_parking_lots:
        print(
            f"::error::시민 이동정보 품질 검증 실패: 따릉이 {len(bike_rows)}개 대여소 "
            f"(최소 {min_bike_stations}), 주차장 {len(parking_rows)}곳 "
            f"(최소 {min_parking_lots}). 기존 대시보드를 보존합니다."
        )
        return 1
    mobility_data = build_mobility_dashboard_data(
        bike_rows,
        parking_rows,
        city_responses,
    )

    print("[population] 서울 전역 행정동 생활인구 수집 중...", flush=True)
    try:
        population_rows, population_meta = fetch_population_rows(key)
        try:
            admin_dong_mapping, origin_mapping = fetch_population_code_mappings()
        except PopulationAPIError as exc:
            print(f"::warning::행정동명 매핑 실패, 코드로 표시합니다: {exc}")
            admin_dong_mapping = {}
            origin_mapping = {}
    except PopulationAPIError as exc:
        print(f"::error::생활인구 수집 실패: {exc}. 기존 대시보드를 보존합니다.")
        return 1
    min_population_dongs = 400
    if len(population_rows) < min_population_dongs:
        print(
            f"::error::생활인구 품질 검증 실패: 행정동 {len(population_rows)}개 "
            f"(최소 {min_population_dongs}개 필요). 기존 대시보드를 보존합니다."
        )
        return 1
    population_data = build_population_dashboard_data(
        population_rows,
        admin_dong_mapping,
        reference_date=population_meta["reference_date"],
        reference_hour=population_meta["reference_hour"],
    )

    print("[movement] 수도권·전국 유입 생활인구 집계 중...", flush=True)
    try:
        if not origin_mapping:
            raise MovementDataError("공식 유입지 코드 매핑이 없습니다.")
        movement_data, movement_reused = fetch_movement_dashboard_data(
            admin_dong_mapping,
            origin_mapping,
            existing=existing_dashboard.get("movement"),
        )
    except MovementDataError as exc:
        print(f"::error::유입 생활인구 수집 실패: {exc}. 기존 대시보드를 보존합니다.")
        return 1
    min_movement_rows = 10000
    movement_periods = movement_data.get("periods") or {}
    if any(
        (movement_periods.get(hour) or {}).get("row_count", 0) < min_movement_rows
        for hour in ("08", "18")
    ):
        print(
            "::error::유입 생활인구 품질 검증 실패: "
            "08시 또는 18시 원본 행이 부족합니다. 기존 대시보드를 보존합니다."
        )
        return 1
    print(
        f"[movement] 기준일 {movement_data['reference_date']} "
        f"({'기존 집계 재사용' if movement_reused else '최신 파일 신규 집계'})",
        flush=True,
    )

    df = pd.DataFrame(records)
    idx, data = write_pages_dashboard(
        df,
        args.docs,
        generated_at=args.generated_at,
        subway_data=subway_data,
        mobility_data=mobility_data,
        population_data=population_data,
        movement_data=movement_data,
    )
    # Jekyll 비활성화 파일 보장
    Path(args.docs, ".nojekyll").touch()
    print(
        f"[OK] 도시 {ok}/{len(ALL_AREAS)}개 지역·지하철 "
        f"{subway_ok}/{len(MONITORED_STATIONS)}개 역·따릉이 {len(bike_rows)}개 대여소·"
        f"시영주차장 {len(parking_rows)}곳·생활인구 {len(population_rows)}개 행정동 "
        f"·유입 생활인구 {movement_data['reference_date']} 기준 → {idx}, {data}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
