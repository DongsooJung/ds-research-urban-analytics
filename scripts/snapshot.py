#!/usr/bin/env python3
"""
서울 실시간 도시데이터 스냅샷 CLI

전체(또는 지정) 지역의 실시간 데이터를 수집해 CSV로 저장하고 요약을 출력한다.

사용:
    # SEOUL_API_KEY 환경변수에 실제 키 설정 시 지역별 실데이터 수집
    python scripts/snapshot.py
    python scripts/snapshot.py --category 관광특구 --out snapshot.csv
    python scripts/snapshot.py --areas 강남역 여의도 홍대_관광특구

키 미설정 시 sample 키로 동작(모든 지역 동일 샘플) — 파이프라인 점검용.
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seoul_citydata import (  # noqa: E402
    fetch_many, to_dataframe, congestion_ranking, category_summary,
    weather_congestion_corr, summary_stats, get_api_key,
)
from seoul_citydata.areas import ALL_AREAS, AREAS_BY_CATEGORY  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="서울 실시간 도시데이터 스냅샷")
    ap.add_argument("--category", help="특정 카테고리만 (예: 관광특구)")
    ap.add_argument("--areas", nargs="+", help="특정 지역명 목록 (밑줄은 공백으로 치환)")
    ap.add_argument("--out", default="snapshot.csv", help="CSV 출력 경로")
    ap.add_argument("--workers", type=int, default=4, help="병렬 요청 수")
    args = ap.parse_args(argv)

    if args.areas:
        areas = [a.replace("_", " ") for a in args.areas]
    elif args.category:
        areas = AREAS_BY_CATEGORY.get(args.category, [])
        if not areas:
            print(f"알 수 없는 카테고리: {args.category}")
            print("가능:", ", ".join(AREAS_BY_CATEGORY))
            return 2
    else:
        areas = ALL_AREAS

    key = get_api_key()
    key_note = "sample(고정 샘플)" if key == "sample" else "개인 키"
    print(f"[i] {len(areas)}개 지역 수집 중... (키: {key_note})")

    raw = fetch_many(areas, max_workers=args.workers)
    df = to_dataframe(raw)
    if df.empty:
        print("수집 실패: 데이터 없음")
        return 1

    df.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[✓] {len(df)}개 지역 → {args.out}\n")

    stats = summary_stats(df)
    print("=== 요약 ===")
    print(f"  지역 수: {stats['n_areas']}")
    print(f"  총 인구(추정): {stats['total_ppltn_min']:,.0f} ~ {stats['total_ppltn_max']:,.0f}명")
    print(f"  평균 혼잡점수: {stats['mean_congest_score']:.2f} / 4")
    print(f"  붐빔(약간붐빔 이상) 지역: {stats['n_crowded']}개")
    if stats["mean_pm10"] is not None:
        print(f"  평균 PM10: {stats['mean_pm10']:.1f} / 기온: {stats['mean_temp']:.1f}°C")

    print("\n=== 혼잡 TOP 10 ===")
    print(congestion_ranking(df, top=10).to_string())

    if key != "sample":  # 실데이터일 때만 카테고리/상관 의미 있음
        print("\n=== 카테고리별 요약 ===")
        print(category_summary(df).round(1).to_string())
        print("\n=== 혼잡-날씨/대기질 상관 ===")
        print(weather_congestion_corr(df).round(3).to_string())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
