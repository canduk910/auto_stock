# `execute_sell` 기준선 다시 잡기 — 2026-10-09 (cycle422-net)

리팩토링 카드 #12 1단계. **코드 무변경** — 지금 코드로 다시 잰 지도와 B4-3·B4-5 착수 전 그물.
규약 = [`2026-09-20_execute_sell_plan.md`](2026-09-20_execute_sell_plan.md)(성공의 정의 · 관문 · 중단 기준 · 절대 건드리지 않는 것).
판단 근거 = `2026-10-09_review.md`(main 작업 디렉터리, 미커밋) 「① 매도 함수」·「카드 #12」.

## 0. 잰 기준

| 항목 | 값 |
|---|---|
| 기준 커밋 | main `8a6d9682`(2026-10-09, cycle419 병합) — `order_engine.py` 마지막 변경 = `fee85880`(cycle409) |
| `src/engine/order_engine.py` 파일 sha256 | `08c479841352fb579f767c109de3e8f901d1c27bdce705b39b5ba6556fc0b3e1` (3,845줄) |
| `execute_sell` 소스 세그먼트 sha256 (`ast.get_source_segment`) | `e72fd3fd2ca384e5df9e6afb51b51231d139727dc5d12e42a18593bde849069e` |
| `execute_sell` 위치 | `:1767-2575` = **809줄** |
| `execute_sell` CC (`radon cc -s`) | **107** (F) — 리포 1위. 2위 `journal_view.build_card` 100 |
| 최대 중첩(if/for/while/try/with/except 깊이) | **10** |
| 같은 파일 비교 | `_handle_sell_fill` CC 45 · `execute_buy` CC 43 |

잰 방법 — CC 는 radon. 블록별 「결정점」 은 같은 규칙(if·elif·ifexp·for·while·except·bool 연산자 피연산자−1·comprehension if)을 AST 로 센 근사다. 블록을 감싸는 `except`·`if` 자체의 1점은 바깥 블록 몫이라 블록 합 ≠ 107.

## 1. 관심사 지도 — ①~⑲ (09-20 카드 번호 그대로, 줄 앵커만 새로)

| # | 관심사 | 지금 줄 | 줄 수 | 결정점 | 비고 |
|---|---|---|---|---|---|
| ① | `_selling` 중복 차단·진입 표식 | 1781-1787 | 7 | 1 | `_selling.add` · `_selling_locked_wait.discard` · `_selling_since` |
| ② | 거부 TTL 진입 게이트 | 1789-1805 | 17 | 3 | `SellRejectionTracker.is_blocked` → `[market_closed_blocked]` |
| ③ | 전략·포지션 존재 확인 | 1807-1817 | 11 | 2 | |
| — | 루프 상태 초기화 | 1819-1821 | 3 | 0 | `last_error` · `insufficient_qty` · `sell_cap` |
| ④ | 호가유형·가격 결정 | 1822-1826 | 5 | 2 | |
| ⑤ | 거래소 라우팅 | 1827-1838 | 12 | 1 | 지정가 = `_apply_clock("NXT")` / 시장가 = `_strategy_exchange_async` |
| ⑥ | 15:30~16:00 휴식 컷 | 1840-1852 | 13 | 1 | cycle295 |
| ⑦ | NXT 프리장 시장가→지정가 사전 변환 | 1854-1884 | 31 | 7 | 🔴 `test_cycle287_ast_scope.py` 동결 구간 `execute_sell_pre_nxt_preconvert`(B4-6 = 건너뛰기 권고) |
| ⑧ | KRX 애프터 44/41 변환 + `primary_div`/`fallback_div` | 1886-1951 | 66 | 9 | |
| ⑨ | 재시도 루프 + 포지션 재조회 + `send_qty` 고정 | 1953-1976 | 24 | 2 | cycle327 ⓒ · cycle385 §a-2 |
| ⑩ | 발사 | 1977-1985 | 9 | 0 | |
| ⑪ | 주문번호 매핑 5종 | 1987-1995 | 9 | 0 | 동기 영역 |
| ⑫ | 접수 후 영속화(주 경로) | 1997-2007 | 11 | 0 | `_persist_sell_pending_after_send(path="market")` |
| ⑬ | 접수 로그 + return | 2009-2013 | 5 | 0 | |
| ⑭ | 장운영시간 외 거부(`market_closed`) | 2015-2126 | 112 | 13 | `nxt_tradable=False` 사후 보강 · 애프터 포기 래치 |
| ⑮ | APBK0400 잔고 재대조 5분기 | 2127-2318 | **192** | **36** | cycle236 + cycle385 R·R2·R3·R4. B4-4 대상 |
| ⑯ | 진짜 보유 부족(insufficient) | 2319-2328 | 10 | 1 | `break` |
| ⑰ | **시장가 거부 → 지정가 폴백** | **2329-2509** (코드 2340-2509) | **170** | **16** | **B4-3 대상** — 아래 2절 |
| ⑱ | backoff(분류 밖 `KisApiError` · 일반 `Exception`) | 2510-2523 | 14 | 2 | `SELL_RETRY_DELAY × 2^(attempt−1)` = 1s·2s |
| ⑲ | **마지막 실패 뒤처리** | **2525-2575** | **51** | **7** | **B4-5 대상** — 아래 3절 |

`except KisApiError` 한 덩어리(⑭~⑰ + ⑱ 앞 절반) = `:2015-2515` 501줄 — 관심사 4개가 같은 깊이로 붙어 있다.

### 1.1 낡은 앵커 → 새 앵커

| 문서 | 그때 앵커 | 지금 |
|---|---|---|
| `2026-09-20_step1_card.md` | `execute_sell` `:1345-2102`(704~711줄 · CC 89~90) | `:1767-2575`(809줄 · CC 107) |
| `2026-09-20_step1_gate_tester.md` | 폴백 거부 핸들러 `:1995-2043` | `:2454-2509` |
| `red/bundle_D_plan.md` S3(09-26) | 폴백 분기 커버리지 범위 `2084-2261` | `2340-2509` |
| `2026-10-09_review.md` | 폴백 `:2340-2509` · 뒤처리 `:2527-2572` | 폴백 같음 · 뒤처리 `:2525-2575`(첫 줄 `_selling.discard` 와 마지막 CRITICAL 포함) |

커진 몫(09-21 704줄 → 지금 809줄)은 cycle385(분할 매도 — ⑮ 부분 잠김 판매·크레딧·동결 표식) · cycle392·396(매도 장부) · cycle409(주문가)이다. ⑰·⑲ 자체는 09-20 이후 거의 그대로다(⑰ 은 cycle287·327 이후 구조 불변).

## 2. ⑰ 폴백 블록 — B4-3 추출 입력

### 2.1 하위 블록

| 하위 | 줄 | 결정점 | 하는 일 |
|---|---|---|---|
| 관문 | 2340-2343 | (관문 if) | `order_division == primary_div and (is_market_order_disallowed(e) or primary_div is not MARKET)` — 정규장·프리장 = 「시장가 불가」 분류 의존, 애프터 = **구조적 폴백**(분류 무관) |
| a ETP 관측 | 2343-2364 | 2 | 애프터 1차 거부만 — `create_task(_observe_after_exit_etp)` fire-and-forget(`RuntimeError` = DEBUG) + `[after_exit_rejected]` |
| b 현재가 미확보 | 2365-2395 | 3 | `scanner.ticker_prices` 현재가 ≤ 0 → 폴백 못 함 → WARNING → **일반 재시도로 떨어짐**. 애프터면 봉인①(30초 TTL)·봉인②(포기 래치) 적용 |
| c 발사 | 2396-2406 | — | `place_order(quantity=send_qty, price=step_down(cur,5), order_division=fallback_div, exchange=target_exchange)` |
| d 매핑 | 2408-2417 | 0 | 5종 동기 등록(`_order_division` = `fallback_div.value`) |
| e 접수 후 영속화 | 2419-2429 | 0 | `_persist_sell_pending_after_send(path="fallback", record_price=fallback_price, order_unpr=fallback_price)` — 경계 래퍼 |
| f 성공 | 2431-2453 | 1 | WARNING 「지정가 5호가 폴백」 · 애프터 `[after_exit_division]` · TTL(성공) · **return** |
| g 거부 후처리 | 2454-2509 | 5 | `_selling.discard`(첫 await 앞) · 장부 「모두 거부」 · 애프터 마커 · TTL(실패) · NXT 시간대면 익일청산 큐 · 애프터 포기 래치(TTL **뒤**) · **return** |

### 2.2 읽고 쓰는 것

- **읽는 지역 변수**: `e`(1차 거부) · `ticker` · `strategy_id` · `order_division` · `primary_div` · `fallback_div` · `_after_market_dial` · `send_qty` · `target_exchange`. `pos`·`strategy` 는 **읽지 않는다**.
- **쓰는 지역 변수**: `last_error = fb_err`(g) — 바로 `return` 이라 **죽은 대입**이다(추출 시 반환할 필요 없음, 돌연변이로 판별 불가 = 동등 돌연변이).
- **`self` 상태**: `_order_qty`·`_order_strategy`·`_order_ticker`·`_order_exchange`·`_order_division`(쓰기) · `_selling`(discard) · `_sell_rejection.register_market_order_disallowed` · `_pending_next_day_clear_provider()` · 헬퍼 `_persist_sell_pending_after_send` · `_observe_after_exit_etp` · `_register_after_exit_disallowed` · `_bump_after_exit_fails_and_maybe_giveup`(→ `_after_exit_fails`).
- **모듈 전역**: `place_order` · `write_log` · `is_nxt_session_hours` · `step_down` · `scanner.ticker_prices`(함수 안 import) · `_classify_after_exit_rejection`.

### 2.3 제어 신호 — enum 후보

| 출구 | 조건 | 지금 동작 | 호출부(루프)가 할 일 |
|---|---|---|---|
| `SENT` | 폴백 접수(접수 후 영속화 실패 포함 — 래퍼가 삼킨다) | `return` | `return` |
| `REJECTED` | 폴백 `place_order` 가 `KisApiError` | `return` | `return` |
| `NO_PRICE` | 현재가 ≤ 0 | 블록 밖으로 떨어짐 | 아래 「매도 주문 실패 (시도 n/3)」 WARNING + backoff + 다음 시도 |
| (관문 거짓) | 관문 불성립 | 블록 미진입 | 위와 같음 — 관문 판정을 호출부에 남길지 메서드에 넣을지는 설계 선택 |
| **전파** | 폴백 `place_order` 가 **비-`KisApiError`**(`httpx.ReadTimeout` 등) | `execute_sell` 밖으로 전파 · `_selling` 잔존 | 🔴 **그대로 전파되게 둔다**(아래 2.4). 추출한 메서드를 `try:` 안에서 부르면 바깥 `except Exception` 이 받아 재시도 = **재발사**가 된다 |

### 2.4 발견 — F-422-1 (결함 후보, 이번 단계에서 고치지 않음)

폴백 `place_order` 가 `KisApiError` 가 **아닌** 예외(전송 오류·5xx 재시도 소진·타임아웃 — `src/api/base.py::_request` 는 이 경우 `httpx` 예외를 그대로 올린다)를 내면, 형제 `except Exception` 은 `except KisApiError` 핸들러 **안**에서 난 예외를 받지 못해 `execute_sell` 밖으로 나간다.

- 결과 ① `_selling`·`_selling_since` 가 남는다 → 그 종목 손절 재평가가 `selling_reconcile`(15분 sync · 180초)이 풀 때까지 멈춘다.
- 결과 ② 호출자 `risk.on_tick`(`risk.py:704` `await`)의 그 틱이 끊긴다 → 같은 틱의 다음 전략 평가가 빠진다.
- 앞 전송이 접수됐을 수도 있어(응답 유실) 「재시도」 로 고치는 것은 답이 아니다 — cycle327 「주문이 나간 뒤 재발사 금지」. 고친다면 「전송 중」 으로 보고 `_selling` 유지 + 전파 차단 + 관측이 후보다. **매매 행위 변경이라 별도 승인 + `domain-consult` 대상**.
- 지금은 그물(`test_f07_*`)이 **현행 행위를 핀**한다. B4-3 은 이 행위를 그대로 옮기고, 결함 수정 사이클이 그 테스트를 의도적으로 뒤집는다.

## 3. ⑲ 마지막 실패 뒤처리 — B4-5 추출 입력

| 줄 | 하는 일 |
|---|---|
| 2526 | `_selling.discard(ticker)` — **무조건 · 첫 await 앞** |
| 2527-2572 | `insufficient_qty` 참: 메모리 포지션 pop → `on_position_closed`(예외 = `[on_position_closed_skip]` ERROR) → DB `delete_position`(예외 = `logger.exception`) → `write_log` WARNING 「매도가능수량 부족 — 메모리 포지션 정리」 → `safe_write_log` INFO `[positions_reconciliation] … reason=insufficient_quantity` → `get_balance` 1회(잔량 > 0 이면 「재등록 권고」 INFO, 예외 = DEBUG) → return |
| 2573-2575 | 그 밖: `매도 주문 최종 실패: {ticker} {signal.value} — {last_error}` CRITICAL(로거 + `write_log`) |

- 읽는 것: `insufficient_qty` · `last_error` · `signal` · `strategy` · `strategy_id` · `ticker`. 출구는 둘 다 함수 끝(반환값 없음).
- 🔴 `tests/unit/ast/test_cycle185_cluster1_ast.py` 가 「포지션 제거 자리 = `{_handle_sell_fill, execute_sell}` 정확히 둘」 을 함수 이름으로 잡는다 → B4-5 는 이 가드를 **같은 커밋**에서 재조준한다(약화 금지 — 「제거 자리는 정확히 둘, 그중 하나는 `execute_sell` 에서만 불리는 뒤처리 메서드」).

## 4. 선행 그물 — `tests/unit/engine/test_cycle422_sell_fallback_net.py`(33 케이스)

절 구성 — F(⑰ 정규장 9) · N(⑰ 접수 후 실패 = 1단계 tester 관문 N2·N3·N4 재현 3) · A(⑰ 애프터 7) · P(⑲ 9) · G(B4-4 대비 5). 분기마다 주문 호출 인자·횟수 · `_selling`(+`_selling_since`·`_selling_locked_wait`) · 매핑 5종(그리고 PENDING INSERT 시점에 이미 서 있는지) · PENDING 행 · TTL 등록 인자 · 익일청산 큐 · 로그 마커 · return/continue/전파 · backoff 지연을 핀한다. 벽시계 무의존(정규장 = 모의 + `is_nxt_session_hours` 주입, 애프터 = `freeze_time` 16:05 + 실전).

### 4.1 분기 커버리지 (`coverage run --branch`, 줄 범위로 자름)

| 범위 | 기존 매도 테스트 79파일 | 새 그물 단독 | 둘 합 |
|---|---|---|---|
| ⑰ `2340-2509` 문장 | 46/54 | **54/54** | 54/54 |
| ⑰ `2340-2509` 분기 | 16/18 | **18/18** | 18/18 |
| ⑲ `2525-2575` 문장 | 19/26 | **26/26** | 26/26 |
| ⑲ `2525-2575` 분기 | 3/4 | **4/4** | 4/4 |
| `execute_sell` 전체 `1767-2575` 문장 · 분기 | 288/315 · 104/110 | — | 303/315 · 108/110 |

기존이 못 덮던 것: ETP 태스크 등록 실패 · 애프터 현재가 미확보(봉인①·②) · 익일청산 공급자 예외·None · 훅 예외 · DB 삭제 예외 · 잔량 > 0 권고 · 잔고 재조회 예외.

### 4.2 돌연변이 (스크래치 사본 cp 원복 · `git` 미사용 · 원복 sha 확인)

| # | 블록 | 돌연변이 | 새 그물 | 처음 잡은 새 테스트 | 기존 매도 테스트 79파일 |
|---|---|---|---|---|---|
| M01 | ⑰ | 관문: 거부 분류와 무관하게 폴백(시장가 불가 판정 제거) | 잡음 | `test_f01_gate_false_when_unclassified_market_rejection_then_plain_retries` | **놓침** |
| M02 | ⑰ | 관문: order_division == primary_div 조건 제거(지정가 매도도 폴백) | 잡음 | `test_f02_gate_false_when_limit_order_then_no_fallback_even_if_disallowed` | **놓침** |
| M03 | ⑰ | 관문: 애프터 구조적 폴백 제거(분류 의존으로 축소) | 잡음 | `test_a01_after_44_rejected_falls_back_to_41_with_etp_observe_and_markers` | 잡음(`test_k9d_unclassified_rejection_registers_ttl`) |
| M04 | ⑰ | 폴백 수량 = pos.quantity (send_qty 대신) | 잡음 | `test_f03b_fallback_quantity_is_this_attempts_send_qty_not_position` | **놓침** |
| M05 | ⑰ | 폴백 가격 5호가 → 4호가 | 잡음 | `test_f03_fallback_success_pins_order_mapping_pending_ttl_and_return` | 잡음(`test_k9_44_rejection_falls_back_to_41`) |
| M06 | ⑰ | 현재가 미확보 판정 <= 0 → < 0 | 잡음 | `test_f06_no_current_price_then_no_fallback_and_plain_retry` | **놓침** |
| M07 | ⑰ | 폴백 호가유형 = 원래 호가유형(시장가 재발사) | 잡음 | `test_f03_fallback_success_pins_order_mapping_pending_ttl_and_return` | 잡음(`test_k9_44_rejection_falls_back_to_41`) |
| M08 | ⑰ | 폴백 매핑 호가유형 = 원래 호가유형 | 잡음 | `test_f03_fallback_success_pins_order_mapping_pending_ttl_and_return` | 잡음(`test_c4d_sell_fallback_path_records_the_fallback_division`) |
| M09 | ⑰ | 폴백 매핑 거래소 누락 | 잡음 | `test_f03_fallback_success_pins_order_mapping_pending_ttl_and_return` | **놓침** |
| M10 | ⑰ | 성공 TTL 을 실패로 등록 | 잡음 | `test_f03_fallback_success_pins_order_mapping_pending_ttl_and_return` | **놓침** |
| M11 | ⑰ | 폴백 성공 뒤 return 제거(재시도로 떨어짐 = 재발사) | 잡음 | `test_f03_fallback_success_pins_order_mapping_pending_ttl_and_return` | 잡음(`test_sell_post_send_error_when_insert_fails_then_record_carries_traceback[fallback]`) |
| M12 | ⑰ | 폴백 거부 시 _selling 해제 누락(좀비) | 잡음 | `test_f04_fallback_rejected_releases_selling_preserves_position_and_returns` | 잡음(`test_k9c_both_rejected_preserves_position_and_discards_selling`) |
| M13 | ⑰ | 폴백 거부 _selling 해제를 await 뒤(return 직전)로 이동 | 잡음 | `test_f04_fallback_rejected_releases_selling_preserves_position_and_returns` | **놓침** |
| M14 | ⑰ | 익일청산 필요 판정 반전 | 잡음 | `test_f04_fallback_rejected_releases_selling_preserves_position_and_returns` | **놓침** |
| M15 | ⑰ | 폴백 거부 뒤 return 제거(재시도로 떨어짐) | 잡음 | `test_f04_fallback_rejected_releases_selling_preserves_position_and_returns` | 잡음(`test_k7_etp_is_observed_but_not_blocked[EF]`) |
| M16 | ⑰ | 포기 래치를 30초 TTL 등록 앞으로 이동 | 잡음 | `test_a02_after_fallback_rejected_queues_next_day_then_bumps_giveup` | 잡음(`test_k9f_daily_giveup_latch_after_repeated_failures`) |
| M17 | ⑰ | 애프터 현재가 미확보 분기의 포기 래치 누락 | 잡음 | `test_a03_after_no_current_price_registers_ttl_bumps_and_retries` | **놓침** |
| M18 | ⑰ | ttl_registered 를 상수 1 로 | 잡음 | `test_a03_after_no_current_price_registers_ttl_bumps_and_retries` | **놓침** |
| M19 | ⑰ | 폴백 접수 후 영속화를 경계 래퍼 대신 코어로 직접 호출(경계 소실) | 잡음 | `test_n_fallback_post_send_error_is_absorbed_not_reported_as_rejection` | 잡음(`test_sell_post_send_error_when_insert_fails_then_record_carries_traceback[fallback]`) |
| M20 | ⑰ | 애프터 1차 거부 관측(ETP·마커) 블록 비활성 | 잡음 | `test_a01_after_44_rejected_falls_back_to_41_with_etp_observe_and_markers` | 잡음(`test_k7_etp_is_observed_but_not_blocked[EF]`) |
| M21 | ⑲ | ⑲ 첫 줄 _selling 해제 누락 | 잡음 | `test_f01_gate_false_when_unclassified_market_rejection_then_plain_retries` | 잡음(`test_b4_2_no_exception_propagates_to_caller`) |
| M22 | ⑲ | ⑲ 잔고부족 분기 반전 | 잡음 | `test_f01_gate_false_when_unclassified_market_rejection_then_plain_retries` | 잡음(`test_execute_sell_when_limit_order_rejected_then_no_fallback`) |
| M23 | ⑲ | ⑲ 보유결합 상태 정리 훅 누락 | 잡음 | `test_p01_insufficient_cleanup_order_and_effects` | 잡음(`test_G2_SECONDARY_COMMON_insufficient_qty_reconciliation_discards`) |
| M24 | ⑲ | ⑲ CRITICAL 장부 기록 누락 | 잡음 | `test_f01_gate_false_when_unclassified_market_rejection_then_plain_retries` | **놓침** |
| M25 | ⑲ | ⑲ 잔량 권고 로그 조건 > 0 → >= 0 | 잡음 | `test_p01_insufficient_cleanup_order_and_effects` | **놓침** |
| M26 | ⑲ | ⑲ 잔고부족 정리 뒤 return 누락(CRITICAL 까지 떨어짐) | 잡음 | `test_p01_insufficient_cleanup_order_and_effects` | **놓침** |
| M27 | ⑲ | ⑲ 훅을 메모리 포지션 제거 앞으로(순서 뒤집기) | 잡음 | `test_p01_insufficient_cleanup_order_and_effects` | **놓침** |
| M28 | ⑰ | 폴백 거래소를 NXT 로 고정 | 잡음 | `test_f03_fallback_success_pins_order_mapping_pending_ttl_and_return` | 잡음(`test_k9_44_rejection_falls_back_to_41`) |
| M29 | ⑰ | 폴백 매핑 수량을 PENDING INSERT(await) 뒤로 이동 — 매핑 동기 영역 위반 | 잡음 | `test_f03_fallback_success_pins_order_mapping_pending_ttl_and_return` | **놓침** |
| M30 | ⑮(G) | G: 재대조 뒤 continue 제거(backoff·일반 재시도로 떨어짐) | 잡음 | `test_g4_qty_exceeded_contamination_reconciles_continues_without_backoff_and_keeps_selling` | **놓침** |

합계 — 새 그물 **30/30** · 기존 79파일 **14/30**. 매 돌연변이 뒤 `order_engine.py` sha256 = `08c47984…` 로 원복 확인(스크래치 사본 cp). 동등 돌연변이(판별 불가) = 폴백 거부 핸들러의 `last_error = fb_err`(바로 return).

### 4.3 B4-4 대비 — `test_cycle236` 5분기 점검

| 분기 | `test_cycle236` 이 핀하던 것 | 빠졌던 것 → 새 그물 |
|---|---|---|
| ① 재대조 불가(잔고 예외) | 발사 3회 · 포지션 보존 | `_selling` 해제 · backoff · CRITICAL → **G1** |
| ② 0 < sellable < 추적 | 재대조(`[3,2]`) · 부분 잠김 판매 · 부분 잠김 보류(`_selling` 유지 + 동결) | 재대조 `continue` 가 backoff 를 건너뛰는 것 · 재대조 뒤 `_selling` 유지 → **G4** / 보류 return 의 backoff 0 → **G5** / 부분 잠김 판매 `continue` 의 backoff 0 → F03b |
| ③ sellable = 0 ∧ 보유 > 0 | return · `_selling` 유지 · 동결 표식 | (다 있음) |
| ④ sellable = 0 ∧ 보유 = 0 | break · 포지션 삭제 | `_selling` 해제 · backoff 0 · CRITICAL 없음 → **G2** |
| ⑤ sellable ≥ 추적(이상) | **테스트 없음**(리포 전체) | 일반 재시도 · 매 회차 재대조 · 보정 없음 · `_selling` 해제 → **G3** |

②의 나머지 하위 분기(`position_replaced` · `[sell_qty_hold_orders_unavailable]` · `[sell_qty_unnoticed_fills]` · 크레딧)는 `test_cycle385r*` 가 핀한다.

## 5. B4-3 · B4-5 착수 때 같은 커밋에서 재조준할 구조 가드

| 가드 | 지금 단언 | 추출 뒤 |
|---|---|---|
| `test_cycle385_ast_b7.py::test_a3_*` | `execute_sell` 안 `place_order` 정확히 2곳 · 둘 다 `quantity=send_qty` | 주 경로 1(execute_sell) + 폴백 1(추출 메서드) — 둘 다 `send_qty` 인자 이름 유지 |
| `test_cycle328_sell_pending_helper.py::test_g328_0b` | 경계 래퍼 호출 `execute_sell` 안 정확히 2곳 | execute_sell 1 + 추출 메서드 1 · `test_g328_3b`(래퍼 `except Exception` 단일) 그대로 |
| `test_cycle276_ast_order_hook.py::test_c6_*` | `execute_sell` 안 LLM 훅 0 | 추출 메서드도 0 (대상 함수 목록에 더한다 — 약화 금지) |
| `test_cycle185_cluster1_ast.py` (B4-5) | 포지션 제거 자리 = `{_handle_sell_fill, execute_sell}` | 「정확히 둘」 유지, 이름만 재조준 |
| `test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` | `order_engine.py` 승인 sha | 새 sha + 승인 사유(8영역) |
| `test_cycle287_ast_scope.py` 동결 구간 | ⑦ 프리장 변환 텍스트 sha | 무접촉(⑦ 은 건드리지 않는다) |

`order_engine.py` 는 영향 인덱스 선택력이 0 이다(백엔드 전부가 직접 의존) — 단계마다 전체 스위트를 돈다.

## 6. 착수 판정

- **B4-3 = 착수 가능**(그물 측면). ⑰ 문장·분기 100%, 돌연변이 30개 중 ⑰ 대상 전부를 새 그물이 잡는다. 남은 선결 = 사용자 승인(8영역) + 관문 3인 순차(tester → domain-expert → tdd-engineer, 규약 §2) + F-422-1 을 **고치지 않고 옮긴다**는 합의.
- **B4-5 = 착수 가능**(그물 측면). ⑲ 문장·분기 100%. 선결 = B4-3 뒤 · `test_cycle185` 재조준 설계.
- **B4-4 = 그물 보강 완료**(5분기 `_selling`·흐름 핀). 가치 판정은 여전히 B4-3 뒤(리뷰 「B4-3 뒤 재판정」).
