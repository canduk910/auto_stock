"""사이클 M1-3 (Red) — src/db/daily_performance.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, M1 마무리).

현행 daily_performance.py = supabase-py 체인 + **RPC** (`.rpc("recompute_daily_performance", {})`).
이 증분 = `pg.*` 전환. **함수 계약(시그니처·반환형·graceful) 100% 보존** → 호출부
(scheduler `_settle` 등) diff 0.

핵심 계약:
- upsert_daily_performance → INSERT ... ON CONFLICT (date, strategy) DO UPDATE (복합 키).
  → None. NUMERIC 컬럼(total_asset/daily_profit_rate/daily_realized_pnl/…) 값 바인딩.
- get_performance(days, strategy) → SELECT ... WHERE strategy=$ ORDER BY date DESC LIMIT $
  → **date ASC 정렬 반환** (코드가 client-side sorted). → list[dict].
- get_latest_performance(strategy) → SELECT ... ORDER BY date DESC LIMIT 1 → dict | None.
- recompute_from_trades → **RPC** `.rpc("recompute_daily_performance",{})`
  → `pg.execute("SELECT recompute_daily_performance()")`. 성공 True / 예외 graceful False.

⚠️ NUMERIC→Decimal: asyncpg 는 NUMERIC 을 Decimal 로 반환한다. get_* 반환 dict 의 NUMERIC
컬럼(total_asset/cumulative_return_rate 등)이 Decimal 이어도 계약 위반 아님 — 라우트
JSON 직렬화 계약은 통합/라우트에서 확인. 여기서는 dict pass-through + 정렬/키만 단언.

Red 유효성: production 미변경 → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.unit

from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# upsert_daily_performance — INSERT ... ON CONFLICT (date, strategy) DO UPDATE
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upsert_daily_performance_uses_pg_upsert_composite_key():
    """upsert → pg.execute 로 INSERT ... ON CONFLICT (date, strategy) DO UPDATE."""
    from src.db import daily_performance

    with patch.object(daily_performance, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        out = await daily_performance.upsert_daily_performance(
            date(2026, 7, 16),
            total_asset=10_000_000.0,
            daily_profit_rate=1.25,
            strategy="momentum",
            net_external_cashflow=500.0,
            daily_realized_pnl=125_000.0,
            deposit=3_000_000.0,
            cumulative_return_rate=8.5,
        )

    assert out is None, "upsert_daily_performance 반환형 None 계약 보존."
    all_sql = _collect_sql(pg_mod)
    assert any("INSERT INTO daily_performance" in s for s in all_sql), (
        "INSERT INTO daily_performance SQL 누락."
    )
    # 복합 키 (date, strategy) ON CONFLICT DO UPDATE
    assert any(
        "ON CONFLICT (date, strategy) DO UPDATE" in s for s in all_sql
    ), "복합 키 upsert = ON CONFLICT (date, strategy) DO UPDATE 누락."

    args = _insert_args(pg_mod)
    assert date(2026, 7, 16) in args, "date 바인딩 누락."
    assert "momentum" in args, "strategy 바인딩 누락."
    # NUMERIC 값 바인딩 (float 그대로 전달)
    assert 10_000_000.0 in args, "total_asset 바인딩 누락."
    assert 1.25 in args, "daily_profit_rate 바인딩 누락."
    assert 125_000.0 in args, "daily_realized_pnl 바인딩 누락."
    assert 8.5 in args, "cumulative_return_rate 바인딩 누락."


@pytest.mark.asyncio
async def test_upsert_daily_performance_default_strategy_total():
    """strategy 미지정 → 'total' 기본값 바인딩 (기존 계약 보존)."""
    from src.db import daily_performance

    with patch.object(daily_performance, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetchrow = AsyncMock(return_value=None)
        await daily_performance.upsert_daily_performance(
            date(2026, 7, 16), total_asset=1.0, daily_profit_rate=0.0
        )

    args = _insert_args(pg_mod)
    assert "total" in args, "strategy 기본값 'total' 바인딩 누락."


# ---------------------------------------------------------------------------
# get_performance — SELECT ... strategy ORDER BY date DESC LIMIT → date ASC 반환
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_performance_uses_pg_fetch_and_returns_date_asc():
    """get_performance → pg.fetch(WHERE strategy ORDER BY date DESC LIMIT) → date ASC 반환.

    코드가 result 를 date 오름차순 client-side sorted → 반환 순서 ASC 보존.
    """
    from src.db import daily_performance

    rows = [
        {"date": date(2026, 7, 16), "strategy": "total", "total_asset": 3.0},
        {"date": date(2026, 7, 14), "strategy": "total", "total_asset": 1.0},
        {"date": date(2026, 7, 15), "strategy": "total", "total_asset": 2.0},
    ]
    with patch.object(daily_performance, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await daily_performance.get_performance(days=30, strategy="total")

    dates = [r["date"] for r in out]
    assert dates == [date(2026, 7, 14), date(2026, 7, 15), date(2026, 7, 16)], (
        "get_performance 반환은 date 오름차순 (client-side sorted 계약 보존)."
    )
    sql = pg_mod.fetch.await_args.args[0]
    assert "daily_performance" in sql and "SELECT" in sql.upper()
    assert "strategy" in sql, "strategy 필터 누락."
    assert "ORDER BY" in sql.upper() and "DESC" in sql.upper(), "date DESC 정렬 누락."
    passed = pg_mod.fetch.await_args.args[1:]
    assert "total" in passed, "strategy 바인딩 누락."
    assert 30 in passed, "days LIMIT 바인딩 누락."


@pytest.mark.asyncio
async def test_get_performance_empty_returns_empty_list():
    """0건 → [] (result.data or [] 대응)."""
    from src.db import daily_performance

    with patch.object(daily_performance, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await daily_performance.get_performance()

    assert out == [], "0건 → 빈 리스트."


# ---------------------------------------------------------------------------
# get_latest_performance — ORDER BY date DESC LIMIT 1 → dict | None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_latest_performance_uses_pg_fetchrow_limit1():
    """get_latest_performance → pg.fetchrow(ORDER BY date DESC LIMIT 1) → dict."""
    from src.db import daily_performance

    row = {"date": date(2026, 7, 16), "strategy": "total", "total_asset": 5.0}
    with patch.object(daily_performance, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=row)
        # fetch 도 허용 (구현 자유도 — 단, 최신 1행 계약)
        pg_mod.fetch = AsyncMock(return_value=[row])
        out = await daily_performance.get_latest_performance(strategy="total")

    assert out == row, "get_latest_performance → 단일 dict 반환."
    sql = _latest_sql(pg_mod)
    assert sql is not None and "daily_performance" in sql
    assert "strategy" in sql and "ORDER BY" in sql.upper() and "DESC" in sql.upper()
    assert "total" in _latest_args(pg_mod), "strategy 바인딩 누락."


@pytest.mark.asyncio
async def test_get_latest_performance_missing_returns_none():
    """미존재 → None (result.data[0] if result.data else None 대응)."""
    from src.db import daily_performance

    with patch.object(daily_performance, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await daily_performance.get_latest_performance()

    assert out is None, "미존재 → None."


# ---------------------------------------------------------------------------
# recompute_from_trades — RPC → pg.execute("SELECT recompute_daily_performance()")
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recompute_from_trades_calls_rpc_via_pg_execute():
    """⚠️ RPC 전환: .rpc(...) → pg.execute('SELECT recompute_daily_performance()') → True."""
    from src.db import daily_performance

    with patch.object(daily_performance, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="SELECT 1")
        pg_mod.fetchval = AsyncMock(return_value=None)
        out = await daily_performance.recompute_from_trades()

    assert out is True, "recompute_from_trades 성공 → True 계약 보존."
    all_sql = _collect_sql(pg_mod)
    assert any("recompute_daily_performance()" in s for s in all_sql), (
        "RPC = SELECT recompute_daily_performance() 호출 누락 (plpgsql 함수 SELECT)."
    )


@pytest.mark.asyncio
async def test_recompute_from_trades_graceful_false_on_error():
    """RPC 예외 시 False (기존 try/except graceful 계약 보존)."""
    from src.db import daily_performance

    with patch.object(daily_performance, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=Exception("boom"))
        pg_mod.fetchval = AsyncMock(side_effect=Exception("boom"))
        out = await daily_performance.recompute_from_trades()

    assert out is False, "recompute 예외 → False graceful (멱등 재계산 실패 흡수)."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase 미참조
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_daily_performance_no_supabase_reference_after_transition():
    """전환 후 daily_performance.py 는 supabase 를 참조하지 않는다 (pg 단독)."""
    from src.db import daily_performance

    assert not hasattr(daily_performance, "supabase"), (
        "전환 후 daily_performance 모듈에 supabase 심볼이 남으면 안 됨 (pg 단독 전환)."
    )
    assert hasattr(daily_performance, "pg"), "daily_performance 가 src.db.pg 를 import 해야 함."


# ---------------------------------------------------------------------------
# 헬퍼 — 발화 경로(execute/fetchrow/fetch/fetchval) SQL·인자 수집 (Green 자유도)
# ---------------------------------------------------------------------------
def _collect_sql(pg_mod) -> list[str]:
    sqls: list[str] = []
    for name in ("execute", "fetchrow", "fetch", "fetchval"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sqls.append(m.await_args.args[0])
    return sqls


def _insert_args(pg_mod) -> tuple:
    """INSERT 를 실제 발화한 mock(execute 우선, 없으면 fetchrow)의 바인딩 인자."""
    for name in ("execute", "fetchrow"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sql = m.await_args.args[0]
            if "INSERT" in sql.upper():
                return m.await_args.args[1:]
    return ()


def _latest_sql(pg_mod) -> str | None:
    """get_latest_performance 를 발화한 mock(fetchrow 우선)의 SQL."""
    for name in ("fetchrow", "fetch"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            return m.await_args.args[0]
    return None


def _latest_args(pg_mod) -> tuple:
    for name in ("fetchrow", "fetch"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            return m.await_args.args[1:]
    return ()
