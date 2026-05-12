"""사전 구독 티커 수집 — `_collect_presubscribe_tickers` 합집합 검증.

G안(2026-05-12) 적용: donchian_swing 스캔 후보는 사전 구독 제외 — Pull 폴링(_swing_buy_poll_loop)
으로 매수 평가. **단 donchian_swing 보유 포지션은 그대로 포함** (청산 위해).

- 돌파(VB+LTV) 스캔 종목 + 모든 전략 보유 포지션 합집합
- 중복 제거 (set 기반)
"""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_presubscribe_includes_breakout_and_swing_and_held_positions(scheduler_env):
    sched = scheduler_env.scheduler

    # VB enable + scanned tickers
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb._scanned_tickers = ["005930", "000660"]

    # LTV enable + scanned tickers
    ltv = sched.registry.get("long_tail_volatility")
    ltv.config.enabled = True
    ltv._scanned_tickers = ["035720"]

    # donchian enable + scanned tickers — G안(2026-05-12)으로 사전 구독 *제외* 대상
    donchian = sched.registry.get("donchian_swing")
    donchian.config.enabled = True
    donchian._scanned_tickers = ["051910"]
    # 단, donchian 보유 포지션은 청산 위해 그대로 포함
    donchian.state.positions["005380"] = Position(
        ticker="005380", buy_price=200000, quantity=1,
        order_no="O2", strategy_id="donchian_swing",
    )

    # momentum 보유 포지션 (스캔되지 않더라도 사전 구독에 포함되어야 한다)
    momentum = sched.registry.get("momentum")
    momentum.state.positions["051915"] = Position(
        ticker="051915", buy_price=600000, quantity=1,
        order_no="O1", strategy_id="momentum",
    )

    tickers = sched._collect_presubscribe_tickers()
    # G안: donchian 스캔(051910) 제외, 보유(005380) 포함, 돌파 스캔 포함, momentum 보유 포함
    assert set(tickers) == {"005930", "000660", "035720", "005380", "051915"}
    assert "051910" not in tickers, "donchian_swing 스캔 후보는 Pull 폴링이므로 사전 구독 제외"


@pytest.mark.asyncio
async def test_presubscribe_deduplicates_overlapping_tickers(scheduler_env):
    """VB 와 보유 포지션이 같은 종목을 가져도 중복 없이 1번만."""
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb._scanned_tickers = ["005930", "000660"]

    momentum = sched.registry.get("momentum")
    momentum.state.positions["005930"] = Position(  # 중복
        ticker="005930", buy_price=80000, quantity=1,
        order_no="O1", strategy_id="momentum",
    )

    tickers = sched._collect_presubscribe_tickers()
    assert sorted(tickers) == ["000660", "005930"]


@pytest.mark.asyncio
async def test_presubscribe_excludes_disabled_strategy_scans(scheduler_env):
    """비활성 전략의 스캔 종목은 포함되지 않음 — 단, 보유 포지션은 별도 (활성/비활성 무관)."""
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = False  # 비활성
    vb._scanned_tickers = ["005930"]

    # 비활성 전략의 보유 포지션도 합집합에는 들어감 (registry.all() 순회)
    vb.state.positions["000660"] = Position(
        ticker="000660", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="volatility_breakout",
    )

    tickers = sched._collect_presubscribe_tickers()
    assert "005930" not in tickers   # 비활성 전략 스캔은 제외
    assert "000660" in tickers       # 보유 포지션은 포함


@pytest.mark.asyncio
async def test_presubscribe_returns_list_type(scheduler_env):
    """반환 타입이 list 인지 확인 (set 으로 중복제거 후 list 변환)."""
    sched = scheduler_env.scheduler
    tickers = sched._collect_presubscribe_tickers()
    assert isinstance(tickers, list)


@pytest.mark.asyncio
async def test_presubscribe_when_no_strategy_enabled_returns_empty(scheduler_env):
    """모든 전략 비활성 + 보유 없음 → 빈 리스트."""
    sched = scheduler_env.scheduler
    # 기본적으로 모든 전략이 disabled 로 시작 (TradingScheduler.__init__ 가 momentum 만 enabled=True)
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = False  # 모멘텀도 비활성

    tickers = sched._collect_presubscribe_tickers()
    assert tickers == []
