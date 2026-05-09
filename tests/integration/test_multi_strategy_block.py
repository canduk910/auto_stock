"""전략 간 중복 매수 통합 차단 — registry.is_ticker_blocked_for_buy 가 OrderEngine 진입에서 발동."""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_buy_blocked_when_other_strategy_holds_ticker(order_env):
    """A 전략이 보유 중인 종목을 B 전략이 매수 시도하면 OrderEngine 가 차단."""
    env = order_env
    # vb 가 005930 보유
    env.vb.state.positions["005930"] = Position(
        ticker="005930", buy_price=80000, quantity=1,
        order_no="VB-001", strategy_id="volatility_breakout",
    )

    # momentum 이 같은 종목 매수 시도 → 통합 가드에 의해 차단
    await env.engine.execute_buy("005930", current_price=90000, strategy=env.momentum)

    assert env.calls.place_order == []
    # momentum.pending_buys 에도 추가되지 않음
    assert "005930" not in env.momentum.state.pending_buys


@pytest.mark.asyncio
async def test_buy_blocked_when_other_strategy_pending(order_env):
    """A 전략이 매수 대기 중인 종목을 B 가 매수 시도하면 차단."""
    env = order_env
    env.vb.state.pending_buys.add("005930")

    await env.engine.execute_buy("005930", current_price=90000, strategy=env.momentum)
    assert env.calls.place_order == []


@pytest.mark.asyncio
async def test_buy_blocked_when_other_strategy_sold_today(order_env):
    """A 전략이 당일 매도한 종목을 B 가 같은 날 재매수 시도하면 차단."""
    env = order_env
    env.vb.state.sold_today.add("005930")

    await env.engine.execute_buy("005930", current_price=90000, strategy=env.momentum)
    assert env.calls.place_order == []


@pytest.mark.asyncio
async def test_buy_allowed_when_no_strategy_touches_ticker(order_env):
    """어떤 전략도 보유/대기/당일매도하지 않은 종목은 정상 매수."""
    env = order_env
    # vb 는 다른 종목 보유
    env.vb.state.positions["000660"] = Position(
        ticker="000660", buy_price=100000, quantity=1,
        order_no="VB-002", strategy_id="volatility_breakout",
    )

    await env.engine.execute_buy("005930", current_price=90000, strategy=env.momentum)
    assert len(env.calls.place_order) == 1
    assert env.calls.place_order[0]["ticker"] == "005930"


@pytest.mark.asyncio
async def test_buy_blocked_at_engine_level_even_if_strategy_state_clean(order_env):
    """전략 자체 state 는 깨끗해도 다른 전략이 보유 중이면 OrderEngine 진입 가드에서 차단.

    (전략의 check_buy_signal 가드는 같은 전략 내부 has_position 만 보지만,
     OrderEngine.execute_buy 는 registry 통합 가드까지 한 번 더 확인.)
    """
    env = order_env
    momentum = env.momentum
    # momentum.state 는 비어있음
    assert "005930" not in momentum.state.positions
    assert "005930" not in momentum.state.pending_buys

    # ltv 가 보유 중
    env.ltv.state.positions["005930"] = Position(
        ticker="005930", buy_price=80000, quantity=1,
        order_no="LTV-001", strategy_id="long_tail_volatility",
    )

    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)
    assert env.calls.place_order == []
