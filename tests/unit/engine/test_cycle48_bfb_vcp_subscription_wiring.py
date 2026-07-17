"""사이클 48 (2026-05-27) — BFB/VCP WebSocket 구독 배선 편입 회귀 가드 (PR #15 P1 후속).

배경 (운영 DB + 코드 확정, 재조사 불필요):
- BFB(bull_flag_breakout)/VCP(vcp_breakout) 매수 신호는 donchian 과 달리 폴링 루프가
  없고 `risk.on_tick`(WebSocket tick) 으로만 평가된다.
- 후보가 WebSocket 구독에 들어가는 유일한 경로 `scheduler._collect_breakout_tickers()`
  가 기존에는 ("volatility_breakout","long_tail_volatility") 두 전략만 순회 →
  BFB/VCP 후보 미구독 → tick 미수신 → on_tick 매수 평가 영영 안 됨 →
  유니버스 시간무관화 + 임계 완화를 해도 BFB/VCP 0건 지속.
- `_collect_breakout_tickers()` 는 (a) `_scan_loop` extra, (b) `_collect_presubscribe_tickers`
  (07:55 사전구독), (c) `_build_priority_groups()["breakout"]` — 세 구독 경로 전부의 소스.

요구 행위:
- `_collect_breakout_tickers()` 는 VB/LTV/BFB/VCP 4 전략의 `get_scanned_tickers()` 를 합산한다.
- `_build_priority_groups()["breakout"]` 도 4 전략 후보를 포함한다 (위임이라 자동 전파).
- `_universe_excluded_today` 필터는 BFB/VCP 후보에도 동일하게 적용된다.
- `_build_subscription_source_counts()` 는 bfb/vcp 후보 개수를 별도 키로 노출한다.

안전 제약 (본 변경의 비목표):
- BFB/VCP 후보는 VB/LTV 와 동일하게 breakout 그룹(LOW + bypass_limit=False)으로 유입 —
  HIGH(positions/next_day_clear, bypass_limit=True) 승격이 아니다. 본 파일은 후보 수집
  배선만 검증하고, HIGH 보장 무회귀는 구독 우선순위/2-pass 테스트가 별도 담당한다.
"""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 더블: scanned_tickers + positions 주입 가능한 전략 스텁
# (test_scheduler_priority_groups.py 의 _DummyStrategy 패턴 재사용)
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


def _make_four_breakout_registry() -> StrategyRegistry:
    """VB/LTV/BFB/VCP 4 전략 각각 고유 후보 1종 보유."""
    registry = StrategyRegistry()
    registry.register(_DummyStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.25, enabled=True),
        scanned=["VB1"],
    ))
    registry.register(_DummyStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="LTV", weight=0.25, enabled=True),
        scanned=["LTV1"],
    ))
    registry.register(_DummyStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.25, enabled=True),
        scanned=["BFB1"],
    ))
    registry.register(_DummyStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.25, enabled=True),
        scanned=["VCP1"],
    ))
    return registry


def _make_scheduler_stub(
    registry: StrategyRegistry,
    *,
    pending: set[tuple[str, str]] | None = None,
    excluded: set[str] | None = None,
):
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = registry
    sched._pending_next_day_clear = set(pending or set())
    sched._universe_excluded_today = set(excluded or set())
    return sched


# ---------------------------------------------------------------------------
# R1: _collect_breakout_tickers 가 BFB/VCP 후보를 포함
# ---------------------------------------------------------------------------
def test_collect_breakout_tickers_includes_bfb_vcp():
    registry = _make_four_breakout_registry()
    sched = _make_scheduler_stub(registry)

    result = sched._collect_breakout_tickers()

    assert "VB1" in result and "LTV1" in result, f"VB/LTV 후보 보존. result={result}"
    assert "BFB1" in result, (
        f"BFB 후보가 _collect_breakout_tickers 에 미포함 → WebSocket 미구독 → on_tick "
        f"매수 평가 불가 (0건 결함). result={result}"
    )
    assert "VCP1" in result, (
        f"VCP 후보가 _collect_breakout_tickers 에 미포함 → 0건 결함. result={result}"
    )


# ---------------------------------------------------------------------------
# R2: _build_priority_groups()["breakout"] 도 BFB/VCP 포함 (위임 자동 전파)
# ---------------------------------------------------------------------------
def test_build_priority_groups_breakout_includes_bfb_vcp():
    registry = _make_four_breakout_registry()
    sched = _make_scheduler_stub(registry)

    groups = sched._build_priority_groups(momentum_tickers=None)

    assert set(groups["breakout"]) == {"VB1", "LTV1", "BFB1", "VCP1"}, (
        f"breakout 그룹은 4 돌파 전략 후보 합집합이어야 함. breakout={groups['breakout']}"
    )
    # BFB/VCP 가 HIGH 그룹(positions/next_day_clear)으로 잘못 승격되지 않음 (구독 우선순위 불변)
    assert "BFB1" not in groups["positions"]
    assert "VCP1" not in groups["positions"]
    assert "BFB1" not in groups["next_day_clear"]
    assert "VCP1" not in groups["next_day_clear"]


# ---------------------------------------------------------------------------
# R3: universe_excluded 필터가 BFB/VCP 후보에도 적용
# ---------------------------------------------------------------------------
def test_collect_breakout_tickers_excludes_bfb_vcp_universe_excluded():
    registry = _make_four_breakout_registry()
    sched = _make_scheduler_stub(registry, excluded={"BFB1"})

    result = sched._collect_breakout_tickers()

    assert "BFB1" not in result, (
        f"_universe_excluded_today 종목은 BFB 후보여도 제외되어야 함. result={result}"
    )
    # 나머지는 보존
    assert "VB1" in result
    assert "LTV1" in result
    assert "VCP1" in result


# ---------------------------------------------------------------------------
# R4: _build_subscription_source_counts 가 bfb/vcp 카운트 키 노출 (운영 가시성)
# ---------------------------------------------------------------------------
def test_subscription_source_counts_has_bfb_vcp_keys():
    registry = _make_four_breakout_registry()
    sched = _make_scheduler_stub(registry)

    counts = sched._build_subscription_source_counts(momentum_tickers=None)

    assert "bfb" in counts and "vcp" in counts, (
        f"source_counts 에 bfb/vcp 키 필요 (구독 완료 로그 가시성). keys={list(counts.keys())}"
    )
    assert counts["bfb"] == 1, f"BFB 후보 1종. counts={counts}"
    assert counts["vcp"] == 1, f"VCP 후보 1종. counts={counts}"
    # 기존 키 보존
    assert counts["vb"] == 1 and counts["ltv"] == 1
