"""cycle411 보완 Red L2 — 보유 중(open) 페어에 분할 매도 체결 행 id (가산형 사영, 페어링 알고리즘 무변경).

계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「보완 결정」 L2.

| # | 계약 |
|---|---|
| L2a | open 페어에 `partial_sell_trade_ids` = 그 사이클 안에서 이미 판 SELL 행 id(시간순). `sell_trade_ids` 는 그대로 `[]` |
| L2b | closed 페어도 `partial_sell_trade_ids` 칸을 갖는다 — 값은 `[]`(판 행은 이미 `sell_trade_ids` 에 있다) |
| L2c | 기존 칸(`buy_qty`=남은 수량·`buy_trade_ids`·`profit_loss`·`pair_key`)은 그대로 |
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.db import trade_history

pytestmark = pytest.mark.asyncio


def _row(tid, tt, price, qty, ts, *, pl=None, ono=""):
    return {
        "id": tid, "ticker": "000660", "ticker_name": "SK하이닉스", "strategy": "kojiro",
        "trade_type": tt, "price": Decimal(str(price)), "quantity": qty, "profit_loss": pl,
        "timestamp": ts, "status": "COMPLETED", "order_no": ono,
    }


async def _pairs(rows):
    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        return await trade_history.get_trade_pairs()


async def test_l2a_open_pair_carries_partial_sell_trade_ids():
    rows = [
        _row(41, "BUY", 100_000, 10, "2026-10-06T09:01:00+09:00", ono="B1"),
        _row(42, "SELL", 110_000, 6, "2026-10-07T10:00:00+09:00", pl=Decimal("60000"), ono="S1"),
    ]
    (p,) = await _pairs(rows)
    assert p["status"] == "open"
    assert p["buy_qty"] == 4  # 기존 칸 불변 — 남은 수량
    assert p["buy_trade_ids"] == [41]
    assert p["sell_trade_ids"] == []
    assert p["partial_sell_trade_ids"] == [42]
    assert p["pair_key"] == "kojiro:000660:B1"


async def test_l2b_closed_pair_has_empty_partial_sell_trade_ids():
    rows = [
        _row(51, "BUY", 100_000, 10, "2026-10-06T09:01:00+09:00", ono="B1"),
        _row(52, "SELL", 110_000, 6, "2026-10-07T10:00:00+09:00", pl=Decimal("60000"), ono="S1"),
        _row(53, "SELL", 111_000, 4, "2026-10-07T11:00:00+09:00", pl=Decimal("44000"), ono="S2"),
    ]
    (p,) = await _pairs(rows)
    assert p["status"] == "closed"
    assert p["sell_trade_ids"] == [52, 53]
    assert p["partial_sell_trade_ids"] == []
