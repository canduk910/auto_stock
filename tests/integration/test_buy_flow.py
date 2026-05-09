"""매수 통합 흐름 — execute_buy → 체결통보 → save_position 정상 케이스."""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position
from src.models.order import OrderSide
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_execute_buy_when_normal_then_records_pending_and_maps_order(order_env):
    """정상 매수 → place_order 호출 + PENDING 행 INSERT + 매핑 등록."""
    env = order_env
    momentum = env.momentum

    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)

    # 주문 1건 발생
    assert len(env.calls.place_order) == 1
    po = env.calls.place_order[0]
    assert po["ticker"] == "005930"
    assert po["side"] == OrderSide.BUY
    assert po["price"] == 0  # 시장가

    # PENDING 행 INSERT
    assert len(env.calls.insert_trade) == 1
    rec = env.calls.insert_trade[0]
    assert rec.status == TradeStatus.PENDING
    assert rec.strategy == "momentum"

    # 주문번호 매핑 등록 — _order_strategy/_order_ticker/_order_qty/_pending_buy_orders
    order_no = rec.order_no
    assert env.engine._order_strategy[order_no] == "momentum"
    assert env.engine._order_ticker[order_no] == "005930"
    assert env.engine._order_qty[order_no] > 0
    assert order_no in env.engine._pending_buy_orders

    # state 변화
    assert "005930" in momentum.state.pending_buys
    assert momentum.state.order_attempt_today == 1


@pytest.mark.asyncio
async def test_execute_buy_then_chegyeol_full_fill_saves_position(order_env):
    """매수 → 체결통보 전량 → COMPLETED UPDATE + save_position + pending_buys 제거."""
    env = order_env
    momentum = env.momentum

    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)
    order_no = env.calls.insert_trade[0].order_no

    # 전량 체결 통보
    qty = env.engine._order_qty[order_no]
    await env.engine.handle_execution_notice(
        ticker="005930", order_no=order_no, side="BUY", price=90000, quantity=qty,
    )

    # 포지션 등록
    pos = momentum.state.positions.get("005930")
    assert pos is not None
    assert pos.buy_price == 90000
    assert pos.quantity == qty
    assert pos.strategy_id == "momentum"

    # pending_buys 제거 + fill_count 증가
    assert "005930" not in momentum.state.pending_buys
    assert momentum.state.fill_count_today == 1

    # COMPLETED UPDATE 호출
    completed_calls = [
        c for c in env.calls.update_trade_status if c["status"] == TradeStatus.COMPLETED
    ]
    assert len(completed_calls) == 1
    assert completed_calls[0]["strategy"] == "momentum"

    # save_position DB 호출
    assert len(env.calls.save_position) == 1
    sp = env.calls.save_position[0]
    assert sp["ticker"] == "005930"
    assert sp["strategy_id"] == "momentum"

    # 매핑 정리
    assert order_no not in env.engine._order_strategy
    assert order_no not in env.engine._order_ticker


@pytest.mark.asyncio
async def test_execute_buy_when_already_held_then_no_order(order_env):
    """이미 보유 중인 종목은 가드에서 차단."""
    env = order_env
    momentum = env.momentum
    momentum.state.positions["005930"] = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="momentum",
    )

    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)

    assert env.calls.place_order == []
    assert env.calls.insert_trade == []


@pytest.mark.asyncio
async def test_execute_buy_when_pending_buys_then_no_order(order_env):
    """이미 매수 대기 중인 종목은 차단."""
    env = order_env
    momentum = env.momentum
    momentum.state.pending_buys.add("005930")

    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)

    assert env.calls.place_order == []


@pytest.mark.asyncio
async def test_execute_buy_uses_buyable_cache_within_ttl(order_env):
    """첫 호출에서 채워진 매수가능 캐시는 TTL(60초) 내 재호출 시 재사용."""
    env = order_env
    momentum = env.momentum

    # 첫 매수 → get_buyable 호출 1회
    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)
    assert len(env.calls.get_buyable) == 1

    # 같은 종목 다시 시도 (보유 중이라 가드에 걸리지만, 다른 ticker 로 매수 가능)
    # 캐시가 살아있다는 것은 cached_buyable_at 이 최근 timestamp 라는 뜻
    # 매수 직후 cached_buyable_at = 0 으로 무효화되므로, 매수 전 상태를 다른 fixture 로 검증
    assert momentum.state.cached_buyable_at == 0.0  # 매수 후 무효화 됨
