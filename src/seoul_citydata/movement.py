"""서울 대도시권 생활인구의 외부 유입 집계.

원본은 하루 약 60만 행이므로 매시간 OpenAPI 전체를 순회하지 않는다.
서울 열린데이터광장의 최신 일별 ZIP을 기준일이 바뀔 때만 내려받아
출근(08시)·퇴근(18시) 시간대의 서울 외 거주 생활인구를 집계한다.
"""
from __future__ import annotations

import csv
import io
import re
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from typing import Any

DATASET_ID = "OA-22850"
DATASET_URL = "https://data.seoul.go.kr/dataList/OA-22850/A/1/datasetView.do"
FILE_VIEW_URL = (
    "https://data.seoul.go.kr/dataList/fileView.do?infId=OA-22850&srvType=F"
)
DOWNLOAD_URL = (
    "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?useCache=false"
)
FILE_PATTERN = re.compile(r"250_ORGN_CT_(\d{8})\.zip")
COMMUTE_HOURS = ("08", "18")


class MovementDataError(RuntimeError):
    """대도시권 생활인구 파일 탐색·다운로드·집계 오류."""


def _read_response(response: Any) -> bytes:
    with response:
        return response.read()


def discover_latest_reference_date(
    *,
    timeout: float = 30.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> str:
    """공식 파일 목록에서 가장 최근 YYYYMMDD 기준일을 찾는다."""
    try:
        html = _read_response(opener(FILE_VIEW_URL, timeout=timeout)).decode(
            "utf-8", errors="replace"
        )
    except Exception as exc:  # noqa: BLE001 - 네트워크 오류 통합
        raise MovementDataError(f"대도시권 생활인구 파일 목록 요청 실패: {exc}") from exc
    dates = FILE_PATTERN.findall(html)
    if not dates:
        raise MovementDataError("대도시권 생활인구 최신 기준일을 찾지 못했습니다.")
    return max(dates)


def download_daily_zip(
    reference_date: str,
    *,
    timeout: float = 120.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> bytes:
    """공식 다운로드 서버에서 선택 기준일의 ZIP을 받는다."""
    sequence = reference_date[2:]
    body = urllib.parse.urlencode(
        {"infId": DATASET_ID, "infSeq": "1", "seq": sequence}
    ).encode("ascii")
    request = urllib.request.Request(DOWNLOAD_URL, data=body, method="POST")
    try:
        payload = _read_response(opener(request, timeout=timeout))
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if not archive.namelist():
                raise MovementDataError("대도시권 생활인구 ZIP이 비어 있습니다.")
        return payload
    except MovementDataError:
        raise
    except Exception as exc:  # noqa: BLE001 - 네트워크/ZIP 오류 통합
        raise MovementDataError(f"대도시권 생활인구 ZIP 요청 실패: {exc}") from exc


def _number(value: str) -> float:
    if not value or value in {"*", r"\N"}:
        return 0.0
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return 0.0


def _origin_label(code: str, origins: dict[str, dict[str, str]]) -> tuple[str, bool]:
    if code == "11000":
        return "서울", False
    info = origins.get(code)
    if not info:
        return ("거주지 미상", False) if code.strip() in {"", r"\N"} else (code, False)
    province = info.get("province", "").strip()
    name = info.get("name", "").strip()
    label = " ".join(part for part in (province, name) if part)
    return label or code, province != "서울"


def _new_period() -> dict[str, Any]:
    return {
        "row_count": 0,
        "total_population": 0.0,
        "external_population": 0.0,
        "external_by_origin": {},
        "external_by_destination": {},
        "external_by_district": {},
    }


def _finish_period(period: dict[str, Any]) -> dict[str, Any]:
    external = period["external_population"]
    total = period["total_population"]
    origins = [
        {"origin": name, "population": round(population)}
        for name, population in sorted(
            period["external_by_origin"].items(),
            key=lambda item: item[1],
            reverse=True,
        )[:10]
    ]
    destinations = [
        {
            "code": code,
            "district": values["district"],
            "dong": values["dong"],
            "population": round(values["population"]),
        }
        for code, values in sorted(
            period["external_by_destination"].items(),
            key=lambda item: item[1]["population"],
            reverse=True,
        )[:10]
    ]
    districts = [
        {"district": district, "population": round(population)}
        for district, population in sorted(
            period["external_by_district"].items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
    return {
        "row_count": period["row_count"],
        "total_population": round(total),
        "external_population": round(external),
        "external_rate": round(external / total * 100, 1) if total else 0.0,
        "top_origins": origins,
        "top_destinations": destinations,
        "by_destination_district": districts,
    }


def aggregate_movement_zip(
    zip_bytes: bytes,
    admin_dongs: dict[str, dict[str, str]],
    origins: dict[str, dict[str, str]],
    *,
    hours: tuple[str, ...] = COMMUTE_HOURS,
) -> dict[str, Any]:
    """일별 ZIP을 스트리밍하며 지정 시간대의 외부 유입만 집계한다."""
    periods = {hour: _new_period() for hour in hours}
    reference_date = ""
    generated_on = ""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not names:
                raise MovementDataError("대도시권 생활인구 CSV가 없습니다.")
            with archive.open(names[0]) as raw:
                text = io.TextIOWrapper(raw, encoding="cp949", errors="replace", newline="")
                reader = csv.reader(text)
                next(reader, None)
                for row in reader:
                    if len(row) < 6:
                        continue
                    reference_date = reference_date or row[0].strip()
                    generated_on = row[-1].strip() if row[-1].strip() else generated_on
                    hour = row[1].strip().zfill(2)
                    if hour not in periods:
                        continue
                    destination_code = row[2].strip()
                    origin_code = row[4].strip()
                    population = _number(row[5])
                    period = periods[hour]
                    period["row_count"] += 1
                    period["total_population"] += population
                    origin_label, is_external = _origin_label(origin_code, origins)
                    if not is_external:
                        continue
                    period["external_population"] += population
                    period["external_by_origin"][origin_label] = (
                        period["external_by_origin"].get(origin_label, 0.0) + population
                    )
                    destination = admin_dongs.get(destination_code, {})
                    district_code = destination_code[:5]
                    district_reference = origins.get(district_code, {})
                    district = (
                        destination.get("district")
                        or district_reference.get("name")
                        or district_code
                    )
                    dong = destination.get("dong") or destination_code
                    target = period["external_by_destination"].setdefault(
                        destination_code,
                        {"district": district, "dong": dong, "population": 0.0},
                    )
                    target["population"] += population
                    period["external_by_district"][district] = (
                        period["external_by_district"].get(district, 0.0) + population
                    )
    except MovementDataError:
        raise
    except Exception as exc:  # noqa: BLE001 - ZIP/CSV 오류 통합
        raise MovementDataError(f"대도시권 생활인구 집계 실패: {exc}") from exc

    return {
        "reference_date": reference_date,
        "generated_on": generated_on,
        "periods": {hour: _finish_period(period) for hour, period in periods.items()},
        "source": {
            "portal": "서울 열린데이터광장",
            "dataset": "서울시 대도시권 생활인구(행정동별)",
            "service": "se250mSpopOrgnCt",
            "url": DATASET_URL,
            "coverage": "거주지 기준 서울 생활인구의 대도시권·전국 유입 분포",
            "freshness_note": (
                "실시간 이동량이나 이동 건수가 아닌 추정 생활인구입니다. "
                "3명 이하 값은 비식별 처리되어 합계가 소폭 작을 수 있습니다."
            ),
        },
    }


def fetch_movement_dashboard_data(
    admin_dongs: dict[str, dict[str, str]],
    origins: dict[str, dict[str, str]],
    *,
    existing: dict[str, Any] | None = None,
    timeout: float = 120.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[dict[str, Any], bool]:
    """최신 기준일이 같으면 기존 집계를 재사용하고, 바뀌면 새로 처리한다."""
    latest = discover_latest_reference_date(timeout=min(timeout, 30.0), opener=opener)
    if (
        existing
        and existing.get("reference_date") == latest
        and all(hour in (existing.get("periods") or {}) for hour in COMMUTE_HOURS)
    ):
        return existing, True
    payload = download_daily_zip(latest, timeout=timeout, opener=opener)
    result = aggregate_movement_zip(payload, admin_dongs, origins)
    if result.get("reference_date") != latest:
        raise MovementDataError(
            f"파일 기준일 불일치: 목록 {latest}, 원본 {result.get('reference_date')}"
        )
    return result, False
