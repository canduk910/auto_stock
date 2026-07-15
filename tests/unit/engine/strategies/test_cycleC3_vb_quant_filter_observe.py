"""사이클 C3 (2026-07-15) — VB 퀀트 재무 관찰 훅 (배제 0) 회귀 가드 (Red).

산출물 (c) `_apply_quant_filter_in_prepare()` 관찰 훅. `quant_filter_enabled=False`(기본)
상태에서 스코어 계산·funnel 노출만, **어떤 종목도 배제 안 함** (관찰 전용 Phase 1).

Red 가드 매트릭스:
- OBSERVE-1 (HIGH, G-2): quant_filter_enabled=False → 전체 통과 (배제 0)
- OBSERVE-2: 스코어 계산 (get_financial_series + compute_f_score_7 + compute_magic_formula)
- OBSERVE-3: funnel step (step_no=7) 스코어 기록
- FAILOPEN-1: series 부족(1기 이하) → f_score=None → 통과
- FAILOPEN-2: get_financial_series 예외 graceful → 통과
- PROTECT-1: 보유 종목 무조건 통과 (사이클 32 R4)
- PARAM-1 (AST): DEFAULT_PARAMS quant_filter_enabled=False/quant_min_f_score=0/quant_max_mf_rank=0
- FUNNEL-1: VB_FUNNEL_STAGES 7단계 (step_no=7 "퀀트 재무 게이트(관찰)")
- HOOK-ORDER (AST): _apply_quant_filter_in_prepare 가 master_block 다음 호출
- G-1 (HIGH SAFETY, AST): check_buy_signal / check_exit_signal 본체 diff 0
- SAFETY-2 (AST): 훅 영역 check_exit_signal 호출 0 + risk/order_engine import 0
- PARAM-RANGES (AST): recommendation_engine.py PARAM_RANGES 에 quant 키 미편입

매매 안전성: VB prepare = 매수 진입 전 (사이클 38). check_exit_signal 호출 0 (G-1).
freeze_time 미사용 — get_financial_series mock (사이클 187 hang 교훈).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[4]
_VB_SRC = _REPO_ROOT / "src" / "engine" / "strategies" / "volatility_breakout.py"
_RECO_SRC = _REPO_ROOT / "src" / "engine" / "recommendation_engine.py"


def _make_strategy(**param_overrides):
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    params = {
        "min_market_cap": 100_000_000_000,
        "min_trade_amount": 20_000_000_000,
        "max_scan_stocks": 100,
    }
    params.update(param_overrides)
    config = StrategyConfig(
        strategy_id="volatility_breakout",
        name="변동성돌파",
        params=params,
    )
    return VolatilityBreakoutStrategy(config)


def _fin_series(ticker: str, n: int = 2) -> list[dict]:
    """get_financial_series 반환 (stac_yymm DESC, n 기)."""
    out = []
    for i in range(n):
        out.append({
            "ticker": ticker,
            "stac_yymm": f"2024{12 - i:02d}31"[:8],
            "div_cls": "0",
            "cptl_ntin_rate": 5.0 - i,
            "lblt_rate": 40.0 + i,
            "crnt_rate": 150.0,
            "sale_totl_rate": 20.0,
            "sale_account": 1000.0,
            "total_aset": 5000.0,
            "cpfn": 500.0,
            "bsop_prti": 100.0,
            "ev_ebitda": 8.0,
            "cras": 2000.0,
            "flow_lblt": 800.0,
            "fxas": 3000.0,
        })
    return out


# ---------------------------------------------------------------------------
# OBSERVE-1 (HIGH, G-2) — quant_filter_enabled=False → 전체 통과 (배제 0)
# ---------------------------------------------------------------------------
class TestObserveModeNoExclusion:
    """G-2: 비활성(관찰) 모드에서 어떤 종목도 배제 안 함."""

    @pytest.mark.asyncio
    async def test_observe_mode_passes_all(self):
        strategy = _make_strategy(quant_filter_enabled=False)
        hook = getattr(strategy, "_apply_quant_filter_in_prepare", None)
        assert hook is not None, (
            "VolatilityBreakoutStrategy._apply_quant_filter_in_prepare 미구현 — C3 (c) 산출물."
        )

        tickers = ["005930", "000660", "035720"]

        with patch("src.db.stock_master_financial.get_financial_series",
                   new=AsyncMock(side_effect=lambda t, **kw: _fin_series(t))), \
             patch("src.db.stock_master.get", new=AsyncMock(return_value=None)), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()):
            result = await hook(tickers)

        assert set(result) == set(tickers), (
            f"관찰 모드(enabled=False)인데 배제 발생 — 입력 {tickers} != 출력 {result}. "
            "배제 0 불변식 위반 (G-2)."
        )
        assert len(result) == len(tickers)


# ---------------------------------------------------------------------------
# OBSERVE-2 — 스코어 계산 (get_financial_series + compute_f_score_7 + magic_formula)
# ---------------------------------------------------------------------------
class TestObserveScoreComputed:
    @pytest.mark.asyncio
    async def test_scores_computed_in_observe_mode(self):
        strategy = _make_strategy(quant_filter_enabled=False)
        hook = getattr(strategy, "_apply_quant_filter_in_prepare", None)
        assert hook is not None

        gfs_mock = AsyncMock(side_effect=lambda t, **kw: _fin_series(t))
        f_mock = MagicMock(return_value=4)
        mf_mock = MagicMock(return_value={
            "005930": {"mf_rank": 3, "ey": 0.1, "roc": 0.2, "ey_rank": 1, "roc_rank": 2},
            "000660": {"mf_rank": 5, "ey": 0.05, "roc": 0.1, "ey_rank": 3, "roc_rank": 2},
        })

        with patch("src.db.stock_master_financial.get_financial_series", new=gfs_mock), \
             patch("src.engine.quant_score.compute_f_score_7", new=f_mock), \
             patch("src.engine.quant_score.compute_magic_formula", new=mf_mock), \
             patch("src.db.stock_master.get", new=AsyncMock(return_value=None)), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()):
            await hook(["005930", "000660"])

        assert gfs_mock.await_count >= 2, (
            "get_financial_series 미호출 — 스코어 계산 안 됨."
        )
        assert f_mock.call_count >= 1, "compute_f_score_7 미호출."
        assert mf_mock.call_count >= 1, "compute_magic_formula 미호출 (유니버스 상대 순위)."


# ---------------------------------------------------------------------------
# OBSERVE-3 — funnel step (step_no=7) 스코어 기록
# ---------------------------------------------------------------------------
class TestObserveFunnelRecorded:
    @pytest.mark.asyncio
    async def test_funnel_step7_recorded(self):
        strategy = _make_strategy(quant_filter_enabled=False)
        hook = getattr(strategy, "_apply_quant_filter_in_prepare", None)
        assert hook is not None

        rec_mock = MagicMock()

        with patch("src.db.stock_master_financial.get_financial_series",
                   new=AsyncMock(side_effect=lambda t, **kw: _fin_series(t))), \
             patch("src.db.stock_master.get", new=AsyncMock(return_value=None)), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()), \
             patch.object(strategy, "_record_funnel_pipeline_step", rec_mock):
            await hook(["005930"])

        assert rec_mock.call_count >= 1, (
            "_apply_quant_filter_in_prepare 가 funnel step (step_no=7) 미기록."
        )


# ---------------------------------------------------------------------------
# FAILOPEN-1 — series 부족(1기 이하) → f_score=None → 통과
# ---------------------------------------------------------------------------
class TestFailOpenInsufficientSeries:
    @pytest.mark.asyncio
    async def test_insufficient_series_passes(self):
        strategy = _make_strategy(quant_filter_enabled=False)
        hook = getattr(strategy, "_apply_quant_filter_in_prepare", None)
        assert hook is not None

        # 1기만 반환 (2기 부족 → f_score=None fail-open)
        with patch("src.db.stock_master_financial.get_financial_series",
                   new=AsyncMock(side_effect=lambda t, **kw: _fin_series(t, n=1))), \
             patch("src.db.stock_master.get", new=AsyncMock(return_value=None)), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()):
            result = await hook(["005930", "000660"])

        assert set(result) == {"005930", "000660"}, (
            "재무 결측(2기 부족)인데 배제 발생 — fail-open 통과 위반."
        )


# ---------------------------------------------------------------------------
# FAILOPEN-2 — get_financial_series 예외 graceful → 통과
# ---------------------------------------------------------------------------
class TestFailOpenGraceful:
    @pytest.mark.asyncio
    async def test_series_exception_passes(self):
        strategy = _make_strategy(quant_filter_enabled=False)
        hook = getattr(strategy, "_apply_quant_filter_in_prepare", None)
        assert hook is not None

        with patch("src.db.stock_master_financial.get_financial_series",
                   new=AsyncMock(side_effect=RuntimeError("DB down"))), \
             patch("src.db.stock_master.get", new=AsyncMock(return_value=None)), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()):
            result = await hook(["005930"])

        assert result == ["005930"], (
            "get_financial_series 예외인데 배제 발생 — graceful 통과 위반 (사이클 88)."
        )


# ---------------------------------------------------------------------------
# PROTECT-1 — 보유 종목 무조건 통과 (사이클 32 R4)
# ---------------------------------------------------------------------------
class TestProtectedPassthrough:
    @pytest.mark.asyncio
    async def test_held_ticker_always_passes(self):
        # 활성 모드(enabled=True)에서도 보유 종목은 절대 배제 안 됨.
        strategy = _make_strategy(quant_filter_enabled=True, quant_min_f_score=9)
        hook = getattr(strategy, "_apply_quant_filter_in_prepare", None)
        assert hook is not None

        # 매우 낮은 f_score 를 반환해도 보유 종목이면 통과
        with patch("src.db.stock_master_financial.get_financial_series",
                   new=AsyncMock(side_effect=lambda t, **kw: _fin_series(t))), \
             patch("src.engine.quant_score.compute_f_score_7", new=MagicMock(return_value=0)), \
             patch("src.engine.quant_score.compute_magic_formula", new=MagicMock(return_value={})), \
             patch("src.db.stock_master.get", new=AsyncMock(return_value=None)), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value={"005930"}):
            result = await hook(["005930"])

        assert "005930" in result, (
            "보유 종목이 재무 게이트에서 배제됨 — 사이클 32 R4 절대 보호 위반."
        )


# ---------------------------------------------------------------------------
# PARAM-1 (AST) — DEFAULT_PARAMS quant 키 3종
# ---------------------------------------------------------------------------
class TestDefaultParamsQuantKeys:
    def test_default_params_quant_keys(self):
        from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

        dp = VolatilityBreakoutStrategy.DEFAULT_PARAMS
        assert dp.get("quant_filter_enabled") is False, (
            f"DEFAULT_PARAMS['quant_filter_enabled'] != False (기본 OFF): {dp.get('quant_filter_enabled')}"
        )
        assert dp.get("quant_min_f_score") == 0, (
            f"DEFAULT_PARAMS['quant_min_f_score'] != 0 (비활성): {dp.get('quant_min_f_score')}"
        )
        assert dp.get("quant_max_mf_rank") == 0, (
            f"DEFAULT_PARAMS['quant_max_mf_rank'] != 0 (비활성): {dp.get('quant_max_mf_rank')}"
        )


# ---------------------------------------------------------------------------
# FUNNEL-1 — VB_FUNNEL_STAGES 7단계 (step_no=7)
# ---------------------------------------------------------------------------
class TestFunnelStagesExtended:
    def test_funnel_stages_has_7_steps(self):
        from src.engine.strategies.volatility_breakout import VB_FUNNEL_STAGES

        assert len(VB_FUNNEL_STAGES) == 7, (
            f"VB_FUNNEL_STAGES 단계 수 {len(VB_FUNNEL_STAGES)} != 7 (관찰 게이트 +1단계)."
        )
        step_nos = [s.step_no for s in VB_FUNNEL_STAGES]
        assert 7 in step_nos, f"step_no=7 (퀀트 재무 게이트) 누락: {step_nos}"
        stage7 = next(s for s in VB_FUNNEL_STAGES if s.step_no == 7)
        assert "퀀트" in stage7.step_name or "재무" in stage7.step_name or "관찰" in stage7.step_name, (
            f"step_no=7 이름이 퀀트 재무 게이트가 아님: {stage7.step_name!r}"
        )


# ---------------------------------------------------------------------------
# HOOK-ORDER (AST) — _apply_quant_filter_in_prepare 가 master_block 다음 호출
# ---------------------------------------------------------------------------
class TestHookOrderAfterMasterBlock:
    def test_quant_hook_after_master_block_in_prepare(self):
        src = _VB_SRC.read_text(encoding="utf-8")
        # prepare 본체에서 master_block 호출 뒤에 quant 훅 호출이 와야 함
        assert "_apply_quant_filter_in_prepare" in src, (
            "_apply_quant_filter_in_prepare 정의/호출 부재."
        )
        mb_idx = src.find("_apply_master_block_filter_in_prepare(tickers)")
        quant_idx = src.find("_apply_quant_filter_in_prepare(")
        assert mb_idx != -1, "master_block 호출부 미발견."
        assert quant_idx != -1, "quant 훅 호출부 미발견."
        # quant 훅 호출은 master_block 호출 이후 위치
        # (정의부가 아닌 prepare 내 호출부 — self. 접두)
        prepare_call = src.find("self._apply_quant_filter_in_prepare(")
        prepare_mb_call = src.find("self._apply_master_block_filter_in_prepare(tickers)")
        assert prepare_mb_call != -1 and prepare_call != -1, (
            "prepare 내 self. 호출부 미발견 (master_block / quant)."
        )
        assert prepare_call > prepare_mb_call, (
            "quant 훅이 master_block 이전에 호출됨 — master_block 다음 단계 삽입 위반."
        )


# ---------------------------------------------------------------------------
# G-1 (HIGH SAFETY, AST) — check_buy_signal / check_exit_signal 본체 diff 0
# ---------------------------------------------------------------------------
class TestMatchingLogicUnchangedSafety:
    def _method_source(self, name: str) -> str:
        src = _VB_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return ast.get_source_segment(src, node) or ""
        return ""

    def test_check_buy_signal_no_quant_hook(self):
        body = self._method_source("check_buy_signal")
        assert body, "check_buy_signal 미발견."
        for token in (
            "quant", "compute_f_score_7", "compute_magic_formula",
            "get_financial_series", "_apply_quant_filter_in_prepare",
        ):
            assert token not in body, (
                f"check_buy_signal 본체에 재무 토큰 '{token}' 인젝션 — 매매 로직 diff 0 위반 (G-1)."
            )

    def test_check_exit_signal_no_quant_hook(self):
        body = self._method_source("check_exit_signal")
        assert body, "check_exit_signal 미발견."
        for token in (
            "quant", "compute_f_score_7", "compute_magic_formula",
            "get_financial_series", "_apply_quant_filter_in_prepare",
        ):
            assert token not in body, (
                f"check_exit_signal 본체에 '{token}' 인젝션 — 청산 로직 diff 0 위반 (G-1)."
            )


# ---------------------------------------------------------------------------
# SAFETY-2 (AST) — 훅 영역 check_exit_signal 호출 0 + risk/order_engine import 0
# ---------------------------------------------------------------------------
class TestQuantHookNoExitOrOrderImport:
    def _method_source(self, name: str) -> str:
        src = _VB_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return ast.get_source_segment(src, node) or ""
        return ""

    def test_quant_hook_no_exit_call(self):
        body = self._method_source("_apply_quant_filter_in_prepare")
        assert body, "_apply_quant_filter_in_prepare 미발견 (C3 (c) 산출물)."
        assert "check_exit_signal" not in body, (
            "quant 훅 영역에 check_exit_signal 호출 — 매수 진입 전 영역 위반 (사이클 38)."
        )

    def test_quant_hook_no_risk_order_import(self):
        body = self._method_source("_apply_quant_filter_in_prepare")
        assert body, "_apply_quant_filter_in_prepare 미발견."
        for token in ("order_engine", "from src.engine.risk", "import risk"):
            assert token not in body, (
                f"quant 훅 영역에 '{token}' import — 매매 hot path 결합 위반 (SAFETY-2)."
            )


# ---------------------------------------------------------------------------
# PARAM-RANGES (AST) — recommendation_engine.py PARAM_RANGES 에 quant 키 미편입
# ---------------------------------------------------------------------------
class TestParamRangesNoQuantKeys:
    def test_reco_param_ranges_excludes_quant(self):
        src = _RECO_SRC.read_text(encoding="utf-8")
        # PARAM_RANGES 딕셔너리 영역에 quant 키가 등록되면 안 됨 (초기 관찰)
        for token in ("quant_min_f_score", "quant_max_mf_rank", "quant_filter_enabled"):
            assert token not in src, (
                f"recommendation_engine.py 에 '{token}' 등장 — "
                "PARAM_RANGES AI 자동튜닝 편입 금지 위반 (관찰 전용, 진입 정체성)."
            )
