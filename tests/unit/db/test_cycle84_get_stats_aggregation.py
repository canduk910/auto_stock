"""사이클 84 Red — H-2 (MEDIUM): `get_stats()` 집계 정확성.

UI 사이클 85 상태 영역 (count_all / bfdy_clpr_present / nxt_tradable_count / top_10_recent).

위험 등급 MEDIUM (UI 진단 가시화).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_H2_get_stats_returns_required_keys():
    """H-2: get_stats() 응답에 필수 4 키 존재."""
    from src.db import stock_master

    get_stats = getattr(stock_master, "get_stats", None)
    assert get_stats is not None, (
        "stock_master.get_stats 헬퍼 미작성 — backend-dev Green 단계 의무"
    )

    # 다양한 chain 패턴 흡수 (구현 자유도 보장)
    fake_all = MagicMock()
    fake_all.data = [
        {"ticker": "005930", "nxt_tradable": True,
         "raw": {"bfdy_clpr": "70000"}, "refreshed_at": "2026-06-09T09:00:00+09:00"},
        {"ticker": "000660", "nxt_tradable": True,
         "raw": {"bfdy_clpr": "100000"}, "refreshed_at": "2026-06-09T09:00:00+09:00"},
        {"ticker": "035720", "nxt_tradable": False,
         "raw": {}, "refreshed_at": "2026-06-09T09:00:00+09:00"},
    ]

    with patch("src.db.stock_master.supabase") as mock_supabase:
        chain = mock_supabase.table.return_value
        # 다양한 select chain 흡수
        chain.select.return_value.execute.return_value = fake_all
        chain.select.return_value.order.return_value.execute.return_value = fake_all
        chain.select.return_value.order.return_value.limit.return_value.execute.return_value = fake_all

        stats = await get_stats()

    required_keys = {"count_all", "bfdy_clpr_present", "nxt_tradable_count", "top_10_recent"}
    missing = required_keys - set(stats.keys())
    assert not missing, f"get_stats() 필수 키 누락: {missing} (실제 keys={list(stats.keys())})"
    assert isinstance(stats["top_10_recent"], list), "top_10_recent 는 list 타입 의무"
