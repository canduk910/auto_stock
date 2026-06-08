"""사이클 84 Red — H-3 (MEDIUM): `list_history(ticker, limit)` ticker filter + changed_at DESC.

UI 사이클 85 ticker detail 영역 변경 이력 조회 (Q1=B 영역).

위험 등급 MEDIUM (UI 변경 이력 가시화).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_H3_list_history_filters_by_ticker_and_orders_desc():
    """H-3: list_history(ticker) → ticker eq + changed_at DESC + limit 적용."""
    from src.db import stock_master

    list_history = getattr(stock_master, "list_history", None)
    assert list_history is not None, (
        "stock_master.list_history 헬퍼 미작성 — backend-dev Green 단계 의무"
    )

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
    fake_result = MagicMock()
    fake_result.data = fake_rows

    with patch("src.db.stock_master.supabase") as mock_supabase:
        chain = mock_supabase.table.return_value
        chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = fake_result
        chain.select.return_value.eq.return_value.order.return_value.execute.return_value = fake_result

        rows = await list_history("005930", limit=50)

    assert len(rows) == 3, f"3건 의무 (실제 {len(rows)})"
    # changed_at DESC 정렬 (최신 → 과거)
    timestamps = [r["changed_at"] for r in rows]
    assert timestamps == sorted(timestamps, reverse=True), (
        f"changed_at DESC 정렬 의무 (실제 순서={timestamps})"
    )
    # ticker filter
    assert all(r["ticker"] == "005930" for r in rows), "ticker eq filter 의무"
