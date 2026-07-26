"""서울 행정동 생활인구 수집·집계 단위 테스트."""
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seoul_citydata.population import (  # noqa: E402
    build_population_dashboard_data,
    fetch_population_rows,
    parse_admin_dong_mapping,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def sample_row(code="11110530", population="1000"):
    return {
        "STDR_DE_ID": "20260721",
        "TMZON_PD_SE": "09",
        "ADSTRD_CODE_SE": code,
        "TOT_LVPOP_CO": population,
        "MALE_F0T9_LVPOP_CO": "50",
        "MALE_F20T24_LVPOP_CO": "100",
        "MALE_F40T44_LVPOP_CO": "150",
        "MALE_F65T69_LVPOP_CO": "50",
        "FEMALE_F0T9_LVPOP_CO": "50",
        "FEMALE_F20T24_LVPOP_CO": "100",
        "FEMALE_F40T44_LVPOP_CO": "150",
        "FEMALE_F65T69_LVPOP_CO": "50",
    }


def test_fetch_population_rows_uses_latest_date_and_hour():
    calls = []

    def opener(url, timeout):
        calls.append((url, timeout))
        if url.endswith("/1/1"):
            root = {"list_total_count": 1, "RESULT": {"CODE": "INFO-000"}, "row": [sample_row()]}
        else:
            root = {
                "list_total_count": 2,
                "RESULT": {"CODE": "INFO-000"},
                "row": [sample_row(), sample_row("11110540", "2000")],
            }
        return FakeResponse({"SPOP_LOCAL_RESD_DONG": root})

    rows, meta = fetch_population_rows(
        "KEY", reference_hour="09", opener=opener
    )
    assert len(rows) == 2
    assert meta == {"reference_date": "20260721", "reference_hour": "09"}
    assert calls[1][0].endswith("/20260721/09")


def test_build_population_dashboard_data():
    rows = [sample_row(), sample_row("11110540", "2000")]
    mapping = {
        "11110530": {"district": "종로구", "dong": "사직동"},
        "11110540": {"district": "종로구", "dong": "삼청동"},
    }
    data = build_population_dashboard_data(
        rows,
        mapping,
        reference_date="20260721",
        reference_hour="09",
        collected_at="2026-07-26 09:00:00",
    )
    assert data["dong_count"] == 2
    assert data["total_population"] == 3000
    assert data["top_dongs"][0]["dong"] == "삼청동"
    assert data["by_district"] == [{"district": "종로구", "population": 3000}]
    assert sum(data["age_rates"]) == pytest.approx(100.0, abs=0.2)
    assert data["source"]["service"] == "SPOP_LOCAL_RESD_DONG"


def test_parse_admin_dong_mapping_from_official_xlsx_shape():
    shared = """<?xml version="1.0" encoding="UTF-8"?>
    <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <si><t>행자부행정동코드</t></si><si><t>시군구명</t></si><si><t>행정동명</t></si>
      <si><t>11110530</t></si><si><t>종로구</t></si><si><t>사직동</t></si>
    </sst>"""
    sheet = """<?xml version="1.0" encoding="UTF-8"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData>
        <row r="1"><c r="B1" t="s"><v>0</v></c></row>
        <row r="2"><c r="B2" t="s"><v>0</v></c></row>
        <row r="3"><c r="B3" t="s"><v>3</v></c><c r="D3" t="s"><v>4</v></c><c r="E3" t="s"><v>5</v></c></row>
      </sheetData>
    </worksheet>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as workbook:
        workbook.writestr("xl/sharedStrings.xml", shared)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet)
    mapping = parse_admin_dong_mapping(buffer.getvalue())
    assert mapping["11110530"] == {"district": "종로구", "dong": "사직동"}
