"""시민 이동에 유용한 서울 열린데이터광장 실시간 정보 수집·집계.

데이터셋:
- 서울시 공공자전거 따릉이 실시간 대여정보 (bikeList)
- 서울시 시영주차장 실시간 주차대수 정보 (GetParkingInfo)
- 서울시 실시간 도시데이터의 사고·통제 항목
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

BASE_URL = "http://openapi.seoul.go.kr:8088"
BIKE_SERVICE = "bikeList"
BIKE_WRAPPER = "rentBikeStatus"
PARKING_SERVICE = "GetParkingInfo"
PARKING_WRAPPER = "GetParkingInfo"

BIKE_SOURCE_URL = "https://data.seoul.go.kr/dataList/OA-15493/A/1/datasetView.do"
PARKING_SOURCE_URL = "https://data.seoul.go.kr/dataList/OA-21709/A/1/datasetView.do"
CITYDATA_SOURCE_URL = "https://data.seoul.go.kr/dataList/OA-21285/A/1/datasetView.do"


class MobilityAPIError(RuntimeError):
    """따릉이·주차장 API 호출 또는 응답 오류."""


def get_open_api_key(explicit: str | None = None) -> str:
    """인자 > 환경변수 > sample 순으로 서울 열린데이터광장 키를 결정한다."""
    return explicit or os.environ.get("SEOUL_API_KEY") or "sample"


def build_page_url(
    service: str,
    start: int,
    end: int,
    api_key: str | None = None,
) -> str:
    key = urllib.parse.quote(get_open_api_key(api_key), safe="")
    return f"{BASE_URL}/{key}/json/{service}/{start}/{end}/"


def _request_json(url: str, timeout: float, tries: int) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(tries):
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "stargateedu-dashboard/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            if raw.lstrip().startswith("<"):
                raise MobilityAPIError("JSON 대신 XML 오류 응답을 받았습니다")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise MobilityAPIError("JSON 최상위 객체가 아닙니다")
            return payload
        except Exception as exc:  # noqa: BLE001 - 네트워크·파싱 오류 통합 재시도
            last_error = exc
            if attempt + 1 < tries:
                time.sleep(0.4 * (attempt + 1))
    raise MobilityAPIError(f"서울 이동정보 API 요청 실패: {last_error}") from last_error


def fetch_paged_rows(
    service: str,
    wrapper: str,
    api_key: str | None = None,
    page_size: int = 1000,
    max_pages: int = 10,
    timeout: float = 30.0,
    tries: int = 3,
) -> list[dict[str, Any]]:
    """서울 OpenAPI 표준 페이징 응답의 모든 행을 수집한다."""
    key = get_open_api_key(api_key)
    effective_page_size = min(page_size, 5) if key == "sample" else min(page_size, 1000)
    rows: list[dict[str, Any]] = []
    start = 1

    for _ in range(max_pages):
        end = start + effective_page_size - 1
        payload = _request_json(build_page_url(service, start, end, key), timeout, tries)
        container = payload.get(wrapper)
        if not isinstance(container, dict):
            top_error = payload.get("RESULT") or {}
            message = top_error.get("MESSAGE") or f"{wrapper} 응답이 없습니다"
            raise MobilityAPIError(f"{service}: {message}")

        result = container.get("RESULT") or {}
        if result.get("CODE") not in (None, "INFO-000"):
            raise MobilityAPIError(
                f"{service}: {result.get('CODE')} {result.get('MESSAGE', '')}".strip()
            )

        page_rows = container.get("row") or []
        if not isinstance(page_rows, list):
            raise MobilityAPIError(f"{service}: row 목록이 아닙니다")
        rows.extend(row for row in page_rows if isinstance(row, dict))

        # 일부 실시간 API는 list_total_count에 전체 건수가 아니라 현재 페이지
        # 건수를 반환한다. 꽉 찬 페이지라면 다음 페이지를 확인하고, 짧은
        # 페이지 또는 빈 페이지에서 종료해야 서울 전역 데이터를 놓치지 않는다.
        if key == "sample" or not page_rows or len(page_rows) < effective_page_size:
            break
        start = end + 1

    return rows


def fetch_bike_status(api_key: str | None = None) -> list[dict[str, Any]]:
    """서울 전역 따릉이 대여소의 실시간 대여 가능 정보를 수집한다."""
    return fetch_paged_rows(BIKE_SERVICE, BIKE_WRAPPER, api_key)


def fetch_parking_status(api_key: str | None = None) -> list[dict[str, Any]]:
    """시영주차장의 실시간 주차대수·요금·운영 정보를 수집한다."""
    return fetch_paged_rows(PARKING_SERVICE, PARKING_WRAPPER, api_key)


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    parsed = _number(value)
    return max(0, int(parsed)) if parsed is not None else 0


def _station_name(value: Any) -> str:
    name = str(value or "이름 없는 대여소").strip()
    if ". " in name and name.split(". ", 1)[0].isdigit():
        return name.split(". ", 1)[1]
    return name


def _build_bike_data(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    stations: list[dict[str, Any]] = []
    for row in rows:
        station_id = str(row.get("stationId") or "").strip()
        if not station_id:
            continue
        bikes = _integer(row.get("parkingBikeTotCnt"))
        racks = _integer(row.get("rackTotCnt"))
        ratio = _number(row.get("shared"))
        stations.append({
            "id": station_id,
            "name": _station_name(row.get("stationName")),
            "bikes": bikes,
            "racks": racks,
            "ratio": round(ratio, 1) if ratio is not None else None,
            "latitude": _number(row.get("stationLatitude")),
            "longitude": _number(row.get("stationLongitude")),
        })

    top_available = sorted(stations, key=lambda item: (-item["bikes"], item["name"]))[:10]
    low_availability = sorted(
        (item for item in stations if item["bikes"] <= 2),
        key=lambda item: (item["bikes"], item["name"]),
    )[:10]
    return {
        "station_count": len(stations),
        "available_bikes": sum(item["bikes"] for item in stations),
        "empty_station_count": sum(item["bikes"] == 0 for item in stations),
        "low_station_count": sum(item["bikes"] <= 2 for item in stations),
        "top_available": top_available,
        "low_availability": low_availability,
    }


def _fee_text(row: dict[str, Any]) -> str:
    if str(row.get("PAY_YN") or "") == "N":
        return "무료"
    fee = _number(row.get("BSC_PRK_CRG"))
    minutes = _number(row.get("BSC_PRK_HR"))
    if fee is None or minutes is None:
        return str(row.get("PAY_YN_NM") or "요금 확인 필요")
    return f"{int(fee):,}원/{int(minutes)}분"


def _district(address: str) -> str:
    first = address.split(" ", 1)[0] if address else ""
    return first if first.endswith("구") else "기타"


def _build_parking_data(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    lots: list[dict[str, Any]] = []
    for row in rows:
        capacity_value = _number(row.get("TPKCT"))
        occupied_value = _number(row.get("NOW_PRK_VHCL_CNT"))
        if (
            str(row.get("PRK_STTS_YN") or "") != "1"
            or capacity_value is None
            or occupied_value is None
            or capacity_value <= 0
        ):
            continue
        capacity = max(0, int(capacity_value))
        occupied = max(0, int(occupied_value))
        available = max(0, capacity - occupied)
        address = str(row.get("ADDR") or "").strip()
        lots.append({
            "code": str(row.get("PKLT_CD") or ""),
            "name": str(row.get("PKLT_NM") or "이름 없는 주차장").strip(),
            "address": address,
            "district": _district(address),
            "capacity": capacity,
            "occupied": occupied,
            "available": available,
            "occupancy_rate": round(min(occupied / capacity * 100, 100), 1),
            "updated_at": str(row.get("NOW_PRK_VHCL_UPDT_TM") or ""),
            "fee": _fee_text(row),
        })

    district_groups: dict[str, dict[str, int | str]] = {}
    for lot in lots:
        group = district_groups.setdefault(
            lot["district"],
            {"district": lot["district"], "lot_count": 0, "available": 0, "capacity": 0},
        )
        group["lot_count"] = int(group["lot_count"]) + 1
        group["available"] = int(group["available"]) + lot["available"]
        group["capacity"] = int(group["capacity"]) + lot["capacity"]

    by_district = sorted(
        district_groups.values(),
        key=lambda item: (-int(item["available"]), str(item["district"])),
    )
    top_available = sorted(lots, key=lambda item: (-item["available"], item["name"]))[:10]
    latest_updates = [lot["updated_at"] for lot in lots if lot["updated_at"]]
    return {
        "live_lot_count": len(lots),
        "available_spaces": sum(lot["available"] for lot in lots),
        "full_lot_count": sum(lot["available"] == 0 for lot in lots),
        "updated_at": max(latest_updates) if latest_updates else None,
        "top_available": top_available,
        "by_district": by_district,
    }


def _build_incident_data(
    city_responses: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    incidents: dict[tuple[str, str], dict[str, Any]] = {}
    for response in city_responses:
        citydata = response.get("CITYDATA", response)
        area = str(citydata.get("AREA_NM") or "").strip()
        for row in citydata.get("ACDNT_CNTRL_STTS") or []:
            info = str(row.get("ACDNT_INFO") or "").strip()
            occurred_at = str(row.get("ACDNT_OCCR_DT") or "").strip()
            if not info:
                continue
            key = (info, occurred_at)
            existing = incidents.get(key)
            if existing:
                if area and area not in existing["areas"]:
                    existing["areas"].append(area)
                continue
            incidents[key] = {
                "type": str(row.get("ACDNT_TYPE") or "교통 통제"),
                "detail": str(row.get("ACDNT_DTYPE") or ""),
                "info": info,
                "occurred_at": occurred_at,
                "expected_clear_at": str(row.get("EXP_CLR_DT") or ""),
                "updated_at": str(row.get("ACDNT_TIME") or ""),
                "areas": [area] if area else [],
            }

    items = sorted(
        incidents.values(),
        key=lambda item: (item["updated_at"], item["occurred_at"]),
        reverse=True,
    )
    latest_updates = [item["updated_at"] for item in items if item["updated_at"]]
    return {
        "incident_count": len(items),
        "updated_at": max(latest_updates) if latest_updates else None,
        "items": items[:12],
    }


def build_mobility_dashboard_data(
    bike_rows: Iterable[dict[str, Any]],
    parking_rows: Iterable[dict[str, Any]],
    city_responses: Iterable[dict[str, Any]] = (),
    collected_at: str | None = None,
) -> dict[str, Any]:
    """세 데이터 소스를 시민 이동정보 대시보드용 구조로 변환한다."""
    collected = collected_at or datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "collected_at": collected,
        "bike": _build_bike_data(bike_rows),
        "parking": _build_parking_data(parking_rows),
        "incidents": _build_incident_data(city_responses),
        "sources": {
            "bike": {
                "dataset": "서울시 공공자전거 따릉이 실시간 대여정보",
                "service": BIKE_SERVICE,
                "url": BIKE_SOURCE_URL,
                "coverage": "서울 전역 대여소",
            },
            "parking": {
                "dataset": "서울시 시영주차장 실시간 주차대수 정보",
                "service": PARKING_SERVICE,
                "url": PARKING_SOURCE_URL,
                "coverage": "실시간 연계 시영주차장",
                "freshness_note": "주차장 여건에 따라 실제 정보와 5분 이상 차이가 날 수 있습니다.",
            },
            "incidents": {
                "dataset": "서울시 실시간 도시데이터",
                "service": "citydata.ACDNT_CNTRL_STTS",
                "url": CITYDATA_SOURCE_URL,
                "coverage": "수집 중인 주요 핫스팟 주변 사고·통제",
            },
        },
    }
