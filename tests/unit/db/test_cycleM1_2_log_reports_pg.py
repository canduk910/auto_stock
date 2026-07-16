"""사이클 M1-2 (Red) — src/db/log_reports.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, 증분 2).

현행 log_reports.py = supabase-py 체인. 이 증분 = `pg.*` 전환. **함수 계약
(시그니처·반환형·graceful) 100% 보존** → 호출부(log_analysis_engine 등) diff 0.

핵심 계약:
- insert_log_report → JSONB `findings`/`metrics` 바인딩 + `cost_estimate_usd` Decimal→float
  + `created_at` TIMESTAMPTZ = datetime 바인딩 (M1-1 패턴 2). target_date UNIQUE 충돌 → None.
- list_log_reports(days=30) → SELECT ... ORDER BY target_date DESC LIMIT $1 → list[dict].
- get_log_report(target_date) → SELECT ... WHERE target_date = $1 → dict | None.

Red 유효성: production 미변경 → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# insert_log_report — JSONB findings/metrics + DECIMAL cost + TIMESTAMPTZ datetime
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insert_log_report_uses_pg_insert_returning():
    """insert_log_report → pg.fetchrow/execute 로 INSERT INTO daily_log_reports RETURNING."""
    from src.db import log_reports

    inserted = {
        "id": "uuid-1",
        "target_date": date(2026, 7, 16),
        "summary": "요약",
        "findings": [{"category": "api", "severity": "low"}],
        "metrics": {"info": 3},
        "model": "gpt-4",
    }
    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=inserted)
        pg_mod.fetchval = AsyncMock(return_value=None)
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        out = await log_reports.insert_log_report(
            target_date=date(2026, 7, 16),
            summary="요약",
            findings=[{"category": "api", "severity": "low"}],
            metrics={"info": 3},
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=1200,
            cost_estimate_usd=Decimal("0.001234"),
        )

    assert out == inserted, "insert_log_report → 삽입 dict 반환 계약."
    # INSERT 는 fetchrow(RETURNING) 또는 execute 중 하나로 발화
    all_sql = _collect_sql(pg_mod)
    assert any("INSERT INTO daily_log_reports" in s for s in all_sql), (
        "INSERT INTO daily_log_reports SQL 누락."
    )
    args = _insert_args(pg_mod)
    assert date(2026, 7, 16) in args, "target_date 바인딩 누락."
    # findings/metrics 는 JSONB — dict/list 그대로 또는 json.dumps 문자열로 바인딩
    assert _has_jsonb_binding(args, [{"category": "api", "severity": "low"}]), (
        "findings JSONB 바인딩 누락 (dict/list 또는 json.dumps)."
    )
    assert _has_jsonb_binding(args, {"info": 3}), "metrics JSONB 바인딩 누락."


@pytest.mark.asyncio
async def test_insert_log_report_cost_estimate_is_float():
    """cost_estimate_usd Decimal → float 캐스트 바인딩 (기존 계약 보존)."""
    from src.db import log_reports

    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.fetchval = AsyncMock(return_value=None)
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await log_reports.insert_log_report(
            target_date=date(2026, 7, 16),
            summary="s",
            findings=[],
            metrics={},
            model=None,
            cost_estimate_usd=Decimal("0.5"),
        )

    args = _insert_args(pg_mod)
    assert any(isinstance(a, float) and abs(a - 0.5) < 1e-9 for a in args), (
        "cost_estimate_usd Decimal → float 캐스트 계약 위반."
    )


@pytest.mark.asyncio
async def test_insert_log_report_created_at_is_datetime():
    """created_at TIMESTAMPTZ 바인딩은 datetime 인스턴스 (M1-1 패턴 2 — asyncpg str 불가)."""
    from src.db import log_reports

    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.fetchval = AsyncMock(return_value=None)
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await log_reports.insert_log_report(
            target_date=date(2026, 7, 16),
            summary="s",
            findings=[],
            metrics={},
            model=None,
        )

    args = _insert_args(pg_mod)
    assert any(isinstance(a, datetime) for a in args), (
        "created_at 은 datetime 바인딩 (fromisoformat(now_kst_iso())) — str 바인딩 금지."
    )


@pytest.mark.asyncio
async def test_insert_log_report_unique_conflict_returns_none():
    """target_date UNIQUE 충돌 시 None (기존 duplicate key/23505 분기 보존)."""
    from src.db import log_reports

    with patch.object(log_reports, "pg", create=True) as pg_mod:
        # asyncpg UniqueViolationError 계열을 흉내 — 메시지에 duplicate/23505
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("duplicate key value violates unique constraint (23505)"))
        pg_mod.execute = AsyncMock(side_effect=Exception("duplicate key value violates unique constraint (23505)"))
        pg_mod.fetchval = AsyncMock(return_value=None)
        out = await log_reports.insert_log_report(
            target_date=date(2026, 7, 16),
            summary="s",
            findings=[],
            metrics={},
            model=None,
        )

    assert out is None, "UNIQUE 충돌 → None 계약 보존."


# ---------------------------------------------------------------------------
# list_log_reports / get_log_report — SELECT
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_log_reports_uses_pg_fetch_order_limit():
    """list_log_reports → pg.fetch(SELECT ... ORDER BY target_date DESC LIMIT $1)."""
    from src.db import log_reports

    rows = [{"target_date": date(2026, 7, 16), "summary": "a"}]
    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await log_reports.list_log_reports(days=7)

    assert out == rows, "list_log_reports → list[dict] 반환 계약."
    sql = pg_mod.fetch.await_args.args[0]
    assert "daily_log_reports" in sql and "SELECT" in sql.upper()
    assert "ORDER BY" in sql.upper() and "DESC" in sql.upper(), "target_date DESC 정렬 누락."
    assert 7 in pg_mod.fetch.await_args.args[1:], "days LIMIT 파라미터 바인딩 누락."


@pytest.mark.asyncio
async def test_list_log_reports_empty_returns_empty_list():
    """0건 → [] (result.data or [] 대응)."""
    from src.db import log_reports

    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await log_reports.list_log_reports()

    assert out == [], "0건 → 빈 리스트."


@pytest.mark.asyncio
async def test_get_log_report_uses_pg_fetchrow_where():
    """get_log_report → pg.fetchrow(SELECT ... WHERE target_date = $1) → dict | None."""
    from src.db import log_reports

    row = {"target_date": date(2026, 7, 16), "summary": "a"}
    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=row)
        out = await log_reports.get_log_report(date(2026, 7, 16))

    assert out == row, "get_log_report → 단일 dict 반환."
    sql = pg_mod.fetchrow.await_args.args[0]
    assert "daily_log_reports" in sql and "target_date" in sql
    assert date(2026, 7, 16) in pg_mod.fetchrow.await_args.args[1:], "target_date 바인딩 누락."


@pytest.mark.asyncio
async def test_get_log_report_missing_returns_none():
    """미존재 → None (fetchrow None 대응)."""
    from src.db import log_reports

    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        out = await log_reports.get_log_report(date(2026, 7, 16))

    assert out is None, "미존재 → None."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase 미참조
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_log_reports_no_supabase_reference_after_transition():
    """전환 후 log_reports.py 는 supabase 를 참조하지 않는다 (pg 단독)."""
    from src.db import log_reports

    assert not hasattr(log_reports, "supabase"), (
        "전환 후 log_reports 모듈에 supabase 심볼이 남으면 안 됨 (pg 단독 전환)."
    )
    assert hasattr(log_reports, "pg"), "log_reports 가 src.db.pg 를 import 해야 함."


# ---------------------------------------------------------------------------
# 헬퍼 — INSERT 발화 경로(fetchrow/execute) 인자 수집 (Green 구현 자유도 허용)
# ---------------------------------------------------------------------------
def _collect_sql(pg_mod) -> list[str]:
    sqls: list[str] = []
    for name in ("fetchrow", "execute", "fetch", "fetchval"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sqls.append(m.await_args.args[0])
    return sqls


def _insert_args(pg_mod) -> tuple:
    """INSERT 를 실제 발화한 mock(fetchrow 우선, 없으면 execute)의 바인딩 인자."""
    for name in ("fetchrow", "execute"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sql = m.await_args.args[0]
            if "INSERT" in sql.upper():
                return m.await_args.args[1:]
    return ()


def _has_jsonb_binding(args: tuple, expected) -> bool:
    """JSONB 컬럼 바인딩이 dict/list 원본 또는 json.dumps 문자열로 포함되는지."""
    import json

    dumped = json.dumps(expected)
    for a in args:
        if a == expected:
            return True
        if isinstance(a, str) and a == dumped:
            return True
    return False
