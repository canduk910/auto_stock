"""사이클 M1-3 (Red) — src/db/strategy_funnel.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, M1 마무리).

현행 strategy_funnel.py = supabase-py 체인 (`.upsert(on_conflict=...)`). 이 증분 =
`pg.*` 전환. **함수 계약(시그니처·반환형·graceful) 100% 보존** → 호출부(scheduler
`capture_funnel_snapshots` / 라우트 `POST /api/strategy-funnel/snapshot`) diff 0.

핵심 계약:
- insert_snapshot → INSERT ... ON CONFLICT (target_date, strategy_id, step_no) DO UPDATE.
  - JSONB `survived_tickers`(list[str|dict]) / `excluded_sample`(list[dict]) 바인딩.
  - cap: survived 200 / excluded 20 자동 적용 (SURVIVED_TICKERS_CAP/EXCLUDED_SAMPLE_CAP).
  - `is_provisional`(사이클 171) 바인딩 보존.
  - strategy_id 빈 값 → ValueError. 실패 시 None (graceful).
  - RETURNING → upsert row dict | None.
- list_snapshots(target_date, strategy_id?) → SELECT ... WHERE target_date [+ strategy_id]
  ORDER BY step_no → list[dict]. 실패 시 [] (graceful).
- list_recent_by_strategy(strategy_id, days) → days<=0 → []. SELECT ... ORDER BY
  target_date DESC, step_no → list[dict]. 실패 시 [] (graceful).

Red 유효성: production 미변경 → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# insert_snapshot — UPSERT ON CONFLICT (target_date, strategy_id, step_no) + JSONB
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insert_snapshot_uses_pg_upsert_triple_conflict():
    """insert_snapshot → INSERT ... ON CONFLICT (target_date, strategy_id, step_no) DO UPDATE."""
    from src.db import strategy_funnel

    survived = [{"ticker": "005930", "name": "삼성전자"}, "000660"]
    excluded = [{"ticker": "035420", "name": "네이버", "reason": "음봉 비율 초과"}]
    returned = {"id": "uuid-1", "target_date": date(2026, 7, 16), "step_no": 1}
    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=returned)
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        out = await strategy_funnel.insert_snapshot(
            target_date=date(2026, 7, 16),
            strategy_id="donchian_swing",
            step_no=1,
            step_name="원천 유니버스 후보",
            survived_tickers=survived,
            excluded_sample=excluded,
            survived_count=2,
            excluded_count=1,
            is_provisional=True,
        )

    assert out == returned, "insert_snapshot → upsert row dict 반환 계약."
    all_sql = _collect_sql(pg_mod)
    assert any("INSERT INTO strategy_funnel_snapshots" in s for s in all_sql), (
        "INSERT INTO strategy_funnel_snapshots SQL 누락."
    )
    assert any(
        "ON CONFLICT (target_date, strategy_id, step_no) DO UPDATE" in s for s in all_sql
    ), "UPSERT = ON CONFLICT (target_date, strategy_id, step_no) DO UPDATE 누락 (사이클 145)."

    args = _insert_args(pg_mod)
    assert date(2026, 7, 16) in args, "target_date 바인딩 누락."
    assert "donchian_swing" in args, "strategy_id 바인딩 누락."
    assert 1 in args, "step_no 바인딩 누락."
    # JSONB survived_tickers / excluded_sample — list 원본 또는 json.dumps 바인딩
    assert _has_jsonb_binding(args, survived), (
        "survived_tickers JSONB 바인딩 누락 (list 또는 json.dumps)."
    )
    assert _has_jsonb_binding(args, excluded), (
        "excluded_sample JSONB 바인딩 누락 (list[dict] 또는 json.dumps)."
    )
    # is_provisional (사이클 171) 보존
    assert True in args, "is_provisional=True 바인딩 누락 (사이클 171)."


@pytest.mark.asyncio
async def test_insert_snapshot_applies_jsonb_caps():
    """survived 200 / excluded 20 cap 자동 적용 (저장 크기 보호)."""
    from src.db import strategy_funnel

    survived = [f"{i:06d}" for i in range(500)]  # 500 → cap 200
    excluded = [{"ticker": f"{i:06d}", "reason": "x"} for i in range(50)]  # 50 → cap 20
    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await strategy_funnel.insert_snapshot(
            target_date=date(2026, 7, 16),
            strategy_id="vcp_breakout",
            step_no=3,
            step_name="Pullback",
            survived_tickers=survived,
            excluded_sample=excluded,
        )

    args = _insert_args(pg_mod)
    survived_bound = _find_jsonb_list(args, list_of_dicts=False)
    excluded_bound = _find_jsonb_list(args, list_of_dicts=True)
    assert survived_bound is not None and len(survived_bound) == strategy_funnel.SURVIVED_TICKERS_CAP, (
        f"survived_tickers cap {strategy_funnel.SURVIVED_TICKERS_CAP} 자동 적용 위반."
    )
    assert excluded_bound is not None and len(excluded_bound) == strategy_funnel.EXCLUDED_SAMPLE_CAP, (
        f"excluded_sample cap {strategy_funnel.EXCLUDED_SAMPLE_CAP} 자동 적용 위반."
    )


@pytest.mark.asyncio
async def test_insert_snapshot_survived_count_defaults_to_len():
    """survived_count=None → len(survived) 기본 (기존 계약 보존)."""
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await strategy_funnel.insert_snapshot(
            target_date=date(2026, 7, 16),
            strategy_id="bull_flag_breakout",
            step_no=2,
            step_name="폴",
            survived_tickers=["005930", "000660", "035420"],
            survived_count=None,
        )

    args = _insert_args(pg_mod)
    assert 3 in args, "survived_count=None → len(survived)=3 기본값 바인딩 누락."


@pytest.mark.asyncio
async def test_insert_snapshot_empty_strategy_id_raises():
    """strategy_id 빈 값 → ValueError (기존 계약 보존)."""
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        with pytest.raises(ValueError):
            await strategy_funnel.insert_snapshot(
                target_date=date(2026, 7, 16),
                strategy_id="",
                step_no=1,
                step_name="x",
            )


@pytest.mark.asyncio
async def test_insert_snapshot_graceful_none_on_error():
    """DB 예외 시 None (기존 try/except graceful 계약 보존)."""
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("boom"))
        pg_mod.execute = AsyncMock(side_effect=Exception("boom"))
        out = await strategy_funnel.insert_snapshot(
            target_date=date(2026, 7, 16),
            strategy_id="momentum",
            step_no=1,
            step_name="x",
        )

    assert out is None, "insert_snapshot 예외 → None graceful."


# ---------------------------------------------------------------------------
# list_snapshots — SELECT WHERE target_date [+ strategy_id] ORDER BY step_no
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_snapshots_uses_pg_fetch_order_step_no():
    """list_snapshots → pg.fetch(SELECT ... WHERE target_date ORDER BY step_no) → list."""
    from src.db import strategy_funnel

    rows = [{"step_no": 1}, {"step_no": 2}]
    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await strategy_funnel.list_snapshots(
            target_date=date(2026, 7, 16), strategy_id="donchian_swing"
        )

    assert out == rows, "list_snapshots → list[dict] 반환 계약."
    sql = pg_mod.fetch.await_args.args[0]
    assert "strategy_funnel_snapshots" in sql and "SELECT" in sql.upper()
    assert "target_date" in sql, "target_date 필터 누락."
    assert "strategy_id" in sql, "strategy_id 필터 누락 (지정 시)."
    assert "ORDER BY" in sql.upper() and "step_no" in sql, "step_no ASC 정렬 누락."
    passed = pg_mod.fetch.await_args.args[1:]
    assert date(2026, 7, 16) in passed, "target_date 바인딩 누락."
    assert "donchian_swing" in passed, "strategy_id 바인딩 누락."


@pytest.mark.asyncio
async def test_list_snapshots_no_strategy_filter_all():
    """strategy_id=None → 전체 조회 (WHERE 에 strategy_id 미포함)."""
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await strategy_funnel.list_snapshots(target_date=date(2026, 7, 16))

    passed = pg_mod.fetch.await_args.args[1:]
    assert date(2026, 7, 16) in passed, "target_date 바인딩 누락."


@pytest.mark.asyncio
async def test_list_snapshots_graceful_empty_on_error():
    """DB 예외 시 [] (기존 graceful 계약 보존)."""
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        out = await strategy_funnel.list_snapshots(target_date=date(2026, 7, 16))

    assert out == [], "list_snapshots 예외 → 빈 리스트 graceful."


# ---------------------------------------------------------------------------
# list_recent_by_strategy — days<=0 → [] + ORDER BY target_date DESC
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_recent_by_strategy_days_zero_short_circuit():
    """days<=0 → [] (DB 미접근, 기존 계약 보존)."""
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"step_no": 1}])
        out = await strategy_funnel.list_recent_by_strategy("momentum", days=0)

    assert out == [], "days<=0 → [] 계약."
    assert pg_mod.fetch.await_count == 0, "days<=0 시 DB 미접근 계약."


@pytest.mark.asyncio
async def test_list_recent_by_strategy_uses_pg_fetch_order_desc():
    """list_recent_by_strategy → pg.fetch(ORDER BY target_date DESC, step_no) → list."""
    from src.db import strategy_funnel

    rows = [{"target_date": date(2026, 7, 16), "step_no": 1}]
    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await strategy_funnel.list_recent_by_strategy("vcp_breakout", days=7)

    assert out == rows, "list_recent_by_strategy → list[dict] 반환."
    sql = pg_mod.fetch.await_args.args[0]
    assert "strategy_funnel_snapshots" in sql
    assert "ORDER BY" in sql.upper() and "DESC" in sql.upper(), "target_date DESC 정렬 누락."
    assert "vcp_breakout" in pg_mod.fetch.await_args.args[1:], "strategy_id 바인딩 누락."


@pytest.mark.asyncio
async def test_list_recent_by_strategy_graceful_empty_on_error():
    """DB 예외 시 [] (기존 graceful 계약 보존)."""
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        out = await strategy_funnel.list_recent_by_strategy("momentum", days=7)

    assert out == [], "list_recent_by_strategy 예외 → 빈 리스트 graceful."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase 미참조
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_funnel_no_supabase_reference_after_transition():
    """전환 후 strategy_funnel.py 는 supabase 를 참조하지 않는다 (pg 단독)."""
    from src.db import strategy_funnel

    assert not hasattr(strategy_funnel, "supabase"), (
        "전환 후 strategy_funnel 모듈에 supabase 심볼이 남으면 안 됨 (pg 단독 전환)."
    )
    assert hasattr(strategy_funnel, "pg"), "strategy_funnel 이 src.db.pg 를 import 해야 함."


# ---------------------------------------------------------------------------
# 헬퍼 — 발화 경로(fetchrow/execute/fetch) SQL·인자 수집 (Green 자유도)
# ---------------------------------------------------------------------------
def _collect_sql(pg_mod) -> list[str]:
    sqls: list[str] = []
    for name in ("fetchrow", "execute", "fetch"):
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
    """JSONB 컬럼 바인딩이 list/dict 원본 또는 json.dumps 문자열로 포함되는지 (cap 적용 후 접두 일치)."""
    dumped = json.dumps(expected)
    for a in args:
        if a == expected:
            return True
        if isinstance(a, str) and a == dumped:
            return True
        # cap 미초과 시 원본과 동일, 초과 시 별도 테스트에서 검증
    return False


def _find_jsonb_list(args: tuple, *, list_of_dicts: bool):
    """바인딩 인자 중 list (또는 그 json.dumps) 를 찾아 파이썬 list 로 반환.

    list_of_dicts=True → 원소가 dict 인 list (excluded_sample).
    False → 원소가 str 또는 dict 인 list (survived_tickers).
    """
    for a in args:
        val = a
        if isinstance(a, str):
            try:
                val = json.loads(a)
            except Exception:
                continue
        if isinstance(val, list) and val:
            first = val[0]
            if list_of_dicts and isinstance(first, dict) and "reason" in first:
                return val
            if not list_of_dicts and isinstance(first, str):
                return val
    return None
