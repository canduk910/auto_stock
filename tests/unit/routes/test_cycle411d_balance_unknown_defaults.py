"""cycle411 3차 LOW 보완 Red — `/api/balance` 매수 수수료 기본값이 「모름」 을 0 으로
지어내던 결함 (항목 5).

| # | 계약 | 위치 |
|---|---|---|
| L5a | `_open_pair_buy_fee` — 범위 조회는 성공했는데 그 페어의 체결 id 가 `costs` 에
       하나도 없으면(데이터 불일치) `(0.0, "estimated")` 대신 `(None, None)` | `balance.py:90` |
| L5b | `_buy_fee_paid_by_ticker` 가 통째로 예외를 내면(코드 결함) `balance()` 의
       `buy_fee_by_ticker` 가 `{}` 가 되고, `.get(ticker, DEFAULT)` 의 기본값이
       `(0.0, "estimated")` 대신 `(None, None)` — 「모름」 을 0 으로 보이지 않는다 | `balance.py:239` |

기존 F3(`db.fail_costs=True`, DB 자체가 죽음) 은 이미 `(None, None)` 으로 통과한다 —
이 Red 는 **DB 는 멀쩩한데 계산/코드 쪽이 실패**하는 다른 경로를 겨냥한다.
"""

from __future__ import annotations

import importlib
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

D1 = date(2026, 10, 6)
D2 = date(2026, 10, 7)


def _cost(pdno, trad_dt, **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "",
        "buy_qty": Decimal(0), "buy_amt": Decimal(0), "sll_qty": Decimal(0),
        "sll_amt": Decimal(0), "rlzt_pfls": Decimal(0), "fee": Decimal(0),
        "tl_tax": Decimal(0), "row_count": 1, "raw": [],
    }
    row.update({k: Decimal(str(v)) for k, v in over.items()})
    return row


def _t(tid, strategy, tt, price, qty, d, *, ticker, name="가나", pl=0) -> dict:
    return {
        "id": tid, "trade_date": d, "ticker": ticker, "ticker_name": name, "trade_type": tt,
        "strategy": strategy, "price": Decimal(str(price)), "quantity": qty,
        "profit_loss": Decimal(str(pl)), "order_no": f"O{tid}", "order_price": None,
        "status": "COMPLETED",
    }


def _pair(**kw) -> dict:
    base = {
        "buy_date": None, "buy_time": "09:01:00", "sell_date": None, "sell_time": "10:00:00",
        "ticker": "005930", "ticker_name": "삼성전자", "buy_price": 0, "buy_qty": 0,
        "sell_price": None, "sell_qty": None, "profit_loss": 0, "profit_rate": 0.0,
        "status": "open", "strategy": "kojiro", "buy_order_nos": [], "sell_order_nos": [],
        "pair_key": None, "buy_trade_ids": [], "sell_trade_ids": [],
        "partial_sell_trade_ids": [],
    }
    base.update(kw)
    return base


class _Db:
    def __init__(self):
        self.cost_rows: list[dict] = []
        self.trades: list[dict] = []
        self.pairs: list[dict] = []


@pytest.fixture
def db(monkeypatch):
    st = _Db()
    pg = importlib.import_module("src.db.pg")
    monkeypatch.setattr(pg, "fetch", AsyncMock(return_value=[]))
    monkeypatch.setattr(pg, "fetchrow", AsyncMock(return_value=None))
    monkeypatch.setattr(pg, "fetchval", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(pg, "execute", AsyncMock(return_value=None))

    tcdb = importlib.import_module("src.db.trade_cost")

    async def get_daily_range(start, end):
        return [r for r in st.cost_rows if start <= r["trad_dt"] <= end]

    async def get_trades_by_status(start, end, statuses=("COMPLETED", "PARTIAL")):
        return [t for t in st.trades if start <= t["trade_date"] <= end and t["status"] in statuses]

    monkeypatch.setattr(tcdb, "get_daily_range", get_daily_range)
    monkeypatch.setattr(tcdb, "get_trades_by_status", get_trades_by_status, raising=False)

    th = importlib.import_module("src.db.trade_history")

    async def get_trade_pairs(strategy=None, ticker=None):
        return [dict(p) for p in st.pairs if ticker is None or p["ticker"] == ticker]

    monkeypatch.setattr(th, "get_trade_pairs", get_trade_pairs)
    return st


def _balance_client(monkeypatch, holdings):
    from src.models.balance import AccountSummary

    summary = AccountSummary(deposit=0, stock_eval_amount=0, total_eval_amount=0, net_asset=0,
                             purchase_total=0, eval_total=0, profit_loss_total=0)
    bal = importlib.import_module("src.routes.balance")
    monkeypatch.setattr(bal, "get_balance", AsyncMock(return_value=(holdings, summary)))
    monkeypatch.setattr(bal, "stock_master_get", AsyncMock(return_value=None))
    monkeypatch.setattr(bal, "resolve_sector_name", AsyncMock(return_value="미분류"))
    app = FastAPI()
    app.include_router(bal.router)
    return TestClient(app, raise_server_exceptions=False)


def _holding(ticker, name, qty, avg, cur):
    from src.models.balance import StockHolding

    return StockHolding(ticker=ticker, name=name, quantity=qty, sellable_quantity=qty,
                        avg_price=avg, purchase_amount=int(avg * qty), current_price=cur,
                        eval_amount=cur * qty, eval_profit_loss=int((cur - avg) * qty),
                        eval_profit_rate=round((cur - avg) / avg * 100, 2))


def _ok(r):
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True, body
    return body["data"]


# ── L5a: entries 비었으면(데이터 불일치) None ────────────────────────────────

def test_l5a_open_pair_missing_trade_ids_in_costs_is_unknown(db, monkeypatch):
    """buy_trade_ids 가 가리키는 체결이 그 범위 조회 결과에 없다 — 0 으로 지어내지 않는다."""
    db.pairs = [_pair(buy_date="2026-10-06", ticker="005930", ticker_name="삼성전자",
                      buy_price=70_000, buy_qty=10, profit_loss=2_000, profit_rate=2.86,
                      pair_key="kojiro:005930:O1", buy_trade_ids=[999])]
    # db.trades·db.cost_rows 는 비어 있다 — 999 는 어디서도 안 나온다(DB 조회 자체는 성공).
    holdings = [_holding("005930", "삼성전자", 10, 70_000, 72_000)]
    data = _ok(_balance_client(monkeypatch, holdings).get("/api/balance"))
    (h,) = data["holdings"]
    assert h["eval_profit_loss"] == 20_000  # 기존 칸 불변
    assert h["buy_fee_paid"] is None, h
    assert h["buy_fee_status"] is None, h


# ── L5b: 매수수수료 계산 전체가 예외를 내면 None(0.0 아님) ───────────────────

def test_l5b_buy_fee_computation_exception_defaults_to_unknown_not_zero(db, monkeypatch):
    """`cost_overlay.trade_costs` 가 코드 결함으로 예외를 내면 `.get(ticker, DEFAULT)` 가
    0.0/"estimated" 를 지어내지 않는다 — 보유 전종목이 「모름」 이어야 한다."""
    db.trades = [_t(1, "kojiro", "BUY", 70_000, 10, D1, ticker="005930")]
    db.cost_rows = [_cost("005930", D1, buy_amt=700_000, fee=99)]
    db.pairs = [_pair(buy_date="2026-10-06", ticker="005930", ticker_name="삼성전자",
                      buy_price=70_000, buy_qty=10, profit_loss=2_000, profit_rate=2.86,
                      pair_key="kojiro:005930:O1", buy_trade_ids=[1])]
    holdings = [_holding("005930", "삼성전자", 10, 70_000, 72_000),
                _holding("000660", "SK하이닉스", 5, 100_000, 102_000)]

    co = importlib.import_module("src.engine.cost_overlay")

    def boom(*a, **kw):
        raise RuntimeError("compute bug")

    monkeypatch.setattr(co, "trade_costs", boom)
    data = _ok(_balance_client(monkeypatch, holdings).get("/api/balance"))
    by = {h["ticker"]: h for h in data["holdings"]}
    for tk in ("005930", "000660"):
        assert by[tk]["buy_fee_paid"] is None, by[tk]
        assert by[tk]["buy_fee_status"] is None, by[tk]
    # 기존 칸 불변
    assert by["005930"]["eval_profit_loss"] == 20_000
