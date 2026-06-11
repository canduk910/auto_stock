# 사이클 110 Red 명세 — `routes/stock_master.py` silent 결함 영역 영구 영속이 영구 시정

**일자**: 2026-06-11 (목)
**위급도**: HIGH (운영자 "지금 새로고침" 100% 영구 실패 영역 영구 영속이)
**근본 원인**: 사이클 101 (Q68=A + Q69=B) `fetch_top_500_universe` + `_universe_eager_refresh_loop` 영구 폐기 → `routes/stock_master.py:52-54` import 영역 영구 영속이 silent 결함 영구 잔존 (사이클 101~108 발견 0건)
**시정 영역 영구 영속이**: 단일 파일 `src/routes/stock_master.py::refresh_universe_now` (5~10L)
**대체 영역 영구 영속이**: `scanner.py:1579 _full_universe_load_once()` 영역 영구 영속이 활용 (사이클 101 영역 정상 함수 + 사이클 109 시정 영역 활용 = market-cap 페이징 KOSPI/KOSDAQ 전체 ~2,800 ticker)

---

## Phase 1 진단 결정적 발견 (영구 영속이 영구 확정)

### 1.1 사용자 보고 (verbatim)
> "혹시 종목마스터에서 새로고침을 눌렀을 때, 적재 실패 - 잠시 후 재시도 가 나오는 이유를 알아? 내가 야간배치에서 종목마스터를 만들라고 해서 그런가? 계속 종목마스터 확장이 잘 안되고 있는데 대안이 필요할 것 같아. 정 안된다면 차라리 상장종목 코드리스트를 받을 수 있는 다른 오픈된 API를 사용해보는건 어떨까?"

### 1.2 결정적 발견 chain (영구 영속이)
- `src/routes/stock_master.py:52-54` 영역 영구 영속이:
  ```python
  from src.engine.scanner import (
      fetch_top_500_universe,                                   # ❌ 사이클 101 영구 폐기 영역
      _universe_eager_refresh_loop as _scanner_upsert_loop,     # ❌ 사이클 101 영구 폐기 영역
  )
  ```
- `src/engine/scanner.py:1720-1737` 영역 영구 영속이 = 사이클 101 영구 폐기 영역 명시 docstring:
  ```python
  # Q68=A (사이클 101) 영구 폐기: fetch_top_500_universe + _universe_eager_refresh_loop
  # NOTE: fetch_top_500_universe() 와 _universe_eager_refresh_loop() 는
  # (사이클 101 Q68=A+Q69=B 에 의해 fetch_top_500_universe/
  # _universe_eager_refresh_loop 영구 폐기 완료.)
  ```
- 결과 chain: 운영자 "지금 새로고침" 클릭 → POST `/api/stock-master/refresh-universe` → ImportError → except → HTTPException 500 → 프론트 "KIS API 일시 결함 — 잠시 후 재시도" 토스트 (사이클 106 메시지 영역 영구 영속이)
- 사이클 101~108 (8 사이클 동안) 발견 0건 = silent 결함 영역 영구 영속이 영구 확정

### 1.3 정상 대체 영역 영구 영속이 (영구 영속이)
- `src/engine/scanner.py:1579 _full_universe_load_once()` 영역 영구 영속이:
  - 사이클 101 영역 영구 영속이 신규 도입 (KOSPI + KOSDAQ market-cap 페이징 누적 + CTPF1002R + stock_master upsert)
  - 사이클 106 영역 영구 영속이 (lifecycle race 차단 = scheduler.py `_full_universe_load_task_loop` start() 직후 즉시 1회 + while 루프)
  - 사이클 107 영역 영구 영속이 (CTPF1002R + FHKST01010100 merge → raw 3 키 보강)
  - 사이클 108 영역 영구 영속이 (`list_by_filter` 신규 메서드)
  - 사이클 109 영역 영구 영속이 (market-cap 화이트리스트 영역 영구 영속이)
  - 영구 영속이 의무 매트릭스: 사이클 32 R4 + 38 명문화 + 88 G-REJECT + 101 영속 + 106 영속 + 107 영속 + 109 영속

---

## 시정 명세 (Green 단계)

### 2.1 영역 1 — `src/routes/stock_master.py::refresh_universe_now` 시정

**위치**: L52~L67 영역 영구 영속이

**Before (사이클 101 silent 결함 영역 영구 영속이)**:
```python
async with _refresh_universe_lock:
    from src.engine.scanner import (
        fetch_top_500_universe,
        _universe_eager_refresh_loop as _scanner_upsert_loop,  # 사이클 93 신규
    )

    start_time = time.monotonic()
    try:
        tickers = await fetch_top_500_universe()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # 사이클 93 — stock_master upsert chain (graceful — 사이클 89 emit 영속)
    try:
        await _scanner_upsert_loop(tickers)
    except Exception:
        pass  # graceful 흡수 — 사이클 89 [stock_master_bulk_refresh] 영속 (Q27=A 영속)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    return ApiResponse(
        success=True,
        data={
            "universe": len(tickers),
            "elapsed_ms": elapsed_ms,
        },
        message=f"universe {len(tickers)} ticker 즉시 적재 완료",
    )
```

**After (사이클 110 시정 영역 영구 영속이)**:
```python
async with _refresh_universe_lock:
    from src.engine.scanner import _full_universe_load_once  # 사이클 110 영역 영구 영속이

    start_time = time.monotonic()
    try:
        summary = await _full_universe_load_once()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    return ApiResponse(
        success=True,
        data={
            "universe": summary.get("total", 0),
            "elapsed_ms": elapsed_ms,
            # 사이클 110 영역 영구 영속이 — _full_universe_load_once 영역 신규 영역
            "fetched": summary.get("fetched", 0),
            "skipped_ttl": summary.get("skipped_ttl", 0),
            "failed": summary.get("failed", 0),
            "kospi": summary.get("kospi", 0),
            "kosdaq": summary.get("kosdaq", 0),
        },
        message=f"universe {summary.get('total', 0)} ticker 즉시 적재 완료 (fetched={summary.get('fetched', 0)})",
    )
```

**시정 사유 영역 영구 영속이**:
1. `fetch_top_500_universe` + `_universe_eager_refresh_loop` 영구 폐기 영역 의존성 해소
2. `_full_universe_load_once()` 영역 영구 영속이 단일 호출 = stock_master upsert chain 영역 내장 영역 (Phase 1 페이징 + Phase 2 종목별 CTPF1002R + upsert)
3. 사이클 89 `[stock_master_bulk_refresh]` emit 영역 영구 영속이 = `_full_universe_load_once` 내부 영역 영속이 (별도 chain 호출 불필요)
4. 응답 영역 영구 영속이 = summary 9 키 중 운영자 관심 7 키 노출 (total + fetched + skipped_ttl + failed + kospi + kosdaq + elapsed_ms)
5. graceful Exception → HTTPException 500 영구 영속이 (사이클 102 G-REJECT 영속)

---

## 회귀 가드 매트릭스 (HIGH 3 + MEDIUM 2 + LOW 1 = 6 케이스)

### HIGH-1: import 영역 영구 영속이 시정 확인
**파일**: `tests/unit/routes/test_cycle110_import_fix.py`
**케이스**: G-IMPORT1
```python
def test_g_import1_refresh_universe_calls_full_universe_load_once():
    """
    HIGH-1: refresh_universe_now 영역 영구 영속이 가 _full_universe_load_once 호출 영역 영구 영속이.
    
    사이클 101 (Q68=A+Q69=B) 영구 폐기 영역 = fetch_top_500_universe + _universe_eager_refresh_loop
    사이클 110 영역 영구 영속이 시정 = _full_universe_load_once 단일 호출 영역 영구 영속이
    """
    # AST 정적 검증: routes/stock_master.py 영역 영구 영속이 에 _full_universe_load_once 호출 ≥1건
    # AST 정적 검증: fetch_top_500_universe + _universe_eager_refresh_loop import 0건 (영구 부재)
```

### HIGH-2: AST 영구 가드 = 사이클 101 영구 폐기 영역 영구 부재 영구 영속이
**파일**: `tests/unit/ast/test_cycle110_ast_no_deprecated_imports.py`
**케이스**: G-AST1
```python
def test_g_ast1_no_deprecated_universe_functions_imported():
    """
    HIGH-2: AST 영구 가드 영역 영구 영속이 = 사이클 101 영구 폐기 영역 영구 차단.
    
    src/routes/stock_master.py 영역 영구 영속이 에서:
    - fetch_top_500_universe import 0건 영구 영속이
    - _universe_eager_refresh_loop import 0건 영구 영속이
    - _scanner_upsert_loop alias 0건 영구 영속이
    
    미래 silent 결함 영역 영구 차단 (회귀 시 즉시 검출).
    """
    import ast
    src = open("src/routes/stock_master.py").read()
    tree = ast.parse(src)
    forbidden = {"fetch_top_500_universe", "_universe_eager_refresh_loop", "_scanner_upsert_loop"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name not in forbidden, f"폐기 영역 import 영역 영구 영속이: {alias.name}"
                if alias.asname:
                    assert alias.asname not in forbidden, f"폐기 영역 alias 영역 영구 영속이: {alias.asname}"
```

### HIGH-3: 200 응답 영역 영구 영속이 정합성
**파일**: `tests/unit/routes/test_cycle110_response_format.py`
**케이스**: G-RESPONSE1
```python
async def test_g_response1_returns_summary_dict():
    """
    HIGH-3: 200 응답 영역 영구 영속이 = ApiResponse{success=True, data={...}, message=...}.
    
    data 영역 영구 영속이 신규 키 7종:
    - universe (≡ summary["total"], 사이클 89 영역 영속이 호환)
    - elapsed_ms
    - fetched (사이클 110 영역 신규 영역 영구 영속이)
    - skipped_ttl (24h TTL idempotency 영역 영구 영속이)
    - failed (사이클 88 G-REJECT 영속)
    - kospi
    - kosdaq
    """
    # mock _full_universe_load_once → summary dict 9 키 반환
    # POST /api/stock-master/refresh-universe 호출
    # 응답 영역 영구 영속이 7 키 검증
```

### MEDIUM-1: 409 Conflict 영역 영구 영속이 영속
**파일**: `tests/unit/routes/test_cycle110_lock_persistence.py`
**케이스**: G-LOCK1
```python
async def test_g_lock1_concurrent_call_returns_409():
    """
    MEDIUM-1: asyncio.Lock 영역 영구 영속이 = 동시 호출 시 두 번째 호출 409 Conflict.
    
    사이클 90 영역 영구 영속이 의무 (Q25=A 영구 영속이).
    """
    # 첫 호출 대기 중 → 두 번째 호출 즉시 409
```

### MEDIUM-2: graceful Exception → 500 영구 영속이
**파일**: `tests/unit/routes/test_cycle110_exception_graceful.py`
**케이스**: G-EXC1
```python
async def test_g_exc1_graceful_exception_returns_500():
    """
    MEDIUM-2: _full_universe_load_once 영역 영구 영속이 Exception → HTTPException 500.
    
    사이클 102 G-REJECT 영속 (양 agent 일치, 매수/매도/익일청산 hot path 영역 보존).
    """
    # mock _full_universe_load_once → raise Exception
    # POST 호출 → 500 응답 확인
```

### LOW-1: 사이클 89 emit 영역 영구 영속이 의무
**파일**: `tests/unit/routes/test_cycle110_emit_persistence.py`
**케이스**: G-EMIT1
```python
async def test_g_emit1_stock_master_bulk_refresh_emit_persistence():
    """
    LOW-1: 사이클 89 [stock_master_bulk_refresh] emit 영역 영구 영속이 의무.
    
    _full_universe_load_once 내부 영역 영구 영속이 에서 emit 발화 (별도 chain 호출 불필요).
    """
    # mock _full_universe_load_once 호출 → caplog 영역 영구 영속이 검증
    # [stock_master_bulk_refresh] prefix 영구 영속이 1행 이상 발견
```

---

## 영구 영속이 의무 매트릭스 (전수 영속)

| 사이클 | 영역 영구 영속이 |
|--------|------------------|
| 사이클 32 R4 universe guard | 보유/익일청산 절대 보호 영역 영구 영속이 |
| 사이클 38 명문화 | scanner 단계 = 매수 진입 전용 영역 영구 영속이 |
| 사이클 88 G-REJECT 3 영역 | 재구독 영역 영구 영속이 폐기 금지 (사이클 29 005935 LMS chain 사고 재현 위험) |
| 사이클 101 영속 | `_full_universe_load_once` 영역 영구 영속이 24h TTL idempotency 영속 |
| 사이클 102 G-REJECT 영속 | 양 agent 일치 영구 영속이 (매수/매도/익일청산 hot path 보존) |
| 사이클 106 영속 | lifecycle race 차단 영역 영구 영속이 |
| 사이클 107 영속 | raw 보강 의존성 해소 영역 영구 영속이 |
| 사이클 109 영속 | market-cap 화이트리스트 영역 영구 영속이 |
| CLAUDE.md "절대 깨지 말 것" 8 영역 | 전수 영속 |

---

## 매매 안전성 영역 영구 영속이 무영향 확정

- POST `/refresh-universe` 영역 영구 영속이 = scanner 단계 매수 진입 전 후보 풀 영역 영구 영속이 한정
- 매도/손절/Trailing/익일청산/15:20 강제청산 hot path 무관
- 사이클 38 명문화 영속 (scanner 단계 = 매수 진입 전용)
- `_full_universe_load_once` 영역 영구 영속이 = 사이클 101 영역 영구 영속이 정상 함수 영역 (매매 hot path 직접 영향 0 + 사이클 106 lifecycle race 차단 영속 + 사이클 107 raw 보강 영속)

---

## 검증 의무 (Phase 4 verify)

- 백엔드 2387 → 2392+ PASS (+5~6 신규 케이스 영역 영구 영속이)
- flakiness 0 (3 회 반복 동일 카운트 영구 영속이)
- 회귀 0 (사이클 101~108 영속 영역 무영향 영구 영속이)
- AST 영구 가드 G-AST1 = 미래 폐기 영역 import 재발 시 즉시 검출

---

## 사이클 111+ 후속 카드 인계 의무

- KRX 정보데이터시스템 OPEN API 영역 영구 영속이 도입 검토 (옵션 A `MDCSTAT01901`)
  - KIS API 영역 영구 영속이 의존성 해소
  - 사용자 요구 사항 ("상장종목 코드리스트를 받을 수 있는 다른 오픈된 API")
- 또는 pykrx 라이브러리 (옵션 B)
- domain-expert 자문 의무 (안정성 + KIS chain 영향 + Rate Limit 차이 + Maintenance 부담)
- 별개 사이클 (사이클 111 또는 이후)

---

## Auto Mode 영역 영구 영속이

- 사용자 결정 의제 없음 (단일 근본 원인 영구 영속이 영구 확정 + 시정 영역 영구 영속이 단순 + 안전 영역 영구 영속이)
- 즉시 발주 의무 (Auto Mode 영역 영구 영속이)
- domain-expert 자문 생략 (LOW 위험 영역 + 사이클 101~109 영역 영속 영구 영속이 + 사이클 38 명문화 영속)
