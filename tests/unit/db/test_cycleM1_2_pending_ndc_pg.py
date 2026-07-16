"""사이클 M1-2 (Red) — src/db/pending_next_day_clear.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, 증분 2).

⚠️ 매매 안전성 (익일청산 큐) — 사이클 162 계약 절대 보존. 소비처(scheduler
`_execute_next_day_clear`/`_drain_…`/`_reset_daily_state` + boot_manager `boot()` load)는
db 함수만 호출 → 시그니처·반환형·graceful 보존 시 호출부 diff 0.

핵심 계약:
- save_pending_ndc → INSERT ... ON CONFLICT (target_date,ticker,strategy_id) DO UPDATE (복합 PK).
  created_at datetime 바인딩. → None.
- delete_pending_ndc → DELETE ... WHERE (target_date,ticker,strategy_id) (idempotent). → None.
- load_pending_ndc → SELECT ticker, strategy_id → set[tuple]. **실패 시 빈 set (graceful)**
  = 호출자 메모리 set 보존 (사이클 162 절대 계약).
- purge_pending_ndc_before → DELETE ... WHERE target_date < $1 → 삭제 행 수 (실패 -1).

Red 유효성: production 미변경 → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# save_pending_ndc — 복합 PK upsert + created_at datetime
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_pending_ndc_uses_pg_upsert_composite_pk():
    """save_pending_ndc → pg.execute 로 INSERT ... ON CONFLICT (복합 PK) DO UPDATE."""
    from src.db import pending_next_day_clear as pnd

    with patch.object(pnd, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        out = await pnd.save_pending_ndc(
            date(2026, 7, 16), "196170", "volatility_breakout", reason="nxt_not_tradable"
        )

    assert out is None, "save_pending_ndc 반환형 None 계약 보존."
    assert pg_mod.execute.await_count == 1
    sql = pg_mod.execute.await_args.args[0]
    assert "INSERT INTO pending_next_day_clear" in sql, "INSERT SQL 누락."
    assert "ON CONFLICT (target_date, ticker, strategy_id) DO UPDATE" in sql, (
        "복합 PK upsert = ON CONFLICT (target_date, ticker, strategy_id) DO UPDATE 누락."
    )
    args = pg_mod.execute.await_args.args[1:]
    assert date(2026, 7, 16) in args, "target_date 바인딩 누락."
    assert "196170" in args and "volatility_breakout" in args, "ticker/strategy_id 바인딩 누락."
    assert "nxt_not_tradable" in args, "reason 바인딩 누락."
    assert any(isinstance(a, datetime) for a in args), (
        "created_at 은 datetime 바인딩 (fromisoformat(now_kst_iso())) — str 금지."
    )


@pytest.mark.asyncio
async def test_save_pending_ndc_default_reason():
    """reason 미지정 → 'unknown' 기본값 바인딩 (기존 계약 보존)."""
    from src.db import pending_next_day_clear as pnd

    with patch.object(pnd, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await pnd.save_pending_ndc(date(2026, 7, 16), "476830", "long_tail_volatility")

    args = pg_mod.execute.await_args.args[1:]
    assert "unknown" in args, "reason 기본값 'unknown' 바인딩 누락."


# ---------------------------------------------------------------------------
# delete_pending_ndc — DELETE 복합 WHERE (idempotent)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_pending_ndc_uses_pg_delete_composite_where():
    """delete_pending_ndc → pg.execute 로 DELETE ... WHERE (target_date,ticker,strategy_id)."""
    from src.db import pending_next_day_clear as pnd

    with patch.object(pnd, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="DELETE 1")
        out = await pnd.delete_pending_ndc(date(2026, 7, 16), "196170", "volatility_breakout")

    assert out is None, "delete_pending_ndc 반환형 None 계약 보존."
    sql = pg_mod.execute.await_args.args[0]
    assert "DELETE FROM pending_next_day_clear" in sql
    assert "target_date" in sql and "ticker" in sql and "strategy_id" in sql, (
        "복합 WHERE (target_date/ticker/strategy_id) 누락."
    )
    args = pg_mod.execute.await_args.args[1:]
    assert date(2026, 7, 16) in args and "196170" in args and "volatility_breakout" in args, (
        "복합 WHERE 파라미터 바인딩 누락."
    )


# ---------------------------------------------------------------------------
# load_pending_ndc — SELECT → set[tuple] + graceful 빈 set (사이클 162 절대 계약)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_load_pending_ndc_returns_set_of_tuples():
    """load_pending_ndc → pg.fetch(SELECT ticker, strategy_id) → set[(ticker, strategy_id)]."""
    from src.db import pending_next_day_clear as pnd

    rows = [
        {"ticker": "196170", "strategy_id": "volatility_breakout"},
        {"ticker": "476830", "strategy_id": "long_tail_volatility"},
    ]
    with patch.object(pnd, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await pnd.load_pending_ndc(date(2026, 7, 16))

    assert out == {
        ("196170", "volatility_breakout"),
        ("476830", "long_tail_volatility"),
    }, "load_pending_ndc → set[tuple] 반환 계약 (scheduler._pending_next_day_clear 직접 update)."
    assert isinstance(out, set)
    sql = pg_mod.fetch.await_args.args[0]
    assert "pending_next_day_clear" in sql and "ticker" in sql and "strategy_id" in sql
    assert date(2026, 7, 16) in pg_mod.fetch.await_args.args[1:], "target_date 바인딩 누락."


@pytest.mark.asyncio
async def test_load_pending_ndc_graceful_empty_set_on_error():
    """⚠️ DB 예외 시 빈 set (호출자 메모리 set 보존 — 사이클 162 절대 계약)."""
    from src.db import pending_next_day_clear as pnd

    with patch.object(pnd, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        out = await pnd.load_pending_ndc(date(2026, 7, 16))

    assert out == set(), "load_pending_ndc 예외 → 빈 set graceful (익일청산 메모리 보존)."
    assert isinstance(out, set)


@pytest.mark.asyncio
async def test_load_pending_ndc_skips_incomplete_rows():
    """ticker/strategy_id 결손 row 는 제외 (기존 필터 계약 보존)."""
    from src.db import pending_next_day_clear as pnd

    rows = [
        {"ticker": "196170", "strategy_id": "volatility_breakout"},
        {"ticker": None, "strategy_id": "x"},
        {"ticker": "y", "strategy_id": None},
    ]
    with patch.object(pnd, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await pnd.load_pending_ndc(date(2026, 7, 16))

    assert out == {("196170", "volatility_breakout")}, "결손 row 제외 계약."


# ---------------------------------------------------------------------------
# purge_pending_ndc_before — DELETE ... WHERE target_date < $1 → count (실패 -1)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_purge_pending_ndc_before_uses_pg_delete_lt():
    """purge_pending_ndc_before → pg.execute 로 DELETE ... WHERE target_date < $1 → 삭제 행 수."""
    from src.db import pending_next_day_clear as pnd

    with patch.object(pnd, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="DELETE 3")
        out = await pnd.purge_pending_ndc_before(date(2026, 7, 16))

    assert out == 3, "삭제 행 수 반환 계약 (asyncpg 'DELETE N' 상태 파싱)."
    sql = pg_mod.execute.await_args.args[0]
    assert "DELETE FROM pending_next_day_clear" in sql
    assert "target_date" in sql and "<" in sql, "target_date < cutoff WHERE 누락."
    assert date(2026, 7, 16) in pg_mod.execute.await_args.args[1:], "cutoff 바인딩 누락."


@pytest.mark.asyncio
async def test_purge_pending_ndc_before_graceful_minus_one_on_error():
    """DB 예외 시 -1 (graceful 계약 보존)."""
    from src.db import pending_next_day_clear as pnd

    with patch.object(pnd, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=Exception("boom"))
        out = await pnd.purge_pending_ndc_before(date(2026, 7, 16))

    assert out == -1, "purge 예외 → -1 graceful."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase 미참조
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pending_ndc_no_supabase_reference_after_transition():
    """전환 후 pending_next_day_clear.py 는 supabase 를 참조하지 않는다 (pg 단독)."""
    from src.db import pending_next_day_clear as pnd

    assert not hasattr(pnd, "supabase"), (
        "전환 후 pending_next_day_clear 모듈에 supabase 심볼이 남으면 안 됨."
    )
    assert hasattr(pnd, "pg"), "pending_next_day_clear 가 src.db.pg 를 import 해야 함."
