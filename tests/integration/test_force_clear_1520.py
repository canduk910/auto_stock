"""15:20 KRX 메인 강제 청산 — `_force_clear_main_only` 정책 검증.

핵심 행위:
- 대상: VB / LTV 중 enabled 전략
- 각 전략의 `tradable_boards` 에 `POST_NXT` 가 포함되어 있으면 청산 보류 (NXT 애프터까지 유지)
- POST_NXT 미활성 전략은 `check_force_clear()` 결과 ticker 들에 대해 `execute_sell(FORCE_CLEAR)` 호출
- momentum / donchian_swing 은 이 함수의 대상이 아님 (각각 익일청산 / 추세추종)
"""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position, Signal

pytestmark = pytest.mark.integration


def _seed_pos(strategy, ticker, buy_price=80000, qty=10):
    pos = Position(
        ticker=ticker, buy_price=buy_price, quantity=qty,
        order_no="ORIG-1", strategy_id=strategy.strategy_id,
    )
    strategy.state.positions[ticker] = pos
    return pos


@pytest.mark.asyncio
async def test_force_clear_when_post_nxt_active_then_keeps_position(scheduler_env):
    """VB 의 tradable_boards 에 post_nxt 포함 → 15:20 강제청산 보류."""
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["tradable_boards"] = ["pre_nxt", "main", "post_nxt"]
    _seed_pos(vb, "005930")

    await sched._force_clear_main_only()

    # POST_NXT 활성 → 청산 미실행
    assert scheduler_env.calls.execute_sell == []
    assert "005930" in vb.state.positions


@pytest.mark.asyncio
async def test_force_clear_when_post_nxt_inactive_then_clears_main_holdings(scheduler_env):
    """VB 의 tradable_boards 에 post_nxt 없음 → 강제청산 실행."""
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["tradable_boards"] = ["main"]  # POST_NXT 미포함
    _seed_pos(vb, "005930")

    await sched._force_clear_main_only()

    # FORCE_CLEAR 신호로 매도 호출
    sells = scheduler_env.calls.execute_sell
    assert len(sells) == 1
    assert sells[0]["ticker"] == "005930"
    assert sells[0]["signal"] == Signal.FORCE_CLEAR
    assert sells[0]["strategy_id"] == "volatility_breakout"


@pytest.mark.asyncio
async def test_force_clear_skips_disabled_strategies(scheduler_env):
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = False  # 비활성
    vb.config.params["tradable_boards"] = ["main"]
    _seed_pos(vb, "005930")

    await sched._force_clear_main_only()
    assert scheduler_env.calls.execute_sell == []


@pytest.mark.asyncio
async def test_force_clear_handles_multiple_strategies_independently(scheduler_env):
    """LTV 는 POST_NXT 미활성 → 청산. VB 는 POST_NXT 활성 → 보존."""
    sched = scheduler_env.scheduler

    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["tradable_boards"] = ["pre_nxt", "main", "post_nxt"]
    _seed_pos(vb, "005930", buy_price=80000)

    ltv = sched.registry.get("long_tail_volatility")
    ltv.config.enabled = True
    ltv.config.params["tradable_boards"] = ["main"]
    _seed_pos(ltv, "000660", buy_price=100000)

    await sched._force_clear_main_only()

    # LTV 의 000660 만 청산 — 1건
    sells = scheduler_env.calls.execute_sell
    tickers = {c["ticker"]: c["strategy_id"] for c in sells}
    assert tickers == {"000660": "long_tail_volatility"}
    assert "005930" in vb.state.positions  # 보존
    assert "000660" not in ltv.state.positions  # 청산됨


@pytest.mark.asyncio
async def test_force_clear_does_not_target_momentum_or_donchian(scheduler_env):
    """momentum / donchian_swing 보유 종목은 이 함수의 대상 아님."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_pos(momentum, "005930")

    donchian = sched.registry.get("donchian_swing")
    donchian.config.enabled = True
    _seed_pos(donchian, "000660")

    await sched._force_clear_main_only()

    # momentum / donchian 은 _force_clear_main_only 의 대상 strategies 에 없음
    assert scheduler_env.calls.execute_sell == []
