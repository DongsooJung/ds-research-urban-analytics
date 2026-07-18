"""
seoul_citydata — 서울 실시간 도시데이터 수집·파싱·분석 패키지

Example:
    >>> from seoul_citydata import fetch_many, to_dataframe, congestion_ranking
    >>> from seoul_citydata.areas import ALL_AREAS
    >>> raw = fetch_many(ALL_AREAS)          # SEOUL_API_KEY 환경변수 사용
    >>> df = to_dataframe(raw)
    >>> congestion_ranking(df, top=10)
"""
from .api import fetch_citydata, fetch_many, get_api_key, SeoulAPIError
from .parser import (
    to_record,
    to_dataframe,
    parse_population,
    parse_weather,
    parse_road,
    parse_commercial,
    parse_forecast,
)
from .analysis import (
    congestion_ranking,
    busiest_areas,
    category_summary,
    demographic_profile,
    gender_balance,
    weather_congestion_corr,
    summary_stats,
)
from .areas import ALL_AREAS, AREAS_BY_CATEGORY, CONGEST_LEVELS, congestion_score
from .subway import (
    MONITORED_STATIONS,
    SubwayAPIError,
    build_arrival_url,
    build_subway_dashboard_data,
    fetch_many_station_arrivals,
    fetch_station_arrivals,
    get_subway_api_key,
)

__all__ = [
    "fetch_citydata", "fetch_many", "get_api_key", "SeoulAPIError",
    "to_record", "to_dataframe", "parse_population", "parse_weather",
    "parse_road", "parse_commercial", "parse_forecast",
    "congestion_ranking", "busiest_areas", "category_summary",
    "demographic_profile", "gender_balance", "weather_congestion_corr",
    "summary_stats",
    "ALL_AREAS", "AREAS_BY_CATEGORY", "CONGEST_LEVELS", "congestion_score",
    "MONITORED_STATIONS", "SubwayAPIError", "build_arrival_url",
    "build_subway_dashboard_data", "fetch_many_station_arrivals",
    "fetch_station_arrivals", "get_subway_api_key",
]
