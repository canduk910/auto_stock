"""사이클 143 — VB 5단계 + LTV 6단계 funnel hook 회귀 가드 (사이클 140 자문 영속).

사용자 결정: Q1=A 사이클 142 commit `5d69467` push + CI success 5분 43초 + EC2 Deploy success 19초 + Q2 사이클 143 funnel hook 즉시 발주.

배경 (사이클 140 자문 영속):
- VB / LTV `prepare()` 영역 `_record_funnel_pipeline_step` 호출 0건 (사이클 132 진단)
- 사이클 39+41 BFB/VCP/donchian 8단계 답습 = VB/LTV 과도 → 단순 5/6단계 적정
- 사이클 132 사용자 결정 Q1=C → 사이클 140 domain-expert 자문 → 옵션 B → 사이클 143 TDD

VB 5단계 권고 (사이클 140 자문):
1. 거래량순위 + stock_master 기반 후보 (universe_candidates)
2. 시총 + 거래대금 필터 통과 (universe_filtered)
3. 일봉 fetch 통과 (candle_fetch_ok)
4. 전일 Range + noise 통과
5. K값 계산 + target_offset > 0 (final_prepared)

LTV 6단계 권고 (사이클 140 자문):
1. 거래량순위 + stock_master 기반 후보
2. 시총 + 거래대금 필터 통과
3. 일봉 fetch 통과
4. 전일 Range + noise 통과
5. 연속 상한가 필터 통과 (consecutive_limit_pass)
6. K값 계산 + target_offset > 0

영속 의무:
- 사이클 21 _scan_stats 9/10 키 (변경 0)
- 사이클 38 명문화 (scanner 매수 진입 *전* 영역 한정)
- 사이클 39+41 funnel hook 패턴 100% 답습
- 사이클 47 FUNNEL_STAGES 위임 패턴 답습
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import (
    count_function_calls,
    count_function_calls_in_node,
    find_function_def,
    read_module_source,
)

pytestmark = pytest.mark.unit


_VB_PY = (
    Path(__file__).resolve().parents[4]
    / "src" / "engine" / "strategies" / "volatility_breakout.py"
)
_LTV_PY = (
    Path(__file__).resolve().parents[4]
    / "src" / "engine" / "strategies" / "long_tail_volatility.py"
)


# =============================================================================
# G-143-VB — VB 5단계 funnel hook (5 케이스)
# =============================================================================


class TestVBFunnelHook:
    """VB `prepare()` 영역 5단계 funnel hook 영속."""

    def test_g_143_vb_1_funnel_stages_constant(self):
        """G-143-VB-1: `VB_FUNNEL_STAGES` 모듈 상수 5 stages 영속.

        donchian `FUNNEL_STAGES` 패턴 답습 (사이클 47).
        Annotated assignment (`VAR: type = (...)`) + 단순 assignment 둘 다 인식.
        """
        source = read_module_source(_VB_PY)
        tree = ast.parse(source)

        # 모듈 영역 영구 영속 `VB_FUNNEL_STAGES = (...)` 영역 찾기 (Assign + AnnAssign 양쪽)
        found_constant = False
        stage_count = 0
        for node in ast.walk(tree):
            target_name = None
            value_node = None
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "VB_FUNNEL_STAGES":
                        target_name = target.id
                        value_node = node.value
                        break
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "VB_FUNNEL_STAGES":
                    target_name = node.target.id
                    value_node = node.value

            if target_name == "VB_FUNNEL_STAGES":
                found_constant = True
                if isinstance(value_node, ast.Tuple):
                    stage_count = len(value_node.elts)
                break

        assert found_constant, "VB_FUNNEL_STAGES 모듈 상수 부재 (사이클 47 패턴 답습)"
        assert stage_count >= 5, (
            f"VB_FUNNEL_STAGES stage 수 = {stage_count}, ≥ 5 영속 의무 위반 "
            f"(사이클 140 자문 권고)"
        )

    def test_g_143_vb_2_prepare_record_funnel_calls(self):
        """G-143-VB-2: `prepare()` 본체 `_record_funnel_pipeline_step` 호출 ≥ 5건 영속."""
        source = read_module_source(_VB_PY)
        node = find_function_def(source, "prepare")
        assert node is not None, "prepare 함수 정의 부재"

        # `_record_funnel_pipeline_step` 호출 사이트 count
        # `self._record_funnel_pipeline_step(...)` 영역 영구 영속
        call_count = count_function_calls_in_node(node, "_record_funnel_pipeline_step")

        assert call_count >= 5, (
            f"VB prepare() `_record_funnel_pipeline_step` 호출 {call_count}건, "
            f"≥ 5건 영속 의무 위반 (사이클 140 자문 권고 5단계)"
        )

    def test_g_143_vb_3_reset_funnel_steps_called(self):
        """G-143-VB-3: `prepare()` 본체 `_reset_funnel_steps()` 호출 영속 (사이클 39 답습)."""
        source = read_module_source(_VB_PY)
        node = find_function_def(source, "prepare")
        assert node is not None

        reset_count = count_function_calls_in_node(node, "_reset_funnel_steps")
        assert reset_count >= 1, (
            f"VB prepare() `_reset_funnel_steps()` 호출 {reset_count}건, "
            f"≥ 1건 영속 의무 (사이클 39 답습)"
        )

    def test_g_143_vb_4_funnel_stages_import(self):
        """G-143-VB-4: `from src.engine.strategy_base import FunnelStage` import 영속."""
        source = read_module_source(_VB_PY)
        # FunnelStage import 영역 영구 영속
        assert "FunnelStage" in source, "VB 영역 FunnelStage import 부재"

    def test_g_143_vb_5_scan_stats_unchanged(self):
        """G-143-VB-5: `_empty_scan_stats` 9 키 영속 (사이클 21 변경 0)."""
        source = read_module_source(_VB_PY)
        node = find_function_def(source, "_empty_scan_stats")
        assert node is not None

        body_src = ast.unparse(node)
        # 사이클 21 키 영속 (변경 0 영역)
        for key in (
            "universe_candidates",
            "universe_filtered",
            "price_filtered",
            "mcap_pass",
            "trade_amount_pass",
            "candle_fetch_ok",
            "k_value_computed",
            "final_prepared",
            "last_run_at",
        ):
            assert key in body_src, f"VB _empty_scan_stats 키 '{key}' 부재"


# =============================================================================
# G-143-LTV — LTV 6단계 funnel hook (5 케이스)
# =============================================================================


class TestLTVFunnelHook:
    """LTV `prepare()` 영역 6단계 funnel hook 영속."""

    def test_g_143_ltv_1_funnel_stages_constant(self):
        """G-143-LTV-1: `LTV_FUNNEL_STAGES` 모듈 상수 6 stages 영속.

        Annotated assignment + 단순 assignment 둘 다 인식.
        """
        source = read_module_source(_LTV_PY)
        tree = ast.parse(source)

        found_constant = False
        stage_count = 0
        for node in ast.walk(tree):
            target_name = None
            value_node = None
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "LTV_FUNNEL_STAGES":
                        target_name = target.id
                        value_node = node.value
                        break
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "LTV_FUNNEL_STAGES":
                    target_name = node.target.id
                    value_node = node.value

            if target_name == "LTV_FUNNEL_STAGES":
                found_constant = True
                if isinstance(value_node, ast.Tuple):
                    stage_count = len(value_node.elts)
                break

        assert found_constant, "LTV_FUNNEL_STAGES 모듈 상수 부재"
        assert stage_count >= 6, (
            f"LTV_FUNNEL_STAGES stage 수 = {stage_count}, ≥ 6 영속 의무 위반"
        )

    def test_g_143_ltv_2_prepare_record_funnel_calls(self):
        """G-143-LTV-2: `prepare()` 본체 `_record_funnel_pipeline_step` 호출 ≥ 6건 영속."""
        source = read_module_source(_LTV_PY)
        node = find_function_def(source, "prepare")
        assert node is not None

        call_count = count_function_calls_in_node(node, "_record_funnel_pipeline_step")

        assert call_count >= 6, (
            f"LTV prepare() `_record_funnel_pipeline_step` 호출 {call_count}건, "
            f"≥ 6건 영속 의무 위반 (사이클 140 자문 권고 6단계 = VB 5 + consecutive_limit)"
        )

    def test_g_143_ltv_3_reset_funnel_steps_called(self):
        """G-143-LTV-3: `prepare()` 본체 `_reset_funnel_steps()` 호출 영속."""
        source = read_module_source(_LTV_PY)
        node = find_function_def(source, "prepare")
        assert node is not None

        reset_count = count_function_calls_in_node(node, "_reset_funnel_steps")
        assert reset_count >= 1, "LTV prepare() `_reset_funnel_steps()` 호출 부재"

    def test_g_143_ltv_4_funnel_stages_import(self):
        """G-143-LTV-4: `FunnelStage` import 영속."""
        source = read_module_source(_LTV_PY)
        assert "FunnelStage" in source, "LTV 영역 FunnelStage import 부재"

    def test_g_143_ltv_5_scan_stats_unchanged(self):
        """G-143-LTV-5: `_empty_scan_stats` 10 키 영속 (사이클 21 변경 0)."""
        source = read_module_source(_LTV_PY)
        node = find_function_def(source, "_empty_scan_stats")
        assert node is not None

        body_src = ast.unparse(node)
        # 사이클 21 LTV 10 키 영속 (변경 0 영역)
        for key in (
            "universe_candidates",
            "universe_filtered",
            "price_filtered",
            "mcap_pass",
            "trade_amount_pass",
            "candle_fetch_ok",
            "consecutive_limit_pass",  # LTV 전용
            "k_value_computed",
            "final_prepared",
            "last_run_at",
        ):
            assert key in body_src, f"LTV _empty_scan_stats 키 '{key}' 부재"


# =============================================================================
# G-143-INTEGRATION — prepare() 후 _funnel_steps 메모리 적재 영역 검증 (2 케이스)
# =============================================================================


class TestFunnelStepsIntegration:
    """`prepare()` 호출 후 `_funnel_steps` 메모리 적재 영역 영속."""

    @pytest.mark.asyncio
    async def test_g_143_int_1_vb_prepare_records_funnel_steps(self, monkeypatch):
        """G-143-INT-1: VB `prepare()` 호출 후 `_funnel_steps` 5건 영속.

        시뮬레이션: stock_master mock + fetch_daily_candles mock → prepare() 호출 → _funnel_steps 길이 ≥ 5.
        """
        from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
        from src.engine.strategy_base import StrategyConfig

        config = StrategyConfig(
            strategy_id="volatility_breakout",
            name="변동성돌파",
            params={
                "k_period": 20,
                "stop_loss_rate": -3.0,
                "position_ratio": 0.10,
                "max_positions": 10,
                "daily_loss_limit": -5.0,
                "k_value_krx_main": 1.0,
                "min_market_cap": 100_000_000_000,
                "min_trade_amount": 20_000_000_000,
                "max_scan_stocks": 100,
                "exchange": "KRX",
            },
            enabled=True,
        )
        strategy = VolatilityBreakoutStrategy(config)

        # stock_master.list_by_filter mock — 빈 list 반환 (universe 0 → 단계 1~2 만 발화)
        async def _mock_list_by_filter(**kwargs):
            return []

        from src.db import stock_master as _sm_mod
        monkeypatch.setattr(_sm_mod, "list_by_filter", _mock_list_by_filter)

        await strategy.prepare()

        # _funnel_steps 영역 영구 영속 ≥ 1건 (단계 1~2 발화 영속)
        assert len(strategy._funnel_steps) >= 1, (
            f"VB prepare() 후 _funnel_steps {len(strategy._funnel_steps)}건, "
            f"≥ 1건 영속 의무 위반"
        )

    @pytest.mark.asyncio
    async def test_g_143_int_2_ltv_prepare_records_funnel_steps(self, monkeypatch):
        """G-143-INT-2: LTV `prepare()` 호출 후 `_funnel_steps` 영속."""
        from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
        from src.engine.strategy_base import StrategyConfig

        config = StrategyConfig(
            strategy_id="long_tail_volatility",
            name="롱테일VB",
            params={
                "k_period": 20,
                "min_prdy_rate": 5.0,
                "min_market_cap": 100_000_000_000,
                "min_trade_amount": 20_000_000_000,
                "max_scan_stocks": 100,
                "exclude_consecutive_limit": 2,
                "intraday_stop_loss": -3.0,
                "limit_up_threshold": 29.0,
                "overnight_stop_loss": -5.0,
                "gap_up_threshold": 10.0,
                "trailing_stop_rate": -1.2,
                "position_ratio": 0.15,
                "max_positions": 6,
                "daily_loss_limit": -5.0,
                "k_value_krx_main": 1.0,
                "exchange": "KRX",
            },
            enabled=True,
        )
        strategy = LongTailVolatilityStrategy(config)

        async def _mock_list_by_filter(**kwargs):
            return []

        from src.db import stock_master as _sm_mod
        monkeypatch.setattr(_sm_mod, "list_by_filter", _mock_list_by_filter)

        await strategy.prepare()

        assert len(strategy._funnel_steps) >= 1, (
            f"LTV prepare() 후 _funnel_steps {len(strategy._funnel_steps)}건, "
            f"≥ 1건 영속 의무 위반"
        )


# =============================================================================
# G-143-SAFETY — 매매 안전성 영역 영구 영속 (3 케이스)
# =============================================================================


class TestSafetyDirectVerification:
    """매매 안전성 직접 검증 — 사이클 38 명문화 영속."""

    def test_g_143_safety_1_vb_tradable_boards_unchanged(self):
        """G-143-SAFETY-1: VB `DEFAULT_TRADABLE_BOARDS=("main",)` 영속 (사이클 26)."""
        source = read_module_source(_VB_PY)
        assert 'DEFAULT_TRADABLE_BOARDS = ("main",)' in source, (
            "VB DEFAULT_TRADABLE_BOARDS 변경 — 사이클 26 영속 위반"
        )

    def test_g_143_safety_2_ltv_tradable_boards_unchanged(self):
        """G-143-SAFETY-2: LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt","main","post_nxt")` 영속 (사이클 38)."""
        source = read_module_source(_LTV_PY)
        # 사이클 38 복원 영속
        assert 'DEFAULT_TRADABLE_BOARDS = ("pre_nxt", "main", "post_nxt")' in source, (
            "LTV DEFAULT_TRADABLE_BOARDS 변경 — 사이클 38 영속 위반"
        )

    def test_g_143_safety_3_no_check_exit_signal_change(self):
        """G-143-SAFETY-3: VB / LTV `check_exit_signal` 영역 변경 0 (매도 hot path 무관)."""
        vb_source = read_module_source(_VB_PY)
        ltv_source = read_module_source(_LTV_PY)

        # VB / LTV `check_exit_signal` 영역 영구 영속
        vb_node = find_function_def(vb_source, "check_exit_signal")
        ltv_node = find_function_def(ltv_source, "check_exit_signal")

        assert vb_node is not None, "VB check_exit_signal 함수 정의 부재"
        assert ltv_node is not None, "LTV check_exit_signal 함수 정의 부재"

        # check_exit_signal 본체 영역 영구 영속 _record_funnel_pipeline_step 호출 0건
        vb_body_funnel_calls = count_function_calls_in_node(vb_node, "_record_funnel_pipeline_step")
        ltv_body_funnel_calls = count_function_calls_in_node(ltv_node, "_record_funnel_pipeline_step")

        assert vb_body_funnel_calls == 0, (
            f"VB check_exit_signal 본체 funnel hook 호출 {vb_body_funnel_calls}건 — "
            f"매도 hot path 영향 위반"
        )
        assert ltv_body_funnel_calls == 0, (
            f"LTV check_exit_signal 본체 funnel hook 호출 {ltv_body_funnel_calls}건 — "
            f"매도 hot path 영향 위반"
        )
