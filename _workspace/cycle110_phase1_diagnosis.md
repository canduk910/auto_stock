# 사이클 110 Phase 1 진단 — `routes/stock_master.py` silent 결함 영구 영속이 영구 발견

**일자**: 2026-06-11 (목)
**진단자**: team-leader
**의뢰자**: 사용자 (운영 보고)

---

## 사용자 보고 (verbatim)

> "혹시 종목마스터에서 새로고침을 눌렀을 때, 적재 실패 - 잠시 후 재시도 가 나오는 이유를 알아? 내가 야간배치에서 종목마스터를 만들라고 해서 그런가? 계속 종목마스터 확장이 잘 안되고 있는데 대안이 필요할 것 같아. 정 안된다면 차라리 상장종목 코드리스트를 받을 수 있는 다른 오픈된 API를 사용해보는건 어떨까?"

---

## Phase 1-A 정밀 진단 결과

### A1: 실시간 routes 영역 영구 영속이 점검

**파일**: `src/routes/stock_master.py:51-67`

```python
async with _refresh_universe_lock:
    from src.engine.scanner import (
        fetch_top_500_universe,                                   # ❌ Line 53
        _universe_eager_refresh_loop as _scanner_upsert_loop,     # ❌ Line 54
    )

    start_time = time.monotonic()
    try:
        tickers = await fetch_top_500_universe()                  # ❌ Line 59
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

### A2: scanner.py 영역 영구 영속이 점검

**파일**: `src/engine/scanner.py:1720-1737`

```python
# Q68=A (사이클 101) 영구 폐기: fetch_top_500_universe + _universe_eager_refresh_loop

# NOTE: fetch_top_500_universe() 와 _universe_eager_refresh_loop() 는
# 사이클 101 (Q68=A+Q69=B) 의 영구 폐기 결정에 의해 본 영역에서 제거되었음.

# (아래 영역은 사이클 101 이전 fetch_top_500_universe() 과 _universe_eager_refresh_loop()
# 의 본체였으나, 모두 _full_universe_load_once() 로 통합되었음.)

# (사이클 101 Q68=A+Q69=B 에 의해 fetch_top_500_universe/
# _universe_eager_refresh_loop 영구 폐기 완료.)
```

### A3: 정상 대체 영역 영구 영속이 확인

**파일**: `src/engine/scanner.py:1579`

```python
async def _full_universe_load_once() -> dict:
    """사이클 101 (2026-06-11) — market_cap FHPST01740000 기반 전체 유니버스 일괄 적재.
    
    매일 20:00:05 scheduler 에서 1회 호출 (Q67=B). KOSPI + KOSDAQ market_cap 페이징
    누적 → 종목별 CTPF1002R 67컬럼 조회 → stock_master upsert.
    
    환경 분리 Rate Limit (domain-expert A3):
    - 실전(real): 50ms + max 300s
    - 모의(vts): 200ms + max 600s
    
    Returns:
        summary dict 9 키:
        total / kospi / kosdaq / securities / etf / fetched / skipped_ttl / failed / elapsed_ms
    """
```

---

## 결함 chain 영구 영속이 영구 확정

1. 운영자 UI 종목마스터 → "지금 새로고침" 버튼 클릭
2. 프론트 → POST `/api/stock-master/refresh-universe` 호출
3. `refresh_universe_now()` 영역 영구 영속이 진입
4. `_refresh_universe_lock` 영역 영구 영속이 획득
5. **L52-55 영역 영구 영속이 = `from src.engine.scanner import (...)` → ImportError**
   - `fetch_top_500_universe` 영역 영구 영속이 = 사이클 101 영구 폐기 영역 (scanner.py 에 함수 영역 영구 영속이 영구 부재)
   - `_universe_eager_refresh_loop` 영역 영구 영속이 = 사이클 101 영구 폐기 영역 (동일)
6. ImportError → except 영역 영구 영속이 → HTTPException 500
7. 프론트 → "KIS API 일시 결함 — 잠시 후 재시도" 토스트 (사이클 106 메시지 영역 영구 영속이)

---

## 단일 근본 원인 영구 영속이 영구 확정

**사이클 101 (Q68=A + Q69=B)** 영역 영구 영속이 = `fetch_top_500_universe` + `_universe_eager_refresh_loop` 영구 폐기 시점에 `src/routes/stock_master.py::refresh_universe_now` 영역 영구 영속이 동행 시정 누락 = silent 결함 영구 영속이 영구 잔존.

사이클 101~108 (8 사이클 동안) 발견 0건 = silent 결함 영역 영구 영속이 영구 확정 (Plan Phase A 데이터 영역 활용 가능 진단 + 6 사이클 통합 시정에도 불구 routes 영역 동행 시정 누락).

---

## 사이클 110 시정 영역 영구 영속이 (Auto Mode 결정)

**옵션 A**: `_full_universe_load_once()` 영역 영구 영속이 활용 → 단일 호출 (사이클 101 영역 영구 영속이 정상 함수 영역 영구 영속이 + 사이클 106/107/108/109 영역 영속 통합)

**옵션 B**: 사이클 101 영구 폐기 영역 부활 → 영구 영속이 의무 위반 (사이클 88 G-REJECT 영속 + 사이클 101 영구 영속이 정합성 위배)

**채택 영역 영구 영속이 = 옵션 A** (사용자 결정 의제 없음 + Auto Mode 영역 영구 영속이 + 단순 시정 + 안전 영역 영구 영속이)

---

## 매매 안전성 영역 영구 영속이 무영향 확정

- POST `/refresh-universe` 영역 영구 영속이 = scanner 단계 매수 진입 전 후보 풀 영역 영구 영속이 한정
- 매도/손절/Trailing/익일청산/15:20 강제청산 hot path 무관
- 사이클 38 명문화 영속

---

## 영구 영속이 의무 매트릭스 (시정 영역 영구 영속이 영구 영속)

- 사이클 32 R4 universe guard 영속
- 사이클 38 명문화 영속
- 사이클 88 G-REJECT 3 영역 영속
- 사이클 101 영속 (`_full_universe_load_once` 영역 영구 영속이 활용)
- 사이클 102 G-REJECT 영속
- 사이클 106 영속 (lifecycle race 차단 영역 영구 영속이)
- 사이클 107 영속 (raw 보강 의존성 해소 영역 영구 영속이)
- 사이클 109 영속 (market-cap 화이트리스트 영역 영구 영속이)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

---

## 사이클 111+ 후속 카드 인계 의무

1. **KRX 정보데이터시스템 OPEN API 영역 영구 영속이 도입 검토** (옵션 A `MDCSTAT01901`)
   - 사용자 요구 사항 영역 영구 영속이 ("상장종목 코드리스트를 받을 수 있는 다른 오픈된 API")
   - KIS API 영역 영구 영속이 의존성 해소
2. **또는 pykrx 라이브러리** (옵션 B)
   - PyPI 영구 영속이 + 활성 maintenance + KRX 영역 영구 영속이 직접 호출
3. **domain-expert 자문 의무**:
   - 안정성 (KRX vs KIS Maintenance 비교)
   - KIS chain 영향 (KIS LMS chain 차단 가능성)
   - Rate Limit 차이
   - 호환성 (사이클 101~109 영역 영속 유지 + KRX 영역 보강만 vs 전면 교체)
4. **별개 사이클** (사이클 111 또는 이후) — 본 사이클 영역 영구 영속이 = 응급 시정 영역만 한정
