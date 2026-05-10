"""P0 Red — NXT 프리(08:00) 매도 거부 시 positions 보존.

운영 회고:
- 08:00 NXT 프리 시점에 모멘텀 익일 청산이 KRX 단독 종목(012200 KEC)을 시장가 매도 시도
- KIS 응답: `APBK0918` + "장운영시간이 아닙니다" → 기존 로직은 보유 부족으로 오분류
- 메모리 positions 및 DB positions 즉시 삭제 → 좀비 포지션 (KIS엔 6주 그대로 있음)

요구 행위 (Step C-1 Red):
1. `place_order` 가 APBK0918 + '장운영시간' 메시지로 실패 시
2. `execute_sell` 는 재시도 의미 없으므로 즉시 break 한다 (재시도 횟수 1회로 끝)
3. **메모리 `state.positions[ticker]` 는 보존된다**
4. **DB `delete_position` 호출이 발생하지 않는다**
5. `_selling` 은 해제된다 (다음 거래 가능 시각에 자연 재트리거 위해)
6. trade_history 의 PENDING SELL 행도 INSERT 되지 않는다 (place_order 가 던졌으므로)
"""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position, Signal
from src.models.order import OrderSide

pytestmark = pytest.mark.integration


def _seed_position(strategy, ticker="012200", buy_price=15000, qty=6):
    pos = Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=qty,
        order_no="ORIG-FUNDED-001",
        strategy_id=strategy.strategy_id,
        high_since_buy=buy_price,
    )
    strategy.state.positions[ticker] = pos
    return pos


@pytest.mark.asyncio
async def test_execute_sell_when_market_closed_apbk0918_then_preserves_position(
    order_env, kis_error
):
    env = order_env
    momentum = env.momentum
    pos = _seed_position(momentum)

    # KIS 가 APBK0918 + 장운영시간 외 메시지로 거부 (NXT 프리 시점 KRX 단독 종목 매도)
    env.state.place_order_error = kis_error(
        code="APBK0918", msg="장운영시간이 아닙니다."
    )
    env.state.place_order_raises_persist = True  # 매 시도마다 같은 에러

    await env.engine.execute_sell("012200", Signal.NEXT_DAY_CLEAR, "momentum")

    # 1) 메모리 포지션 보존 — 좀비 포지션 방지의 핵심
    assert "012200" in momentum.state.positions, "장운영시간 외 거부 시 메모리 포지션은 보존되어야 함"
    assert momentum.state.positions["012200"].quantity == 6

    # 2) DB delete_position 호출되면 안 됨
    assert env.calls.delete_position == [], "장운영시간 외 거부 시 DB positions 삭제 금지"

    # 3) _selling 해제 (다음 거래 가능 시각에 재시도되도록)
    assert "012200" not in env.engine._selling

    # 4) PENDING SELL 행 INSERT 되지 않음 (place_order 가 모두 실패)
    pending_sells = [r for r in env.calls.insert_trade]
    assert pending_sells == [], "place_order 가 던졌으면 trade_history INSERT 도 없어야 함"


@pytest.mark.asyncio
async def test_execute_sell_when_market_closed_then_no_retry_storm(order_env, kis_error):
    """장운영시간 외 거부는 재시도 의미 없으므로 1번만 호출(즉시 break)."""
    env = order_env
    _seed_position(env.momentum)

    env.state.place_order_error = kis_error(
        code="APBK0918", msg="매매 불가 시간입니다."
    )
    env.state.place_order_raises_persist = True

    await env.engine.execute_sell("012200", Signal.NEXT_DAY_CLEAR, "momentum")

    # 장운영시간 외 거부는 재시도 안 함 (1회만)
    sell_attempts = [c for c in env.calls.place_order if c["side"] == OrderSide.SELL]
    assert len(sell_attempts) == 1, "장운영시간 외 거부는 즉시 break, 재시도 금지"


@pytest.mark.asyncio
async def test_execute_sell_when_real_insufficient_quantity_still_deletes(
    order_env, kis_error
):
    """회귀 가드 — 진짜 보유 부족(APBK1234)일 때는 기존 동작(positions 정리) 유지."""
    env = order_env
    _seed_position(env.momentum, ticker="012200")

    env.state.place_order_error = kis_error(
        code="APBK1234", msg="매도가능수량이 부족합니다."
    )
    env.state.place_order_raises_persist = True

    await env.engine.execute_sell("012200", Signal.NEXT_DAY_CLEAR, "momentum")

    # 진짜 보유 부족 → 기존 안전장치(positions 정리)는 유지되어야 함
    assert "012200" not in env.momentum.state.positions
    assert env.calls.delete_position == [{"ticker": "012200"}]
