"""서울 지하철 실시간 도착정보 수집·집계 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seoul_citydata.subway import (  # noqa: E402
    SOURCE_URL,
    SubwayAPIError,
    build_arrival_url,
    build_subway_dashboard_data,
    fetch_station_arrivals,
    get_subway_api_key,
)


def arrival(
    station: str,
    line_id: str,
    direction: str,
    message: str,
    seconds: str,
    code: str,
    train_no: str,
    received: str,
) -> dict:
    return {
        "subwayId": line_id,
        "updnLine": direction,
        "trainLineNm": f"성수행 - {station}방면",
        "statnNm": station,
        "btrainSttus": "일반",
        "barvlDt": seconds,
        "btrainNo": train_no,
        "recptnDt": received,
        "arvlMsg2": message,
        "arvlMsg3": "전역",
        "arvlCd": code,
    }


@pytest.fixture
def responses():
    return {
        "강남": [
            arrival("강남", "1002", "외선", "전역 출발", "80", "3", "2001", "2026-07-19 09:00:01"),
            arrival("강남", "1077", "하행", "4분 후", "240", "99", "D101", "2026-07-19 09:00:03"),
        ],
        "잠실": [
            arrival("잠실", "1002", "내선", "2분 후", "120", "99", "2002", "2026-07-19 09:00:05"),
        ],
    }


class TestHelpers:
    def test_key_precedence(self, monkeypatch):
        monkeypatch.setenv("SEOUL_SUBWAY_API_KEY", "ENV")
        assert get_subway_api_key("EXPLICIT") == "EXPLICIT"
        assert get_subway_api_key() == "ENV"

    def test_url_encodes_station(self):
        url = build_arrival_url("고속터미널", api_key="K", limit=8)
        assert "/K/json/realtimeStationArrival/0/8/" in url
        assert "고속터미널" not in url
        assert "%" in url

    def test_fetch_rejects_api_error(self, monkeypatch):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"errorMessage": {"code": "ERROR-301", "message": "KEY ERROR"}}).encode()

        monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
        with pytest.raises(SubwayAPIError, match="ERROR-301"):
            fetch_station_arrivals("강남", api_key="BAD")


class TestDashboardData:
    def test_summary_and_freshness(self, responses):
        data = build_subway_dashboard_data(responses)
        assert data["station_count"] == 2
        assert data["arrival_count"] == 3
        assert data["board_count"] == 3
        assert data["line_count"] == 2
        assert data["near_count"] == 2
        assert data["updated_at"] == "2026-07-19 09:00:05"

    def test_line_rollup_deduplicates_trains(self, responses):
        data = build_subway_dashboard_data(responses)
        line2 = next(item for item in data["lines"] if item["line_id"] == "1002")
        assert line2["train_count"] == 2
        assert line2["arrival_records"] == 2
        assert line2["nearest_wait_seconds"] == 80

    def test_source_metadata(self, responses):
        source = build_subway_dashboard_data(responses)["source"]
        assert source["service"] == "realtimeStationArrival"
        assert source["url"] == SOURCE_URL
        assert source["portal"] == "서울 열린데이터광장"
