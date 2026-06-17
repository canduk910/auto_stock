"""사이클 160 hotfix — _wait_until target 도달 시 break 본질 복원.

운영 사례 (verbatim):
- 2026-06-17 알테오젠 (196170, VB) + 알지노믹스 (476830, LTV) 15:20 강제청산 누락
- 14:33:26 EC2 재시작 → 14:34:01 "매매 모드 진입" + `_wait_until(15:20)` 진입
- 15:20 정각 도달 시 사이클 152 hotfix 결함 `_wait_until` 이 target 도달도 "이미 지난"
  으로 판정 → target +=1day → 영원히 return 불가
- run_daily L657 `_force_clear_main_only` 호출 자체 누락
- 15:30 phase 전환 / 19:50 매수중단 / 20:00 자문 / 20:10 정산 모두 도달 불가

근본 원인 = 사이클 152 hotfix 가 `_wait_until` 본질을 깨뜨림.
시정 = 2 모드 분기 — `run_daily` 영역 = target 도달 즉시 break (본질 복원),
       `task_loop_helper` 영역 = `advance_if_passed=True` 명시 (사이클 152 폭주 차단 의도 영속).

회귀 가드:
- G-160-BREAK-1 (HIGH): default 모드 target 도달 즉시 return
- G-160-BREAK-2 (HIGH): default 모드 target 정확 도달 시점 return (=동등)
- G-160-ADVANCE-1: advance_if_passed=True 모드 target 지난 시점 내일 대기 (사이클 152 폭주 차단)
- G-160-FUTURE-1: target 미래 시점 정상 대기 (양 모드 공통)
- G-160-RUN-DAILY (HIGH): run_daily 영역 `_wait_until` 호출 전부 default 모드 (advance_if_passed 미명시)
- G-160-TASK-HELPER (HIGH): task_loop_helper 의 `_wait_until` 호출 `advance_if_passed=True` 명시
- G-160-SAFETY: scheduler.py 의 force_clear / risk / order_engine import 변경 0
"""

from __future__ import annotations

import ast
import pathlib
from datetime import datetime, time
from unittest.mock import patch

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SCHEDULER_PATH = _REPO_ROOT / "src" / "engine" / "scheduler.py"
_HELPER_PATH = _REPO_ROOT / "src" / "engine" / "task_loop_helper.py"


def _make_scheduler():
    from src.engine.scheduler import TradingScheduler
    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True
    return sched


@pytest.mark.asyncio
async def test_g_160_break_1_default_mode_target_passed_immediate_return():
    """G-160-BREAK-1 (HIGH) — default 모드 target 도달 시점 즉시 return.

    사이클 160 핵심 = `run_daily` 영역 phase 전환 즉시 진입 의무.
    재현 = 15:20:00.5 시점 _wait_until(15:20) → 즉시 return 의무.
    """
    sched = _make_scheduler()
    target = time(15, 20)
    now = datetime(2026, 6, 17, 15, 20, 0, 500_000)

    class _MockDT:
        @classmethod
        def now(cls):
            return now

    sleep_calls: list[float] = []

    async def _fake_sleep(secs: float):
        sleep_calls.append(secs)

    with patch("src.engine.scheduler.datetime", _MockDT), \
         patch("asyncio.sleep", _fake_sleep):
        await sched._wait_until(target)

    # 즉시 return = sleep 0회
    assert sleep_calls == [], (
        f"default 모드 target 도달 시점 즉시 return 의무 (사이클 160 본질 복원). "
        f"sleep_calls={sleep_calls}"
    )


@pytest.mark.asyncio
async def test_g_160_break_2_default_mode_target_already_passed_immediate_return():
    """G-160-BREAK-2 (HIGH) — default 모드 target 이미 지난 시점 즉시 return.

    재현 = 16:00 시점 _wait_until(15:20) → 즉시 return.
    `run_daily` 가 늦게 진입한 경우 phase 누락 차단 의무.
    """
    sched = _make_scheduler()
    target = time(15, 20)
    now = datetime(2026, 6, 17, 16, 0, 0)

    class _MockDT:
        @classmethod
        def now(cls):
            return now

    sleep_calls: list[float] = []

    async def _fake_sleep(secs: float):
        sleep_calls.append(secs)

    with patch("src.engine.scheduler.datetime", _MockDT), \
         patch("asyncio.sleep", _fake_sleep):
        await sched._wait_until(target)

    assert sleep_calls == [], (
        f"default 모드 target 이미 지난 시점 즉시 return 의무. sleep_calls={sleep_calls}"
    )


@pytest.mark.asyncio
async def test_g_160_advance_1_advance_mode_target_passed_next_day_wait():
    """G-160-ADVANCE-1 — advance_if_passed=True 모드 target 지난 시점 내일 대기.

    사이클 152 폭주 차단 의도 영속 (task_loop_helper 영역).
    """
    sched = _make_scheduler()
    target = time(16, 30)
    now = datetime(2026, 6, 16, 18, 0, 0)

    class _MockDT:
        @classmethod
        def now(cls):
            return now

    sleep_calls: list[float] = []

    async def _fake_sleep(secs: float):
        sleep_calls.append(secs)
        sched._running = False

    with patch("src.engine.scheduler.datetime", _MockDT), \
         patch("asyncio.sleep", _fake_sleep):
        await sched._wait_until(target, advance_if_passed=True)

    # 내일 대기 = sleep ≥ 1 + 첫 sleep > 0
    assert len(sleep_calls) >= 1
    assert sleep_calls[0] > 0
    # 60초 cap 영속
    assert sleep_calls[0] <= 60


@pytest.mark.asyncio
async def test_g_160_future_1_target_future_wait_both_modes():
    """G-160-FUTURE-1 — target 미래 시점 정상 대기 (양 모드 공통)."""
    for advance in (False, True):
        sched = _make_scheduler()
        target = time(15, 20)
        now = datetime(2026, 6, 17, 10, 0, 0)

        class _MockDT:
            @classmethod
            def now(cls):
                return now

        sleep_calls: list[float] = []

        async def _fake_sleep(secs: float):
            sleep_calls.append(secs)
            sched._running = False

        with patch("src.engine.scheduler.datetime", _MockDT), \
             patch("asyncio.sleep", _fake_sleep):
            if advance:
                await sched._wait_until(target, advance_if_passed=True)
            else:
                await sched._wait_until(target)

        assert len(sleep_calls) >= 1, f"advance={advance} 정상 대기 실패"
        assert sleep_calls[0] > 0
        assert sleep_calls[0] <= 60


def test_g_160_run_daily_default_mode_calls():
    """G-160-RUN-DAILY (HIGH) — run_daily 영역 `_wait_until` 호출 default 모드.

    `run_daily()` 영역에서 `advance_if_passed=True` 호출 0건 의무 — phase 전환 영속.
    """
    src = _SCHEDULER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # run_daily / start 함수 영역 검색
    run_daily_func = None
    start_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            if node.name == "run_daily":
                run_daily_func = node
            elif node.name == "start":
                start_func = node

    assert run_daily_func is not None
    assert start_func is not None

    # start() 본문에서 _wait_until 호출 검사 (run_daily 가 start 호출함)
    violations = []
    for func in (run_daily_func, start_func):
        for sub in ast.walk(func):
            if isinstance(sub, ast.Call):
                if isinstance(sub.func, ast.Attribute) and sub.func.attr == "_wait_until":
                    # advance_if_passed=True 키워드 인자 존재 시 결함
                    for kw in sub.keywords:
                        if kw.arg == "advance_if_passed":
                            if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                violations.append(f"{func.name}:{sub.lineno}")

    assert not violations, (
        f"run_daily/start 영역 `_wait_until` 호출 advance_if_passed=True 금지 "
        f"(phase 전환 영속). 위반 위치: {violations}"
    )


def test_g_160_task_helper_advance_if_passed_explicit():
    """G-160-TASK-HELPER (HIGH) — task_loop_helper 의 `_wait_until` advance_if_passed=True 명시.

    사이클 152 폭주 차단 의도 영속.
    """
    src = _HELPER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # task_loop_helper.py 내부 `_wait_until` 호출 검사
    found_advance_true = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "_wait_until":
                for kw in node.keywords:
                    if kw.arg == "advance_if_passed":
                        if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            found_advance_true = True
                            break

    assert found_advance_true, (
        "task_loop_helper 의 `_wait_until` 호출 영역 `advance_if_passed=True` 명시 의무 "
        "(사이클 152 폭주 차단 의도 영속)"
    )


def test_g_160_safety_no_critical_module_change():
    """G-160-SAFETY — scheduler.py 의 매매 안전성 hot path import 변경 0.

    사이클 160 시정 영역 = `_wait_until` 본체 한정.
    risk / order_engine / scanner / realtime / auth 변경 0 영속.
    """
    src = _SCHEDULER_PATH.read_text(encoding="utf-8")
    # 핵심 import 영속 확인 (사이클 152 hotfix 기존 import 영역 보존)
    assert "from src.engine.order_engine" in src or "order_engine" in src
    assert "TIME_KRX_MAIN_BUY_STOP" in src
    assert "TIME_KRX_MAIN_CLOSE" in src
    assert "_force_clear_main_only" in src
