"""정산 후 일일 상태 리셋 — `_reset_daily_state` 흐름 검증.

핵심 행위:
- 모든 전략의 state 초기화 (positions / pending_buys / sold_today / pnl / investment / disabled / signals / low_funds / 퍼널 카운터)
- OrderEngine 추적 상태 초기화 (_selling, _filled_qty, _order_qty, _order_strategy, _order_ticker, _pending_buy_orders, _pending_cancel_tasks)
- scanner 전역 dict clear + ticker_names 에 STATIC_TICKER_NAMES 재시드
"""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_reset_clears_all_strategy_state_fields(scheduler_env):
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    vb = sched.registry.get("volatility_breakout")

    # 더러운 상태 시드
    momentum.state.positions["005930"] = Position(
        ticker="005930", buy_price=80000, quantity=1,
        order_no="O1", strategy_id="momentum",
    )
    momentum.state.pending_buys.add("000660")
    momentum.state.sold_today.add("035720")
    momentum.state.daily_realized_pnl = -50000
    momentum.state.total_investment = 5_000_000
    momentum.state.buy_disabled = True
    momentum.state.buy_signals.append({"ticker": "005930"})
    momentum.state.low_funds_tickers["015760"] = 9999
    momentum.state.signal_count_today = 7
    momentum.state.order_attempt_today = 5
    momentum.state.fill_count_today = 3
    vb.state.positions["000660"] = Position(
        ticker="000660", buy_price=100000, quantity=1,
        order_no="O2", strategy_id="volatility_breakout",
    )

    sched._reset_daily_state()

    # 모든 전략 검증
    for s in (momentum, vb):
        assert s.state.positions == {}
        assert s.state.pending_buys == set()
        assert s.state.sold_today == set()
        assert s.state.daily_realized_pnl == 0
        assert s.state.total_investment == 0
        assert s.state.buy_disabled is False
        assert s.state.buy_signals == []
        assert s.state.low_funds_tickers == {}
        assert s.state.signal_count_today == 0
        assert s.state.order_attempt_today == 0
        assert s.state.fill_count_today == 0


def test_reset_clears_order_engine_tracking_state(scheduler_env):
    sched = scheduler_env.scheduler
    eng = sched.order_engine

    eng._selling.add("005930")
    eng._filled_qty["BUY-001"] = 5
    eng._order_qty["BUY-001"] = 10
    eng._order_strategy["BUY-001"] = "momentum"
    eng._order_ticker["BUY-001"] = "005930"
    eng._pending_buy_orders["BUY-001"] = {"ticker": "005930", "price": 80000, "quantity": 10, "strategy_id": "momentum"}

    sched._reset_daily_state()

    assert eng._selling == set()
    assert eng._filled_qty == {}
    assert eng._order_qty == {}
    assert eng._order_strategy == {}
    assert eng._order_ticker == {}
    assert eng._pending_buy_orders == {}


def test_reset_clears_scanner_globals_and_reseeds_static_names(scheduler_env):
    sched = scheduler_env.scheduler
    from src.engine import scanner

    # 더러운 상태 시드
    scanner.ticker_prices["005930"] = {"current_price": 80000}
    scanner.ticker_prev_close["005930"] = 70000
    scanner.ticker_market_info["005930"] = {"market": "KOSPI"}
    scanner.ticker_names["005930"] = "삼성전자"

    sched._reset_daily_state()

    # 휘발성 dict 초기화
    assert scanner.ticker_prices == {}
    assert scanner.ticker_prev_close == {}
    assert scanner.ticker_market_info == {}
    # ticker_names 는 STATIC 재시드 — 빈 dict 는 아니어야 함 (정적 종목명이 다시 들어옴)
    assert isinstance(scanner.ticker_names, dict)
    # STATIC_TICKER_NAMES 재시드 검증 — STATIC 자체와 일치
    assert scanner.ticker_names == scanner.STATIC_TICKER_NAMES


@pytest.mark.asyncio
async def test_reset_cancels_pending_cancel_tasks(scheduler_env):
    """진행 중이던 취소 task 들이 모두 cancel + dict clear."""
    import asyncio

    sched = scheduler_env.scheduler
    eng = sched.order_engine

    async def long_running():
        await asyncio.sleep(60)

    real_task = asyncio.create_task(long_running())
    eng._pending_cancel_tasks["005930"] = real_task
    # cycle273a (D2-가-a) — 짝 dict(order_no 그림자)도 같은 자리에서 함께 검증한다
    # (직전 검증 LOW#4 — S1 의 동행 clear 를 잡는 가드가 이 파일에 0건이었다).
    eng._pending_cancel_order_no["005930"] = "BUY-001"

    sched._reset_daily_state()

    # dict 즉시 clear
    assert eng._pending_cancel_tasks == {}
    assert eng._pending_cancel_order_no == {}, (
        "짝 dict(order_no 그림자) 가 일일 정산 후에도 남아 있다(scheduler.py S1 동행 clear 회귀)"
    )
    # task.cancel() 호출 후 cancelled() 가 True 가 되려면 이벤트 루프 1회 yield 필요
    await asyncio.sleep(0)
    assert real_task.cancelled() or real_task.done()
