"""cycle396 — 매매손익 그리드(`get_trade_pairs`)에 소수가 보이지 않게 한다.

사용자 요청(2026-10-02): 「손익계산 시 소수점 표시되는 사례가 있어. 9/28 054920 종목이야.
소수점은 절사하도록 수정해줄래?」

계약
- `buy_price`·`sell_price` = 가중평균을 원 단위 내림한 `int` (closed·open 공통)
- closed `profit_loss` = 그 페어의 SELL 행 `profit_loss` 합(엔진이 기록한 정수 실현손익 —
  `daily_performance` 와 같은 출처) — 단 SELL 행 **전부** 값이 있을 때만. 하나라도 NULL 이면
  가중평균 재계산값을 0 쪽으로 절사한 `int`
- `profit_rate` = profit_loss ÷ (매수 가중평균 × 매도 수량) × 100, 소수 넷째 자리
"""
from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.db import trade_history

pytestmark = pytest.mark.asyncio


def _row(tt, price, qty, ts, *, pl=None, ono="", ticker="054920", strategy="long_tail_volatility"):
    return {
        "ticker": ticker, "ticker_name": "한컴위드", "strategy": strategy,
        "trade_type": tt, "price": price, "quantity": qty, "profit_loss": pl,
        "timestamp": ts, "status": "COMPLETED", "order_no": ono,
    }


async def _pairs(rows):
    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        return await trade_history.get_trade_pairs()


async def test_closed_pair_when_sell_rows_have_profit_loss_then_uses_stored_sum_as_int():
    """054920 형 — 매수 9@5,090 · 매도 9@4,826(장부 −2,375). 재계산이면 −2,376 이 된다."""
    rows = [
        _row("BUY", Decimal("5090"), 9, "2026-09-26T09:01:00+09:00", ono="B1"),
        _row("SELL", Decimal("4826"), 9, "2026-09-28T10:52:33+09:00", pl=Decimal("-2375"), ono="S1"),
    ]
    (p,) = await _pairs(rows)
    assert p["status"] == "closed"
    assert p["profit_loss"] == -2375 and type(p["profit_loss"]) is int, p["profit_loss"]
    assert p["sell_price"] == 4826 and type(p["sell_price"]) is int, p["sell_price"]
    assert p["buy_price"] == 5090 and type(p["buy_price"]) is int, p["buy_price"]
    assert p["profit_rate"] == round(-2375 / (5090 * 9) * 100, 4)
    json.dumps(p)


async def test_closed_pair_when_several_sell_rows_then_profit_loss_is_their_sum():
    rows = [
        _row("BUY", 10_000, 1, "2026-09-26T09:01:00+09:00", ono="B1"),
        _row("BUY", 10_001, 2, "2026-09-26T09:02:00+09:00", ono="B2"),
        _row("SELL", 10_100, 1, "2026-09-28T10:00:00+09:00", pl=Decimal("100"), ono="S1"),
        _row("SELL", 10_051, 2, "2026-09-28T11:00:00+09:00", pl=Decimal("99"), ono="S2"),
    ]
    (p,) = await _pairs(rows)
    assert p["profit_loss"] == 199 and type(p["profit_loss"]) is int
    assert p["buy_price"] == 10_000 and type(p["buy_price"]) is int   # 30,002/3 = 10,000.67 → 10,000
    assert p["sell_price"] == 10_067 and type(p["sell_price"]) is int  # 30,202/3 = 10,067.33 → 10,067
    assert p["profit_rate"] == round(float(Decimal(199) / (Decimal(30_002) / 3 * 3) * 100), 4)


@pytest.mark.parametrize(("sell_price", "expected"), [(10_011, 30), (9_999, -5)])
async def test_closed_pair_when_any_sell_profit_loss_null_then_recomputes_truncated_toward_zero(sell_price, expected):
    """매수 30,002/3 = 10,000.67 · 매도 3주 — (10,011 − 10,000.67)×3 = 30.99… → 30,
    (9,999 − 10,000.67)×3 = −5.00… → −5 (0 쪽 절사)."""
    rows = [
        _row("BUY", 10_000, 1, "2026-09-26T09:01:00+09:00", ono="B1"),
        _row("BUY", 10_001, 2, "2026-09-26T09:02:00+09:00", ono="B2"),
        _row("SELL", sell_price, 1, "2026-09-28T10:00:00+09:00", pl=Decimal("11"), ono="S1"),
        _row("SELL", sell_price, 2, "2026-09-28T11:00:00+09:00", pl=None, ono="S2"),
    ]
    (p,) = await _pairs(rows)
    assert p["profit_loss"] == expected and type(p["profit_loss"]) is int, p["profit_loss"]
    assert type(p["sell_price"]) is int and p["sell_price"] == sell_price


async def test_open_pair_buy_price_is_floored_int():
    rows = [
        _row("BUY", 10_000, 1, "2026-09-26T09:01:00+09:00", ono="B1"),
        _row("BUY", 10_001, 2, "2026-09-26T09:02:00+09:00", ono="B2"),
    ]
    (p,) = await _pairs(rows)
    assert p["status"] == "open"
    assert p["buy_price"] == 10_000 and type(p["buy_price"]) is int



@pytest.mark.parametrize(("cur", "expected"), [(10_050, 148), (9_990, -32)])
async def test_open_pair_unrealized_pnl_is_int_truncated_toward_zero(cur, expected):
    """보유 중(open) 페어 평가손익도 원 단위 정수, 0 쪽 절사 — 매수 30,002/3 = 10,000.67,
    (10,050 − 10,000.67)×3 = 148.0 → 148 · (9,990 − 10,000.67)×3 = −32.0… → −32."""
    from src.engine import scanner
    rows = [
        _row("BUY", 10_000, 1, "2026-09-26T09:01:00+09:00", ono="B1"),
        _row("BUY", 10_001, 2, "2026-09-26T09:02:00+09:00", ono="B2"),
    ]
    tkr = rows[0]["ticker"]
    with patch.dict(scanner.ticker_prices, {tkr: {"current_price": cur}}):
        (p,) = await _pairs(rows)
    assert p["status"] == "open"
    assert p["profit_loss"] == expected and type(p["profit_loss"]) is int, p["profit_loss"]
