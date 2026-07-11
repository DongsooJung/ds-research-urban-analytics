"""seoul_citydata.viz 단위 테스트 — HTML 대시보드 생성."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seoul_citydata.viz import build_dashboard_data, generate_dashboard


@pytest.fixture
def df():
    rows = [
        dict(area="A", category="관광특구", congest_level="붐빔", congest_score=4,
             ppltn_min=90000, ppltn_max=100000, ppltn_mid=95000, male_rate=55, female_rate=45,
             temp=30, humidity=60, pm10=80, pm25=50, uv_index=5, road_spd=10,
             rate_0=1, rate_10=5, rate_20=30, rate_30=25, rate_40=20, rate_50=12, rate_60=5, rate_70=2),
        dict(area="B", category="공원", congest_level="여유", congest_score=1,
             ppltn_min=10000, ppltn_max=12000, ppltn_mid=11000, male_rate=48, female_rate=52,
             temp=22, humidity=70, pm10=20, pm25=10, uv_index=2, road_spd=40,
             rate_0=2, rate_10=8, rate_20=18, rate_30=22, rate_40=22, rate_50=16, rate_60=8, rate_70=4),
        dict(area="C", category="공원", congest_level="여유", congest_score=1,
             ppltn_min=8000, ppltn_max=9000, ppltn_mid=8500, male_rate=47, female_rate=53,
             temp=21, humidity=72, pm10=15, pm25=8, uv_index=1, road_spd=45,
             rate_0=3, rate_10=10, rate_20=16, rate_30=20, rate_40=22, rate_50=17, rate_60=8, rate_70=4),
    ]
    return pd.DataFrame(rows)


class TestBuildData:
    def test_keys(self, df):
        d = build_dashboard_data(df)
        assert set(d.keys()) >= {"stats", "ranking", "categories", "age", "age_labels", "corr"}

    def test_ranking_sorted(self, df):
        d = build_dashboard_data(df)
        ppltns = [r["ppltn"] for r in d["ranking"]]
        assert ppltns == sorted(ppltns, reverse=True)

    def test_age_length(self, df):
        d = build_dashboard_data(df)
        assert len(d["age"]) == 8
        assert len(d["age_labels"]) == 8

    def test_json_serializable(self, df):
        d = build_dashboard_data(df)
        # NaN → None 처리로 JSON 직렬화 가능해야 함
        s = json.dumps(d, ensure_ascii=False)
        assert "NaN" not in s


class TestGenerate:
    def test_creates_html(self, df, tmp_path):
        out = tmp_path / "dash.html"
        generate_dashboard(df, str(out))
        assert out.exists()
        html = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html
        assert "Chart" in html
        assert "__DATA__" not in html  # placeholder 치환됨
        assert "__TITLE__" not in html

    def test_embeds_data(self, df, tmp_path):
        out = tmp_path / "dash.html"
        generate_dashboard(df, str(out), title="테스트 대시보드")
        html = out.read_text(encoding="utf-8")
        assert "테스트 대시보드" in html
        assert "const D =" in html


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
