"""사이클 61 Phase 2-A2 Red — J 카테고리: universe guard 익일청산 보호 (HIGH, 1 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (J-1)
> **위험 등급**: **HIGH** — 익일청산 시가 race 차단 보장

`_evaluate_universe_guard` — `_pending_next_day_clear` 종목 절대 제외 금지.

검증:
1. `_pending_next_day_clear = {("005930", "ltv")}` 시
2. stale=10 + today_volume=100 (THRESHOLD 미만) 시나리오 (registry 보유 False)
3. `_universe_excluded_today` 에 추가 안 됨
4. `inquire_ccnl` 호출 자체 skip (사전 가드)

Red 단계: stale_manager.evaluate_universe_guard 미존재 → AttributeError 정상.

회귀 가드: CLAUDE.md 절대 깨지 말 것 — 익일청산 종목 시가 race 차단 보호.
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
async def test_J1_universe_guard_ndc_ticker_never_excluded():
    """J-1 (HIGH): 익일청산 종목은 stale>5 + low_volume 이어도 universe 제외 안 함.

    `_pending_next_day_clear` 분기 사전 가드 → `inquire_ccnl` 호출 자체 skip.
    `registry.is_ticker_held_by_any` 는 False (보유는 아니지만 익일청산 후보).
    """
    from src.engine import stale_manager  # noqa: F401 — Red: AttributeError 가능

    sched = _make_scheduler()

    # stale > MAX_STALE_RETRIES (=5)
    sched._stale_retry_count["005930"] = 10

    # `_pending_next_day_clear` set — (ticker, strategy_id) tuple
    sched._pending_next_day_clear = {("005930", "long_tail_volatility")}

    # registry mock — is_ticker_held_by_any 는 False (보유 아님, 익일청산만)
    sched.registry = MagicMock()
    sched.registry.is_ticker_held_by_any = MagicMock(return_value=False)

    # inquire_ccnl mock — 호출되면 fail (사전 가드 검증)
    # kis_ws_pool.unsubscribe mock — 호출되면 fail (익일청산 unsubscribe 절대 금지)
    with patch("src.api.quotation.inquire_ccnl", new=AsyncMock(return_value=None)) as mock_inquire, \
         patch("src.realtime.websocket_pool.kis_ws_pool") as mock_pool, \
         patch("src.engine.scheduler.write_log", new=AsyncMock(return_value=None)):
        mock_pool.unsubscribe = AsyncMock(return_value=None)

        await sched._evaluate_universe_guard(["005930"])

        # 사전 가드 — `inquire_ccnl` 호출 자체 skip
        mock_inquire.assert_not_called()
        # 익일청산 종목 unsubscribe 절대 금지
        mock_pool.unsubscribe.assert_not_called()

    # universe_excluded_today 에 추가 안 됨 (익일청산 절대 보호)
    assert "005930" not in sched._universe_excluded_today, (
        "익일청산 종목 005930 이 universe_excluded_today 에 추가됨 — "
        "stale universe 가드 익일청산 절대 보호 위반 (시가 race 위험)"
    )
