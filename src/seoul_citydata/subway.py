"""서울시 지하철 실시간 도착정보 수집·집계.

출처: 서울 열린데이터광장 「서울시 지하철 실시간 도착정보」
API: realtimeStationArrival
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

BASE_URL = "http://swopenAPI.seoul.go.kr/api/subway"
SERVICE = "realtimeStationArrival"
SOURCE_URL = "https://data.seoul.go.kr/dataList/OA-12764/F/1/datasetView.do"

# 환승·관광·상권·교통거점을 고르게 반영한 운영 표본.
MONITORED_STATIONS: tuple[str, ...] = (
    "강남", "잠실", "홍대입구", "서울", "고속터미널", "여의도", "건대입구", "명동",
)

LINE_NAMES: dict[str, str] = {
    "1001": "1호선", "1002": "2호선", "1003": "3호선", "1004": "4호선",
    "1005": "5호선", "1006": "6호선", "1007": "7호선", "1008": "8호선",
    "1009": "9호선", "1061": "중앙선", "1063": "경의중앙선", "1065": "공항철도",
    "1067": "경춘선", "1075": "수인분당선", "1077": "신분당선", "1092": "우이신설선",
    "1093": "서해선",
}

LINE_COLORS: dict[str, str] = {
    "1001": "#0052A4", "1002": "#00A84D", "1003": "#EF7C1C", "1004": "#00A5DE",
    "1005": "#996CAC", "1006": "#CD7C2F", "1007": "#747F00", "1008": "#E6186C",
    "1009": "#BDB092", "1061": "#77C4A3", "1063": "#77C4A3", "1065": "#0090D2",
    "1067": "#178C72", "1075": "#FABE00", "1077": "#D4003B", "1092": "#B0CE18",
    "1093": "#8FC31F",
}

NEAR_ARRIVAL_CODES = {"0", "1", "2", "3", "4", "5"}


class SubwayAPIError(RuntimeError):
    """지하철 실시간 API 호출/응답 오류."""


def get_subway_api_key(explicit: str | None = None) -> str:
    """인자 > 환경변수 > sample 순으로 인증키를 결정한다."""
    return explicit or os.environ.get("SEOUL_SUBWAY_API_KEY") or "sample"


def build_arrival_url(station: str, api_key: str | None = None, limit: int = 6) -> str:
    key = get_subway_api_key(api_key)
    encoded = urllib.parse.quote(station)
    return f"{BASE_URL}/{key}/json/{SERVICE}/0/{limit}/{encoded}"


def fetch_station_arrivals(
    station: str,
    api_key: str | None = None,
    limit: int = 6,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """한 역의 실시간 도착정보를 반환한다."""
    request = urllib.request.Request(
        build_arrival_url(station, api_key, limit),
        headers={"Accept": "application/json", "User-Agent": "stargateedu-dashboard/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - 네트워크/응답 오류 통합
        raise SubwayAPIError(f"{station} 도착정보 요청 실패: {exc}") from exc

    error = payload.get("errorMessage") or {}
    if error.get("code") not in (None, "INFO-000"):
        raise SubwayAPIError(f"{station}: {error.get('code')} {error.get('message', '')}".strip())

    arrivals = payload.get("realtimeArrivalList")
    if not isinstance(arrivals, list):
        raise SubwayAPIError(f"{station}: realtimeArrivalList 없음")
    return arrivals


def fetch_many_station_arrivals(
    stations: Iterable[str] = MONITORED_STATIONS,
    api_key: str | None = None,
    limit: int = 6,
    max_workers: int = 4,
) -> dict[str, list[dict[str, Any]]]:
    """여러 역을 병렬 호출하고 실패 역은 제외한다."""
    station_list = list(stations)
    output: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_station_arrivals, station, api_key, limit): station
            for station in station_list
        }
        for future in as_completed(futures):
            station = futures[future]
            try:
                output[station] = future.result()
            except SubwayAPIError:
                continue
    return output


def _seconds(value: Any) -> int | None:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _line_name(line_id: str) -> str:
    return LINE_NAMES.get(line_id, f"노선 {line_id}")


def build_subway_dashboard_data(
    responses: dict[str, list[dict[str, Any]]],
    per_station: int = 2,
) -> dict[str, Any]:
    """역별 API 응답을 대시보드용 요약으로 변환한다.

    도착 목록은 각 역의 API 응답 순서(최선 도착 우선)를 따르며,
    역당 최대 ``per_station``건만 공개한다.
    """
    board: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    updated_values: list[str] = []

    for requested_station in MONITORED_STATIONS:
        rows = responses.get(requested_station) or []
        all_rows.extend(rows)
        selected: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            line_id = str(row.get("subwayId") or "")
            direction = str(row.get("updnLine") or "")
            pair = (line_id, direction)
            if pair in seen and len(selected) < per_station:
                continue
            seen.add(pair)
            selected.append(row)
            if len(selected) >= per_station:
                break
        if len(selected) < per_station:
            for row in rows:
                if row not in selected:
                    selected.append(row)
                if len(selected) >= per_station:
                    break
        for row in selected:
            line_id = str(row.get("subwayId") or "")
            received_at = str(row.get("recptnDt") or "")
            if received_at:
                updated_values.append(received_at)
            seconds = _seconds(row.get("barvlDt"))
            code = str(row.get("arvlCd") or "")
            board.append({
                "station": str(row.get("statnNm") or requested_station),
                "line_id": line_id,
                "line": _line_name(line_id),
                "color": LINE_COLORS.get(line_id, "#8A94A8"),
                "direction": str(row.get("updnLine") or ""),
                "destination": str(row.get("trainLineNm") or ""),
                "message": str(row.get("arvlMsg2") or "정보 없음"),
                "previous_station": str(row.get("arvlMsg3") or ""),
                "wait_seconds": seconds,
                "received_at": received_at,
                "train_type": str(row.get("btrainSttus") or "일반"),
                "near": code in NEAR_ARRIVAL_CODES or (seconds is not None and seconds <= 180),
            })

    line_groups: dict[str, list[dict[str, Any]]] = {}
    for row in all_rows:
        line_id = str(row.get("subwayId") or "")
        if line_id:
            line_groups.setdefault(line_id, []).append(row)

    lines: list[dict[str, Any]] = []
    for line_id, rows in line_groups.items():
        positive_waits = [seconds for row in rows if (seconds := _seconds(row.get("barvlDt"))) is not None]
        codes = {str(row.get("arvlCd") or "") for row in rows}
        nearest_seconds = min(positive_waits) if positive_waits else (0 if codes & NEAR_ARRIVAL_CODES else None)
        trains = {str(row.get("btrainNo")) for row in rows if row.get("btrainNo")}
        lines.append({
            "line_id": line_id,
            "line": _line_name(line_id),
            "color": LINE_COLORS.get(line_id, "#8A94A8"),
            "arrival_records": len(rows),
            "train_count": len(trains),
            "nearest_wait_seconds": nearest_seconds,
        })
    lines.sort(key=lambda item: (item["nearest_wait_seconds"] is None,
                                 item["nearest_wait_seconds"] or 0, item["line"]))

    return {
        "updated_at": max(updated_values) if updated_values else None,
        "station_count": sum(1 for station in MONITORED_STATIONS if responses.get(station)),
        "requested_station_count": len(MONITORED_STATIONS),
        "arrival_count": len(all_rows),
        "board_count": len(board),
        "near_count": sum(1 for item in board if item["near"]),
        "line_count": len(lines),
        "stations": list(MONITORED_STATIONS),
        "lines": lines,
        "board": board,
        "source": {
            "provider": "서울특별시·TOPIS",
            "portal": "서울 열린데이터광장",
            "dataset": "서울시 지하철 실시간 도착정보",
            "service": SERVICE,
            "url": SOURCE_URL,
            "coverage": f"주요역 {len(MONITORED_STATIONS)}곳·역당 최대 6건 표본",
            "freshness_field": "recptnDt",
        },
    }
