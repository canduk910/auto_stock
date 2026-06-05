"""사이클 63 Phase 2-A3 Red — J 카테고리: history 60분 슬라이딩 윈도우 (2 케이스).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 J
> **회귀 가드**: 사이클 29-R1 — `_stale_force_retry_history` 60분 슬라이딩 윈도우 evict
>   `STALE_FORCE_RETRY_HOURLY_CAP=12` 정확 도달 시 WARNING + skip.

Red 단계: `stale_manager.check_and_resubscribe_stale` 미존재 → AttributeError FAIL.

freezegun 의무 — 60분 윈도우 evict 검증.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _make_scheduler():
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    object.__setattr__(sched, "_pending_next_day_clear", set())
    sched.registry = MagicMock(all=lambda: [])
    return sched


def _make_mock_pool(subscribed: set):
    mock_pool = MagicMock()
    mock_pool.get_subscribed_tickers = MagicMock(return_value=subscribed)
    mock_pool.unsubscribe_in_pool = AsyncMock(return_value=None)
    mock_pool.subscribe = AsyncMock(return_value=None)
    return mock_pool


# ===========================================================================
# J-1: history 60분 슬라이딩 윈도우 evict (60분 이전 항목 제거)
# ===========================================================================
@pytest.mark.asyncio
async def test_J1_history_evicts_entries_older_than_60_minutes():
    """J-1: history 에서 60분 이전 entry 자동 evict (`history[:] = [t for t in history if t > hour_ago]`).

    검증 시나리오:
    - now = 10:00:00
    - history = [09:10 (50분 전), 08:50 (70분 전)]
    - now 시점 force_retry 분기 진입 → evict 후 history = [09:10] 만 잔존
    - cap=12 미달 → 강제 재시도 발화 (호출 1회)
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    sched._stale_retry_count["005930"] = 5  # +1 → retry=6 force_retry 분기
    # 60분 이전 1건 + 50분 전 1건 (evict 후 1건 잔존)
    sched._stale_force_retry_history["005930"] = [
        base - timedelta(minutes=70),  # evict 대상 (60분 이전)
        base - timedelta(minutes=50),  # 잔존
    ]

    mock_pool = _make_mock_pool({"005930"})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched)

    # cap=12 미달 → 강제 재시도 발화 + history append (총 2건)
    assert mock_pool.subscribe.await_count == 1, (
        "60분 이전 evict 후 history=1건 < cap=12 → 강제 재시도 의무"
    )
    # history 검증: evict 후 [50분 전, base] 2건
    history_after = sched._stale_force_retry_history["005930"]
    assert len(history_after) == 2, (
        f"history evict 후 신규 append → 2건 의무. 실제: {len(history_after)}건"
    )
    assert all((base - t).total_seconds() <= 3600 for t in history_after), (
        "history 모든 항목이 60분 이내여야 함 (evict 정합성)"
    )


# ===========================================================================
# J-2: cap=12 정확 도달 경계 (12건 vs 11건)
# ===========================================================================
@pytest.mark.asyncio
async def test_J2_history_cap_12_exact_boundary_blocks_force_retry():
    """J-2: history 12건 (cap 정확 도달) → 13회차 skip (>= 비교).

    `if len(history) >= STALE_FORCE_RETRY_HOURLY_CAP: skip`
    경계 (12 vs 11) 검증.

    분기 1: history 12건 (모두 60분 이내) → cap 도달 → skip
    분기 2: history 11건 (모두 60분 이내) → cap 미달 → 강제 재시도 (호출 1회)
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)

    # 분기 1: history 12건 (cap 정확 도달)
    sched1 = _make_scheduler()
    sched1._stale_retry_count["005930"] = 5  # +1 → retry=6
    sched1._stale_force_retry_history["005930"] = [
        base - timedelta(minutes=i) for i in range(1, 13)  # 1~12분 전 = 12건
    ]
    mock_pool1 = _make_mock_pool({"005930"})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool1), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched1)

    assert mock_pool1.subscribe.await_count == 0, (
        "history 12건 (cap 정확 도달) → skip 의무 (>=12 비교)"
    )

    # 분기 2: history 11건 (cap 미달)
    sched2 = _make_scheduler()
    sched2._stale_retry_count["005930"] = 5
    sched2._stale_force_retry_history["005930"] = [
        base - timedelta(minutes=i) for i in range(1, 12)  # 1~11분 전 = 11건
    ]
    mock_pool2 = _make_mock_pool({"005930"})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool2), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched2)

    assert mock_pool2.subscribe.await_count == 1, (
        "history 11건 (cap 미달) → 강제 재시도 발화 의무"
    )
