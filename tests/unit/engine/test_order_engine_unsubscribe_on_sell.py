"""사이클 15-A (2026-05-19) — 매도 체결 후 WS 구독 정리 hook.

배경: 매도 전량 체결 시 `del state.positions[ticker]` 만 호출되고 WS 구독은
다음 _scan_loop 5분 주기까지 잔존. KIS 정상 패턴 ("불필요 종목 구독해제") 위반.

fix: `_handle_sell_fill` 전량 체결 분기에서 다음 조건 모두 만족 시 unsubscribe:
- `registry.is_ticker_held_by_any(ticker) == False` (다른 전략 보유 X)
- `_pending_next_day_clear` 에 없음 (익일청산 대기 X)
- 다른 전략 `_scanned_tickers` 에 없음 (스캔 후보 X)

3 케이스:
- A: 매도 + 다른 전략 대상 아닐 때 unsubscribe 호출
- B: 다른 전략이 보유 중일 때 unsubscribe 안 함
- C: pending_next_day_clear 에 있을 때 unsubscribe 안 함
- D: 다른 전략 `_scanned_tickers` 에 있을 때 unsubscribe 안 함
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def fake_registry(monkeypatch):
    """`StrategyRegistry` mock — 단일 전략(momentum) + positions."""
    from src.engine.strategy_base import Position, StrategyConfig, StrategyState
    from src.engine.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()

    # momentum 전략 mock
    momentum = MagicMock()
    momentum.config = StrategyConfig(
        strategy_id="momentum", name="momentum",
        weight=1.0, enabled=True,
        params={},
    )
    momentum.state = StrategyState(strategy_id="momentum")
    momentum.state.total_investment = 1_000_000
    momentum.get_scanned_tickers = MagicMock(return_value=[])

    registry._strategies["momentum"] = momentum
    registry._enabled = ["momentum"]

    return registry


# ===========================================================================
# Case A: 매도 + 다른 전략 대상 아닐 때 unsubscribe
# ===========================================================================
@pytest.mark.asyncio
async def test_sell_fill_unsubscribes_when_no_other_strategy(monkeypatch, fake_registry):
    """전량 매도 체결 시 다른 전략 대상이 아니면 WS unsubscribe 호출."""
    from src.engine.order_engine import OrderEngine
    from src.engine.scanner import TICK_TR_ID
    from src.engine.strategy_base import Position
    from src.realtime import websocket_pool as wp_mod

    engine = OrderEngine(fake_registry)
    # 포지션 시드
    momentum = fake_registry.get("momentum")
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="OS001", strategy_id="momentum",
    )
    momentum.state.positions["005930"] = pos
    engine._order_strategy["OS001"] = "momentum"
    engine._order_qty["OS001"] = 10
    engine._order_ticker["OS001"] = "005930"
    engine._filled_qty["OS001"] = 0
    engine._selling.add("005930")

    unsub_spy = AsyncMock()
    monkeypatch.setattr(wp_mod.kis_ws_pool, "unsubscribe", unsub_spy, raising=False)
    # update_trade_status / delete_position / write_log mock
    monkeypatch.setattr("src.engine.order_engine.update_trade_status",
                       AsyncMock(return_value=1), raising=False)
    monkeypatch.setattr("src.db.positions.delete_position",
                       AsyncMock(), raising=False)

    # _pending_next_day_clear 빈 상태로 hook (또는 scheduler 가 None 일 경우 자체 가드)
    engine._pending_next_day_clear_provider = lambda: set()

    # 전량 매도 체결
    await engine._handle_sell_fill(
        ticker="005930", order_no="OS001",
        price=75000, quantity=10,
        total_filled=10, ordered_qty=10,
    )

    # unsubscribe 1회 호출 (다른 전략 대상 아님)
    assert unsub_spy.await_count >= 1, (
        f"다른 전략 대상 아닐 때 unsubscribe 호출 필요. 실제 count={unsub_spy.await_count}"
    )
    call_args = unsub_spy.await_args_list[0].args
    assert call_args == (TICK_TR_ID, "005930"), (
        f"unsubscribe (TICK_TR_ID, ticker) 호출 필요. 실제={call_args}"
    )


# ===========================================================================
# Case B: 다른 전략이 보유 중 → unsubscribe 안 함
# ===========================================================================
@pytest.mark.asyncio
async def test_sell_fill_skips_unsubscribe_when_other_strategy_holds(monkeypatch, fake_registry):
    """다른 전략(VB 등) 이 같은 종목 보유 중이면 unsubscribe 안 함."""
    from src.engine.order_engine import OrderEngine
    from src.engine.scanner import TICK_TR_ID
    from src.engine.strategy_base import Position, StrategyConfig, StrategyState
    from src.realtime import websocket_pool as wp_mod

    # VB 전략 추가 + 005930 보유
    vb_mock = MagicMock()
    vb_mock.config = StrategyConfig(
        strategy_id="volatility_breakout", name="VB",
        weight=1.0, enabled=True, params={},
    )
    vb_mock.state = StrategyState(strategy_id="volatility_breakout")
    vb_mock.state.positions["005930"] = Position(
        ticker="005930", buy_price=70000, quantity=5,
        order_no="VB001", strategy_id="volatility_breakout",
    )
    vb_mock.get_scanned_tickers = MagicMock(return_value=[])
    fake_registry._strategies["volatility_breakout"] = vb_mock
    fake_registry._enabled.append("volatility_breakout")

    engine = OrderEngine(fake_registry)
    # momentum 매도 시뮬
    momentum = fake_registry.get("momentum")
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="OS001", strategy_id="momentum",
    )
    momentum.state.positions["005930"] = pos
    engine._order_strategy["OS001"] = "momentum"
    engine._order_qty["OS001"] = 10
    engine._order_ticker["OS001"] = "005930"
    engine._filled_qty["OS001"] = 0
    engine._selling.add("005930")

    unsub_spy = AsyncMock()
    monkeypatch.setattr(wp_mod.kis_ws_pool, "unsubscribe", unsub_spy, raising=False)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status",
                       AsyncMock(return_value=1), raising=False)
    monkeypatch.setattr("src.db.positions.delete_position",
                       AsyncMock(), raising=False)
    engine._pending_next_day_clear_provider = lambda: set()

    await engine._handle_sell_fill(
        ticker="005930", order_no="OS001",
        price=75000, quantity=10,
        total_filled=10, ordered_qty=10,
    )

    # VB 가 보유 중이라 unsubscribe 안 함
    assert unsub_spy.await_count == 0, (
        f"다른 전략 보유 중일 때 unsubscribe 안 함. 실제 count={unsub_spy.await_count}"
    )


# ===========================================================================
# Case C: pending_next_day_clear 에 있을 때 unsubscribe 안 함
# ===========================================================================
@pytest.mark.asyncio
async def test_sell_fill_skips_unsubscribe_when_pending_next_day_clear(monkeypatch, fake_registry):
    """`_pending_next_day_clear` 에 있는 종목은 unsubscribe 안 함."""
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_base import Position
    from src.realtime import websocket_pool as wp_mod

    engine = OrderEngine(fake_registry)
    momentum = fake_registry.get("momentum")
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="OS001", strategy_id="momentum",
    )
    momentum.state.positions["005930"] = pos
    engine._order_strategy["OS001"] = "momentum"
    engine._order_qty["OS001"] = 10
    engine._order_ticker["OS001"] = "005930"
    engine._filled_qty["OS001"] = 0
    engine._selling.add("005930")

    # pending_next_day_clear 에 있음
    engine._pending_next_day_clear_provider = lambda: {("005930", "momentum")}

    unsub_spy = AsyncMock()
    monkeypatch.setattr(wp_mod.kis_ws_pool, "unsubscribe", unsub_spy, raising=False)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status",
                       AsyncMock(return_value=1), raising=False)
    monkeypatch.setattr("src.db.positions.delete_position",
                       AsyncMock(), raising=False)

    await engine._handle_sell_fill(
        ticker="005930", order_no="OS001",
        price=75000, quantity=10,
        total_filled=10, ordered_qty=10,
    )

    assert unsub_spy.await_count == 0, (
        f"pending_next_day_clear 에 있을 때 unsubscribe 안 함. 실제 count={unsub_spy.await_count}"
    )


# ===========================================================================
# Case D: 다른 전략 `_scanned_tickers` 에 있을 때 unsubscribe 안 함
# ===========================================================================
@pytest.mark.asyncio
async def test_sell_fill_skips_unsubscribe_when_in_scanned_tickers(monkeypatch, fake_registry):
    """다른 전략의 `_scanned_tickers` 에 포함된 종목은 unsubscribe 안 함."""
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_base import Position, StrategyConfig, StrategyState
    from src.realtime import websocket_pool as wp_mod

    # VB 가 005930 을 스캔 후보로 보유 (포지션 X, _scanned_tickers 에 있음)
    vb_mock = MagicMock()
    vb_mock.config = StrategyConfig(
        strategy_id="volatility_breakout", name="VB",
        weight=1.0, enabled=True, params={},
    )
    vb_mock.state = StrategyState(strategy_id="volatility_breakout")
    vb_mock.get_scanned_tickers = MagicMock(return_value=["005930", "000660"])
    fake_registry._strategies["volatility_breakout"] = vb_mock
    fake_registry._enabled.append("volatility_breakout")

    engine = OrderEngine(fake_registry)
    momentum = fake_registry.get("momentum")
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="OS001", strategy_id="momentum",
    )
    momentum.state.positions["005930"] = pos
    engine._order_strategy["OS001"] = "momentum"
    engine._order_qty["OS001"] = 10
    engine._order_ticker["OS001"] = "005930"
    engine._filled_qty["OS001"] = 0
    engine._selling.add("005930")
    engine._pending_next_day_clear_provider = lambda: set()

    unsub_spy = AsyncMock()
    monkeypatch.setattr(wp_mod.kis_ws_pool, "unsubscribe", unsub_spy, raising=False)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status",
                       AsyncMock(return_value=1), raising=False)
    monkeypatch.setattr("src.db.positions.delete_position",
                       AsyncMock(), raising=False)

    await engine._handle_sell_fill(
        ticker="005930", order_no="OS001",
        price=75000, quantity=10,
        total_filled=10, ordered_qty=10,
    )

    assert unsub_spy.await_count == 0, (
        f"VB 스캔 후보면 unsubscribe 안 함. 실제 count={unsub_spy.await_count}"
    )
