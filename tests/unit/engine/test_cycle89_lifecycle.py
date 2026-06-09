"""사이클 89 M-1 — `_universe_eager_refresh_task` lifecycle 검증 (asyncio mock).

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

사이클 79 G-LC1 (`test_cycle79_task_lifecycle.py`) + 사이클 83 G-LC1
(`test_cycle83_task_lifecycle.py`) 직답습 패턴.

기대 동작 (Green, 사이클 90):
- `done()=False` 인 `_universe_eager_refresh_task` mock 주입 후 `stop()` 호출
  → cancel() 호출 1회 + setattr None 1회

Red 단계 (사이클 89):
- 현재 `stop()` task_attrs 튜플에 `_universe_eager_refresh_task` 미포함
  → cancel() 호출 0회 + attribute 보존 → FAIL.

안전 가드 (CLAUDE.md):
- WebSocket 4중 안전망 / 매도 안전성 / 사이클 17 KIS LMS chain 영역 무관
- 운영 영향 0 (lifecycle 정리만, 매매 hot path 무관)
- 사이클 38 명문화 영속 (`tradable_boards` 영향 0)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit


def _fake_task(*, done: bool = False) -> MagicMock:
    """``asyncio.Task`` 인터페이스 일부를 흉내내는 mock task.

    사이클 79/83 G-LC1 `_fake_task` 직답습.
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
# M-1 — stop() 호출 시 _universe_eager_refresh_task cancel + setattr None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_m1_stop_cancels_universe_eager_refresh_task():
    """M-1: `stop()` 호출 시 `_universe_eager_refresh_task` 가 cancel() + await
    + setattr(None) 처리되어야 한다 — 좀비 task 0 보장 (사이클 79/83 G-LC1 답습).

    검증:
    - active mock (done()=False) 주입
    - stop() 호출 후:
      1. task.cancel() 호출 1회
      2. sched._universe_eager_refresh_task 가 None 으로 재대입

    Red 상태 (사이클 89): 현재 `stop()` 의 task_attrs 튜플에
    `_universe_eager_refresh_task` 미포함 → cancel() 호출 0회 + attribute 보존
    → FAIL.

    Green (사이클 90): backend-dev 가 task_attrs 튜플에 추가 + 신규 task
    구조 도입 → cancel 1회 + None 재대입 → PASS.
    """
    sched = TradingScheduler()
    sched._running = True

    # 사이클 89 검증 대상 task 단독 주입
    fake_eager_task = _fake_task(done=False)
    sched._universe_eager_refresh_task = fake_eager_task

    # 다른 task 는 None 으로 설정 (getattr None → skip 분기)
    for attr in (
        "_next_day_task", "_session_task", "_stale_watcher_task",
        "_session_health_task",
        "_swing_poll_task", "_swing_rest_poll_task",
        "_5xx_dedupe_summary_task",
        "_api_recovered_collector_task",  # 사이클 79 영속
        "_scan_pool_eager_refresh_task",  # 사이클 83 영속
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

    # 1. cancel() 호출 1회 (사이클 79/83 G-LC1 패턴 답습)
    assert fake_eager_task.cancel.call_count == 1, (
        f"\n사이클 89 M-1 위반 — `_universe_eager_refresh_task.cancel()` "
        f"호출 누락:\n"
        f"  현재 호출 횟수: {fake_eager_task.cancel.call_count} (= 1 필요)\n\n"
        f"  사이클 89 신규 task `_universe_eager_refresh_task` 도입 의무\n"
        f"  → stop() task_attrs 튜플 추가 의무 (사이클 79 G-AST1 패턴 답습).\n\n"
        f"  Green 시정 (사이클 90 backend-dev): scheduler.py::stop() 의 \n"
        f"  task_attrs 튜플에 `\"_universe_eager_refresh_task\"` 추가.\n"
        f"  사이클 42 `_heartbeat_metrics_loop` 좀비 task 패턴 답습 (영구 가드)."
    )

    # 2. setattr(None) 재대입 (사이클 13-E-1 패턴)
    assert sched._universe_eager_refresh_task is None, (
        f"\n사이클 89 M-1 위반 — `_universe_eager_refresh_task` attribute 가 "
        f"None 으로 재대입되지 않음:\n"
        f"  현재값: {sched._universe_eager_refresh_task!r}\n\n"
        f"  사이클 13-E-1 명세: `setattr(self, task_attr, None)` 는 done() 여부와 "
        f"  무관하게 무조건 수행."
    )
