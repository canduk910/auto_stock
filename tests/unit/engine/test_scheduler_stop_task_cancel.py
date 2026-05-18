"""사이클 13-E-1 Red — 수동 `stop()` 의 task 5종 cancel 통일 검증.

명세 (`_workspace/cycle13e_shutdown_pool_cleanup_spec.md` §4 Patch 3, §8 Test F):

PR #12 Copilot 리뷰 ② — `src/engine/scheduler.py:621` 위치에서 발견된 누락:
현재 ``stop()`` 의 task cancel 목록은 4종 (`_next_day_task`, `_session_task`,
`_stale_watcher_task`, `_swing_poll_task`) 으로 ``_swing_rest_poll_task`` 가 누락.
``start()`` 가 생성하는 백그라운드 task 5종 중 마지막 1종을 cancel 하지 않으면
``disconnect()`` / ``kis_ws_pool.stop()`` 이후 REST 폴링이 한 사이클 더 돌거나
close 된 자원에 접근하며 예외 로그가 발생할 수 있다.

기대 동작 (Green Patch 3):
- ``stop()`` 의 task cancel 목록을 finally 와 동일한 5종 패턴으로 통일:
  ``(_next_day_task, _session_task, _stale_watcher_task, _swing_poll_task,
    _swing_rest_poll_task)``
- 각 task: ``cancel() → await → setattr(None)`` 동일 처리
- cancel 위치는 ``unsubscribe_all() / kis_ws.disconnect() / kis_ws_pool.stop()``
  *이전* — 폴링이 종료된 후 자원 해제 순서 유지

Red 단계:
- 현재 `stop()` 의 task cancel 목록 ( `src/engine/scheduler.py:605`) 에
  ``_swing_rest_poll_task`` 가 빠져있음 → Test F-1 fail.
- 호출 순서 검증 (cancel 5종이 unsubscribe_all/disconnect/pool.stop 이전) →
  ``_swing_rest_poll_task`` 만 누락된 상태에서는 Test F-2 의 cancel 부분이 fail.

안전 가드 (CLAUDE.md):
- 체결통보 분기 (H0STCNI0/H0STCNI9) 무관 — task cancel 만 검증
- ``_subscriptions`` set 직접 수정 금지 — mock 객체로 격리
- 메인→보조 순서 보존 (자금 안전 핵심)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — 가짜 background task
# ---------------------------------------------------------------------------
def _fake_task(*, done: bool = False) -> MagicMock:
    """``asyncio.Task`` 인터페이스 일부를 흉내내는 mock task.

    - ``done()`` → 호출 시점 상태 반환 (기본 False)
    - ``cancel()`` → MagicMock (호출 추적)
    - ``await task`` 지원: ``__await__`` 가 yield 없이 즉시 반환하도록 generator 위임

    Patch 3 검증에서 task 객체 자체를 await 하는 흐름 (`try: await task`) 을 통과해야 하므로
    awaitable 로 동작해야 한다.
    """
    task = MagicMock()
    task.done = MagicMock(return_value=done)
    task.cancel = MagicMock()

    # ``await task`` 가 즉시 None 반환하도록 generator 기반 __await__ 구현
    def _await_gen():
        if False:
            yield  # pragma: no cover — generator 표식
        return None

    task.__await__ = lambda: _await_gen()
    return task


# ---------------------------------------------------------------------------
# Test F-1 — stop() 호출 시 task 5종 (특히 _swing_rest_poll_task) cancel + setattr None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stop_cancels_all_five_tasks_including_swing_rest_poll():
    """Red: ``scheduler.stop()`` 이 백그라운드 task 5종을 모두 cancel 해야 한다 — 현재 코드에서 fail.

    명세 §4 Patch 3 — finally 와 동일한 5종 목록:
    - ``_next_day_task``
    - ``_session_task``
    - ``_stale_watcher_task``
    - ``_swing_poll_task``
    - ``_swing_rest_poll_task``  ← **현재 누락**

    Red 상태: 현재 `stop()` 의 cancel 목록 (`scheduler.py:605`) 에
    ``_swing_rest_poll_task`` 가 없음 → 마지막 task 의 cancel() 가 호출되지 않음 + None
    재대입도 안 됨 → 이 테스트의 cancel/setattr assert 가 fail.
    """
    sched = TradingScheduler()
    sched._running = True

    # 5종 task 모두 active mock 으로 주입 — done()=False → cancel() 호출돼야 함
    task_attrs = [
        "_next_day_task",
        "_session_task",
        "_stale_watcher_task",
        "_swing_poll_task",
        "_swing_rest_poll_task",
    ]
    fake_tasks = {name: _fake_task(done=False) for name in task_attrs}
    for name, task in fake_tasks.items():
        setattr(sched, name, task)

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock()

    with patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched.stop()

    # 5종 모두 cancel() 호출 검증 — 핵심은 마지막 _swing_rest_poll_task
    for name, task in fake_tasks.items():
        assert task.cancel.call_count == 1, (
            f"task {name} cancel() 호출 누락 (호출 횟수: {task.cancel.call_count}). "
            f"명세 §4 Patch 3 — finally 와 동일한 5종 목록 통일 필수."
        )
        # setattr(self, name, None) 으로 재대입 검증
        assert getattr(sched, name) is None, (
            f"task {name} attribute 가 None 으로 재대입되지 않음 — 현재값: {getattr(sched, name)}. "
            f"명세 §4 Patch 3 — cancel + await + setattr None 동일 처리."
        )


# ---------------------------------------------------------------------------
# Test F-2 — cancel 위치가 unsubscribe_all / disconnect / pool.stop 이전
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stop_cancels_tasks_before_resource_cleanup():
    """Red: ``stop()`` 의 task cancel 5종이 ``unsubscribe_all()`` / ``kis_ws.disconnect()`` /
    ``kis_ws_pool.stop()`` 보다 *먼저* 호출돼야 한다 — 현재 코드에서 fail (5종 중 1종 누락).

    명세 §4 Patch 3 중요:
    > task cancel 은 `unsubscribe_all()`/`disconnect()`/`pool.stop()` *이전* 에 수행 —
    > 폴링 task 가 종료된 후 자원 해제 순서 유지.

    Red 상태: 현재 코드는 4종만 cancel → ``_swing_rest_poll_task`` 가 cancel 되기 *전* 에
    disconnect/pool.stop 이 발화 → 폴링이 한 사이클 더 돌 가능. 본 테스트는
    "_swing_rest_poll_task.cancel 가 disconnect 보다 *먼저*" 라는 assert 가 fail.
    """
    sched = TradingScheduler()
    sched._running = True

    call_order: list[str] = []

    task_attrs = [
        "_next_day_task",
        "_session_task",
        "_stale_watcher_task",
        "_swing_poll_task",
        "_swing_rest_poll_task",
    ]
    fake_tasks: dict[str, MagicMock] = {}
    for name in task_attrs:
        task = _fake_task(done=False)
        # cancel 호출 시 순서 기록 — task 이름 그대로
        task.cancel = MagicMock(side_effect=lambda n=name: call_order.append(f"cancel:{n}"))
        fake_tasks[name] = task
        setattr(sched, name, task)

    async def _record_unsubscribe_all():
        call_order.append("unsubscribe_all")

    async def _record_main_disconnect():
        call_order.append("main_disconnect")

    async def _record_pool_stop():
        call_order.append("pool_stop")

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock(side_effect=_record_main_disconnect)

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock(side_effect=_record_pool_stop)

    with patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.engine.scheduler.unsubscribe_all",
               new=AsyncMock(side_effect=_record_unsubscribe_all)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched.stop()

    # 모든 5종 cancel 이 unsubscribe_all/disconnect/pool_stop *이전* 에 호출
    resource_markers = ("unsubscribe_all", "main_disconnect", "pool_stop")
    for marker in resource_markers:
        assert marker in call_order, (
            f"자원 정리 호출 누락: {marker}. 호출 순서: {call_order}"
        )

    for name in task_attrs:
        cancel_marker = f"cancel:{name}"
        assert cancel_marker in call_order, (
            f"task {name} cancel 누락 — 현재 5종 중 1종 (특히 _swing_rest_poll_task) 미반영. "
            f"호출 순서: {call_order}"
        )
        cancel_idx = call_order.index(cancel_marker)
        for marker in resource_markers:
            marker_idx = call_order.index(marker)
            assert cancel_idx < marker_idx, (
                f"task {name} cancel 이 {marker} 이후 호출됨 — "
                f"폴링이 자원 정리 후 한 사이클 더 돌 위험. 호출 순서: {call_order}"
            )


# ---------------------------------------------------------------------------
# Test F-3 — 이미 done() 인 task 는 cancel skip 하되 setattr None 은 수행
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stop_done_tasks_skip_cancel_but_clear_attr():
    """Red: ``done()=True`` 인 task 는 cancel() 호출 skip 하되 attribute 는 None 재대입.

    명세 §4 Patch 3 코드 패턴:
    ```python
    task = getattr(self, task_attr, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    setattr(self, task_attr, None)  # done() 여부와 무관하게 None 재대입
    ```

    Red 상태: 현재 코드는 4종만 처리 → ``_swing_rest_poll_task`` 가 done()=True 라도
    None 재대입이 안 됨 (attribute 자체를 건드리지 않음) → 본 테스트의
    "5종 모두 None" assert 가 fail.
    """
    sched = TradingScheduler()
    sched._running = True

    task_attrs = [
        "_next_day_task",
        "_session_task",
        "_stale_watcher_task",
        "_swing_poll_task",
        "_swing_rest_poll_task",
    ]
    # 모두 done() = True 로 주입
    fake_tasks = {name: _fake_task(done=True) for name in task_attrs}
    for name, task in fake_tasks.items():
        setattr(sched, name, task)

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock()
    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock()

    with patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched.stop()

    # done()=True 이므로 cancel() 호출은 0회여야 함 (skip)
    for name, task in fake_tasks.items():
        assert task.cancel.call_count == 0, (
            f"done()=True 인 task {name} 의 cancel() 가 호출됨 ({task.cancel.call_count}회). "
            f"명세 §4 Patch 3 — `if task and not task.done():` 가드 필수."
        )
        # setattr(None) 은 done() 여부와 무관하게 수행돼야 함
        assert getattr(sched, name) is None, (
            f"done()=True 인 task {name} 의 attribute 가 None 으로 재대입되지 않음 "
            f"— 현재값: {getattr(sched, name)}. "
            f"명세 §4 Patch 3 — setattr(None) 은 done() 분기 외부 (무조건 수행)."
        )
