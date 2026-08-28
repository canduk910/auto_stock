"""RiskManager.on_tick — 보드 가드 / 자금 사전 가드 / signal_count 카운터."""

from __future__ import annotations

import time

import pytest
from freezegun import freeze_time

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_on_tick_when_board_inactive_then_no_buy_signal_evaluated(order_env, monkeypatch):
    """현재 활성 보드가 전략의 tradable_boards 밖이면 신호 평가 자체 스킵."""
    env = order_env
    momentum = env.momentum  # tradable_boards = [krx_open, main]

    # POST_NXT 만 활성 — momentum 은 매매 불가
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.POST_NXT}))

    # 모멘텀이 normally 발동할 가격으로 on_tick — 첫 틱 + 두 번째 틱
    await env.risk.on_tick("005930", current_price=89000, open_price=80000, change_rate=11.25)
    await env.risk.on_tick("005930", current_price=92000, open_price=80000, change_rate=15.0)

    # 매수 시도 없음
    assert env.calls.place_order == []
    assert momentum.state.signal_count_today == 0


@pytest.mark.asyncio
async def test_on_tick_when_low_funds_blocked_and_price_above_total_then_skip(order_env):
    """자금 사전 가드 — 종목 cooldown + 1주 가격 > total_investment 이면 신호 평가 자체 skip.

    OrderEngine 에 도달해 사후 cooldown 등록되던 경고 노이즈를 사전 차단.
    """
    env = order_env
    momentum = env.momentum

    # 이 종목에 대한 low_funds cooldown 등록
    momentum.state.block_low_funds("005930", time.time() + 600)
    # 가격이 전략 할당 자금보다 높음
    momentum.state.total_investment = 100_000

    # 모멘텀 신호 조건을 만들어도 (29% 돌파)
    await env.risk.on_tick("005930", current_price=89000, open_price=80000, change_rate=27.14)
    await env.risk.on_tick("005930", current_price=200_000, open_price=80000, change_rate=185.7)

    # check_buy_signal 자체 스킵 → signal_count 증가 X, place_order X
    assert env.calls.place_order == []
    assert momentum.state.signal_count_today == 0


# cycle229 적응 — momentum 매수 컷(15:20 KST) 도입으로 무-freeze 실행이 벽시계 의존.
# 장중 KST 로 동결해 결정성 확보(행위 불변).
@freeze_time("2026-05-08 01:00:00")
@pytest.mark.asyncio
async def test_on_tick_buy_signal_when_breakout_increments_signal_count_and_orders(order_env):
    """매수 신호 발동 → signal_count +1, execute_buy 호출 → place_order 1건."""
    env = order_env
    momentum = env.momentum

    # 첫 틱: 기록만
    await env.risk.on_tick("005930", current_price=89000, open_price=80000, change_rate=27.14)
    assert momentum.state.signal_count_today == 0
    assert env.calls.place_order == []

    # 두 번째 틱: 29% 돌파 → BUY 신호 → execute_buy
    await env.risk.on_tick("005930", current_price=90400, open_price=80000, change_rate=29.14)
    assert momentum.state.signal_count_today == 1
    assert len(env.calls.place_order) == 1
    assert env.calls.place_order[0]["ticker"] == "005930"


@pytest.mark.asyncio
async def test_on_tick_when_position_held_then_exit_signal_takes_priority(order_env):
    """보유 중 종목은 청산 신호 평가가 우선이고, 청산 시 매수 신호는 평가하지 않는다."""
    env = order_env
    momentum = env.momentum
    # 손절 발동 가능한 보유 등록 (-7.5% 도달)
    momentum.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="ORIG-1", strategy_id="momentum",
    )

    await env.risk.on_tick("005930", current_price=92500, open_price=95000, change_rate=-7.5)

    # SELL 주문 발동
    sell_calls = [c for c in env.calls.place_order if c["side"].value == "SELL"]
    assert len(sell_calls) == 1
    # signal_count 는 BUY 신호 카운터라 증가하지 않음
    assert momentum.state.signal_count_today == 0


@pytest.mark.asyncio
async def test_on_tick_updates_ticker_prices_dict(order_env):
    """on_tick 첫 진입 시 scanner.ticker_prices 에 시세 갱신."""
    env = order_env
    from src.engine import scanner

    await env.risk.on_tick("005930", current_price=85000, open_price=80000, change_rate=15.0)

    assert "005930" in scanner.ticker_prices
    info = scanner.ticker_prices["005930"]
    assert info["current_price"] == 85000
    assert info["open_price"] == 80000
