"""
서울 실시간 도시데이터 파서

중첩 JSON(CITYDATA) → 분석용 평탄 레코드/DataFrame 변환.
인구·혼잡·날씨·대기질·도로소통·상권 핵심 지표를 추출한다.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from .areas import congestion_score, AREA_TO_CATEGORY, CMRCL_LEVELS, ROAD_TRAFFIC_LEVELS


def _f(value: Any) -> Optional[float]:
    """문자열/None → float (변환 실패 시 None)."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_population(citydata: dict[str, Any]) -> dict[str, Any]:
    """LIVE_PPLTN_STTS → 인구/혼잡 지표."""
    lst = citydata.get("LIVE_PPLTN_STTS") or []
    if not lst:
        return {}
    p = lst[0]
    return {
        "congest_level": p.get("AREA_CONGEST_LVL"),
        "congest_score": congestion_score(p.get("AREA_CONGEST_LVL")),
        "ppltn_min": _f(p.get("AREA_PPLTN_MIN")),
        "ppltn_max": _f(p.get("AREA_PPLTN_MAX")),
        "male_rate": _f(p.get("MALE_PPLTN_RATE")),
        "female_rate": _f(p.get("FEMALE_PPLTN_RATE")),
        "rate_0": _f(p.get("PPLTN_RATE_0")),
        "rate_10": _f(p.get("PPLTN_RATE_10")),
        "rate_20": _f(p.get("PPLTN_RATE_20")),
        "rate_30": _f(p.get("PPLTN_RATE_30")),
        "rate_40": _f(p.get("PPLTN_RATE_40")),
        "rate_50": _f(p.get("PPLTN_RATE_50")),
        "rate_60": _f(p.get("PPLTN_RATE_60")),
        "rate_70": _f(p.get("PPLTN_RATE_70")),
        "resident_rate": _f(p.get("RESNT_PPLTN_RATE")),
        "non_resident_rate": _f(p.get("NON_RESNT_PPLTN_RATE")),
        "ppltn_time": p.get("PPLTN_TIME"),
    }


def parse_weather(citydata: dict[str, Any]) -> dict[str, Any]:
    """WEATHER_STTS → 날씨/대기질 지표."""
    lst = citydata.get("WEATHER_STTS") or []
    if not lst:
        return {}
    w = lst[0]
    return {
        "temp": _f(w.get("TEMP")),
        "humidity": _f(w.get("HUMIDITY")),
        "wind_spd": _f(w.get("WIND_SPD")),
        "precipitation": w.get("PRECIPITATION"),
        "pm10": _f(w.get("PM10")),
        "pm25": _f(w.get("PM25")),
        "air_idx": w.get("AIR_IDX"),
        "air_idx_val": _f(w.get("AIR_IDX_MVL")),
        "uv_index": _f(w.get("UV_INDEX")),
        "weather_time": w.get("WEATHER_TIME"),
    }


def parse_road(citydata: dict[str, Any]) -> dict[str, Any]:
    """ROAD_TRAFFIC_STTS.AVG_ROAD_DATA → 도로 소통 지표."""
    road = (citydata.get("ROAD_TRAFFIC_STTS") or {}).get("AVG_ROAD_DATA") or {}
    idx = road.get("ROAD_TRAFFIC_IDX")
    return {
        "road_idx": idx,
        "road_score": ROAD_TRAFFIC_LEVELS.get((idx or "").strip(), 0),
        "road_spd": _f(road.get("ROAD_TRAFFIC_SPD")),
    }


def parse_commercial(citydata: dict[str, Any]) -> dict[str, Any]:
    """LIVE_CMRCL_STTS → 상권 지표."""
    c = citydata.get("LIVE_CMRCL_STTS") or {}
    lvl = c.get("AREA_CMRCL_LVL")
    return {
        "cmrcl_level": lvl,
        "cmrcl_score": CMRCL_LEVELS.get((lvl or "").strip(), 0),
        "payment_cnt": _f(c.get("AREA_SH_PAYMENT_CNT")),
    }


def parse_forecast(citydata: dict[str, Any]) -> list[dict[str, Any]]:
    """LIVE_PPLTN_STTS[0].FCST_PPLTN → 12단계 인구 예보 레코드 리스트."""
    lst = citydata.get("LIVE_PPLTN_STTS") or []
    if not lst:
        return []
    fcst = lst[0].get("FCST_PPLTN") or []
    out = []
    for f in fcst:
        out.append({
            "fcst_time": f.get("FCST_TIME"),
            "fcst_congest_level": f.get("FCST_CONGEST_LVL"),
            "fcst_congest_score": congestion_score(f.get("FCST_CONGEST_LVL")),
            "fcst_ppltn_min": _f(f.get("FCST_PPLTN_MIN")),
            "fcst_ppltn_max": _f(f.get("FCST_PPLTN_MAX")),
        })
    return out


def to_record(citydata_response: dict[str, Any]) -> dict[str, Any]:
    """원본 API 응답(dict) → 한 지역의 평탄 레코드.

    citydata_response는 fetch_citydata()가 반환한 최상위 dict이거나
    CITYDATA dict 자체 둘 다 허용한다.
    """
    cd = citydata_response.get("CITYDATA", citydata_response)
    area = cd.get("AREA_NM")
    rec: dict[str, Any] = {
        "area": area,
        "area_cd": cd.get("AREA_CD"),
        "category": AREA_TO_CATEGORY.get(area, "기타"),
    }
    rec.update(parse_population(cd))
    rec.update(parse_weather(cd))
    rec.update(parse_road(cd))
    rec.update(parse_commercial(cd))
    # 인구 중앙값(min/max 평균) 파생
    if rec.get("ppltn_min") is not None and rec.get("ppltn_max") is not None:
        rec["ppltn_mid"] = (rec["ppltn_min"] + rec["ppltn_max"]) / 2.0
    return rec


def to_dataframe(responses: dict[str, dict[str, Any]] | list[dict[str, Any]]) -> pd.DataFrame:
    """여러 지역 응답 → DataFrame.

    Args:
        responses: {area: raw} dict 또는 raw 리스트
    """
    if isinstance(responses, dict):
        items = list(responses.values())
    else:
        items = list(responses)
    records = [to_record(r) for r in items if r]
    return pd.DataFrame(records)
