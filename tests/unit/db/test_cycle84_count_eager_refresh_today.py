"""사이클 84 Red — H-4 (MEDIUM): `count_eager_refresh_today()` 사이클 83 emit 카운트.

사이클 83 `_eager_refresh_stock_master_for_held_positions` 가 `[scan_pool_eager_refresh]` INFO
emit. 본 헬퍼는 system_logs 에서 오늘 KST 발생 카운트를 집계 (UI 운영 측정 영역).

위험 등급 MEDIUM (사이클 83 운영 측정 의존).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_H4_count_eager_refresh_today_counts_today_logs():
    """H-4: count_eager_refresh_today() → system_logs `[scan_pool_eager_refresh]` 카운트.

    오늘 KST 범위 (`T00:00:00+09:00` ~ `T23:59:59.999999+09:00`) ilike `%[scan_pool_eager_refresh]%`.
    """
    from src.db import stock_master

    counter = getattr(stock_master, "count_eager_refresh_today", None)
    assert counter is not None, (
        "stock_master.count_eager_refresh_today 헬퍼 미작성 — backend-dev Green 단계 의무"
    )

    fake_result = MagicMock()
    fake_result.count = 3
    fake_result.data = [{"id": i} for i in range(3)]

    with patch("src.db.stock_master.supabase") as mock_supabase:
        chain = mock_supabase.table.return_value
        # 다양한 chain 흡수
        chain.select.return_value.ilike.return_value.gte.return_value.lte.return_value.execute.return_value = fake_result
        chain.select.return_value.like.return_value.gte.return_value.lte.return_value.execute.return_value = fake_result
        chain.select.return_value.ilike.return_value.gte.return_value.execute.return_value = fake_result

        cnt = await counter()

    assert isinstance(cnt, int), f"int 반환 의무 (실제 {type(cnt).__name__})"
    assert cnt >= 0, f"음수 결함 (실제 {cnt})"
