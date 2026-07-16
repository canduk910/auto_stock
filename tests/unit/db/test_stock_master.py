"""Phase G Red — `src/db/stock_master.py` CRUD + 24h staleness.

종목 마스터 캐시. CTPF1002R 1건 조회 → upsert. 24시간 TTL 로 stale 판정.

요구 행위:

1. `upsert_one(StockBasics)` — ticker PK upsert. refreshed_at 은 now() 로 자동 세팅.
2. `get(ticker)` — 미존재 시 `None`, 존재 시 `StockBasics` 반환.
3. `is_stale(ticker, max_age_hours=24)` — 미존재/24h 초과면 True.
4. read/write 는 `src.db.pg` (asyncpg) 헬퍼 경유.

테스트 더블 (사이클 M2b — Supabase→RDS asyncpg 전환):
- `src.db.stock_master.pg` 를 stateful `fake_pg_stock_master` 로 monkeypatch
  (upsert_one → get → is_stale round-trip 계약을 pg.execute/fetchrow/fetch 로 흉내).
- `freezegun` 으로 refreshed_at 시각을 통제해 stale 판정 검증.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit


def _basics(
    ticker: str = "012200",
    *,
    name: str = "계양전기",
    nxt_tradable: bool = True,
    krx_halted: bool = False,
    admin_item: bool = False,
    excg: str = "02",
):
    """StockBasics 인스턴스 — 모델 import 는 테스트 시점에 lazy 로 수행."""
    from src.models.stock import StockBasics

    return StockBasics(
        ticker=ticker,
        name=name,
        excg_dvsn_cd=excg,
        nxt_tradable=nxt_tradable,
        krx_halted=krx_halted,
        admin_item=admin_item,
        raw={"pdno": ticker},
    )


@pytest.mark.asyncio
async def test_upsert_one_and_get_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_stock_master,
):
    """upsert 후 get 라운드트립."""
    from src.db import stock_master

    monkeypatch.setattr(stock_master, "pg", fake_pg_stock_master)

    await stock_master.upsert_one(_basics("012200", name="계양전기", nxt_tradable=True))

    loaded = await stock_master.get("012200")
    assert loaded is not None
    assert loaded.ticker == "012200"
    assert loaded.nxt_tradable is True


@pytest.mark.asyncio
async def test_get_returns_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_stock_master,
):
    from src.db import stock_master

    monkeypatch.setattr(stock_master, "pg", fake_pg_stock_master)

    loaded = await stock_master.get("999999")
    assert loaded is None


@pytest.mark.asyncio
async def test_is_stale_when_missing_then_true(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_stock_master,
):
    from src.db import stock_master

    monkeypatch.setattr(stock_master, "pg", fake_pg_stock_master)

    assert await stock_master.is_stale("999999") is True


@pytest.mark.asyncio
async def test_is_stale_when_recent_then_false(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_stock_master,
):
    from src.db import stock_master

    monkeypatch.setattr(stock_master, "pg", fake_pg_stock_master)

    with freeze_time("2026-05-11 09:00:00", tz_offset=9):
        await stock_master.upsert_one(_basics("012200"))

    # 1시간 후 — 24h 이내이므로 fresh
    with freeze_time("2026-05-11 10:00:00", tz_offset=9):
        assert await stock_master.is_stale("012200", max_age_hours=24) is False


@pytest.mark.asyncio
async def test_is_stale_when_older_than_24h_then_true(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_stock_master,
):
    from src.db import stock_master

    monkeypatch.setattr(stock_master, "pg", fake_pg_stock_master)

    with freeze_time("2026-05-10 09:00:00", tz_offset=9):
        await stock_master.upsert_one(_basics("012200"))

    # 25시간 후 — 24h 초과
    with freeze_time("2026-05-11 10:00:00", tz_offset=9):
        assert await stock_master.is_stale("012200", max_age_hours=24) is True


@pytest.mark.asyncio
async def test_upsert_updates_existing_row(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_stock_master,
):
    """동일 ticker 재 upsert 시 갱신 (행 중복 없음)."""
    from src.db import stock_master

    monkeypatch.setattr(stock_master, "pg", fake_pg_stock_master)

    await stock_master.upsert_one(_basics("012200", nxt_tradable=True))
    await stock_master.upsert_one(_basics("012200", nxt_tradable=False))

    loaded = await stock_master.get("012200")
    assert loaded is not None
    assert loaded.nxt_tradable is False
    # store 직접 어설션 — 동일 ticker 행은 1개 (ticker PK upsert)
    assert sum(1 for t in fake_pg_stock_master.store if t == "012200") == 1
