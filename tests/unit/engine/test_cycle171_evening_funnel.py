"""사이클 171 — 저녁 16:20 잠정 funnel 캡처 + capture 헬퍼 3 호출처 정합 회귀 가드.

배경 (자문 cycle171_master_funnel_timing_redesign.md 의제 4 우선순위 2 + 의제 6 (a)):
- capture_funnel_snapshots(registry, *, is_provisional) 공통 헬퍼 추출 (3 호출처 공유).
- 09:30 자동 (False) + 16:20 저녁 (True) + 수동 trigger (False).
- 16:20 task = run_periodic_task_loop 답습 + 16:00 일봉 적재 완료 대기 (count_all 폴링).

회귀 가드:
- G-171-CAP-1: capture_funnel_snapshots 헬퍼 존재 (registry + is_provisional 인자)
- G-171-CAP-2: 헬퍼가 단계별 + step_no=99 insert_snapshot 호출 (09:30 행위 보존)
- G-171-CAP-3: is_provisional 전파 (True/False 그대로 insert_snapshot 동행)
- G-171-CAP-4: _auto_capture_funnel_snapshots 가 헬퍼 위임 (is_provisional=False)
- G-171-EVE-1: TIME_EVENING_FUNNEL_CAPTURE == time(16, 20)
- G-171-EVE-2: 16:20 task 가 prepare → capture(is_provisional=True) 호출
- G-171-EVE-3: 일봉 미적재 시 count_all 폴링 대기 (사이클 163 패턴)
- G-171-EVE-4: task_attrs 4 위치 (_evening_funnel_capture_task)
- G-171-SAFETY-1 (HIGH): check_exit_signal / check_buy_signal funnel hook 0건
- G-171-SAFETY-2 (HIGH): risk / order_engine / realtime / auth import 0
"""

from __future__ import annotations

import ast
import inspect
from datetime import date, time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.ast._ast_helpers import (
    count_function_calls_in_node,
    find_function_def,
    read_module_source,
)

pytestmark = pytest.mark.unit

_SCHEDULER_PY = Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
_REPO = Path(__file__).resolve().parents[3]


# ──────────────────────────────────────────────────────────────────────
# capture_funnel_snapshots 공통 헬퍼
# ──────────────────────────────────────────────────────────────────────


def _make_strategy(sid: str, funnel_steps: list[dict], scanned: list[str]):
    strat = MagicMock()
    strat.strategy_id = sid
    strat._funnel_steps = funnel_steps
    strat.get_scanned_tickers = MagicMock(return_value=scanned)
    return strat


def _make_registry(strategies):
    reg = MagicMock()
    reg.all = MagicMock(return_value=strategies)
    return reg


class TestCaptureHelper:
    """capture_funnel_snapshots 공통 헬퍼 — 3 호출처 공유."""

    def test_g_171_cap_1_helper_exists(self):
        """G-171-CAP-1: capture_funnel_snapshots 헬퍼 존재 + registry/is_provisional 인자."""
        from src.engine import scheduler as sched_mod

        fn = getattr(sched_mod, "capture_funnel_snapshots", None)
        assert fn is not None, "capture_funnel_snapshots 헬퍼 부재 (사이클 171)"
        sig = inspect.signature(fn)
        assert "registry" in sig.parameters
        assert "is_provisional" in sig.parameters

    @pytest.mark.asyncio
    async def test_g_171_cap_2_step_and_final_insert(self, monkeypatch):
        """G-171-CAP-2: 단계별 + step_no=99 insert_snapshot 호출 (09:30 행위 보존)."""
        from src.engine import scheduler as sched_mod
        from src.db import strategy_funnel as sf_mod

        strat = _make_strategy(
            "bull_flag_breakout",
            funnel_steps=[
                {
                    "step_no": 2, "step_name": "유니버스 필터",
                    "survived": [{"ticker": "005930", "name": "삼성전자"}],
                    "survived_count": 1, "excluded": [], "excluded_count": 0,
                    "step_conditions": "BFB: 시총 ≥ 500억",
                },
            ],
            scanned=["005930"],
        )
        captured: list = []

        async def _fake_insert(**kwargs):
            captured.append(kwargs)
            return {"id": f"row-{kwargs['step_no']}"}

        monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

        await sched_mod.capture_funnel_snapshots(
            _make_registry([strat]), is_provisional=False
        )

        step_nos = sorted(c["step_no"] for c in captured)
        assert 2 in step_nos, "단계별 (step_no=2) insert 누락"
        assert 99 in step_nos, "최종 (step_no=99) insert 누락 (사이클 34 호환)"

    @pytest.mark.asyncio
    async def test_g_171_cap_3_provisional_propagated(self, monkeypatch):
        """G-171-CAP-3: is_provisional=True 전파 (모든 insert_snapshot 호출 동행)."""
        from src.engine import scheduler as sched_mod
        from src.db import strategy_funnel as sf_mod

        strat = _make_strategy(
            "donchian_swing",
            funnel_steps=[
                {
                    "step_no": 1, "step_name": "코스피200+코스닥150",
                    "survived": ["005930"], "survived_count": 1,
                    "excluded": [], "excluded_count": 0,
                },
            ],
            scanned=["005930"],
        )
        captured: list = []

        async def _fake_insert(**kwargs):
            captured.append(kwargs)
            return {"id": "x"}

        monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

        await sched_mod.capture_funnel_snapshots(
            _make_registry([strat]), is_provisional=True
        )

        assert captured, "insert 호출 0건"
        assert all(c.get("is_provisional") is True for c in captured), (
            "is_provisional=True 전파 누락"
        )

    def test_g_171_cap_4_auto_delegates_to_helper(self):
        """G-171-CAP-4: _auto_capture_funnel_snapshots 가 헬퍼 위임 (AST).

        주의: 메서드명 `_auto_capture_funnel_snapshots` 자체가 substring 으로
        `capture_funnel_snapshots` 를 포함하므로, *호출* (Call) 발생 횟수로 검증.
        """
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_auto_capture_funnel_snapshots")
        assert node is not None
        calls = count_function_calls_in_node(node, "capture_funnel_snapshots")
        assert calls >= 1, (
            "_auto_capture_funnel_snapshots 가 capture_funnel_snapshots 헬퍼 호출 안 함"
        )


# ──────────────────────────────────────────────────────────────────────
# 16:20 저녁 task
# ──────────────────────────────────────────────────────────────────────


class TestEveningTask:
    """16:20 저녁 잠정 funnel 캡처 task."""

    def test_g_171_eve_1_time_constant(self):
        """G-171-EVE-1: TIME_EVENING_FUNNEL_CAPTURE == time(16, 20)."""
        from src.engine import scheduler as sched_mod

        assert hasattr(sched_mod, "TIME_EVENING_FUNNEL_CAPTURE"), (
            "TIME_EVENING_FUNNEL_CAPTURE 상수 부재"
        )
        assert sched_mod.TIME_EVENING_FUNNEL_CAPTURE == time(16, 20)

    def test_g_171_eve_2_task_loop_method_exists(self):
        """G-171-EVE-2: _evening_funnel_capture_task_loop 메서드 + run_periodic_task_loop 답습."""
        from src.engine.scheduler import TradingScheduler

        assert hasattr(TradingScheduler, "_evening_funnel_capture_task_loop")
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "_evening_funnel_capture_task_loop")
        assert node is not None
        wrapper_body = ast.unparse(node)
        assert "TIME_EVENING_FUNNEL_CAPTURE" in wrapper_body
        # [의미 전환 refactor-review B1] 본체는 data_load_tasks 로 위임 이관 —
        # wrapper 는 wait_time=TIME_ 전달, run_periodic_task_loop 위임은 본체에서 확인.
        dlt_src = read_module_source(_SCHEDULER_PY.parent / "data_load_tasks.py")
        dlt_node = find_function_def(dlt_src, "evening_funnel_capture_task_loop")
        assert dlt_node is not None, "data_load_tasks.evening_funnel_capture_task_loop 부재 (B1)"
        assert "run_periodic_task_loop" in ast.unparse(dlt_node), (
            "evening_funnel_capture_task_loop run_periodic_task_loop 답습 의무"
        )

    @pytest.mark.asyncio
    async def test_g_171_eve_2b_once_prepares_and_captures_provisional(self):
        """G-171-EVE-2b: once 본체가 prepare → capture(is_provisional=True) 호출."""
        from src.engine.scheduler import TradingScheduler

        strat = MagicMock()
        strat.strategy_id = "volatility_breakout"
        strat.prepare = AsyncMock()
        strat._funnel_steps = []
        strat.get_scanned_tickers = MagicMock(return_value=[])

        sched = TradingScheduler.__new__(TradingScheduler)
        sched.registry = _make_registry([strat])

        capture_mock = AsyncMock()
        with patch("src.engine.scheduler.capture_funnel_snapshots", capture_mock), \
             patch("src.db.stock_master_daily.count_all", AsyncMock(return_value=2768)):
            # once 본체 직접 호출 (run_periodic_task_loop once_callable)
            once = sched._evening_funnel_capture_once
            await once()

        strat.prepare.assert_awaited()
        capture_mock.assert_awaited()
        # is_provisional=True 전달 검증
        _, kwargs = capture_mock.call_args
        assert kwargs.get("is_provisional") is True, (
            "저녁 capture 는 is_provisional=True 의무"
        )

    @pytest.mark.asyncio
    async def test_g_171_eve_3_waits_for_daily_load(self):
        """G-171-EVE-3: 일봉 미적재(count_all=0) 시 폴링 대기 (사이클 163 패턴)."""
        from src.engine.scheduler import TradingScheduler

        strat = MagicMock()
        strat.strategy_id = "vcp_breakout"
        strat.prepare = AsyncMock()
        strat._funnel_steps = []
        strat.get_scanned_tickers = MagicMock(return_value=[])

        sched = TradingScheduler.__new__(TradingScheduler)
        sched.registry = _make_registry([strat])

        # count_all: 처음 0 (대기) → 이후 2768 (진입)
        count_seq = AsyncMock(side_effect=[0, 0, 2768])
        sleep_mock = AsyncMock()

        with patch("src.engine.scheduler.capture_funnel_snapshots", AsyncMock()), \
             patch("src.db.stock_master_daily.count_all", count_seq), \
             patch("src.engine.scheduler.asyncio.sleep", sleep_mock):
            await sched._evening_funnel_capture_once()

        # count_all 0 동안 sleep 발화 (폴링 대기)
        assert sleep_mock.await_count >= 1, "일봉 미적재 시 폴링 대기 누락"
        # 최종 진입 후 prepare 발화
        strat.prepare.assert_awaited()

    def test_g_171_eve_4_task_attrs_4_sites(self):
        """G-171-EVE-4: task_attrs 4 위치 (_evening_funnel_capture_task).

        사이클 79 G-AST2 = instance(create_task 1) + 3 cancel 튜플 (start finally /
        run_daily finally / stop). 식별자 `_evening_funnel_capture_task` 총 4회 이상.
        """
        source = read_module_source(_SCHEDULER_PY)
        # create_task 할당 (bare) 1 + cancel 튜플 quoted 3
        bare_cnt = source.count("_evening_funnel_capture_task")
        quoted_cnt = source.count('"_evening_funnel_capture_task"')
        assert quoted_cnt >= 3, (
            f"_evening_funnel_capture_task cancel 튜플 3 위치 미달 (실측 quoted {quoted_cnt})"
        )
        assert bare_cnt >= 4, (
            f"_evening_funnel_capture_task task_attrs 4 위치 미달 (실측 {bare_cnt}, "
            "사이클 79 G-AST2 = create_task 1 + cancel 튜플 3)"
        )


# ──────────────────────────────────────────────────────────────────────
# SAFETY — 매매 hot path 무영향
# ──────────────────────────────────────────────────────────────────────


class TestSafety:
    """관찰성 한정 — 매매 hot path diff 0."""

    def test_g_171_safety_1_no_funnel_hook_in_exit_buy(self):
        """G-171-SAFETY-1 (HIGH): check_exit_signal / check_buy_signal funnel hook 0건."""
        strat_dir = _REPO / "src" / "engine" / "strategies"
        violations = []
        for py in strat_dir.glob("*.py"):
            source = py.read_text(encoding="utf-8")
            for fn_name in ("check_exit_signal", "check_buy_signal"):
                node = find_function_def(source, fn_name)
                if node is None:
                    continue
                # funnel 캡처 호출 0건 (사이클 143/170 영속)
                for hook in ("_record_funnel_step", "_record_funnel_pipeline_step",
                             "capture_funnel_snapshots", "insert_snapshot"):
                    if count_function_calls_in_node(node, hook) > 0:
                        violations.append(f"{py.name}::{fn_name} → {hook}")
        assert not violations, f"check_exit/buy funnel hook 적재 금지 위반: {violations}"

    def test_g_171_safety_2_capture_no_trading_imports(self):
        """G-171-SAFETY-2 (HIGH): capture 헬퍼 영역 risk/order_engine/realtime/auth import 0."""
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "capture_funnel_snapshots")
        assert node is not None
        body = ast.unparse(node)
        for forbidden in ("risk", "order_engine", "realtime", "auth", "execute_buy",
                          "execute_sell", "place_order"):
            assert forbidden not in body, (
                f"capture_funnel_snapshots 영역 매매 hot path '{forbidden}' 참조 금지"
            )
