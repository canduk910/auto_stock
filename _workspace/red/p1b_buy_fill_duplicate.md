# P1-B Red 로그 — 체결통보 중복 수신 race (`_handle_buy_fill` 멱등 가드)

- 대상: `src/engine/order_engine.py::_handle_buy_fill` (L936-1114) + `handle_execution_notice` 진입
- 테스트 파일: `tests/unit/engine/test_p1b_buy_fill_duplicate_race.py` (4 케이스)
- 명세: `_workspace/red/_behaviors_p1_20260729.md` 사이클 B
- 자문: `_workspace/domain_consult/cycle_weekly_review_20260729.md`
- 작성: 2026-07-29 (tdd-engineer)

## 사고 (07-27 377450 실사고)

전량 체결 완료 시 `_handle_buy_fill` 이 매핑 4종(`_order_qty`/`_order_strategy`/`_order_ticker`/
`_filled_qty`) 을 pop (L1099-1102). 동일 order_no 2차 체결통보 도착 →
`handle_execution_notice` 의 `_order_ticker.get(order_no)` miss → payload ticker 사용 →
`_handle_buy_fill` 에서 `_order_strategy.get(order_no)` miss →
`_lookup_strategy_from_trade_history` PENDING 탐색인데 이미 COMPLETED → miss →
`"momentum"` 하드코딩 폴백(L974) → `registry.get("momentum")` → `pos=None` →
`state.positions[ticker]` 신규 등록 + DB positions PK(ticker) 덮어쓰기 →
원래 kojiro 포지션이 비활성 momentum 명의로 실명 → 손절/익일청산 사각.

## RED 실행 결과 (2026-07-29)

기존 GREEN 기준선: `test_cycle161_buy_fill_price_consistency`(7) +
`test_cycle147_sell_fill_strategy_fallback`(5) + `test_cycle163_buy_fill_db_error_isolation`(6) +
`test_order_engine_buy`(14) = **32 passed** (변경 없음, 무회귀 = B-5 보정 INSERT race 가드 보존).

신규 4 케이스 → **3 RED / 1 PASS**:

| 케이스 | 행위 | 상태 | RED 원인 |
|--------|------|------|----------|
| test_B1_duplicate_notice_after_full_fill_is_ignored | B-1 HIGH | RED | 2차 통보 @11,860 → momentum Position 신규 등록됨 (`{'377450': ...strategy_id='momentum', buy_price=11860}`) |
| test_B1_duplicate_notice_no_second_registration_log | B-1 | RED | `[buy_fill_duplicate_ignored]` 로그 부재 + "포지션 등록" 로그 발생 |
| test_B2_fallback_skips_when_ticker_held_by_other_strategy | B-2 HIGH | RED | 매핑 miss 폴백이 donchian 보유 000660 을 momentum 으로 덮어씀 |
| test_B4_partial_then_full_fill_unchanged | B-4 회귀 | PASS | 부분→전량 정상 흐름 무변경 (멱등 가드 오작동 방지) |

RED 3 = B-1(2) + B-2(1). PASS 1 = B-4 회귀 (구현 후에도 GREEN 유지 의무).

377450 실사고 시퀀스 정확 재현 확인: kojiro 매수 → 1차 @11,850 전량(3주) 체결 →
2차 @11,860 → 현행 momentum Position 신규 등록 (`buy_price=11860, quantity=3`).

## backend-dev 인계 요약

1. **B-1 멱등 상태**: 전량 체결 완료 시점(L1099 pop 영역) 에 완료 order_no 를 동기 등록
   (예: `self._completed_buy_orders: set[str]`, `_reset_daily_state` 동행 clear = 무한 성장 금지).
   `_handle_buy_fill` 진입부에서 완료 order_no 면 즉시 return + `[buy_fill_duplicate_ignored]` INFO 1행.
   (주의: `_completed_orders` 는 이미 "선행 race 보정 INSERT" 용도로 사용 중 — 별도 set 권장.)
2. **B-2 폴백 안전**: momentum 하드코딩 폴백(L974) 직전/직후, ticker 가 `registry` 전체에서
   이미 어느 전략 포지션에 존재하면(`is_ticker_held_by_any` 등) 신규 등록/덮어쓰기 대신 skip +
   `[buy_fill_fallback_held_conflict]` ERROR 1행 (기존 포지션 보존).
3. **B-3 가시화** (명세, 본 파일 미커버): B-1/B-2 미해당 진짜 고아 체결로 momentum 폴백 신규 등록 시
   `system_logs` CRITICAL 1행 (fire-and-forget) — tester 통합 단계 또는 후속 케이스 인계.
4. **회귀 0 의무**: B-4 부분→전량 흐름 + B-5 `_completed_orders` 선행 race 보정 INSERT +
   `_handle_sell_fill` + 사이클 147/161/163 chain 전부 무변경.
