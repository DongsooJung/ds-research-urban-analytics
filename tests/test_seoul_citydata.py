"""seoul_citydata 단위 테스트 — fixture 기반(네트워크 불필요)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seoul_citydata import (
    to_record, to_dataframe, congestion_ranking, busiest_areas,
    category_summary, demographic_profile, gender_balance,
    weather_congestion_corr, summary_stats, congestion_score,
)
from seoul_citydata.parser import (
    parse_population, parse_weather, parse_road, parse_commercial, parse_forecast,
)
from seoul_citydata.api import build_url, get_api_key

FIXTURE = Path(__file__).parent / "fixtures" / "sample_citydata.json"


@pytest.fixture(scope="module")
def raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def citydata(raw):
    return raw["CITYDATA"]


# ----------------------------------------------------------------------
# 상수/헬퍼
# ----------------------------------------------------------------------
class TestConstants:
    def test_congestion_score_order(self):
        assert congestion_score("여유") == 1
        assert congestion_score("붐빔") == 4
        assert congestion_score("여유") < congestion_score("붐빔")

    def test_unknown_level_zero(self):
        assert congestion_score("알수없음") == 0
        assert congestion_score(None) == 0


# ----------------------------------------------------------------------
# API URL / 키
# ----------------------------------------------------------------------
class TestAPIHelpers:
    def test_default_key_is_sample(self, monkeypatch):
        monkeypatch.delenv("SEOUL_API_KEY", raising=False)
        assert get_api_key() == "sample"

    def test_explicit_key_wins(self):
        assert get_api_key("MYKEY") == "MYKEY"

    def test_env_key(self, monkeypatch):
        monkeypatch.setenv("SEOUL_API_KEY", "ENVKEY")
        assert get_api_key() == "ENVKEY"

    def test_url_encodes_korean(self):
        url = build_url("광화문·덕수궁", api_key="K")
        assert "citydata" in url
        assert "%" in url  # 한글 인코딩됨
        assert "광화문" not in url


# ----------------------------------------------------------------------
# 파서
# ----------------------------------------------------------------------
class TestParsePopulation:
    def test_fields(self, citydata):
        p = parse_population(citydata)
        assert p["congest_level"] == "여유"
        assert p["congest_score"] == 1
        assert p["ppltn_min"] == 30000.0
        assert p["ppltn_max"] == 32000.0
        assert 0 <= p["male_rate"] <= 100

    def test_age_rates_sum_near_100(self, citydata):
        p = parse_population(citydata)
        age_sum = sum(p[f"rate_{d}"] for d in (0, 10, 20, 30, 40, 50, 60, 70))
        assert age_sum == pytest.approx(100.0, abs=1.0)

    def test_empty(self):
        assert parse_population({}) == {}


class TestParseWeather:
    def test_fields(self, citydata):
        w = parse_weather(citydata)
        assert w["temp"] is not None
        assert w["pm10"] is not None
        assert w["pm25"] is not None
        assert w["air_idx"] is not None


class TestParseRoadCommercial:
    def test_road(self, citydata):
        r = parse_road(citydata)
        assert r["road_spd"] is not None
        assert r["road_idx"] in ("원활", "서행", "정체")

    def test_commercial(self, citydata):
        c = parse_commercial(citydata)
        assert c["cmrcl_level"] is not None
        assert c["payment_cnt"] is not None


class TestParseForecast:
    def test_12_steps(self, citydata):
        fc = parse_forecast(citydata)
        assert len(fc) == 12
        for f in fc:
            assert "fcst_time" in f
            assert 0 <= f["fcst_congest_score"] <= 4


class TestToRecord:
    def test_record_from_full_response(self, raw):
        rec = to_record(raw)
        assert rec["area"] == "광화문·덕수궁"
        assert rec["category"] == "고궁·문화유산"
        assert rec["congest_score"] == 1
        assert rec["ppltn_mid"] == 31000.0

    def test_record_from_citydata_dict(self, citydata):
        rec = to_record(citydata)
        assert rec["area"] == "광화문·덕수궁"


# ----------------------------------------------------------------------
# 분석 (합성 다지역 DataFrame)
# ----------------------------------------------------------------------
@pytest.fixture
def multi_df():
    """혼잡·날씨가 다른 5개 지역 합성 스냅샷."""
    rows = [
        dict(area="A", category="관광특구", congest_level="붐빔", congest_score=4,
             ppltn_min=90000, ppltn_max=100000, ppltn_mid=95000,
             male_rate=55, female_rate=45, temp=30, humidity=60, pm10=80, pm25=50,
             uv_index=5, road_spd=10,
             rate_0=1, rate_10=5, rate_20=30, rate_30=25, rate_40=20, rate_50=12, rate_60=5, rate_70=2),
        dict(area="B", category="공원", congest_level="여유", congest_score=1,
             ppltn_min=10000, ppltn_max=12000, ppltn_mid=11000,
             male_rate=48, female_rate=52, temp=22, humidity=70, pm10=20, pm25=10,
             uv_index=2, road_spd=40,
             rate_0=2, rate_10=8, rate_20=18, rate_30=22, rate_40=22, rate_50=16, rate_60=8, rate_70=4),
        dict(area="C", category="관광특구", congest_level="약간 붐빔", congest_score=3,
             ppltn_min=50000, ppltn_max=55000, ppltn_mid=52500,
             male_rate=50, female_rate=50, temp=28, humidity=65, pm10=60, pm25=35,
             uv_index=4, road_spd=18,
             rate_0=1, rate_10=6, rate_20=28, rate_30=24, rate_40=21, rate_50=13, rate_60=5, rate_70=2),
        dict(area="D", category="인구밀집지역", congest_level="보통", congest_score=2,
             ppltn_min=30000, ppltn_max=33000, ppltn_mid=31500,
             male_rate=51, female_rate=49, temp=25, humidity=68, pm10=40, pm25=22,
             uv_index=3, road_spd=28,
             rate_0=1, rate_10=7, rate_20=25, rate_30=23, rate_40=21, rate_50=15, rate_60=6, rate_70=2),
        dict(area="E", category="공원", congest_level="여유", congest_score=1,
             ppltn_min=8000, ppltn_max=9000, ppltn_mid=8500,
             male_rate=47, female_rate=53, temp=21, humidity=72, pm10=15, pm25=8,
             uv_index=1, road_spd=45,
             rate_0=3, rate_10=10, rate_20=16, rate_30=20, rate_40=22, rate_50=17, rate_60=8, rate_70=4),
    ]
    return pd.DataFrame(rows)


class TestAnalysis:
    def test_congestion_ranking_order(self, multi_df):
        r = congestion_ranking(multi_df)
        assert r.iloc[0]["area"] == "A"   # 최다 인구
        assert r.iloc[-1]["area"] == "E"  # 최소 인구
        assert list(r.index) == [1, 2, 3, 4, 5]

    def test_busiest_areas(self, multi_df):
        assert busiest_areas(multi_df, 2) == ["A", "C"]

    def test_category_summary(self, multi_df):
        cs = category_summary(multi_df)
        assert "관광특구" in cs.index
        assert cs.loc["관광특구", "area_count"] == 2
        # 관광특구가 공원보다 평균 인구 많음
        assert cs.loc["관광특구", "ppltn_mid"] > cs.loc["공원", "ppltn_mid"]

    def test_demographic_profile_sums_100(self, multi_df):
        prof = demographic_profile(multi_df)
        assert prof.sum() == pytest.approx(100.0, abs=1.0)

    def test_gender_balance(self, multi_df):
        gb = gender_balance(multi_df)
        assert gb.iloc[0]["area"] == "A"  # 남성 우세 최고(55-45)
        assert gb.iloc[0]["male_lead"] == pytest.approx(10.0)

    def test_weather_congestion_corr(self, multi_df):
        corr = weather_congestion_corr(multi_df)
        # 혼잡할수록 도로속도 낮음 → 음의 상관
        assert corr["road_spd"] < 0
        # 혼잡할수록 미세먼지 높게 설계됨 → 양의 상관
        assert corr["pm10"] > 0

    def test_summary_stats(self, multi_df):
        s = summary_stats(multi_df)
        assert s["n_areas"] == 5
        assert s["total_ppltn_min"] == 188000.0
        assert s["n_crowded"] == 2   # A(4), C(3)
        assert set(s["crowded_areas"]) == {"A", "C"}


class TestToDataFrame:
    def test_from_fixture(self, raw):
        df = to_dataframe({"광화문·덕수궁": raw})
        assert len(df) == 1
        assert df.iloc[0]["area"] == "광화문·덕수궁"
        assert "congest_score" in df.columns


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
