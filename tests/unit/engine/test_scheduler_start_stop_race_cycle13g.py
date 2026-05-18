"""사이클 13-G Red — `start()` / `stop()` 동시성 race 가드 검증.

명세 (`_workspace/cycle13g_start_stop_race_guard_spec.md` §4 + §5 + §8):

PR #12 Copilot 추가 리뷰 2건. 13-E-2 에서 `_ws_task` / `_scan_task` 를 self.*
속성으로 승격하고 13-E-3 에서 `stop()` 의 task cancel 루프를 7종으로 통일한
이후, **`start()` 본문 자체가 `self._scan_task` / `self._ws_task` 를 직접
참조하는 4 곳 (line 408~409, 491~495)** 의 race 안전성이 평가되지 않았다.

race window:
- line 408 `await self._wait_until(TIME_KRX_MAIN_BUY_STOP)` — 수 시간 대기.
  그 사이 `/api/trading/stop` 호출 → `_scan_task = None` → 재개 시 line 409
  `self._scan_task.cancel()` 가 None 참조 → **AttributeError**.
- line 491 `await kis_ws.disconnect()` — 네트워크 IO yield.
  그 사이 `/api/trading/stop` 호출 → `_ws_task = None` → 재개 시 line 493
  `await self._ws_task` → **TypeError: object NoneType can't be used in 'await'**.

기대 동작 (Green Patch A/B — backend-dev 가 별도 적용):
- Patch A (line 408~409): `if self._scan_task is not None and not self._scan_task.done():
                            self._scan_task.cancel()`
- Patch B (line 491~495): 로컬 캡처 + None 가드:
                          ```
                          _ws_task = self._ws_task
                          if _ws_task is not None:
                              try:
                                  await _ws_task
                              except asyncio.CancelledError:
                                  pass
                          ```

Red 단계:
- O-1 (race AttributeError): 현재 코드 → fail (`except Exception` 진입 →
  `write_log("ERROR", "매매 프로세스 비정상 종료")` 호출 → assert_not_called fail).
- P-1 (race TypeError): 현재 코드 → fail (동일 매커니즘).
- O-2 / P-2 정상 회귀: stop 미발화 + 정상 cancel/await → PASS (의도된 PASS).

race 동기화 전략:
- `asyncio.Event` 를 통해 start() 의 yield point (`_wait_until` 또는
  `kis_ws.disconnect`) 와 stop() 의 7종 cancel 루프 (`_*_task = None` 재대입)
  가 정확한 순서로 진행되도록 강제:
    1. start() 가 yield 지점 진입 → event 미설정 → 무한 대기
    2. 별도 task 에서 stop() 호출 → 7종 task cancel + setattr None 완료
    3. stop() 가 진행 도중 event.set() → start() yield 해제
    4. start() 재개 시 self.*_task 는 이미 None 인 상태

안전 가드 (CLAUDE.md / 명세 §6):
- scheduler.py 구현부 수정 금지 (Green 은 backend-dev 담당)
- 체결통보 분기 (H0STCNI0/H0STCNI9) 무관
- `_subscriptions` 직접 수정 금지 — mock 객체로 격리
- 메인 disconnect 순서 보존 (자금 안전 핵심)
- start() task 생성 위치 (line 247/405/411/431/432/444/445) 변경 금지
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.engine.scheduler import TIME_KRX_MAIN_BUY_STOP, TradingScheduler

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — 가짜 asyncio.Task
# ---------------------------------------------------------------------------
class _FakeTask:
    """`asyncio.Task` 인터페이스 일부를 흉내내는 클래스 기반 가짜 task.

    `start()` 본문은 line 493 에서 ``await self._ws_task`` 를 수행한다 — Python 의
    dunder lookup 은 **타입에서** `__await__` 를 찾으므로 MagicMock 인스턴스에
    `__await__` 를 할당해도 `await mock_instance` 는 TypeError. 따라서 클래스 기반
    awaitable 로 정상 경로 (Test P-2) 와 race 경로 (Test O-1) 둘 다 안전하게 처리.

    `test_scheduler_zombie_task_cleanup.py` 의 MagicMock + lambda 패턴은 본문에서
    실제 await 가 호출되지 않는 시나리오 (예외 흐름) 에서만 동작 — 본 사이클은
    정상 경로 line 493 의 ``await self._ws_task`` 를 검증해야 하므로 클래스 기반.
    """

    def __init__(self, *, done: bool = False) -> None:
        self._done = done
        # MagicMock 으로 호출 추적 가능
        self.cancel = MagicMock()

    def done(self) -> bool:
        return self._done

    def __await__(self):
        if False:
            yield  # pragma: no cover — generator 표식
        return None


def _fake_task(*, done: bool = False) -> _FakeTask:
    """가짜 task 인스턴스 생성 헬퍼 — 기존 `_fake_task` 시그니처 호환."""
    return _FakeTask(done=done)


def _close_coro_factory():
    """asyncio.create_task 모킹용 — coroutine 을 close 후 fake task 반환.

    첫 호출(=ws_task)만 race 검증용 fake_ws_task 를 반환하도록 closure 로 관리.
    """
    state = {"n": 0, "ws_task": None, "scan_task": None}

    def _create_task_side_effect(coro):
        try:
            coro.close()
        except Exception:
            pass
        state["n"] += 1
        coro_name = getattr(coro, "__qualname__", "") or getattr(coro, "__name__", "")
        # 첫 호출은 ws_task (line 247)
        if state["n"] == 1:
            state["ws_task"] = _fake_task(done=False)
            return state["ws_task"]
        # `_scan_loop` coroutine 은 scan_task
        if "_scan_loop" in coro_name and state["scan_task"] is None:
            state["scan_task"] = _fake_task(done=False)
            return state["scan_task"]
        # 그 외 background task (session/stale/swing/swing_rest/next_day) 는 done 더미
        return _fake_task(done=True)

    return _create_task_side_effect, state


def _build_common_patches(sched, main_ws, fake_pool, create_task_side_effect,
                          *, wait_until_side_effect, disconnect_side_effect):
    """O/P 4 시나리오 공통 patch 묶음. ExitStack 으로 풀어 사용.

    - 6 `_collect_*` / `_build_*` / `scan_stocks` / `subscribe_filtered_stocks` 등
      `start()` 본문 진행을 위한 의존 함수들을 noop / 빈 결과로 치환.
    - `_confirm_breakout_open_prices` / `_force_clear_main_only` /
      `_drain_pending_next_day_clear` / `_settle` / `_reset_daily_state` 도 noop.
    - 자문/로그분석 모듈 import 차단을 위해 `sched._settle` 까지 noop.
    """

    async def _async_noop(*args, **kwargs):
        return None

    async def _boot_noop():
        return None

    main_ws.disconnect = AsyncMock(side_effect=disconnect_side_effect) \
        if disconnect_side_effect else AsyncMock()

    patches = [
        patch.object(sched, "_boot", side_effect=_boot_noop),
        patch.object(sched, "_wait_until",
                     side_effect=wait_until_side_effect, create=True),
        patch.object(sched, "_confirm_breakout_open_prices",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_force_clear_main_only",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_drain_pending_next_day_clear",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_settle", side_effect=_async_noop, create=True),
        patch.object(sched, "_reset_daily_state", create=True),
        patch.object(sched, "_collect_breakout_tickers", return_value=[]),
        patch.object(sched, "_collect_swing_tickers", return_value=[]),
        patch.object(sched, "_collect_presubscribe_tickers", return_value=[]),
        patch.object(sched, "_build_subscription_source_counts", return_value={}),
        patch.object(sched, "_build_priority_groups", return_value={}),
        patch("src.engine.scheduler.scan_stocks",
              new=AsyncMock(return_value=[])),
        patch("src.engine.scheduler.subscribe_filtered_stocks",
              new=AsyncMock()),
        patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()),
        patch("src.engine.scheduler.kis_ws", main_ws),
        patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool),
        patch("src.engine.scheduler.register_tick_handler"),
        patch("src.engine.scheduler.register_execution_handler"),
        patch("src.engine.scheduler.register_board_handler"),
        patch("src.engine.scheduler.asyncio.create_task",
              side_effect=create_task_side_effect),
        patch("src.engine.scheduler.asyncio.sleep", new=AsyncMock()),
    ]
    return patches


# ---------------------------------------------------------------------------
# Test O-1 — `_wait_until(15:20)` 대기 중 stop() race → AttributeError 0건
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_scan_task_cancel_guard_during_stop_race():
    """Red: ``start()`` 가 line 408 ``await self._wait_until(TIME_KRX_MAIN_BUY_STOP)``
    에서 대기 중일 때 외부에서 ``stop()`` 호출 → ``_scan_task = None`` 재대입 →
    재개 시 line 409 ``self._scan_task.cancel()`` 가 **None 안전 가드** 로
    AttributeError 발생 0건 + ``write_log("ERROR", "매매 프로세스 비정상 종료")``
    호출 0건이어야 한다.

    현재 코드 (Patch A 적용 전) 에서 fail —
    무가드 ``self._scan_task.cancel()`` → ``AttributeError: 'NoneType' has no
    attribute 'cancel'`` → ``except Exception:`` → ``write_log("ERROR", ...)`` 1회.

    race 동기화:
    - ``asyncio.Event`` (``wait_event``) — start() 가 ``_wait_until`` 진입 시 wait,
      stop() 의 7종 cancel 루프가 ``_scan_task = None`` 까지 setattr 완료한 직후
      이 event.set() 으로 start() 재개. 재개 시 line 409 에 도달.
    - ``stop_ready_event`` — start() 가 ``_wait_until`` 에 진입했음을 stop() 측에
      알려 race window 시작 시점 동기화 (사전 setattr None 누락 방지).
    """
    sched = TradingScheduler()

    # race 동기화 이벤트
    stop_ready_event = asyncio.Event()  # start()→stop(): wait_until 진입 신호
    resume_event = asyncio.Event()      # stop()→start(): _scan_task = None 완료 신호

    write_log_mock = AsyncMock()

    main_ws = MagicMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()
    # disconnect 도 호출될 수 있음 (finally) — 단순 AsyncMock 으로 충분
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.start = AsyncMock()
    fake_pool.stop = AsyncMock()

    create_task_side_effect, ct_state = _close_coro_factory()

    async def _wait_until_race(target_time, *args, **kwargs):
        """TIME_KRX_MAIN_BUY_STOP 에서만 race 시뮬레이션, 그 외는 noop."""
        if target_time == TIME_KRX_MAIN_BUY_STOP:
            # start() 가 line 408 진입했음을 stop 측에 알림
            stop_ready_event.set()
            # stop() 의 setattr(_scan_task, None) 완료 대기 후 재개 → line 409
            await resume_event.wait()
            return None
        return None

    patches = _build_common_patches(
        sched, main_ws, fake_pool, create_task_side_effect,
        wait_until_side_effect=_wait_until_race,
        disconnect_side_effect=None,
    )
    patches.append(patch("src.engine.scheduler.write_log", new=write_log_mock))

    async def _trigger_stop_when_ready():
        """start() 가 _wait_until 진입할 때까지 기다린 뒤 stop() 호출 + resume."""
        await stop_ready_event.wait()
        # 7종 cancel 루프 직접 시뮬레이션 (실제 sched.stop() 의 핵심 부수효과만 재현):
        # `self._scan_task = None` 재대입 + `self._running = False`
        # 실 stop() 을 호출하면 unsubscribe_all/disconnect 가 추가로 호출되어 검증이
        # 복잡해진다. 명세 §1-3 다이어그램의 핵심 부수효과 (setattr None) 만 재현.
        sched._scan_task = None
        sched._running = False
        # start() 재개 — race 가드 검증 시점
        resume_event.set()

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        # start() 와 stop trigger 를 병렬로 실행
        await asyncio.gather(sched.start(), _trigger_stop_when_ready())

    # ===== 핵심 검증 (Red — 현재 코드에서 fail) =====
    # 1. ``write_log("ERROR", "매매 프로세스 비정상 종료")`` 호출 0건
    #    → AttributeError 가 except Exception 분기에 진입한 흔적
    error_calls = [
        c for c in write_log_mock.call_args_list
        if len(c.args) >= 2
        and c.args[0] == "ERROR"
        and "매매 프로세스 비정상 종료" in str(c.args[1])
    ]
    assert error_calls == [], (
        f"매매 프로세스 비정상 종료 ERROR 로그 호출 발생 — "
        f"line 408~409 race 가드 부재 (Patch A 미적용). "
        f"호출 내역: {error_calls}. "
        f"명세 §3-1 — system_logs ERROR 오기록 시 20:10 일일 로그 분석 false-positive."
    )

    # 2. ws_task 는 정상 생성되었으나, scan_task 는 race 로 stop() 에 의해 None.
    #    finally 진입 시 _scan_task 는 None 으로 유지 (stop() 가 이미 처리).
    assert getattr(sched, "_scan_task", "MISSING") is None, (
        f"_scan_task 가 race 후 None 이 아님 — 현재값: "
        f"{getattr(sched, '_scan_task', 'MISSING')}. stop() 의 setattr None 흔적."
    )


# ---------------------------------------------------------------------------
# Test O-2 — 정상 흐름: _wait_until(15:20) 종료 후 _scan_task.cancel() 정상
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_scan_task_cancel_normal_path():
    """정상 회귀 가드 (의도된 PASS): stop() 호출 없이 자연 흐름 —
    ``_wait_until(15:20)`` 즉시 종료 → line 409 ``self._scan_task.cancel()``
    정상 호출 + ``_force_clear_main_only()`` 진입.

    명세 §5 Test O-2 — Patch A 가드가 들어가도 정상 경로에서 기존 동작 보존
    (`is not None and not done()` → True → cancel() 호출).

    의도: 현재 코드 + Green Patch A 둘 다에서 PASS. 본 테스트는 Patch A 이
    cancel() 자체를 막아버리는 회귀 (예: 가드 조건 오타) 를 차단.
    """
    sched = TradingScheduler()

    main_ws = MagicMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.start = AsyncMock()
    fake_pool.stop = AsyncMock()

    create_task_side_effect, ct_state = _close_coro_factory()

    force_clear_called = {"v": False}

    async def _wait_until_noop(*args, **kwargs):
        return None

    async def _force_clear_main_only_recorder():
        force_clear_called["v"] = True

    async def _async_noop(*args, **kwargs):
        return None

    # _wait_until 은 즉시 종료 → line 409 cancel → 그 후 _force_clear_main_only 진입
    # 단, 진행 후속의 20:00 generate_recommendations / 20:10 settle / disconnect
    # 까지 가야 finally 진입 — 마지막 _wait_until 들도 noop 처리.

    write_log_mock = AsyncMock()

    patches = [
        patch.object(sched, "_boot", side_effect=_async_noop),
        patch.object(sched, "_wait_until",
                     side_effect=_wait_until_noop, create=True),
        patch.object(sched, "_confirm_breakout_open_prices",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_force_clear_main_only",
                     side_effect=_force_clear_main_only_recorder, create=True),
        patch.object(sched, "_drain_pending_next_day_clear",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_settle", side_effect=_async_noop, create=True),
        patch.object(sched, "_reset_daily_state", create=True),
        patch.object(sched, "_collect_breakout_tickers", return_value=[]),
        patch.object(sched, "_collect_swing_tickers", return_value=[]),
        patch.object(sched, "_collect_presubscribe_tickers", return_value=[]),
        patch.object(sched, "_build_subscription_source_counts", return_value={}),
        patch.object(sched, "_build_priority_groups", return_value={}),
        patch("src.engine.scheduler.scan_stocks",
              new=AsyncMock(return_value=[])),
        patch("src.engine.scheduler.subscribe_filtered_stocks",
              new=AsyncMock()),
        patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()),
        patch("src.engine.scheduler.kis_ws", main_ws),
        patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool),
        patch("src.engine.scheduler.write_log", new=write_log_mock),
        patch("src.engine.scheduler.register_tick_handler"),
        patch("src.engine.scheduler.register_execution_handler"),
        patch("src.engine.scheduler.register_board_handler"),
        patch("src.engine.scheduler.asyncio.create_task",
              side_effect=create_task_side_effect),
        patch("src.engine.scheduler.asyncio.sleep", new=AsyncMock()),
        # 20:00 자문 / 20:10 일일 로그 분석 모듈 import 차단 (Settle/log_analysis_engine)
        patch("src.engine.recommendation_engine.generate_recommendations",
              new=AsyncMock(), create=True),
        patch("src.engine.log_analysis_engine.generate_daily_log_report",
              new=AsyncMock(), create=True),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        await sched.start()

    # ===== 정상 회귀 검증 =====
    # 1. scan_task 가 생성되고 cancel() 이 line 409 (또는 line 445) 에서 호출됨
    scan_task = ct_state["scan_task"]
    assert scan_task is not None, (
        "scan_task (line 405 create_task(_scan_loop)) 가 생성되지 않음 — "
        "정상 흐름이 line 405 도달 못함. mock 설정 점검 필요."
    )
    # line 409 에서 1회 + line 445 (NXT 애프터 종료) 에서 가능. 둘 다 정상.
    assert scan_task.cancel.call_count >= 1, (
        f"scan_task.cancel() 호출 누락 — 현재 호출 횟수: "
        f"{scan_task.cancel.call_count}. line 409 정상 경로 cancel 부재."
    )

    # 2. _force_clear_main_only() 정상 진입 (line 417)
    assert force_clear_called["v"] is True, (
        "_force_clear_main_only() 호출 누락 — line 409 cancel 후 line 417 진입 실패. "
        "AttributeError 등으로 except Exception 분기 진입 의심."
    )

    # 3. ERROR 로그 0건 (정상 흐름이므로 write_log("ERROR", ...) 호출 없음)
    error_calls = [
        c for c in write_log_mock.call_args_list
        if len(c.args) >= 2
        and c.args[0] == "ERROR"
        and "매매 프로세스 비정상 종료" in str(c.args[1])
    ]
    assert error_calls == [], (
        f"정상 흐름에서 ERROR 로그 발생 — 현재 호출: {error_calls}."
    )


# ---------------------------------------------------------------------------
# Test P-1 — `await kis_ws.disconnect()` 중 stop() race → TypeError 0건
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_ws_task_await_guard_during_stop_race():
    """Red: ``start()`` 가 line 491 ``await kis_ws.disconnect()`` 에서 yield 중
    외부 ``stop()`` 호출 → ``_ws_task = None`` 재대입 → 재개 시 line 493
    ``await self._ws_task`` 가 **로컬 캡처 + None 가드** 로 TypeError 0건 +
    ``write_log("ERROR", "매매 프로세스 비정상 종료")`` 호출 0건이어야 한다.

    현재 코드 (Patch B 적용 전) 에서 fail —
    무가드 ``await self._ws_task`` → ``TypeError: object NoneType can't be used in
    'await' expression`` → ``except CancelledError:`` 미포착 → ``except Exception:``
    → ``write_log("ERROR", ...)`` 1회.

    race 동기화:
    - ``disconnect`` 가 ``stop_ready_event.set()`` 후 ``resume_event.wait()`` 로 yield.
    - 별도 task 에서 stop() 의 setattr(_ws_task, None) 시뮬레이션 후 resume.set().
    """
    sched = TradingScheduler()

    stop_ready_event = asyncio.Event()  # start()→stop(): disconnect 진입 신호
    resume_event = asyncio.Event()      # stop()→start(): _ws_task = None 완료 신호

    write_log_mock = AsyncMock()

    main_ws = MagicMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()

    async def _disconnect_race():
        """kis_ws.disconnect() yield 시뮬레이션 — stop() 의 setattr None 완료까지 대기."""
        stop_ready_event.set()
        await resume_event.wait()
        return None

    main_ws.disconnect = AsyncMock(side_effect=_disconnect_race)

    fake_pool = MagicMock()
    fake_pool.start = AsyncMock()
    fake_pool.stop = AsyncMock()

    create_task_side_effect, ct_state = _close_coro_factory()

    async def _wait_until_noop(*args, **kwargs):
        return None

    async def _async_noop(*args, **kwargs):
        return None

    patches = [
        patch.object(sched, "_boot", side_effect=_async_noop),
        patch.object(sched, "_wait_until",
                     side_effect=_wait_until_noop, create=True),
        patch.object(sched, "_confirm_breakout_open_prices",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_force_clear_main_only",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_drain_pending_next_day_clear",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_settle", side_effect=_async_noop, create=True),
        patch.object(sched, "_reset_daily_state", create=True),
        patch.object(sched, "_collect_breakout_tickers", return_value=[]),
        patch.object(sched, "_collect_swing_tickers", return_value=[]),
        patch.object(sched, "_collect_presubscribe_tickers", return_value=[]),
        patch.object(sched, "_build_subscription_source_counts", return_value={}),
        patch.object(sched, "_build_priority_groups", return_value={}),
        patch("src.engine.scheduler.scan_stocks",
              new=AsyncMock(return_value=[])),
        patch("src.engine.scheduler.subscribe_filtered_stocks",
              new=AsyncMock()),
        patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()),
        patch("src.engine.scheduler.kis_ws", main_ws),
        patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool),
        patch("src.engine.scheduler.write_log", new=write_log_mock),
        patch("src.engine.scheduler.register_tick_handler"),
        patch("src.engine.scheduler.register_execution_handler"),
        patch("src.engine.scheduler.register_board_handler"),
        patch("src.engine.scheduler.asyncio.create_task",
              side_effect=create_task_side_effect),
        patch("src.engine.scheduler.asyncio.sleep", new=AsyncMock()),
        patch("src.engine.recommendation_engine.generate_recommendations",
              new=AsyncMock(), create=True),
        patch("src.engine.log_analysis_engine.generate_daily_log_report",
              new=AsyncMock(), create=True),
    ]

    async def _trigger_stop_when_disconnect_yields():
        """disconnect() 가 yield 했을 때 stop() 의 setattr None 시뮬레이션."""
        await stop_ready_event.wait()
        # 명세 §1-3 다이어그램 — 7종 cancel 루프 핵심 부수효과: _ws_task = None
        sched._ws_task = None
        sched._running = False
        resume_event.set()

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        await asyncio.gather(
            sched.start(),
            _trigger_stop_when_disconnect_yields(),
        )

    # ===== 핵심 검증 (Red — 현재 코드에서 fail) =====
    # 1. ``write_log("ERROR", "매매 프로세스 비정상 종료")`` 호출 0건
    #    → TypeError 가 except Exception 분기에 진입한 흔적
    error_calls = [
        c for c in write_log_mock.call_args_list
        if len(c.args) >= 2
        and c.args[0] == "ERROR"
        and "매매 프로세스 비정상 종료" in str(c.args[1])
    ]
    assert error_calls == [], (
        f"매매 프로세스 비정상 종료 ERROR 로그 호출 발생 — "
        f"line 491~495 race 가드 부재 (Patch B 미적용). "
        f"호출 내역: {error_calls}. "
        f"명세 §3-1 — TypeError(await None) → except Exception → ERROR 오기록."
    )

    # 2. _ws_task 는 race 로 stop() 에 의해 None 재대입
    assert getattr(sched, "_ws_task", "MISSING") is None, (
        f"_ws_task 가 race 후 None 이 아님 — 현재값: "
        f"{getattr(sched, '_ws_task', 'MISSING')}. stop() 의 setattr None 흔적."
    )

    # 3. disconnect 는 정상 호출됨 (race window 의 yield point)
    main_ws.disconnect.assert_awaited()


# ---------------------------------------------------------------------------
# Test P-2 — 정상 흐름: _ws_task 정상 await + CancelledError 흡수
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_ws_task_await_normal_path():
    """정상 회귀 가드 (의도된 PASS): stop() 호출 없이 자연 종료 —
    line 491 ``await kis_ws.disconnect()`` 종료 후 line 493
    ``await self._ws_task`` 가 정상 완료 + CancelledError 흡수.

    명세 §5 Test P-2 — Patch B 가드가 들어가도 정상 경로에서 기존 동작 보존
    (`_ws_task = self._ws_task` 로컬 캡처 → not None → await → CancelledError 흡수).

    의도: 현재 코드 + Green Patch B 둘 다에서 PASS. 본 테스트는 Patch B 가
    await 자체를 막아버리는 회귀 (예: 가드 조건 오타) 를 차단.
    """
    sched = TradingScheduler()

    main_ws = MagicMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()
    main_ws.disconnect = AsyncMock()  # 즉시 완료 (race 없음)

    fake_pool = MagicMock()
    fake_pool.start = AsyncMock()
    fake_pool.stop = AsyncMock()

    create_task_side_effect, ct_state = _close_coro_factory()

    async def _wait_until_noop(*args, **kwargs):
        return None

    async def _async_noop(*args, **kwargs):
        return None

    write_log_mock = AsyncMock()

    patches = [
        patch.object(sched, "_boot", side_effect=_async_noop),
        patch.object(sched, "_wait_until",
                     side_effect=_wait_until_noop, create=True),
        patch.object(sched, "_confirm_breakout_open_prices",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_force_clear_main_only",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_drain_pending_next_day_clear",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_settle", side_effect=_async_noop, create=True),
        patch.object(sched, "_reset_daily_state", create=True),
        patch.object(sched, "_collect_breakout_tickers", return_value=[]),
        patch.object(sched, "_collect_swing_tickers", return_value=[]),
        patch.object(sched, "_collect_presubscribe_tickers", return_value=[]),
        patch.object(sched, "_build_subscription_source_counts", return_value={}),
        patch.object(sched, "_build_priority_groups", return_value={}),
        patch("src.engine.scheduler.scan_stocks",
              new=AsyncMock(return_value=[])),
        patch("src.engine.scheduler.subscribe_filtered_stocks",
              new=AsyncMock()),
        patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()),
        patch("src.engine.scheduler.kis_ws", main_ws),
        patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool),
        patch("src.engine.scheduler.write_log", new=write_log_mock),
        patch("src.engine.scheduler.register_tick_handler"),
        patch("src.engine.scheduler.register_execution_handler"),
        patch("src.engine.scheduler.register_board_handler"),
        patch("src.engine.scheduler.asyncio.create_task",
              side_effect=create_task_side_effect),
        patch("src.engine.scheduler.asyncio.sleep", new=AsyncMock()),
        patch("src.engine.recommendation_engine.generate_recommendations",
              new=AsyncMock(), create=True),
        patch("src.engine.log_analysis_engine.generate_daily_log_report",
              new=AsyncMock(), create=True),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        await sched.start()

    # ===== 정상 회귀 검증 =====
    # 1. ws_task 가 line 247 에서 생성됨
    ws_task = ct_state["ws_task"]
    assert ws_task is not None, (
        "ws_task (line 247 create_task(kis_ws.connect)) 가 생성되지 않음 — "
        "정상 흐름이 line 247 도달 못함. mock 설정 점검 필요."
    )

    # 2. disconnect 정상 호출 (line 491)
    main_ws.disconnect.assert_awaited()

    # 3. ERROR 로그 0건 (정상 흐름)
    error_calls = [
        c for c in write_log_mock.call_args_list
        if len(c.args) >= 2
        and c.args[0] == "ERROR"
        and "매매 프로세스 비정상 종료" in str(c.args[1])
    ]
    assert error_calls == [], (
        f"정상 흐름에서 ERROR 로그 발생 — 현재 호출: {error_calls}."
    )

    # 4. finally 정리 — ws_task / scan_task 모두 None 재대입
    assert getattr(sched, "_ws_task", "MISSING") is None, (
        f"_ws_task 가 정상 종료 후 None 재대입되지 않음 — "
        f"현재값: {getattr(sched, '_ws_task', 'MISSING')}. "
        f"finally 7종 cancel 루프 회귀 (13-E-2)."
    )
