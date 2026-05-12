# K — WebSocket 시세 silent inactive 자동 복구 (stale_watcher)

## 의도 (사용자 명세 요약)
KIS WebSocket 구독은 됐으나 시세가 silent 하게 안 들어오는 종목을 30s 주기로 감시,
60s 미수신이면 `_send_subscribe` 재발송. 3회 연속 stale이면 unsubscribe + subscribe 강제 재등록.
6회 누적 stale이면 skip (다음 `_scan_loop` 사이클에 위임). F1(재연결 1회) + `_scan_loop`(5분) + K(30s) 3중 안전망.

## 결함 증거 (2026-05-12 운영 로그)
- 11:48 [tick_coverage] subscribed=27 fresh=1 stale=26 (96% silent inactive)
- 12:23 fresh=3 stale=25 — KIS 한도(41) 미만이라 한도 초과 아님
- F1 1회 + _scan_loop 5분으로는 시간차 silent inactive 미회복

## 행위 분해 (= TDD Red 단위)

| # | 행위 | 입력 | 기대 결과 | Red 파일 위치 |
|---|------|------|----------|---------------|
| K-1 | **전체 fresh일 때** 재구독/강제 재등록 모두 발생 안 함 | subscribed={A,B,C} 모두 last_tick = now | `_send_subscribe` 0회, `unsubscribe`/`subscribe` 0회, `_stale_retry_count` empty | tests/integration/test_stale_watcher.py::test_all_fresh_noop |
| K-2 | **1종목 stale, retry=1**: `_send_subscribe(TICK_TR_ID, t, subscribe=True)` 1회 (unsubscribe 미발생) | A는 70s 전 last_tick, B/C는 fresh | resubscribed=1, force=0, retry_count={A:1} | tests/integration/test_stale_watcher.py::test_single_stale_resends |
| K-3 | **3종목 stale, 이미 retry=3 누적 → 4회 진입**: 강제 재등록 (unsubscribe + subscribe(bypass_limit=True)) 각 3회 | retry_count={A:3,B:3,C:3}, 모두 stale | force_reregistered=3, unsubscribe 3회 + subscribe 3회 + `_send_subscribe` 0회 | tests/integration/test_stale_watcher.py::test_force_reregister_after_3 |
| K-4 | **retry 7회 누적(=6 초과)**: skip — unsubscribe/subscribe/`_send_subscribe` 미호출 | retry_count={A:6}, A stale | skipped_giveup=1, 0 calls | tests/integration/test_stale_watcher.py::test_skip_after_6_giveup |
| K-5 | **stale → fresh 회복 후 다시 stale**: retry_count 1부터 재시작 | 사이클1: A stale(retry=1) → 사이클2: A fresh(clear) → 사이클3: A stale → retry=1 | 마지막 사이클 retry_count={A:1}, 추가 `_send_subscribe` 호출 | tests/integration/test_stale_watcher.py::test_retry_resets_on_recovery |
| K-6 | **mixed**: 일부 첫 회 stale + 일부 4회째: resubscribed + force_reregistered 동시 카운트 | A retry=0→1(resend), B retry=3→4(force) | resubscribed=1, force=1 | tests/integration/test_stale_watcher.py::test_mixed_resend_and_force |
| K-7 | **`_running=False`**: 즉시 종료, 추가 호출 없음 | watcher loop 도중 _running=False | sleep 후 즉시 break, task cancel 안전 | tests/integration/test_stale_watcher.py::test_running_false_exits |
| K-8 | **체크 함수 예외**: 다음 사이클 정상 동작 | `_check_and_resubscribe_stale` 1회 raise | 예외 후에도 다음 sleep + 호출 진행, logger.exception 호출 | tests/integration/test_stale_watcher.py::test_exception_resilient |
| K-9 | **`_reset_daily_state()` clear**: `_stale_retry_count.clear()` | retry_count={A:2,B:3} 상태에서 reset | reset 후 retry_count == {} | tests/integration/test_stale_watcher.py::test_reset_clears_retry_count |
| K-10 | **task lifecycle**: `start()` finally에서 cancel + None 설정 | `_stale_watcher_task` 생성 후 종료 | finally 블록 task_attr 포함, task.done() / None | (기존 lifecycle 패턴 동일 — start() finally 어셋션 또는 코드 리뷰로 검증) |

## 안전 불변식 (변경 없음 확인)
- F1 `_verify_subscriptions_after_reconnect` 무변경
- E1 우선순위 큐, MAX_SUBSCRIPTIONS=41 무변경 (강제 재등록은 `bypass_limit=True`)
- D `ticker_last_tick` read-only 사용
- 6자리 영숫자/숫자 매수 가드 영향 없음

## 통합 지점
- `src/engine/scheduler.py`
  - 상수 추가: `STALE_WATCHER_INTERVAL_SECS=30`, `STALE_FRESHNESS_SECS=60`, `STALE_FORCE_REREGISTER_AFTER=3`
  - `__init__`: `self._stale_watcher_task: asyncio.Task | None = None`, `self._stale_retry_count: dict[str, int] = {}`
  - 신규: `async def _stale_watcher_loop(self)`, `async def _check_and_resubscribe_stale(self)`
  - `start()` body: `self._stale_watcher_task = asyncio.create_task(self._stale_watcher_loop())` (07:55 사전 구독 시점 또는 _session_task 발화 직후)
  - `start()` finally: task_attr 튜플에 `_stale_watcher_task` 추가 — cancel + await + None
  - `_reset_daily_state()`: `self._stale_retry_count.clear()` 추가

## 문서 동기화 (TDD 사이클 종료 후 별도)
- `src/realtime/CLAUDE.md` 또는 `src/engine/CLAUDE.md` `_stale_watcher_loop` 1~2줄
- 루트 `CLAUDE.md` 핵심 안전 규칙 추가

## 절대 금지
- git commit/add/push 금지 (워킹 트리에만)
- `_subscriptions` set 직접 수정 금지 — `_send_subscribe`/`subscribe`/`unsubscribe` 메서드만
- 6회 초과 skip 가드 누락 금지 (무한 루프 차단)
- finally 블록 task cancel 누락 금지
