"""cycle461 L4 — `trade_history.get_open_roundtrip_owner` · `get_open_roundtrip_first_buy_date` 실 Postgres.

단위 쌍 = `tests/unit/engine/test_cycle461_unknown_holding.py`(fetchrow 스텁) — 이 파일은 SQL 자체
(스칼라 서브쿼리 · `ANY($n::text[])` · `'-infinity'::timestamptz`)를 실 PG 로 검증한다.

docker / `DATABASE_URL_TEST` 가 없으면 `pg_harness` fixture 가 `pytest.skip` 한다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

KST = timezone(timedelta(hours=9))
T = "123450"


def _at(d: int, h: int = 10) -> datetime:
    return datetime(2026, 10, d, h, 0, tzinfo=KST)


@pytest.fixture
async def clean_trades(pg_pool):
    await pg_pool.execute("DELETE FROM trade_history WHERE ticker = $1", T)
    yield pg_pool
    await pg_pool.execute("DELETE FROM trade_history WHERE ticker = $1", T)


async def _ins(pool, trade_type, strategy, ts, status="COMPLETED", order_no=None):
    await pool.execute(
        "INSERT INTO trade_history (ticker, ticker_name, trade_type, price, quantity, strategy, status, order_no, timestamp) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        T, "시험", trade_type, 10_000, 1, strategy, status, order_no or f"{trade_type}{ts:%d%H}", ts,
    )


@pytest.mark.asyncio
async def test_no_rows_is_none(clean_trades) -> None:
    from src.db import trade_history as th
    assert await th.get_open_roundtrip_owner(T) == ("none", None)
    assert await th.get_open_roundtrip_first_buy_date(T) is None


@pytest.mark.asyncio
async def test_open_roundtrip_found_with_first_buy_date(clean_trades) -> None:
    from src.db import trade_history as th
    await _ins(clean_trades, "BUY", "kojiro", _at(1))
    await _ins(clean_trades, "SELL", "kojiro", _at(2))
    await _ins(clean_trades, "BUY", "donchian_swing", _at(5))
    await _ins(clean_trades, "BUY", "donchian_swing", _at(6), status="PARTIAL")
    assert await th.get_open_roundtrip_owner(T) == ("found", "donchian_swing")
    assert await th.get_open_roundtrip_first_buy_date(T) == date(2026, 10, 5)


@pytest.mark.asyncio
async def test_closed_roundtrip_is_none(clean_trades) -> None:
    from src.db import trade_history as th
    await _ins(clean_trades, "BUY", "kojiro", _at(1))
    await _ins(clean_trades, "SELL", "kojiro", _at(2))
    assert await th.get_open_roundtrip_owner(T) == ("none", None)
    assert await th.get_open_roundtrip_first_buy_date(T) is None


@pytest.mark.asyncio
async def test_cancelled_rows_are_ignored(clean_trades) -> None:
    from src.db import trade_history as th
    await _ins(clean_trades, "BUY", "kojiro", _at(1))
    await _ins(clean_trades, "SELL", "kojiro", _at(2), status="CANCELLED")  # 체결 안 된 매도
    await _ins(clean_trades, "BUY", "vcp_breakout", _at(3), status="CANCELLED")
    assert await th.get_open_roundtrip_owner(T) == ("found", "kojiro")
    assert await th.get_open_roundtrip_first_buy_date(T) == date(2026, 10, 1)


@pytest.mark.asyncio
async def test_kst_date_boundary(clean_trades) -> None:
    """KST 00:30 매수(UTC 로는 전날) — 날짜는 KST 로 읽는다."""
    from src.db import trade_history as th
    await _ins(clean_trades, "BUY", "kojiro", datetime(2026, 10, 8, 0, 30, tzinfo=KST))
    assert await th.get_open_roundtrip_first_buy_date(T) == date(2026, 10, 8)
