"""사이클 170 카드 B — funnel atomic 일관성 (0-시드 + in-place upsert).

결함: `_record_funnel_step` append-only + `_reset_funnel_steps` 빈 리스트 → 조기반환/
다중 실행 시 실패 run 이 step1~3 만 0 으로 덮고 step4~9 는 이전 성공 run stale(7) 잔존.
→ donchian 6/19 step1=0/step4=7 논리 불가능 패턴.

채택안: `_reset_funnel_steps(stages)` 0-시드 (각 step_no survived=[] pre-populate)
+ `_record_funnel_step` 같은 step_no 존재 시 in-place 교체 (없으면 append).

회귀 가드 (B 6 케이스):
- G-B-1: `_reset_funnel_steps(STAGES)` 후 길이 == len(STAGES), survived_count 전부 0.
- G-B-2: 같은 step_no 2회 → 길이 불변 + 최신 값 (append-only 회귀 차단).
- G-B-3 (HIGH): donchian universe=0 조기반환 시 step1~9 전부 존재 + step4~9 count=0.
- G-B-4: auto_capture step_no 누락 0 (0-시드 step 도 UPSERT).
- G-B-5: `_reset_funnel_steps()` (인자 None) 빈 리스트 회귀 보존.
- G-B-6 (AST): 5 전략 prepare() `_reset_funnel_steps` 호출 모두 STAGES 인자 전달.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.engine.strategy_base import (
    FunnelStage,
    StrategyBase,
    StrategyConfig,
)


# ------------------------------------------------------------------
# 최소 StrategyBase 구현 (추상 메서드 stub)
# ------------------------------------------------------------------
class _DummyStrategy(StrategyBase):
    async def prepare(self) -> None:  # pragma: no cover
        pass

    def check_buy_signal(self, ticker, current_price, open_price):  # pragma: no cover
        from src.engine.strategy_base import Signal
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):  # pragma: no cover
        from src.engine.strategy_base import Signal
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):  # pragma: no cover
        return 0


_STAGES = (
    FunnelStage(1, "단계1"),
    FunnelStage(2, "단계2"),
    FunnelStage(3, "단계3"),
    FunnelStage(4, "단계4"),
)


def _make_strategy() -> _DummyStrategy:
    return _DummyStrategy(StrategyConfig(strategy_id="dummy", name="dummy"))


# ------------------------------------------------------------------
# G-B-1 — 0-시드: stages 의 모든 step_no pre-populate (survived_count=0)
# ------------------------------------------------------------------
def test_g_b_1_reset_seeds_all_stages():
    """`_reset_funnel_steps(STAGES)` 후 funnel_steps 길이 == len(STAGES), 전부 0-시드."""
    strat = _make_strategy()
    strat._reset_funnel_steps(_STAGES)

    assert len(strat._funnel_steps) == len(_STAGES), (
        f"0-시드 길이 불일치 — 실제={len(strat._funnel_steps)} 기대={len(_STAGES)}"
    )
    step_nos = sorted(s["step_no"] for s in strat._funnel_steps)
    assert step_nos == [1, 2, 3, 4]
    for step in strat._funnel_steps:
        assert step["survived_count"] == 0, f"step {step['step_no']} 0-시드 아님"
        assert step["survived"] == []


# ------------------------------------------------------------------
# G-B-2 — in-place upsert: 같은 step_no 2회 → 길이 불변 + 최신값
# ------------------------------------------------------------------
def test_g_b_2_record_same_step_in_place_replace():
    """같은 step_no 2회 `_record_funnel_step` → 길이 불변 + 최신 survived 반영."""
    strat = _make_strategy()
    strat._reset_funnel_steps(_STAGES)
    base_len = len(strat._funnel_steps)

    strat._record_funnel_step(2, "단계2", survived=["005930", "000660"])
    assert len(strat._funnel_steps) == base_len, "append 발생 (회귀)"
    step2 = next(s for s in strat._funnel_steps if s["step_no"] == 2)
    assert step2["survived_count"] == 2

    # 같은 step_no 재기록 → 교체 (누적 금지)
    strat._record_funnel_step(2, "단계2", survived=["005930"])
    assert len(strat._funnel_steps) == base_len, "동일 step_no 재기록 시 append 발생 (회귀)"
    step2 = next(s for s in strat._funnel_steps if s["step_no"] == 2)
    assert step2["survived_count"] == 1, "최신값 미반영"


def test_g_b_2b_record_new_step_appends():
    """0-시드에 없는 step_no 기록 시 append (in-place 대상 부재)."""
    strat = _make_strategy()
    strat._reset_funnel_steps(_STAGES)
    base_len = len(strat._funnel_steps)

    strat._record_funnel_step(99, "최종", survived=["005930"])
    assert len(strat._funnel_steps) == base_len + 1
    step99 = next(s for s in strat._funnel_steps if s["step_no"] == 99)
    assert step99["survived_count"] == 1


# ------------------------------------------------------------------
# G-B-3 (HIGH) — donchian universe=0 조기반환 시 step1~9 전부 존재 + step4~9=0
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_b_3_donchian_early_return_seeds_all_steps(monkeypatch):
    """donchian universe=0 조기반환 시 step1~9 전부 존재 + step4~9 survived_count=0."""
    from src.engine.strategies import donchian_swing
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy, FUNNEL_STAGES

    strat = DonchianSwingStrategy(StrategyConfig(strategy_id="donchian_swing", name="dc"))

    # _scan_universe 가 빈 list 반환 (universe=0) → prepare 조기반환 경로
    async def _empty_scan(self):
        self._scan_stats["universe_candidates"] = 0
        self._scan_stats["universe_filtered"] = 0
        return []

    monkeypatch.setattr(DonchianSwingStrategy, "_scan_universe", _empty_scan)

    # master block filter 도 빈 통과 (조기반환 전 단계)
    async def _empty_block(self, tickers):
        return [], []

    monkeypatch.setattr(
        DonchianSwingStrategy, "_apply_master_block_filter_in_prepare", _empty_block
    )

    # retry 루프 asyncio.sleep(30) × 3 회피 (즉시 통과). donchian prepare 는
    # 함수 내부에서 `import asyncio` 하므로 모듈 sleep 직접 패치.
    import asyncio as _aio

    async def _no_sleep(_secs):
        return None

    monkeypatch.setattr(_aio, "sleep", _no_sleep)

    await strat.prepare()

    step_nos = sorted(s["step_no"] for s in strat._funnel_steps)
    expected = [st.step_no for st in FUNNEL_STAGES]
    assert step_nos == sorted(expected), (
        f"조기반환 시 step_no 누락 — 실제={step_nos} 기대={sorted(expected)} "
        f"(stale step4=7 패턴 차단 의무)"
    )
    # step4~9 (조기반환 미도달 단계) survived_count == 0
    for step in strat._funnel_steps:
        if step["step_no"] >= 4:
            assert step["survived_count"] == 0, (
                f"조기반환 단계 step{step['step_no']} stale 값 잔존 — count={step['survived_count']}"
            )


# ------------------------------------------------------------------
# G-B-4 — auto_capture 가 0-시드 step 도 step_no 누락 없이 처리
# ------------------------------------------------------------------
def test_g_b_4_auto_capture_no_step_no_gap():
    """0-시드된 _funnel_steps 의 step_no 집합이 1..N 연속 (auto_capture UPSERT 대상)."""
    strat = _make_strategy()
    strat._reset_funnel_steps(_STAGES)
    # 일부만 실제 기록 (조기반환 시뮬레이션)
    strat._record_funnel_step(1, "단계1", survived=["005930", "000660"])
    strat._record_funnel_step(2, "단계2", survived=["005930"])

    step_nos = sorted(s["step_no"] for s in strat._funnel_steps)
    assert step_nos == [1, 2, 3, 4], "auto_capture UPSERT 대상 step_no 누락"
    # step3/4 는 여전히 0-시드 (UPSERT 시 0 으로 기록되어 stale 차단)
    step3 = next(s for s in strat._funnel_steps if s["step_no"] == 3)
    step4 = next(s for s in strat._funnel_steps if s["step_no"] == 4)
    assert step3["survived_count"] == 0
    assert step4["survived_count"] == 0


# ------------------------------------------------------------------
# G-B-5 — 회귀 보존: 인자 None 시 빈 리스트
# ------------------------------------------------------------------
def test_g_b_5_reset_none_clears():
    """`_reset_funnel_steps()` (인자 None) → 빈 리스트 회귀 보존."""
    strat = _make_strategy()
    strat._record_funnel_step(1, "x", survived=["005930"])
    assert len(strat._funnel_steps) == 1
    strat._reset_funnel_steps()
    assert strat._funnel_steps == [], "인자 None 시 빈 리스트 회귀 보존 위반"


# ------------------------------------------------------------------
# G-B-6 (AST) — 5 전략 prepare() _reset_funnel_steps 호출 STAGES 인자 의무
# ------------------------------------------------------------------
_STRATEGY_STAGE_CONST = {
    "donchian_swing": "FUNNEL_STAGES",
    "bull_flag_breakout": "FUNNEL_STAGES",
    "vcp_breakout": "FUNNEL_STAGES",
    "volatility_breakout": "VB_FUNNEL_STAGES",
    "long_tail_volatility": "LTV_FUNNEL_STAGES",
}


@pytest.mark.parametrize("mod_name,stage_const", _STRATEGY_STAGE_CONST.items())
def test_g_b_6_ast_reset_funnel_steps_has_stages_arg(mod_name, stage_const):
    """5 전략 prepare() 의 `_reset_funnel_steps` 호출이 모두 STAGES 상수 인자 전달."""
    import importlib

    mod = importlib.import_module(f"src.engine.strategies.{mod_name}")
    src = Path(inspect.getfile(mod)).read_text(encoding="utf-8")
    tree = ast.parse(src)

    reset_calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_reset_funnel_steps"
        ):
            reset_calls.append(node)

    assert reset_calls, f"{mod_name}: _reset_funnel_steps 호출 0건"
    for call in reset_calls:
        assert call.args, (
            f"{mod_name}: _reset_funnel_steps() 인자 없는 호출 발견 "
            f"(0-시드 미적용 — {stage_const} 인자 의무)"
        )
        arg = call.args[0]
        assert isinstance(arg, ast.Name) and arg.id == stage_const, (
            f"{mod_name}: _reset_funnel_steps 인자가 {stage_const} 아님 "
            f"(실제={ast.dump(arg)})"
        )
