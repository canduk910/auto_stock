"""사이클 84 Red — H-1 (MEDIUM): `list_all(limit, offset)` 페이징 정합.

UI 사이클 85 list 영역 페이징 100건 단위 호출. limit=100 / offset=0 default.

위험 등급 MEDIUM (UI list 영역 정합성).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _rows(n: int, prefix: str = "00") -> list[dict]:
    return [
        {"ticker": f"{prefix}{i:04d}", "name": f"종목{i}", "excg_dvsn_cd": "STK",
         "nxt_tradable": True, "krx_halted": False, "admin_item": False,
         "raw": {}, "refreshed_at": "2026-06-09T09:00:00+09:00"}
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_H1_list_all_default_pagination():
    """H-1-A: list_all() 디폴트 limit=100 offset=0.

    사이클 M2b — pg.fetch 경유. LIMIT/OFFSET 페이징 (range→LIMIT/OFFSET 전환).
    """
    from src.db import stock_master

    list_all = getattr(stock_master, "list_all", None)
    assert list_all is not None, "stock_master.list_all 헬퍼 미작성 의무"

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=_rows(100))
        rows = await list_all()

    assert len(rows) == 100, f"디폴트 limit=100 의무 (실제 {len(rows)})"
    # 디폴트 인자 (limit=100, offset=0) 가 pg.fetch 에 바인딩
    args = pg_mod.fetch.await_args.args[1:]
    assert 100 in args and 0 in args, f"디폴트 limit=100/offset=0 바인딩 누락: {args}"
    sql = pg_mod.fetch.await_args.args[0].upper()
    assert "LIMIT" in sql and "OFFSET" in sql, "range → LIMIT/OFFSET 전환 누락"


@pytest.mark.asyncio
async def test_H1_list_all_custom_limit_offset():
    """H-1-B: list_all(limit=50, offset=100) 명시 인자 정합 (pg.fetch 바인딩)."""
    from src.db import stock_master

    list_all = getattr(stock_master, "list_all", None)
    assert list_all is not None

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=_rows(50, prefix="99"))
        rows = await list_all(limit=50, offset=100)

    assert len(rows) == 50, f"limit=50 의무 (실제 {len(rows)})"
    args = pg_mod.fetch.await_args.args[1:]
    assert 50 in args and 100 in args, f"명시 limit=50/offset=100 바인딩 누락: {args}"
