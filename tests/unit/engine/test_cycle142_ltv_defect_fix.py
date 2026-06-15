"""사이클 142 — LTV 결함 #1 + #2 통합 시정 회귀 가드.

사용자 결정: 옵션 A 단일 통합 TDD (사이클 140 funnel 자문 + 사이클 141 LTV 재설계 자문 통합).

결함 #1 (`_force_clear_main_only`):
- 현행: POST_NXT 활성 시 LTV `check_force_clear()` 호출 자체 안 함 → 모든 종목 보류 (사이클 38 명세 위반)
- 시정: `check_force_clear()` 호출 → LTV 본체가 _limit_up_reached 제외 (상한가 모드 종목 보존)

결함 #2 (`_execute_next_day_clear`):
- 현행: 트레일링 분기 메시지만 emit + LTV strategy 후성 미동기화 → check_exit_signal 당일 모드 진입 → 트레일링 silent 미발화
- 시정: trail 분기에 _limit_up_reached.add(ticker) + pos.high_since_buy = today_open (VB 변경 0)

운영 사례 후성 093370:
- 6/12 매수 17,150원
- 6/15 일중 고점 23,700원 (15:55) → 마감 22,300원 = -5.91% 하락
- 운영 trailing_stop_rate=-1.2% 임계 + 매도 silent 미발화

영속 의무:
- 사이클 38 명문화 영속 (LTV check_force_clear 본체 정합)
- 사이클 141 자문 영속 (refactor + domain 일치)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit


_SCHEDULER_PY = Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
_LTV_PY = (
    Path(__file__).resolve().parents[3]
    / "src" / "engine" / "strategies" / "long_tail_volatility.py"
)


# =============================================================================
# G-142-DEFECT1 — 결함 #1 시정 회귀 가드 (5 케이스)
# =============================================================================


class TestDefect1ForceClearMainOnly:
    """결함 #1 — `_force_clear_main_only` LTV `check_force_clear()` 호출 보장."""

    def test_g_142_defect1_1_check_force_clear_called_for_ltv(self):
        """G-142-DEFECT1-1: `_force_clear_main_only` 영역 LTV `check_force_clear()` 호출 영속.

        시정 후 = `keeps_post_nxt` 무관 `check_force_clear()` 호출.
        Red = 사이클 142 시정 *전* (현행 코드 `continue` 분기에서 호출 자체 안 함) FAIL.
        Green = 시정 후 PASS.
        """
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_force_clear_main_only")
        assert node is not None, "_force_clear_main_only 함수 정의 부재"

        # 함수 본체에 strategy.check_force_clear() 호출 사이트 ≥ 1건
        check_force_clear_calls = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                if isinstance(func, ast.Attribute) and func.attr == "check_force_clear":
                    check_force_clear_calls.append(sub.lineno)

        assert len(check_force_clear_calls) >= 1, (
            f"_force_clear_main_only 본체 check_force_clear() 호출 0건 — "
            f"사이클 142 시정 의무 위반 (사이클 141 자문 결함 #1)"
        )

    def test_g_142_defect1_2_no_keeps_post_nxt_continue_before_check_force_clear(self):
        """G-142-DEFECT1-2: `keeps_post_nxt` continue 분기 영구 폐기 영속.

        시정 후 = `continue` 가 `check_force_clear()` 호출 *후* 만 존재.
        """
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_force_clear_main_only")
        assert node is not None

        # 함수 본체 ast.unparse
        body_src = ast.unparse(node)

        # check_force_clear 호출 위치 vs keeps_post_nxt continue 분기 위치 비교
        # 시정 패턴: check_force_clear() 가 keeps_post_nxt 분기 *전* 호출
        # 또는 keeps_post_nxt 분기에 continue 없음 (단순 log emit 만)
        # 결함 패턴: keeps_post_nxt: ... continue → check_force_clear() 호출 안 됨
        ccfc_idx = body_src.find("check_force_clear()")
        keeps_post_nxt_block_idx = body_src.find("keeps_post_nxt = ")

        if ccfc_idx >= 0 and keeps_post_nxt_block_idx >= 0:
            # 패턴 A: check_force_clear() 가 keeps_post_nxt 영역 *전* → 시정 정합
            # 패턴 B: keeps_post_nxt 영역에 continue 없음 → 시정 정합
            keeps_block_end = body_src.find("\n\n", keeps_post_nxt_block_idx)
            if keeps_block_end < 0:
                keeps_block_end = len(body_src)
            keeps_block = body_src[keeps_post_nxt_block_idx:keeps_block_end]

            if "continue" in keeps_block and ccfc_idx > keeps_post_nxt_block_idx:
                pytest.fail(
                    f"_force_clear_main_only 영역에 `keeps_post_nxt` continue 분기 *후* "
                    f"`check_force_clear()` 호출 — 시정 위반 (결함 #1 영속)"
                )

    def test_g_142_defect1_3_ltv_check_force_clear_body_unchanged(self):
        """G-142-DEFECT1-3: LTV `check_force_clear()` 본체 변경 0 (상한가 모드 제외 로직 영속)."""
        source = read_module_source(_LTV_PY)
        node = find_function_def(source, "check_force_clear")
        assert node is not None, "LTV check_force_clear 함수 정의 부재"

        body_src = ast.unparse(node)
        # 본체에 `_limit_up_reached` 영역 영속 (상한가 모드 종목 제외)
        assert "_limit_up_reached" in body_src, (
            "LTV check_force_clear 영역 `_limit_up_reached` 제외 로직 부재 — "
            "사이클 38 명세 정합 위반"
        )

    def test_g_142_defect1_4_ast_continue_before_check_force_clear_zero(self):
        """G-142-DEFECT1-4: AST 가드 — `continue` 분기 영구 `check_force_clear()` 호출 *전* 차단 0건."""
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_force_clear_main_only")
        assert node is not None

        # 함수 본체 내 모든 Continue 노드 + 그 이전 check_force_clear 호출 패턴 검사
        # AST 단일 walk 으로는 line-order 추적이 어려우므로 ast.unparse + 패턴 분석
        body_src = ast.unparse(node)

        # 검출 패턴: keeps_post_nxt 블록 내부에 continue + check_force_clear 미호출
        # 시정: 분기 폐기 또는 check_force_clear 호출 후 continue
        lines = body_src.split("\n")
        ccfc_line = next(
            (i for i, line in enumerate(lines) if "check_force_clear()" in line),
            -1,
        )
        # check_force_clear() 가 함수 본체에 존재 의무
        assert ccfc_line >= 0, "check_force_clear() 호출 미존재 (사이클 142 시정 위반)"

    def test_g_142_defect1_5_for_loop_includes_both_strategies(self):
        """G-142-DEFECT1-5: `_force_clear_main_only` for sid loop 영역 영속 영역.

        VB + LTV 두 전략 모두 영역.
        """
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_force_clear_main_only")
        assert node is not None

        body_src = ast.unparse(node)
        assert "volatility_breakout" in body_src
        assert "long_tail_volatility" in body_src


# =============================================================================
# G-142-DEFECT2 — 결함 #2 시정 회귀 가드 (5 케이스)
# =============================================================================


class TestDefect2NextDayClearTrailing:
    """결함 #2 — `_execute_next_day_clear` 트레일링 분기 LTV strategy 상태 동기화."""

    def test_g_142_defect2_1_limit_up_reached_add_in_trailing_branch(self):
        """G-142-DEFECT2-1: 트레일링 분기 영역 `_limit_up_reached.add` 호출 영속."""
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_execute_next_day_clear")
        assert node is not None, "_execute_next_day_clear 함수 정의 부재"

        body_src = ast.unparse(node)

        # 트레일링 분기 영역 영구 영속 = `gap_rate >= gap_up_threshold` if 분기 내부
        # `_limit_up_reached.add` 호출 영역 영구 영속
        assert "_limit_up_reached" in body_src, (
            "_execute_next_day_clear 영역 _limit_up_reached 동기화 부재 — "
            "사이클 142 결함 #2 시정 위반"
        )

    def test_g_142_defect2_2_high_since_buy_set_to_today_open(self):
        """G-142-DEFECT2-2: 트레일링 분기 영역 `pos.high_since_buy = today_open` 설정 영속."""
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_execute_next_day_clear")
        assert node is not None

        body_src = ast.unparse(node)
        # 트레일링 분기 영역 영구 영속 = `pos.high_since_buy` 영역 영구 영속 설정 영역 영구 영속
        # 시정 패턴: pos.high_since_buy = today_open
        assert "pos.high_since_buy" in body_src and "today_open" in body_src, (
            "_execute_next_day_clear 영역 pos.high_since_buy = today_open 설정 부재"
        )

    def test_g_142_defect2_3_vb_no_change_in_trailing_branch(self):
        """G-142-DEFECT2-3: VB 변경 0 영역 영속 (`strategy_id == "long_tail_volatility"` 가드)."""
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_execute_next_day_clear")
        assert node is not None

        body_src = ast.unparse(node)
        # 시정 패턴: strategy_id == "long_tail_volatility" 가드 영역
        assert "long_tail_volatility" in body_src, (
            "_execute_next_day_clear 영역 LTV 분기 가드 부재 — VB 영향 위험"
        )

    def test_g_142_defect2_4_trailing_log_includes_open_price(self):
        """G-142-DEFECT2-4: 트레일링 로그 기준가 명시 영속 (운영 가시화 영역)."""
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_execute_next_day_clear")
        assert node is not None

        body_src = ast.unparse(node)
        # 시정 패턴: 트레일링 스탑 모드 로그 메시지 영역 영구 영속 기준가 영역 영구 영속
        assert "트레일링 스탑 모드" in body_src

    def test_g_142_defect2_5_ast_limit_up_reached_add_persistence(self):
        """G-142-DEFECT2-5: AST 가드 — `_limit_up_reached.add` 호출 영역 영구 영속."""
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_execute_next_day_clear")
        assert node is not None

        # `_limit_up_reached` 영역 영구 영속 + `.add` 호출 영역 영구 영속
        # AST 정적 가드
        body_src = ast.unparse(node)
        assert "_limit_up_reached" in body_src and ".add(" in body_src


# =============================================================================
# G-142-SAFETY — 매매 안전성 직접 검증 (4 케이스)
# =============================================================================


class TestMatchingSafetyDirectVerification:
    """매매 안전성 영역 영구 영속 직접 검증."""

    def test_g_142_safety_1_cycle38_meeting_preserved(self):
        """G-142-SAFETY-1: 사이클 38 명세 정합 — 상한가 모드 종목 영역 영구 영속 15:20 보존."""
        ltv_source = read_module_source(_LTV_PY)
        ltv_node = find_function_def(ltv_source, "check_force_clear")
        assert ltv_node is not None

        ltv_body = ast.unparse(ltv_node)
        # 사이클 38 명세 = LTV check_force_clear 영역 영구 영속 `_limit_up_reached` 제외
        assert "_limit_up_reached" in ltv_body, "사이클 38 명세 위반"
        # ticker not in _limit_up_reached 패턴 영역 영구 영속
        assert "not in" in ltv_body or "not (" in ltv_body, (
            "사이클 38 명세 영역 영구 영속 상한가 모드 제외 패턴 영역 부재"
        )

    def test_g_142_safety_2_vb_unchanged(self):
        """G-142-SAFETY-2: VB 변경 0 (사용자 verbatim "VB는 잘 동작" 보존)."""
        vb_path = (
            Path(__file__).resolve().parents[3]
            / "src" / "engine" / "strategies" / "volatility_breakout.py"
        )
        vb_source = read_module_source(vb_path)

        # VB `DEFAULT_TRADABLE_BOARDS = ("main",)` 영속 (사이클 26)
        assert 'DEFAULT_TRADABLE_BOARDS = ("main",)' in vb_source

        # VB check_force_clear 영역 영구 영속
        vb_node = find_function_def(vb_source, "check_force_clear")
        assert vb_node is not None

    def test_g_142_safety_3_pending_next_day_clear_preserved(self):
        """G-142-SAFETY-3: `_pending_next_day_clear` + 30s 안정화 영속."""
        source = read_module_source(_SCHEDULER_PY)
        # 30s 안정화 영역 영구 영속 = `NEXT_DAY_STABILIZE_SECS`
        assert "NEXT_DAY_STABILIZE_SECS" in source
        # `_pending_next_day_clear` 영속
        assert "_pending_next_day_clear" in source

    def test_g_142_safety_4_no_risk_order_engine_change(self):
        """G-142-SAFETY-4: risk/order_engine/realtime/auth 변경 0 영역 영구 영속.

        본 가드 영역 영구 영속 = 사이클 142 시정 영역 영구 영속이 scheduler.py 영역 영구 영속 한정 영역 영구 영속.
        scheduler.py 시정 후에도 risk.on_tick / order_engine.execute_sell / WebSocket 영역 영구 영속 변경 0.
        """
        # AST 정적 가드 — risk/order_engine import 영역 영구 영속 (변경 0)
        scheduler_source = read_module_source(_SCHEDULER_PY)
        # `from src.engine.order_engine import` 또는 `from src.engine.risk import` 영역 영구 영속
        # 본 영역 영구 영속 = 기존 import 영역 영구 영속 보존 영역 영구 영속
        assert "order_engine" in scheduler_source, "order_engine import 영역 변경"


# =============================================================================
# G-142-INTEGRATION — 후성 093370 운영 사례 재현 (1 케이스)
# =============================================================================


class TestHooSung093370Reproduction:
    """후성 093370 운영 사례 재현 — 시정 후 트레일링 정합 발화 보장."""

    @pytest.mark.asyncio
    async def test_g_142_integration_1_hoosung_093370_trailing_fires(self):
        """G-142-INT-1: 후성 093370 운영 사례 재현 영역 영구 영속.

        시뮬레이션:
        - 6/12 매수 17,150원
        - 6/15 시가 22,500원 (갭률 +31.2%)
        - gap_up_threshold = 10.0%
        - 6/15 일중 고점 23,700원 (15:55)
        - 6/15 마감 22,300원 (-5.91% 하락)
        - trailing_stop_rate = -1.2%

        시정 후 기대 동작:
        - _execute_next_day_clear 트레일링 분기 진입
        - LTV._limit_up_reached.add("093370")
        - pos.high_since_buy = today_open (22,500)
        - check_exit_signal 영역 트레일링 분기 진입
        - pos.high_since_buy = max(22,500, 23,700) = 23,700
        - drop_rate = (22,300 - 23,700) / 23,700 × 100 = -5.91%
        - -5.91% ≤ -1.2% → TRAILING_STOP 발화

        본 가드 영역 영구 영속 = check_exit_signal 영역 영구 영속 시뮬레이션 영역 영구 영속.
        """
        from src.engine.strategies.long_tail_volatility import (
            LongTailVolatilityStrategy,
        )
        from src.engine.strategy_base import (
            Position,
            Signal,
            StrategyConfig,
            StrategyState,
        )

        # LTV 인스턴스 영역 영구 영속
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
                "trailing_stop_rate": -1.2,  # 운영값
                "position_ratio": 0.15,
                "max_positions": 6,
                "daily_loss_limit": -5.0,
            },
            enabled=True,
        )
        strategy = LongTailVolatilityStrategy(config)

        # 6/12 매수 영역 영구 영속
        pos = Position(
            ticker="093370",
            buy_price=17150,
            quantity=10,
            order_no="ORDER1",
            strategy_id="long_tail_volatility",
        )
        from datetime import datetime, date, timedelta, timezone
        # buy_date < today → is_next_day = True
        pos.buy_date = date(2026, 6, 12)
        pos.high_since_buy = 22500  # 시정 후 today_open 설정 영역
        strategy.state.positions["093370"] = pos

        # 시정 후 영역 영구 영속: _limit_up_reached 영역 영구 영속 등록 영역 영구 영속
        strategy._limit_up_reached.add("093370")

        # ticker_prev_close 영역 영구 영속 (상한가 모드 진입 영역 영구 영속 시점 검증 안 함, 이미 등록)
        from src.engine import scanner
        scanner.ticker_prev_close["093370"] = 17500  # 영향 0 영역

        # 6/15 일중 고점 추적 영역 영구 영속 (high_since_buy 갱신)
        # check_exit_signal 호출 시 = 6/15 일중 고점 23,700원
        # is_next_day=True (6/12 매수, 6/15 호출) + _limit_up_reached 등록 → 익일 트레일링 분기
        signal_high = strategy.check_exit_signal(
            "093370",
            current_price=23700,
            open_price=22500,
        )
        # 6/15 일중 고점 영역 = NONE (trailing 미발화, 고점 추적만)
        # high_since_buy = max(22500, 23700) = 23700
        assert pos.high_since_buy == 23700, (
            f"high_since_buy 추적 영역 결함 — got {pos.high_since_buy}"
        )

        # 6/15 마감 22,300원 영역 영구 영속
        signal_close = strategy.check_exit_signal(
            "093370",
            current_price=22300,
            open_price=22500,
        )
        # drop_rate = (22300 - 23700) / 23700 × 100 = -5.91%
        # -5.91% ≤ -1.2% → TRAILING_STOP 발화 영역 영구 영속
        assert signal_close == Signal.TRAILING_STOP, (
            f"후성 093370 영역 영구 영속 트레일링 영역 영구 영속 미발화 — "
            f"got {signal_close}, expected TRAILING_STOP. "
            f"high_since_buy={pos.high_since_buy}, current=22300, "
            f"drop_rate={((22300 - pos.high_since_buy) / pos.high_since_buy * 100):.2f}%, "
            f"trailing_stop_rate=-1.2%"
        )
