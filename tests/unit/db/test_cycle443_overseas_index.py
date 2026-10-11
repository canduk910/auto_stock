"""cycle443 — overseas_index_daily CRUD 회귀 가드 (ndx2x_riskoff 신호 원천).

패턴 = `test_cycle122_stock_master_daily.py` 답습(`patch.object(module, "pg", create=True)`).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.db import overseas_index

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_upsert_many_empty_rows_is_noop():
    with patch.object(overseas_index, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        n = await overseas_index.upsert_many("NDX", [])
    assert n == 0
    pg_mod.executemany.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_many_binds_date_and_sends_all_rows():
    rows = [("20261009", 25000.12), ("20261008", 24900.0)]
    with patch.object(overseas_index, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        n = await overseas_index.upsert_many("NDX", rows)
    assert n == 2
    sql, args_list = pg_mod.executemany.await_args.args
    assert "ON CONFLICT (index_code, bas_dd) DO UPDATE" in sql
    assert args_list[0][0] == "NDX"
    assert args_list[0][1] == date(2026, 10, 9)
    assert args_list[0][2] == 25000.12


@pytest.mark.asyncio
async def test_upsert_many_db_exception_is_graceful():
    with patch.object(overseas_index, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock(side_effect=RuntimeError("pg down"))
        n = await overseas_index.upsert_many("NDX", [("20261009", 100.0)])
    assert n == 0


@pytest.mark.asyncio
async def test_get_recent_closes_returns_ascending_order():
    """DB 는 DESC 로 가져오지만, 함수는 지표 계산 입력 순서(오름차순)로 뒤집어 돌린다."""
    mock_rows = [
        {"bas_dd": date(2026, 10, 9), "close_price": 3},
        {"bas_dd": date(2026, 10, 8), "close_price": 2},
        {"bas_dd": date(2026, 10, 7), "close_price": 1},
    ]
    with patch.object(overseas_index, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=mock_rows)
        out = await overseas_index.get_recent_closes("NDX", limit=3)
    assert out == [
        (date(2026, 10, 7), 1.0), (date(2026, 10, 8), 2.0), (date(2026, 10, 9), 3.0),
    ]


@pytest.mark.asyncio
async def test_get_recent_closes_db_exception_returns_empty_list():
    with patch.object(overseas_index, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=RuntimeError("pg down"))
        out = await overseas_index.get_recent_closes("NDX")
    assert out == []


@pytest.mark.asyncio
async def test_get_latest_date_passthrough():
    with patch.object(overseas_index, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=date(2026, 10, 9))
        out = await overseas_index.get_latest_date("NDX")
    assert out == date(2026, 10, 9)


@pytest.mark.asyncio
async def test_get_latest_date_db_exception_returns_none():
    with patch.object(overseas_index, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=RuntimeError("pg down"))
        out = await overseas_index.get_latest_date("NDX")
    assert out is None
