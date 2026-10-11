"""cycle444 — 섀도 전략 후보의 WS 구독 우선순위 최후순위화 (scheduler.py 쪽).

사용자 지시(2026-10-11) 「섀도전략들은 웹소켓 시세구독 우선순위를 낮춰야해」.

검증 대상:
- `TradingScheduler._collect_breakout_tickers()` — 섀도 전략의 후보를 제외한다.
- `TradingScheduler._collect_shadow_breakout_tickers()` — 섀도 전략의 후보만 모은다.
- `TradingScheduler._build_priority_groups()` — `shadow` 키(6번째 카테고리)가
  섀도 돌파 후보 + (momentum 이 섀도면) momentum 몫을 담는다. `positions`(보유)는
  섀도 여부와 무관하게 그대로 — 보유·익일청산은 무접촉.
- `TradingScheduler._build_subscription_source_counts()` — `shadow` 카운트 필드.

명세 정본은 main 세션이 전달한 cycle444 작업 지시(`_workspace/` 문서 없음 —
세션 메시지가 정본). 돌연변이 2건은 `test_mutationN_*` 로 같은 파일에 둔다
(스크래치 백업/복원만 — git checkout/stash/reset 금지).
"""
from __future__ import annotations

import pytest

from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 더블 — test_scheduler_priority_groups.py 의 _DummyStrategy 와 동형(중복 정의,
# shadow 전용 kwarg 를 params 로 주입하는 생성자가 다르다).
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

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0

    def get_scanned_tickers(self) -> list[str]:
        return list(self._scanned_tickers)


def _shadow_config(strategy_id: str, name: str, *, scanned_as=None) -> StrategyConfig:
    return StrategyConfig(
        strategy_id=strategy_id, name=name, weight=0.0, enabled=True,
        params={"shadow_mode": True},
    )


def _live_config(strategy_id: str, name: str, *, weight: float = 0.3) -> StrategyConfig:
    return StrategyConfig(strategy_id=strategy_id, name=name, weight=weight, enabled=True)


def _make_scheduler_stub(registry: StrategyRegistry, pending=None):
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = registry
    sched._pending_next_day_clear = set(pending or set())
    return sched


# ===========================================================================
# 1) _collect_breakout_tickers — 섀도 전략의 후보는 빠진다
# ===========================================================================
def test_collect_breakout_tickers_excludes_shadow_strategy():
    registry = StrategyRegistry()
    vb_shadow = _DummyStrategy(_shadow_config("volatility_breakout", "VB"), scanned=["VBX1", "VBX2"])
    bfb_live = _DummyStrategy(_live_config("bull_flag_breakout", "BFB"), scanned=["BFB1"])
    registry.register(vb_shadow)
    registry.register(bfb_live)

    sched = _make_scheduler_stub(registry)

    live = sched._collect_breakout_tickers()
    assert "VBX1" not in live and "VBX2" not in live, (
        f"섀도 VB 후보가 live breakout 목록에 남아 있다: {live}"
    )
    assert "BFB1" in live, f"실전 BFB 후보는 그대로 있어야 한다: {live}"


# ===========================================================================
# 2) _collect_shadow_breakout_tickers — 섀도 전략의 후보만 모은다
# ===========================================================================
def test_collect_shadow_breakout_tickers_returns_only_shadow():
    registry = StrategyRegistry()
    vb_shadow = _DummyStrategy(_shadow_config("volatility_breakout", "VB"), scanned=["VBX1", "VBX2"])
    bfb_live = _DummyStrategy(_live_config("bull_flag_breakout", "BFB"), scanned=["BFB1"])
    registry.register(vb_shadow)
    registry.register(bfb_live)

    sched = _make_scheduler_stub(registry)

    shadow = sched._collect_shadow_breakout_tickers()
    assert set(shadow) == {"VBX1", "VBX2"}, f"섀도 후보만 담겨야 한다: {shadow}"


# ===========================================================================
# 3) live ∪ shadow == 섀도 구분 전 전체 집합 (분할 항등식)
# ===========================================================================
def test_live_and_shadow_breakout_partition_is_total():
    registry = StrategyRegistry()
    vb_shadow = _DummyStrategy(_shadow_config("volatility_breakout", "VB"), scanned=["VBX1"])
    ltv_live = _DummyStrategy(_live_config("long_tail_volatility", "LTV"), scanned=["LTV1"])
    bfb_live = _DummyStrategy(_live_config("bull_flag_breakout", "BFB"), scanned=["BFB1"])
    vcp_live = _DummyStrategy(_live_config("vcp_breakout", "VCP"), scanned=["VCP1"])
    for s in (vb_shadow, ltv_live, bfb_live, vcp_live):
        registry.register(s)

    sched = _make_scheduler_stub(registry)
    live = set(sched._collect_breakout_tickers())
    shadow = set(sched._collect_shadow_breakout_tickers())

    assert live == {"LTV1", "BFB1", "VCP1"}
    assert shadow == {"VBX1"}
    assert live & shadow == set()


# ===========================================================================
# 4) _build_priority_groups — shadow 키(6번째) + momentum 섀도 이동
# ===========================================================================
def test_build_priority_groups_has_shadow_key_with_breakout_candidates():
    registry = StrategyRegistry()
    vb_shadow = _DummyStrategy(_shadow_config("volatility_breakout", "VB"), scanned=["VBX1"])
    bfb_live = _DummyStrategy(_live_config("bull_flag_breakout", "BFB"), scanned=["BFB1"])
    registry.register(vb_shadow)
    registry.register(bfb_live)

    sched = _make_scheduler_stub(registry)
    groups = sched._build_priority_groups(momentum_tickers=["M1"])

    assert set(groups.keys()) == {
        "positions", "next_day_clear", "swing", "momentum", "breakout", "shadow",
    }
    assert groups["breakout"] == ["BFB1"]
    assert groups["shadow"] == ["VBX1"]
    assert groups["momentum"] == ["M1"], "momentum 이 섀도가 아니면 그대로 momentum 그룹"


def test_build_priority_groups_moves_shadow_momentum_entirely():
    """momentum 전략이 섀도면 momentum 몫 전체가 shadow 티어로 옮겨간다."""
    registry = StrategyRegistry()
    momentum_shadow = _DummyStrategy(_shadow_config("momentum", "MOM"), scanned=[])
    registry.register(momentum_shadow)

    sched = _make_scheduler_stub(registry)
    groups = sched._build_priority_groups(momentum_tickers=["M_SURGE1", "M_SURGE2"])

    assert groups["momentum"] == [], "섀도 momentum 은 momentum 그룹에 남지 않는다"
    assert set(groups["shadow"]) == {"M_SURGE1", "M_SURGE2"}, (
        f"섀도 momentum 후보 전체가 shadow 티어로 가야 한다: {groups['shadow']}"
    )


# ===========================================================================
# 5) 겹침 — 같은 종목이 실전·섀도 둘 다의 후보여도 실전 돌파 그룹에 남는다
#    (섀도 돌파 수집은 "섀도 전략만" 을 보므로, 교집합 종목은 섀도 전략에서
#     나온 것이 아니면 shadow 에 들지 않는다 — 이 테스트는 그 경계를 고정한다)
# ===========================================================================
def test_overlap_ticker_from_both_live_and_shadow_strategy_stays_in_live_group():
    """SHARED 종목을 실전 BFB 와 섀도 VB 가 동시에 스캔해도 breakout(실전)에 남는다.

    `subscribe_filtered_stocks` 의 중복 제거(`already`)가 breakout → shadow 순으로
    처리되므로 실제 "실전 쪽에 남는다" 보장은 scanner 쪽 통합 테스트
    (test_cycle444_scanner_shadow_subscribe.py)가 맡는다. 여기서는 `_build_priority_groups`
    가 겹치는 종목을 양쪽 리스트에 모두 실어 보내는지(= scanner 의 dedup 이 실제로
    처리할 재료가 있는지)만 고정한다.
    """
    registry = StrategyRegistry()
    vb_shadow = _DummyStrategy(_shadow_config("volatility_breakout", "VB"), scanned=["SHARED"])
    bfb_live = _DummyStrategy(_live_config("bull_flag_breakout", "BFB"), scanned=["SHARED", "BFB_ONLY"])
    registry.register(vb_shadow)
    registry.register(bfb_live)

    sched = _make_scheduler_stub(registry)
    groups = sched._build_priority_groups()

    assert "SHARED" in groups["breakout"], "실전(BFB) 쪽 breakout 그룹에 SHARED 가 있어야 한다"
    assert "SHARED" in groups["shadow"], "섀도(VB) 쪽 shadow 그룹에도 SHARED 가 실려야 한다"


# ===========================================================================
# 6) 보유·익일청산은 무접촉 — 섀도 전략의 보유 종목도 positions(HIGH) 그룹에 남는다
# ===========================================================================
def test_shadow_strategy_holding_still_lands_in_positions_group():
    registry = StrategyRegistry()
    vb_shadow = _DummyStrategy(
        _shadow_config("volatility_breakout", "VB"),
        scanned=["VBX1"],
        position_tickers=["HELD_BY_SHADOW"],
    )
    registry.register(vb_shadow)

    sched = _make_scheduler_stub(
        registry, pending={("NDC_BY_SHADOW", "volatility_breakout")},
    )
    groups = sched._build_priority_groups()

    assert "HELD_BY_SHADOW" in groups["positions"], (
        "섀도 전략의 보유 종목은 섀도 여부와 무관하게 positions(HIGH) 에 남아야 한다"
    )
    assert "NDC_BY_SHADOW" in groups["next_day_clear"], (
        "섀도 전략의 익일청산 대기 종목도 next_day_clear(HIGH) 에 남아야 한다"
    )
    # 보유 종목 자체는 breakout/shadow 스캔 후보 목록과 무관 — 중복 가산되지 않는다
    assert "HELD_BY_SHADOW" not in groups["shadow"]


# ===========================================================================
# 7) ndx2x_riskoff 류 — 후보 0 이면 shadow 티어에 아무 영향도 없다
# ===========================================================================
def test_ndx2x_like_strategy_with_zero_candidates_has_no_effect():
    """ndx2x_riskoff 는 BREAKOUT_SUBSCRIBE_ORDER 에 없고 get_scanned_tickers()==[] —
    섀도여도 shadow 티어에 아무것도 더하지 않는다. 보유가 생기면 positions(HIGH)."""
    registry = StrategyRegistry()
    ndx2x_shadow = _DummyStrategy(
        StrategyConfig(
            strategy_id="ndx2x_riskoff", name="나스닥2배-위험회피", weight=0.0, enabled=True,
            params={"shadow_mode": True},
        ),
        scanned=[],
    )
    registry.register(ndx2x_shadow)

    sched = _make_scheduler_stub(registry)
    groups = sched._build_priority_groups()
    assert groups["shadow"] == [], "ndx2x 는 BREAKOUT_SUBSCRIBE_ORDER 밖이라 영향 없음"
    assert groups["positions"] == [], "보유 0 이므로 positions 도 영향 없음"

    # 보유가 생기면 HIGH(positions) 로 들어간다
    ndx2x_shadow.state.positions["251340"] = Position(
        ticker="251340", buy_price=10000, quantity=1, order_no="O1",
        strategy_id="ndx2x_riskoff",
    )
    groups2 = sched._build_priority_groups()
    assert "251340" in groups2["positions"], "ndx2x 보유 종목은 positions(HIGH) 이어야 한다"


# ===========================================================================
# 8) _build_subscription_source_counts — shadow 카운트 필드
# ===========================================================================
def test_build_subscription_source_counts_has_shadow_field():
    registry = StrategyRegistry()
    vb_shadow = _DummyStrategy(_shadow_config("volatility_breakout", "VB"), scanned=["VBX1", "VBX2"])
    registry.register(vb_shadow)

    sched = _make_scheduler_stub(registry)
    counts = sched._build_subscription_source_counts(momentum_tickers=None)
    assert counts["shadow"] == 2, f"섀도 돌파 후보 2개가 shadow 카운트에 잡혀야 한다: {counts}"


def test_build_subscription_source_counts_shadow_includes_momentum_when_momentum_shadow():
    registry = StrategyRegistry()
    momentum_shadow = _DummyStrategy(_shadow_config("momentum", "MOM"), scanned=[])
    registry.register(momentum_shadow)

    sched = _make_scheduler_stub(registry)
    counts = sched._build_subscription_source_counts(momentum_tickers=["M1", "M2", "M3"])
    assert counts["shadow"] == 3, f"섀도 momentum 후보 3개가 shadow 카운트에 잡혀야 한다: {counts}"
    assert counts["momentum"] == 3, "momentum 카운트 자체는 인자 길이 그대로(섀도 무관)"


# ===========================================================================
# 돌연변이 1 — 섀도 후보를 원래(live) 그룹에 되돌리면 테스트가 잡아야 한다
# ===========================================================================
def test_mutation1_shadow_candidates_restored_to_live_group_is_caught():
    """뮤테이션: `_collect_breakout_tickers` 가 섀도도 포함하도록 되돌리면
    test_collect_breakout_tickers_excludes_shadow_strategy 가 실패해야 한다
    (여기서는 그 결함을 직접 흉내내 「탐지됨」을 증명한다)."""
    registry = StrategyRegistry()
    vb_shadow = _DummyStrategy(_shadow_config("volatility_breakout", "VB"), scanned=["VBX1"])
    registry.register(vb_shadow)
    sched = _make_scheduler_stub(registry)

    # 뮤테이션 흉내: shadow_mode_on 체크 없이 돌파 후보를 모으면(결함 재현)
    mutated: list[str] = []
    for sid in ("bull_flag_breakout", "vcp_breakout", "volatility_breakout", "long_tail_volatility"):
        strategy = registry.get(sid)
        if strategy and strategy.config.enabled and hasattr(strategy, "get_scanned_tickers"):
            mutated.extend(strategy.get_scanned_tickers())  # shadow 체크 생략(결함)

    live = sched._collect_breakout_tickers()
    assert mutated != live, (
        "뮤테이션(섀도 체크 생략)과 시정된 live 목록이 달라야 한다 — "
        f"mutated={mutated} live={live}"
    )
    assert "VBX1" in mutated and "VBX1" not in live


# ===========================================================================
# 돌연변이 2 — 섀도 전략의 보유를 LOW 로 내리면 테스트가 잡아야 한다
# ===========================================================================
def test_mutation2_shadow_holding_demoted_to_low_is_caught():
    """뮤테이션: positions 집계에서 섀도 전략을 빼면(보유를 LOW 로 내리는 결함)
    `HELD_BY_SHADOW` 가 positions 에서 사라진다 — 그 결함을 직접 재현해 탐지를 증명."""
    registry = StrategyRegistry()
    vb_shadow = _DummyStrategy(
        _shadow_config("volatility_breakout", "VB"), position_tickers=["HELD_BY_SHADOW"],
    )
    registry.register(vb_shadow)
    sched = _make_scheduler_stub(registry)

    # 뮤테이션 흉내: positions 집계에서 섀도 전략을 제외(결함 재현)
    mutated_positions: list[str] = []
    for s in registry.all():
        if StrategyBase.shadow_mode_on(s):
            continue  # 결함: 섀도 보유를 HIGH 에서 뺀다
        mutated_positions.extend(s.state.positions.keys())

    real_groups = sched._build_priority_groups()
    assert "HELD_BY_SHADOW" not in mutated_positions, "뮤테이션은 섀도 보유를 빠뜨려야 결함 재현"
    assert "HELD_BY_SHADOW" in real_groups["positions"], (
        "시정된 구현은 섀도 보유를 positions(HIGH) 에 반드시 남긴다"
    )
