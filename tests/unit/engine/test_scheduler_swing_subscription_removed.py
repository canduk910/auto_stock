"""scheduler — swing 후보를 WebSocket 구독에서 제외 (G안, 2026-05-12).

donchian_swing 은 Pull 폴링(_swing_buy_poll_loop) 으로 매수 평가 → WebSocket 구독 불필요.
단, **보유 종목은 그대로 positions HIGH 그룹**으로 구독되어야 함 (청산 평가 위해).

검증:
1. `_collect_presubscribe_tickers()` 에 swing scanned ticker 미포함, 보유는 포함
2. `_build_priority_groups()["swing"]` 가 `[]`
3. `_scan_loop` extra 합집합에 swing scanned ticker 미포함, 보유는 포함
4. donchian_swing 보유 종목은 `_build_priority_groups()["positions"]` 에 포함 (HIGH 보장)
"""

from __future__ import annotations

import pytest

from src.engine.scheduler import TradingScheduler
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


class _DummyStrategy(StrategyBase):
    def __init__(self, config, scanned=None, positions=None):
        super().__init__(config)
        self._scanned_tickers = list(scanned or [])
        for t in positions or []:
            self.state.positions[t] = Position(
                ticker=t, buy_price=10000, quantity=1, order_no=f"O-{t}",
                strategy_id=config.strategy_id,
            )

    async def prepare(self):
        pass

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0

    def get_scanned_tickers(self):
        return list(self._scanned_tickers)


def _make_scheduler():
    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = StrategyRegistry()
    sched._pending_next_day_clear = set()
    return sched


# ---------------------------------------------------------------------------
# Case 1: presubscribe 에서 swing 스캔 후보 제외
# ---------------------------------------------------------------------------
def test_collect_presubscribe_excludes_swing_scanned():
    """donchian_swing 의 get_scanned_tickers() 는 사전 구독 목록에 포함되지 않아야 한다."""
    sched = _make_scheduler()

    ds = _DummyStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="DS", weight=0.2, enabled=True),
        scanned=["DS_SCAN1", "DS_SCAN2"],
        positions=["DS_HOLD"],
    )
    vb = _DummyStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True),
        scanned=["VB_SCAN1"],
    )
    sched.registry.register(ds)
    sched.registry.register(vb)

    presub = sched._collect_presubscribe_tickers()

    # swing 스캔 후보는 제외
    assert "DS_SCAN1" not in presub
    assert "DS_SCAN2" not in presub
    # swing 보유는 포함 (positions 합집합 경로)
    assert "DS_HOLD" in presub
    # breakout 스캔 후보는 그대로 포함
    assert "VB_SCAN1" in presub


# ---------------------------------------------------------------------------
# Case 2: priority_groups["swing"] 빈 list
# ---------------------------------------------------------------------------
def test_build_priority_groups_swing_is_empty():
    """G안 적용: swing 키는 항상 빈 list (Pull 폴링으로 평가하므로)."""
    sched = _make_scheduler()

    ds = _DummyStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="DS", weight=0.2, enabled=True),
        scanned=["DS_SCAN1", "DS_SCAN2", "DS_SCAN3"],
        positions=["DS_HOLD"],
    )
    sched.registry.register(ds)

    groups = sched._build_priority_groups(momentum_tickers=None)

    # swing 키는 빈 list — donchian_swing 스캔 후보는 더 이상 WebSocket 구독 안 함
    assert groups["swing"] == []
    # 보유는 positions HIGH 그룹에 포함
    assert "DS_HOLD" in groups["positions"]


# ---------------------------------------------------------------------------
# Case 3: donchian_swing 보유 종목은 HIGH 그룹 절대 보장
# ---------------------------------------------------------------------------
def test_donchian_holdings_go_to_high_positions():
    """청산(ATR 트레일링/하드 -7%) 보장 위해 donchian 보유는 HIGH 그룹 필수."""
    sched = _make_scheduler()

    ds = _DummyStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="DS", weight=0.2, enabled=True),
        scanned=[],
        positions=["DS_HOLD1", "DS_HOLD2"],
    )
    sched.registry.register(ds)

    groups = sched._build_priority_groups()

    # donchian_swing 보유 2종목 모두 positions HIGH 그룹
    assert "DS_HOLD1" in groups["positions"]
    assert "DS_HOLD2" in groups["positions"]


# ---------------------------------------------------------------------------
# Case 4: swing 스캔 후보가 HIGH 보유와 분리되어 처리됨
# ---------------------------------------------------------------------------
def test_swing_scanned_not_subscribed_but_holding_yes():
    """스캔 후보는 구독 안 하지만, 같은 종목이 보유이기도 하면 HIGH 로 구독."""
    sched = _make_scheduler()

    # DS_OVERLAP 은 스캔에도 있고 보유에도 있는 종목
    ds = _DummyStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="DS", weight=0.2, enabled=True),
        scanned=["DS_OVERLAP", "DS_SCAN_ONLY"],
        positions=["DS_OVERLAP", "DS_HOLD_ONLY"],
    )
    sched.registry.register(ds)

    groups = sched._build_priority_groups()

    # 스캔만(보유 아님) 종목은 어디에도 없어야 함
    assert "DS_SCAN_ONLY" not in groups["swing"]
    assert "DS_SCAN_ONLY" not in groups["positions"]
    # 보유 종목은 positions
    assert "DS_HOLD_ONLY" in groups["positions"]
    assert "DS_OVERLAP" in groups["positions"]
