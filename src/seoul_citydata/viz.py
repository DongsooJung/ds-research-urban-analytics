"""
서울 실시간 도시데이터 시각화

스냅샷 DataFrame → 자기완결형 HTML 대시보드 생성.
혼잡 순위·카테고리 요약·연령 분포·날씨/대기질·혼잡-환경 상관을 한 페이지에.

Chart.js(CDN)를 사용하며, 데이터는 placeholder 치환 방식으로 주입한다
(f-string 중괄호 escape 문제 회피).
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .analysis import (
    congestion_ranking, category_summary, demographic_profile,
    weather_congestion_corr, summary_stats,
)

AGE_LABELS = ["0대", "10대", "20대", "30대", "40대", "50대", "60대", "70+"]


def build_dashboard_data(df: pd.DataFrame) -> dict[str, Any]:
    """DataFrame → 대시보드용 JSON 직렬화 가능 dict."""
    stats = summary_stats(df)

    ranking = congestion_ranking(df, top=15)
    rank_data = [
        {"area": r["area"], "ppltn": r.get("ppltn_mid"),
         "level": r.get("congest_level"), "score": r.get("congest_score")}
        for _, r in ranking.iterrows()
    ]

    try:
        cat = category_summary(df).reset_index()
        cat_data = [
            {"category": r["category"], "ppltn": r.get("ppltn_mid"),
             "congest": r.get("congest_score"), "count": int(r.get("area_count", 0))}
            for _, r in cat.iterrows()
        ]
    except Exception:
        cat_data = []

    prof = demographic_profile(df)
    age_data = [float(prof.get(f"rate_{d}", 0.0)) for d in (0, 10, 20, 30, 40, 50, 60, 70)]

    corr = weather_congestion_corr(df)
    corr_data = [
        {"metric": k, "corr": (None if pd.isna(v) else float(v))}
        for k, v in corr.items()
    ]

    return {
        "stats": stats,
        "ranking": rank_data,
        "categories": cat_data,
        "age": age_data,
        "age_labels": AGE_LABELS,
        "corr": corr_data,
    }


def generate_dashboard(df: pd.DataFrame, out_path: str = "dashboard.html",
                       title: str = "서울 실시간 도시데이터") -> str:
    """스냅샷 DataFrame → HTML 대시보드 파일 생성. 경로 반환."""
    data = build_dashboard_data(df)
    html = (
        _TEMPLATE
        .replace("__TITLE__", title)
        .replace("__DATA__", json.dumps(data, ensure_ascii=False))
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<meta name="description" content="서울 실시간 도시데이터 스냅샷 대시보드 — 혼잡·인구·날씨·상관 분석">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'Malgun Gothic','Apple SD Gothic Neo','Segoe UI',sans-serif;
    background:#0a0e27;color:#e0e6f0;padding:24px;line-height:1.5}
  h1{font-size:24px;color:#8ab4f8;margin-bottom:4px}
  .sub{color:#8892b0;font-size:13px;margin-bottom:20px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:22px}
  .kpi{background:#151933;border:1px solid #2a3354;border-radius:12px;padding:18px}
  .kpi .label{font-size:12px;color:#8892b0;margin-bottom:6px}
  .kpi .value{font-size:26px;font-weight:700;color:#8ab4f8}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
  .panel{background:#151933;border:1px solid #2a3354;border-radius:12px;padding:20px}
  .panel h2{font-size:15px;color:#e0e6f0;margin-bottom:14px}
  .panel.full{grid-column:1/-1}
  .chart-box{position:relative;height:300px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{text-align:left;color:#8892b0;padding:8px;border-bottom:1px solid #2a3354}
  td{padding:8px;border-bottom:1px solid #1e2547}
  .corr-pos{color:#4ecca3}.corr-neg{color:#e94560}
  @media(max-width:768px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
  <h1>🏙️ __TITLE__</h1>
  <div class="sub" id="sub"></div>
  <div class="kpis" id="kpis"></div>
  <div class="grid">
    <div class="panel"><h2>📊 혼잡 순위 (인구 추정 중앙값)</h2><div class="chart-box"><canvas id="rankChart"></canvas></div></div>
    <div class="panel"><h2>🏷️ 카테고리별 평균 인구</h2><div class="chart-box"><canvas id="catChart"></canvas></div></div>
  </div>
  <div class="grid">
    <div class="panel"><h2>👥 연령대 분포 (인구 가중)</h2><div class="chart-box"><canvas id="ageChart"></canvas></div></div>
    <div class="panel"><h2>🔗 혼잡–환경 상관</h2><table id="corrTable"><thead><tr><th>지표</th><th>상관계수</th></tr></thead><tbody></tbody></table></div>
  </div>

<script>
const D = __DATA__;

// KPI
const s = D.stats;
document.getElementById('sub').textContent =
  `지역 ${s.n_areas}곳 · 총 인구(추정) ${Math.round(s.total_ppltn_min).toLocaleString()}~${Math.round(s.total_ppltn_max).toLocaleString()}명`;
const kpis = [
  ['지역 수', s.n_areas],
  ['평균 혼잡점수', (s.mean_congest_score||0).toFixed(2)+' / 4'],
  ['붐빔 지역', s.n_crowded+'곳'],
  ['평균 PM10', s.mean_pm10==null?'—':s.mean_pm10.toFixed(0)],
];
document.getElementById('kpis').innerHTML = kpis.map(k=>
  `<div class="kpi"><div class="label">${k[0]}</div><div class="value">${k[1]}</div></div>`).join('');

const gridColor='#2a3354', tick='#8892b0';
const axis=(extra={})=>Object.assign({ticks:{color:tick},grid:{color:gridColor}},extra);

// 혼잡 순위 (수평 막대)
new Chart(document.getElementById('rankChart'),{
  type:'bar',
  data:{labels:D.ranking.map(r=>r.area),
    datasets:[{label:'인구(중앙값)',data:D.ranking.map(r=>r.ppltn),
      backgroundColor:'#4a6fdc',borderRadius:4}]},
  options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{x:axis(),y:{ticks:{color:tick,font:{size:10}},grid:{display:false}}}}
});

// 카테고리별 평균 인구
new Chart(document.getElementById('catChart'),{
  type:'bar',
  data:{labels:D.categories.map(c=>c.category),
    datasets:[{label:'평균 인구',data:D.categories.map(c=>c.ppltn),
      backgroundColor:'#8b5cf6',borderRadius:4}]},
  options:{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{x:{ticks:{color:tick,font:{size:10}},grid:{display:false}},y:axis()}}
});

// 연령대 분포
new Chart(document.getElementById('ageChart'),{
  type:'bar',
  data:{labels:D.age_labels,
    datasets:[{label:'비율(%)',data:D.age,
      backgroundColor:'#4ecca3',borderRadius:4}]},
  options:{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{x:{ticks:{color:tick},grid:{display:false}},y:axis()}}
});

// 상관 테이블
const NAMES={temp:'기온',humidity:'습도',pm10:'PM10',pm25:'PM2.5',uv_index:'자외선',road_spd:'도로속도'};
document.querySelector('#corrTable tbody').innerHTML = D.corr.map(c=>{
  const v=c.corr;
  const cls=v==null?'':(v>=0?'corr-pos':'corr-neg');
  const txt=v==null?'—':v.toFixed(3);
  return `<tr><td>${NAMES[c.metric]||c.metric}</td><td class="${cls}">${txt}</td></tr>`;
}).join('');
</script>
</body>
</html>"""
