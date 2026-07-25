"""따릉이·주차장·사고통제 수집 및 집계 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seoul_citydata.mobility import (  # noqa: E402
    BIKE_SOURCE_URL,
    MobilityAPIError,
    build_mobility_dashboard_data,
    build_page_url,
    fetch_paged_rows,
)


@pytest.fixture
def bike_rows():
    return [
        {
            "stationId": "ST-1", "stationName": "101. 시민청 앞",
            "parkingBikeTotCnt": "10", "rackTotCnt": "20", "shared": "50",
            "stationLatitude": "37.56", "stationLongitude": "126.97",
        },
        {
            "stationId": "ST-2", "stationName": "102. 서울광장",
            "parkingBikeTotCnt": "2", "rackTotCnt": "10", "shared": "20",
            "stationLatitude": "37.57", "stationLongitude": "126.98",
        },
        {
            "stationId": "ST-3", "stationName": "103. 덕수궁",
            "parkingBikeTotCnt": "0", "rackTotCnt": "8", "shared": "0",
            "stationLatitude": "37.56", "stationLongitude": "126.97",
        },
    ]


@pytest.fixture
def parking_rows():
    return [
        {
            "PKLT_CD": "P1", "PKLT_NM": "광장 주차장", "ADDR": "중구 태평로 1",
            "PRK_STTS_YN": "1", "TPKCT": 20, "NOW_PRK_VHCL_CNT": 14,
            "NOW_PRK_VHCL_UPDT_TM": "2026-07-25 10:01:00",
            "PAY_YN": "Y", "PAY_YN_NM": "유료", "BSC_PRK_CRG": 500, "BSC_PRK_HR": 5,
        },
        {
            "PKLT_CD": "P2", "PKLT_NM": "공원 주차장", "ADDR": "종로구 세종로 1",
            "PRK_STTS_YN": "1", "TPKCT": 10, "NOW_PRK_VHCL_CNT": 12,
            "NOW_PRK_VHCL_UPDT_TM": "2026-07-25 10:02:00",
            "PAY_YN": "N", "PAY_YN_NM": "무료",
        },
        {
            "PKLT_CD": "P3", "PKLT_NM": "미연계 주차장", "ADDR": "중구 을지로 1",
            "PRK_STTS_YN": "0", "TPKCT": 30, "NOW_PRK_VHCL_CNT": 1,
        },
    ]


@pytest.fixture
def city_responses():
    incident = {
        "ACDNT_OCCR_DT": "2026-07-25 09:00",
        "EXP_CLR_DT": "2026-07-25 12:00",
        "ACDNT_TYPE": "공사",
        "ACDNT_DTYPE": "차로통제",
        "ACDNT_INFO": "세종대로 1개 차로 통제",
        "ACDNT_TIME": "2026-07-25 10:00",
    }
    return [
        {"CITYDATA": {"AREA_NM": "광화문·덕수궁", "ACDNT_CNTRL_STTS": [incident]}},
        {"CITYDATA": {"AREA_NM": "서울역", "ACDNT_CNTRL_STTS": [incident.copy()]}},
    ]


class TestFetch:
    def test_url_and_key_precedence(self, monkeypatch):
        monkeypatch.setenv("SEOUL_API_KEY", "ENV")
        assert "/ENV/json/bikeList/1/5/" in build_page_url("bikeList", 1, 5)
        assert "/EXPLICIT/json/" in build_page_url("bikeList", 1, 5, "EXPLICIT")

    def test_sample_key_limits_page_to_five(self, monkeypatch):
        called_urls = []

        def fake_request(url, *_args):
            called_urls.append(url)
            return {
                "rentBikeStatus": {
                    "list_total_count": 2500,
                    "RESULT": {"CODE": "INFO-000"},
                    "row": [{"stationId": f"ST-{i}"} for i in range(5)],
                }
            }

        monkeypatch.setattr("seoul_citydata.mobility._request_json", fake_request)
        rows = fetch_paged_rows("bikeList", "rentBikeStatus", api_key="sample")
        assert len(rows) == 5
        assert called_urls == [build_page_url("bikeList", 1, 5, "sample")]

    def test_missing_wrapper_is_error(self, monkeypatch):
        monkeypatch.setattr(
            "seoul_citydata.mobility._request_json",
            lambda *_args: {"RESULT": {"MESSAGE": "서비스 없음"}},
        )
        with pytest.raises(MobilityAPIError, match="서비스 없음"):
            fetch_paged_rows("bad", "missing", api_key="K")

    def test_real_key_paginates_until_total(self, monkeypatch):
        called_urls = []

        def fake_request(url, *_args):
            called_urls.append(url)
            start = int(url.rstrip("/").split("/")[-2])
            rows = [{"stationId": f"ST-{start}"}]
            if start == 1:
                rows.append({"stationId": "ST-2"})
            return {
                "rentBikeStatus": {
                    "list_total_count": 3,
                    "RESULT": {"CODE": "INFO-000"},
                    "row": rows,
                }
            }

        monkeypatch.setattr("seoul_citydata.mobility._request_json", fake_request)
        rows = fetch_paged_rows(
            "bikeList", "rentBikeStatus", api_key="REAL", page_size=2
        )
        assert [row["stationId"] for row in rows] == ["ST-1", "ST-2", "ST-3"]
        assert called_urls == [
            build_page_url("bikeList", 1, 2, "REAL"),
            build_page_url("bikeList", 3, 4, "REAL"),
        ]


class TestDashboardData:
    def test_citizen_summary(self, bike_rows, parking_rows, city_responses):
        data = build_mobility_dashboard_data(
            bike_rows,
            parking_rows,
            city_responses,
            collected_at="2026-07-25 10:03:00",
        )
        assert data["collected_at"] == "2026-07-25 10:03:00"
        assert data["bike"]["station_count"] == 3
        assert data["bike"]["available_bikes"] == 12
        assert data["bike"]["empty_station_count"] == 1
        assert data["bike"]["low_station_count"] == 2
        assert data["bike"]["top_available"][0]["name"] == "시민청 앞"

        assert data["parking"]["live_lot_count"] == 2
        assert data["parking"]["available_spaces"] == 6
        assert data["parking"]["full_lot_count"] == 1
        assert data["parking"]["updated_at"] == "2026-07-25 10:02:00"
        assert data["parking"]["top_available"][0]["fee"] == "500원/5분"

        assert data["incidents"]["incident_count"] == 1
        assert data["incidents"]["items"][0]["areas"] == ["광화문·덕수궁", "서울역"]

    def test_source_metadata(self, bike_rows, parking_rows):
        sources = build_mobility_dashboard_data(bike_rows, parking_rows)["sources"]
        assert sources["bike"]["url"] == BIKE_SOURCE_URL
        assert sources["bike"]["service"] == "bikeList"
        assert sources["parking"]["service"] == "GetParkingInfo"
        assert "5분" in sources["parking"]["freshness_note"]
