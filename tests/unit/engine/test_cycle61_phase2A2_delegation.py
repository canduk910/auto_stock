"""사이클 61 Phase 2-A2 Red — A 카테고리: wrapper 위임 1회 검증 (4 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md`
> **설계 카드**: `_workspace/cycle61_phase2A2_design_card.md`
> **선례**: 사이클 60 A1 `test_cycle60_phase2A1_stale_manager.py` 카테고리 A 패턴 답습.

A2 4 wrapper 가 `stale_manager` 단일 함수만 호출하는지 검증.

Red 단계: `stale_manager` 모듈에 A2 4 함수 (`detect_silent_inactive_sessions` /
`force_reconnect_session` / `delta_unsubscribe_dropped` / `evaluate_universe_guard`)
가 미존재 → `AttributeError` 정상.

회귀 가드: CLAUDE.md 절대 깨지 말 것 — WebSocket 4 중 안전망 행위 보존
(scheduler wrapper 가 stale_manager 단일 호출 = 행위 변경 0건 보장).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init (사이클 60 A1 패턴 답습)."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    return sched


# ===========================================================================
# A-1: _detect_silent_inactive_sessions 위임
# ===========================================================================
def test_A1_detect_silent_inactive_sessions_delegates_to_stale_manager():
    """A-1: `_detect_silent_inactive_sessions` wrapper → stale_manager 단일 호출."""
    from src.engine import stale_manager  # Red: AttributeError 가능 (함수 미존재)

    sched = _make_scheduler()
    expected = ["main", "quote-1"]

    with patch.object(
        stale_manager, "detect_silent_inactive_sessions", return_value=expected
    ) as mock_fn:
        result = sched._detect_silent_inactive_sessions()

    mock_fn.assert_called_once_with(sched)
    assert result == expected, "wrapper 가 stale_manager 반환값 그대로 전달해야 함"


# ===========================================================================
# A-2: _force_reconnect_session 위임 (async)
# ===========================================================================
@pytest.mark.asyncio
async def test_A2_force_reconnect_session_delegates_to_stale_manager():
    """A-2: `_force_reconnect_session` wrapper → stale_manager 단일 호출 (async)."""
    from src.engine import stale_manager  # Red: AttributeError 가능

    sched = _make_scheduler()

    with patch.object(
        stale_manager, "force_reconnect_session", new=AsyncMock(return_value=True)
    ) as mock_fn:
        result = await sched._force_reconnect_session("main")

    mock_fn.assert_awaited_once_with(sched, "main")
    assert result is True, "wrapper 가 stale_manager 반환값 그대로 전달해야 함"


# ===========================================================================
# A-3: _delta_unsubscribe_dropped 위임 (async)
# ===========================================================================
@pytest.mark.asyncio
async def test_A3_delta_unsubscribe_dropped_delegates_to_stale_manager():
    """A-3: `_delta_unsubscribe_dropped` wrapper → stale_manager 단일 호출 (async)."""
    from src.engine import stale_manager  # Red: AttributeError 가능

    sched = _make_scheduler()
    new_set = {"005930", "000660"}
    expected = ["009150"]

    with patch.object(
        stale_manager, "delta_unsubscribe_dropped", new=AsyncMock(return_value=expected)
    ) as mock_fn:
        result = await sched._delta_unsubscribe_dropped(new_set)

    mock_fn.assert_awaited_once_with(sched, new_set)
    assert result == expected, "wrapper 가 stale_manager 반환값 그대로 전달해야 함"


# ===========================================================================
# A-4: _evaluate_universe_guard 위임 (async)
# ===========================================================================
@pytest.mark.asyncio
async def test_A4_evaluate_universe_guard_delegates_to_stale_manager():
    """A-4: `_evaluate_universe_guard` wrapper → stale_manager 단일 호출 (async)."""
    from src.engine import stale_manager  # Red: AttributeError 가능

    sched = _make_scheduler()
    candidates = ["005930", "000660"]

    with patch.object(
        stale_manager, "evaluate_universe_guard", new=AsyncMock(return_value=None)
    ) as mock_fn:
        await sched._evaluate_universe_guard(candidates)

    mock_fn.assert_awaited_once_with(sched, candidates)
