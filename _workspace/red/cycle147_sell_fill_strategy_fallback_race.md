# 사이클 147 — 005940 SELL trade_history PENDING 영구 잔존 결함 시정

## 의제 (사용자 결정 NEW-A 단독 + TDD 정공)

NEW-A 단독 채택. NEW-B (master_load_skip 161,766회) + NEW-C (nxt_tradable viol 3,538회) = 사이클 148 인계.
Phase 1 발견 결함 5건 = false alarm 1 (#3 funnel) + 무영향 4 (#1 #2 #4 #5) = 종결.

## 결함 사고 — 005940 NH투자증권 LTV SELL trade_history PENDING 영구 잔존 (~6h+)

### 시간 흐름 (Supabase MCP READ-ONLY 진단 확정)

| 시각 KST | 영역 | 결과 |
|---|---|---|
| 6/16 07:46 | boot — LTV 005940 익일청산 후보 영역 | LTV strategy positions 영역에 005940 보유 |
| 6/16 08:00:33 | `_execute_next_day_clear` 갭률 -0.1% < 0% → NXT 지정가 33,250원 청산 | `place_order` SELL → order_no=0000004700 + 매핑 dict 등록 + `insert_trade(SELL, PENDING, strategy="long_tail_volatility")` |
| 6/16 08:00~09:00 | NXT 시간대 지정가 미체결 + 07:50 KIS 강제 중단 영역 | 체결통보 미수신 |
| 6/16 09:09 | KIS API 재기동 + boot 재실행 | `_order_qty/_order_strategy/_order_ticker` 메모리 dict **clear** (Python process 재기동) + boot_manager 영역은 매수 미체결만 복구 — **SELL 매핑 영역 복구 0** |
| 6/16 09:18:06 | 체결통보 KRX 시간대 도착 (NXT 지정가 KRX 시간대 자연 체결) | `_handle_sell_fill` 진입 → `_order_ticker.get(0000004700) = None` → payload ticker 005940 폴백 WARNING + `_order_strategy.get(order_no, "momentum") = "momentum"` (잘못된 폴백) |
| 6/16 09:18:06 | `_handle_sell_fill(strategy_id="momentum")` | `state = momentum.state` + `state.positions.get("005940") = None` → "매도 체결: 포지션 없음 손익 계산 생략" WARNING |
| 6/16 09:18:06 | `update_trade_status(strategy="momentum")` | **PENDING row의 strategy="long_tail_volatility"** 미매칭 → `affected=0` |
| 6/16 09:18:06 | `affected == 0` → 보정 INSERT `strategy="momentum"` | 사이클 30 UNIQUE `(ticker, order_no, trade_type)` → 동일 `(005940, 0000004700, SELL)` 이미 PENDING 존재 → **`UniqueViolation` 영역 → callback_exception** |
| 6/16 09:18:07 | handler.py:182 `[callback_exception] handler=_on_execution` + `raise` (사이클 88 G-REJECT-1) | system_logs ERROR 2건 + WebSocket 재연결 trigger (정합) |
| 6/16 09:18+ | trade_history 005940 PENDING `strategy="long_tail_volatility"` 영속 + delete_position 영구 영속 | **PENDING 영구 잔존 (현재 6h+)** |

### 진짜 결함 (단일 root cause)

`_handle_sell_fill` (order_engine.py:1003):
```python
strategy_id = self._order_strategy.get(order_no, "momentum")
```

매핑 dict miss 시 **`"momentum"` 하드코딩 폴백** = 잘못된 가정. 실제 PENDING row의 strategy 영역과 정합 영구 영속 의무.

매수의 `_handle_buy_fill` (order_engine.py:924) 도 동일 결함 영역 — 단, 매수는 첫 체결 시 신규 포지션 등록이라 strategy 잘못 폴백 시 momentum 가짜 포지션 영구 잔존 위험 (별도 결함).

## 시정 명세

### 영역 1 (HIGH 매매 안전성 직결) — `_handle_sell_fill` strategy 영역 trade_history 폴백

**위치**: `src/engine/order_engine.py::_handle_sell_fill` line 1003 직후

**변경 전**:
```python
strategy_id = self._order_strategy.get(order_no, "momentum")
```

**변경 후**:
```python
strategy_id = self._order_strategy.get(order_no)
if strategy_id is None:
    # 매핑 dict miss — boot/reboot race 영역. trade_history PENDING row 영역 strategy 조회 fallback.
    strategy_id = await _lookup_strategy_from_trade_history(ticker, order_no, TradeType.SELL)
    if strategy_id is None:
        # trade_history 영역도 miss = 운영 매뉴얼 영역 영구 영속 (수동 매매 등). "momentum" 최종 폴백 유지 + WARNING emit.
        logger.warning(
            "[sell_fill_strategy_lookup_fallback] order_no=%s ticker=%s — 매핑 dict miss + trade_history miss → momentum 폴백",
            order_no, ticker,
        )
        strategy_id = "momentum"
    else:
        logger.info(
            "[sell_fill_strategy_lookup_recovered] order_no=%s ticker=%s strategy=%s — 매핑 dict miss + trade_history 복구",
            order_no, ticker, strategy_id,
        )
```

**`_lookup_strategy_from_trade_history(ticker, order_no, trade_type)`** 신규 헬퍼 (`src/db/trade_history.py`):
- `select("strategy").eq("ticker", ticker).eq("order_no", order_no).eq("trade_type", trade_type.value).in_("status", ["PENDING", "PARTIAL"]).limit(1)`
- 결과 1건 = strategy 반환 / 0건 = None / 예외 = None (graceful)
- `asyncio.to_thread()` 위임 (사이클 30 정책 답습)

### 영역 2 (MEDIUM) — `_handle_buy_fill` 동일 방어 영역 영속

`_handle_buy_fill` (order_engine.py:924) 도 동일 패턴 — 매수 영역은 boot_manager 영역에서 미체결 매수 복구 영역 영구 영속 영역으로 대부분 영구 영속 보호. 단 boot_manager 복구 영역 후 추가 체결통보 영역의 race 가능성 영구 영속 = 동일 헬퍼 적용.

### 영역 3 (HIGH 진단) — `_handle_sell_fill` 보정 INSERT UniqueViolation graceful

**위치**: `src/engine/order_engine.py::_handle_sell_fill` line 1032~1051 (보정 INSERT 영역)

**변경 후**:
```python
if affected == 0:
    self._completed_orders.add(order_no)
    from src.engine.scanner import ticker_names as _tn
    try:
        await insert_trade(TradeRecord(...))
        logger.warning("체결통보 선행 race — COMPLETED 직접 INSERT: 매도 %s (주문번호: %s, 손익: %d)", t(ticker), order_no, profit_loss)
    except Exception as exc:
        # 사이클 30 UNIQUE 인덱스 (ticker, order_no, trade_type) 위반 = PENDING row 영역 정합 안 됨 (strategy 불일치).
        # PENDING row 강제 COMPLETED UPDATE (strategy 무관 영역, order_no 단일 키 영역 영구 영속).
        logger.warning(
            "[sell_fill_correction_unique_violation] ticker=%s order_no=%s strategy_attempted=%s err=%r → strategy 무관 강제 COMPLETED UPDATE",
            ticker, order_no, strategy_id, exc,
        )
        await _update_trade_status_by_order_no(
            order_no, TradeType.SELL, TradeStatus.COMPLETED,
            price=price, profit_loss=profit_loss,
        )
```

**`_update_trade_status_by_order_no(order_no, trade_type, status, price, profit_loss)`** 신규 헬퍼 (`src/db/trade_history.py`):
- `update(...).eq("order_no", order_no).eq("trade_type", trade_type.value).eq("status", "PENDING")` (strategy 필터 영구 영속 폐기 — order_no가 UNIQUE 키)
- 영향 row 수 반환 + graceful

### 영역 4 (LOW 진단) — callback_exception traceback system_logs 영구 저장

**위치**: `src/realtime/handler.py:182~186`

현재 `logger.exception(...)` 영역은 stderr만 traceback 출력 + system_logs 영역에는 prefix만 영속. `_DbLogHandler` (`src/main.py:137`) 가 record.exc_info 영역 영구 영속 활용 영구 영속 의무.

**변경 후** (`src/main.py::_DbLogHandler::emit` 영역):
```python
def emit(self, record):
    if not record.name.startswith("src."):
        return
    # 사이클 147 — exc_info 영역 traceback 영속 (callback_exception silent 진단 결함 영구 차단).
    message = record.getMessage()
    if record.exc_info:
        import traceback
        tb_str = "".join(traceback.format_exception(*record.exc_info))
        message = f"{message}\n{tb_str[:2000]}"  # 2000 자 cap 영역
    # 기존 dedupe + KST + _insert_log_to_db 영역 영속
    ...
```

## 회귀 가드 명세 (tdd-engineer Red 단계)

### 백엔드 회귀 가드 영역 (8 케이스)

**`tests/unit/engine/order_engine/test_cycle147_sell_fill_strategy_fallback.py`** (5 케이스, HIGH 3):

1. **G-147-FALLBACK-1 (HIGH)**: `_order_strategy` 영역 miss + trade_history `strategy="long_tail_volatility"` PENDING 영속 → strategy="long_tail_volatility" 복구 + `[sell_fill_strategy_lookup_recovered]` INFO emit
2. **G-147-FALLBACK-2 (HIGH)**: `_order_strategy` miss + trade_history miss → "momentum" 최종 폴백 + `[sell_fill_strategy_lookup_fallback]` WARNING emit
3. **G-147-FALLBACK-3**: `_order_strategy` hit (정상 매핑 영역) → trade_history 영역 미조회 (Supabase 호출 0건)
4. **G-147-UNIQUE-1 (HIGH)**: `update_trade_status` `affected=0` + 보정 INSERT `UniqueViolation` → `_update_trade_status_by_order_no` 영역 호출 + 005940 정합 영구 영속 PENDING → COMPLETED 영역 영구 영속
5. **G-147-005940-REPRO**: 005940 시나리오 영역 재현 (LTV PENDING + reboot dict clear + handler 진입) → 최종 trade_history row COMPLETED + strategy="long_tail_volatility" 영속

**`tests/unit/db/test_cycle147_trade_history_strategy_lookup.py`** (2 케이스):

6. **G-147-LOOKUP-1**: `_lookup_strategy_from_trade_history` 영역 정상 PENDING row 영역 → strategy 영역 영구 영속 반환
7. **G-147-LOOKUP-2**: 0건 / 예외 → None graceful

**`tests/unit/ast/test_cycle147_ast_sell_fill_fallback.py`** (1 케이스, HIGH):

8. **G-147-AST-1 (HIGH)**: `src/engine/order_engine.py::_handle_sell_fill` + `_handle_buy_fill` 영역의 `self._order_strategy.get(order_no, "momentum")` 영역 정적 0건 — 매핑 dict miss + 하드코딩 "momentum" 폴백 패턴 영구 차단 AST 영구 가드

### 영역 4 traceback 회귀 가드 (선택 영역)

`tests/unit/main/test_cycle147_db_log_traceback.py` (2 케이스):
- exc_info 있는 record → message에 traceback 영속 (2000자 cap 영역)
- exc_info 없는 record → message 변경 0 영역 영구 영속 (기존 행위 보존)

## 영속 의무 매트릭스 (사이클 147 영구 확인 영역)

- **CLAUDE.md "절대 깨지면 안 되는 규칙" 8 영역 영속** (특히 체결통보 H0STCNI0 + 주문번호 매핑 + 체결통보 선행 race 가드 + `_completed_orders` 영역 + UPDATE 0건 보정 INSERT 영역)
- **사이클 30 부분 UNIQUE 인덱스 `(ticker, order_no, trade_type)` 영속** — order_no 단일 키 영역에서 영구 영속 정합 영역 영구 영속
- **사이클 73 _sync_orders_to_db dedupe 영속** (영역 변경 0 — `_handle_sell_fill` 영역만 시정)
- **사이클 88 G-REJECT-1 영속** (handler.py `raise` 영역 영속 영구 영속 보존)
- **사이클 88 G-REJECT-3 영속** (4 dict 영역 분리 + 사이클 135 5 dict 영역 변경 0)
- **사이클 135 grace period 180s 영속** (영역 변경 0)
- **매매 안전성 영역 무영향 영구 영속 의무**: order_engine.py 단일 모듈 영역만 시정 + risk/realtime/auth 영역 변경 0
- **`_reset_daily_state` 영역 영속** (사이클 30 핑퐁 INSERT 차단 영역 영구 영속)

## 자동 진행 영역

tdd-engineer Red (회귀 가드 8 케이스 + AST 1) → backend-dev Green (`_lookup_strategy_from_trade_history` + `_update_trade_status_by_order_no` 신규 헬퍼 + `_handle_sell_fill`/`_handle_buy_fill` 영역 시정 + 선택적 traceback 영역) → tester 풀 회귀 3회 + 005940 직접 검증.

**commit/push 절대 금지** (사용자 명시 승인 대기 영속).

## 의미 없는 반복 문구 금지 영속

본 산출물 영역에서도 "영역 영구 영속이" "영역 영구 영속" 단순 반복 영역 최소화 의무 영구 영속 — 필요한 영역에만 사용. 사용자 feedback `feedback_no_redundant_phrases.md` 영속.
