"""사이클 84 Red — H-3 (MEDIUM): `list_history(ticker, limit)` ticker filter + changed_at DESC.

UI 사이클 85 ticker detail 영역 변경 이력 조회 (Q1=B 영역).

위험 등급 MEDIUM (UI 변경 이력 가시화).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_H3_list_history_filters_by_ticker_and_orders_desc():
    """H-3: list_history(ticker) → ticker eq + changed_at DESC + limit 적용.

    사이클 M2b — pg.fetch 경유. DESC 정렬은 DB(ORDER BY changed_at DESC)가 수행 →
    fake 는 이미 DESC 정렬된 rows 를 pass-through (production 이 fetch 결과를 그대로 반환).
    """
    from src.db import stock_master

    list_history = getattr(stock_master, "list_history", None)
    assert list_history is not None, "stock_master.list_history 헬퍼 미작성 의무"

    fake_rows = [
        {"id": 3, "ticker": "005930", "change_type": "TTL_REFRESH",
         "before_raw": {"a": 1}, "after_raw": {"a": 1},
         "changed_at": "2026-06-09T09:30:00+09:00"},
        {"id": 2, "ticker": "005930", "change_type": "UPDATE",
         "before_raw": {"a": 1}, "after_raw": {"a": 2},
         "changed_at": "2026-06-09T09:15:00+09:00"},
        {"id": 1, "ticker": "005930", "change_type": "INSERT",
         "before_raw": None, "after_raw": {"a": 1},
         "changed_at": "2026-06-09T09:00:00+09:00"},
    ]

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=fake_rows)
        rows = await list_history("005930", limit=50)

    # ticker + limit 이 pg.fetch 에 바인딩 (WHERE ticker=$1 ... LIMIT $2)
    args = pg_mod.fetch.await_args.args[1:]
    assert "005930" in args and 50 in args, f"ticker/limit 바인딩 누락: {args}"
    sql = pg_mod.fetch.await_args.args[0].upper()
    assert "ORDER BY" in sql and "DESC" in sql, "changed_at DESC 정렬 누락"

    assert len(rows) == 3, f"3건 의무 (실제 {len(rows)})"
    # changed_at DESC 정렬 (최신 → 과거)
    timestamps = [r["changed_at"] for r in rows]
    assert timestamps == sorted(timestamps, reverse=True), (
        f"changed_at DESC 정렬 의무 (실제 순서={timestamps})"
    )
    # ticker filter
    assert all(r["ticker"] == "005930" for r in rows), "ticker eq filter 의무"
