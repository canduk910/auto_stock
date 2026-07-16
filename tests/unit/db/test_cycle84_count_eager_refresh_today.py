"""사이클 84 Red — H-4 (MEDIUM): `count_eager_refresh_today()` 사이클 83 emit 카운트.

사이클 83 `_eager_refresh_stock_master_for_held_positions` 가 `[scan_pool_eager_refresh]` INFO
emit. 본 헬퍼는 system_logs 에서 오늘 KST 발생 카운트를 집계 (UI 운영 측정 영역).

위험 등급 MEDIUM (사이클 83 운영 측정 의존).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_H4_count_eager_refresh_today_counts_today_logs():
    """H-4: count_eager_refresh_today() → system_logs `[scan_pool_eager_refresh]` 카운트.

    사이클 M2b — pg.fetchval 경유 (3 prefix ilike + KST 범위, 사이클 100 3 prefix OR).
    각 prefix 당 fetchval 1회 → 합산.
    """
    from src.db import stock_master

    counter = getattr(stock_master, "count_eager_refresh_today", None)
    assert counter is not None, "stock_master.count_eager_refresh_today 헬퍼 미작성 의무"

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=5)
        cnt = await counter()

    assert isinstance(cnt, int), f"int 반환 의무 (실제 {type(cnt).__name__})"
    assert cnt >= 0, f"음수 결함 (실제 {cnt})"
    # 3 prefix 각각 별도 쿼리 → 합산 (5 × 3 = 15)
    assert cnt == 15, f"3 prefix 합산 의무 (5×3=15). 실제 {cnt}"
    assert pg_mod.fetchval.await_count == 3, "3 prefix 각각 fetchval 발화 의무"
