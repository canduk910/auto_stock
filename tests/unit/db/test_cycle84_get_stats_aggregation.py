"""사이클 84 Red — H-2 (MEDIUM): `get_stats()` 집계 정확성.

UI 사이클 85 상태 영역 (count_all / bfdy_clpr_present / nxt_tradable_count / top_10_recent).

위험 등급 MEDIUM (UI 진단 가시화).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_H2_get_stats_returns_required_keys():
    """H-2: get_stats() 응답에 필수 4 키 존재.

    사이클 M2b — pg.fetchval (4+ 카운트) + pg.fetch (top_10_recent) 경유 +
    stock_master_daily 연동 (count_all/max_bas_dd) graceful mock.
    """
    from src.db import stock_master

    get_stats = getattr(stock_master, "get_stats", None)
    assert get_stats is not None, "stock_master.get_stats 헬퍼 미작성 의무"

    top10 = [
        {"ticker": "005930", "name": "삼성전자", "refreshed_at": "2026-06-09T09:00:00+09:00"},
        {"ticker": "000660", "name": "SK하이닉스", "refreshed_at": "2026-06-09T09:00:00+09:00"},
    ]

    with patch.object(stock_master, "pg", create=True) as pg_mod, \
            patch("src.db.stock_master_daily.count_all", new=AsyncMock(return_value=100)), \
            patch("src.db.stock_master_daily.max_bas_dd", new=AsyncMock(return_value=None)):
        pg_mod.fetchval = AsyncMock(return_value=3)
        pg_mod.fetch = AsyncMock(return_value=top10)
        stats = await get_stats()

    required_keys = {"count_all", "bfdy_clpr_present", "nxt_tradable_count", "top_10_recent"}
    missing = required_keys - set(stats.keys())
    assert not missing, f"get_stats() 필수 키 누락: {missing} (실제 keys={list(stats.keys())})"
    assert isinstance(stats["top_10_recent"], list), "top_10_recent 는 list 타입 의무"
