"""매도 통합 흐름 — execute_sell → 체결통보 → delete_position + sold_today 등록."""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position, Signal
from src.models.order import OrderSide
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.integration


def _seed_position(strategy, ticker="005930", buy_price=80000, qty=10):
    pos = Position(
        ticker=ticker, buy_price=buy_price, quantity=qty,
        order_no="ORIG-001", strategy_id=strategy.strategy_id,
        high_since_buy=buy_price,
    )
    strategy.state.positions[ticker] = pos
    return pos


@pytest.mark.asyncio
async def test_execute_sell_when_normal_then_orders_and_marks_selling(order_env):
    env = order_env
    momentum = env.momentum
    _seed_position(momentum)

    await env.engine.execute_sell("005930", Signal.STOP_LOSS, "momentum")

    # SELL place_order 호출
    sell_calls = [c for c in env.calls.place_order if c["side"] == OrderSide.SELL]
    assert len(sell_calls) == 1
    assert sell_calls[0]["ticker"] == "005930"
    assert sell_calls[0]["quantity"] == 10

    # _selling 등록
    assert "005930" in env.engine._selling

    # PENDING SELL row INSERT
    pending = [r for r in env.calls.insert_trade if r.trade_type == TradeType.SELL]
    assert len(pending) == 1
    assert pending[0].status == TradeStatus.PENDING
    assert pending[0].strategy == "momentum"

    # 매핑 등록
    order_no = pending[0].order_no
    assert env.engine._order_strategy[order_no] == "momentum"
    assert env.engine._order_ticker[order_no] == "005930"


@pytest.mark.asyncio
async def test_execute_sell_then_full_fill_removes_position_and_marks_sold_today(order_env):
    env = order_env
    momentum = env.momentum
    _seed_position(momentum, buy_price=80000, qty=10)

    await env.engine.execute_sell("005930", Signal.STOP_LOSS, "momentum")
    sell_record = [r for r in env.calls.insert_trade if r.trade_type == TradeType.SELL][0]
    order_no = sell_record.order_no

    # 체결통보 — 80000 매수 → 78000 매도 (-2,000원/주, 10주 → -20,000원 PnL)
    await env.engine.handle_execution_notice(
        ticker="005930", order_no=order_no, side="SELL", price=78000, quantity=10,
    )

    # 포지션 제거
    assert "005930" not in momentum.state.positions
    # 당일 매도 표시
    assert "005930" in momentum.state.sold_today
    # _selling 해제
    assert "005930" not in env.engine._selling
    # 손익 누적
    assert momentum.state.daily_realized_pnl == (78000 - 80000) * 10

    # COMPLETED SELL UPDATE 호출
    completed = [
        c for c in env.calls.update_trade_status
        if c["status"] == TradeStatus.COMPLETED and c["trade_type"] == TradeType.SELL
    ]
    assert len(completed) == 1
    assert completed[0]["profit_loss"] == -20000

    # delete_position DB 호출
    assert len(env.calls.delete_position) == 1
    assert env.calls.delete_position[0]["ticker"] == "005930"


@pytest.mark.asyncio
async def test_execute_sell_when_already_in_selling_then_no_order(order_env):
    env = order_env
    momentum = env.momentum
    _seed_position(momentum)
    env.engine._selling.add("005930")

    await env.engine.execute_sell("005930", Signal.STOP_LOSS, "momentum")
    assert env.calls.place_order == []


@pytest.mark.asyncio
async def test_execute_sell_when_no_position_then_no_order(order_env):
    env = order_env
    await env.engine.execute_sell("005930", Signal.STOP_LOSS, "momentum")
    assert env.calls.place_order == []
    # _selling 자동 해제
    assert "005930" not in env.engine._selling
