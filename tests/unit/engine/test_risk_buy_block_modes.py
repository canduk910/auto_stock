"""사이클 I (2026-08-03) — 레짐 매수 게이트 제거 회귀.

사이클 8 의 4 모드 매수 가드(HARD 차단 / SOFT 수량 축소 / WARN 로그)를 제거했다.
마켓레짐은 더 이상 매수를 차단/축소하지 않는다 (관찰 전용 전환).

새 불변식:
- risk.on_tick 은 `get_current_regime` / `get_buy_block_state` 를 호출하지 않는다.
- 매수 신호는 레짐(defensive 포함) 무관하게 execute_buy 호출.
- execute_buy 에 `soft_multiplier` kwarg 를 전달하지 않는다 (수량 축소 없음).
- 청산은 원래도 레짐 무관 — 정상 실행.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


def _make_mock_strategy(strategy_id: str = "momentum"):
    state = MagicMock()
    state.buy_disabled = False
    state.positions = {}
    state.signal_count_today = 0
    state.total_investment = 1_000_000
    state.is_low_funds_blocked.return_value = False
    state.has_position.return_value = False

    s = MagicMock()
    s.strategy_id = strategy_id
    s.state = state
    s.config = MagicMock()
    s.config.params = {}
    s.is_daily_loss_exceeded.return_value = False
    s.check_buy_signal.return_value = None
    s.check_exit_signal.return_value = None
    s.calc_buy_quantity.return_value = 10
    return s


def _make_risk():
    from src.engine.risk import RiskManager

    registry = MagicMock()
    order_engine = MagicMock()
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()

    rm = RiskManager(registry=registry, order_engine=order_engine)
    return rm, registry, order_engine


@pytest.fixture(autouse=True)
def _patch_session_tracker(monkeypatch):
    from src.engine import risk as risk_mod
    monkeypatch.setattr(
        risk_mod.session_tracker, "is_tradable",
        lambda strategy_id, params: True,
    )


@pytest.mark.asyncio
async def test_regime_does_not_block_buy():
    """레짐 무관 — 매수 신호는 항상 execute_buy 호출 (게이트 제거)."""
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_buy_no_soft_multiplier():
    """레짐 게이트 제거 — execute_buy 에 soft_multiplier 를 전달하지 않는다 (수량 축소 없음)."""
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_awaited_once()
    call = order_engine.execute_buy.await_args
    assert "soft_multiplier" not in call.kwargs, (
        f"레짐 게이트 제거 후 soft_multiplier 전달 금지: kwargs={call.kwargs}"
    )


@pytest.mark.asyncio
async def test_risk_does_not_consume_regime(monkeypatch):
    """risk.on_tick 이 get_buy_block_state 를 호출하지 않는다 (게이트 제거 확증).

    `MarketRegime.get_buy_block_state` 를 폭발하도록 patch 해도 매수가 정상 실행되면
    risk.on_tick 이 레짐을 소비하지 않음이 확증된다.
    """
    from src.engine.market_regime import MarketRegime
    from src.engine.strategy_base import Signal

    async def _boom(self):
        raise AssertionError("get_buy_block_state 는 호출되면 안 됨 (게이트 제거)")

    monkeypatch.setattr(MarketRegime, "get_buy_block_state", _boom)

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_awaited_once()


@pytest.mark.asyncio
async def test_exit_signal_still_executes():
    """청산은 레짐 게이트 제거와 무관하게 정상 실행."""
    from src.engine.strategy_base import Position, Signal

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    pos = Position(
        ticker="005930", buy_price=68000, quantity=1, order_no="ord-1",
        strategy_id="momentum",
    )
    strategy.state.positions = {"005930": pos}
    strategy.state.has_position.return_value = True
    strategy.check_exit_signal.return_value = Signal.STOP_LOSS
    strategy.check_buy_signal.return_value = None
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    await rm.on_tick(ticker="005930", current_price=62000, open_price=68000, change_rate=-8.5)

    order_engine.execute_sell.assert_awaited_once()
    order_engine.execute_buy.assert_not_awaited()
