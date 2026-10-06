"""cycle409 — 사용자 결정 10-04 Q4: 슬리피지 원천을 `trade_history.order_price` 로 (`src/engine/trade_cost.py`).

| # | 계약 |
|---|---|
| P1 | 매수 슬리피지 = (체결가 − 주문가) × 수량 — + 가 비용(비싸게 샀다) |
| P2 | 매도 슬리피지 = (주문가 − 체결가) × 수량 — + 가 비용(싸게 팔았다) |
| P3 | `order_price` 가 NULL·0 이하인 행은 빠지고 `slippage_n` 은 덮인 행 수다 · bp 분모 = Σ 주문가 × 수량 |
| P4 | 요약이 `llm_buy_evaluations` 를 읽지 않는다 — `build_summary` 는 정산 행·체결 행 두 읽기만 한다 |
| P5 | `get_completed_trades` SQL 이 `order_price` 를 고른다 |
"""

from __future__ import annotations

import importlib
import inspect
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

D = date(2026, 9, 30)


def _mod():
    return importlib.import_module("src.engine.trade_cost")


def _trade(trade_type, price, qty, order_price, *, strategy="kojiro", order_no="1"):
    return {
        "trade_date": D, "ticker": "035760", "trade_type": trade_type, "strategy": strategy,
        "price": Decimal(str(price)), "quantity": qty, "profit_loss": Decimal(0),
        "order_no": order_no,
        "order_price": None if order_price is None else Decimal(str(order_price)),
    }


def test_p1_buy_slippage_fill_minus_order():
    s = _mod().summarize([], [_trade("BUY", 39450, 5, 39400)])
    (k,) = s["strategies"]
    assert k["slippage_won"] == pytest.approx(50 * 5)
    assert k["slippage_n"] == 1
    assert k["slippage_bp"] == pytest.approx(250 / (39400 * 5) * 10000, abs=0.01)


def test_p2_sell_slippage_order_minus_fill():
    s = _mod().summarize([], [_trade("SELL", 36110, 5, 36200)])
    (k,) = s["strategies"]
    assert k["slippage_won"] == pytest.approx(90 * 5)
    assert k["slippage_n"] == 1


def test_p3_null_and_nonpositive_order_price_excluded():
    trades = [
        _trade("BUY", 39450, 5, 39400, order_no="B1"),
        _trade("SELL", 36110, 5, None, order_no="S1"),
        _trade("BUY", 1000, 1, 0, order_no="B2"),
        _trade("BUY", 2010, 2, 2000, strategy="vcp_breakout", order_no="B3"),
    ]
    s = _mod().summarize([], trades)
    by = {r["strategy"]: r for r in s["strategies"]}
    assert by["kojiro"]["slippage_n"] == 1
    assert by["kojiro"]["slippage_won"] == pytest.approx(250)
    assert by["vcp_breakout"]["slippage_won"] == pytest.approx(20)
    assert s["total"]["slippage_n"] == 2
    assert s["total"]["slippage_bp"] == pytest.approx(270 / (39400 * 5 + 2000 * 2) * 10000,
                                                      abs=0.01)


def test_p3b_no_order_price_column_means_no_slippage():
    t = _trade("BUY", 39450, 5, None)
    del t["order_price"]
    k = _mod().summarize([], [t])["total"]
    assert k["slippage_n"] == 0
    assert k["slippage_bp"] is None


async def test_p4_build_summary_reads_only_cost_and_trades(monkeypatch):
    m = _mod()
    get_daily = AsyncMock(return_value=[])
    get_trades = AsyncMock(return_value=[_trade("BUY", 39450, 5, 39400)])
    monkeypatch.setattr(m.trade_cost_db, "get_daily_range", get_daily)
    monkeypatch.setattr(m.trade_cost_db, "get_completed_trades", get_trades)
    out = await m.build_summary(D, D)
    assert out["total"]["slippage_n"] == 1
    assert not hasattr(m.trade_cost_db, "get_buy_order_prices")
    assert "llm_buy_evaluations" not in inspect.getsource(m)
    assert "llm_buy_evaluations" not in inspect.getsource(m.trade_cost_db)


async def test_p5_completed_trades_selects_order_price(monkeypatch):
    db = importlib.import_module("src.db.trade_cost")
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(db.pg, "fetch", fetch)
    await db.get_completed_trades(D, D)
    assert "order_price" in fetch.await_args.args[0]
