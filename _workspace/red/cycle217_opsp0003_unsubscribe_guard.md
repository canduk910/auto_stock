# 사이클 217 Red — `resubscribe_stale_priority` OPSP0003 스팸 회귀 가드

- **작성**: tdd-engineer (Red 단계, 구현은 backend-dev)
- **날짜**: 2026-08-13
- **위험 등급**: MEDIUM (LOW 후보 거부 = 손절 무해 / but ERROR 스팸 + 잠재 KIS LMS)
- **8영역 diff 0**: stale_watcher_core.py 는 realtime/ 미포함 = 8영역 아님. `_ticker_to_session`
  직접 접근은 런타임 — realtime/ 파일 미편집. 사이클 88 G-REJECT-1 AST(`def
  resubscribe_stale_priority` 존재)와 무충돌.

## 배포 후 발견된 회귀 (2026-08-13 EC2 실측)

cycle215 가 `resubscribe_stale_priority`(`src/engine/stale_watcher_core.py:509-533`) 에
이식한 무조건 `unsubscribe_in_pool(TICK_TR_ID, ticker)` 이 KIS 에 unsubscribe SEND 를
보낸다. 그런데 이 함수의 stale 소스(`scanner.ticker_last_tick`) 에는 **실제 미구독 종목**
(stale 후보 / split-brain) 이 섞여 있어, 미구독 종목에 unsubscribe SEND 를 보내면 KIS 가
`OPSP0003 "UNSUBSCRIBE ERROR(not found!)"` 를 반환한다.

- 08-13 하루 59 건 (08-11/12 는 0 = cycle215 배포 직후 발생).
- 거부 전부 LOW 후보(보유 아님, 손절 무해)나 ERROR 스팸 + 잠재 LMS chain.
- **K watcher(`check_and_resubscribe_stale`) 무발생 근거**: stale 소스가
  `kis_ws_pool.get_subscribed_tickers()`(=`_subscriptions`, 항상 실제 구독)라 미구독
  종목이 섞이지 않음. 결함은 소스가 `ticker_last_tick` 인 `resubscribe_stale_priority` 한정.

## 시정 방향 (backend-dev 구현)

재구독 루프에서 **구독 상태로 unsubscribe SEND 를 가드**:

1. 루프 진입 *전* (targets 조립 직후) 구독 스냅샷 1회:
   `subscribed = kis_ws_pool.get_subscribed_tickers()` (try/except → set() 폴백).
2. 각 ticker (priority/bypass 분기 *후*, 기존 try 블록 안):
   - `ticker in subscribed`(실제 구독 중) → 기존대로 `unsubscribe_in_pool` + `sleep(0.05)`
     (실제 해지 = KIS "신규 등록" 패턴, 재등록 회피).
   - `ticker not in subscribed`(미구독 = split-brain / stale 후보) →
     **`kis_ws_pool._ticker_to_session.pop(ticker, None)` 직접 pop 만** (KIS unsubscribe
     미발송 → OPSP0003 회피). try/except graceful.
   - 이후 `subscribe(...)` 무변경 (dedup 가드가 pop 덕에 재SEND).

**정확한 삽입 (검증된 patch, `src/engine/stale_watcher_core.py`)**:
`targets = high_targets + ...` / `resubscribed = []` 직후 스냅샷 추가 + 기존 490-line
`await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)` + `await asyncio.sleep(0.05)`
2줄을 `if ticker in subscribed_snapshot: <기존 2줄> else: try: kis_ws_pool._ticker_to_session
.pop(ticker, None) except Exception: pass` if/else 분기로 교체. 나머지 (subscribe / append /
`_stale_last_resubscribe_at` 갱신 / 최종 `sleep(0.05)`) 무변경.

tdd-engineer 가 이 patch 를 임시 적용 → 전 테스트(신규 7 + cycle215 갱신 6 + cycle216 7 +
인접 97) GREEN 확인 후 revert. backend-dev 는 동일 구조로 재적용.

## 산출물

- **신규**: `tests/unit/engine/stale_manager/test_cycle217_unsubscribe_guard.py` (7 케이스)
- **갱신 (의미 전환)**: `tests/unit/engine/stale_manager/test_cycle215_resubscribe_split_brain.py`

## Red 케이스 매트릭스 (신규 cycle217)

| ID | 등급 | 명제 | Red 사유 (현 코드) |
|----|------|------|-------------------|
| G217-1 | HIGH | 미구독 → unsubscribe_in_pool 미호출 + 매핑 pop + 재SEND | await_count>=1 |
| G217-2 | HIGH | 구독분만 unsubscribe_in_pool, 미구독분 미호출 (게이트) | 둘 다 호출 |
| G217-3 | HIGH | 실경로 split-brain HIGH 재SEND 복구 + KIS unsubscribe SEND 미발생 | 세션 unsub SEND |
| G217-4 | HIGH | 실경로 OPSP0003 회피 실증 — 구독분만 세션 unsubscribe SEND | 둘 다 SEND |
| G217-5 | HIGH | cycle216 동시호가 LOW skip 병존 + HIGH 구독 가드 | HIGH unsub_in_pool 호출 |
| G217-6 | MEDIUM | cycle216 throttle skip 병존 + 통과분 구독 가드 | 통과분 unsub_in_pool 호출 |
| G217-7 | MEDIUM | AST — 구독 스냅샷 + `_ticker_to_session.pop` 분기 + 순서 | 두 seam 부재 |

## cycle215 의미 전환 (갱신)

| ID | 전환 | Red/불변 |
|----|------|----------|
| GS-1 | split-brain(미구독) → unsubscribe_in_pool **미호출**(직접 pop)로 반전 (구 명제=호출) | RED |
| GS-2 | 재SEND 복구 **유지**(핵심) + KIS unsubscribe SEND 미발생 조건 추가 | RED |
| GS-6 | `unsubscribe_in_pool precede` → 구독 스냅샷 + `_ticker_to_session.pop` 분기 AST 로 재정의 | RED |
| GS-3 | HIGH priority/bypass 불변 (구독분 경로로 명시) | 불변 PASS |
| GS-4 | 구독 LOW → unsubscribe_in_pool 선행 (구독분 한정 재정의) | 불변 PASS |
| GS-5 | 구독분 unsubscribe_in_pool 시그니처 + subscribe 인자 불변 | 불변 PASS |

## Red → Green 로그

- **Red 확인 (현 코드, cycle215/216 배포 상태)**: `pytest cycle217 + cycle215` = **10 failed
  (7 cycle217 + GS-1/2/6), 3 passed (GS-3/4/5 불변)**. 실패 사유 전수 = 의도한 Red 단언
  (미구독에 unsubscribe SEND / OPSP0003 유발 / AST seam 부재). 인접 오탐 0.
- **Green 검증 (임시 patch 적용)**: cycle217 7 + cycle215 6 + cycle216 7 = **20 passed**.
  인접(stale_manager 전체 + scan_loop_stale_priority + scheduler_stale_tracking +
  stale_watcher_priority_split + cycle63_priority_cap/delegation + breakout_candidate +
  cycle74 + cycle135 grace + external_llm_reject + cycle92) = **97 passed, 4 xfailed**
  (pre-existing). patch revert 후 `git diff src/engine/stale_watcher_core.py` = **빈 diff**.

## 인접 영향 평가 (backend-dev 주의)

- **cycle66/cycle63 priority_cap 테스트**: bare `MagicMock` 풀 사용 — `ticker in
  mock.get_subscribed_tickers()` → `False`(MagicMock `__contains__` 기본), `mock.
  _ticker_to_session.pop()` → MagicMock(무해). 전부 미구독 분기로 처리되나 subscribe 는
  양 분기 공통 호출이라 `subscribe.await_count` 단언 불변 → **GREEN 유지**.
- **cycle216 T1~T7**: 구독 가드는 동시호가/throttle 필터 *후* 루프 내 → 필터 결과·subscribe
  행위 불변. **무영향 확인**(7 passed).
- **priority-split 테스트(`test_stale_watcher_priority_split.py`)의 `unsubscribe_in_pool.
  assert_awaited_once`**: 대상이 **K watcher(`_check_and_resubscribe_stale`)** 라 본 시정
  (resubscribe_stale_priority 한정)과 무관 → **무영향**.
- **G-REJECT-1 AST**: `def resubscribe_stale_priority` 존재만 검사 → 함수 내부 분기 추가
  무충돌.

## 영속 의무

- cycle215 split-brain 재SEND 복구(HIGH bypass=True) — 핵심 불변 (GS-2/G217-3 유지).
- cycle216 동시호가 LOW skip + LOW throttle — 병존 (G217-5/6).
- 사이클 32 R4 보유/익일청산 절대 보장 + 사이클 66 priority 분리 *후* cap 불변.
