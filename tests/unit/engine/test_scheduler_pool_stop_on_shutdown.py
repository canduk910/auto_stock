"""사이클 13-E Red — scheduler 종료 시 kis_ws_pool.stop() 호출 회귀 가드.

진단 (`_workspace/cycle13e_shutdown_pool_cleanup_spec.md` §2 원인 2/3):

원인 2 — `src/engine/scheduler.py:488-492` (정상 종료):
    await kis_ws.disconnect()    # ← 메인만 disconnect
    try:
        await ws_task
    except asyncio.CancelledError:
        pass
    # 여기에 `await kis_ws_pool.stop()` 호출 누락

원인 3 — `src/engine/scheduler.py:604-605` (수동 중지 `stop()`):
    await unsubscribe_all()
    await kis_ws.disconnect()
    await write_log("INFO", "매매 시스템 수동 중지")
    # 여기에 `await kis_ws_pool.stop()` 호출 누락

본 테스트는 두 종료 경로 (정상 finally + 수동 stop()) 모두에서
``kis_ws_pool.stop()`` 이 호출되는지 검증한다.

Red 단계:
- 현재 scheduler 코드에는 ``kis_ws_pool.stop()`` 호출 자체가 없음 → 본 테스트 모두 fail
- Green Patch 2 (정상 finally) + Patch 3 (수동 stop) 추가 후 통과

안전 가드 (CLAUDE.md):
- 체결통보 분기 (H0STCNI0/H0STCNI9) 영향 없음 — disconnect 만 검증
- ``_subscriptions`` set 직접 수정 금지 — 모든 mock 객체로 격리
- 메인 disconnect 호출 순서 보존 — pool.stop() 보다 *먼저* 호출되는지 verify
  (시나리오 E — 자금 안전 핵심)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Test B-1 — 수동 중지 `stop()` 시 pool.stop() 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manual_stop_invokes_pool_stop_after_main_disconnect():
    """``scheduler.stop()`` 가 ``kis_ws.disconnect()`` *후* ``kis_ws_pool.stop()`` 도 호출.

    명세 §2 원인 3 (수동 중지 경로):
    ``await unsubscribe_all() → await kis_ws.disconnect() → ?? → write_log``
    여기서 ``kis_ws_pool.stop()`` 호출 누락. Green Patch 3 적용 후 통과.

    호출 순서 보장 (자금 안전): kis_ws.disconnect() (메인) 가 pool.stop() (보조) *전*
    호출 — 시나리오 E 의 회귀 가드.
    """
    sched = TradingScheduler()
    sched._running = True

    # 모든 백그라운드 task None — finally 정리 분기 우회
    for attr in ("_next_day_task", "_session_task", "_stale_watcher_task", "_swing_poll_task"):
        setattr(sched, attr, None)

    call_order: list[str] = []

    async def _record_main_disconnect():
        call_order.append("main_disconnect")

    async def _record_pool_stop():
        call_order.append("pool_stop")

    async def _record_unsubscribe_all():
        call_order.append("unsubscribe_all")

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock(side_effect=_record_main_disconnect)

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock(side_effect=_record_pool_stop)

    with patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock(side_effect=_record_unsubscribe_all)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched.stop()

    # 호출 검증
    main_ws.disconnect.assert_awaited_once()
    fake_pool.stop.assert_awaited_once()

    # 순서 검증 — main disconnect 가 pool stop 보다 *먼저*
    assert "main_disconnect" in call_order, f"메인 disconnect 호출 누락: {call_order}"
    assert "pool_stop" in call_order, (
        f"수동 stop() 에서 kis_ws_pool.stop() 호출 누락 — "
        f"보조 세션 잔존 결함. 호출 순서: {call_order}"
    )
    assert call_order.index("main_disconnect") < call_order.index("pool_stop"), (
        f"메인 disconnect 가 풀 stop 보다 *먼저* 호출돼야 함 (자금 안전). "
        f"실제 순서: {call_order}"
    )


# ---------------------------------------------------------------------------
# Test B-2 — 수동 중지 시 pool.stop 예외가 main disconnect 흐름 중단 안 함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manual_stop_pool_exception_does_not_block_shutdown():
    """``kis_ws_pool.stop()`` 이 예외 raise 해도 ``write_log("INFO", "매매 시스템 수동 중지")``
    도달 verify.

    명세 시나리오 E (보조 stop 예외 흡수):
    > 보조 stop() 실패가 메인 종료 흐름을 막아선 안 됨.
    > write_log("INFO", "매매 시스템 종료") 가 도달 가능.

    Green Patch 3 의 try/except 흡수 가드 필수.
    """
    sched = TradingScheduler()
    sched._running = True

    for attr in ("_next_day_task", "_session_task", "_stale_watcher_task", "_swing_poll_task"):
        setattr(sched, attr, None)

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock(side_effect=RuntimeError("보조 세션 disconnect 실패"))

    write_log_mock = AsyncMock()

    with patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", write_log_mock):
        # 예외가 stop() 흐름을 중단시키면 안 됨
        await sched.stop()

    # 메인 disconnect 는 호출됐어야 함
    main_ws.disconnect.assert_awaited_once()
    # 풀 stop 도 호출 시도됐어야 함
    fake_pool.stop.assert_awaited_once()
    # write_log("INFO", "매매 시스템 수동 중지") 도달 verify
    write_log_calls = [c.args for c in write_log_mock.await_args_list]
    assert any(
        len(args) >= 2 and args[0] == "INFO" and "수동 중지" in args[1]
        for args in write_log_calls
    ), (
        f"수동 중지 종료 로그 미도달 — pool.stop 예외가 종료 흐름을 중단시킴. "
        f"write_log 호출 인자들: {write_log_calls}"
    )


# ---------------------------------------------------------------------------
# Test B-3 — 정상 finally 종료 경로에서 pool.stop() 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_normal_shutdown_finally_invokes_pool_stop():
    """정상 종료 finally 블록에서 ``kis_ws_pool.stop()`` 호출 verify.

    명세 §2 원인 2 (정상 종료 경로) + §4 Patch 2 (반드시 finally 배치):
    > Patch 2 는 반드시 `finally` 블록 안 — 또는 try/except 외부에서 정상·비정상 종료
    > 둘 다 통과하는 경로 — 에 둬야 한다.

    검증 방법: scheduler.start() 가 _boot() 진입 즉시 ``CancelledError`` raise 하도록
    유도 → try 본문이 끊긴 채 finally 블록 도달 → pool.stop() 호출 verify.

    Red 단계: 현재 finally 블록에 ``kis_ws_pool.stop()`` 호출이 없음 → fail.
    """
    sched = TradingScheduler()

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock()
    fake_pool.start = AsyncMock()

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()

    # _boot() 가 즉시 CancelledError raise → try 본문 끊김 → finally 도달
    async def _boot_raises():
        raise RuntimeError("boot 실패 (시뮬레이션)")

    with patch.object(sched, "_boot", side_effect=_boot_raises), \
         patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()), \
         patch("src.engine.scheduler.register_tick_handler"), \
         patch("src.engine.scheduler.register_execution_handler"), \
         patch("src.engine.scheduler.register_board_handler"):
        # start() 가 RuntimeError 흡수 후 finally 통과
        await sched.start()

    # 비정상 종료 경로 (try 본문 raise) → finally 도달 → pool.stop() 호출
    fake_pool.stop.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# Test B-4 — finally 의 pool.stop 예외도 흡수 (비정상 종료 시 종료 메시지 도달)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_normal_shutdown_finally_pool_exception_does_not_block_log():
    """finally 블록의 ``pool.stop()`` 이 예외 raise 해도 ``write_log("INFO", "매매 시스템 종료")``
    가 도달.

    명세 §4 Green Patch 2:
    > try:
    >     await kis_ws_pool.stop()
    > except Exception:
    >     logger.warning("[scheduler_shutdown] pool.stop 실패", exc_info=True)

    회귀 가드: try/except 흡수 누락 시 finally 마지막 라인 ``write_log("INFO", "매매 시스템 종료")``
    가 도달 안 함 → 정상 종료 추적 가시성 손실.
    """
    sched = TradingScheduler()

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock(side_effect=RuntimeError("풀 정리 실패"))
    fake_pool.start = AsyncMock()

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()

    write_log_mock = AsyncMock()

    async def _boot_raises():
        raise RuntimeError("boot 실패 (시뮬레이션)")

    with patch.object(sched, "_boot", side_effect=_boot_raises), \
         patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", write_log_mock), \
         patch("src.engine.scheduler.register_tick_handler"), \
         patch("src.engine.scheduler.register_execution_handler"), \
         patch("src.engine.scheduler.register_board_handler"):
        # pool.stop 예외가 finally 흐름을 중단시키면 안 됨
        await sched.start()

    # pool.stop 호출 시도됐어야 함
    fake_pool.stop.assert_awaited_once()
    # write_log("INFO", "매매 시스템 종료") 도달 verify
    write_log_calls = [c.args for c in write_log_mock.await_args_list]
    assert any(
        len(args) >= 2 and args[0] == "INFO" and "매매 시스템 종료" in args[1]
        for args in write_log_calls
    ), (
        f"finally 의 매매 시스템 종료 로그 미도달 — pool.stop 예외가 finally 흐름을 중단시킴. "
        f"write_log 호출 인자들: {write_log_calls}"
    )
