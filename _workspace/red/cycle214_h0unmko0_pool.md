# cycle214 — H0UNMKO0 후보 구독 풀 분산 + cap 20→60

**명세 출처**: 사이클 214 지시 + domain 자문 `_workspace/domain_consult/cycle214_h0unmko0_cap.md` (판정 (b))
**행위**: `scheduler._subscribe_market_operation_tickers` 의 LOW 후보 H0UNMKO0 구독을 메인 세션 단독(`kis_ws.subscribe`)에서 풀 분산(`kis_ws_pool.subscribe(priority="LOW")`)으로 전환 + cap 기본값 20→60. HIGH(보유/익일청산)는 메인 직접 `bypass_limit=True` 유지(cycle 32 R4 절대 보호). 체결통보 메인 단일 강제(`_EXECUTION_NOTICE_TR_IDS`) 불변.

## 배경
유니버스 확대(203/204/208/211)로 H0UNMKO0 후보 구독이 메인 41-cap 초과 드롭(119건). domain 판정 = 후보 LOW 를 메인 단독→풀 분산(보조 205 슬롯 활용). cycle 149 "보조 세션 절대 금지"는 반증(H0UNMKO0=실시간시세 quote류, `_EXECUTION_NOTICE_TR_IDS`={H0STCNI0/H0STCNI9}만 보조 차단). LOW cap 20→60.

## Red (production 미변경 상태에서 FAIL 이어야 하는 케이스)

### 행위 (`tests/unit/engine/test_cycle214_h0unmko0_pool.py`)
- **G-214-1 (HIGH, cycle 32 R4)**: HIGH(보유+익일청산) H0UNMKO0 는 `kis_ws.subscribe(bypass_limit=True)` 메인 직접 유지(풀 미경유). → 현재도 PASS(불변식, 회귀 가드).
- **G-214-2 (HIGH, 행위)**: LOW 후보 H0UNMKO0 는 `kis_ws_pool.subscribe(MARKET_OP_TR_ID, ticker, priority="LOW")` 경유. 현재 `kis_ws.subscribe(..., bypass_limit=False)` → FAIL.
- **G-214-4**: `_subscribe_market_operation_tickers` cap 기본값 == 60. 현재 20 → FAIL.
- **불변식 보조 0개 fallback**: pool.subscribe 가 보조 0개 시 메인 fallback(회귀 0) — pool 경유 자체만 단언.

### AST/SAFETY (`tests/unit/ast/test_cycle214_ast_h0unmko0_pool.py`)
- **G-214-3 (SAFETY)**: `websocket_pool._EXECUTION_NOTICE_TR_IDS == {"H0STCNI0","H0STCNI9"}` 불변(H0UNMKO0 미포함). → PASS(회귀 가드).
- **G-214-5 (AST/SAFETY)**: `_subscribe_market_operation_tickers` LOW 루프에 `kis_ws_pool` 사용 + HIGH 루프 `kis_ws`(메인) 유지. 현재 LOW 도 `kis_ws` → FAIL.
- **매매 안전성 8영역 diff 0**: 변경은 scheduler.py(8영역 밖) + realtime/ 미변경.

## Green (backend-dev — `scheduler.py::_subscribe_market_operation_tickers` L3398)
1. LOW 후보 루프: `kis_ws.subscribe(MARKET_OP_TR_ID, ticker, bypass_limit=False)` → `kis_ws_pool.subscribe(MARKET_OP_TR_ID, ticker, priority="LOW")`. `from src.realtime.websocket import kis_ws_pool` import 추가.
2. HIGH 루프 변경 0.
3. cap 기본값 20→60.
4. docstring "보조 세션 절대 금지" → "LOW 풀 분산(사이클 214)".

## Refactor
- 영향 인덱스 재생성 예정.
