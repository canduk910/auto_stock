"""사이클 13-E-1 Red — scheduler 종료 finally 의 메인 disconnect best-effort 보강 검증.

명세 (`_workspace/cycle13e_shutdown_pool_cleanup_spec.md` §4 Patch 2, §8 Test E):

PR #12 Copilot 리뷰 ① — `src/engine/scheduler.py:519` 위치에서 발견된 누수:
``start()`` 본문이 488 라인의 ``await kis_ws.disconnect()`` *전* 에 예외를 raise 하면
``except Exception`` → ``finally`` 진입은 되지만 메인 WebSocket 이 연결된 채 잔존.
24h 토큰 만료 후 다음 _boot 진입 시 동일 계정 중복 접속 위험.

기대 동작 (Green Patch 2):
- finally 블록 안, ``kis_ws_pool.stop()`` *전* 위치에 ``await kis_ws.disconnect()``
  best-effort 호출 (try/except 흡수 + WARNING `[scheduler_shutdown]` prefix)
- ``KisWebSocket.disconnect()`` 는 idempotent (`src/realtime/websocket.py:163-169`
  ``if self._ws:`` 가드 + ``self._ws = None`` nullify) — 정상 경로 두 번째 호출은 noop
- 호출 순서: ``kis_ws.disconnect()`` (메인) → ``kis_ws_pool.stop()`` (보조) 절대 보존

Red 단계:
- 현재 finally 에는 메인 disconnect best-effort 호출이 없음. ``start()`` 본문 488 라인
  도달 *전* 예외 raise 시나리오에서 ``kis_ws.disconnect()`` 가 단 1회만 호출 → Test E-1 fail.

안전 가드 (CLAUDE.md):
- 체결통보 분기 (H0STCNI0/H0STCNI9) 무관 — disconnect 만 검증
- ``_subscriptions`` set 직접 수정 금지 — mock 객체로 격리
- 메인→보조 순서 보존 (자금 안전 핵심)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Test E-1 — start() 본문 예외 시 finally 에서 메인 disconnect best-effort 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_start_exception_triggers_main_disconnect_in_finally():
    """Red: ``start()`` 본문이 488 라인 도달 *전* 예외 raise 시 finally 의
    ``kis_ws.disconnect()`` best-effort 호출이 발화해야 한다 — 현재 코드에서 fail 해야 함.

    명세 시나리오 G:
    1. ``start()`` 본문 ``_boot()`` 단계에서 의도적 예외 raise (488 라인 도달 못함)
    2. except 분기 → finally 진입
    3. finally 에서 ``kis_ws.disconnect()`` best-effort 호출 verify
    4. 호출 순서 ``disconnect → pool.stop`` 보장 (메인→보조 자금 안전 핵심)

    Red 상태: 현재 finally 블록에는 메인 disconnect 호출 자체가 없음 → fail.
    Green Patch 2 후 통과.
    """
    sched = TradingScheduler()

    call_order: list[str] = []

    async def _record_main_disconnect():
        call_order.append("main_disconnect")

    async def _record_pool_stop():
        call_order.append("pool_stop")

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock(side_effect=_record_main_disconnect)
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock(side_effect=_record_pool_stop)
    fake_pool.start = AsyncMock()

    # _boot() 가 즉시 예외 raise → try 본문 488 라인 도달 *못함* → finally 만 통과
    async def _boot_raises():
        raise RuntimeError("boot 실패 (시뮬레이션 — 488 라인 도달 전)")

    with patch.object(sched, "_boot", side_effect=_boot_raises), \
         patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()), \
         patch("src.engine.scheduler.register_tick_handler"), \
         patch("src.engine.scheduler.register_execution_handler"), \
         patch("src.engine.scheduler.register_board_handler"):
        # start() 가 RuntimeError 흡수 후 finally 통과
        await sched.start()

    # 488 라인 도달 못함 → try 본문 disconnect 호출 0회 → finally 가 유일한 호출 경로
    main_ws.disconnect.assert_awaited()  # ≥1회 (Patch 2 적용 시 finally 1회)
    fake_pool.stop.assert_awaited_once()

    # 호출 순서 검증 — main_disconnect 가 pool_stop 보다 *먼저*
    assert "main_disconnect" in call_order, (
        f"finally 의 메인 disconnect best-effort 호출 누락 — "
        f"비정상 종료 시 메인 WebSocket 자원 누수. 호출 순서: {call_order}"
    )
    assert "pool_stop" in call_order, (
        f"finally 의 pool.stop 호출 누락. 호출 순서: {call_order}"
    )
    assert call_order.index("main_disconnect") < call_order.index("pool_stop"), (
        f"finally 에서 메인 disconnect 가 풀 stop 보다 *먼저* 호출돼야 함 "
        f"(자금 안전 — 메인→보조 순서). 실제 순서: {call_order}"
    )


# ---------------------------------------------------------------------------
# Test E-2 — 정상 경로 disconnect 2회 호출이지만 close 부작용 1회만 (idempotent)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_normal_path_main_disconnect_idempotent_two_calls():
    """Red: 정상 경로에서 try 본문 + finally = 메인 disconnect 가 총 2회 호출되지만,
    ``KisWebSocket.disconnect()`` 가 idempotent (`_ws` nullify 후 두 번째 호출은 close skip)
    이므로 close 부작용은 1회만 발생해야 한다 — 현재 코드에서 fail 해야 함.

    명세 §4 Patch 2:
    > 정상 경로: try `kis_ws.disconnect()` → `self._ws = None` → finally
    > `kis_ws.disconnect()` 진입 시 `if self._ws:` False → noop. 회귀 0.

    검증 방법: ``MagicMock.disconnect`` 가 await 될 때 2회 호출됨을 verify.
    실제 idempotent 보장은 ``src/realtime/websocket.py`` 측 분리 검증 — 본 테스트는
    "scheduler 가 try + finally 두 곳에서 호출한다" 만 검증.

    Red 상태: 현재 finally 에 disconnect 호출 자체가 없어 2회 호출 자체가 일어나지 않음 → fail.
    Green Patch 2 후 try 1회 + finally 1회 = 2회 await 확인 통과.
    """
    sched = TradingScheduler()

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.start = AsyncMock()
    fake_pool.stop = AsyncMock()

    # 정상 경로 시뮬레이션 — _boot 직후 try 분기 즉시 끝나도록 _wait_until 가짜로
    # bypass. 정상 종료 시퀀스에서는 488 라인 ``await kis_ws.disconnect()`` 1회 발화 +
    # finally 도 1회 → 총 2회 await 가 기대값. 488 라인 도달을 위해 _boot 정상 + 이후
    # 무한 루프 회피 위해 ``_settle`` 직후 자연 종료 흐름이 필요.
    #
    # 단순화: ``_boot`` 직후 488 라인 도달을 강제하려면 try 본문 구조 전체를 통과해야 함.
    # 본 테스트는 "정상 종료" 흐름의 외부 관찰 가능 시그널 (write_log "매매 시스템 종료"
    # + disconnect 2회 await) 만 검증 — try 본문 분기를 정확히 따라가는 통합 검증은
    # tester 가 시나리오 G 회귀로 담당.
    #
    # Red 보장: 본 테스트는 _boot 가 raise 안 하는 정상 흐름을 시뮬레이트하는 대신
    # try 본문이 자연 종료되는 mock 으로 _boot 만 정상 + 이후 모든 시간 분기를 skip.
    # 현재 코드의 try 본문 488 라인 ``await kis_ws.disconnect()`` 1회 + finally 0회 =
    # 총 1회 await → assert 2회 fail (Red).

    async def _boot_noop():
        return None

    async def _settle_noop():
        return None

    # 모든 시간 분기를 강제 통과하기 위해 _wait_until 패치
    async def _wait_noop(*args, **kwargs):
        return None

    with patch.object(sched, "_boot", side_effect=_boot_noop), \
         patch.object(sched, "_settle", side_effect=_settle_noop), \
         patch.object(sched, "_wait_until", side_effect=_wait_noop, create=True), \
         patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()), \
         patch("src.engine.scheduler.register_tick_handler"), \
         patch("src.engine.scheduler.register_execution_handler"), \
         patch("src.engine.scheduler.register_board_handler"), \
         patch("src.engine.scheduler.asyncio.create_task", side_effect=lambda coro: _close_coro(coro)):
        # start() 가 정상 흐름으로 종료될 수 있도록 _wait_until 가 모두 즉시 반환 →
        # try 본문이 자연 통과되어 488 라인 disconnect 1회 + finally 1회 = 총 2회 기대.
        try:
            await sched.start()
        except Exception:
            # 정상 경로 시뮬레이션 실패 시 흐름 보존 (Red 시 try 본문 진입 자체가
            # 막혀도 finally 가 호출돼야 한다는 명세는 본 테스트의 핵심)
            pass

    # Green Patch 2 후 기대값: 메인 disconnect 가 try (488 라인) + finally 양쪽에서
    # 호출 → 총 ≥2회. Red 상태에서는 try 1회만 (혹은 _wait_until 우회 실패 시 0회) → fail.
    call_count = main_ws.disconnect.await_count
    assert call_count >= 2, (
        f"정상 경로에서 메인 disconnect 가 try (488 라인) + finally 양쪽 호출돼 총 ≥2회 "
        f"기대 (idempotent 검증). 실제 await 횟수: {call_count}. "
        f"finally 의 best-effort disconnect 호출 누락."
    )


def _close_coro(coro):
    """create_task 모킹용 — coroutine 을 즉시 close 해 RuntimeWarning 회피.

    `asyncio.create_task` 패치 시 인자로 들어온 coroutine 객체가 await 되지 못해
    "coroutine was never awaited" 경고가 발생하는 것을 차단한다. 본 테스트는 task
    내부 동작을 검증하지 않으므로 close 로 안전 폐기.
    """
    try:
        coro.close()
    except Exception:
        pass
    dummy = MagicMock()
    dummy.cancel = MagicMock()
    dummy.done = MagicMock(return_value=True)
    return dummy


# ---------------------------------------------------------------------------
# Test E-3 — finally 의 disconnect 가 예외 raise 해도 pool.stop 도달 verify
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_finally_main_disconnect_exception_does_not_block_pool_stop():
    """Red: finally 의 ``kis_ws.disconnect()`` best-effort 가 예외를 raise 해도
    그 *후* 의 ``kis_ws_pool.stop()`` 이 정상 도달해야 한다 — 현재 코드에서 fail 해야 함.

    명세 §4 Patch 2:
    > try:
    >     await kis_ws.disconnect()
    > except Exception:
    >     logger.warning("[scheduler_shutdown] main disconnect 실패 (best-effort)", exc_info=True)

    try/except 흡수가 누락되면 finally 의 ``write_log("INFO", "매매 시스템 종료")`` 와
    ``kis_ws_pool.stop()`` 모두 도달 불가 → 보조 세션 잔존 + 종료 가시성 손실.

    Red 상태: 현재 finally 에 메인 disconnect 호출 자체가 없음 → 예외 흡수 가드 미존재 →
    Green Patch 2 추가 후 try/except 로 흡수해야 통과.
    """
    sched = TradingScheduler()

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock(side_effect=RuntimeError("메인 disconnect 실패"))
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock()
    fake_pool.start = AsyncMock()

    write_log_mock = AsyncMock()

    # _boot 가 raise → finally 진입
    async def _boot_raises():
        raise RuntimeError("boot 실패")

    with patch.object(sched, "_boot", side_effect=_boot_raises), \
         patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", write_log_mock), \
         patch("src.engine.scheduler.register_tick_handler"), \
         patch("src.engine.scheduler.register_execution_handler"), \
         patch("src.engine.scheduler.register_board_handler"):
        # finally 의 메인 disconnect 예외가 흐름을 막아선 안 됨
        await sched.start()

    # 메인 disconnect 가 finally 에서 호출 시도됐어야 함 (raise 흡수 후)
    main_ws.disconnect.assert_awaited()
    # 그 후 pool.stop 도 도달했어야 함
    fake_pool.stop.assert_awaited_once()
    # 정상 종료 로그 도달 (try/except 가드 정상 동작)
    write_log_calls = [c.args for c in write_log_mock.await_args_list]
    assert any(
        len(args) >= 2 and args[0] == "INFO" and "매매 시스템 종료" in args[1]
        for args in write_log_calls
    ), (
        f"finally 의 메인 disconnect 예외가 종료 흐름을 중단시킴 — "
        f"try/except 흡수 가드 누락. write_log 호출 인자들: {write_log_calls}"
    )
