"""사이클 61 Phase 2-A2 Red — I 카테고리: universe guard 보유 보호 (HIGH, 1 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (I-1)
> **위험 등급**: **HIGH** — 보유 종목 손절·트레일링 우선 보장

`_evaluate_universe_guard` — 보유 종목은 stale>5 + low_volume 이어도 제외 안 함.

검증:
1. `registry.is_ticker_held_by_any("005930") == True` 시
2. stale=10 (MAX_STALE_RETRIES=5 초과) + today_volume=100 (THRESHOLD 미만) 시나리오
3. `_universe_excluded_today` 에 추가 안 됨
4. `inquire_ccnl` 호출 자체 skip (사전 가드, KIS Rate Limit 절약)

Red 단계: stale_manager.evaluate_universe_guard 미존재 → AttributeError 정상.

회귀 가드: CLAUDE.md 절대 깨지 말 것 — stale universe 가드 보유 절대 보호.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    return sched


@pytest.mark.asyncio
async def test_I1_universe_guard_held_ticker_never_excluded(caplog):
    """I-1 (HIGH): 보유 종목은 stale>5 + low_volume 이어도 universe 제외 안 함.

    사전 가드 (보유) → `inquire_ccnl` 호출 자체 skip.
    """
    from src.engine import stale_manager  # noqa: F401 — Red: AttributeError 가능

    sched = _make_scheduler()

    # stale > MAX_STALE_RETRIES (=5)
    sched._stale_retry_count["005930"] = 10
    # 익일청산은 비어있음 (보유 분기만 검증)
    sched._pending_next_day_clear = set()

    # registry mock — is_ticker_held_by_any("005930") == True
    sched.registry = MagicMock()
    sched.registry.is_ticker_held_by_any = MagicMock(return_value=True)

    # inquire_ccnl mock — 호출되면 fail (사전 가드 검증)
    # kis_ws_pool.unsubscribe mock — 호출되면 fail (보유 unsubscribe 절대 금지)
    with patch("src.api.quotation.inquire_ccnl", new=AsyncMock(return_value=None)) as mock_inquire, \
         patch("src.realtime.websocket_pool.kis_ws_pool") as mock_pool, \
         patch("src.engine.scheduler.write_log", new=AsyncMock(return_value=None)):
        mock_pool.unsubscribe = AsyncMock(return_value=None)

        await sched._evaluate_universe_guard(["005930"])

        # 사전 가드 — `inquire_ccnl` 호출 자체 skip
        mock_inquire.assert_not_called()
        # 보유 종목 unsubscribe 절대 금지
        mock_pool.unsubscribe.assert_not_called()

    # universe_excluded_today 에 추가 안 됨 (보유 절대 보호)
    assert "005930" not in sched._universe_excluded_today, (
        "보유 종목 005930 이 universe_excluded_today 에 추가됨 — "
        "stale universe 가드 보유 절대 보호 위반 (손절/트레일링 우선 정책 깨짐)"
    )
