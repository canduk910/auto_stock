"""사이클 M1-2 (Red) — src/db/backtest_runs.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, 증분 2).

현행 backtest_runs.py = supabase-py 체인. 이 증분 = `pg.*` 전환.

핵심 계약:
- insert_run → 사전 중복 SELECT 존재 시 None + INSERT ... RETURNING (params_snapshot JSONB).
  복합 UNIQUE (target_date, strategy_id, params_kind) — 충돌 시 None. params_kind 검증 ValueError 보존.
- get_by_id / list_by_date → SELECT.
- update_status → UPDATE ... SET (metrics JSONB, completed_at datetime) WHERE id → dict | {}. status 검증.

Red 유효성: production 미변경 → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# insert_run — 사전 중복 SELECT + INSERT (params_snapshot JSONB) + created_at datetime
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insert_run_uses_pg_insert_returning():
    """insert_run → 중복 없으면 INSERT INTO backtest_runs RETURNING → dict 반환."""
    from src.db import backtest_runs

    inserted = {"id": "uuid-1", "strategy_id": "momentum", "status": "queued"}
    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])  # 사전 중복 조회 = 없음
        pg_mod.fetchrow = AsyncMock(return_value=inserted)
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        out = await backtest_runs.insert_run(
            date(2026, 7, 16), "momentum", "current", {"k_value": 1.3}
        )

    assert out == inserted, "insert_run → 삽입 dict 반환 계약."
    all_sql = _collect_sql(pg_mod)
    assert any("INSERT INTO backtest_runs" in s for s in all_sql), (
        "INSERT INTO backtest_runs SQL 누락."
    )
    args = _insert_args(pg_mod)
    assert "momentum" in args and "current" in args, "strategy_id/params_kind 바인딩 누락."
    assert _has_jsonb_binding(args, {"k_value": 1.3}), "params_snapshot JSONB 바인딩 누락."
    assert any(isinstance(a, datetime) for a in args), (
        "created_at 은 datetime 바인딩 (fromisoformat(now_kst_iso())) — str 금지."
    )


@pytest.mark.asyncio
async def test_insert_run_invalid_params_kind_raises():
    """params_kind ∉ {current, recommended} → ValueError (본체 검증 보존)."""
    from src.db import backtest_runs

    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        with pytest.raises(ValueError):
            await backtest_runs.insert_run(
                date(2026, 7, 16), "momentum", "invalid_kind", {}
            )


@pytest.mark.asyncio
async def test_insert_run_existing_duplicate_returns_none():
    """사전 중복 SELECT 존재 시 None (멱등, INSERT 미발화)."""
    from src.db import backtest_runs

    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"id": "existing"}])  # 이미 존재
        pg_mod.fetchrow = AsyncMock(return_value={"id": "should-not-insert"})
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        out = await backtest_runs.insert_run(
            date(2026, 7, 16), "momentum", "current", {"k": 1}
        )

    assert out is None, "사전 중복 존재 → None."
    # INSERT 는 발화하지 않아야 함
    all_sql = _collect_sql(pg_mod)
    assert not any("INSERT INTO backtest_runs" in s for s in all_sql), (
        "중복 시 INSERT 미발화 계약."
    )


@pytest.mark.asyncio
async def test_insert_run_unique_race_returns_none():
    """INSERT 시점 UNIQUE 충돌(race) → None (graceful)."""
    from src.db import backtest_runs

    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("duplicate key (23505) unique_violation"))
        pg_mod.execute = AsyncMock(side_effect=Exception("duplicate key (23505) unique_violation"))
        out = await backtest_runs.insert_run(
            date(2026, 7, 16), "momentum", "current", {"k": 1}
        )

    assert out is None, "UNIQUE race → None graceful."


# ---------------------------------------------------------------------------
# get_by_id / list_by_date
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_by_id_uses_pg_fetchrow_where():
    """get_by_id → pg.fetchrow(SELECT ... WHERE id = $1) → dict | None."""
    from src.db import backtest_runs

    row = {"id": "uuid-1", "status": "completed"}
    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=row)
        out = await backtest_runs.get_by_id("uuid-1")

    assert out == row
    sql = pg_mod.fetchrow.await_args.args[0]
    assert "backtest_runs" in sql and "id" in sql
    assert "uuid-1" in pg_mod.fetchrow.await_args.args[1:], "id 바인딩 누락."


@pytest.mark.asyncio
async def test_get_by_id_missing_returns_none():
    from src.db import backtest_runs

    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        out = await backtest_runs.get_by_id("nope")

    assert out is None


@pytest.mark.asyncio
async def test_list_by_date_uses_pg_fetch_where():
    """list_by_date → pg.fetch(SELECT ... WHERE target_date = $1) → list[dict]."""
    from src.db import backtest_runs

    rows = [{"id": "1"}, {"id": "2"}]
    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await backtest_runs.list_by_date(date(2026, 7, 16))

    assert out == rows and isinstance(out, list)
    sql = pg_mod.fetch.await_args.args[0]
    assert "backtest_runs" in sql and "target_date" in sql
    assert date(2026, 7, 16) in pg_mod.fetch.await_args.args[1:], "target_date 바인딩 누락."


@pytest.mark.asyncio
async def test_list_by_date_empty_returns_empty_list():
    from src.db import backtest_runs

    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await backtest_runs.list_by_date(date(2026, 7, 16))

    assert out == []


# ---------------------------------------------------------------------------
# update_status — UPDATE ... SET (metrics JSONB, completed_at datetime) WHERE id
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_status_completed_sets_metrics_and_completed_at():
    """update_status(completed, metrics=…) → UPDATE ... RETURNING → dict.

    metrics JSONB 바인딩 + completed_at datetime 바인딩.
    """
    from src.db import backtest_runs

    updated = {"id": "uuid-1", "status": "completed", "metrics": {"sharpe": 1.2}}
    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=updated)
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        out = await backtest_runs.update_status(
            "uuid-1", "completed", metrics={"sharpe": 1.2}
        )

    assert out == updated, "update_status → 갱신 dict 반환."
    all_sql = _collect_sql(pg_mod)
    assert any("UPDATE backtest_runs" in s and "SET" in s.upper() for s in all_sql), (
        "UPDATE backtest_runs SET SQL 누락."
    )
    args = _update_args(pg_mod)
    assert "uuid-1" in args, "id WHERE 바인딩 누락."
    assert _has_jsonb_binding(args, {"sharpe": 1.2}), "metrics JSONB 바인딩 누락."
    assert any(isinstance(a, datetime) for a in args), (
        "completed_at 은 datetime 바인딩 — str 금지."
    )


@pytest.mark.asyncio
async def test_update_status_running_sets_mcp_job_id():
    """update_status(running, mcp_job_id=…) → UPDATE (completed_at 미기록)."""
    from src.db import backtest_runs

    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "uuid-1", "status": "running"})
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        out = await backtest_runs.update_status("uuid-1", "running", mcp_job_id="job-123")

    assert out.get("status") == "running"
    args = _update_args(pg_mod)
    assert "job-123" in args, "mcp_job_id 바인딩 누락."


@pytest.mark.asyncio
async def test_update_status_invalid_status_raises():
    """status ∉ 허용집합 → ValueError (본체 검증 보존)."""
    from src.db import backtest_runs

    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        with pytest.raises(ValueError):
            await backtest_runs.update_status("uuid-1", "bogus")


@pytest.mark.asyncio
async def test_update_status_zero_rows_returns_empty_dict():
    """적용 row 0건 → {} (기존 'row 0건 → {}' 계약 보존)."""
    from src.db import backtest_runs

    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)  # RETURNING 0건
        pg_mod.execute = AsyncMock(return_value="UPDATE 0")
        out = await backtest_runs.update_status("missing-id", "completed")

    assert out == {}, "적용 row 0건 → {} 계약."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase 미참조
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_backtest_runs_no_supabase_reference_after_transition():
    """전환 후 backtest_runs.py 는 supabase 를 참조하지 않는다 (pg 단독)."""
    from src.db import backtest_runs

    assert not hasattr(backtest_runs, "supabase"), (
        "전환 후 backtest_runs 모듈에 supabase 심볼이 남으면 안 됨."
    )
    assert hasattr(backtest_runs, "pg"), "backtest_runs 가 src.db.pg 를 import 해야 함."


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _collect_sql(pg_mod) -> list[str]:
    sqls: list[str] = []
    for name in ("fetchrow", "execute", "fetch", "fetchval"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sqls.append(m.await_args.args[0])
    return sqls


def _insert_args(pg_mod) -> tuple:
    for name in ("fetchrow", "execute"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sql = m.await_args.args[0]
            if "INSERT" in sql.upper():
                return m.await_args.args[1:]
    return ()


def _update_args(pg_mod) -> tuple:
    for name in ("fetchrow", "execute"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sql = m.await_args.args[0]
            if "UPDATE" in sql.upper():
                return m.await_args.args[1:]
    return ()


def _has_jsonb_binding(args: tuple, expected) -> bool:
    import json

    dumped = json.dumps(expected)
    for a in args:
        if a == expected:
            return True
        if isinstance(a, str) and a == dumped:
            return True
    return False
