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
from seoul_citydata.parser import to_record  # noqa: E402
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

    key = os.environ.get("SEOUL_API_KEY")
    if not key or key == "sample":
        print("::error::SEOUL_API_KEY 미설정(또는 sample). 실데이터 수집 불가.")
        return 2

    subway_key = os.environ.get("SEOUL_SUBWAY_API_KEY")
    if not subway_key or subway_key == "sample":
        print("::error::SEOUL_SUBWAY_API_KEY 미설정(또는 sample). 실시간 지하철 수집 불가.")
        return 2

    records = []
    ok = 0
    for i, area in enumerate(ALL_AREAS, 1):
        d = fetch(area, key)
        if d:
            records.append(to_record(d))
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

    df = pd.DataFrame(records)
    idx, data = write_pages_dashboard(
        df,
        args.docs,
        generated_at=args.generated_at,
        subway_data=subway_data,
    )
    # Jekyll 비활성화 파일 보장
    Path(args.docs, ".nojekyll").touch()
    print(
        f"[OK] 도시 {ok}/{len(ALL_AREAS)}개 지역·지하철 "
        f"{subway_ok}/{len(MONITORED_STATIONS)}개 역 → {idx}, {data}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
