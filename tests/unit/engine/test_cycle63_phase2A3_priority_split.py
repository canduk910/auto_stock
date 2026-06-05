"""사이클 63 Phase 2-A3 Red — I 카테고리: 우선순위 분리 HIGH/LOW (3 케이스, HIGH).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 I
> **회귀 가드**: CLAUDE.md 절대 깨지 말 것 — K stale watcher 우선순위 분리 (사이클 29-R3).
>   `high_tickers` = positions ∪ `_pending_next_day_clear` → HIGH+bypass=True
>   그 외 후보 → LOW+bypass=False (보조 라운드로빈 분산)
>   사이클 28 실측: main=25 → main=2 편중 73% → 5% (사고 자동 회복)

Red 단계: `stale_manager.check_and_resubscribe_stale` 미존재 → AttributeError FAIL.

domain Q2 RECOMMEND — `try/except` 4 중 가드 위치 그대로 보존 검증.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _make_scheduler_with_high_tickers(positions: list[str] = None, ndc: set = None):
    """`TradingScheduler.__new__` + positions / _pending_next_day_clear 주입."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    object.__setattr__(sched, "_pending_next_day_clear", ndc or set())

    # registry mock — positions 합집합 구성용
    strategy_state = MagicMock()
    strategy_state.positions = {t: MagicMock() for t in (positions or [])}
    strategy = MagicMock(state=strategy_state)
    sched.registry = MagicMock(all=lambda: [strategy] if positions else [])
    return sched


def _make_mock_pool(subscribed: set):
    mock_pool = MagicMock()
    mock_pool.get_subscribed_tickers = MagicMock(return_value=subscribed)
    mock_pool.unsubscribe_in_pool = AsyncMock(return_value=None)
    mock_pool.subscribe = AsyncMock(return_value=None)
    return mock_pool


# ===========================================================================
# I-1: positions 소속 stale → HIGH + bypass_limit=True
# ===========================================================================
@pytest.mark.asyncio
async def test_I1_positions_member_stale_resubscribes_with_HIGH_priority_bypass():
    """I-1 (HIGH): positions 소속 stale → subscribe(priority='HIGH', bypass_limit=True).

    사이클 29-R3 — 보유 종목 메인 절대 보장 (KIS 41 한도 무시).
    손절 평가 latency 의 최후 보루.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    # 005930 = positions 소속 → HIGH
    sched = _make_scheduler_with_high_tickers(positions=["005930"])

    mock_pool = _make_mock_pool({"005930"})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched)

    # subscribe 호출 인자 검증
    assert mock_pool.subscribe.await_count == 1
    call_kwargs = mock_pool.subscribe.await_args.kwargs
    assert call_kwargs.get("priority") == "HIGH", (
        f"positions 소속 stale → priority='HIGH' 의무. 실제: {call_kwargs.get('priority')}"
    )
    assert call_kwargs.get("bypass_limit") is True, (
        f"positions 소속 stale → bypass_limit=True 의무 (메인 절대 보장). "
        f"실제: {call_kwargs.get('bypass_limit')}"
    )


# ===========================================================================
# I-2: _pending_next_day_clear 소속 stale → HIGH + bypass_limit=True
# ===========================================================================
@pytest.mark.asyncio
async def test_I2_next_day_clear_member_stale_resubscribes_with_HIGH_priority_bypass():
    """I-2 (HIGH): `_pending_next_day_clear` 소속 stale → HIGH + bypass=True.

    사이클 29-R3 — 익일청산 보류 종목도 손절 평가 latency 보장.
    `_pending_next_day_clear` set 멤버 = (ticker, strategy_id) 튜플.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    # 005930 = _pending_next_day_clear 소속 → HIGH
    sched = _make_scheduler_with_high_tickers(ndc={("005930", "long_tail_volatility")})

    mock_pool = _make_mock_pool({"005930"})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched)

    call_kwargs = mock_pool.subscribe.await_args.kwargs
    assert call_kwargs.get("priority") == "HIGH", (
        f"_pending_next_day_clear 소속 stale → priority='HIGH' 의무. "
        f"실제: {call_kwargs.get('priority')}"
    )
    assert call_kwargs.get("bypass_limit") is True, (
        f"_pending_next_day_clear 소속 stale → bypass_limit=True 의무. "
        f"실제: {call_kwargs.get('bypass_limit')}"
    )


# ===========================================================================
# I-3: 그 외 후보 stale → LOW + bypass_limit=False
# ===========================================================================
@pytest.mark.asyncio
async def test_I3_non_high_candidate_stale_resubscribes_with_LOW_priority_no_bypass():
    """I-3 (HIGH): positions/next_day_clear 외 후보 stale → LOW + bypass=False.

    사이클 29-R3 — VB/LTV/donchian 후보 스캔 종목은 보조 라운드로빈 분산.
    사이클 28 실측 메인 편중 73% → 사이클 29-R3 후 5% (사고 자동 회복).
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    # 005930 stale 이지만 positions / _pending_next_day_clear 부재 → LOW
    sched = _make_scheduler_with_high_tickers()  # 둘 다 빈 상태

    mock_pool = _make_mock_pool({"005930"})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched)

    call_kwargs = mock_pool.subscribe.await_args.kwargs
    assert call_kwargs.get("priority") == "LOW", (
        f"high_tickers 외 후보 stale → priority='LOW' 의무 (보조 분산). "
        f"실제: {call_kwargs.get('priority')}"
    )
    assert call_kwargs.get("bypass_limit") is False, (
        f"high_tickers 외 후보 → bypass_limit=False 의무 (메인 편중 차단). "
        f"실제: {call_kwargs.get('bypass_limit')}"
    )
