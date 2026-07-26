"""서울 전역 행정동 생활인구 수집·집계.

서울 열린데이터광장의 행정동 생활인구 API는 최근 제공일의 시간대별
내국인 생활인구와 성·연령 구성을 제공한다. 행정동명은 공식 매핑 파일을
함께 읽어 API의 행정동 코드와 연결한다.
"""
from __future__ import annotations

import io
import json
import time
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import datetime
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

BASE_URL = "http://openapi.seoul.go.kr:8088"
SERVICE = "SPOP_LOCAL_RESD_DONG"
DATASET_URL = "https://data.seoul.go.kr/dataList/OA-14991/A/1/datasetView.do"
CODE_DOWNLOAD_URL = (
    "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?useCache=false"
)
XML_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class PopulationAPIError(RuntimeError):
    """생활인구 API 또는 행정동 코드 파일 처리 오류."""


def _fetch_json(
    api_key: str,
    start: int,
    end: int,
    filters: tuple[str, ...] = (),
    timeout: float = 30.0,
    tries: int = 3,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    suffix = "/".join(urllib.parse.quote(value) for value in filters)
    url = f"{BASE_URL}/{api_key}/json/{SERVICE}/{start}/{end}"
    if suffix:
        url += f"/{suffix}"
    for attempt in range(tries):
        try:
            with opener(url, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            root = payload.get(SERVICE)
            if not root:
                raise PopulationAPIError(f"{SERVICE} 응답이 없습니다.")
            result = root.get("RESULT") or {}
            if result.get("CODE") not in (None, "INFO-000"):
                raise PopulationAPIError(
                    f"{result.get('CODE')}: {result.get('MESSAGE', 'API 오류')}"
                )
            return root
        except PopulationAPIError:
            raise
        except Exception as exc:  # noqa: BLE001 - 네트워크/JSON 오류 통합
            if attempt + 1 == tries:
                raise PopulationAPIError(f"생활인구 요청 실패: {exc}") from exc
            time.sleep(0.5 * (attempt + 1))
    raise PopulationAPIError("생활인구 요청 실패")


def fetch_population_rows(
    api_key: str,
    *,
    reference_hour: str | None = None,
    page_size: int = 1000,
    timeout: float = 30.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """최근 제공일의 특정 시간대 행정동 생활인구를 모두 수집한다."""
    probe = _fetch_json(api_key, 1, 1, timeout=timeout, opener=opener)
    probe_rows = probe.get("row") or []
    if not probe_rows:
        raise PopulationAPIError("최근 생활인구 기준일을 확인할 수 없습니다.")

    reference_date = str(probe_rows[0].get("STDR_DE_ID") or "")
    if not reference_date:
        raise PopulationAPIError("생활인구 기준일이 비어 있습니다.")
    hour = reference_hour or datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H")
    hour = str(hour).zfill(2)

    rows: list[dict[str, Any]] = []
    start = 1
    total: int | None = None
    while total is None or start <= total:
        end = start + page_size - 1
        root = _fetch_json(
            api_key,
            start,
            end,
            (reference_date, hour),
            timeout=timeout,
            opener=opener,
        )
        page = root.get("row") or []
        if total is None:
            total = int(root.get("list_total_count") or len(page))
        rows.extend(page)
        if not page or len(page) < page_size:
            break
        start += page_size

    return rows, {"reference_date": reference_date, "reference_hour": hour}


def _xlsx_cell_value(
    cell: ElementTree.Element,
    shared_strings: list[str],
) -> str:
    value = cell.findtext("x:v", default="", namespaces=XML_NS)
    if cell.get("t") == "s" and value:
        return shared_strings[int(value)]
    return value


def parse_admin_dong_mapping(xlsx_bytes: bytes) -> dict[str, dict[str, str]]:
    """공식 행정동 코드 XLSX를 ``행자부 코드 → 구/동명``으로 변환한다."""
    try:
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as workbook:
            shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(node.text or "" for node in item.findall(".//x:t", XML_NS))
                for item in shared_root.findall("x:si", XML_NS)
            ]
            sheet_root = ElementTree.fromstring(
                workbook.read("xl/worksheets/sheet1.xml")
            )
    except Exception as exc:  # noqa: BLE001 - ZIP/XML 오류 통합
        raise PopulationAPIError(f"행정동 코드 파일 해석 실패: {exc}") from exc

    mapping: dict[str, dict[str, str]] = {}
    rows = sheet_root.findall(".//x:sheetData/x:row", XML_NS)
    for row in rows[2:]:
        values: dict[str, str] = {}
        for cell in row.findall("x:c", XML_NS):
            column = "".join(ch for ch in (cell.get("r") or "") if ch.isalpha())
            values[column] = _xlsx_cell_value(cell, shared_strings)
        code = values.get("B", "")
        if code:
            mapping[code] = {
                "district": values.get("D", ""),
                "dong": values.get("E", ""),
            }
    return mapping


def fetch_admin_dong_mapping(
    *,
    timeout: float = 30.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, dict[str, str]]:
    """서울 생활인구 페이지가 제공하는 공식 행정동 매핑 파일을 받는다."""
    body = urllib.parse.urlencode(
        {"infId": "DOWNLOAD", "infSeq": "4", "seq": "7"}
    ).encode("ascii")
    request = urllib.request.Request(CODE_DOWNLOAD_URL, data=body, method="POST")
    try:
        with opener(request, timeout=timeout) as response:
            return parse_admin_dong_mapping(response.read())
    except PopulationAPIError:
        raise
    except Exception as exc:  # noqa: BLE001 - 네트워크 오류 통합
        raise PopulationAPIError(f"행정동 코드 파일 요청 실패: {exc}") from exc


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _sum_fields(row: dict[str, Any], fragments: tuple[str, ...]) -> float:
    return sum(
        _number(value)
        for key, value in row.items()
        if key.startswith(("MALE_", "FEMALE_"))
        and any(fragment in key for fragment in fragments)
    )


def build_population_dashboard_data(
    rows: list[dict[str, Any]],
    mapping: dict[str, dict[str, str]] | None = None,
    *,
    reference_date: str = "",
    reference_hour: str = "",
    collected_at: str | None = None,
) -> dict[str, Any]:
    """행정동 원본 행을 시민용 대시보드 집계로 변환한다."""
    names = mapping or {}
    enriched: list[dict[str, Any]] = []
    district_totals: dict[str, float] = {}
    total_population = 0.0
    male_population = 0.0
    female_population = 0.0
    age_totals = {"0~19세": 0.0, "20~39세": 0.0, "40~64세": 0.0, "65세+": 0.0}

    for row in rows:
        code = str(row.get("ADSTRD_CODE_SE") or "")
        name = names.get(code, {})
        population = _number(row.get("TOT_LVPOP_CO"))
        male = sum(
            _number(value) for key, value in row.items() if key.startswith("MALE_")
        )
        female = sum(
            _number(value)
            for key, value in row.items()
            if key.startswith("FEMALE_")
        )
        district = name.get("district") or code[:5]
        dong = name.get("dong") or code
        total_population += population
        male_population += male
        female_population += female
        district_totals[district] = district_totals.get(district, 0.0) + population
        age_totals["0~19세"] += _sum_fields(row, ("F0T9_", "F10T14_", "F15T19_"))
        age_totals["20~39세"] += _sum_fields(
            row, ("F20T24_", "F25T29_", "F30T34_", "F35T39_")
        )
        age_totals["40~64세"] += _sum_fields(
            row, ("F40T44_", "F45T49_", "F50T54_", "F55T59_", "F60T64_")
        )
        age_totals["65세+"] += _sum_fields(row, ("F65T69_", "F70T74_"))
        enriched.append(
            {
                "code": code,
                "district": district,
                "dong": dong,
                "population": round(population),
            }
        )

    top_dongs = sorted(enriched, key=lambda item: item["population"], reverse=True)[:10]
    for item in top_dongs:
        item["share"] = (
            round(item["population"] / total_population * 100, 2)
            if total_population
            else 0.0
        )
    by_district = [
        {"district": district, "population": round(population)}
        for district, population in sorted(
            district_totals.items(), key=lambda item: item[1], reverse=True
        )
    ]
    gender_total = male_population + female_population
    age_total = sum(age_totals.values())
    now_label = collected_at or datetime.now(ZoneInfo("Asia/Seoul")).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    return {
        "collected_at": now_label,
        "reference_date": reference_date,
        "reference_hour": reference_hour,
        "dong_count": len(enriched),
        "total_population": round(total_population),
        "male_rate": round(male_population / gender_total * 100, 1)
        if gender_total
        else None,
        "female_rate": round(female_population / gender_total * 100, 1)
        if gender_total
        else None,
        "top_dongs": top_dongs,
        "by_district": by_district,
        "age_labels": list(age_totals),
        "age_rates": [
            round(value / age_total * 100, 1) if age_total else 0.0
            for value in age_totals.values()
        ],
        "source": {
            "portal": "서울 열린데이터광장",
            "dataset": "행정동 단위 서울 생활인구(내국인)",
            "service": SERVICE,
            "url": DATASET_URL,
            "coverage": "서울 전역 행정동·시간대별 내국인 생활인구",
            "freshness_note": (
                "생활인구는 실시간 값이 아니며 서울시 제공 일정에 따라 "
                "통상 D-4 기준으로 갱신됩니다."
            ),
        },
    }
