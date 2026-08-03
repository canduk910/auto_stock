"""사이클 2 → 사이클 I 전환 — 시장 레짐 매수 가드 제거.

사이클 2 B6 가드(defensive 레짐 → 매수 차단)를 사이클 I 에서 제거했다.
risk.on_tick 은 더 이상 `get_current_regime` / `get_buy_block_state` 를 소비하지 않는다.

- (구 B6-A 반전) defensive 레짐이어도 매수 실행
- (구 B6-C 보존) 청산은 레짐 무관 정상

포괄 신규 회귀 = `test_risk_buy_block_modes.py`.
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


# ---------------------------------------------------------------------------
# 구 B6-A 반전 — defensive 레짐이어도 매수 실행 (게이트 제거)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_defensive_regime_no_longer_blocks_buy(monkeypatch):
    """사이클 I — defensive 레짐 메모리 상태에서도 매수 차단 안 함.

    risk.on_tick 은 레짐을 소비하지 않으므로 메모리 regime 이 defensive 여도
    매수 신호는 정상 execute_buy 호출된다.
    """
    from src.engine import market_regime as mr_mod
    from src.engine.market_regime import MarketRegime
    from src.engine.strategy_base import Signal

    # defensive 레짐을 메모리에 세팅 (테스트 후 empty 로 복원)
    prev = mr_mod.get_current_regime()
    mr_mod.set_current_regime(
        MarketRegime(regime="defensive", vix=20.0, fear_greed_score=50.0)
    )
    try:
        rm, registry, order_engine = _make_risk()
        strategy = _make_mock_strategy("momentum")
        strategy.check_buy_signal.return_value = Signal.BUY
        registry.enabled.return_value = [strategy]
        registry.is_ticker_blocked_for_buy.return_value = False

        await rm.on_tick(
            ticker="005930", current_price=70000, open_price=69000, change_rate=1.0
        )

        order_engine.execute_buy.assert_awaited_once()
        strategy.check_buy_signal.assert_called_once()
    finally:
        mr_mod.set_current_regime(prev)


# ---------------------------------------------------------------------------
# 구 B6-C 보존 — 청산 신호는 레짐 무관 → execute_sell 호출됨
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exit_signal_ignores_regime():
    """defensive 레짐 + STOP_LOSS 청산 신호 → execute_sell 정상 호출 (안전 원칙)."""
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
