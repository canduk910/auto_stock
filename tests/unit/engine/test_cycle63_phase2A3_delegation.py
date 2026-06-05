"""사이클 63 Phase 2-A3 Red — A 카테고리: wrapper 위임 1회 검증 (4 케이스).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 A
> **설계 카드**: `_workspace/cycle63_phase2A3_design_card.md`
> **선례**: 사이클 60 A1 / 사이클 61 A2 `test_*_delegation.py` 패턴 답습.

A3 2 wrapper (`_check_and_resubscribe_stale` / `_resubscribe_stale_priority`) 가
`stale_manager` 단일 함수만 호출하는지 검증 + 사이클 60 A1 `_emit_stale_session_detail`
wrapper 보존 검증 (외부 호환).

Red 단계: `stale_manager` 모듈에 A3 2 함수 (`check_and_resubscribe_stale` /
`resubscribe_stale_priority`) 미존재 → `AttributeError` 정상.

회귀 가드: CLAUDE.md 절대 깨지 말 것 — WebSocket 4 중 안전망 행위 보존
(scheduler wrapper 가 stale_manager 단일 호출 = 행위 변경 0건 보장).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init (사이클 60/61 A 패턴 답습)."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    return sched


# ===========================================================================
# A-1: _check_and_resubscribe_stale 위임 (async, HIGH)
# ===========================================================================
@pytest.mark.asyncio
async def test_A1_check_and_resubscribe_stale_delegates_to_stale_manager():
    """A-1 (HIGH): `_check_and_resubscribe_stale` wrapper → stale_manager 단일 호출.

    K stale watcher 본체 (222L) 이주 — 핵심 hot path 360 회/일.
    행위 변경 0건 + 위임 1회 = 안전선.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능 (함수 미존재)

    sched = _make_scheduler()

    with patch.object(
        stale_manager, "check_and_resubscribe_stale", new=AsyncMock(return_value=None)
    ) as mock_fn:
        result = await sched._check_and_resubscribe_stale()

    mock_fn.assert_awaited_once_with(sched)
    assert result is None, "wrapper 가 stale_manager 반환값 (None) 그대로 전달"


# ===========================================================================
# A-2: _resubscribe_stale_priority 위임 (async, default cap=10)
# ===========================================================================
@pytest.mark.asyncio
async def test_A2_resubscribe_stale_priority_delegates_with_default_cap():
    """A-2: `_resubscribe_stale_priority()` wrapper → stale_manager 호출 (cap=10).

    `_scan_loop` 5분 우선 재구독 본체 (100L) 이주.
    cap 인자 그대로 전달 + 반환값 (list[str]) 보존.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    sched = _make_scheduler()
    expected = ["005930", "000660"]

    with patch.object(
        stale_manager, "resubscribe_stale_priority",
        new=AsyncMock(return_value=expected),
    ) as mock_fn:
        result = await sched._resubscribe_stale_priority()

    mock_fn.assert_awaited_once_with(sched, cap=10)
    assert result == expected, "wrapper 가 stale_manager 반환값 (list) 그대로 전달"


# ===========================================================================
# A-3: _resubscribe_stale_priority cap 인자 전달 (cap=5)
# ===========================================================================
@pytest.mark.asyncio
async def test_A3_resubscribe_stale_priority_passes_cap_argument():
    """A-3: `_resubscribe_stale_priority(cap=5)` wrapper → cap 인자 그대로 전달.

    cap 디폴트 값(10)이 아닌 명시 인자 시 keyword-pass 보존 검증.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    sched = _make_scheduler()

    with patch.object(
        stale_manager, "resubscribe_stale_priority",
        new=AsyncMock(return_value=[]),
    ) as mock_fn:
        await sched._resubscribe_stale_priority(cap=5)

    mock_fn.assert_awaited_once_with(sched, cap=5)


# ===========================================================================
# A-4: _emit_stale_session_detail wrapper 보존 (사이클 60 A1 외부 호환)
# ===========================================================================
def test_A4_emit_stale_session_detail_wrapper_preserved_for_external_callers():
    """A-4: `_emit_stale_session_detail` scheduler wrapper 가 사이클 60 A1 답습 유지.

    Q4=B (직접 호출) 채택 후 A3 본체 내부 호출은 `stale_manager.emit_stale_session_detail`
    직접 호출이지만, scheduler.py 의 wrapper 자체는 *외부 호출자 호환 보존* 의무
    (예: 향후 진단 라우트가 scheduler 메서드로 호출할 가능성).

    회귀 가드: 사이클 60 A1 wrapper 정의 영속 + stale_manager 동일 함수로 1:1 위임.
    """
    from src.engine import stale_manager

    sched = _make_scheduler()
    stale_tickers = ["005930"]
    from datetime import datetime, timedelta, timezone
    KST = timezone(timedelta(hours=9))
    now = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)

    with patch.object(
        stale_manager, "emit_stale_session_detail", return_value=None,
    ) as mock_fn:
        sched._emit_stale_session_detail(stale_tickers, now)

    mock_fn.assert_called_once_with(sched, stale_tickers, now)
