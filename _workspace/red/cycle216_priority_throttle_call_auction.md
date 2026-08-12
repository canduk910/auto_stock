# cycle216 Red — resubscribe_stale_priority 동시호가 LOW-scoped skip + LOW-only throttle

- 파일: `tests/unit/engine/stale_manager/test_cycle216_priority_throttle_call_auction.py` (7 케이스)
- 대상: `src/engine/stale_watcher_core.py::resubscribe_stale_priority` (376-509)
- 삽입 위치: 466-467 low_targets 계산 후, 477 targets 조립 전 (A 동시호가 → B throttle 순)
- 상수: 모듈 레벨 `RESUBSCRIBE_THROTTLE_SECS = 3 * STALE_FRESHNESS_SECS`(=180) — 반드시 < 300
- RED 확인(현 코드): T1/T3/T6/T7 FAIL, T2/T4/T5 PASS (불변 가드)
  - T1 FAIL: session_tracker 미참조 → LOW 재구독 `['005930','035420','035720']`
  - T3 FAIL: throttle 부재 → 035420(now-100s) 재구독
  - T6 FAIL: `RESUBSCRIBE_THROTTLE_SECS` 상수 부재
  - T7 FAIL: throttle 부재 → cap 이 미필터 LOW(000001~) 먼저 소비
- Green 인계: backend-dev (stale_watcher_core.py 단독, 8영역 무접촉)
