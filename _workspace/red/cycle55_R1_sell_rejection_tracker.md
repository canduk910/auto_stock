# 사이클 55 R-1 Red — SellRejectionTracker 단일 정책 객체

> **작성**: tdd-engineer (2026-06-03)
> **선행**: domain-expert Q1~Q5 자문 + refactor-expert 설계 카드 (`_workspace/cycle55_R1_design_card.md`)
> **위험 등급**: HIGH (매매 hot path, 4 분류 분기 통합)

## Red 산출물

1. `tests/unit/engine/test_sell_rejection_tracker.py` (신규, 18 케이스) — tracker 단위
2. `tests/unit/engine/test_b1_market_closed_zombie_block.py` (갱신, +2 신규 + 1 좁힘) — 사이클 52 호환
3. `tests/integration/test_sell_rejection_integration.py` (신규, 8 케이스) — execute_sell 위임

## Red 매트릭스 (36 케이스)

### 단위 — test_sell_rejection_tracker.py (18 FAIL)
모듈 `src.engine.sell_rejection` 부재 → 전 케이스 ModuleNotFoundError.

| ID | 분류 | 검증 |
|----|------|------|
| A1-1 | Q1 | KRX 11:00 거부 → 5분 TTL (11:05) |
| A1-2 | Q1 | NXT 08:30 거부 → 다음 09:00 TTL |
| A1-3 | Q1 | 경계 시각 4종 (08:59:59 / 09:00:00 / 15:29:59 / 15:30:00) |
| A1-4 | Q1 | KRX 5분 만료 → is_blocked=False + lazy clear |
| A2-1 | Q2 | KRX 폴백 성공 → 30초 TTL + next_day=False |
| A2-2 | Q2 | KRX 폴백 실패 → next_day=False |
| A2-3 | Q2 | NXT 폴백 실패 → **next_day=True** (Q2 핵심) |
| A2-4 | Q2 | 30초 만료 → is_blocked=False |
| A3-1 | Q3 | register_insufficient_quantity → 차단 X, history 적재 |
| A3-2 | Q3 | history event reason/occurred_at 정확성 |
| A3-3 | Q3 | ticker 격리 |
| A5-1 | Q5 | deque maxlen=20 — 21번째 push → 1번째 evict |
| A5-2 | Q5 | get_recent_rejections list 사본 반환 |
| A5-3 | Q5 | ticker 격리 |
| compat-1 | 호환 | reset_daily 4 필드 일괄 clear |
| compat-2 | 호환 | 미등록 ticker is_blocked=False |
| compat-3 | 호환 | should_emit_block_log/mark_block_logged 1회 cap |
| compat-4 | 호환 | register_market_closed → _logged_today.discard |

### 호환 — test_b1_market_closed_zombie_block.py (8 PASS + 2 FAIL)

| ID | 상태 | 의미 |
|----|------|------|
| S1/S2/S3a/S4_NXT/S5/S6/S7 | **PASS 보존** | NXT 시간대 정책 보존 + 호환 layer 위임 시 무회귀. (현재 사이클 52 구현으로 이미 PASS) |
| S3b (좁힘) | **PASS 보존** | "차단 set 미등록" 검증 제거, 폴백 호출 자체만 검증 — 사이클 55 후엔 폴백 성공 시 30초 TTL 등록되므로 |
| S3c (신규) | **FAIL** | Q2 — market_order_disallowed 폴백 후 30초 TTL 등록 (KRX 10:00 → 10:00:30) |
| S4_KRX (신규) | **FAIL** | Q1 — KRX 11:00 거부 → 5분 TTL → 11:04 차단 → 11:05:01 재진입 |

### 통합 — test_sell_rejection_integration.py (7 FAIL + 1 PASS)

| ID | 상태 | 검증 |
|----|------|------|
| C-1 | **FAIL** | 진입 게이트 위임 — tracker.is_blocked=True 시 KIS 호출 0 + INFO 1줄 |
| C-2 | **FAIL** | NXT market_closed → tracker.register + stock_master.upsert 양쪽 발화 |
| C-3 | **FAIL** | market_order_disallowed → 폴백 + tracker.register (30초 TTL 등록) |
| C-4 | **FAIL** | **Q2 핵심** — NXT 폴백 실패 → _pending_next_day_clear_provider().add(ticker) |
| C-5 | **FAIL** | **Q3** — insufficient_quantity → tracker history + [positions_reconciliation] 로그 + get_balance() 호출 |
| C-6 | **FAIL** | reset_daily_state → tracker.reset_daily 위임 체인 |
| C-7 | **FAIL** | 호환 property `is` 동일성 (engine._market_closed_blocked is tracker._blocked_until) |
| C-8 | **PASS** | 사이클 30 _completed_orders race 가드 무영향 — 회귀 가드 |

## 핵심 결정 (테스트 작성 중)

- **tdd 자율 결정**: `get_balance()` 함수명 사용 (설계 카드 D-3 의 `inquire_balance()` 표현은 실제 함수 `src/api/balance.py::get_balance` 의 별칭). Q3 reconciliation 검증은 `mock_get_balance.await_count >= 1` 로 호출 검증.
- **freezegun 함정 회피**: `@freeze_time("2026-06-03 11:00:00", tz_offset=-9)` + `datetime.now(KST_TZ)` 패턴 — 사이클 52/54 선례 답습 (현 시각이 정확히 11:00 KST 가 되도록).
- **S3b 좁힘 vs S3c 신규 분리**: 사이클 52 가드 S3b 의 `_market_closed_blocked` 미등록 검증은 사이클 55 후엔 30초 TTL 등록으로 깨짐. 좁힘으로 PASS 보존 + S3c 가 신규 행위 검증 분리.
- **호환 property `is` 동일성** (C-7): 사이클 48 stale_tracker S-6 패턴 답습. tracker._blocked_until 을 그대로 노출 (wrapping 금지) — 외부 코드의 `.add()/.discard()` 직접 호출 보존.

## Green 인터페이스 메모 (backend-dev)

### 1) `src/engine/sell_rejection.py` 신규 (130~170L)
설계 카드 §1.2 그대로:
- `RejectionEvent` (frozen dataclass) / `RejectionResult` (frozen dataclass)
- `SellRejectionTracker` dataclass — 4 필드 (`_blocked_until` / `_blocked_reason` / `_logged_today` / `_history`)
- 메서드: `is_blocked` / `should_emit_block_log` / `mark_block_logged` / `register_market_closed` / `register_market_order_disallowed` / `register_insufficient_quantity` / `record_rejection` / `get_recent_rejections` / `reset_daily` / `_append_history`
- 모듈 함수: `_compute_next_market_open_kst` (사이클 52 헬퍼 재이주) / `is_krx_main_hours` / `is_nxt_session_hours`

### 2) `src/engine/order_engine.py` 변경
- `__init__`: 3 필드 (`_market_closed_blocked` / `_market_closed_blocked_logged_today`) → `self._sell_rejection = SellRejectionTracker()` 단일 필드. `_nxt_downgrade_logged_today` 유지 (R-1 범위 밖).
- 호환 property 2개 추가 (`_market_closed_blocked` / `_market_closed_blocked_logged_today`) — 사이클 48 stale_tracker S-4 답습.
- `execute_sell` 진입 게이트 (line 481~499): tracker.is_blocked 위임 11줄 치환. 로그 prefix `[market_closed_blocked]` 유지 (설계 카드 D-1 추천 — 운영 grep 호환).
- `execute_sell` market_closed 분기 (line 577~629): `_market_closed_blocked[ticker] = _compute_next_market_open_kst(...)` 2줄 → `self._sell_rejection.register_market_closed(ticker, _now_kst, in_krx_main_hours=is_krx_main_hours(_now_kst))` 1줄. stock_master 사후 보강 보존.
- `execute_sell` market_order_disallowed 분기 (line 643~713): 폴백 결과 직후 `result = self._sell_rejection.register_market_order_disallowed(ticker, _now_kst, is_nxt_session=is_nxt_session_hours(_now_kst), fallback_succeeded=<bool>)` 호출. `result.next_day_clear_required=True` 시 `self._pending_next_day_clear_provider().add(ticker)`.
- `execute_sell` insufficient_quantity 분기 (line 631~637): `self._sell_rejection.register_insufficient_quantity(ticker, _now_kst)` 1줄 추가. 루프 외 positions 정리 직후 (line 729~743) `get_balance()` 호출 + `[positions_reconciliation]` INFO 1줄 추가 (Q3).
- `reset_daily_state` (line 1046~1054): 3 줄 clear → `self._sell_rejection.reset_daily()` 1줄 + `self._nxt_downgrade_logged_today.clear()` (사이클 54 유지).

### 3) 회귀 가드 - 절대 깨지면 안 되는 항목
- 사이클 30 `_completed_orders` race 가드 (C-8 PASS) — 무관 영역
- 사이클 32 stock_master 사후 보강 (C-2 검증) — execute_sell 잔존
- 주문번호 매핑 동기 영역 (place_order 응답 직후) — 무관
- `_pending_next_day_clear_provider` 주입 패턴 (사이클 15-A 답습) — Q2 신규 활용

## 실행 결과 (Red 확인)

```
$ python -m pytest tests/unit/engine/test_sell_rejection_tracker.py \
                    tests/unit/engine/test_b1_market_closed_zombie_block.py \
                    tests/integration/test_sell_rejection_integration.py -v

36 collected → 27 failed + 9 passed
```

Green 후 기대: 36 PASS / 0 FAIL.

## 다음 액션 (backend-dev Green)

1. `src/engine/sell_rejection.py` 신규 작성 (설계 카드 §1.2 코드 거의 그대로)
2. `src/engine/order_engine.py` 위임 치환 (위 §2)
3. `python -m pytest tests/unit/engine/test_sell_rejection_tracker.py tests/unit/engine/test_b1_market_closed_zombie_block.py tests/integration/test_sell_rejection_integration.py -v` → 36 PASS 확인
4. 백엔드 전체 회귀 `python -m pytest -q` → 1776+24=1800 안팎 PASS 기대
