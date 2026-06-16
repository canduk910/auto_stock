# 사이클 149 Red 명세 — 종목별 H0UNMKO0 구독 확장 + VI/거래정지 stale 회피

## 행위 분해

### 행위 1 (영역 A) — MARKET_OP_TR_ID 상수 + MarketOpEvent dataclass + parser

- `src/api/market_operation.py` 신규
- `MARKET_OP_TR_ID = "H0UNMKO0"` 상수
- `MarketOpEvent` dataclass: ticker / trht_yn / vi_cls_code / ovtm_vi_cls_code / iscd_stat_cls_code / mkop_cls_code / received_at (KST datetime)
- `parse_market_op_payload(tr_key: str, payload: str) -> MarketOpEvent` — handler.py 의 `^` 구분 10 컬럼 파싱
- `is_event_blocking(event) -> bool` — VI 활성 / 거래정지 / 종목상태 이상 통합 판정 ("0"/"" = 비활성 블랙리스트, 자문 의제 1)
- `inquire_vi_status_today() -> set[str]` — REST FHPST01390000 호출 + `vi_cls_code != "0"` ticker set 반환 + graceful (자문 의제 4)

### 행위 2 (영역 B) — market_operation_monitor 모듈 (state + hook)

- `src/engine/market_operation_monitor.py` 신규
- 모듈 전역 dict: `_vi_active_tickers: set[str]` + `_halt_active_tickers: set[str]` + `_market_op_last_event: dict[str, MarketOpEvent]` (자문 의제 5 — VI/거래정지/종목상태 통합 set 2 + 마지막 이벤트 dict 1)
- 사이클 88 G-REJECT-3 영속 = 4 dict (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`) + 사이클 135 `_subscribed_at` 5 dict → **사이클 149 신규 3 dict 추가 → 8 dict 분리 영속**
- 헬퍼:
  - `record_market_op_event(event: MarketOpEvent) -> None` — 이벤트 누적 + VI/거래정지 활성 시 set add / 비활성 시 set discard
  - `is_ticker_stale_excluded(ticker: str) -> bool` — VI ∪ 거래정지 활성 ticker 면 True (stale 회피 hook)
  - `get_market_op_active_tickers() -> set[str]` — VI ∪ 거래정지 합집합 (subscribe_market_operation_tickers 용)
  - `seed_vi_active_from_rest(tickers: set[str]) -> None` — 부팅 시 REST 폴백 (자문 의제 4)
  - `reset_market_op_state() -> None` — `_reset_daily_state` 동행 clear (자문 의제 5)
  - `get_market_op_state_summary() -> dict` — 진단 응답용

### 행위 3 (영역 C) — scheduler H0UNMKO0 종목별 구독 확장

- `src/engine/scheduler.py::_subscribe_market_operation_tickers(tickers: Iterable[str], *, high_tickers: set[str]) -> int` 신규
- HIGH (보유/익일청산) → `bypass_limit=True` 강제 (자문 의제 3)
- LOW (전략 후보) → cap=20 (자문 의제 3) + sorted 결정적 순서
- 메인 세션 단일 구독 (`kis_ws.subscribe(MARKET_OP_TR_ID, ticker)` — 보조 세션 절대 금지, 자문 의제 2)
- 기존 005930 대표 구독 영역 보존 (시장 단위 신호 영속)
- 5분 `_scan_loop` 끝에 `_subscribe_market_operation_tickers` delta 호출 (포지션 변경 반영)

### 행위 4 (영역 D) — handler `_handle_market_op` parser 연동

- `handler.py::_handle_market_op` 본체 = 기존 `_on_board` 콜백 영역 보존 + `parse_market_op_payload` 호출 + `market_operation_monitor.record_market_op_event(event)` 추가
- 콜백 분기 + record_market_op_event 분기 try/except 4중 (사이클 102 G-REJECT-1 영속)

### 행위 5 (영역 E) — stale_watcher_core VI/halt 회피 hook

- `src/engine/stale_watcher_core.py::check_and_resubscribe_stale` 영역 stale_tickers 추출 후 `is_ticker_stale_excluded(t)` 추가 필터 (`_is_within_grace` 패턴 답습, 사이클 135)
- `_resubscribe_stale_priority` 영역도 동일 필터 추가
- 회피 시 `[stale_skip_market_op] ticker=... reason=vi_active|halt_active` INFO emit (운영 가시화)

### 행위 6 (영역 F) — _reset_daily_state 동행 reset

- `scheduler.py::_reset_daily_state()` 끝에 `market_operation_monitor.reset_market_op_state()` 호출
- 사이클 88 G-REJECT 영속 답습 (모든 dict 일일 0 초기화 의무)

## 회귀 가드 (16 케이스 추정)

### `tests/unit/api/test_cycle149_market_operation.py` (2 케이스 MEDIUM 1)
- G-A1 (MEDIUM): MARKET_OP_TR_ID == "H0UNMKO0" + parse_market_op_payload 10 컬럼 정확 추출
- G-A2 (MEDIUM): is_event_blocking "0"/""/None 비활성 + "1"/"Y" 활성 (자문 의제 1 truthy 매핑)

### `tests/unit/engine/test_cycle149_market_operation_monitor.py` (11 케이스 HIGH 6)
- G-B1 (HIGH): record_market_op_event VI 활성 → `_vi_active_tickers` add
- G-B2 (HIGH): record_market_op_event VI 해제 → discard
- G-B3 (HIGH): record_market_op_event 거래정지 활성 → `_halt_active_tickers` add
- G-B4 (HIGH): record_market_op_event 거래정지 해제 → discard
- G-B5 (HIGH): is_ticker_stale_excluded VI 활성 ticker → True
- G-B6 (HIGH): is_ticker_stale_excluded 거래정지 활성 ticker → True
- G-B7 (MEDIUM): is_ticker_stale_excluded 비활성 ticker → False
- G-B8 (MEDIUM): get_market_op_active_tickers VI ∪ 거래정지 합집합 정확
- G-B9 (MEDIUM): seed_vi_active_from_rest 부팅 폴백 시드
- G-B10 (MEDIUM): reset_market_op_state 3 dict 일괄 clear
- G-B11 (MEDIUM): _market_op_last_event dict 마지막 이벤트 보존

### `tests/unit/realtime/test_cycle149_handler_market_op.py` (2 케이스 HIGH 2)
- G-D1 (HIGH): _handle_market_op 호출 시 record_market_op_event 호출 발화 (parse 정합)
- G-D2 (HIGH): _on_board 콜백 + record_market_op_event 양쪽 호출 (try/except 4중 영속)

### `tests/unit/ast/test_cycle149_ast_dict_separation.py` (1 케이스 HIGH AST)
- G-AST1 (HIGH): market_operation_monitor.py 모듈 전역 3 dict (`_vi_active_tickers` + `_halt_active_tickers` + `_market_op_last_event`) 영구 분리 영속 (사이클 88 G-REJECT-3 4→5→8 dict 분리 영속 답습)

## 영속 의무

- 사이클 17 OPSP0002 backoff 변경 0 (300s)
- 사이클 26 H0UNMKO0 메인 단일 영속 (005930 대표 구독 보존 + 종목별 추가)
- 사이클 29 005935 사고 영역 변경 0 (HIGH 절대 보장)
- 사이클 32 R4 universe guard 영속 (보유/익일청산 절대 보호)
- 사이클 38 명문화 영속 (매수 진입 전 한정, hot path 무관)
- 사이클 88 G-REJECT-1/2/3 영속 (callback raise + ticker_last_tick ↔ _last_ws_message_at 분리 + dict 분리)
- 사이클 102 force_retry 임계 변경 0 (600s/6회)
- 사이클 135 grace period 변경 0 (180s)
- WebSocket 4중 안전망 영속

## 매매 안전성 무영향

- stale 회피 = stale 판정 *지연*만 (재구독 발화 차단)
- check_exit_signal 영역 = 사이클 38 명문화 영속 = 항상 발화
- risk.on_tick / order_engine / auth 변경 0
- 메인 WebSocket 단일 (보조 세션 변경 0)
