# Cycle 102 Red 명세 — 영역 2: 외부 의견 가시화 신규

**명세 출처**: `_workspace/cycle102_phase2_design.md` §영역 2 + `_workspace/cycle102_domain_consult.md` §A2/§A3
**위급도**: HIGH — 사이클 88 G-REJECT-1/2/3 영구 영속 + 보조 가시화 3 영역 신규
**행위**: (2-A) `_last_ws_message_at` 세션별 update + (2-B) `_silent_drop_count` ticker별 누적 + 5분 emit + (2-C) 3 콜백 일관 `try/except` + `[callback_exception]` + **raise 영속** (사이클 88 G-REJECT-1 재연결 trigger 영속)

## 사용자 결정 (영속)

- **Q72=F+가시화**: `last_ws_message_at` (보조 가시화) + dispatch + callback 3 영역 통합
- **사이클 88 G-REJECT-1/2/3 영구 영속 의무**: 책임 분리 영속 (종목별 `ticker_last_tick` 판정 vs 세션별 `_last_ws_message_at` 보조 가시화)

## 결정적 발견 (domain-consult §A2/§A3)

- **세션별 가시화 부재**: `[ws_heartbeat]` 5분 PINGPONG 통계 영속이나 *마지막 메시지 시각 단독 추적 = 부재*
- **dispatch 누락 silent drop**: `handler.py::_handle_tick` `if len(fields) < 10: return` graceful → 운영 가시화 0
- **callback 예외 일관 패턴 부재**: 현재 `_on_tick` await 시 `_receive_loop` 정지 + 재연결 trigger (사이클 88 G-REJECT-1 핵심) — try/except 보강 + `raise` 영속 의무

## Production 영역 (Green 단계 backend-dev 인계)

### 2-A `src/realtime/websocket.py`

- `KisWebSocket.__init__` (L99 영역) 인스턴스 변수 신규: `self._last_ws_message_at: dict[str, datetime] = {}` (label → 마지막 메시지 KST datetime)
- `_handle_raw` (L601 영역) 진입 시 update: `self._last_ws_message_at[self.label] = datetime.now(KST_TZ)` (사이클 68 KST 일관성 영속)
- 사이클 16 `_aes_iv` 인스턴스 변수 패턴 답습 (`__init__` + `_handle_raw` 양쪽 영역 분리)

### 2-B `src/realtime/handler.py`

```python
# 모듈 전역 (사이클 88 G-REJECT-2 종목별 영속 답습)
_silent_drop_count: dict[str, int] = {}

async def _handle_tick(payload: str) -> None:
    fields = payload.split("^")
    if len(fields) < 10:
        ticker = fields[0] if len(fields) >= 1 else "_unknown"
        _silent_drop_count[ticker] = _silent_drop_count.get(ticker, 0) + 1
        return

    ticker = fields[0]
    parsed = _parse_tick_prices(fields)
    if parsed is None:
        _silent_drop_count[ticker] = _silent_drop_count.get(ticker, 0) + 1
        logger.debug("실시간 체결가 파싱 실패: payload=%s", payload[:140])
        return
    # ...영속...

def flush_silent_drop_count() -> None:
    """5분 주기 collector flush — [dispatch_drop_summary] 1행 emit (사이클 74 답습)."""
    global _silent_drop_count
    if not _silent_drop_count:
        return
    drops_total = sum(_silent_drop_count.values())
    by_ticker = dict(_silent_drop_count)
    logger.info(
        "[dispatch_drop_summary] window=300s drops_total=%d by_ticker=%s",
        drops_total, by_ticker,
    )
    _silent_drop_count.clear()
```

`scheduler._api_recovered_collector_loop` 영역에 `from src.realtime.handler import flush_silent_drop_count` import + try/except 호출 추가 (사이클 78 패턴 답습).

### 2-C `src/realtime/handler.py` — 3 콜백 일관 try/except

```python
async def _handle_tick(payload: str) -> None:
    # ... 파싱 영속 ...
    if _on_tick:
        try:
            await _on_tick(ticker, current_price, open_price, change_rate)
        except Exception:
            logger.exception(
                "[callback_exception] handler=_on_tick ticker=%s", ticker,
            )
            raise  # 재연결 trigger 영속 (사이클 88 G-REJECT-1 영속)

async def _handle_execution(payload: str, *, encrypted: bool = False) -> None:
    # ... 파싱 영속 ...
    if _on_execution:
        try:
            await _on_execution(ticker, order_no, side, price, quantity)
        except Exception:
            logger.exception(
                "[callback_exception] handler=_on_execution ticker=%s order_no=%s",
                ticker, order_no,
            )
            raise

async def _handle_market_op(tr_id: str, tr_key: str, payload: str) -> None:
    # ... 파싱 영속 ...
    if _on_board:
        try:
            await _on_board(tr_key, mkop_cls_code, payload)
        except Exception:
            logger.exception(
                "[callback_exception] handler=_on_board tr_id=%s tr_key=%s",
                tr_id, tr_key,
            )
            raise
```

## Red 케이스 7 (HIGH 5 + MEDIUM 2)

| 가드 | 위급도 | 파일 | 영역 |
|------|------|------|------|
| **G-WS-MSG1** | HIGH | `tests/unit/realtime/test_cycle102_last_ws_message_at.py` | `_handle_raw` 진입 시 `_last_ws_message_at[label]` KST datetime update 영속 |
| **G-WS-MSG2** | MEDIUM | `tests/unit/realtime/test_cycle102_last_ws_message_at.py` | `KisWebSocket.__init__` 영역 `_last_ws_message_at: dict[str, datetime]` 초기 = {} (인스턴스 격리) |
| **G-DISPATCH1** | HIGH | `tests/unit/realtime/test_cycle102_dispatch_drop.py` | `_handle_tick(payload)` `len(fields) < 10` 또는 `parsed is None` 진입 시 `_silent_drop_count[ticker]` +1 영속 |
| **G-DISPATCH2** | MEDIUM | `tests/unit/realtime/test_cycle102_dispatch_drop.py` | `flush_silent_drop_count()` 호출 → `[dispatch_drop_summary] window=300s drops_total=N by_ticker={...}` 1행 emit + collector clear |
| **G-DISPATCH3** | HIGH | `tests/unit/realtime/test_cycle102_dispatch_drop.py` | `flush_silent_drop_count` 함수 존재 + empty collector 진입 시 emit 0 (no-op) + `import` 가능 (scheduler 사용처) |
| **G-CALLBACK1** | HIGH | `tests/unit/realtime/test_cycle102_callback_exception.py` | `_on_tick` 예외 발생 시 `_handle_tick` 가 `[callback_exception] handler=_on_tick` ERROR + **raise 영속** (사이클 88 G-REJECT-1 재연결 trigger) |
| **G-CALLBACK2** | HIGH | `tests/unit/ast/test_cycle102_ast_callback_exception.py` | 3 콜백 (`_on_tick` / `_on_execution` / `_on_board`) 모두 `try/except` + `logger.exception` + `raise` 일관 패턴 AST 정적 검증 |

## Red 검증 명령

```bash
python -m pytest -x \
  tests/unit/realtime/test_cycle102_last_ws_message_at.py \
  tests/unit/realtime/test_cycle102_dispatch_drop.py \
  tests/unit/realtime/test_cycle102_callback_exception.py \
  tests/unit/ast/test_cycle102_ast_callback_exception.py -v
# Red 단계 = production 영역 부재 → 7 케이스 모두 FAIL 영역 (의도 영역)
# Green 단계 backend-dev 시정 후 7 PASS 영역 전환
```

## 영속 의무 매트릭스 (HIGH)

- **사이클 88 G-REJECT-1 영구 영속**: 단일 restore 도입 차단 = `raise` 영속 영역 = 재연결 trigger 영속 보장
- **사이클 88 G-REJECT-2 영구 영속**: 종목별 `ticker_last_tick` 14 사이트 영속 + 세션별 `_last_ws_message_at` 보조 가시화 책임 분리
- **사이클 88 G-REJECT-3 영구 영속**: 4 dict 분리 영속 (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`)
- 사이클 16 AES 키 격리 영속 (`_aes_iv` 인스턴스 변수 영역 패턴 답습)
- 사이클 68 KST 일관성 영속 (`datetime.now(KST_TZ)` 사용)
- 사이클 74 collector 패턴 답습 (5분 윈도우 emit + clear)
- 사이클 78 patterns 답습 (scheduler `_api_recovered_collector_loop` 추가)
- 4중 안전망 영속 (F1 + scan_loop + K + priority)

## Green 인계 (backend-dev)

- `src/realtime/websocket.py`: `__init__` + `_handle_raw` 2 영역
- `src/realtime/handler.py`: 모듈 전역 + `_handle_tick` + `_handle_execution` + `_handle_market_op` + `flush_silent_drop_count` 5 영역
- `src/engine/scheduler.py::_api_recovered_collector_loop`: import + try/except flush 1 영역

## Refactor

- 영역 2 = collector 패턴 사이클 74/78 답습 (shared 헬퍼 추출 영역은 사이클 76+ 카드 #20 인계 영속)
- 영향 인덱스 갱신: `python tools/test_impact/build_index.py`
