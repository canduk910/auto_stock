"""사이클 C3 (2026-07-15) — 퀀트 재무 적재 task (관찰 전용) 회귀 가드 (Red).

산출물 (a) scanner `_stock_master_financial_load_once` + (b) scheduler 주1회 task.
매매 로직 diff 0 (관찰 전용 Phase 1). momentum 발사 경로 byte-identical (G-3).

Red 가드 매트릭스:
- LOAD-1 (HIGH): 유니버스 = list_by_filter 재사용 → fetch_all_financials 호출
- LOAD-2: max_stac_yymm 신선도 skip (당분기 이미 적재)
- LOAD-3: graceful — 개별 fetch 예외 → failed++ + 다음 ticker 진행
- LOAD-4: [stock_master_financial_load_summary] emit + summary 키
- LOAD-5: upsert_financial_batch 호출 (fetch 성공 시)
- G-3 (HIGH SAFETY, AST): scan_stocks / subscribe_filtered_stocks 본체 diff 0
- TASKKEY-1: refresh_progress TaskKey / TASK_KEYS 에 "financial" 포함
- SCHED-1 (AST): TIME_STOCK_MASTER_FINANCIAL_LOAD = time(16, 40)
- SCHED-2 (AST): _stock_master_financial_load_task_loop = run_periodic_task_loop 위임
- SCHED-3 (AST, G-AST2): task_attrs 4위치
- ZOMBIE-1: stop tuple 에 _stock_master_financial_load_task 포함

매매 안전성: scanner 16:40 재무 task = 매수 진입 전 (사이클 38). risk/order_engine/realtime diff 0.
freeze_time 미사용 — DB read (list_by_filter / max_stac_yymm / fetch_all_financials) mock (사이클 187 hang 교훈).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCANNER_SRC = _REPO_ROOT / "src" / "engine" / "scanner.py"
_SCHED_SRC = _REPO_ROOT / "src" / "engine" / "scheduler.py"
# refactor-review B1 (2026-08-09) — task loop 본체 data_load_tasks.py 위임 이관.
_DATA_LOAD_SRC = _REPO_ROOT / "src" / "engine" / "data_load_tasks.py"


def _sm_row(ticker: str, *, is_index: bool = False, mcap_eok: int = 1000,
            trade_won: int = 50_000_000_000, name: str = "테스트종목") -> dict:
    """list_by_filter 가 반환하는 stock_master row (index ∪ 자격 유니버스)."""
    return {
        "ticker": ticker,
        "name": name,
        "is_kospi200": is_index,
        "is_kosdaq150": False,
        "raw": {
            "hts_avls": str(mcap_eok),
            "acml_tr_pbmn": str(trade_won),
        },
    }


def _fin_row(ticker: str, stac_yymm: str = "20241231") -> dict:
    """fetch_all_financials 정규화 row (upsert_financial_batch 입력)."""
    return {
        "ticker": ticker,
        "stac_yymm": stac_yymm,
        "div_cls": "0",
        "cptl_ntin_rate": 5.0,
        "lblt_rate": 40.0,
        "raw": {},
    }


# ---------------------------------------------------------------------------
# LOAD-1 (HIGH) — 유니버스 = list_by_filter 재사용 → fetch_all_financials 호출
# ---------------------------------------------------------------------------
class TestFinancialLoadUniverse:
    """LOAD-1: 재무 적재 유니버스 = list_by_filter (index∪자격) 재사용."""

    @pytest.mark.asyncio
    async def test_load_uses_list_by_filter_and_fetches(self):
        load_fn = getattr(scanner, "_stock_master_financial_load_once", None)
        assert load_fn is not None, (
            "scanner._stock_master_financial_load_once 미구현 — C3 (a) 산출물."
        )

        rows = [_sm_row("005930", is_index=True), _sm_row("000660")]

        fetch_mock = AsyncMock(return_value=[_fin_row("005930"), _fin_row("005930", "20231231")])
        upsert_mock = AsyncMock(return_value=2)

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)), \
             patch("src.db.stock_master_financial.max_stac_yymm", new=AsyncMock(return_value=None)), \
             patch("src.api.finance.fetch_all_financials", new=fetch_mock), \
             patch("src.db.stock_master_financial.upsert_financial_batch", new=upsert_mock), \
             patch("src.engine.refresh_progress.start_progress"), \
             patch("src.engine.refresh_progress.update_progress"), \
             patch("src.engine.refresh_progress.finish_progress"), \
             patch("asyncio.sleep", new=AsyncMock()):
            summary = await load_fn()

        # 두 종목 모두 fetch_all_financials 호출
        assert fetch_mock.await_count == 2, (
            f"fetch_all_financials 호출 수 {fetch_mock.await_count} != 2 — "
            "list_by_filter 유니버스 재사용 실패."
        )
        assert summary["total"] == 2


# ---------------------------------------------------------------------------
# LOAD-2 — max_stac_yymm 신선도 skip (당분기 이미 적재)
# ---------------------------------------------------------------------------
class TestFinancialLoadFreshnessSkip:
    """LOAD-2: max_stac_yymm 존재(최신) → skipped++ + fetch 미호출."""

    @pytest.mark.asyncio
    async def test_fresh_ticker_skipped(self):
        load_fn = getattr(scanner, "_stock_master_financial_load_once", None)
        assert load_fn is not None

        rows = [_sm_row("005930", is_index=True)]
        fetch_mock = AsyncMock(return_value=[_fin_row("005930")])

        # max_stac_yymm 이 최신 결산연월 반환 → 신선 → skip
        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)), \
             patch("src.db.stock_master_financial.max_stac_yymm",
                   new=AsyncMock(return_value="20241231")), \
             patch("src.api.finance.fetch_all_financials", new=fetch_mock), \
             patch("src.db.stock_master_financial.upsert_financial_batch", new=AsyncMock(return_value=0)), \
             patch("src.engine.refresh_progress.start_progress"), \
             patch("src.engine.refresh_progress.update_progress"), \
             patch("src.engine.refresh_progress.finish_progress"), \
             patch("asyncio.sleep", new=AsyncMock()):
            summary = await load_fn(force=False)

        assert fetch_mock.await_count == 0, (
            "신선 ticker 는 fetch_all_financials 호출하면 안 됨 (max_stac_yymm skip)."
        )
        assert summary.get("skipped", 0) >= 1, (
            f"skipped 카운터 미증가: {summary}"
        )


# ---------------------------------------------------------------------------
# LOAD-3 — graceful (개별 fetch 예외 → failed++ + 다음 ticker 진행)
# ---------------------------------------------------------------------------
class TestFinancialLoadGraceful:
    """LOAD-3: 개별 ticker fetch 예외 → failed++ + 다음 ticker 계속 (사이클 88)."""

    @pytest.mark.asyncio
    async def test_individual_failure_continues(self):
        load_fn = getattr(scanner, "_stock_master_financial_load_once", None)
        assert load_fn is not None

        rows = [_sm_row("005930", is_index=True), _sm_row("000660", is_index=True)]

        async def _fetch(ticker, div_cls="0"):
            if ticker == "005930":
                raise RuntimeError("KIS SESSION FULL")
            return [_fin_row(ticker)]

        fetch_mock = AsyncMock(side_effect=_fetch)
        upsert_mock = AsyncMock(return_value=1)

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)), \
             patch("src.db.stock_master_financial.max_stac_yymm", new=AsyncMock(return_value=None)), \
             patch("src.api.finance.fetch_all_financials", new=fetch_mock), \
             patch("src.db.stock_master_financial.upsert_financial_batch", new=upsert_mock), \
             patch("src.engine.refresh_progress.start_progress"), \
             patch("src.engine.refresh_progress.update_progress"), \
             patch("src.engine.refresh_progress.finish_progress"), \
             patch("asyncio.sleep", new=AsyncMock()):
            summary = await load_fn()

        assert summary.get("failed", 0) >= 1, (
            f"005930 fetch 예외인데 failed 미증가: {summary}"
        )
        # 두 번째 ticker 는 정상 진행 (fetch 2회 호출)
        assert fetch_mock.await_count == 2, (
            "예외 후 다음 ticker 진행 실패 (graceful continue 미준수)."
        )


# ---------------------------------------------------------------------------
# LOAD-4 — [stock_master_financial_load_summary] emit + summary 키
# ---------------------------------------------------------------------------
class TestFinancialLoadSummary:
    """LOAD-4: summary emit + 필수 키 (total/updated/skipped/failed)."""

    @pytest.mark.asyncio
    async def test_summary_keys_and_emit(self, caplog):
        load_fn = getattr(scanner, "_stock_master_financial_load_once", None)
        assert load_fn is not None

        rows = [_sm_row("005930", is_index=True)]

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)), \
             patch("src.db.stock_master_financial.max_stac_yymm", new=AsyncMock(return_value=None)), \
             patch("src.api.finance.fetch_all_financials",
                   new=AsyncMock(return_value=[_fin_row("005930")])), \
             patch("src.db.stock_master_financial.upsert_financial_batch", new=AsyncMock(return_value=1)), \
             patch("src.engine.refresh_progress.start_progress"), \
             patch("src.engine.refresh_progress.update_progress"), \
             patch("src.engine.refresh_progress.finish_progress"), \
             patch("asyncio.sleep", new=AsyncMock()):
            summary = await load_fn()

        for key in ("total", "updated", "skipped", "failed"):
            assert key in summary, f"summary 키 '{key}' 누락: {summary}"

        # emit 문자열이 소스에 존재해야 함 (운영 가시화)
        src = inspect.getsource(load_fn)
        assert "[stock_master_financial_load_summary]" in src, (
            "summary emit prefix 누락."
        )


# ---------------------------------------------------------------------------
# LOAD-5 — upsert_financial_batch 호출 (fetch 성공 시)
# ---------------------------------------------------------------------------
class TestFinancialLoadUpsert:
    @pytest.mark.asyncio
    async def test_upsert_called_on_fetch_success(self):
        load_fn = getattr(scanner, "_stock_master_financial_load_once", None)
        assert load_fn is not None

        rows = [_sm_row("005930", is_index=True)]
        upsert_mock = AsyncMock(return_value=2)

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)), \
             patch("src.db.stock_master_financial.max_stac_yymm", new=AsyncMock(return_value=None)), \
             patch("src.api.finance.fetch_all_financials",
                   new=AsyncMock(return_value=[_fin_row("005930"), _fin_row("005930", "20231231")])), \
             patch("src.db.stock_master_financial.upsert_financial_batch", new=upsert_mock), \
             patch("src.engine.refresh_progress.start_progress"), \
             patch("src.engine.refresh_progress.update_progress"), \
             patch("src.engine.refresh_progress.finish_progress"), \
             patch("asyncio.sleep", new=AsyncMock()):
            await load_fn()

        assert upsert_mock.await_count == 1, (
            f"upsert_financial_batch 호출 수 {upsert_mock.await_count} != 1"
        )


# ---------------------------------------------------------------------------
# G-3 (HIGH SAFETY, AST) — scan_stocks / subscribe_filtered_stocks 본체 diff 0
# ---------------------------------------------------------------------------
class TestScanStocksUnchangedSafety:
    """G-3: momentum 발사 경로 (scan_stocks / subscribe_filtered_stocks) 에
    재무 스코어가 인젝션되지 않았음 — 검증 +47K 알파 hot path 보호.

    관찰은 오프라인이므로 scan_stocks 에 스코어 훅을 넣지 않는다.
    """

    def _func_source(self, name: str) -> str:
        src = _SCANNER_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return ast.get_source_segment(src, node) or ""
        return ""

    def test_scan_stocks_has_no_quant_score_hook(self):
        body = self._func_source("scan_stocks")
        assert body, "scan_stocks 함수를 찾지 못함."
        for token in (
            "compute_f_score_7", "compute_magic_formula",
            "fetch_all_financials", "get_financial_series",
            "_stock_master_financial_load_once", "quant_score",
        ):
            assert token not in body, (
                f"scan_stocks 본체에 재무 스코어 토큰 '{token}' 인젝션 발견 — "
                "momentum 발사 경로 diff 0 위반 (G-3 SAFETY)."
            )

    def test_subscribe_filtered_stocks_has_no_quant_score_hook(self):
        body = self._func_source("subscribe_filtered_stocks")
        assert body, "subscribe_filtered_stocks 함수를 찾지 못함."
        for token in (
            "compute_f_score_7", "compute_magic_formula",
            "fetch_all_financials", "get_financial_series", "quant_score",
        ):
            assert token not in body, (
                f"subscribe_filtered_stocks 본체에 '{token}' 인젝션 발견 — 구독 발사 경로 diff 0 위반."
            )


# ---------------------------------------------------------------------------
# TASKKEY-1 — refresh_progress TaskKey / TASK_KEYS 에 "financial" 포함
# ---------------------------------------------------------------------------
class TestRefreshProgressFinancialKey:
    def test_task_keys_includes_financial(self):
        from src.engine import refresh_progress as rp

        assert "financial" in rp.TASK_KEYS, (
            f"refresh_progress.TASK_KEYS 에 'financial' 누락: {rp.TASK_KEYS}"
        )
        assert len(rp.TASK_KEYS) == 5, (
            f"TASK_KEYS 개수 {len(rp.TASK_KEYS)} != 5 (universe/basics/daily/master/financial)"
        )

    def test_task_key_literal_source_has_financial(self):
        """Literal + tuple 동행 영속 (사이클 129 AST 패턴 답습)."""
        src = (_REPO_ROOT / "src" / "engine" / "refresh_progress.py").read_text(encoding="utf-8")
        # Literal 정의에 "financial" 존재
        assert '"financial"' in src, "refresh_progress.py 소스에 \"financial\" 문자열 누락."


# ---------------------------------------------------------------------------
# SCHED-1 (AST) — TIME_STOCK_MASTER_FINANCIAL_LOAD = time(16, 40)
# ---------------------------------------------------------------------------
class TestSchedulerFinancialConstant:
    def test_financial_load_time_constant(self):
        from src.engine import scheduler as sched_mod
        from datetime import time as _time

        const = getattr(sched_mod, "TIME_STOCK_MASTER_FINANCIAL_LOAD", None)
        assert const is not None, (
            "scheduler.TIME_STOCK_MASTER_FINANCIAL_LOAD 상수 미정의 — C3 (b) 산출물."
        )
        assert const == _time(16, 40), (
            f"TIME_STOCK_MASTER_FINANCIAL_LOAD {const} != time(16, 40) (master 16:30 후 stagger)."
        )


# ---------------------------------------------------------------------------
# SCHED-2 (AST) — task loop = run_periodic_task_loop 위임 + 168h 게이트 + 900s delay
# ---------------------------------------------------------------------------
class TestSchedulerFinancialTaskLoop:
    def _method_source(self, name: str) -> str:
        # refactor-review B1 — scheduler wrapper(name) + data_load_tasks 본체(name.lstrip("_")) 결합.
        combined = ""
        for path, lookup in ((_SCHED_SRC, name), (_DATA_LOAD_SRC, name.lstrip("_"))):
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == lookup:
                    combined += (ast.get_source_segment(src, node) or "") + "\n"
        return combined

    def test_task_loop_delegates_and_gates(self):
        body = self._method_source("_stock_master_financial_load_task_loop")
        assert body, (
            "_stock_master_financial_load_task_loop 미정의 — C3 (b) 산출물."
        )
        assert "run_periodic_task_loop" in body, (
            "task loop 이 run_periodic_task_loop 위임 안 함."
        )
        assert "_stock_master_financial_load_once" in body, (
            "once_callable 로 _stock_master_financial_load_once 미연결."
        )
        # 주1회 신선도 게이트 (7일 = 168h)
        assert "168" in body or "immediate_skip_if_fresh_hours" in body, (
            "주1회 신선도 게이트 (immediate_skip_if_fresh_hours=168) 누락."
        )
        # master 720 후 stagger
        assert "900" in body, (
            "initial_delay_secs=900 (master 720 후 stagger) 누락."
        )


# ---------------------------------------------------------------------------
# SCHED-3 (AST, G-AST2) — task_attrs 4위치
# ---------------------------------------------------------------------------
class TestSchedulerFinancialTaskAttrs4Sites:
    """사이클 79 G-AST2 — instance create + connect finally + run_daily finally + stop tuple."""

    def _method_source(self, name: str) -> str:
        # refactor-review B1 — scheduler wrapper(name) + data_load_tasks 본체(name.lstrip("_")) 결합.
        combined = ""
        for path, lookup in ((_SCHED_SRC, name), (_DATA_LOAD_SRC, name.lstrip("_"))):
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == lookup:
                    combined += (ast.get_source_segment(src, node) or "") + "\n"
        return combined

    def test_instance_create_in_start(self):
        start_src = self._method_source("start")
        assert "_stock_master_financial_load_task = asyncio.create_task(" in start_src \
            or ("_stock_master_financial_load_task" in start_src
                and "_stock_master_financial_load_task_loop" in start_src), (
            "start() 에 _stock_master_financial_load_task instance create 누락 (위치 1)."
        )

    def test_start_finally_cancel_tuple(self):
        """connect/start finally task cancel tuple (위치 2)."""
        start_src = self._method_source("start")
        # start finally 의 for task_attr tuple 에 포함
        assert start_src.count('"_stock_master_financial_load_task"') >= 1, (
            "start() finally cancel tuple 에 _stock_master_financial_load_task 누락 (위치 2)."
        )

    def test_run_daily_finally_cancel_tuple(self):
        run_daily_src = self._method_source("run_daily")
        assert '"_stock_master_financial_load_task"' in run_daily_src, (
            "run_daily() finally cancel tuple 에 _stock_master_financial_load_task 누락 (위치 3)."
        )

    def test_stop_cancel_tuple(self):
        stop_src = self._method_source("stop")
        assert '"_stock_master_financial_load_task"' in stop_src, (
            "stop() cancel tuple 에 _stock_master_financial_load_task 누락 (위치 4)."
        )


# ---------------------------------------------------------------------------
# ZOMBIE-1 — stop tuple 에 _stock_master_financial_load_task 포함
# (기존 test_scheduler_stop_zombie_tasks.py::expected_members 갱신은 Green 동반)
# ---------------------------------------------------------------------------
class TestZombieStopTupleMembership:
    def test_stop_finally_tuple_symmetry_includes_financial(self):
        from src.engine.scheduler import TradingScheduler

        stop_src = inspect.getsource(TradingScheduler.stop)
        start_src = inspect.getsource(TradingScheduler.start)

        assert '"_stock_master_financial_load_task"' in stop_src, (
            "stop tuple 에 _stock_master_financial_load_task 미포함 — zombie 방지 위반."
        )
        assert '"_stock_master_financial_load_task"' in start_src, (
            "start finally tuple 에 _stock_master_financial_load_task 미포함 — "
            "stop ≡ finally 대칭 위반 (사이클 13-E-3)."
        )
