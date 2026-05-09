"""보드별 시가 확정 — `_confirm_breakout_open_prices` 흐름 검증.

핵심 행위:
- 대상: VB / LTV 중 enabled + 해당 board 가 tradable_boards 에 포함된 전략만
- 각 종목에 대해 ticker_prices[ticker]["open_price"] 폴링 (최대 max_wait_s)
- 받으면 strategy.on_open_price_confirmed(ticker, open_price, board=board)
- 시간 초과 시 KIS API 폴백 — fetch_stock_detail
- board 미지정 시 SessionTracker 활성 보드 우선순위 (main → post_nxt → pre_nxt)
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _seed_target(strategy, ticker, prev_range=1000, k=0.5):
    base = int(prev_range * k)
    strategy._targets[ticker] = {
        "k": k, "prev_range": prev_range, "target_offset_base": base,
        "target_offset": base, "target_price": 0, "open_price": 0, "boards": {},
    }
    strategy._open_confirmed[ticker] = {}


@pytest.mark.asyncio
async def test_confirm_main_board_when_open_price_in_cache_then_target_set(scheduler_env):
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["k_value_krx_main"] = 1.0
    _seed_target(vb, "005930", prev_range=1000, k=0.5)  # base 500

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 80000}

    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)

    # main 보드 target 등록
    board_info = vb._targets["005930"]["boards"]["main"]
    assert board_info["open_price"] == 80000
    assert board_info["target_price"] == 80500
    assert vb._open_confirmed["005930"]["main"] is True


@pytest.mark.asyncio
async def test_confirm_skips_strategy_when_board_not_in_tradable(scheduler_env):
    """tradable_boards 에 main 이 없는 전략은 main 보드 확정 대상에서 제외."""
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["tradable_boards"] = ["pre_nxt"]  # main 미포함
    _seed_target(vb, "005930")

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 80000}

    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)

    # main 보드 확정 발생 X
    assert "main" not in vb._open_confirmed.get("005930", {})


@pytest.mark.asyncio
async def test_confirm_falls_back_to_kis_api_when_open_price_missing(scheduler_env, monkeypatch):
    """ticker_prices 에 open_price 없으면 KIS fetch_stock_detail 폴백."""
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["k_value_krx_main"] = 1.0
    _seed_target(vb, "005930", prev_range=1000, k=0.5)

    # ticker_prices 에는 시가 없음
    from src.engine import scanner
    scanner.ticker_prices.pop("005930", None)

    # KIS API 폴백 모킹
    fetch_calls = []

    async def fake_fetch_stock_detail(ticker):
        fetch_calls.append(ticker)
        return {"stck_oprc": "82000"}

    import src.api.condition as condition_mod
    monkeypatch.setattr(condition_mod, "fetch_stock_detail", fake_fetch_stock_detail)

    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)

    # KIS 폴백으로 시가 82000 확정
    assert fetch_calls == ["005930"]
    board_info = vb._targets["005930"]["boards"]["main"]
    assert board_info["open_price"] == 82000


@pytest.mark.asyncio
async def test_confirm_when_board_arg_omitted_then_uses_active_board(scheduler_env, monkeypatch):
    """board=None 일 때 SessionTracker 활성 보드 자동 결정."""
    sched = scheduler_env.scheduler
    from src.engine.session import session_tracker, MarketBoard

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.PRE_NXT}))

    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["k_value_nxt_pre"] = 1.0
    vb.config.params["tradable_boards"] = ["pre_nxt", "main", "post_nxt"]
    _seed_target(vb, "005930", prev_range=1000, k=0.5)

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 79000}

    await sched._confirm_breakout_open_prices(max_wait_s=0.5, interval_s=0.5)

    # pre_nxt 보드로 확정됨
    assert "pre_nxt" in vb._open_confirmed["005930"]


@pytest.mark.asyncio
async def test_confirm_does_nothing_when_no_enabled_strategy(scheduler_env):
    sched = scheduler_env.scheduler
    # 어느 전략도 enabled X (default)
    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)
    # 외부 호출 없음
    assert scheduler_env.calls.fetch_stock_detail == []
