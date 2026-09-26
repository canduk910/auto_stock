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
- G-171-EVE-1: TIME_EVENING_FUNNEL_CAPTURE == time(21, 0)  (🔁 cycle364 개정 — 16:20 → 21:00, A1 저녁 미리보기)
- G-171-EVE-2: 16:20 task 가 prepare → capture(is_provisional=True) 호출
- G-171-EVE-3: 🔁 cycle364 개정 — 저녁 경로는 20:30 일봉 적재 **성공 마커**를 30초 간격으로 기다린다
  (`count_all() > 0` 은 빈 테이블만 막을 뿐 그날 적재를 기다리지 않는다 — F-D8-a · 설계 §2.4 · M5)
- G-171-EVE-4: task_attrs 4 위치 (_evening_funnel_capture_task)
- G-171-SAFETY-1 (HIGH): check_exit_signal / check_buy_signal funnel hook 0건
- G-171-SAFETY-2 (HIGH): risk / order_engine / realtime / auth import 0
"""

from __future__ import annotations

import ast
import inspect
from datetime import date, datetime, time, timedelta, timezone
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
        """G-171-EVE-1: TIME_EVENING_FUNNEL_CAPTURE == time(21, 0).

        🔁 cycle364 의도적 개정(설계 `_workspace/domain_consult/cycle364_a1_as_of_design.md`
        §2.4 · 사용자 결정 카드2 (가)) — 16:20 은 20:30 일봉 적재 **앞**이라 전략의 오늘봉 절단과
        겹쳐 D-1 목록만 만들 수 있었다. A1 은 적재(20:30) 뒤 · 토큰 체인(20:45~20:51) 뒤 ·
        정산(21:30) 전인 21:00 에 다음 거래일 미리보기를 만든다.
        """
        from src.engine import scheduler as sched_mod

        assert hasattr(sched_mod, "TIME_EVENING_FUNNEL_CAPTURE"), (
            "TIME_EVENING_FUNNEL_CAPTURE 상수 부재"
        )
        assert sched_mod.TIME_EVENING_FUNNEL_CAPTURE == time(21, 0)

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
    async def test_g_171_eve_2b_once_prepares_and_captures_provisional(self, monkeypatch):
        """G-171-EVE-2b: once 본체가 prepare → capture(is_provisional=True) 호출.

        🔁 cycle364 개정 — 벽시계 제거(21:00 고정) + 저녁 경로 계약: 준비 = `prepare(as_of=다음
        거래일)` · 캡처 라벨 = 그 as_of · 잠정. 종전 단언(「capture 가 is_provisional=True 로
        불린다」)의 의도는 그대로 — 저녁 캡처는 여전히 잠정이다.
        """
        from freezegun import freeze_time

        from src.engine.scheduler import TradingScheduler

        async def _cal(d):
            return d.weekday() < 5

        monkeypatch.setattr("src.engine.trading_calendar._lookup_open", _cal)
        monkeypatch.setattr(
            "src.db.system_config.get_task_last_success",
            AsyncMock(return_value="2026-09-22T20:32:10+09:00"),
        )
        inserts: list = []

        async def _insert(**kw):
            inserts.append(kw)
            return {"id": "x"}

        monkeypatch.setattr("src.db.strategy_funnel.insert_snapshot", _insert)
        monkeypatch.setattr("src.db.stock_master_daily.count_all", AsyncMock(return_value=2768))

        strat = MagicMock()
        strat.strategy_id = "volatility_breakout"
        strat.prepare = AsyncMock()
        strat._funnel_steps = []
        strat.get_scanned_tickers = MagicMock(return_value=[])

        sched = TradingScheduler.__new__(TradingScheduler)
        sched.registry = _make_registry([strat])
        sched._pending_next_day_clear = set()

        with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True):
            await sched._evening_funnel_capture_once()

        strat.prepare.assert_awaited()
        assert strat.prepare.await_args.kwargs.get("as_of") == date(2026, 9, 23), (
            "저녁 준비는 prepare(as_of=다음 거래일)"
        )
        assert inserts, "저녁 캡처가 한 행도 쓰지 않았다"
        assert all(kw.get("is_provisional") is True for kw in inserts), (
            "저녁 capture 는 is_provisional=True 의무"
        )
        assert {kw["target_date"] for kw in inserts} == {date(2026, 9, 23)}

    @pytest.mark.asyncio
    async def test_g_171_eve_3_waits_for_daily_load(self, monkeypatch):
        """G-171-EVE-3: 🔁 cycle364 개정 — 20:30 일봉 적재 **성공 마커**를 30초 간격으로 기다린다.

        종전(사이클 163 패턴 `count_all()` 폴링)은 빈 테이블만 막고 그날 적재 완료를 기다리지
        않았다(F-D8-a). 의도(「적재 전에 준비하지 않는다」)는 같고 신호만 정확해졌다 — 설계 §2.4.
        """
        import asyncio as _asyncio

        from freezegun import freeze_time

        from src.engine.scheduler import TradingScheduler

        kst = timezone(timedelta(hours=9))

        async def _cal(d):
            return d.weekday() < 5

        monkeypatch.setattr("src.engine.trading_calendar._lookup_open", _cal)

        async def _marker(label):
            if datetime.now(kst) >= datetime(2026, 9, 22, 21, 1, tzinfo=kst):
                return "2026-09-22T21:00:50+09:00"
            return "2026-09-21T20:32:10+09:00"

        monkeypatch.setattr("src.db.system_config.get_task_last_success", _marker)
        monkeypatch.setattr("src.db.strategy_funnel.insert_snapshot", AsyncMock(return_value={"id": "x"}))
        # 🔴 count_all 이 참이어도 마커가 오늘 20:30 이상이 될 때까지는 준비하지 않는다(M5)
        monkeypatch.setattr("src.db.stock_master_daily.count_all", AsyncMock(return_value=2768))

        strat = MagicMock()
        strat.strategy_id = "vcp_breakout"
        strat.prepare = AsyncMock()
        strat._funnel_steps = []
        strat.get_scanned_tickers = MagicMock(return_value=[])

        sched = TradingScheduler.__new__(TradingScheduler)
        sched.registry = _make_registry([strat])
        sched._pending_next_day_clear = set()

        orig_sleep = _asyncio.sleep
        sleeps: list = []

        with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
            async def _fake_sleep(secs, *a, **k):
                sleeps.append(secs)
                fz.tick(timedelta(seconds=float(secs)))
                await orig_sleep(0)

            monkeypatch.setattr(_asyncio, "sleep", _fake_sleep)
            try:
                import src.engine.funnel_capture as _fc

                monkeypatch.setattr(_fc, "_sleep", _fake_sleep, raising=False)
            except ImportError:
                pass
            await sched._evening_funnel_capture_once()

        assert sleeps and set(sleeps) == {30}, f"적재 마커 대기 = 30초 폴링 (실측 {sleeps})"
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
