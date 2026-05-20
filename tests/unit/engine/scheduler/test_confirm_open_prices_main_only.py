"""사이클 26 — _confirm_breakout_open_prices board=main 단일 검증.

계획서 H 영역: 2 케이스
- pre_nxt 시점(08:00) 호출이 제거됨 — VB/LTV pre_nxt 에 없으므로 건너뜀
- post_nxt 시점(15:30) 호출이 제거됨 — VB/LTV post_nxt 에 없으므로 건너뜀
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

pytestmark = pytest.mark.unit


def _make_scheduler_with_vb_ltv(monkeypatch):
    """VB/LTV 가 등록된 최소 TradingScheduler."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategy_registry import StrategyRegistry

    with patch("src.engine.scheduler.token_manager"), \
         patch("src.engine.scheduler.kis_ws"), \
         patch("src.engine.scheduler.kis_ws_pool"):
        sched = TradingScheduler.__new__(TradingScheduler)
        sched.registry = StrategyRegistry()
        sched._pending_next_day_clear = set()
        sched._running = False
        sched._phase = "idle"
        sched._stale_retry_count = {}
        sched._silent_inactive_first_seen = {}
        sched._silent_inactive_recovery_count = {}

        vb = VolatilityBreakoutStrategy(
            StrategyConfig(strategy_id="volatility_breakout", name="VB", enabled=True, weight=0.3)
        )
        # 타겟 종목 등록
        vb._targets["005930"] = {
            "k": 0.5,
            "prev_range": 1000,
            "target_offset_base": 500,
            "target_offset": 0,
            "target_price": 0,
            "open_price": 0,
            "boards": {},
        }
        vb._open_confirmed["005930"] = {}
        sched.registry.register(vb)

        ltv = LongTailVolatilityStrategy(
            StrategyConfig(strategy_id="long_tail_volatility", name="LTV", enabled=True, weight=0.3)
        )
        sched.registry.register(ltv)

        return sched


# ---------------------------------------------------------------------------
# 1. _confirm_breakout_open_prices(board="pre_nxt") 가 VB/LTV 대상 없음
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirm_open_prices_pre_nxt_skips_vb_ltv(monkeypatch):
    """사이클 26: VB/LTV tradable_boards=("main",) → board="pre_nxt" 호출 시 대상 없음."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", {
        "005930": {"current_price": 80000, "open_price": 79000, "change_rate": 3.0},
    })

    sched = _make_scheduler_with_vb_ltv(monkeypatch)
    vb = sched.registry.get("volatility_breakout")

    # on_open_price_confirmed 가 호출되지 않아야 한다
    confirmed_calls = []
    original_confirm = vb.on_open_price_confirmed

    def mock_confirm(ticker, price, board=None):
        confirmed_calls.append((ticker, price, board))
        return original_confirm(ticker, price, board=board)

    vb.on_open_price_confirmed = mock_confirm

    # board="pre_nxt" 호출 — VB/LTV 가 pre_nxt 를 지원하지 않으므로 targets 0
    await sched._confirm_breakout_open_prices(board="pre_nxt")

    assert len(confirmed_calls) == 0, (
        "VB/LTV tradable_boards=('main',) 이므로 board='pre_nxt' 시 on_open_price_confirmed "
        "가 호출되면 안 된다. 호출 기록: %s" % confirmed_calls
    )


# ---------------------------------------------------------------------------
# 2. _confirm_breakout_open_prices(board="post_nxt") 가 VB/LTV 대상 없음
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirm_open_prices_post_nxt_skips_vb_ltv(monkeypatch):
    """사이클 26: VB/LTV tradable_boards=("main",) → board="post_nxt" 호출 시 대상 없음."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", {
        "005930": {"current_price": 80000, "open_price": 79000, "change_rate": 3.0},
    })

    sched = _make_scheduler_with_vb_ltv(monkeypatch)
    vb = sched.registry.get("volatility_breakout")

    confirmed_calls = []
    original_confirm = vb.on_open_price_confirmed

    def mock_confirm(ticker, price, board=None):
        confirmed_calls.append((ticker, price, board))
        return original_confirm(ticker, price, board=board)

    vb.on_open_price_confirmed = mock_confirm

    # board="post_nxt" 호출 — VB/LTV 가 post_nxt 를 지원하지 않으므로 targets 0
    await sched._confirm_breakout_open_prices(board="post_nxt")

    assert len(confirmed_calls) == 0, (
        "VB/LTV tradable_boards=('main',) 이므로 board='post_nxt' 시 on_open_price_confirmed "
        "가 호출되면 안 된다. 호출 기록: %s" % confirmed_calls
    )
