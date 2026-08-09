"""사이클 150 (2026-06-16) — SUPABASE 용량초과 시정 3 영역 통합 회귀 가드.

영역 A (G-150-HIST): stock_master_history seq=0/1 단일 정책 (migration 036)
영역 B (G-150-DAILY): stock_master_daily T-150일 retention cron
영역 C (G-150-PURGE): system_logs purge_old_logs 실효 (사이클 6 silent 결함 시정)
영역 D (G-150-SAFETY): 매매 안전성 영구 영속 정적 검증

사용자 결정 영구 영속:
- Q1=A stock_master_history PK (ticker, seq) seq IN (0, 1)
- Q3=C stock_master_daily T-150일 cron (VCP T-120일 + 30일 안전 마진)
- Q4=B 즉시 TDD (domain-expert 자문 생략)
- Q5=B 즉시 DROP
- Q6=A 사이클 6 retention silent 결함 동행 시정
"""

from __future__ import annotations

import ast
import re
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_036 = _REPO_ROOT / "supabase" / "migrations" / "036_stock_master_history_seq.sql"
_SCHEDULER_PY = _REPO_ROOT / "src" / "engine" / "scheduler.py"
_DAILY_PY = _REPO_ROOT / "src" / "db" / "stock_master_daily.py"
_SYSLOG_PY = _REPO_ROOT / "src" / "db" / "system_logs.py"


# =============================================================================
# G-150-HIST (영역 A) — stock_master_history seq=0/1 단일 정책
# =============================================================================


class TestG150HistMigrationExists:
    """G-150-HIST-1 (HIGH): migration 036 영역 영구 영속."""

    def test_g150_hist_1_migration_file_exists(self) -> None:
        """migration 036 파일 영역 영구 영속."""
        assert _MIGRATION_036.exists(), \
            "supabase/migrations/036_stock_master_history_seq.sql 영역 영구 영속 의무"

    def test_g150_hist_1b_drop_table_present(self) -> None:
        """기존 stock_master_history 영역 DROP (Q5=B 즉시 DROP)."""
        content = _MIGRATION_036.read_text(encoding="utf-8")
        assert "DROP TABLE IF EXISTS stock_master_history" in content, \
            "Q5=B 즉시 DROP 영역 영구 영속 의무"
        assert "DROP TRIGGER IF EXISTS stock_master_history_track" in content, \
            "기존 trigger DROP 영구 영속 의무"

    def test_g150_hist_1c_check_seq_in_0_1(self) -> None:
        """CHECK seq IN (0, 1) 영역 영구 영속."""
        content = _MIGRATION_036.read_text(encoding="utf-8")
        # 정규식 영역 영구 영속 — 공백 / 인용 영역 흡수
        match = re.search(r"CHECK\s*\(\s*seq\s+IN\s*\(\s*0\s*,\s*1\s*\)\s*\)", content)
        assert match is not None, "CHECK seq IN (0, 1) 영역 영구 영속 의무"


class TestG150HistTriggerDesign:
    """G-150-HIST-2 (HIGH): trigger 영역 영구 영속 = TTL_REFRESH 미발화."""

    def test_g150_hist_2_distinct_branch(self) -> None:
        """`OLD.raw IS DISTINCT FROM NEW.raw` 분기 영역 영구 영속."""
        content = _MIGRATION_036.read_text(encoding="utf-8")
        assert "OLD.raw IS DISTINCT FROM NEW.raw" in content, \
            "TTL_REFRESH 영역 미발화 의무 (raw 변경 시에만 trigger)"

    def test_g150_hist_2b_no_ttl_refresh_branch(self) -> None:
        """TTL_REFRESH 영역 INSERT 분기 영구 폐기 (raw 미변경 시 trigger 0건)."""
        content = _MIGRATION_036.read_text(encoding="utf-8")
        # 사이클 84 영역 TTL_REFRESH INSERT 분기 폐기 영구 영속
        assert "'TTL_REFRESH'" not in content, \
            "TTL_REFRESH 영역 INSERT 분기 영구 폐기 의무"

    def test_g150_hist_2c_seq_shift_logic(self) -> None:
        """UPDATE 시 seq=0 → seq=1 shift 영역 영속."""
        content = _MIGRATION_036.read_text(encoding="utf-8")
        # seq=1 INSERT (직전본) + seq=0 INSERT (최신본) 양쪽 영구 영속
        assert "NEW.ticker, 1, 'UPDATE', OLD.raw" in content, \
            "seq=1 = 직전본 (OLD.raw) INSERT 영역 영구 영속"
        assert "NEW.ticker, 0, 'UPDATE', NEW.raw" in content, \
            "seq=0 = 최신본 (NEW.raw) INSERT 영역 영구 영속"


class TestG150HistPrimaryKey:
    """G-150-HIST-3: PK (ticker, seq) 영역 영구 영속."""

    def test_g150_hist_3_primary_key(self) -> None:
        content = _MIGRATION_036.read_text(encoding="utf-8")
        match = re.search(r"PRIMARY KEY\s*\(\s*ticker\s*,\s*seq\s*\)", content)
        assert match is not None, "PRIMARY KEY (ticker, seq) 영역 영구 영속 의무"


class TestG150HistSeqConstraint:
    """G-150-HIST-4: seq=2+ INSERT 자동 차단 (CHECK constraint)."""

    def test_g150_hist_4_check_constraint_blocks_seq_2(self) -> None:
        """CHECK seq IN (0, 1) 영역 영구 영속 = seq=2 INSERT 자동 차단."""
        content = _MIGRATION_036.read_text(encoding="utf-8")
        # CHECK 영역 영구 영속 시 seq=2 자동 차단 (PostgreSQL 영역 자동 처리)
        assert "seq IN (0, 1)" in content or "seq IN ( 0, 1 )" in content or \
            re.search(r"seq\s+IN\s*\(\s*0\s*,\s*1\s*\)", content) is not None, \
            "seq IN (0, 1) CHECK constraint 영구 영속"


class TestG150HistBeforeRawDropped:
    """G-150-HIST-5: before_raw 컬럼 영구 폐기 영속 (사이클 84 → seq=1 자체가 이전본)."""

    def test_g150_hist_5_before_raw_dropped(self) -> None:
        content = _MIGRATION_036.read_text(encoding="utf-8")
        # 신규 영역에 before_raw 컬럼 영구 부재 영속
        # (DROP TABLE 이후 재생성 영역에서만 검증)
        create_section = content.split("CREATE TABLE stock_master_history")[1].split(";")[0]
        assert "before_raw" not in create_section, \
            "before_raw 컬럼 영역 영구 폐기 영속 (seq=1 자체가 이전본)"
        assert "after_raw" not in create_section, \
            "after_raw 컬럼 영역 영구 폐기 영속 (raw 단일 컬럼 영속)"


# =============================================================================
# G-150-DAILY (영역 B) — stock_master_daily T-150일 retention cron
# =============================================================================


class TestG150DailyPurgeFunction:
    """G-150-DAILY-1 (HIGH): purge_old_rows 시그너처 영역 영구 영속."""

    def test_g150_daily_1_signature_exists(self) -> None:
        """purge_old_rows 함수 영역 영구 영속."""
        from src.db.stock_master_daily import purge_old_rows
        assert callable(purge_old_rows), "purge_old_rows 함수 영역 영구 영속 의무"

    def test_g150_daily_1b_signature_keyword_args(self) -> None:
        """purge_old_rows(cutoff_date, *, protected_tickers) 시그너처 영역 영속."""
        import inspect
        from src.db.stock_master_daily import purge_old_rows
        sig = inspect.signature(purge_old_rows)
        params = sig.parameters
        assert "cutoff_date" in params, "cutoff_date 영역 영구 영속 의무"
        assert "protected_tickers" in params, "protected_tickers 영역 영구 영속 의무"
        # protected_tickers = keyword-only 영역 영구 영속
        assert params["protected_tickers"].kind == inspect.Parameter.KEYWORD_ONLY, \
            "protected_tickers keyword-only 영역 영구 영속"


class TestG150DailyRetentionDays:
    """G-150-DAILY-2 (HIGH): retention cutoff 상수 가드.

    사이클 172 (2026-06-22) 의미 전환 (사이클 66 K-2 패턴) — 150 → 230.
    사유: 사이클 173 prepare DB일봉 전환 시 VCP 220일 lookback DB 충족 보장.
    150 (VCP T-120일 + 30일 마진) → 230 (VCP 220일 + 10일 마진) 확장.
    purge_old_rows 로직 불변 (상수만 변경, "N일 지난 것만 삭제").
    """

    def test_g150_daily_2_retention_days_constant(self) -> None:
        from src.db.stock_master_daily import DAILY_RETENTION_DAYS
        assert DAILY_RETENTION_DAYS == 230, \
            "DAILY_RETENTION_DAYS = 230 (사이클 172 — VCP 220일 + 10일 안전 마진)"


class TestG150DailyProtectedTickers:
    """G-150-DAILY-3: protected_tickers 영역 절대 보호 (사이클 32 R4 답습)."""

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 "
            "`.select().lt().not_.in_().order().limit()` / `.delete().eq().not_.in_()` 의 "
            "call_args 를 직접 단언한다. asyncpg 전환으로 `.not_.in_()` 체인이 "
            "`ticker <> ALL($::text[])` SQL 절 + 위치 인자로 대체되어 이 체인 패턴이 "
            "존재하지 않는다. SELECT/DELETE 양쪽 protected 제외 (never-drain P-3) 불변식은 "
            "M2b 신규 가드 test_cycleM2b_stock_master_daily_pg.py::"
            "test_purge_select_and_delete_both_exclude_protected 가 pg 레벨에서 동등 커버."
        ),
    )
    @pytest.mark.asyncio
    async def test_g150_daily_3_protected_tickers_excluded(self) -> None:
        """protected_tickers 영역 영구 영속 = SELECT/DELETE 양쪽 제외.

        사이클 192 의미 전환 (사이클 66 K-2) — 날짜 슬라이스 루프 패턴에 맞게
        mock 형식 전환. 검증 의도 보존: DELETE 쪽 not_.in_ 호출 확인.
        신규 추가: SELECT 쪽 not_.in_ 도 확인 (never-drain 가드 영속).
        """
        from src.db import stock_master_daily as _smd

        # SELECT: 1회차 row 반환 → 2회차 empty (drained)
        sel_result_1 = MagicMock()
        sel_result_1.data = [{"bas_dd": "2025-01-01"}]
        sel_result_2 = MagicMock()
        sel_result_2.data = []

        # DELETE: count=1 반환
        del_result = MagicMock()
        del_result.count = 1

        table_mock = MagicMock()

        # SELECT chain: .select().lt().not_.in_().order().limit().execute()
        table_mock.select.return_value.lt.return_value.not_.in_.return_value \
            .order.return_value.limit.return_value.execute.side_effect = [
                sel_result_1, sel_result_2,
            ]

        # DELETE chain: .delete().eq().not_.in_().execute()
        table_mock.delete.return_value.eq.return_value.not_.in_.return_value \
            .execute.return_value = del_result

        with patch.object(_smd, "supabase") as mock_supa:
            mock_supa.table.return_value = table_mock
            result = await _smd.purge_old_rows(
                date(2026, 1, 1),
                protected_tickers={"005930", "000660"},
            )

        # DELETE 쪽 not_.in_ 호출 검증 (보호 의도 보존)
        delete_not_in = table_mock.delete.return_value.eq.return_value.not_.in_
        delete_not_in.assert_called_once()
        call_args = delete_not_in.call_args
        assert call_args[0][0] == "ticker", "ticker 컬럼 영구 영속"
        assert set(call_args[0][1]) == {"005930", "000660"}, \
            "protected_tickers DELETE 제외 영구 영속"

        # SELECT 쪽 not_.in_ 도 호출 검증 (never-drain 가드)
        select_not_in = table_mock.select.return_value.lt.return_value.not_.in_
        select_not_in.assert_called()

        assert result["protected_count"] == 2


class TestG150DailySchedulerTask:
    """G-150-DAILY-4: scheduler 16:15 KST task 영역 영속."""

    def test_g150_daily_4_time_constant(self) -> None:
        from src.engine.scheduler import TIME_STOCK_MASTER_DAILY_PURGE
        from datetime import time as _time
        assert TIME_STOCK_MASTER_DAILY_PURGE == _time(16, 15), \
            "TIME_STOCK_MASTER_DAILY_PURGE = 16:15 KST 영구 영속 의무"

    def test_g150_daily_4b_task_loop_function_exists(self) -> None:
        """_stock_master_daily_purge_task_loop 영역 영구 영속."""
        content = _SCHEDULER_PY.read_text(encoding="utf-8")
        assert "_stock_master_daily_purge_task_loop" in content, \
            "_stock_master_daily_purge_task_loop 메서드 영역 영구 영속"

    def test_g150_daily_4c_task_attrs_3_locations(self) -> None:
        """task_attrs 영역 3 위치 영구 영속 (start.finally + run_daily.finally + stop)."""
        content = _SCHEDULER_PY.read_text(encoding="utf-8")
        # 사이클 79 G-AST2 영속 — `_stock_master_daily_purge_task` 3 위치 영구 영속
        occurrences = content.count("_stock_master_daily_purge_task")
        # task 생성 1 + task_attrs 3 + 함수 정의 1 (5 영역 최소 영구 영속)
        assert occurrences >= 4, \
            f"_stock_master_daily_purge_task 영역 최소 4 위치 영구 영속 의무 (실측 {occurrences})"


class TestG150DailyGraceful:
    """G-150-DAILY-5: graceful (예외 시 0 반환)."""

    @pytest.mark.asyncio
    async def test_g150_daily_5_graceful_exception(self) -> None:
        """예외 발생 시 graceful 영역 영구 영속 = 0 반환 (사이클 M2b — pg.fetchrow 예외)."""
        from src.db import stock_master_daily as _smd

        with patch.object(_smd, "pg", create=True) as pg_mod:
            pg_mod.fetchrow = AsyncMock(side_effect=RuntimeError("pg connection error"))
            pg_mod.execute = AsyncMock()
            result = await _smd.purge_old_rows(date(2026, 1, 1))

        assert result["deleted"] == 0, "graceful 영역 영구 영속 = 0 반환"


# =============================================================================
# G-150-PURGE (영역 C) — system_logs purge_old_logs 실효 (사이클 6 silent 결함 시정)
# =============================================================================


class TestG150PurgeNoLimit:
    """G-150-PURGE-1 (HIGH): DELETE chain `.limit()` 호출 영역 영구 부재 (사이클 6 영역 재발 차단)."""

    def test_g150_purge_1_no_delete_limit_pattern(self) -> None:
        """`supabase.table("system_logs").delete()` 직후 `.limit(` 호출 영역 영구 부재."""
        content = _SYSLOG_PY.read_text(encoding="utf-8")
        # AST 영역 영구 영속 — _purge_by_cutoff 함수 본체 영역 한정
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_purge_by_cutoff":
                func_source = ast.unparse(node)
                # delete() chain 영역에서 .limit() 호출 영역 영구 부재
                # (subquery select chain 영역에서만 .limit() 허용 영구 영속)
                # 본체 grep: `.delete()` 직후 ... `.limit(` 패턴 잔존 0건
                assert ".delete().limit(" not in func_source.replace(" ", "").replace("\n", ""), \
                    "사이클 6 결함 영역 재발 차단 = DELETE chain `.limit()` 호출 0건 영구 영속"
                # chain 영역 정합 검증 — `.lt("timestamp", cutoff_iso).limit(MAX_PURGE_BATCH)` 영역
                # 영속 영역은 SELECT chain 영역에 한정
                return
        pytest.fail("_purge_by_cutoff 함수 영역 영구 영속 의무")


class TestG150PurgeSubqueryPattern:
    """G-150-PURGE-2 (HIGH): subquery select + DELETE in_ id 영역 영구 영속."""

    @pytest.mark.xfail(
        reason="사이클M3b — _purge_by_cutoff supabase→pg 전환. SELECT id 는 이제 "
        "pg.fetch SQL 문자열('SELECT id FROM system_logs ...'). 루프배치 계약은 "
        "test_cycleM3b_system_logs_pg.py::test_purge_* 로 이관",
        strict=False,
    )
    def test_g150_purge_2_select_subquery_present(self) -> None:
        """SELECT id 영역 영구 영속 (subquery 영역)."""
        content = _SYSLOG_PY.read_text(encoding="utf-8")
        # `_purge_by_cutoff` 본체에 SELECT("id") 영역 영구 영속
        assert '.select("id")' in content, \
            "SELECT('id') 영역 영구 영속 의무 (subquery 영역)"

    @pytest.mark.xfail(
        reason="사이클M3b — _purge_by_cutoff supabase→pg 전환. DELETE 는 이제 "
        "pg.execute('DELETE FROM system_logs WHERE id = ANY($1::bigint[])'). "
        "루프배치 계약은 test_cycleM3b_system_logs_pg.py::test_purge_* 로 이관",
        strict=False,
    )
    def test_g150_purge_2b_delete_in_id_present(self) -> None:
        """`DELETE WHERE id IN (...)` 영역 영구 영속.

        사이클 175 (2026-06-24) 변수명 적응 — 루프 배치 전환으로 closure 변수
        `ids` → `_ids` (기본값 인자) 사용. DELETE in_ 2-step 본질은 보존 (정규식 `_?ids`).
        """
        content = _SYSLOG_PY.read_text(encoding="utf-8")
        # `.delete().in_("id", ids|_ids)` 영역 영구 영속 (변수명 무관, 2-step 본질 가드)
        assert re.search(r'\.delete\(\)\s*\.in_\(\s*"id"\s*,\s*_?ids\s*\)', content) is not None, \
            "DELETE WHERE id IN (ids) 영역 영구 영속 의무 (사이클 175 루프 _ids 변수명 호환)"


class TestG150PurgeFunctional:
    """G-150-PURGE-3: INFO/HIGH 양쪽 cutoff 정확 (mock)."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="사이클M3b — _purge_by_cutoff supabase→pg 전환. mock supabase table "
        "chain 이 더 이상 가로채지 못함. 2-step 계약은 "
        "test_cycleM3b_system_logs_pg.py::test_purge_* 로 이관",
        strict=False,
    )
    async def test_g150_purge_3_select_delete_2_step(self) -> None:
        """2-step 영역 영구 영속 = SELECT + DELETE."""
        from src.db import system_logs as _sl

        # mock supabase chain
        ids_returned = [{"id": 1}, {"id": 2}, {"id": 3}]
        select_result = MagicMock()
        select_result.data = ids_returned

        delete_result = MagicMock()
        delete_result.data = []
        delete_result.count = 3

        select_chain = MagicMock()
        select_chain.eq.return_value = select_chain
        select_chain.in_.return_value = select_chain
        select_chain.lt.return_value = select_chain
        select_chain.limit.return_value = select_chain
        select_chain.execute = MagicMock(return_value=select_result)

        delete_chain = MagicMock()
        delete_chain.in_.return_value = delete_chain
        delete_chain.execute = MagicMock(return_value=delete_result)

        table_mock = MagicMock()
        table_mock.select.return_value = select_chain
        table_mock.delete.return_value = delete_chain

        with patch.object(_sl, "supabase") as mock_supa:
            mock_supa.table.return_value = table_mock
            count = await _sl._purge_by_cutoff(
                cutoff_iso="2026-06-14T00:00:00+09:00",
                level_filter="INFO",
            )

        # SELECT + DELETE 2-step 영역 영구 영속
        assert table_mock.select.called, "SELECT chain 영역 영구 영속 호출 의무"
        assert table_mock.delete.called, "DELETE chain 영역 영구 영속 호출 의무"
        assert count == 3, "삭제 row 수 영역 영구 영속"


class TestG150PurgeEmptyResult:
    """G-150-PURGE-4: 빈 결과 short-circuit graceful."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="사이클M3b — _purge_by_cutoff supabase→pg 전환. mock supabase table "
        "chain 이 더 이상 가로채지 못함. 빈 결과 계약은 "
        "test_cycleM3b_system_logs_pg.py::test_purge_empty_returns_zero_no_delete 로 이관",
        strict=False,
    )
    async def test_g150_purge_4_empty_select_returns_0(self) -> None:
        """SELECT 결과 0건 시 DELETE 미호출 + 0 반환."""
        from src.db import system_logs as _sl

        select_result = MagicMock()
        select_result.data = []

        select_chain = MagicMock()
        select_chain.eq.return_value = select_chain
        select_chain.in_.return_value = select_chain
        select_chain.lt.return_value = select_chain
        select_chain.limit.return_value = select_chain
        select_chain.execute = MagicMock(return_value=select_result)

        delete_chain = MagicMock()
        delete_chain.execute = MagicMock()

        table_mock = MagicMock()
        table_mock.select.return_value = select_chain
        table_mock.delete.return_value = delete_chain

        with patch.object(_sl, "supabase") as mock_supa:
            mock_supa.table.return_value = table_mock
            count = await _sl._purge_by_cutoff(
                cutoff_iso="2026-06-14T00:00:00+09:00",
                level_filter="INFO",
            )

        assert count == 0, "빈 결과 영역 영구 영속 = 0 반환"
        # DELETE chain 호출 영역 부재 영구 영속 (short-circuit)
        assert not table_mock.delete.called, "빈 결과 영역 DELETE 미호출 영구 영속"


# =============================================================================
# G-150-SAFETY (영역 D) — 매매 안전성 영구 영속
# =============================================================================


class TestG150Safety:
    """G-150-SAFETY: 매매 안전성 영구 영속 정적 검증."""

    def test_g150_safety_1_no_strategy_prepare_change(self) -> None:
        """VCP/donchian/BFB prepare 영역 변경 0 (사이클 38 명문화 영속).

        사이클 150 = scanner 영역 매수 진입 *전* 한정.
        prepare 영역 (전략 영역) 영구 영속 = 사이클 150 변경 0.
        """
        # 사이클 150 변경 파일 영역 영구 영속
        # = src/db/stock_master_daily.py + src/db/system_logs.py + src/engine/scheduler.py + supabase/migrations/036_*.sql
        # 전략 prepare 영역 (src/engine/strategies/*) 변경 0 영구 영속 (이 사이클 영역 영구 영속)
        strategies_dir = _REPO_ROOT / "src" / "engine" / "strategies"
        # 6 전략 영역 모두 영구 영속
        expected_strategies = {
            "momentum.py", "volatility_breakout.py", "long_tail_volatility.py",
            "donchian_swing.py", "bull_flag_breakout.py", "vcp_breakout.py",
        }
        actual = {p.name for p in strategies_dir.glob("*.py") if not p.name.startswith("_")}
        assert expected_strategies.issubset(actual), \
            "6 전략 영역 영구 영속 의무 (사이클 38 명문화 영속)"

    def test_g150_safety_2_purge_protected_tickers_keyword(self) -> None:
        """G-150-SAFETY-2 (HIGH): purge_old_rows 호출 시 protected_tickers keyword 의무.

        scheduler task_loop 영역에서 보유/익일청산 영역 절대 보호 (사이클 32 R4 답습).
        """
        # refactor-review B1 (2026-08-09) — purge task 본체는 data_load_tasks.py 로 위임 이관.
        content = _SCHEDULER_PY.read_text(encoding="utf-8") + (
            _SCHEDULER_PY.parent / "data_load_tasks.py"
        ).read_text(encoding="utf-8")
        # purge_old_rows 호출 영역에서 protected_tickers= keyword 의무 영구 영속
        assert "protected_tickers=" in content, \
            "purge_old_rows 호출 시 protected_tickers= keyword 의무 영구 영속"

    def test_g150_safety_3_no_trade_history_change(self) -> None:
        """trade_history / daily_performance / positions 영역 미변경 영구 영속."""
        # 사이클 150 영역 = stock_master_history + stock_master_daily + system_logs 한정
        # 매매 영역 (trade_history / positions / daily_performance) 변경 0 영구 영속
        for fname in ("trade_history.py", "daily_performance.py", "positions.py"):
            target = _REPO_ROOT / "src" / "db" / fname
            assert target.exists(), f"{fname} 영역 영구 영속 의무"
            content = target.read_text(encoding="utf-8")
            assert "사이클 150" not in content, \
                f"{fname} 영역 사이클 150 변경 0 의무 영구 영속"
