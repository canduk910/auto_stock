"""사이클 13-E-3 Red — `stop()` 의 좀비 task 차단 (7종 통합) 검증.

명세 (`_workspace/cycle13e3_stop_zombie_and_hook_idempotency_spec.md` §4 Patch A, §5 Test L/M):

PR #12 Copilot 리뷰 ① — `src/engine/scheduler.py:636` 위치에서 발견된 비대칭:
현재 ``stop()`` 의 task cancel 목록은 5종 (`_next_day_task`, `_session_task`,
`_stale_watcher_task`, `_swing_poll_task`, `_swing_rest_poll_task`) 으로
``_ws_task`` / ``_scan_task`` 가 누락. finally 블록(line 500~518)은 이미 13-E-2
사이클에서 7종으로 확장된 상태 → stop() 와 finally 의 비대칭 발생.

**좀비 task 시나리오** (stop→start 빠른 재시작):
- `_scan_loop()` 가 `SCAN_INTERVAL=5분` sleep 도중에는 `_running=False` 전환을 감지하지 못한다.
  → cancel 명시 없이 stop() 만 호출 후 곧바로 start() 가 다시 호출되면, 이전 `_scan_task` 가
  살아남아 새 task 와 함께 중복 scan 루프가 돌 수 있다.
- `_ws_task` 역시 `kis_ws.disconnect()` 직후 await 가 stop() 본문에 없어 disconnect/connect
  race 에서 좀비로 잔존 가능.

기대 동작 (Green Patch A):
- ``stop()`` 의 task cancel 목록을 finally(line 500~518) 와 **동일한 7종 tuple** 로 통일:
  ``(_next_day_task, _session_task, _stale_watcher_task,
    _swing_poll_task, _swing_rest_poll_task, _ws_task, _scan_task)``
- 각 task: ``cancel() → await → setattr(None)`` 동일 처리
- cancel 위치는 ``unsubscribe_all() / kis_ws.disconnect() / kis_ws_pool.stop()`` 이전 유지

Red 단계:
- 현재 `stop()` (`src/engine/scheduler.py:625~636`) tuple 은 5종 → Test L-1/L-2 fail
- finally tuple (line 505~509) 은 7종이라 Test M 의 set 동등 비교 fail (5종 ≠ 7종)

안전 가드 (CLAUDE.md):
- 체결통보 분기 (H0STCNI0/H0STCNI9) 무관 — task cancel 만 검증
- ``_subscriptions`` set 직접 수정 금지 — mock 객체로 격리
- 메인 disconnect 순서 보존 (자금 안전 핵심) — Test L-1/L-2 는 cancel 만 검증, 순서 회귀는
  기존 `test_scheduler_stop_task_cancel.py::test_stop_cancels_tasks_before_resource_cleanup`
  이 담당
- Test M 은 read-only — `inspect.getsource` 로 scheduler.py 의 stop / finally tuple 만 파싱

13-E-1 Test F 와 차별점:
- 13-E-1 Test F 는 5종 cancel 호출/위치를 검증 (현 코드의 5종 stop tuple 회귀 가드).
- 13-E-3 Test L 은 **새로 7종에 합류한 `_ws_task` / `_scan_task` 만 별도 검증** (집중 ASsert).
- 13-E-3 Test M 은 **stop tuple == finally tuple 멤버 집합 동등성** 정합성 가드 (소스 파싱).
"""

from __future__ import annotations

import inspect
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import scheduler as scheduler_module
from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — 가짜 background task (`test_scheduler_stop_task_cancel.py` 와 동일 패턴)
# ---------------------------------------------------------------------------
def _fake_task(*, done: bool = False) -> MagicMock:
    """``asyncio.Task`` 인터페이스 일부를 흉내내는 mock task.

    - ``done()`` → 호출 시점 상태 반환 (기본 False)
    - ``cancel()`` → MagicMock (호출 추적)
    - ``await task`` 지원: ``__await__`` 가 yield 없이 즉시 반환하도록 generator 위임
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


# ---------------------------------------------------------------------------
# Test L-1 — stop() 호출 시 `_ws_task` cancel + await + setattr None 처리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stop_cancels_ws_task_and_clears_attr():
    """Red: ``scheduler.stop()`` 이 ``_ws_task`` 까지 cancel + await + None 재대입해야 한다.

    명세 §4 Patch A — finally(7종) 와 동일한 tuple 로 stop() 확장. 현재 stop() 본문(`scheduler.py:625~636`)
    tuple 은 5종이라 ``_ws_task`` 가 cancel 호출 안 받음 + None 재대입 안 됨 → 본 테스트 fail.

    좀비 시나리오: stop() 후 빠른 재시작 시 `_ws_task` 가 살아남아 중복 connect 가능 (Copilot #1).
    """
    sched = TradingScheduler()
    sched._running = True

    # 7종 중 본 테스트가 검증할 _ws_task 만 active mock. 나머지는 None 으로 setup → cancel 루프
    # 본문이 None 가드(`if task and not task.done()`) 로 noop 수행하므로 안전.
    ws_task = _fake_task(done=False)
    sched._ws_task = ws_task
    sched._scan_task = None
    sched._next_day_task = None
    sched._session_task = None
    sched._stale_watcher_task = None
    sched._swing_poll_task = None
    sched._swing_rest_poll_task = None

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock()

    with patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched.stop()

    assert ws_task.cancel.call_count == 1, (
        f"_ws_task.cancel() 호출 누락 (현재 횟수: {ws_task.cancel.call_count}). "
        f"명세 §4 Patch A — stop() tuple 을 finally(7종) 와 동일하게 _ws_task 포함 필수."
    )
    # await _ws_task 흐름 통과 검증 — __await__ 가 1회 invoke 되어야 함
    # (MagicMock 의 __await__ 는 명시 호출 추적 어렵지만, cancel + setattr None 으로 cancel→await→None
    # 3 단계 패턴 확인. None 재대입은 별도 assert.)
    assert sched._ws_task is None, (
        f"_ws_task attribute 가 None 으로 재대입되지 않음 — 현재값: {sched._ws_task}. "
        f"명세 §4 Patch A — cancel + await + setattr None 동일 처리."
    )


# ---------------------------------------------------------------------------
# Test L-2 — stop() 호출 시 `_scan_task` cancel + await + setattr None 처리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stop_cancels_scan_task_and_clears_attr():
    """Red: ``scheduler.stop()`` 이 ``_scan_task`` 까지 cancel + await + None 재대입해야 한다.

    명세 §4 Patch A — `_scan_loop()` 는 `SCAN_INTERVAL=5분` sleep 도중 `_running=False` 전환을
    감지 못함 → cancel 명시 없으면 좀비 task 잔존 + 다음 start() 와 중복 scan (Copilot #1).
    """
    sched = TradingScheduler()
    sched._running = True

    scan_task = _fake_task(done=False)
    sched._scan_task = scan_task
    sched._ws_task = None
    sched._next_day_task = None
    sched._session_task = None
    sched._stale_watcher_task = None
    sched._swing_poll_task = None
    sched._swing_rest_poll_task = None

    main_ws = MagicMock()
    main_ws.disconnect = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.stop = AsyncMock()

    with patch("src.engine.scheduler.kis_ws", main_ws), \
         patch("src.engine.scheduler.unsubscribe_all", new=AsyncMock()), \
         patch("src.realtime.websocket_pool.kis_ws_pool", fake_pool), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched.stop()

    assert scan_task.cancel.call_count == 1, (
        f"_scan_task.cancel() 호출 누락 (현재 횟수: {scan_task.cancel.call_count}). "
        f"명세 §4 Patch A — stop() tuple 을 finally(7종) 와 동일하게 _scan_task 포함 필수."
    )
    assert sched._scan_task is None, (
        f"_scan_task attribute 가 None 으로 재대입되지 않음 — 현재값: {sched._scan_task}. "
        f"명세 §4 Patch A — cancel + await + setattr None 동일 처리."
    )


# ---------------------------------------------------------------------------
# Test M — stop() tuple == finally tuple 정합성 가드 (소스 파싱 기반)
# ---------------------------------------------------------------------------
def _extract_task_tuple_members(method_source: str) -> set[str]:
    """주어진 메서드 소스에서 ``for task_attr in (...)`` tuple 멤버를 set 으로 추출.

    파싱 전략:
    - ``for task_attr in (`` 로 시작하는 라인을 찾아 그 이후 첫 ``)`` 까지를 tuple 본문으로 자름.
    - 따옴표(`"` 또는 `'`) 로 둘러싸인 식별자만 추출 → 정확히 task 속성 이름만 잡힘.
    - 순서 무관성 (set) — Test M 명세: "두 tuple 의 멤버가 정확히 일치 (순서 무관)"
    """
    # 정규식: 첫 `for task_attr in (...)` 블록을 캡쳐 (multi-line tuple 지원)
    m = re.search(
        r"for\s+task_attr\s+in\s*\(([^)]+)\)",
        method_source,
        re.DOTALL,
    )
    if m is None:
        return set()
    body = m.group(1)
    # 따옴표 안의 식별자만 추출 — 줄바꿈/공백/콤마/주석 모두 무시
    members = re.findall(r"""['"]([A-Za-z_][A-Za-z0-9_]*)['"]""", body)
    return set(members)


def test_stop_tuple_equals_finally_tuple_members():
    """Red: ``stop()`` 메서드의 task tuple 멤버 집합이 ``start()`` finally 블록의
    task tuple 멤버 집합과 **정확히 동일** 해야 한다 (순서 무관).

    명세 §4 Patch A — 13-E-2 finally(7종) 와 13-E-3 stop(7종) 통일.
    명세 §9 검수 ① — `("_next_day_task", "_session_task", "_stale_watcher_task",
                          "_swing_poll_task", "_swing_rest_poll_task",
                          "_api_recovered_collector_task",
                          "_ws_task", "_scan_task")` 동일 (10종, 사이클 79 갱신).

    Red 상태: 현재 stop() tuple 은 5종, finally tuple 은 7종 → 차집합 `{_ws_task, _scan_task}` 발견 → fail.

    13-E-1 Test F 와 차별점:
    - F-1: stop tuple 의 cancel 호출 횟수 verify (5종 단독)
    - M: stop tuple ≡ finally tuple **멤버 집합 동등성** 가드 (정합성)
    """
    # stop() 메서드 소스
    stop_src = inspect.getsource(TradingScheduler.stop)
    stop_members = _extract_task_tuple_members(stop_src)

    # start() 메서드 소스 — finally 블록도 start() 본문에 포함
    start_src = inspect.getsource(TradingScheduler.start)
    finally_members = _extract_task_tuple_members(start_src)

    # 두 tuple 모두 빈 set 이면 파싱 실패 → 명세 어긋남
    assert stop_members, (
        "stop() 메서드에서 `for task_attr in (...)` tuple 을 추출하지 못함. "
        f"파싱 대상 소스 길이={len(stop_src)}. 명세 §4 Patch A 코드 패턴 변경됨?"
    )
    assert finally_members, (
        "start() finally 블록에서 `for task_attr in (...)` tuple 을 추출하지 못함. "
        "13-E-2 finally 7종 처리 코드가 사라졌거나 패턴이 바뀜."
    )

    # 멤버 집합 동등성 — 차집합이 양방향 모두 비어있어야 정확히 일치
    missing_in_stop = finally_members - stop_members  # finally 에는 있는데 stop 에 없음
    missing_in_finally = stop_members - finally_members  # stop 에는 있는데 finally 에 없음

    assert missing_in_stop == set() and missing_in_finally == set(), (
        f"stop() tuple ≠ finally tuple — 비대칭 발견.\n"
        f"  stop tuple    : {sorted(stop_members)}\n"
        f"  finally tuple : {sorted(finally_members)}\n"
        f"  finally 에만 있음 (stop 누락): {sorted(missing_in_stop)}\n"
        f"  stop 에만 있음 (finally 누락): {sorted(missing_in_finally)}\n"
        f"명세 §4 Patch A — 두 tuple 멤버 집합 완전 동일 필수 (13-E-2 finally 7종 ≡ 13-E-3 stop 7종)."
    )

    # 추가 강화: 명세가 지정한 멤버 모두 포함 verify (회귀 가드 — 향후 멤버 회귀 방지)
    # 사이클 17 (2026-05-19): 사이클 15-B-2 의 `_near_signal_task` 롤백 — 8 → 7 환원.
    # 사이클 18 (2026-05-19): 5xx WARNING dedupe summary 60s task 추가 — 7 → 8 환원.
    expected_members = {
        "_next_day_task",
        "_session_task",
        "_stale_watcher_task",
        "_session_health_task",  # 사이클 46 (2026-05-22) — refactor-review 카드 #6
        "_swing_poll_task",
        "_swing_rest_poll_task",
        "_5xx_dedupe_summary_task",
        "_api_recovered_collector_task",  # 사이클 79 추가 (사이클 76 도입, cancel 누락 시정)
        "_scan_pool_eager_refresh_task",  # 사이클 83 추가 (후보 풀 eager refresh 5분 task)
        "_full_universe_load_task",  # 사이클 101 추가 (Q68=A+Q69=B — _universe_eager_refresh_task 대체)
        "_stock_master_daily_load_task",  # 사이클 122 추가 (KIS 일봉 16:00 KST 적재 task)
        "_stock_master_basics_refresh_task",  # 사이클 126 추가 (KIS CTPF1002R 16:10 KST 매스 보강 task)
        "_stock_master_master_load_task",  # 사이클 129 추가 (KIS 종목 마스터 파일 16:30 KST 적재 task)
        "_stock_master_financial_load_task",  # 사이클 C3 추가 (퀀트 재무 16:40 KST 주1회 적재 task)
        "_stock_master_daily_purge_task",  # 사이클 150 추가 (T-150일 retention cron 16:15 KST task)
        "_evening_funnel_capture_task",  # 사이클 171 추가 (16:20 KST 저녁 잠정 funnel 캡처 task)
        # cycle264 추가 (2026-09-06) — 09:05:30 시가 3자 대조 shadow task.
        # 관측 전용(행위 0)이지만 종목당 0.2초 throttle 로 최대 ~28초를 도는 루프라
        # cancel 목록 누락 시 `stop()` 이 그 REST 버스트를 끊지 못한다. 속성명이
        # `_*_task_handle` 이던 초안은 cycle79 가드의 수집 패턴(`endswith("_task")`)
        # 에도 안 잡혀 세 목록 전부에서 조용히 빠져 있었다(적대 검증 MEDIUM).
        "_open_source_compare_task",
        # cycle269 추가 (2026-09-08) — 매일 15:45 KST 보조 시세 계정 접근토큰 강제
        # 재발급 task. 7계정 × 61초 직렬화로 ~7분을 도는 루프라 cancel 누락 시
        # `stop()` 이 그 발급 cascade 를 끊지 못한다.
        "_quote_token_refresh_task",
        "_ws_task",
        "_scan_task",
    }
    assert stop_members == expected_members, (
        f"stop() tuple 이 명세 §9 ① 의 20종과 불일치.\n"
        f"  실제 : {sorted(stop_members)}\n"
        f"  기대 : {sorted(expected_members)}\n"
        f"명세 §4 Patch A 코드 블록 참조."
    )


# ---------------------------------------------------------------------------
# 모듈 import 부수효과 가드 — `scheduler` 가 정상 임포트되었는지 확인
# (`inspect.getsource` 가 동작하려면 모듈이 로드돼 있어야 함)
# ---------------------------------------------------------------------------
def test_scheduler_module_loaded():
    """sanity check — scheduler 모듈이 정상 로드되어 `TradingScheduler.stop` /
    `TradingScheduler.start` 메서드가 inspect-able 상태인지 verify.

    Test M 의 전제 (소스 파싱 가능) 가 깨지면 빠르게 fail-fast.
    """
    assert hasattr(scheduler_module, "TradingScheduler"), \
        "scheduler 모듈에서 TradingScheduler 를 찾을 수 없음 — 모듈 구조 변경됨?"
    assert callable(TradingScheduler.stop), "TradingScheduler.stop 가 호출 가능하지 않음"
    assert callable(TradingScheduler.start), "TradingScheduler.start 가 호출 가능하지 않음"
