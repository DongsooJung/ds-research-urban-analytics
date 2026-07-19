"""
서울 실시간 도시데이터 시각화

스냅샷 DataFrame → 자기완결형 HTML 대시보드 생성.
혼잡 순위·카테고리 요약·연령 분포·날씨/대기질·혼잡-환경 상관을 한 페이지에.

Chart.js(CDN)를 사용하며, 데이터는 placeholder 치환 방식으로 주입한다
(f-string 중괄호 escape 문제 회피).
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import numpy as np
import pandas as pd

from .analysis import (
    congestion_ranking, category_summary, demographic_profile,
    weather_congestion_corr, summary_stats,
)

AGE_LABELS = ["0대", "10대", "20대", "30대", "40대", "50대", "60대", "70+"]


def build_dashboard_data(
    df: pd.DataFrame,
    source_mode: str = "unknown",
) -> dict[str, Any]:
    """DataFrame → 대시보드용 JSON 직렬화 가능 dict."""
    stats = summary_stats(df)

    data_updated_at = None
    if "ppltn_time" in df.columns:
        timestamps = pd.to_datetime(df["ppltn_time"], errors="coerce")
        if timestamps.notna().any():
            data_updated_at = timestamps.max().strftime("%Y-%m-%d %H:%M")

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

    snapshot_time = ""
    if "ppltn_time" in df.columns and df["ppltn_time"].notna().any():
        snapshot_time = str(df["ppltn_time"].dropna().iloc[0])

    return {
        "meta": {
            "source_mode": source_mode,
            "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="minutes"),
            "data_updated_at": data_updated_at,
        },
        "stats": stats,
        "ranking": rank_data,
        "categories": cat_data,
        "age": age_data,
        "age_labels": AGE_LABELS,
        "corr": corr_data,
        "snapshot_time": snapshot_time,
    }


def write_pages_dashboard(
    df: pd.DataFrame,
    docs_dir: str = "docs",
    generated_at: str = "",
    subway_data: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """GitHub Pages용 셸+데이터 분리 배포 파일 생성.

    data.json(집계 데이터) + index.html(셸)을 docs_dir에 쓴다.
    셸은 로드 시 data.json을 fetch해 렌더하며, 새로고침 버튼으로 재요청한다.

    Returns:
        (index_path, data_path)
    """
    import os

    os.makedirs(docs_dir, exist_ok=True)
    data = build_dashboard_data(df, source_mode="api")
    if generated_at:
        data["generated_at"] = generated_at
    if subway_data is not None:
        data["subway"] = subway_data

    data_path = os.path.join(docs_dir, "data.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    index_path = os.path.join(docs_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(_SHELL_TEMPLATE)

    return index_path, data_path


def generate_dashboard(
    df: pd.DataFrame,
    out_path: str = "dashboard.html",
    title: str = "서울 실시간 도시데이터",
    source_mode: str = "unknown",
) -> str:
    """스냅샷 DataFrame → HTML 대시보드 파일 생성. 경로 반환."""
    data = build_dashboard_data(df, source_mode=source_mode)
    # HTML script 태그 종료 문자열이 데이터에 있어도 안전하게 임베드한다.
    serialized = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    html = (
        _TEMPLATE
        .replace("__TITLE__", title)
        .replace("__DATA__", serialized)
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
  .status-row{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:8px 0 20px}
  .sub{color:#8892b0;font-size:13px}
  .status{display:inline-flex;align-items:center;gap:6px;border:1px solid #2a3354;
    border-radius:999px;padding:4px 9px;font-size:12px;color:#c7d2e5;background:#151933}
  .status::before{content:'';width:7px;height:7px;border-radius:50%;background:#4ecca3;
    box-shadow:0 0 10px rgba(78,204,163,.75)}
  .status.stale::before{background:#f2b84b;box-shadow:0 0 10px rgba(242,184,75,.7)}
  .refresh{border:1px solid #2a3354;border-radius:8px;background:#151933;color:#8ab4f8;
    padding:5px 9px;cursor:pointer;font-size:12px}
  .refresh:hover{border-color:#4a6fdc}
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
  <div class="status-row">
    <span class="status" id="status">서울 API 자동 갱신</span>
    <span class="sub" id="sub"></span>
    <button class="refresh" id="refresh" type="button">최신 데이터 확인</button>
  </div>
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
const meta = D.meta || {};
const updatedAt = meta.data_updated_at || meta.generated_at || '확인 불가';
document.getElementById('sub').textContent =
  `데이터 기준 ${updatedAt} (KST) · ${s.n_areas}곳 · 총 인구(추정) ${Math.round(s.total_ppltn_min).toLocaleString()}~${Math.round(s.total_ppltn_max).toLocaleString()}명`;

const status = document.getElementById('status');
if (meta.data_updated_at) {
  const parsed = new Date(meta.data_updated_at.replace(' ', 'T') + ':00+09:00');
  const ageMinutes = (Date.now() - parsed.getTime()) / 60000;
  if (!Number.isFinite(ageMinutes) || ageMinutes > 130) {
    status.classList.add('stale');
    status.textContent = '갱신 지연 · 마지막 정상 데이터';
  }
}

function requestLatest() {
  const next = new URL(window.location.href);
  next.searchParams.set('refresh', Date.now().toString());
  window.location.replace(next.toString());
}
document.getElementById('refresh').addEventListener('click', requestLatest);
setInterval(requestLatest, 5 * 60 * 1000);
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


# GitHub Pages 셸 — data.json을 fetch해 렌더 + 수동 새로고침 버튼
_ADMIN_WORKFLOW_URL = (
    "https://github.com/DongsooJung/ds-research-urban-analytics/"
    "actions/workflows/refresh.yml"
)

_SHELL_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>서울 실시간 도시데이터 대시보드</title>
<meta name="description" content="서울 실시간 도시·지하철 대시보드 — 혼잡·인구·날씨·주요역 도착정보 자동 갱신">
<meta property="og:title" content="서울 실시간 도시데이터 대시보드">
<meta property="og:description" content="서울시 핫스팟 인구·혼잡·날씨와 주요 지하철역 실시간 도착정보">
<meta property="og:type" content="website">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'Malgun Gothic','Apple SD Gothic Neo','Segoe UI',sans-serif;
    background:#0a0e27;color:#e0e6f0;padding:24px;line-height:1.5}
  h1{font-size:24px;color:#8ab4f8;margin-bottom:4px}
  .bar{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:20px}
  .sub{color:#8892b0;font-size:13px}
  .status{display:inline-flex;align-items:center;gap:6px;margin-top:6px;border:1px solid #2a3354;
    border-radius:999px;padding:4px 9px;font-size:12px;color:#c7d2e5;background:#151933}
  .status::before{content:'';width:7px;height:7px;border-radius:50%;background:#4ecca3;
    box-shadow:0 0 10px rgba(78,204,163,.75)}
  .status.stale::before{background:#f2b84b;box-shadow:0 0 10px rgba(242,184,75,.7)}
  .btn{background:#1e2547;border:1px solid #2a3354;color:#b4c2f5;font-size:13px;font-family:inherit;
    padding:9px 14px;border-radius:8px;cursor:pointer;transition:.15s}
  .btn:hover{border-color:#8ab4f8;background:#243060}
  .btn:disabled{opacity:.6;cursor:default}
  .btn.ghost{background:transparent}
  .actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  a{color:#8ab4f8;text-decoration:none}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:22px}
  .kpi{background:#151933;border:1px solid #2a3354;border-radius:12px;padding:18px}
  .kpi .label{font-size:12px;color:#8892b0;margin-bottom:6px}
  .kpi .value{font-size:24px;font-weight:700;color:#8ab4f8}
  .section-head{display:flex;justify-content:space-between;align-items:end;gap:14px;flex-wrap:wrap;
    margin:34px 0 14px;padding-top:24px;border-top:1px solid #1e2547}
  .section-head h2{font-size:20px;color:#e0e6f0}
  .source{font-size:12px;color:#8892b0}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
  .panel{background:#151933;border:1px solid #2a3354;border-radius:12px;padding:20px}
  .panel h2{font-size:15px;color:#e0e6f0;margin-bottom:6px}
  .panel .cap{font-size:12px;color:#8892b0;margin-bottom:12px}
  .panel.full{grid-column:1/-1}
  .chart-box{position:relative;width:100%}
  .legend{display:flex;gap:12px;font-size:12px;color:#8892b0;flex-wrap:wrap;margin-bottom:10px}
  .legend span{display:inline-flex;align-items:center;gap:5px}
  .dot{width:10px;height:10px;border-radius:2px;display:inline-block}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{text-align:left;color:#8892b0;padding:8px;border-bottom:1px solid #2a3354}
  td{padding:8px;border-bottom:1px solid #1e2547}
  .table-wrap{overflow-x:auto}
  .line-pill{display:inline-flex;align-items:center;white-space:nowrap;border-radius:999px;
    padding:3px 8px;color:#fff;font-size:11px;font-weight:700}
  .arrival.near td{background:rgba(78,204,163,.045)}
  .arrival-message{font-weight:650;color:#dce7f9;white-space:nowrap}
  .muted{color:#8892b0;font-size:12px}
  .corr-pos{color:#4ecca3}.corr-neg{color:#e94560}
  .chip{display:inline-flex;align-items:center;gap:6px;font-size:13px;padding:6px 12px;border-radius:8px}
  #err{color:#e94560;font-size:13px;margin:8px 0}
  @media(max-width:768px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
  <div class="bar">
    <div>
      <h1>🏙️ 서울 실시간 도시데이터 대시보드</h1>
      <div class="sub" id="sub">불러오는 중…</div>
      <div class="status" id="status">서울 API 자동 갱신</div>
    </div>
    <div class="actions">
      <button class="btn" id="refresh" onclick="loadData(true)">🔄 새로고침</button>
      <a class="btn ghost" href="__ADMIN_URL__" target="_blank" rel="noopener" title="관리자: 서울 API에서 최신 데이터 재수집 (GitHub Actions 수동 실행)">⚙ 지금 수집</a>
    </div>
  </div>
  <div id="err"></div>

  <div class="kpis" id="kpis"></div>

  <section id="subwayRoot" hidden>
    <div class="section-head">
      <div>
        <h2>🚇 주요역 실시간 도착정보</h2>
        <div class="sub" id="subwaySub"></div>
      </div>
      <div class="source" id="subwaySource"></div>
    </div>
    <div class="kpis" id="subwayKpis"></div>
    <div class="grid">
      <div class="panel">
        <h2>노선별 도착예보 열차</h2>
        <div class="cap">8개 표본역 API 응답에 포함된 고유 열차 수</div>
        <div class="chart-box" id="subwayChartBox"><canvas id="subwayChart" role="img" aria-label="노선별 실시간 도착예보 열차 수"></canvas></div>
      </div>
      <div class="panel">
        <h2>수집 범위·해석 안내</h2>
        <div class="cap">전체 서울 지하철이 아닌 주요 환승·상권·관광역 표본입니다.</div>
        <div id="subwayCoverage" class="muted"></div>
      </div>
    </div>
    <div class="panel" style="margin-bottom:18px">
      <h2>실시간 도착 전광판</h2>
      <div class="cap">API 도착 메시지·수신시각 기준 · 역당 최대 2건</div>
      <div class="table-wrap">
        <table><thead><tr><th>역</th><th>노선</th><th>방향·행선</th><th>도착 상태</th><th>수신</th></tr></thead>
          <tbody id="subwayBoard"></tbody></table>
      </div>
    </div>
  </section>

  <div class="grid">
    <div class="panel full">
      <h2>혼잡 순위</h2>
      <div class="cap">막대 = 인구 추정 중앙값(명) · 색 = 혼잡 등급</div>
      <div class="legend" id="legend"></div>
      <div class="chart-box" id="rankBox"><canvas id="rankChart" role="img" aria-label="지역별 인구 가로 막대, 색은 혼잡 등급"></canvas></div>
    </div>
  </div>
  <div class="grid">
    <div class="panel"><h2>연령대 분포</h2><div class="cap">인구 가중 평균(%)</div>
      <div class="chart-box" style="height:260px"><canvas id="ageChart" role="img" aria-label="연령대별 유동인구 비율"></canvas></div></div>
    <div class="panel"><h2>혼잡–환경 상관</h2><div class="cap">혼잡 점수와 환경 지표의 상관계수</div>
      <div id="corr" style="display:flex;flex-wrap:wrap;gap:10px"></div></div>
  </div>

<script>
const LVL={"여유":"#0ca30c","보통":"#fab219","약간 붐빔":"#ec835a","붐빔":"#d03b3b"};
const fmt=n=>Math.round(n).toLocaleString();
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const shortTime=value=>value?value.split(' ').pop():'—';
let charts={};

function loadData(manual){
  const btn=document.getElementById('refresh');
  if(manual){btn.disabled=true;btn.textContent='불러오는 중…';}
  fetch('./data.json?t='+Date.now(),{cache:'no-store'})
    .then(r=>{if(!r.ok)throw new Error('data.json '+r.status);return r.json();})
    .then(D=>{render(D);document.getElementById('err').textContent='';})
    .catch(e=>{document.getElementById('err').textContent='데이터 로드 실패: '+e.message;})
    .finally(()=>{if(manual){btn.disabled=false;btn.textContent='🔄 새로고침';}});
}

function render(D){
  const now=new Date().toLocaleString('ko-KR',{hour12:false});
  const snap=D.snapshot_time||'';
  const gen=D.generated_at?(' · 생성 '+D.generated_at):'';
  document.getElementById('sub').textContent=
    `데이터 기준 ${snap}${gen} · 지역 ${D.stats.n_areas}곳 · 마지막 확인 ${now}`;
  const status=document.getElementById('status');
  const stamp=(D.meta&&D.meta.data_updated_at)||snap;
  const parsed=stamp?new Date(stamp.replace(' ','T')+':00+09:00'):null;
  const ageMinutes=parsed?(Date.now()-parsed.getTime())/60000:Infinity;
  status.classList.toggle('stale',!Number.isFinite(ageMinutes)||ageMinutes>130);
  status.textContent=status.classList.contains('stale')
    ? '갱신 지연 · 마지막 정상 데이터'
    : '서울 API 자동 갱신';

  const s=D.stats;
  const kpis=[['지역 수',s.n_areas],
    ['총 인구(추정)',fmt(s.total_ppltn_min)+'~'+fmt(s.total_ppltn_max)],
    ['평균 혼잡점수',(s.mean_congest_score||0).toFixed(2)+' / 4'],
    ['평균 기온',s.mean_temp==null?'—':s.mean_temp.toFixed(1)+'°C']];
  document.getElementById('kpis').innerHTML=kpis.map(k=>
    `<div class="kpi"><div class="label">${k[0]}</div><div class="value">${k[1]}</div></div>`).join('');

  document.getElementById('legend').innerHTML=Object.entries(LVL).map(([k,v])=>
    `<span><span class="dot" style="background:${v}"></span>${k}</span>`).join('');

  const R=D.ranking;
  document.getElementById('rankBox').style.height=(R.length*34+60)+'px';
  Object.values(charts).forEach(c=>c&&c.destroy());
  charts.rank=new Chart(document.getElementById('rankChart'),{
    type:'bar',
    data:{labels:R.map(d=>d.area),datasets:[{data:R.map(d=>d.ppltn),
      backgroundColor:R.map(d=>LVL[d.level]||'#888'),borderRadius:4,barThickness:20}]},
    options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>fmt(c.raw)+'명 · '+R[c.dataIndex].level}}},
      scales:{x:{ticks:{color:'#8892b0',callback:v=>fmt(v)},grid:{color:'#1e2547'}},
        y:{ticks:{color:'#b4c2f5',font:{size:11}},grid:{display:false}}}}
  });

  charts.age=new Chart(document.getElementById('ageChart'),{
    type:'bar',
    data:{labels:D.age_labels,datasets:[{data:D.age,backgroundColor:'#4a6fdc',borderRadius:4}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.raw.toFixed(1)+'%'}}},
      scales:{x:{ticks:{color:'#8892b0'},grid:{display:false}},
        y:{ticks:{color:'#8892b0',callback:v=>v+'%'},grid:{color:'#1e2547'}}}}
  });

  const NAMES={temp:'기온',humidity:'습도',pm10:'PM10',pm25:'PM2.5',uv_index:'자외선',road_spd:'도로속도'};
  document.getElementById('corr').innerHTML=D.corr.map(c=>{
    if(c.corr==null)return '';
    const pos=c.corr>=0,bg=pos?'#12294a':'#3a1520',fg=pos?'#8ab4f8':'#e98aa0';
    return `<span class="chip" style="background:${bg};color:${fg}">${NAMES[c.metric]||c.metric} <b>${pos?'+':''}${c.corr.toFixed(2)}</b></span>`;
  }).join('');

  renderSubway(D.subway);
}

function renderSubway(S){
  const root=document.getElementById('subwayRoot');
  if(!S||!Array.isArray(S.board)){root.hidden=true;return;}
  root.hidden=false;
  document.getElementById('subwaySub').textContent=
    `API 수신 ${S.updated_at||'—'} · ${S.station_count}/${S.requested_station_count}개 역 수집`;
  const src=S.source||{};
  document.getElementById('subwaySource').innerHTML=src.url
    ? `<a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(src.portal)} · ${esc(src.dataset)} ↗</a>`
    : '';
  const subwayKpis=[
    ['표본역',S.station_count+'곳'],
    ['포착 노선',S.line_count+'개'],
    ['도착 예보',S.arrival_count+'건'],
    ['진입·도착 임박',S.near_count+'건']
  ];
  document.getElementById('subwayKpis').innerHTML=subwayKpis.map(k=>
    `<div class="kpi"><div class="label">${k[0]}</div><div class="value">${k[1]}</div></div>`).join('');

  const L=S.lines||[];
  document.getElementById('subwayChartBox').style.height=Math.max(230,L.length*34+55)+'px';
  charts.subway=new Chart(document.getElementById('subwayChart'),{
    type:'bar',data:{labels:L.map(x=>x.line),datasets:[{data:L.map(x=>x.train_count),
      backgroundColor:L.map(x=>x.color),borderRadius:4,barThickness:19}]},
    options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.raw+'개 열차'}}},
      scales:{x:{beginAtZero:true,ticks:{color:'#8892b0',precision:0},grid:{color:'#1e2547'}},
        y:{ticks:{color:'#b4c2f5'},grid:{display:false}}}}
  });

  document.getElementById('subwayCoverage').innerHTML=
    `<p><b style="color:#dce7f9">${esc(src.coverage||'')}</b></p>`+
    `<p style="margin-top:8px">수집역: ${S.stations.map(esc).join(' · ')}</p>`+
    `<p style="margin-top:8px">도착정보는 원천 수집·가공 시차가 있을 수 있어 <code>recptnDt</code> 수신시각을 함께 표시합니다.</p>`;

  document.getElementById('subwayBoard').innerHTML=S.board.map(row=>
    `<tr class="arrival ${row.near?'near':''}">`+
      `<td><b>${esc(row.station)}</b></td>`+
      `<td><span class="line-pill" style="background:${esc(row.color)}">${esc(row.line)}</span></td>`+
      `<td>${esc(row.direction)}<div class="muted">${esc(row.destination)}</div></td>`+
      `<td class="arrival-message">${esc(row.message)}${row.train_type&&row.train_type!=='일반'?` <span class="muted">${esc(row.train_type)}</span>`:''}</td>`+
      `<td class="muted">${esc(shortTime(row.received_at))}</td></tr>`
  ).join('');
}

loadData(false);
setInterval(()=>loadData(false),5*60*1000);
</script>
</body>
</html>""".replace("__ADMIN_URL__", _ADMIN_WORKFLOW_URL)
