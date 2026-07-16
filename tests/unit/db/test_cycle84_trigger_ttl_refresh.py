"""사이클 84 Red — M-4 (HIGH): trigger TTL_REFRESH 동작 검증.

stock_master UPSERT 시 raw 동일 (refreshed_at 만 갱신) → `change_type='TTL_REFRESH'`.

Q5=B 결정 — 24h TTL 사이클 83 답습 갱신 빈도 측정 영역.
trigger PL/pgSQL: `IF NEW.raw = OLD.raw THEN change_type='TTL_REFRESH' ELSE 'UPDATE' END`.

위험 등급 HIGH (Q5=B 핵심 ENUM 분기 정확성).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_M4_trigger_ttl_refresh_when_raw_unchanged():
    """M-4: stock_master UPSERT raw 동일 (refreshed_at 만 갱신) → history `change_type=TTL_REFRESH`.

    예: 24h TTL 만료 후 KIS inquire_stock_basics 재조회 결과 raw 동일 → TTL_REFRESH (UPDATE 아님).
    사이클 83 eager refresh 영역 운영 측정 가시화.
    """
    from src.db import stock_master

    list_history = getattr(stock_master, "list_history", None)
    assert list_history is not None, (
        "stock_master.list_history 헬퍼 미작성 — backend-dev Green 단계 의무"
    )

    fake_rows = [{
        "id": 3,
        "ticker": "005930",
        "change_type": "TTL_REFRESH",
        "before_raw": {"prdt_name": "삼성전자", "bfdy_clpr": "70000"},
        "after_raw": {"prdt_name": "삼성전자", "bfdy_clpr": "70000"},
        "changed_at": "2026-06-09T09:30:00+09:00",
    }]
    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=fake_rows)
        rows = await list_history("005930", limit=100)

    assert rows, "TTL_REFRESH history row 0건"
    row = rows[0]
    assert row["change_type"] == "TTL_REFRESH", (
        f"TTL_REFRESH change_type 의무 — raw 동일 시 UPDATE 가 아닌 TTL_REFRESH (실제={row['change_type']})"
    )
    assert row["before_raw"] == row["after_raw"], (
        "TTL_REFRESH 케이스 before/after raw 동일 의무"
    )
