"""잔고부족 → 매수 락(900s) + per-ticker 매수 수량 0 → low_funds cooldown(900s)."""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_buy_when_kis_returns_insufficient_cash_then_block_buy_lock(order_env, kis_error):
    env = order_env
    momentum = env.momentum

    # get_buyable 호출 시 KisApiError(insufficient_cash) 발생
    env.state.get_buyable_error = kis_error("APBK0919", "주문가능금액이 부족합니다.")

    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)

    # 매수 락 발동 — buy_blocked_until > now
    now = time.time()
    assert momentum.state.is_buy_blocked(now) is True
    assert momentum.state.buy_blocked_until - now > 800  # ~900s

    # 주문은 발생하지 않음
    assert env.calls.place_order == []


@pytest.mark.asyncio
async def test_buy_when_max_buy_qty_zero_then_block_buy_lock(order_env):
    env = order_env
    momentum = env.momentum

    # get_buyable 응답이 정상이지만 max_buy_quantity=0
    env.state.buyable_max_qty = 0
    env.state.buyable_max_amount = 0

    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)

    now = time.time()
    assert momentum.state.is_buy_blocked(now) is True
    assert env.calls.place_order == []


@pytest.mark.asyncio
async def test_buy_when_calc_qty_zero_then_low_funds_cooldown_per_ticker(order_env):
    """전략 자금 부족으로 calc_buy_quantity == 0 인 경우 해당 종목만 cooldown 등록 (전역 락 X)."""
    env = order_env
    momentum = env.momentum

    # 전략 자금을 가격 미달로 강제
    momentum.state.total_investment = 1000  # 가격 100k 의 1주에도 모자람

    await env.engine.execute_buy("005930", current_price=100_000, strategy=momentum)

    now = time.time()
    # per-ticker low_funds cooldown 등록
    assert momentum.state.is_low_funds_blocked("005930", now) is True
    # 다른 종목은 영향 없음
    assert momentum.state.is_low_funds_blocked("000660", now) is False
    # 전역 매수 락은 발동 X
    assert momentum.state.is_buy_blocked(now) is False
    # 주문은 미발생
    assert env.calls.place_order == []


@pytest.mark.asyncio
async def test_buy_when_buy_blocked_then_skips_kis_call(order_env):
    """이미 락이 걸린 상태에서는 get_buyable 호출조차 하지 않는다."""
    env = order_env
    momentum = env.momentum
    momentum.state.block_buy(time.time() + 600)  # 10분 후까지 락

    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)

    assert env.calls.get_buyable == []
    assert env.calls.place_order == []


@pytest.mark.asyncio
async def test_buy_when_low_funds_blocked_for_ticker_then_skips_kis_call(order_env):
    env = order_env
    momentum = env.momentum
    momentum.state.block_low_funds("005930", time.time() + 600)

    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)

    assert env.calls.get_buyable == []
    assert env.calls.place_order == []
    # 다른 종목은 정상 진행 (별도 종목 cooldown 분리 검증)
    await env.engine.execute_buy("000660", current_price=110000, strategy=momentum)
    assert len(env.calls.get_buyable) == 1
    assert len(env.calls.place_order) == 1
