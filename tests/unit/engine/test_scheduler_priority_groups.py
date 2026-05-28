"""scheduler._build_priority_groups 헬퍼 (E1, 2026-05-12).

`subscribe_filtered_stocks(priority_groups=...)` 가 받을 5개 카테고리 dict 를
scheduler 가 산출하는지 검증한다.

카테고리:
- positions: 모든 전략 보유 합집합 (dedupe)
- next_day_clear: `_pending_next_day_clear` set 의 ticker (dedupe)
- swing: `_collect_swing_tickers()` (donchian_swing)
- momentum: `momentum_tickers` 인자 그대로
- breakout: `_collect_breakout_tickers()` (volatility_breakout + long_tail_volatility
            + bull_flag_breakout + vcp_breakout — 사이클 48. 본 케이스는 VB/LTV 만 등록)

호출 사양:
    `self._build_priority_groups(momentum_tickers: list[str] | None = None) -> dict[str, list[str]]`

빈 카테고리도 반드시 키 자체는 5개 모두 존재 (빈 리스트).
"""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 더블: scanned_tickers + positions 을 주입 가능한 전략 스텁
# ---------------------------------------------------------------------------
class _DummyStrategy(StrategyBase):
    def __init__(
        self,
        config: StrategyConfig,
        scanned: list[str] | None = None,
        position_tickers: list[str] | None = None,
    ):
        super().__init__(config)
        self._scanned_tickers: list[str] = list(scanned or [])
        for t in position_tickers or []:
            self.state.positions[t] = Position(
                ticker=t,
                buy_price=10000,
                quantity=1,
                order_no=f"O-{t}",
                strategy_id=config.strategy_id,
            )

    async def prepare(self) -> None:
        pass

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price):
        return 0

    def get_scanned_tickers(self) -> list[str]:
        return list(self._scanned_tickers)


def _make_scheduler_stub(
    registry: StrategyRegistry,
    pending: set[tuple[str, str]] | None = None,
):
    """TradingScheduler 인스턴스 없이 _build_priority_groups 만 호출하기 위한 stub."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = registry
    sched._pending_next_day_clear = set(pending or set())
    return sched


# ---------------------------------------------------------------------------
# Case F: 5개 카테고리 모두 산출
# ---------------------------------------------------------------------------
def test_build_priority_groups_returns_all_five_keys():
    """5개 키 모두 반환 + 각 값 정확."""
    registry = StrategyRegistry()
    vb = _DummyStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True),
        scanned=["VB1", "VB2"],
        position_tickers=["P_VB"],
    )
    ltv = _DummyStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="LTV", weight=0.3, enabled=True),
        scanned=["LTV1"],
        position_tickers=[],
    )
    ds = _DummyStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="DS", weight=0.2, enabled=True),
        scanned=["DS1", "DS2", "DS3"],
        position_tickers=["P_DS"],
    )
    mom = _DummyStrategy(
        StrategyConfig(strategy_id="momentum", name="MOM", weight=0.2, enabled=True),
        scanned=[],
        position_tickers=["P_MOM"],
    )
    for s in (vb, ltv, ds, mom):
        registry.register(s)

    sched = _make_scheduler_stub(
        registry,
        pending={("ND1", "momentum"), ("ND2", "long_tail_volatility")},
    )
    groups = sched._build_priority_groups(momentum_tickers=["M_SCAN1", "M_SCAN2"])

    # 5개 키 모두 존재
    assert set(groups.keys()) == {"positions", "next_day_clear", "swing", "momentum", "breakout"}

    # positions: P_VB + P_DS + P_MOM (3개, dedupe)
    assert set(groups["positions"]) == {"P_VB", "P_DS", "P_MOM"}

    # next_day_clear: ND1, ND2
    assert set(groups["next_day_clear"]) == {"ND1", "ND2"}

    # swing: G안(2026-05-12) — 항상 빈 list. donchian_swing 후보는 Pull 폴링으로 평가.
    # 보유 종목은 positions HIGH 그룹에 포함되어 청산(ATR/-7%) 보장.
    assert groups["swing"] == []
    # donchian_swing 보유(P_DS)는 positions 그룹에 그대로 (위에서 검증됨)

    # breakout: VB1, VB2, LTV1 (이 케이스는 VB/LTV 만 등록 — 사이클 48 후 BFB/VCP 도
    # 동일 그룹 대상이며 별도 검증은 test_cycle48_bfb_vcp_subscription_wiring.py)
    assert set(groups["breakout"]) == {"VB1", "VB2", "LTV1"}

    # momentum: 인자 그대로
    assert groups["momentum"] == ["M_SCAN1", "M_SCAN2"]


# ---------------------------------------------------------------------------
# Case G: _pending_next_day_clear 비어있으면 next_day_clear=[]
# ---------------------------------------------------------------------------
def test_build_priority_groups_empty_pending_yields_empty_list():
    registry = StrategyRegistry()
    sched = _make_scheduler_stub(registry, pending=set())
    groups = sched._build_priority_groups(momentum_tickers=None)

    assert groups["next_day_clear"] == []
    # 다른 카테고리도 모두 빈 리스트 (등록된 전략 없음)
    assert groups["positions"] == []
    assert groups["swing"] == []
    assert groups["breakout"] == []
    assert groups["momentum"] == []


# ---------------------------------------------------------------------------
# Case H: 두 전략이 같은 ticker 보유 → positions 합집합 dedupe
# ---------------------------------------------------------------------------
def test_build_priority_groups_dedupes_positions_across_strategies():
    """동일 ticker 가 두 전략에 있으면 positions 리스트에 1번만."""
    registry = StrategyRegistry()
    mom = _DummyStrategy(
        StrategyConfig(strategy_id="momentum", name="MOM", weight=0.5, enabled=True),
        position_tickers=["SHARED", "MOM_ONLY"],
    )
    vb = _DummyStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.5, enabled=True),
        position_tickers=["SHARED", "VB_ONLY"],
    )
    registry.register(mom)
    registry.register(vb)

    sched = _make_scheduler_stub(registry)
    groups = sched._build_priority_groups()

    assert set(groups["positions"]) == {"SHARED", "MOM_ONLY", "VB_ONLY"}
    assert len(groups["positions"]) == 3, "동일 ticker dedupe 후 3개"


# ---------------------------------------------------------------------------
# 회귀: momentum_tickers=None → momentum=[]
# ---------------------------------------------------------------------------
def test_build_priority_groups_momentum_none_yields_empty_list():
    registry = StrategyRegistry()
    sched = _make_scheduler_stub(registry)
    groups = sched._build_priority_groups(momentum_tickers=None)
    assert groups["momentum"] == []


# ---------------------------------------------------------------------------
# 회귀: next_day_clear 도 dedupe (동일 ticker 가 두 전략으로 등록되어도 1회)
# ---------------------------------------------------------------------------
def test_build_priority_groups_dedupes_next_day_clear():
    registry = StrategyRegistry()
    sched = _make_scheduler_stub(
        registry,
        pending={("X", "momentum"), ("X", "volatility_breakout"), ("Y", "momentum")},
    )
    groups = sched._build_priority_groups()
    assert set(groups["next_day_clear"]) == {"X", "Y"}
    assert len(groups["next_day_clear"]) == 2
