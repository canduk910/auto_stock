"""사이클 79 Red — `stop()` 호출 시 `_api_recovered_collector_task` 의
실제 cancel + await + setattr None lifecycle 검증 (asyncio mock 기반).

명세 (`_workspace/red/cycle79_task_cancel_guard.md`):

정적 grep (G-CC1/G-CC2/G-CC3) 외에 *실제 호출 시점에 task lifecycle 동작* 을 검증.
사이클 13-E-1 `test_scheduler_stop_task_cancel.py` 패턴 직답습 (8 task 통합 루프
중 신규 1종 `_api_recovered_collector_task` 검증).

기대 동작 (Green):
- `done()=False` 인 `_api_recovered_collector_task` mock 주입 후 `stop()` 호출
  → cancel() 호출 1회 + await 1회 + setattr None 1회

Red 단계:
- 현재 `stop()` task_attrs 튜플에 `_api_recovered_collector_task` 미포함
  → cancel() 호출 0회 → FAIL.

안전 가드 (CLAUDE.md):
- WebSocket 4중 안전망 / 매도 안전성 / 사이클 17 KIS LMS chain 영역 무관
- 운영 영향 0 (lifecycle 정리만)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit


def _fake_task(*, done: bool = False) -> MagicMock:
    """``asyncio.Task`` 인터페이스 일부를 흉내내는 mock task.

    사이클 13-E-1 `test_scheduler_stop_task_cancel.py::_fake_task` 직답습.
    """
    task = MagicMock()
    task.done = MagicMock(return_value=done)
    task.cancel = MagicMock()

    def _await_gen():
        if False:
            yield  # pragma: no cover
        return None

    task.__await__ = lambda: _await_gen()
    return task


# ---------------------------------------------------------------------------
# G-LC1 — stop() 호출 시 _api_recovered_collector_task cancel + setattr None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_lc1_stop_cancels_api_recovered_collector_task():
    """G-LC1: `stop()` 호출 시 `_api_recovered_collector_task` 가 cancel() + await
    + setattr(None) 처리되어야 한다 — 좀비 task 0 보장.

    검증:
    - active mock (done()=False) 주입
    - stop() 호출 후:
      1. task.cancel() 호출 1회
      2. sched._api_recovered_collector_task 가 None 으로 재대입

    Red 상태: 현재 `stop()` 의 task_attrs 튜플 (L860~865) 에
    `_api_recovered_collector_task` 미포함 → cancel() 호출 0회 + attribute 보존
    → FAIL.

    Green: backend-dev 가 task_attrs 튜플에 추가 → cancel 1회 + None 재대입 → PASS.
    """
    sched = TradingScheduler()
    sched._running = True

    # 사이클 79 검증 대상 task 단독 주입 (다른 task 는 None — getattr None 분기)
    fake_collector_task = _fake_task(done=False)
    sched._api_recovered_collector_task = fake_collector_task

    # 다른 task 는 None 으로 설정 (getattr None → skip 분기)
    for attr in (
        "_next_day_task", "_session_task", "_stale_watcher_task",
        "_session_health_task",
        "_swing_poll_task", "_swing_rest_poll_task",
        "_5xx_dedupe_summary_task",
        "_ws_task", "_scan_task",
    ):
        setattr(sched, attr, None)

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock()

    with patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()), \
         patch("src.engine.scheduler.flush_swing_rest_poll_collector",
               new=MagicMock()), \
         patch("src.engine.stale_watcher_core.flush_stale_watcher_collector",
               new=MagicMock()):
        await sched.stop()

    # 1. cancel() 호출 1회 (사이클 13-E-1 통합 루프 패턴)
    assert fake_collector_task.cancel.call_count == 1, (
        f"\n사이클 79 G-LC1 위반 — `_api_recovered_collector_task.cancel()` "
        f"호출 누락:\n"
        f"  현재 호출 횟수: {fake_collector_task.cancel.call_count} (= 1 필요)\n\n"
        f"  사이클 76 commit (0d633a8) 도입 시 `stop()` task_attrs 튜플\n"
        f"  (L860~865) 추가 누락 → 좀비 task 잠재 위험 (사이클 78 부차 발견).\n\n"
        f"  사이클 42 `_heartbeat_metrics_loop` 좀비 task 패턴 답습 (영구 가드)."
    )

    # 2. setattr(None) 재대입 (사이클 13-E-1 패턴 — `if not task.done()` 분기 외부)
    assert sched._api_recovered_collector_task is None, (
        f"\n사이클 79 G-LC1 위반 — `_api_recovered_collector_task` attribute 가 "
        f"None 으로 재대입되지 않음:\n"
        f"  현재값: {sched._api_recovered_collector_task!r}\n\n"
        f"  사이클 13-E-1 명세: `setattr(self, task_attr, None)` 는 done() 여부와 "
        f"  무관하게 무조건 수행."
    )
