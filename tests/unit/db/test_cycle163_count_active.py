"""사이클 163 (2026-06-18) — stock_master.count_active() 신규 회귀 가드.

의제 #5 영역 — _boot prepare 호출 *전* 가드 헬퍼.
사이클 128 count="exact" 패턴 답습 (PostgREST 1000행 silent cap 회피).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_G163_COUNT_1_count_active_returns_int():
    """G-163-COUNT-1: count_active() 정상 응답 = count(*) 반환.

    사이클 M2b — pg.fetchval("SELECT count(*) FROM stock_master") 경유.
    """
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=2768)
        cnt = await stock_master.count_active()

    assert cnt == 2768
    # count(*) SELECT 사용 검증
    sql = pg_mod.fetchval.await_args.args[0].lower()
    assert "count(" in sql and "stock_master" in sql, "count(*) SELECT 누락"


@pytest.mark.asyncio
async def test_G163_COUNT_2_count_active_exception_returns_zero():
    """G-163-COUNT-2: count_active() 예외 → 0 폴백 graceful.

    사이클 88 G-REJECT graceful 영속 답습.
    """
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=RuntimeError("pg ConnectionTerminated"))
        cnt = await stock_master.count_active()

    assert cnt == 0
