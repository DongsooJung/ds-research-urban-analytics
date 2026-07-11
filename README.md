# Seoul Real-time City Data Analytics · 서울 실시간 도시데이터 분석

> 서울시 120개 핫스팟의 실시간 인구·혼잡·날씨·교통·상권 데이터를 수집·파싱·분석하는 파이프라인

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Data](https://img.shields.io/badge/data-Seoul%20Open%20Data-1E88E5?style=flat-square)](https://data.seoul.go.kr)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

## 개요 · Overview

서울시는 관광특구·발달상권·인구밀집지역·공원·고궁문화유산 등 **120개 주요 장소**의
실시간 도시데이터(인구 혼잡도, 12단계 인구 예보, 날씨·대기질, 도로 소통, 상권 결제)를
공개 API로 제공한다. 본 저장소는 이 데이터를 수집→평탄화→분석하는 재현 가능한
파이프라인을 제공한다.

Seoul provides real-time city data (crowd congestion, 12-step population forecast,
weather/air quality, road traffic, commercial activity) for 120 hotspots via an open API.
This repo collects, flattens, and analyzes it.

## 주요 기능 · Features

- **수집** (`api.py`): 지역별 `citydata` API 병렬 호출, 오류 지역 자동 스킵
- **파싱** (`parser.py`): 중첩 JSON → 분석용 평탄 레코드/DataFrame
  (혼잡도·인구·성별·연령·거주비율·날씨·PM10/PM2.5·도로속도·상권)
- **분석** (`analysis.py`): 혼잡 순위, 카테고리 요약, 인구통계 프로파일,
  성비, **혼잡–날씨/대기질 상관**, 스냅샷 요약통계
- **12단계 인구 예보** 파싱 (`parse_forecast`)

## 데이터 소스 · Data Source

서울 열린데이터광장 「서울시 실시간 도시데이터」

```
http://openapi.seoul.go.kr:8088/{KEY}/json/citydata/1/5/{지역명}
```

### API 키 설정

```bash
# data.seoul.go.kr 에서 발급받은 인증키를 환경변수로 설정
export SEOUL_API_KEY="발급받은_인증키"      # Windows(PowerShell): $env:SEOUL_API_KEY="..."
```

- 키 **미설정 시** `sample` 키로 동작 → 지역과 무관하게 **동일한 고정 샘플**을 반환한다
  (구조 확인·파이프라인 점검용). 지역별 실데이터는 개인 키가 필요하다.

## 빠른 시작 · Quick Start

```bash
pip install -r requirements.txt

# 전체 지역 스냅샷 → CSV + 요약 출력
python scripts/snapshot.py

# 관광특구만
python scripts/snapshot.py --category 관광특구 --out tour.csv

# 특정 지역 (공백은 밑줄로)
python scripts/snapshot.py --areas 강남역 여의도 홍대_관광특구
```

### 라이브러리로 사용

```python
from seoul_citydata import fetch_many, to_dataframe, congestion_ranking, weather_congestion_corr
from seoul_citydata.areas import ALL_AREAS

raw = fetch_many(ALL_AREAS)              # SEOUL_API_KEY 사용
df = to_dataframe(raw)
print(congestion_ranking(df, top=10))    # 가장 붐비는 10곳
print(weather_congestion_corr(df))       # 혼잡 vs 날씨/대기질 상관
```

### 시각화 · Dashboard

`viz.py`가 스냅샷 DataFrame → 자기완결형 HTML 대시보드(혼잡 순위·카테고리·연령분포·
혼잡-환경 상관, Chart.js)를 생성한다.

```bash
# 라이브 수집 → 대시보드
python scripts/dashboard.py --out dashboard.html

# 저장된 스냅샷 CSV로부터
python scripts/dashboard.py --csv snapshot.csv --out dashboard.html

# 키 없이 차트 미리보기 (합성 데모 데이터)
python scripts/dashboard.py --demo --out demo.html
```

```python
from seoul_citydata.viz import generate_dashboard
generate_dashboard(df, "dashboard.html")
```

## 프로젝트 구조 · Structure

```
ds-research-urban-analytics/
├── src/seoul_citydata/
│   ├── api.py          # API 클라이언트 (병렬 수집)
│   ├── parser.py       # 중첩 JSON → 평탄 레코드/DataFrame
│   ├── analysis.py     # 순위·요약·상관·프로파일
│   ├── viz.py          # 스냅샷 → HTML 대시보드 생성
│   └── areas.py        # 120개 지역 큐레이션 목록 + 혼잡도 상수
├── scripts/
│   ├── snapshot.py     # 스냅샷 수집 CLI (CSV)
│   └── dashboard.py    # HTML 대시보드 생성 CLI
├── tests/              # fixture 기반 단위 테스트 (네트워크 불필요)
│   ├── fixtures/sample_citydata.json
│   ├── test_seoul_citydata.py
│   └── test_viz.py
├── requirements.txt
└── README.md
```

## 분석 지표 · Metrics

| 범주 | 지표 |
|---|---|
| 인구·혼잡 | 혼잡도(여유·보통·약간붐빔·붐빔), 인구 min/max, 12단계 예보 |
| 인구통계 | 성비, 연령대(0~70+) 분포, 거주/비거주 비율 |
| 날씨·대기질 | 기온·습도·강수, PM10·PM2.5, 통합대기지수, 자외선 |
| 교통 | 도로 소통(원활·서행·정체), 평균 속도 |
| 상권 | 상권 혼잡, 결제 건수 |

## 테스트 · Tests

```bash
pytest -q            # 29개 테스트 (fixture 기반, 네트워크 불필요)
```

## 라이선스 · License

MIT License

## 저자 · Author

**정동수 (Dongsoo Jung)** — 서울대학교 박사과정 · 공간계량 & 도시분석
