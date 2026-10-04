"""cycle409 — 사용자 결정 10-04 Q4: `trade_history.order_price`(주문가) 기록 (`src/db/trade_history.py`).

`price` 는 PENDING 때 주문가였다가 체결통보가 체결가로 덮는다. 주문가를 따로 남겨 슬리피지 원천으로 쓴다.

| # | 계약 |
|---|---|
| O1 | `insert_trade` 가 **PENDING ∧ BUY** 행에서만 `order_price = price` 를 쓴다 |
| O2 | PENDING SELL 은 NULL — 매도 주 경로 PENDING `price` 는 주문가가 아니라 **매수가**다(`order_engine.py` `record_price=pos.buy_price`) |
| O3 | COMPLETED·PARTIAL INSERT(체결통보 선행 race 보정 · sync) 는 NULL — 그 `price` 는 체결가다 |
| O4 | 체결 UPDATE 두 경로(`update_trade_status` · `_update_trade_status_by_order_no`)의 SQL 에 `order_price` 가 없다 |
| O5 | `src/db/trade_history.py` 의 어떤 `UPDATE trade_history` SQL 도 `order_price` 를 건드리지 않는다(AST — 문자열 상수 전수) |
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.models.trade import TradeRecord, TradeStatus, TradeType

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]


def _rec(trade_type: TradeType, status: TradeStatus, price: float = 39450) -> TradeRecord:
    return TradeRecord(
        ticker="035760", ticker_name="CJ ENM", trade_type=trade_type, price=price,
        quantity=5, profit_loss=0, status=status, strategy="kojiro", order_no="0000012345",
    )


async def _insert_and_capture(monkeypatch, record: TradeRecord) -> tuple[str, dict]:
    from src.db import trade_history

    ex = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(trade_history.pg, "execute", ex)
    await trade_history.insert_trade(record)
    sql, *args = ex.await_args.args
    cols_part = sql.split("(", 1)[1].split(")", 1)[0]
    cols = [c.strip() for c in cols_part.split(",")]
    assert len(cols) == len(args), (cols, args)
    return sql, dict(zip(cols, args))


async def test_o1_pending_buy_records_order_price(monkeypatch):
    sql, row = await _insert_and_capture(monkeypatch, _rec(TradeType.BUY, TradeStatus.PENDING, 39400))
    assert "order_price" in row, sql
    assert row["order_price"] == pytest.approx(39400)
    assert row["price"] == pytest.approx(39400)


async def test_o2_pending_sell_leaves_order_price_null(monkeypatch):
    _, row = await _insert_and_capture(monkeypatch, _rec(TradeType.SELL, TradeStatus.PENDING, 36000))
    assert row["order_price"] is None


@pytest.mark.parametrize("status", [TradeStatus.COMPLETED, TradeStatus.PARTIAL])
@pytest.mark.parametrize("trade_type", [TradeType.BUY, TradeType.SELL])
async def test_o3_non_pending_insert_leaves_order_price_null(monkeypatch, status, trade_type):
    _, row = await _insert_and_capture(monkeypatch, _rec(trade_type, status))
    assert row["order_price"] is None


async def test_o4_fill_updates_never_set_order_price(monkeypatch):
    from src.db import trade_history

    ex = AsyncMock(return_value="UPDATE 1")
    monkeypatch.setattr(trade_history.pg, "execute", ex)
    await trade_history.update_trade_status(
        "035760", TradeType.BUY, TradeStatus.COMPLETED, "kojiro", price=39450,
        order_no="0000012345", match_partial=True,
    )
    await trade_history._update_trade_status_by_order_no(
        "0000012345", TradeType.BUY, TradeStatus.COMPLETED, price=39450,
    )
    sqls = [c.args[0] for c in ex.await_args_list]
    assert len(sqls) == 2
    for s in sqls:
        assert "UPDATE trade_history" in s
        assert "order_price" not in s, s


def test_o5_no_update_sql_touches_order_price():
    src = (_ROOT / "src" / "db" / "trade_history.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    updates = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "UPDATE trade_history" in node.value:
                updates.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            text = "".join(v.value for v in node.values
                           if isinstance(v, ast.Constant) and isinstance(v.value, str))
            if "UPDATE trade_history" in text:
                updates.append(text)
    assert updates, "UPDATE trade_history SQL 을 하나도 못 찾았다 — 스캔이 공허하다"
    assert not [u for u in updates if "order_price" in u]
