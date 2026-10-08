"""cycle411 3차 LOW 보완 Red — 비용 계산 자체의 예외도 try 로 감싼다 (항목 4).

배경 — `trade_cost_db.get_daily_range`/`get_trades_by_status` 같은 **DB 조회** 실패는 이미
try 로 감싸여 있다(`_overlay_trade_costs`·`_net_overlay_rows`). 그런데 그 뒤 **순수 계산**
호출(`cost_overlay.trade_costs`·`cost_overlay.net_twr`·`cost_overlay.overlay_pairs`)이
코드 결함으로 예외를 내면 그 try 밖이라 라우트까지 전파돼 기존 세전 응답(200)이 500 으로
바뀐다 — 비용 계산 실패가 세전 응답 자체를 삼키면 안 된다(계약 결정 2).

| # | 계약 | 위치 |
|---|---|---|
| L4a | `/api/history` — `cost_overlay.trade_costs` 가 예외를 내도 200 + 기존 칸 그대로(새 칸 없음) | `history.py:59` |
| L4b | `/api/history/pnl` — `cost_overlay.overlay_pairs` 가 예외를 내도 200 + summary 세후 칸 None | `history.py:130` |
| L4c | `/api/performance/daily` — `cost_overlay.trade_costs` 가 예외를 내도 200 + net 6칸 None | `performance.py:43` |
| L4d | `/api/performance/daily`·`summary` — `cost_overlay.net_twr` 가 예외를 내도 200 + net 칸 None | `performance.py:64` |

각 경우 `[cost_overlay_unavailable]` WARNING 로그가 남는다.
"""

from __future__ import annotations

import importlib
import logging
from datetime import date, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
D1 = date(2026, 10, 6)
D2 = date(2026, 10, 7)


def _t(tid, strategy, tt, price, qty, d, *, ticker="005930", name="삼성전자", pl=0) -> dict:
    return {
        "id": tid, "trade_date": d, "ticker": ticker, "ticker_name": name, "trade_type": tt,
        "strategy": strategy, "price": Decimal(str(price)), "quantity": qty,
        "profit_loss": Decimal(str(pl)), "order_no": f"O{tid}", "order_price": None,
        "status": "COMPLETED", "timestamp": f"{d.isoformat()}T10:00:00+09:00",
    }


def _hist(t: dict) -> dict:
    return {k: v for k, v in t.items() if k != "trade_date"}


def _pair(**kw) -> dict:
    base = {
        "buy_date": None, "buy_time": "09:01:00", "sell_date": None, "sell_time": "10:00:00",
        "ticker": "005930", "ticker_name": "삼성전자", "buy_price": 0, "buy_qty": 0,
        "sell_price": None, "sell_qty": None, "profit_loss": 0, "profit_rate": 0.0,
        "status": "closed", "strategy": "momentum", "buy_order_nos": [], "sell_order_nos": [],
        "pair_key": None, "buy_trade_ids": [], "sell_trade_ids": [],
    }
    base.update(kw)
    return base


TRADES = [
    _t(1, "momentum", "BUY", 70_000, 10, D1),
    _t(2, "momentum", "SELL", 72_000, 10, D2, pl=20_000),
]
PAIRS = [
    _pair(buy_date="2026-10-06", sell_date="2026-10-07", buy_price=70_000, buy_qty=10,
          sell_price=72_000, sell_qty=10, profit_loss=20_000, profit_rate=2.8571,
          buy_order_nos=["O1"], sell_order_nos=["O2"], pair_key="momentum:005930:O1",
          buy_trade_ids=[1], sell_trade_ids=[2]),
]
PERF = [
    {"date": D1, "strategy": "total", "total_asset": 10_000_000, "daily_realized_pnl": 0,
     "daily_profit_rate": 0.0, "cumulative_return_rate": 0.0, "net_external_cashflow": 0,
     "deposit": 0},
    {"date": D2, "strategy": "total", "total_asset": 10_020_000, "daily_realized_pnl": 20_000,
     "daily_profit_rate": 0.2, "cumulative_return_rate": 0.2, "net_external_cashflow": 0,
     "deposit": 0},
]


class _Db:
    def __init__(self):
        self.trades = list(TRADES)
        self.pairs = [dict(p) for p in PAIRS]
        self.perf = [dict(r) for r in PERF]
        self.history_trades = [_hist(t) for t in TRADES]


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
        return []

    async def get_trades_by_status(start, end, statuses=("COMPLETED", "PARTIAL")):
        return [t for t in st.trades if start <= t["trade_date"] <= end and t["status"] in statuses]

    monkeypatch.setattr(tcdb, "get_daily_range", get_daily_range)
    monkeypatch.setattr(tcdb, "get_trades_by_status", get_trades_by_status, raising=False)

    async def get_performance(days=30, strategy="total"):
        return [dict(r) for r in st.perf][-days:]

    async def get_latest_performance(strategy="total"):
        return dict(st.perf[-1]) if st.perf else None

    dp = importlib.import_module("src.db.daily_performance")
    monkeypatch.setattr(dp, "get_performance", get_performance)
    monkeypatch.setattr(dp, "get_latest_performance", get_latest_performance)
    perf_route = importlib.import_module("src.routes.performance")
    monkeypatch.setattr(perf_route, "get_performance", get_performance)
    monkeypatch.setattr(perf_route, "get_latest_performance", get_latest_performance)

    async def get_trade_pairs(strategy=None, ticker=None):
        return [dict(p) for p in st.pairs if strategy is None or p["strategy"] == strategy]

    async def get_trades(limit=20, offset=0, ticker=None, strategy=None):
        rows = [dict(t) for t in st.history_trades]
        return rows[offset:offset + limit], len(rows)

    hist_route = importlib.import_module("src.routes.history")
    monkeypatch.setattr(hist_route, "get_trade_pairs", get_trade_pairs)
    monkeypatch.setattr(hist_route, "get_trades", get_trades)

    sm = importlib.import_module("src.db.stock_master")
    monkeypatch.setattr(sm, "get_master_raw", AsyncMock(return_value=None))
    monkeypatch.setattr(sm, "get", AsyncMock(return_value=None))
    return st


def _client(*modules: str) -> TestClient:
    app = FastAPI()
    for m in modules:
        app.include_router(importlib.import_module(m).router)
    return TestClient(app, raise_server_exceptions=False)


def _ok(r):
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True, body
    return body["data"]


def _warns(caplog, prefix: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)]


# ── L4a: /api/history — trade_costs 가 예외를 내도 200 ───────────────────────

def test_l4a_history_survives_trade_costs_exception(db, monkeypatch, caplog):
    co = importlib.import_module("src.engine.cost_overlay")

    def boom(*a, **kw):
        raise RuntimeError("compute bug")

    monkeypatch.setattr(co, "trade_costs", boom)
    with caplog.at_level(logging.DEBUG):
        data = _ok(_client("src.routes.history").get("/api/history"))
    rows = {r["id"]: r for r in data["trades"]}
    # 기존 칸 불변, 새 칸(fee/tax/net_profit_loss/cost_status)은 아예 없다 — 0 으로 지어내지 않는다.
    assert rows[2]["profit_loss"] == pytest.approx(20_000)
    assert "fee" not in rows[1]
    assert "net_profit_loss" not in rows[2]
    assert _warns(caplog, "[cost_overlay_unavailable]")


# ── L4b: /api/history/pnl — overlay_pairs 가 예외를 내도 200 ─────────────────

def test_l4b_pnl_survives_overlay_pairs_exception(db, monkeypatch, caplog):
    co = importlib.import_module("src.engine.cost_overlay")

    async def boom(pairs):
        raise RuntimeError("compute bug")

    monkeypatch.setattr(co, "overlay_pairs", boom)
    with caplog.at_level(logging.DEBUG):
        data = _ok(_client("src.routes.history").get("/api/history/pnl"))
    assert data["summary"]["closed_count"] == 1  # 기존 칸 불변
    assert data["summary"]["realized_total_krw"] == pytest.approx(20_000)
    for k in ("fee_sum", "tax_sum", "realized_net_total_krw", "realized_net_rate_pct",
              "slippage_n"):
        assert data["summary"][k] is None, (k, data["summary"])
    assert _warns(caplog, "[cost_overlay_unavailable]")


# ── L4c: /api/performance/daily — trade_costs 가 예외를 내도 200 ─────────────

def test_l4c_performance_daily_survives_trade_costs_exception(db, monkeypatch, caplog):
    co = importlib.import_module("src.engine.cost_overlay")

    def boom(*a, **kw):
        raise RuntimeError("compute bug")

    monkeypatch.setattr(co, "trade_costs", boom)
    with caplog.at_level(logging.DEBUG):
        data = _ok(_client("src.routes.performance").get("/api/performance/daily?days=30"))
    by = {r["date"]: r for r in data}
    d2 = by["2026-10-07"]
    assert d2["daily_realized_pnl"] == pytest.approx(20_000)  # 기존 칸 불변
    for k in ("daily_fee", "daily_tax", "daily_net_pnl", "net_daily_profit_rate",
              "net_cumulative_return_rate", "cost_status"):
        assert d2[k] is None, (k, d2)
    assert _warns(caplog, "[cost_overlay_unavailable]")


# ── L4d: net_twr 가 예외를 내도 200 (daily + summary) ─────────────────────────

def test_l4d_performance_survives_net_twr_exception(db, monkeypatch, caplog):
    co = importlib.import_module("src.engine.cost_overlay")

    def boom(*a, **kw):
        raise RuntimeError("compute bug")

    monkeypatch.setattr(co, "net_twr", boom)
    with caplog.at_level(logging.DEBUG):
        daily_data = _ok(_client("src.routes.performance").get("/api/performance/daily?days=30"))
        summary_data = _ok(_client("src.routes.performance").get("/api/performance/summary"))
    d2 = {r["date"]: r for r in daily_data}["2026-10-07"]
    assert d2["daily_realized_pnl"] == pytest.approx(20_000)
    assert d2["net_cumulative_return_rate"] is None
    assert summary_data["net_total_profit_rate"] is None
    assert summary_data["net_avg_daily_profit_rate"] is None
    assert summary_data["total_profit_rate"] == round(PERF[-1]["cumulative_return_rate"], 2)
    assert _warns(caplog, "[cost_overlay_unavailable]")
