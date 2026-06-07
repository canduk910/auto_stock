"""익일 NXT 프리 청산 — `_execute_next_day_clear` 흐름 검증.

핵심 행위:
- 대상 전략: momentum + long_tail_volatility 중 enabled 인 것
- is_next_day=True 포지션만 처리
- `_next_day_clear_pending = True` 설정 → on_tick 의 NEXT_DAY_CLEAR 억제 (손절은 유지)
- 30초 안정화 대기 (NEXT_DAY_STABILIZE_SECS, asyncio.sleep — fixture 가 무력화)
- 시가 미수신 시 `_resolve_open_price` 폴백
- gap_rate >= gap_up_threshold(10%) → 트레일링 모드 (직접 청산 X)
- gap_rate < threshold → execute_sell(NEXT_DAY_CLEAR) 즉시
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_KST_TEST = timezone(timedelta(hours=9))  # 사이클 68 hotfix

import pytest

from src.engine.strategy_base import Position, Signal

pytestmark = pytest.mark.integration


def _seed_next_day_pos(strategy, ticker, buy_price=80000, qty=10):
    pos = Position(
        ticker=ticker, buy_price=buy_price, quantity=qty,
        order_no="ORIG-NEXT", strategy_id=strategy.strategy_id,
        buy_date=datetime.now(_KST_TEST).date() - timedelta(days=1),  # 익일
        high_since_buy=buy_price,
    )
    strategy.state.positions[ticker] = pos
    return pos


@pytest.mark.asyncio
async def test_next_day_clear_when_no_overnight_positions_then_returns_early(scheduler_env):
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    # 보유 없음
    await sched._execute_next_day_clear()
    assert scheduler_env.calls.execute_sell == []


@pytest.mark.asyncio
async def test_next_day_clear_when_gap_below_threshold_then_immediate_clear(scheduler_env):
    """갭률 5% < 10% → 즉시 청산."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "005930", buy_price=80000)

    # 시가 84000 = 갭 +5%
    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 84000, "current_price": 84000}

    await sched._execute_next_day_clear()

    sells = scheduler_env.calls.execute_sell
    assert len(sells) == 1
    assert sells[0]["ticker"] == "005930"
    assert sells[0]["signal"] == Signal.NEXT_DAY_CLEAR
    assert sells[0]["strategy_id"] == "momentum"


@pytest.mark.asyncio
async def test_next_day_clear_when_gap_above_threshold_then_trailing_mode_no_sell(scheduler_env):
    """갭률 +12% ≥ 10% → 트레일링 모드 (직접 청산 X, on_tick 에서 처리)."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "005930", buy_price=80000)

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 89600, "current_price": 89600}  # +12%

    await sched._execute_next_day_clear()

    # 트레일링 모드 — execute_sell 호출 X
    assert scheduler_env.calls.execute_sell == []
    # 포지션 유지
    assert "005930" in momentum.state.positions


@pytest.mark.asyncio
async def test_next_day_clear_pending_flag_lifecycle(scheduler_env):
    """_next_day_clear_pending 플래그가 set → 안정화 대기 → clear 흐름을 따라야 한다."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "005930", buy_price=80000)

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 84000, "current_price": 84000}

    # 함수 종료 시점에는 pending=False (asyncio.sleep 도 무력화)
    await sched._execute_next_day_clear()
    assert momentum._next_day_clear_pending is False


@pytest.mark.asyncio
async def test_next_day_clear_subscribes_websocket_for_overnight_tickers(scheduler_env):
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "005930", buy_price=80000)

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 84000, "current_price": 84000}

    await sched._execute_next_day_clear()

    # WS subscribe 호출 — 익일 청산 대상 종목 1건
    subs = scheduler_env.calls.ws_subscribe
    tickers = {s["tr_key"] for s in subs}
    assert "005930" in tickers


@pytest.mark.asyncio
async def test_next_day_clear_handles_both_momentum_and_ltv(scheduler_env):
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    ltv = sched.registry.get("long_tail_volatility")
    ltv.config.enabled = True
    _seed_next_day_pos(momentum, "005930", buy_price=80000)
    _seed_next_day_pos(ltv, "000660", buy_price=100000)

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 84000}   # +5% 청산
    scanner.ticker_prices["000660"] = {"open_price": 105000}  # +5% 청산

    await sched._execute_next_day_clear()

    by_strat = {c["strategy_id"]: c["ticker"] for c in scheduler_env.calls.execute_sell}
    assert by_strat == {"momentum": "005930", "long_tail_volatility": "000660"}
