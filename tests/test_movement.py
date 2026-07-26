"""대도시권 생활인구 외부 유입 집계 단위 테스트."""
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seoul_citydata.movement import (  # noqa: E402
    aggregate_movement_zip,
    discover_latest_reference_date,
    fetch_movement_dashboard_data,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def movement_zip():
    rows = [
        ["일자", "시간", "도착지", "순위", "거주지", "생활인구", "생성일"],
        ["20260721", "08", "11110530", "1", "41131", "100", "25-07-2026"],
        ["20260721", "08", "11110530", "2", "11110", "200", "25-07-2026"],
        ["20260721", "08", "11110540", "3", "28110", "50", "25-07-2026"],
        ["20260721", "18", "11110530", "1", "41131", "150", "25-07-2026"],
        ["20260721", "18", "11110540", "2", "11110", "250", "25-07-2026"],
    ]
    text = "\n".join(",".join(row) for row in rows).encode("cp949")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("250_ORGN_CT_20260721.csv", text)
    return buffer.getvalue()


def mappings():
    admin = {
        "11110530": {"district": "종로구", "dong": "사직동"},
        "11110540": {"district": "종로구", "dong": "삼청동"},
    }
    origins = {
        "11110": {"province": "서울", "name": "종로구"},
        "41131": {"province": "경기", "name": "성남시 수정구"},
        "28110": {"province": "인천", "name": "중구"},
    }
    return admin, origins


def test_aggregate_movement_zip():
    admin, origins = mappings()
    data = aggregate_movement_zip(movement_zip(), admin, origins)
    morning = data["periods"]["08"]
    evening = data["periods"]["18"]
    assert data["reference_date"] == "20260721"
    assert morning["total_population"] == 350
    assert morning["external_population"] == 150
    assert morning["external_rate"] == 42.9
    assert morning["top_origins"][0]["origin"] == "경기 성남시 수정구"
    assert morning["top_destinations"][0]["dong"] == "사직동"
    assert evening["external_population"] == 150


def test_discover_latest_reference_date():
    html = (
        "250_ORGN_CT_20260720.zip "
        "250_ORGN_CT_20260721.zip"
    ).encode()
    assert discover_latest_reference_date(
        opener=lambda *_args, **_kwargs: FakeResponse(html)
    ) == "20260721"


def test_existing_current_date_is_reused():
    admin, origins = mappings()
    existing = {
        "reference_date": "20260721",
        "periods": {"08": {"row_count": 1}, "18": {"row_count": 1}},
    }
    html = b"250_ORGN_CT_20260721.zip"
    result, reused = fetch_movement_dashboard_data(
        admin,
        origins,
        existing=existing,
        opener=lambda *_args, **_kwargs: FakeResponse(html),
    )
    assert reused is True
    assert result is existing
