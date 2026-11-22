# 기여 안내

> 연구 재현성을 함께 유지합니다. 분석 결과의 출처와 조건이 코드에 남아 있어야
> 다른 사람이 같은 결론을 확인할 수 있습니다.

---

## 1. 환경 설정

```bash
git clone https://github.com/DongsooJung/ds-research-urban-analytics.git
cd ds-research-urban-analytics
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. 테스트

```bash
pytest tests/ -v
```

테스트는 API 키 없이 로컬 데이터로만 동작합니다. 외부 API 응답이 필요한
경우에는 `monkeypatch`로 대체 응답을 주입하는 방식만 사용합니다.

## 3. 작업 절차

1. 이슈를 먼저 등록하고 접근 방법을 합의합니다.
2. `main`에서 브랜치를 파고(`feat/`, `fix/`, `docs/`), 기능 단위로 커밋합니다.
3. 공개 함수에는 타입 힌트를 붙이고, 동작 변경에는 테스트를 함께 추가합니다.
4. PR에 무엇을 왜 바꿨는지 적어 제출합니다.

## 4. 데이터와 재현성

- 데이터 수집 시점·출처·질의 조건을 코드와 문서에 함께 남깁니다.
- API 키는 `.env`로만 주입하고 저장소에 커밋하지 않습니다.
- 좌표계(EPSG:4326 → 5186 변환 등)와 거리 기준(직선거리/도로망)을 명시합니다.

## 라이선스

기여분은 [MIT License](LICENSE) 기준으로 받습니다.
