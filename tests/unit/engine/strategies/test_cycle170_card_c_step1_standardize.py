"""사이클 170 카드 C — 5 전략 funnel step1 의미 표준화 + SAFETY 가드.

결함: step1 의미 불일치 — VB/LTV `survived=[]` placeholder / BFB step_conditions
구버전 문구 / donchian 오라벨 (카드 A 에서 union 노출로 시정 완료).

채택안: step1 = "원천 유니버스 후보 (필터 전)" 의미 통일.
- VB/LTV: `survived=[]` → `_scan_universe` 보관 `_universe_candidate_tickers` 실제 후보.
- BFB: step_conditions 구버전 "KRX 등락률 순위" → 실제 소스 (list_by_filter) 정합.
- VCP: list_by_filter union → step1 후보 노출 (VB/LTV 패턴 통일).

회귀 가드 (C 5 + SAFETY 2):
- G-C-1: 5 전략 prepare 후 _funnel_steps step_no 전 단계 (1..N) 포함.
- G-C-2: step1 survived placeholder 아님 (universe>0 시 비어있지 않음).
- G-C-3 (SAFETY): 5 전략 check_exit_signal/check_buy_signal funnel hook 0건.
- G-C-4 (SAFETY): risk/order/realtime/auth/scanner import 0건 (funnel 영역).
- G-C-5 (AST): VB/LTV step1 survived 가 [] 리터럴 placeholder 아님.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.engine.strategy_base import StrategyConfig


_STRATEGY_MODULES = {
    "donchian_swing": "DonchianSwingStrategy",
    "bull_flag_breakout": "BullFlagBreakoutStrategy",
    "vcp_breakout": "VCPBreakoutStrategy",
    "volatility_breakout": "VolatilityBreakoutStrategy",
    "long_tail_volatility": "LongTailVolatilityStrategy",
}


def _import_class(mod_name, cls_name):
    import importlib

    mod = importlib.import_module(f"src.engine.strategies.{mod_name}")
    return getattr(mod, cls_name)


# ------------------------------------------------------------------
# G-C-2 / G-C-1 — VB step1 = 실제 후보 (placeholder 아님)
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_c_2_vb_step1_not_empty_placeholder(monkeypatch):
    """VB prepare 후 step1 survived 가 실제 후보 리스트 (placeholder [] 아님)."""
    from src.engine.strategies import volatility_breakout as vb_mod
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    strat = VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="vb")
    )

    cand = ["005930", "000660", "035720"]

    async def _fake_scan(self):
        self._universe_candidate_tickers = list(cand)
        self._scan_stats["universe_candidates"] = len(cand)
        self._scan_stats["universe_filtered"] = len(cand)
        return list(cand)

    monkeypatch.setattr(VolatilityBreakoutStrategy, "_scan_universe", _fake_scan)

    async def _empty_block(self, tickers):
        return tickers, []

    monkeypatch.setattr(
        VolatilityBreakoutStrategy, "_apply_master_block_filter_in_prepare", _empty_block
    )

    import src.api.condition as _cond

    async def _empty_candles(ticker, days=0):
        return []

    monkeypatch.setattr(_cond, "fetch_daily_candles", _empty_candles)

    await strat.prepare()

    step1 = next(s for s in strat._funnel_steps if s["step_no"] == 1)
    assert step1["survived_count"] == 3, (
        f"VB step1 placeholder 잔존 — count={step1['survived_count']} (실제 후보 미반영)"
    )


@pytest.mark.asyncio
async def test_g_c_2_ltv_step1_not_empty_placeholder(monkeypatch):
    """LTV prepare 후 step1 survived 가 실제 후보 리스트 (placeholder [] 아님)."""
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy

    strat = LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="ltv")
    )

    cand = ["005930", "000660"]

    async def _fake_scan(self):
        self._universe_candidate_tickers = list(cand)
        self._scan_stats["universe_candidates"] = len(cand)
        self._scan_stats["universe_filtered"] = len(cand)
        return list(cand)

    monkeypatch.setattr(LongTailVolatilityStrategy, "_scan_universe", _fake_scan)

    async def _empty_block(self, tickers):
        return tickers, []

    monkeypatch.setattr(
        LongTailVolatilityStrategy, "_apply_master_block_filter_in_prepare", _empty_block
    )

    import src.api.condition as _cond

    async def _empty_candles(ticker, days=0):
        return []

    monkeypatch.setattr(_cond, "fetch_daily_candles", _empty_candles)

    await strat.prepare()

    step1 = next(s for s in strat._funnel_steps if s["step_no"] == 1)
    assert step1["survived_count"] == 2, (
        f"LTV step1 placeholder 잔존 — count={step1['survived_count']}"
    )


# ------------------------------------------------------------------
# G-C-5 (AST) — VB/LTV step1 survived 가 [] 리터럴 placeholder 아님
# ------------------------------------------------------------------
@pytest.mark.parametrize(
    "mod_name,stage_const",
    [("volatility_breakout", "VB_FUNNEL_STAGES"),
     ("long_tail_volatility", "LTV_FUNNEL_STAGES")],
)
def test_g_c_5_ast_vb_ltv_step1_survived_not_empty_literal(mod_name, stage_const):
    """VB/LTV step1 (STAGES[0]) `_record_funnel_pipeline_step` survived 가 [] 리터럴 아님."""
    import importlib

    mod = importlib.import_module(f"src.engine.strategies.{mod_name}")
    src = Path(inspect.getfile(mod)).read_text(encoding="utf-8")
    tree = ast.parse(src)

    step1_calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_record_funnel_pipeline_step"
        ):
            # 첫 positional arg 가 STAGES[0] subscript 인지 확인
            if node.args:
                a0 = node.args[0]
                if (
                    isinstance(a0, ast.Subscript)
                    and isinstance(a0.value, ast.Name)
                    and a0.value.id == stage_const
                    and isinstance(a0.slice, ast.Constant)
                    and a0.slice.value == 0
                ):
                    step1_calls.append(node)

    assert step1_calls, f"{mod_name}: STAGES[0] _record_funnel_pipeline_step 호출 부재"
    for call in step1_calls:
        survived_kw = next(
            (kw for kw in call.keywords if kw.arg == "survived"), None
        )
        assert survived_kw is not None, f"{mod_name} step1 survived kwarg 부재"
        # survived 가 빈 리스트 리터럴 [] 이면 placeholder 잔존 (결함)
        is_empty_literal = (
            isinstance(survived_kw.value, ast.List) and not survived_kw.value.elts
        )
        assert not is_empty_literal, (
            f"{mod_name}: step1 survived=[] placeholder 잔존 (실제 후보 미반영)"
        )


# ------------------------------------------------------------------
# G-C-1 — 5 전략 FUNNEL_STAGES step_no 연속 (1..N)
# ------------------------------------------------------------------
@pytest.mark.parametrize(
    "mod_name,stage_const",
    [("donchian_swing", "FUNNEL_STAGES"),
     ("bull_flag_breakout", "FUNNEL_STAGES"),
     ("vcp_breakout", "FUNNEL_STAGES"),
     ("volatility_breakout", "VB_FUNNEL_STAGES"),
     ("long_tail_volatility", "LTV_FUNNEL_STAGES")],
)
def test_g_c_1_funnel_stages_step_no_continuous(mod_name, stage_const):
    """5 전략 STAGES step_no 1..N 연속 (0-시드 대상 정합)."""
    import importlib

    mod = importlib.import_module(f"src.engine.strategies.{mod_name}")
    stages = getattr(mod, stage_const)
    step_nos = [st.step_no for st in stages]
    assert step_nos == list(range(1, len(stages) + 1)), (
        f"{mod_name} {stage_const} step_no 불연속 — {step_nos}"
    )


# ------------------------------------------------------------------
# G-C-3 (SAFETY) — check_exit_signal / check_buy_signal funnel hook 0건
# ------------------------------------------------------------------
@pytest.mark.parametrize("mod_name,cls_name", _STRATEGY_MODULES.items())
def test_g_c_3_safety_no_funnel_hook_in_exit_buy(mod_name, cls_name):
    """5 전략 check_exit_signal/check_buy_signal 내부 funnel hook 호출 0건 (사이클 143 답습)."""
    import importlib

    mod = importlib.import_module(f"src.engine.strategies.{mod_name}")
    src = Path(inspect.getfile(mod)).read_text(encoding="utf-8")
    tree = ast.parse(src)

    funnel_methods = {"_record_funnel_step", "_record_funnel_pipeline_step", "_reset_funnel_steps"}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
            "check_exit_signal", "check_buy_signal",
        ):
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr in funnel_methods
                ):
                    pytest.fail(
                        f"{mod_name}.{node.name} 내부 funnel hook {inner.func.attr} 호출 발견 "
                        f"(매도/매수 hot path funnel 적재 금지 — 사이클 143 SAFETY)"
                    )


# ------------------------------------------------------------------
# G-C-4 (SAFETY) — risk/order/realtime/auth/scanner hot path import 0건
# ------------------------------------------------------------------
@pytest.mark.parametrize("mod_name,cls_name", _STRATEGY_MODULES.items())
def test_g_c_4_safety_no_hot_path_module_level_import(mod_name, cls_name):
    """5 전략 파일 모듈-레벨 매매 hot path import 0건 (AST 정적 가드)."""
    import importlib

    mod = importlib.import_module(f"src.engine.strategies.{mod_name}")
    src = Path(inspect.getfile(mod)).read_text(encoding="utf-8")
    tree = ast.parse(src)

    forbidden = {
        "src.engine.order_engine",
        "src.engine.risk",
        "src.realtime.websocket",
        "src.realtime.websocket_pool",
        "src.auth.token",
    }
    # 모듈-레벨 (함수 밖) import 만 검사 — scanner 일부 헬퍼 lazy import 는 허용 (사이클 157)
    bad = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in forbidden:
            bad.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden:
                    bad.append(alias.name)

    assert not bad, f"{mod_name}: 모듈-레벨 hot path import 발견 {bad}"
