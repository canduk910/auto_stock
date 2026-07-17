"""RiskManager.on_tick — donchian_swing 매수 신호 평가 skip (G안, 2026-05-12).

donchian_swing 은 Pull 폴링(_swing_buy_poll_loop) 으로만 매수 평가하고,
WebSocket tick 흐름에서는 매수 신호 평가를 우회한다.

**청산 평가는 그대로** — 보유 종목의 ATR 트레일링/하드 손절은 실시간 시세 필수.

검증:
1. donchian_swing 의 check_buy_signal 이 on_tick 에서 호출되지 않음
2. donchian_swing 의 check_exit_signal 은 보유 종목에 대해 그대로 호출
3. 다른 전략(momentum/VB/LTV)의 check_buy_signal 은 영향 없음
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.risk import RiskManager
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


class _SpyStrategy(StrategyBase):
    """check_buy_signal / check_exit_signal 호출 추적용 스파이."""

    def __init__(self, config):
        super().__init__(config)
        self.buy_calls: list[tuple[str, int, int]] = []
        self.exit_calls: list[tuple[str, int, int]] = []

    async def prepare(self):
        pass

    def check_buy_signal(self, ticker, current_price, open_price):
        self.buy_calls.append((ticker, current_price, open_price))
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        self.exit_calls.append((ticker, current_price, open_price))
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


@pytest.fixture(autouse=True)
def _active_main_board(monkeypatch):
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))


@pytest.fixture(autouse=True)
def _ticker_prev_close(monkeypatch):
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 70000})
    monkeypatch.setattr(scanner, "ticker_prices", {})


# ---------------------------------------------------------------------------
# Case 1: donchian_swing — check_buy_signal 호출되지 않음
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_donchian_check_buy_signal_skipped_in_on_tick():
    registry = StrategyRegistry()
    donchian = _SpyStrategy(StrategyConfig(
        strategy_id="donchian_swing", name="DS", weight=1.0, enabled=True,
        params={"tradable_boards": ["main"]},
    ))
    donchian.state.total_investment = 100_000_000  # 가격 가드 통과
    registry.register(donchian)

    order_engine = MagicMock()
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()

    risk = RiskManager(registry, order_engine)

    # 신호 평가 조건 충족 가격으로 on_tick
    await risk.on_tick("005930", current_price=85000, open_price=80000, change_rate=21.43)

    # donchian_swing 의 check_buy_signal 은 호출되지 않아야 함 (G안)
    assert donchian.buy_calls == [], (
        "donchian_swing 매수 평가는 Pull 폴링에서만 → on_tick 에서 skip"
    )
    # execute_buy 도 호출되지 않음
    assert order_engine.execute_buy.call_count == 0


# ---------------------------------------------------------------------------
# Case 2: donchian_swing — 보유 종목 check_exit_signal 은 그대로 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_donchian_check_exit_signal_called_for_holdings():
    """ATR 트레일링/하드 -7% 손절은 on_tick 으로 평가되어야 한다."""
    registry = StrategyRegistry()
    donchian = _SpyStrategy(StrategyConfig(
        strategy_id="donchian_swing", name="DS", weight=1.0, enabled=True,
        params={"tradable_boards": ["main"]},
    ))
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O-1", strategy_id="donchian_swing",
    )
    registry.register(donchian)

    order_engine = MagicMock()
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()

    risk = RiskManager(registry, order_engine)

    await risk.on_tick("005930", current_price=65000, open_price=70000, change_rate=-7.14)

    # 보유 종목이므로 check_exit_signal 은 호출
    assert len(donchian.exit_calls) == 1
    assert donchian.exit_calls[0][0] == "005930"
    # 매수 평가는 그대로 skip
    assert donchian.buy_calls == []


# ---------------------------------------------------------------------------
# Case 3: momentum/VB/LTV — 정상적으로 check_buy_signal 호출됨 (회귀 가드)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_other_strategies_buy_signal_still_evaluated():
    """donchian_swing 스킵이 다른 전략에 영향을 주면 안 된다."""
    registry = StrategyRegistry()
    momentum = _SpyStrategy(StrategyConfig(
        strategy_id="momentum", name="MOM", weight=1.0, enabled=True,
        params={"tradable_boards": ["main"]},
    ))
    momentum.state.total_investment = 100_000_000
    registry.register(momentum)

    order_engine = MagicMock()
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()

    risk = RiskManager(registry, order_engine)

    await risk.on_tick("005930", current_price=85000, open_price=80000, change_rate=21.43)

    # momentum 은 정상적으로 매수 평가
    assert len(momentum.buy_calls) == 1
    assert momentum.buy_calls[0][0] == "005930"


# ---------------------------------------------------------------------------
# Case 4: donchian_swing 매수 평가 skip + 동일 tick 에서 다른 전략은 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_donchian_and_momentum_coexist():
    registry = StrategyRegistry()
    donchian = _SpyStrategy(StrategyConfig(
        strategy_id="donchian_swing", name="DS", weight=0.5, enabled=True,
        params={"tradable_boards": ["main"]},
    ))
    donchian.state.total_investment = 100_000_000
    momentum = _SpyStrategy(StrategyConfig(
        strategy_id="momentum", name="MOM", weight=0.5, enabled=True,
        params={"tradable_boards": ["main"]},
    ))
    momentum.state.total_investment = 100_000_000
    registry.register(donchian)
    registry.register(momentum)

    order_engine = MagicMock()
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()

    risk = RiskManager(registry, order_engine)
    await risk.on_tick("005930", current_price=85000, open_price=80000, change_rate=21.43)

    assert donchian.buy_calls == []
    assert len(momentum.buy_calls) == 1
