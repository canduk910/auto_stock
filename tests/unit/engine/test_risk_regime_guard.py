"""사이클 2 — `src/engine/risk.py::on_tick` 시장 레짐 매수 가드 검증.

요구 행위:
- B6-A: 매수 신호 발생 시점에 `MarketRegime.is_buy_allowed=False` → `execute_buy` 호출 안 함
- B6-B: is_buy_allowed=True → 기존 동작 유지 (정상 매수)
- B6-C: 청산(STOP_LOSS) 신호는 가드 무관 → `execute_sell` 호출됨

`get_current_regime()` 을 monkeypatch 로 제어. on_tick 의 다른 분기는 통과.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


def _make_mock_strategy(strategy_id: str = "momentum"):
    """on_tick 진입에 필요한 최소 strategy mock."""
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
    s.check_buy_signal.return_value = None  # 기본은 신호 없음 — 케이스마다 덮어씀
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
    """on_tick 의 `session_tracker.is_tradable` 가 True 를 반환하도록.

    보드 가드는 본 테스트의 대상이 아니므로 통과시킨다.
    `session_tracker.active` 는 property 라 monkeypatch 불가 — `_maybe_emit_regime_block`
    이 active 접근하는 tradable_skip 헬퍼와는 다르므로 (regime 분기는 active 무관)
    별도 패치 불필요.
    """
    from src.engine import risk as risk_mod

    monkeypatch.setattr(
        risk_mod.session_tracker, "is_tradable",
        lambda strategy_id, params: True,
    )


# ---------------------------------------------------------------------------
# B6-A: 매수 신호 + regime block → execute_buy 호출 안 함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b6a_regime_block_prevents_execute_buy(monkeypatch):
    from src.engine import risk as risk_mod
    from src.engine.market_regime import MarketRegime
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()

    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    # defensive 레짐 — 매수 차단
    blocked = MarketRegime(regime="defensive", vix=20.0, fear_greed_score=50.0)
    monkeypatch.setattr(risk_mod, "get_current_regime", lambda: blocked)

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_not_awaited()
    # check_buy_signal 자체도 호출 안 함 (regime 가드가 더 앞)
    strategy.check_buy_signal.assert_not_called()


# ---------------------------------------------------------------------------
# B6-B: regime allow → 기존 매수 흐름 정상
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b6b_regime_allows_buy_executes_normally(monkeypatch):
    from src.engine import risk as risk_mod
    from src.engine.market_regime import MarketRegime
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()

    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    # 안전 레짐 — 매수 허용
    allow = MarketRegime(regime="aggressive", vix=15.0, fear_greed_score=50.0)
    monkeypatch.setattr(risk_mod, "get_current_regime", lambda: allow)

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_awaited_once()
    strategy.check_buy_signal.assert_called_once()


# ---------------------------------------------------------------------------
# B6-C: 청산 신호는 regime 가드 무관 → execute_sell 호출됨
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b6c_exit_signal_ignores_regime_block(monkeypatch):
    """defensive 레짐 + STOP_LOSS 청산 신호 → execute_sell 정상 호출.

    보유 종목의 청산은 시장 레짐과 무관해야 한다 (안전 원칙).
    """
    from src.engine import risk as risk_mod
    from src.engine.market_regime import MarketRegime
    from src.engine.strategy_base import Position, Signal

    rm, registry, order_engine = _make_risk()

    strategy = _make_mock_strategy("momentum")
    # 보유 종목 가정
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

    # defensive 레짐 (매수 차단 상태)
    blocked = MarketRegime(regime="defensive", vix=20.0, fear_greed_score=50.0)
    monkeypatch.setattr(risk_mod, "get_current_regime", lambda: blocked)

    await rm.on_tick(ticker="005930", current_price=62000, open_price=68000, change_rate=-8.5)

    # 청산은 무관하게 실행되어야 함
    order_engine.execute_sell.assert_awaited_once()
    # 매수는 차단됨
    order_engine.execute_buy.assert_not_awaited()


# ---------------------------------------------------------------------------
# B6-D: empty regime (외부 fetch 실패 폴백) → 기존 동작 유지 (매수 허용)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b6d_empty_regime_allows_buy_graceful(monkeypatch):
    from src.engine import risk as risk_mod
    from src.engine.market_regime import MarketRegime
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()

    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    # 외부 fetch 실패 시 empty regime — 매수 허용 (graceful)
    empty = MarketRegime.empty()
    monkeypatch.setattr(risk_mod, "get_current_regime", lambda: empty)

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_awaited_once()
