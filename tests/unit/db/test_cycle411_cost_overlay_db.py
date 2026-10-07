"""cycle411 Red — DB 읽기 두 가지 (가산형, 저장값·마이그레이션 무변경).

명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` §설계.

| # | 계약 |
|---|---|
| P1 | `get_trade_pairs` closed 페어에 체결 행 id 병행 리스트 `buy_trade_ids`·`sell_trade_ids`(시간순) |
| P2 | open 페어는 `buy_trade_ids` = 남은 매수 행 id · `sell_trade_ids` = `[]`(None 아님) |
| P3 | 기존 칸(`buy_order_nos`·`profit_loss`·`pair_key` …)은 그대로 — id 가 없는 행은 목록에서만 빠진다 |
| B1 | `trade_cost.get_trades_by_status(start, end, statuses)` = 상태 목록을 `ANY($n::text[])` 로 받아 KST 날짜 `trade_date` 와 `id`·`ticker_name`·`order_price` 를 함께 읽는다 |
| B2 | 기존 `get_completed_trades` 는 그대로 COMPLETED 만 본다(실비용 요약 행위 보존) |
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.db import trade_history

pytestmark = pytest.mark.asyncio


def _row(tid, tt, price, qty, ts, *, pl=None, ono="", ticker="005930", strategy="momentum"):
    return {
        "id": tid, "ticker": ticker, "ticker_name": "삼성전자", "strategy": strategy,
        "trade_type": tt, "price": Decimal(str(price)), "quantity": qty, "profit_loss": pl,
        "timestamp": ts, "status": "COMPLETED", "order_no": ono,
    }


async def _pairs(rows):
    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        return await trade_history.get_trade_pairs()


async def test_p1_closed_pair_carries_trade_id_lists_in_time_order():
    rows = [
        _row(11, "BUY", 70000, 4, "2026-10-06T09:01:00+09:00", ono="B1"),
        _row(12, "BUY", 70100, 6, "2026-10-06T09:05:00+09:00", ono="B2"),
        _row(15, "SELL", 72000, 10, "2026-10-07T10:00:00+09:00", pl=Decimal("19400"), ono="S1"),
    ]
    (p,) = await _pairs(rows)
    assert p["status"] == "closed"
    assert p["buy_trade_ids"] == [11, 12]
    assert p["sell_trade_ids"] == [15]
    # P3 — 기존 칸 불변
    assert p["buy_order_nos"] == ["B1", "B2"]
    assert p["sell_order_nos"] == ["S1"]
    assert p["profit_loss"] == 19400
    assert p["pair_key"] == "momentum:005930:B1"


async def test_p2_open_pair_has_buy_ids_and_empty_sell_ids():
    rows = [
        _row(21, "BUY", 70000, 4, "2026-10-06T09:01:00+09:00", ono="B1"),
        _row(22, "SELL", 71000, 4, "2026-10-06T10:00:00+09:00", pl=Decimal("4000"), ono="S1"),
        _row(23, "BUY", 70500, 2, "2026-10-07T09:01:00+09:00", ono="B3"),
    ]
    pairs = await _pairs(rows)
    open_ = [p for p in pairs if p["status"] == "open"]
    closed = [p for p in pairs if p["status"] == "closed"]
    assert len(open_) == 1 and len(closed) == 1
    assert open_[0]["buy_trade_ids"] == [23]
    assert open_[0]["sell_trade_ids"] == []
    assert closed[0]["buy_trade_ids"] == [21]
    assert closed[0]["sell_trade_ids"] == [22]


async def test_p3_rows_without_id_only_drop_from_list():
    rows = [
        _row(None, "BUY", 70000, 4, "2026-10-06T09:01:00+09:00", ono="B1"),
        _row(32, "SELL", 71000, 4, "2026-10-06T10:00:00+09:00", pl=Decimal("4000"), ono="S1"),
    ]
    (p,) = await _pairs(rows)
    assert p["buy_trade_ids"] == []
    assert p["sell_trade_ids"] == [32]
    assert p["profit_loss"] == 4000


async def test_b1_get_trades_by_status_binds_status_list_and_selects_ids():
    from src.db import trade_cost as trade_cost_db

    fake = AsyncMock(return_value=[{"id": 1}])
    with patch.object(trade_cost_db.pg, "fetch", fake):
        out = await trade_cost_db.get_trades_by_status(
            date(2026, 10, 1), date(2026, 10, 8), ["COMPLETED", "PARTIAL"])
    assert out == [{"id": 1}]
    sql = fake.await_args.args[0]
    args = fake.await_args.args[1:]
    assert "ANY(" in sql and "::text[]" in sql
    assert ["COMPLETED", "PARTIAL"] in [list(a) for a in args if isinstance(a, (list, tuple))]
    for col in ("id", "ticker_name", "order_price", "trade_date", "status"):
        assert col in sql, col
    assert "Asia/Seoul" in sql


async def test_b2_get_completed_trades_still_completed_only():
    from src.db import trade_cost as trade_cost_db

    fake = AsyncMock(return_value=[])
    with patch.object(trade_cost_db.pg, "fetch", fake):
        await trade_cost_db.get_completed_trades(date(2026, 10, 1), date(2026, 10, 8))
    assert "status = 'COMPLETED'" in fake.await_args.args[0]
