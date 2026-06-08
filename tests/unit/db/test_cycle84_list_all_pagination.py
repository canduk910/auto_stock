"""사이클 84 Red — H-1 (MEDIUM): `list_all(limit, offset)` 페이징 정합.

UI 사이클 85 list 영역 페이징 100건 단위 호출. limit=100 / offset=0 default.

위험 등급 MEDIUM (UI list 영역 정합성).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_H1_list_all_default_pagination():
    """H-1-A: list_all() 디폴트 limit=100 offset=0."""
    from src.db import stock_master

    list_all = getattr(stock_master, "list_all", None)
    assert list_all is not None, (
        "stock_master.list_all 헬퍼 미작성 — backend-dev Green 단계 의무"
    )

    fake_result = MagicMock()
    fake_result.data = [
        {"ticker": f"00{i:04d}", "name": f"종목{i}", "excg_dvsn_cd": "STK",
         "nxt_tradable": True, "krx_halted": False, "admin_item": False,
         "raw": {}, "refreshed_at": "2026-06-09T09:00:00+09:00"}
        for i in range(100)
    ]

    with patch("src.db.stock_master.supabase") as mock_supabase:
        chain = mock_supabase.table.return_value
        chain.select.return_value.order.return_value.range.return_value.execute.return_value = fake_result
        chain.select.return_value.range.return_value.execute.return_value = fake_result
        chain.select.return_value.order.return_value.limit.return_value.offset.return_value.execute.return_value = fake_result
        chain.select.return_value.limit.return_value.offset.return_value.execute.return_value = fake_result

        rows = await list_all()

    assert len(rows) == 100, f"디폴트 limit=100 의무 (실제 {len(rows)})"


@pytest.mark.asyncio
async def test_H1_list_all_custom_limit_offset():
    """H-1-B: list_all(limit=50, offset=100) 명시 인자 정합."""
    from src.db import stock_master

    list_all = getattr(stock_master, "list_all", None)
    assert list_all is not None

    fake_result = MagicMock()
    fake_result.data = [
        {"ticker": f"99{i:04d}", "name": f"종목{i}", "excg_dvsn_cd": "STK",
         "nxt_tradable": False, "krx_halted": False, "admin_item": False,
         "raw": {}, "refreshed_at": "2026-06-09T09:00:00+09:00"}
        for i in range(50)
    ]

    with patch("src.db.stock_master.supabase") as mock_supabase:
        chain = mock_supabase.table.return_value
        chain.select.return_value.order.return_value.range.return_value.execute.return_value = fake_result
        chain.select.return_value.range.return_value.execute.return_value = fake_result
        chain.select.return_value.order.return_value.limit.return_value.offset.return_value.execute.return_value = fake_result
        chain.select.return_value.limit.return_value.offset.return_value.execute.return_value = fake_result

        rows = await list_all(limit=50, offset=100)

    assert len(rows) == 50, f"limit=50 의무 (실제 {len(rows)})"
