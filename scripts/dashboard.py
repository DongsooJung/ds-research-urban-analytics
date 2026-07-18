#!/usr/bin/env python3
"""
서울 실시간 도시데이터 대시보드 생성 CLI

라이브 수집(또는 저장된 CSV)에서 HTML 대시보드를 생성한다.

사용:
    # 라이브 수집 → 대시보드 (SEOUL_API_KEY 필요; 미설정 시 sample=동일값)
    python scripts/dashboard.py --out dashboard.html

    # 저장된 스냅샷 CSV로부터
    python scripts/dashboard.py --csv snapshot.csv --out dashboard.html

    # 데모 데이터(합성 다지역)로 시각화 미리보기 — 키 없이 차트 확인용
    python scripts/dashboard.py --demo --out demo.html
"""
from __future__ import annotations

import sys
import argparse
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd  # noqa: E402

from seoul_citydata import fetch_many, to_dataframe, get_api_key  # noqa: E402
from seoul_citydata.areas import ALL_AREAS, AREAS_BY_CATEGORY  # noqa: E402
from seoul_citydata.viz import generate_dashboard  # noqa: E402


def demo_dataframe() -> pd.DataFrame:
    """키 없이 차트를 확인하기 위한 합성 다지역 스냅샷."""
    rows = [
        dict(area="강남역", category="인구밀집지역", congest_level="붐빔", congest_score=4,
             ppltn_min=90000, ppltn_max=98000, ppltn_mid=94000, male_rate=53, female_rate=47,
             temp=29, humidity=62, pm10=75, pm25=45, uv_index=5, road_spd=12,
             rate_0=1, rate_10=5, rate_20=31, rate_30=26, rate_40=19, rate_50=12, rate_60=4, rate_70=2),
        dict(area="홍대 관광특구", category="관광특구", congest_level="붐빔", congest_score=4,
             ppltn_min=82000, ppltn_max=90000, ppltn_mid=86000, male_rate=49, female_rate=51,
             temp=28, humidity=64, pm10=68, pm25=40, uv_index=4, road_spd=15,
             rate_0=1, rate_10=8, rate_20=42, rate_30=24, rate_40=14, rate_50=7, rate_60=3, rate_70=1),
        dict(area="여의도", category="발달상권", congest_level="약간 붐빔", congest_score=3,
             ppltn_min=55000, ppltn_max=60000, ppltn_mid=57500, male_rate=54, female_rate=46,
             temp=27, humidity=60, pm10=55, pm25=32, uv_index=4, road_spd=22,
             rate_0=1, rate_10=4, rate_20=22, rate_30=28, rate_40=24, rate_50=14, rate_60=5, rate_70=2),
        dict(area="광화문·덕수궁", category="고궁·문화유산", congest_level="보통", congest_score=2,
             ppltn_min=33000, ppltn_max=36000, ppltn_mid=34500, male_rate=49, female_rate=51,
             temp=27, humidity=63, pm10=42, pm25=24, uv_index=3, road_spd=25,
             rate_0=1, rate_10=6, rate_20=24, rate_30=23, rate_40=22, rate_50=15, rate_60=6, rate_70=3),
        dict(area="서울숲공원", category="공원", congest_level="여유", congest_score=1,
             ppltn_min=12000, ppltn_max=14000, ppltn_mid=13000, male_rate=47, female_rate=53,
             temp=25, humidity=68, pm10=25, pm25=13, uv_index=2, road_spd=38,
             rate_0=4, rate_10=11, rate_20=18, rate_30=24, rate_40=20, rate_50=14, rate_60=6, rate_70=3),
        dict(area="뚝섬한강공원", category="공원", congest_level="여유", congest_score=1,
             ppltn_min=15000, ppltn_max=17000, ppltn_mid=16000, male_rate=50, female_rate=50,
             temp=24, humidity=70, pm10=20, pm25=10, uv_index=2, road_spd=42,
             rate_0=3, rate_10=9, rate_20=20, rate_30=25, rate_40=21, rate_50=13, rate_60=6, rate_70=3),
        dict(area="잠실 관광특구", category="관광특구", congest_level="약간 붐빔", congest_score=3,
             ppltn_min=60000, ppltn_max=66000, ppltn_mid=63000, male_rate=48, female_rate=52,
             temp=28, humidity=61, pm10=58, pm25=34, uv_index=4, road_spd=18,
             rate_0=2, rate_10=9, rate_20=27, rate_30=25, rate_40=19, rate_50=12, rate_60=4, rate_70=2),
        dict(area="명동 관광특구", category="관광특구", congest_level="붐빔", congest_score=4,
             ppltn_min=78000, ppltn_max=85000, ppltn_mid=81500, male_rate=46, female_rate=54,
             temp=28, humidity=63, pm10=64, pm25=38, uv_index=4, road_spd=14,
             rate_0=1, rate_10=6, rate_20=33, rate_30=25, rate_40=18, rate_50=11, rate_60=4, rate_70=2),
    ]
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="서울 실시간 도시데이터 대시보드 생성")
    ap.add_argument("--csv", help="저장된 스냅샷 CSV 경로")
    ap.add_argument("--demo", action="store_true", help="합성 데모 데이터로 생성")
    ap.add_argument("--category", help="라이브 수집 시 특정 카테고리만")
    ap.add_argument("--require-key", action="store_true",
                    help="SEOUL_API_KEY가 없으면 실패(자동 배포용)")
    ap.add_argument("--min-areas", type=int, default=1,
                    help="성공으로 수집되어야 할 최소 지역 수")
    ap.add_argument("--out", default="dashboard.html", help="HTML 출력 경로")
    args = ap.parse_args(argv)

    if args.demo:
        df = demo_dataframe()
        note = "데모(합성) 데이터"
        source_mode = "demo"
    elif args.csv:
        df = pd.read_csv(args.csv)
        note = f"CSV: {args.csv}"
        source_mode = "csv"
    else:
        areas = AREAS_BY_CATEGORY.get(args.category, ALL_AREAS) if args.category else ALL_AREAS
        key = get_api_key()
        if args.require_key and (key == "sample" or not os.environ.get("SEOUL_API_KEY", "").strip()):
            print("[!] SEOUL_API_KEY가 없어 라이브 대시보드 생성을 중단합니다.", file=sys.stderr)
            return 2
        note = "라이브 수집(sample 고정값)" if key == "sample" else "라이브 수집(개인 키)"
        source_mode = "sample" if key == "sample" else "api"
        print(f"[i] {len(areas)}개 지역 수집 중... ({note})")
        df = to_dataframe(fetch_many(areas))

    unique_areas = int(df["area"].nunique()) if "area" in df.columns else 0
    if df.empty or unique_areas < args.min_areas:
        print(
            f"[!] 데이터 품질 검증 실패: 고유 지역 {unique_areas}개 "
            f"(최소 {args.min_areas}개 필요). 기존 대시보드를 보존합니다.",
            file=sys.stderr,
        )
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 생성 중 오류가 나면 기존 정상 파일을 덮어쓰지 않는다.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", dir=out_path.parent, delete=False, encoding="utf-8"
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        generate_dashboard(df, str(tmp_path), source_mode=source_mode)
        tmp_path.replace(out_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    out = str(out_path)
    print(f"[OK] 대시보드 생성: {out}  ({note}, {len(df)}개 지역)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
