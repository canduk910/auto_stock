"""사이클 M1-2 (Red) — src/db/market_regime_snapshots.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, 증분 2).

현행 market_regime_snapshots.py = supabase-py 체인. 이 증분 = `pg.*` 전환.

핵심 계약:
- insert_snapshot → 사전 중복 SELECT 존재 시 None + INSERT ... RETURNING (raw_response JSONB,
  NUMERIC vix/fg/buffett/ratio, created_at datetime). snapshot_date UNIQUE 충돌 → None (graceful).
- get_by_date / get_latest → SELECT → dict | None (except graceful None).
- list_recent(days=30) → SELECT ... ORDER BY snapshot_date DESC LIMIT $1 → list[dict] (except graceful []).

Red 유효성: production 미변경 → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _sample_kwargs():
    return dict(
        snapshot_date=date(2026, 7, 16),
        regime="neutral",
        regime_desc="중립",
        cycle_phase="expansion",
        vix=18.5,
        fear_greed_score=55.0,
        buffett_ratio=140.0,
        raw_response={"macro": {"regime": "neutral"}, "sentiment": {"fg": 55}},
        computed_cash_usage_ratio=0.8,
        buy_blocked=False,
        block_reason=None,
    )


# ---------------------------------------------------------------------------
# insert_snapshot — 사전 중복 + INSERT (raw_response JSONB) + created_at datetime
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insert_snapshot_uses_pg_insert_returning():
    """insert_snapshot → 중복 없으면 INSERT INTO market_regime_snapshots RETURNING."""
    from src.db import market_regime_snapshots as mrs

    inserted = {"id": "uuid-1", "snapshot_date": date(2026, 7, 16), "regime": "neutral"}
    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])  # 사전 중복 = 없음
        pg_mod.fetchrow = AsyncMock(return_value=inserted)
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        out = await mrs.insert_snapshot(**_sample_kwargs())

    assert out == inserted, "insert_snapshot → 삽입 dict 반환 계약."
    all_sql = _collect_sql(pg_mod)
    assert any("INSERT INTO market_regime_snapshots" in s for s in all_sql), (
        "INSERT INTO market_regime_snapshots SQL 누락."
    )
    args = _insert_args(pg_mod)
    assert date(2026, 7, 16) in args and "neutral" in args, "snapshot_date/regime 바인딩 누락."
    assert _has_jsonb_binding(args, {"macro": {"regime": "neutral"}, "sentiment": {"fg": 55}}), (
        "raw_response JSONB 바인딩 누락."
    )
    assert any(isinstance(a, datetime) for a in args), (
        "created_at 은 datetime 바인딩 (fromisoformat(now_kst_iso())) — str 금지."
    )


@pytest.mark.asyncio
async def test_insert_snapshot_existing_duplicate_returns_none():
    """사전 중복 SELECT 존재 시 None (INSERT 미발화)."""
    from src.db import market_regime_snapshots as mrs

    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"id": "existing"}])
        pg_mod.fetchrow = AsyncMock(return_value={"id": "no"})
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        out = await mrs.insert_snapshot(**_sample_kwargs())

    assert out is None, "사전 중복 존재 → None."
    all_sql = _collect_sql(pg_mod)
    assert not any("INSERT INTO market_regime_snapshots" in s for s in all_sql), (
        "중복 시 INSERT 미발화 계약."
    )


@pytest.mark.asyncio
async def test_insert_snapshot_unique_race_returns_none():
    """INSERT 시점 UNIQUE 충돌(race) → None (graceful)."""
    from src.db import market_regime_snapshots as mrs

    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("duplicate (23505) unique_violation"))
        pg_mod.execute = AsyncMock(side_effect=Exception("duplicate (23505) unique_violation"))
        out = await mrs.insert_snapshot(**_sample_kwargs())

    assert out is None, "UNIQUE race → None graceful."


# ---------------------------------------------------------------------------
# get_by_date / get_latest / list_recent
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_by_date_uses_pg_fetchrow_where():
    from src.db import market_regime_snapshots as mrs

    row = {"snapshot_date": date(2026, 7, 16), "regime": "neutral"}
    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=row)
        out = await mrs.get_by_date(date(2026, 7, 16))

    assert out == row
    sql = pg_mod.fetchrow.await_args.args[0]
    assert "market_regime_snapshots" in sql and "snapshot_date" in sql
    assert date(2026, 7, 16) in pg_mod.fetchrow.await_args.args[1:], "snapshot_date 바인딩 누락."


@pytest.mark.asyncio
async def test_get_by_date_graceful_none_on_error():
    """DB 예외 시 None (except graceful 계약 보존)."""
    from src.db import market_regime_snapshots as mrs

    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("boom"))
        out = await mrs.get_by_date(date(2026, 7, 16))

    assert out is None, "get_by_date 예외 → None graceful."


@pytest.mark.asyncio
async def test_get_latest_uses_pg_fetchrow_order_desc():
    from src.db import market_regime_snapshots as mrs

    row = {"snapshot_date": date(2026, 7, 16)}
    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=row)
        out = await mrs.get_latest()

    assert out == row
    sql = pg_mod.fetchrow.await_args.args[0]
    assert "market_regime_snapshots" in sql
    assert "ORDER BY" in sql.upper() and "DESC" in sql.upper(), "snapshot_date DESC 정렬 누락."


@pytest.mark.asyncio
async def test_get_latest_graceful_none_on_error():
    from src.db import market_regime_snapshots as mrs

    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("boom"))
        out = await mrs.get_latest()

    assert out is None


@pytest.mark.asyncio
async def test_list_recent_uses_pg_fetch_order_limit():
    from src.db import market_regime_snapshots as mrs

    rows = [{"snapshot_date": date(2026, 7, 16)}]
    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await mrs.list_recent(days=7)

    assert out == rows and isinstance(out, list)
    sql = pg_mod.fetch.await_args.args[0]
    assert "market_regime_snapshots" in sql
    assert "ORDER BY" in sql.upper() and "DESC" in sql.upper()
    assert 7 in pg_mod.fetch.await_args.args[1:], "days LIMIT 파라미터 바인딩 누락."


@pytest.mark.asyncio
async def test_list_recent_graceful_empty_on_error():
    """DB 예외 시 [] (except graceful 계약 보존)."""
    from src.db import market_regime_snapshots as mrs

    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        out = await mrs.list_recent()

    assert out == [], "list_recent 예외 → [] graceful."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase 미참조
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_market_regime_no_supabase_reference_after_transition():
    """전환 후 market_regime_snapshots.py 는 supabase 를 참조하지 않는다 (pg 단독)."""
    from src.db import market_regime_snapshots as mrs

    assert not hasattr(mrs, "supabase"), (
        "전환 후 market_regime_snapshots 모듈에 supabase 심볼이 남으면 안 됨."
    )
    assert hasattr(mrs, "pg"), "market_regime_snapshots 가 src.db.pg 를 import 해야 함."


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


def _has_jsonb_binding(args: tuple, expected) -> bool:
    import json

    dumped = json.dumps(expected)
    for a in args:
        if a == expected:
            return True
        if isinstance(a, str) and a == dumped:
            return True
    return False
