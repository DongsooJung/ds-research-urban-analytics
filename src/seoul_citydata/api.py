"""
서울 실시간 도시데이터 API 클라이언트

엔드포인트:
    http://openapi.seoul.go.kr:8088/{KEY}/{TYPE}/citydata/{START}/{END}/{AREA_NM}

인증키는 SEOUL_API_KEY 환경변수에서 읽는다. 미설정 시 "sample" 키를 사용하며,
sample 키는 지역과 무관하게 동일한 고정 샘플을 반환한다(구조 확인/개발용).
실제 지역별 실시간 데이터는 data.seoul.go.kr에서 발급받은 개인 키가 필요하다.
"""
from __future__ import annotations

import os
import json
import logging
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

logger = logging.getLogger(__name__)

BASE_URL = "http://openapi.seoul.go.kr:8088"
SERVICE = "citydata"


def get_api_key(explicit: Optional[str] = None) -> str:
    """API 키 결정: 인자 > 환경변수 > 'sample'."""
    return explicit or os.environ.get("SEOUL_API_KEY") or "sample"


def build_url(
    area_name: str,
    api_key: Optional[str] = None,
    fmt: str = "json",
    start: int = 1,
    end: int = 5,
) -> str:
    """citydata 요청 URL 생성 (지역명은 URL 인코딩)."""
    key = get_api_key(api_key)
    area_enc = urllib.parse.quote(area_name)
    return f"{BASE_URL}/{key}/{fmt}/{SERVICE}/{start}/{end}/{area_enc}"


class SeoulAPIError(RuntimeError):
    """서울 API 오류 (RESULT.CODE가 정상이 아닌 경우 등)."""


def fetch_citydata(
    area_name: str,
    api_key: Optional[str] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """단일 지역의 실시간 도시데이터(원본 JSON dict) 반환.

    Raises:
        SeoulAPIError: 네트워크 오류 또는 API가 CITYDATA를 반환하지 않은 경우
    """
    url = build_url(area_name, api_key)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - 네트워크/파싱 오류 통합
        raise SeoulAPIError(f"{area_name} 요청 실패: {e}") from e

    # 최상위 오류 응답 처리 (키 오류 등은 RESULT로 옴)
    result = data.get("RESULT") or {}
    code = result.get("RESULT.CODE") or result.get("CODE")
    if "CITYDATA" not in data:
        raise SeoulAPIError(
            f"{area_name}: CITYDATA 없음 (code={code}, msg={result})"
        )

    logger.debug("fetch OK: %s", area_name)
    return data


def fetch_many(
    area_names: list[str],
    api_key: Optional[str] = None,
    timeout: float = 30.0,
    max_workers: int = 4,
) -> dict[str, dict[str, Any]]:
    """여러 지역을 병렬 요청. 실패 지역은 결과에서 제외하고 경고 로그.

    Returns:
        {area_name: raw_json_dict}
    """
    out: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(fetch_citydata, a, api_key, timeout): a
            for a in area_names
        }
        for fut in as_completed(futures):
            area = futures[fut]
            try:
                out[area] = fut.result()
            except SeoulAPIError as e:
                logger.warning("skip %s: %s", area, e)
    return out
