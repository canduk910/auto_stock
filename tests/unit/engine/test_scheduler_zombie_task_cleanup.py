"""사이클 13-E-2 Red — start() 로컬 task lifecycle 좀비 차단 회귀 가드.

명세 (`_workspace/cycle13e2_zombie_task_spec.md` §4 + §5 + §8):

PR #12 Copilot 두 번째 리뷰 — `src/engine/scheduler.py:519` 위치에서 발견된 누수:
``start()`` 본문이 244 라인 ``ws_task = asyncio.create_task(kis_ws.connect(...))``
와 402 라인 ``scan_task = asyncio.create_task(self._scan_loop())`` 를 **로컬 변수**
로 보유. try 본문 중간 (244 ~ 488) 에서 예외 raise 시 finally 진입 시점에
이 두 task 가 **unreachable** — cancel/await 경로 부재 → 좀비 task.

기대 동작 (Green Patch 1~4 — backend-dev 가 별도 적용):
- Patch 1: `__init__` 에 `self._ws_task = None` + `self._scan_task = None` 추가
- Patch 2~3: 244 / 402 / 408 / 428 / 441 / 490 의 모든 로컬 참조 self.* 화
- Patch 4: finally 루프 task_attr tuple 에 `_ws_task` + `_scan_task` 2종 추가
  (정리 순서 보존: task cancel → main disconnect → pool stop)

Red 단계:
- 현재 코드는 로컬 변수 → `sched._ws_task` / `sched._scan_task` attribute 자체가 부재 →
  `assert getattr(sched, "_ws_task", "MISSING") is not "MISSING"` 류 검증 fail.
- J-1 / J-2 — 좀비 task cancel 검증이 핵심 (Red 필수)
- J-3 / J-4 / J-5 — 일부는 Green 전에도 PASS 가능 (현재 attribute 부재 자체로 인해
  setattr None / done() 가드 분기를 타지 않음). docstring 에 의도된 PASS 명시.

안전 가드 (CLAUDE.md):
- 체결통보 (H0STCNI0/H0STCNI9) 분기 무관 — task lifecycle 만 검증
- ``_subscriptions`` set 직접 수정 금지 — mock 객체로 격리
- 메인→보조 순서 보존 (자금 안전 핵심) — 13-E + 13-E-1 회귀 가드는 별도 파일
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — 가짜 asyncio.Task
# ---------------------------------------------------------------------------
def _fake_task(*, done: bool = False) -> MagicMock:
    """``asyncio.Task`` 인터페이스 일부를 흉내내는 mock task.

    - ``done()`` → 호출 시점 상태 반환 (기본 False)
    - ``cancel()`` → MagicMock (호출 추적)
    - ``await task`` 지원: ``__await__`` 가 즉시 None 반환하도록 generator 위임

    13-E-1 의 ``test_scheduler_stop_task_cancel.py`` 패턴을 그대로 따른다.
    """
    task = MagicMock()
    task.done = MagicMock(return_value=done)
    task.cancel = MagicMock()

    def _await_gen():
        if False:
            yield  # pragma: no cover — generator 표식
        return None

    task.__await__ = lambda: _await_gen()
    return task


def _close_coro(coro):
    """asyncio.create_task 모킹용 — coroutine 을 close 해 RuntimeWarning 회피.

    13-E-1 의 ``test_scheduler_finally_main_disconnect.py`` 와 동일 패턴.
    """
    try:
        coro.close()
    except Exception:
        pass
    dummy = _fake_task(done=False)
    return dummy


# ---------------------------------------------------------------------------
# Test J-1 — line 244 직후 예외 → self._ws_task cancel + self._scan_task None skip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_exception_after_ws_task_creation_cancels_ws_task_and_skips_scan_task():
    """Red: ``start()`` 본문 line 244 (`ws_task` 생성) 직후 + line 402 (`scan_task` 생성)
    *전* 단계에서 예외 raise 시, finally 가:

    1. ``self._ws_task.cancel()`` + ``await`` (CancelledError 흡수) verify
    2. ``self._scan_task is None`` 상태에서 AttributeError 없이 skip verify
    3. 13-E-1 의 메인 disconnect best-effort + ``kis_ws_pool.stop()`` 도달 verify

    현재 코드 (변경 전) 에서 fail 해야 함 — ``ws_task`` 가 로컬 변수라 ``sched._ws_task``
    속성 자체가 부재. fake_ws_task.cancel 호출이 일어나지 않음 → assert fail.

    시뮬레이션: line 269 ``kis_ws.subscribe(cni_tr_id, cni_tr_key)`` 가 raise →
    외부 ``except Exception`` → finally. line 244 의 ws_task 는 이미 생성된 상태.
    line 402 scan_task 는 미생성 (line 269 < line 402).
    """
    sched = TradingScheduler()

    # 메인 disconnect 호출 순서 기록
    call_order: list[str] = []

    main_ws = MagicMock()
    main_ws.connect = AsyncMock()
    # 핵심: kis_ws.subscribe 가 raise — line 269 에서 발화. ws_task 는 이미 생성된 상태.
    main_ws.subscribe = AsyncMock(side_effect=RuntimeError(
        "subscribe 실패 (시뮬레이션 — line 244 직후, line 402 이전)"))

    async def _record_main_disconnect():
        call_order.append("main_disconnect")
    main_ws.disconnect = AsyncMock(side_effect=_record_main_disconnect)

    fake_pool = MagicMock()

    async def _record_pool_stop():
        call_order.append("pool_stop")
    fake_pool.stop = AsyncMock(side_effect=_record_pool_stop)
    fake_pool.start = AsyncMock()

    # asyncio.create_task 패치 — line 244 의 `kis_ws.connect(dispatch_message)` 를
    # 즉시 close + fake task 반환. Green 적용 후 scheduler 코드가 self._ws_task 에 대입
    # 하면 sched._ws_task 가 이 fake_task 가 됨. 후속 create_task (session_task /
    # stale_watcher_task / swing_poll_task / swing_rest_poll_task) 는 더미.
    fake_ws_task = _fake_task(done=False)
    create_task_calls = {"n": 0}

    def _create_task_side_effect(coro):
        try:
            coro.close()
        except Exception:
            pass
        create_task_calls["n"] += 1
        if create_task_calls["n"] == 1:
            return fake_ws_task
        return _fake_task(done=True)  # 후속 task 들은 done 으로 finally 가드 통과

    async def _boot_noop():
        return None

    # asyncio.sleep 도 noop (line 258 의 sleep(2) 회피)
    async def _sleep_noop(*args, **kwargs):
        return None

    with patch.object(sched, "_boot", side_effect=_boot_noop), \
         patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()), \
         patch("src.engine.scheduler.register_tick_handler"), \
         patch("src.engine.scheduler.register_execution_handler"), \
         patch("src.engine.scheduler.register_board_handler"), \
         patch("src.engine.scheduler.asyncio.create_task",
               side_effect=_create_task_side_effect), \
         patch("src.engine.scheduler.asyncio.sleep", side_effect=_sleep_noop):
        # start() 는 RuntimeError 흡수 후 finally 통과
        await sched.start()

    # ===== 핵심 검증 (Red — 현재 코드에서 fail) =====
    # 1. self._ws_task 가 finally 루프에서 cancel() 호출됐어야 함
    assert fake_ws_task.cancel.call_count == 1, (
        f"self._ws_task.cancel() 호출 누락 — line 244 직후 예외 시나리오에서 "
        f"finally 루프가 _ws_task 를 cancel 하지 않음 (현재 호출 횟수: "
        f"{fake_ws_task.cancel.call_count}). 명세 §4 Patch 1+2+4 필수."
    )

    # 2. setattr(None) 검증 — finally 가 완료 후 None 재대입
    assert getattr(sched, "_ws_task", "MISSING") is None, (
        f"self._ws_task 가 finally 종료 후 None 재대입되지 않음 — "
        f"현재값: {getattr(sched, '_ws_task', 'MISSING')}. 명세 §4 Patch 4."
    )

    # 3. self._scan_task is None — line 402 이전 단계 예외이므로 scan_task 미생성.
    #    finally 의 `if task and not task.done():` 가드가 None 안전 처리 → AttributeError 0
    assert getattr(sched, "_scan_task", "MISSING") is None, (
        f"self._scan_task 가 None 이 아님 — line 402 이전 예외 시나리오에서 "
        f"scan_task 미생성 상태가 finally 에서 None 으로 정상 처리돼야 함. "
        f"현재값: {getattr(sched, '_scan_task', 'MISSING')}."
    )

    # 4. 13-E + 13-E-1 회귀 — 메인 disconnect best-effort + pool.stop 도달
    main_ws.disconnect.assert_awaited()
    fake_pool.stop.assert_awaited()
    assert "main_disconnect" in call_order, (
        f"finally 메인 disconnect best-effort 누락 (13-E-1 회귀). 순서: {call_order}"
    )
    assert "pool_stop" in call_order, (
        f"finally pool.stop 누락 (13-E 회귀). 순서: {call_order}"
    )
    assert call_order.index("main_disconnect") < call_order.index("pool_stop"), (
        f"메인→보조 순서 깨짐. 순서: {call_order}"
    )


# ---------------------------------------------------------------------------
# Test J-2 — line 402 직후 예외 → ws_task + scan_task 둘 다 cancel + await
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_exception_after_scan_task_creation_cancels_both_tasks():
    """Red: ``start()`` 본문 line 402 (`scan_task` 생성) 직후 ~ line 488 *이전*
    단계에서 예외 raise 시, finally 가:

    1. ``self._ws_task.cancel()`` + ``await`` verify
    2. ``self._scan_task.cancel()`` + ``await`` verify
    3. 둘 다 setattr None 으로 재대입 verify
    4. 좀비 task 0건 (둘 다 cancel + await 완료)

    현재 코드 (변경 전) 에서 fail — ws_task / scan_task 가 로컬 변수라
    finally 가 두 task 를 모두 인지하지 못해 cancel 0회.

    시뮬레이션: ``_wait_until(TIME_KRX_MAIN_BUY_STOP)`` 가 raise. 이때
    line 244 의 ws_task + line 402 의 scan_task 가 둘 다 생성된 상태.
    """
    sched = TradingScheduler()

    main_ws = MagicMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.start = AsyncMock()
    fake_pool.stop = AsyncMock()

    fake_ws_task = _fake_task(done=False)
    fake_scan_task = _fake_task(done=False)

    # asyncio.create_task — 첫 호출 = ws_task (line 244). 후속 호출들 중 _scan_loop
    # 와 관련된 것을 fake_scan_task 로 매핑. coroutine 의 __qualname__ 으로 식별 가능.
    create_task_call_count = {"n": 0, "scan_assigned": False}

    def _create_task_side_effect(coro):
        # coroutine name 으로 식별 — _scan_loop 면 fake_scan_task, 그 외 ws_task / 더미
        coro_name = getattr(coro, "__qualname__", "") or getattr(coro, "__name__", "")
        try:
            coro.close()
        except Exception:
            pass
        create_task_call_count["n"] += 1
        if create_task_call_count["n"] == 1:
            return fake_ws_task
        if "_scan_loop" in coro_name and not create_task_call_count["scan_assigned"]:
            create_task_call_count["scan_assigned"] = True
            return fake_scan_task
        return _fake_task(done=True)  # 나머지 background task 는 done 더미

    async def _boot_noop():
        return None

    async def _wait_until_main_buy_stop_raises(target_time, *args, **kwargs):
        """첫 호출 (presubscribe / pre_nxt_open) 은 noop, line 405
        `_wait_until(TIME_KRX_MAIN_BUY_STOP)` 만 raise — 이미 line 402 scan_task 생성됨.
        """
        # target_time 비교 — TIME_KRX_MAIN_BUY_STOP=15:20 만 raise
        from src.engine.scheduler import TIME_KRX_MAIN_BUY_STOP
        if target_time == TIME_KRX_MAIN_BUY_STOP:
            raise RuntimeError("wait_until 실패 (시뮬레이션 — line 405)")
        return None

    async def _async_noop(*args, **kwargs):
        return None

    # _scan_loop / _execute_next_day_clear / _session_loop / _stale_watcher_loop /
    # _swing_buy_poll_loop / _swing_rest_poll_loop 는 create_task 에서 close 처리되어
    # 실제 실행되지 않음. 추가로 _collect_breakout_tickers 등은 빈 리스트 반환 시 분기
    # skip → scan_task 생성 라인 (402) 까지 도달.

    # nested-block 한도 (>20) 를 피하기 위해 ExitStack 사용
    patches = [
        patch.object(sched, "_boot", side_effect=_boot_noop),
        patch.object(sched, "_wait_until",
                     side_effect=_wait_until_main_buy_stop_raises, create=True),
        patch.object(sched, "_confirm_breakout_open_prices",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_force_clear_main_only",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_drain_pending_next_day_clear",
                     side_effect=_async_noop, create=True),
        patch.object(sched, "_collect_breakout_tickers", return_value=[]),
        patch.object(sched, "_collect_swing_tickers", return_value=[]),
        patch.object(sched, "_collect_presubscribe_tickers", return_value=[]),
        patch.object(sched, "_build_subscription_source_counts", return_value={}),
        patch.object(sched, "_build_priority_groups", return_value={}),
        patch("src.engine.scheduler.scan_stocks",
              new=AsyncMock(return_value=[])),
        patch("src.engine.scheduler.subscribe_filtered_stocks", new=AsyncMock()),
        patch("src.engine.scheduler.kis_ws", main_ws),
        patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool),
        patch("src.engine.scheduler.write_log", new=AsyncMock()),
        patch("src.engine.scheduler.register_tick_handler"),
        patch("src.engine.scheduler.register_execution_handler"),
        patch("src.engine.scheduler.register_board_handler"),
        patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()),
        patch("src.engine.scheduler.asyncio.create_task",
              side_effect=_create_task_side_effect),
        patch("src.engine.scheduler.asyncio.sleep", new=AsyncMock()),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        await sched.start()

    # ===== 핵심 검증 (Red) =====
    # 1. ws_task.cancel() 호출
    assert fake_ws_task.cancel.call_count == 1, (
        f"self._ws_task.cancel() 호출 누락 — line 402 이후 예외 시나리오. "
        f"현재 호출 횟수: {fake_ws_task.cancel.call_count}. 명세 §4 Patch 4."
    )
    # 2. scan_task.cancel() 호출
    assert fake_scan_task.cancel.call_count == 1, (
        f"self._scan_task.cancel() 호출 누락 — line 402 이후 예외 시나리오에서 "
        f"finally 가 scan_task 를 인지하지 못함 (좀비 task). "
        f"현재 호출 횟수: {fake_scan_task.cancel.call_count}. 명세 §4 Patch 4."
    )
    # 3. setattr None 재대입 — 두 task 모두
    assert getattr(sched, "_ws_task", "MISSING") is None, (
        f"self._ws_task setattr(None) 누락 — 현재값: "
        f"{getattr(sched, '_ws_task', 'MISSING')}."
    )
    assert getattr(sched, "_scan_task", "MISSING") is None, (
        f"self._scan_task setattr(None) 누락 — 현재값: "
        f"{getattr(sched, '_scan_task', 'MISSING')}."
    )


# ---------------------------------------------------------------------------
# Test J-3 — 정상 경로 idempotent (try 본문에서 await ws_task 완료 후 finally 진입)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_normal_path_done_tasks_skip_cancel_but_clear_attr():
    """Red(부분 PASS 가능): 정상 경로에서 try 본문 line 490 ``await self._ws_task`` 완료
    후 finally 진입. 두 task 모두 ``done()=True`` → finally 의
    ``if task and not task.done():`` 가드로 cancel skip, 그러나 setattr None 은 수행.

    명세 §5 Test J-3:
    > self._ws_task 이미 await 완료 → finally 의 `not done()` 가드로 cancel skip,
    > self._scan_task 도 line 442 에서 cancel 후 finally 에서 done 가드 skip

    의도된 PASS 가능성: 현재 코드 (변경 전) 에서도 sched._ws_task / sched._scan_task
    attribute 자체가 부재 (로컬 변수) → 본 테스트의 `cancel.call_count == 0` assert 는
    PASS 가능 (호출 자체가 0회). 그러나 setattr None 검증은 fail (attribute 부재이므로
    `getattr default` 가 None 일 수 있어 트릭하게 PASS 가능 — 본 테스트의 강력한 시그널은
    `cancel 가 호출되지 않았는가` 가 아니라 `Green 후 회귀 시 done 가드가 잘 동작하는가`).

    → 본 테스트는 Green 후의 회귀 가드용. Red 시점에서는 PASS 일 수 있음. docstring 명시.

    검증의 핵심:
    1. 정상 종료 흐름에서 두 번째 cancel 시도가 RuntimeError 발생하지 않음 (idempotent)
    2. setattr None 으로 attribute 정리됨
    """
    sched = TradingScheduler()

    # Green 적용 후를 시뮬레이션하기 위해 직접 self.* 속성으로 done 상태 task 주입
    # (현재 코드는 __init__ 에 _ws_task / _scan_task 가 없으므로 동적 추가)
    fake_ws_task = _fake_task(done=True)
    fake_scan_task = _fake_task(done=True)
    sched._ws_task = fake_ws_task  # type: ignore[attr-defined]
    sched._scan_task = fake_scan_task  # type: ignore[attr-defined]

    main_ws = MagicMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.start = AsyncMock()
    fake_pool.stop = AsyncMock()

    # _boot 이 raise → 즉시 finally 진입 (try 본문은 우회)
    async def _boot_raises():
        raise RuntimeError("boot 실패 (Test J-3 시뮬레이션)")

    with patch.object(sched, "_boot", side_effect=_boot_raises), \
         patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()), \
         patch("src.engine.scheduler.register_tick_handler"), \
         patch("src.engine.scheduler.register_execution_handler"), \
         patch("src.engine.scheduler.register_board_handler"), \
         patch("src.engine.scheduler.asyncio.create_task",
               side_effect=_close_coro):
        # 정상 종료 흐름 (RuntimeError 흡수)
        await sched.start()

    # done()=True 인 task 는 cancel() 호출 0회
    assert fake_ws_task.cancel.call_count == 0, (
        f"done()=True 인 self._ws_task 의 cancel() 가 호출됨 "
        f"({fake_ws_task.cancel.call_count}회). 명세 §4 Patch 4 — "
        f"`if task and not task.done():` 가드로 idempotent 보장."
    )
    assert fake_scan_task.cancel.call_count == 0, (
        f"done()=True 인 self._scan_task 의 cancel() 가 호출됨 "
        f"({fake_scan_task.cancel.call_count}회). 명세 §4 Patch 4."
    )

    # setattr None 은 done() 여부와 무관하게 수행 (Green 후 회귀 가드 — Red 시점은 PASS 가능)
    assert getattr(sched, "_ws_task", "MISSING") is None, (
        f"done()=True 인 self._ws_task attribute 가 None 재대입되지 않음 — "
        f"현재값: {getattr(sched, '_ws_task', 'MISSING')}."
    )
    assert getattr(sched, "_scan_task", "MISSING") is None, (
        f"done()=True 인 self._scan_task attribute 가 None 재대입되지 않음 — "
        f"현재값: {getattr(sched, '_scan_task', 'MISSING')}."
    )


# ---------------------------------------------------------------------------
# Test J-4 — 15:20 이후 시작 분기 (self._scan_task = None) finally 안전 처리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_scan_task_none_branch_finally_skips_safely():
    """Red(부분 PASS 가능): 15:20 이후 시작 분기 (line 408 명세 위치) 에서
    ``self._scan_task = None`` 상태로 진입. 이후 다른 단계에서 예외 raise 시
    finally 가 ``if task and not task.done():`` 가드로 None 안전 처리.

    명세 §5 Test J-4:
    > 15:20 이후 시작 분기 (line 408 → `self._scan_task = None`).
    > finally 의 `if task and not task.done()` 가드가 None 안전 처리, AttributeError 없음

    의도된 PASS 가능성: 현재 코드 (변경 전) 에서도 `sched._scan_task` 가 없으므로
    `getattr(sched, "_scan_task", None)` → None → 가드 skip → AttributeError 0.
    Red 시점에 본 테스트는 PASS 일 수 있음. Green 후 회귀 가드용. docstring 명시.

    검증의 핵심:
    1. _scan_task 가 None 일 때 finally 가 AttributeError / TypeError 0건
    2. 메인 disconnect + pool.stop 정상 도달
    """
    sched = TradingScheduler()

    # 명세 §4 Patch 3 line 408 시뮬레이션 — Green 후 상태
    sched._scan_task = None  # type: ignore[attr-defined]
    # ws_task 는 active (이미 line 244 생성 완료된 상태)
    fake_ws_task = _fake_task(done=False)
    sched._ws_task = fake_ws_task  # type: ignore[attr-defined]

    main_ws = MagicMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.start = AsyncMock()
    fake_pool.stop = AsyncMock()

    async def _boot_raises():
        raise RuntimeError("boot 실패 (Test J-4 시뮬레이션)")

    with patch.object(sched, "_boot", side_effect=_boot_raises), \
         patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()), \
         patch("src.engine.scheduler.register_tick_handler"), \
         patch("src.engine.scheduler.register_execution_handler"), \
         patch("src.engine.scheduler.register_board_handler"), \
         patch("src.engine.scheduler.asyncio.create_task",
               side_effect=_close_coro):
        # finally 에서 AttributeError / TypeError 발생하면 본 await 가 raise
        # → 테스트 자체가 실패. raise 0건 = PASS.
        await sched.start()

    # _scan_task is None 분기에서 AttributeError 0 — assert 자체는 RuntimeError 가
    # finally 에서 흡수되었는지 검증
    # 메인 disconnect + pool.stop 도달 (정상 종료 흐름 보존)
    main_ws.disconnect.assert_awaited()
    fake_pool.stop.assert_awaited()

    # ws_task 는 active 였으므로 cancel 호출
    assert fake_ws_task.cancel.call_count == 1, (
        f"self._ws_task.cancel() 호출 누락 (scan_task=None 분기에서도 ws_task 는 처리). "
        f"현재 호출 횟수: {fake_ws_task.cancel.call_count}."
    )

    # _scan_task 는 None 유지 (또는 None 재대입) — 어느 쪽이든 정상
    assert getattr(sched, "_scan_task", "MISSING") is None, (
        f"_scan_task 가 None 이 아님 — 현재값: "
        f"{getattr(sched, '_scan_task', 'MISSING')}. 가드 분기 회귀."
    )


# ---------------------------------------------------------------------------
# Test J-5 — done() 인 task 의 cancel skip but setattr None 수행 (Test F-3 패턴)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@freeze_time("2026-05-18 10:00:00")
async def test_already_done_tasks_finally_skip_cancel_but_clear_attrs():
    """Red(부분 PASS 가능): ws_task / scan_task 가 이미 ``done()=True`` 인 상태로
    finally 진입 → cancel skip but setattr None 수행. Test F-3 와 동일 패턴.

    명세 §5 Test J-5:
    > done task cancel 안전성 — finally 루프 진입 → cancel skip but setattr None 수행

    의도된 PASS 가능성: 본 테스트는 Green 후의 회귀 가드용. Red 시점 (현재 코드) 에서는
    `sched._ws_task` / `sched._scan_task` attribute 자체가 없어 `cancel.call_count == 0`
    assert 는 trivially PASS. Green 후의 done() 가드 회귀 검증 목적. docstring 명시.

    검증의 핵심:
    1. done()=True 인 task 의 cancel() 가 호출되지 않음 (idempotent)
    2. setattr None 은 done() 여부와 무관하게 수행
    3. logger.warning 이나 예외 raise 0건 (안전)
    """
    sched = TradingScheduler()

    fake_ws_task = _fake_task(done=True)
    fake_scan_task = _fake_task(done=True)
    sched._ws_task = fake_ws_task  # type: ignore[attr-defined]
    sched._scan_task = fake_scan_task  # type: ignore[attr-defined]

    main_ws = MagicMock()
    main_ws.connect = AsyncMock()
    main_ws.subscribe = AsyncMock()
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.start = AsyncMock()
    fake_pool.stop = AsyncMock()

    async def _boot_raises():
        raise RuntimeError("boot 실패 (Test J-5 시뮬레이션)")

    with patch.object(sched, "_boot", side_effect=_boot_raises), \
         patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()), \
         patch("src.engine.scheduler.register_tick_handler"), \
         patch("src.engine.scheduler.register_execution_handler"), \
         patch("src.engine.scheduler.register_board_handler"), \
         patch("src.engine.scheduler.asyncio.create_task",
               side_effect=_close_coro):
        await sched.start()

    # done()=True → cancel() 호출 0회
    assert fake_ws_task.cancel.call_count == 0, (
        f"done()=True 인 self._ws_task 의 cancel() 가 호출됨 "
        f"({fake_ws_task.cancel.call_count}회). 명세 §4 Patch 4 가드 필수."
    )
    assert fake_scan_task.cancel.call_count == 0, (
        f"done()=True 인 self._scan_task 의 cancel() 가 호출됨 "
        f"({fake_scan_task.cancel.call_count}회). 명세 §4 Patch 4 가드 필수."
    )

    # setattr None 은 done() 여부와 무관 (Test F-3 와 동일 패턴)
    assert getattr(sched, "_ws_task", "MISSING") is None, (
        f"done()=True 인 self._ws_task attribute 가 None 으로 재대입되지 않음 "
        f"— 현재값: {getattr(sched, '_ws_task', 'MISSING')}."
    )
    assert getattr(sched, "_scan_task", "MISSING") is None, (
        f"done()=True 인 self._scan_task attribute 가 None 으로 재대입되지 않음 "
        f"— 현재값: {getattr(sched, '_scan_task', 'MISSING')}."
    )
