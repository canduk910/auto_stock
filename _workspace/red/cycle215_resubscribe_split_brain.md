# cycle215 Red — resubscribe_stale_priority split-brain 재구독 결함

- **의도**: 개장러시 풀 포화 → HIGH 보유 tick 구독이 OPSP0008 거부 → 세션 `_subscriptions` discard(websocket.py:716) 되나 풀 `_ticker_to_session[t]=main` 잔존(split-brain) → `resubscribe_stale_priority`(stale_watcher_core.py:489)가 `unsubscribe_in_pool` 없이 `subscribe(HIGH)` 직접 호출 → 풀 dedup 가드(`existing is self._main → return "main"`)에 걸려 재SEND 0건 = 온종일 손절 사각. 실측 001450(donchian)·053800(kojiro) 09:05/09:07 매수 후 14:23 미구독.
- **시정 방향(backend-dev)**: stale_watcher_core.py:489 `subscribe` *앞*에 `await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)` + `await asyncio.sleep(0.05)` 추가(K watcher 342-347 패턴 이식). HIGH/LOW 공통.
- **파일**: `tests/unit/engine/stale_manager/test_cycle215_resubscribe_split_brain.py`
- **RED 결과 (현재 코드)**: 5 FAIL + 1 PASS.
  - GS-1 FAIL: `unsubscribe_in_pool.await_count == 0` (subscribe 앞 팝 미발생).
  - GS-2 FAIL(실경로): 진짜 WebsocketPool+가짜세션 → `실제 세션 subscribe 호출: []` (dedup 가드로 재SEND 0건, `_subscriptions` 공집합 잔존).
  - GS-4 FAIL: LOW 후보도 `unsubscribe_in_pool` 미호출(HIGH/LOW 공통 미적용).
  - GS-5 FAIL: unsubscribe_in_pool 호출 부재로 시그니처 단언 미충족.
  - GS-6 FAIL(AST): `resubscribe_stale_priority` 본체에 `.unsubscribe_in_pool(` 부재.
  - GS-3 PASS(불변): 현재도 subscribe 는 HIGH/bypass=True → 시정 후 불변 가드.
- **8영역 diff 0**: stale_watcher_core.py 는 realtime/ 미포함 = 8영역 아님. 테스트는 realtime/ 수정 미요구.
- **G-REJECT-1 무충돌**: 4함수 존재 가드는 함수 제거가 아닌 내부 보강이라 무관(확인).
