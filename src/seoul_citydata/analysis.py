"""
서울 실시간 도시데이터 분석

지역별 스냅샷 DataFrame을 입력으로 혼잡도 순위·인구통계 프로파일·
날씨/대기질-혼잡 상관·카테고리별 요약을 산출한다.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

AGE_COLS = [f"rate_{d}" for d in (0, 10, 20, 30, 40, 50, 60, 70)]


def congestion_ranking(df: pd.DataFrame, top: Optional[int] = None) -> pd.DataFrame:
    """인구 중앙값 기준 혼잡 순위 (내림차순)."""
    cols = ["area", "category", "congest_level", "congest_score",
            "ppltn_min", "ppltn_max", "ppltn_mid"]
    have = [c for c in cols if c in df.columns]
    ranked = df[have].sort_values("ppltn_mid", ascending=False).reset_index(drop=True)
    ranked.index += 1
    ranked.index.name = "rank"
    return ranked.head(top) if top else ranked


def busiest_areas(df: pd.DataFrame, n: int = 5) -> list[str]:
    """가장 붐비는 상위 n개 지역명."""
    return congestion_ranking(df, top=n)["area"].tolist()


def category_summary(df: pd.DataFrame) -> pd.DataFrame:
    """카테고리별 평균 인구·혼잡점수·대기질 요약."""
    agg = {
        "ppltn_mid": "mean",
        "congest_score": "mean",
    }
    for c in ("pm10", "pm25", "temp", "road_spd"):
        if c in df.columns:
            agg[c] = "mean"
    g = df.groupby("category").agg(agg)
    g["area_count"] = df.groupby("category").size()
    return g.sort_values("ppltn_mid", ascending=False)


def demographic_profile(df: pd.DataFrame) -> pd.Series:
    """전체 지역 평균 연령대 분포 (인구 가중평균)."""
    weights = df["ppltn_mid"].fillna(0.0)
    if weights.sum() == 0:
        weights = pd.Series(np.ones(len(df)), index=df.index)
    profile = {}
    for col in AGE_COLS:
        if col in df.columns:
            vals = df[col].fillna(0.0)
            profile[col] = float(np.average(vals, weights=weights))
    return pd.Series(profile, name="age_distribution")


def gender_balance(df: pd.DataFrame) -> pd.DataFrame:
    """지역별 성비 (남성 우세도 = male - female)."""
    out = df[["area", "male_rate", "female_rate"]].copy()
    out["male_lead"] = out["male_rate"] - out["female_rate"]
    return out.sort_values("male_lead", ascending=False).reset_index(drop=True)


def weather_congestion_corr(df: pd.DataFrame) -> pd.Series:
    """혼잡 점수와 날씨/대기질 지표 간 상관계수.

    지역 수가 적으면 NaN이 나올 수 있다.
    """
    metrics = ["temp", "humidity", "pm10", "pm25", "uv_index", "road_spd"]
    have = [m for m in metrics if m in df.columns]
    corrs = {}
    base = df["congest_score"].astype(float)
    for m in have:
        col = df[m].astype(float)
        if col.notna().sum() >= 3 and col.nunique() > 1 and base.nunique() > 1:
            corrs[m] = float(base.corr(col))
        else:
            corrs[m] = float("nan")
    return pd.Series(corrs, name="corr_with_congestion")


def summary_stats(df: pd.DataFrame) -> dict:
    """스냅샷 전체 요약 통계."""
    total_min = float(df["ppltn_min"].sum()) if "ppltn_min" in df else 0.0
    total_max = float(df["ppltn_max"].sum()) if "ppltn_max" in df else 0.0
    crowded = df[df["congest_score"] >= 3] if "congest_score" in df else df.iloc[0:0]
    return {
        "n_areas": int(len(df)),
        "total_ppltn_min": total_min,
        "total_ppltn_max": total_max,
        "mean_congest_score": float(df["congest_score"].mean()) if "congest_score" in df else 0.0,
        "n_crowded": int(len(crowded)),  # 약간 붐빔 이상
        "crowded_areas": crowded["area"].tolist() if "area" in crowded else [],
        "mean_pm10": float(df["pm10"].mean()) if "pm10" in df and df["pm10"].notna().any() else None,
        "mean_temp": float(df["temp"].mean()) if "temp" in df and df["temp"].notna().any() else None,
    }
