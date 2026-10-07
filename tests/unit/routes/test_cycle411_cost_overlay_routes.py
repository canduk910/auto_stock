"""cycle411 Red — 실적 라우트에 실비용 칸 **덧붙이기** (기존 칸 값 불변).

명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` (사용자 결정 10-08 Q1~Q4).
Red 메모 = `_workspace/red/cycle411/cost_overlay.md`.

| # | 계약 |
|---|---|
| D1 | `/api/performance/daily` 행마다 `daily_fee`·`daily_tax`·`daily_net_pnl`·`net_daily_profit_rate`·`net_cumulative_return_rate`·`cost_status` |
| D2 | `strategy=` 를 주면 그 전략 체결의 비용만 합친다 |
| S1 | `/api/performance/summary` 에 `net_total_profit_rate`·`net_avg_daily_profit_rate` |
| H1 | `/api/history` SELL 행 `fee`·`tax`·`net_profit_loss`(= 그 행 profit_loss − 그 행 fee − tax), BUY 행 `fee`, 행마다 `cost_status` |
| P1 | `/api/history/pnl` 페어마다 `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp`·`slippage_won`·`cost_status`·`allocated` |
| P2 | 한 날 한 종목 체결 행 2개 이상을 나눠 받은 페어 = `allocated=True` |
| P3 | 정산 행 없는 페어 = `cost_status="estimated"` · ETF 매도세 0 · 보유 중 페어 = 낸 매수 수수료 + 예상 매도비용(추정) |
| P4 | summary 에 `fee_sum`·`tax_sum`·`realized_net_total_krw`·`realized_net_rate_pct`·`slippage_n`(order_price 있는 행 수) |
| T1 | `/api/strategies/te` 판정은 순손익 기준 · 세전은 `*_gross` · `realized_net_sum_krw`·`fee_sum`·`tax_sum` |
| C1 | 새 `GET /api/costs/today?strategy=` — 오늘 체결 × (정산 or 추정 요율), 전략별 + total |
| C2 | 새 `GET /api/costs/daily?from=&to=` — 날짜별 비용·슬리피지·`cost_status` · 날짜 오류 422 |
| B1 | `/api/balance` 보유 종목마다 `sell_cost_rate`(수수료율 + 세율, ETF 는 수수료율만)·`cost_status="estimated"` |
| F1 | 비용 조회가 실패해도 기존 응답은 200 그대로 — 새 순손익 칸만 None (기존 계약 테스트 무수정 통과) |

🔴 모든 테스트가 **기존 칸 값 불변**을 함께 단언한다(DB 저장값·`trade_history.profit_loss` 의미 = 세전).
DB 경계는 `src.db.trade_cost.get_daily_range` · `src.db.trade_cost.get_trades_by_status`(신규) ·
`src.db.daily_performance.get_performance` 모듈 속성으로만 갈아 끼운다 — 구현은 **모듈 속성
경유**로 부른다(`trade_cost.py` 와 같은 관례). 그 밖의 `pg` 호출은 빈 결과를 돌려준다.
"""

from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
D0 = date(2026, 10, 5)
D1 = date(2026, 10, 6)
D2 = date(2026, 10, 7)
D3 = date(2026, 10, 8)


def _cost(pdno, trad_dt, **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "",
        "buy_qty": Decimal(0), "buy_amt": Decimal(0), "sll_qty": Decimal(0),
        "sll_amt": Decimal(0), "rlzt_pfls": Decimal(0), "fee": Decimal(0),
        "tl_tax": Decimal(0), "row_count": 1, "raw": [],
    }
    row.update({k: Decimal(str(v)) for k, v in over.items()})
    return row


def _t(tid, strategy, tt, price, qty, d, *, ticker="005930", name="삼성전자", pl=0,
       order_price=None, status="COMPLETED") -> dict:
    return {
        "id": tid, "trade_date": d, "ticker": ticker, "ticker_name": name, "trade_type": tt,
        "strategy": strategy, "price": Decimal(str(price)), "quantity": qty,
        "profit_loss": Decimal(str(pl)), "order_no": f"O{tid}",
        "order_price": None if order_price is None else Decimal(str(order_price)),
        "status": status,
        "timestamp": f"{d.isoformat()}T10:00:00+09:00",
    }


# 시나리오 — 005930 1왕복(정산) · 000660 3주문 2전략(정산·배분) · 069500 ETF 1왕복(미대사)
TRADES = [
    _t(1, "momentum", "BUY", 70000, 10, D1, order_price=69900),
    _t(2, "momentum", "SELL", 72000, 10, D2, pl=20000, order_price=72100),
    _t(3, "volatility_breakout", "BUY", 100000, 5, D2, ticker="000660", name="SK하이닉스"),
    _t(4, "kojiro", "BUY", 100000, 3, D2, ticker="000660", name="SK하이닉스"),
    _t(5, "volatility_breakout", "SELL", 102000, 5, D2, ticker="000660", name="SK하이닉스", pl=10000),
    _t(6, "etf_trend", "BUY", 30000, 10, D3, ticker="069500", name="KODEX 200"),
    _t(7, "etf_trend", "SELL", 30300, 10, D3, ticker="069500", name="KODEX 200", pl=3000),
]
COST_ROWS = [
    _cost("005930", D1, buy_amt=700000, fee=99),
    _cost("005930", D2, sll_amt=720000, fee=102, tl_tax=1433),
    _cost("000660", D2, buy_amt=800000, sll_amt=510000, fee=183, tl_tax=1015),
]


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


PAIRS = [
    _pair(buy_date="2026-10-07", sell_date=None, ticker="000660", ticker_name="SK하이닉스",
          buy_price=100000, buy_qty=3, profit_loss=600, profit_rate=0.2, status="open",
          strategy="kojiro", buy_order_nos=["O4"], pair_key="kojiro:000660:O4",
          buy_trade_ids=[4], sell_trade_ids=[]),
    _pair(buy_date="2026-10-08", sell_date="2026-10-08", ticker="069500", ticker_name="KODEX 200",
          buy_price=30000, buy_qty=10, sell_price=30300, sell_qty=10, profit_loss=3000,
          profit_rate=1.0, strategy="etf_trend", buy_order_nos=["O6"], sell_order_nos=["O7"],
          pair_key="etf_trend:069500:O6", buy_trade_ids=[6], sell_trade_ids=[7]),
    _pair(buy_date="2026-10-07", sell_date="2026-10-07", ticker="000660", ticker_name="SK하이닉스",
          buy_price=100000, buy_qty=5, sell_price=102000, sell_qty=5, profit_loss=10000,
          profit_rate=2.0, strategy="volatility_breakout", buy_order_nos=["O3"],
          sell_order_nos=["O5"], pair_key="volatility_breakout:000660:O3",
          buy_trade_ids=[3], sell_trade_ids=[5]),
    _pair(buy_date="2026-10-06", sell_date="2026-10-07", buy_price=70000, buy_qty=10,
          sell_price=72000, sell_qty=10, profit_loss=20000, profit_rate=2.8571,
          buy_order_nos=["O1"], sell_order_nos=["O2"], pair_key="momentum:005930:O1",
          buy_trade_ids=[1], sell_trade_ids=[2]),
]

PERF = [
    {"date": D0, "strategy": "total", "total_asset": 10_000_000, "daily_realized_pnl": 0,
     "daily_profit_rate": 0.0, "cumulative_return_rate": 0.0, "net_external_cashflow": 0,
     "deposit": 0},
    {"date": D1, "strategy": "total", "total_asset": 10_000_000, "daily_realized_pnl": 0,
     "daily_profit_rate": 0.0, "cumulative_return_rate": 0.0, "net_external_cashflow": 0,
     "deposit": 0},
    {"date": D2, "strategy": "total", "total_asset": 10_030_000, "daily_realized_pnl": 30_000,
     "daily_profit_rate": 0.3, "cumulative_return_rate": 0.3, "net_external_cashflow": 0,
     "deposit": 0},
    {"date": D3, "strategy": "total", "total_asset": 10_033_000, "daily_realized_pnl": 3_000,
     "daily_profit_rate": 3_000 / 10_030_000 * 100,
     "cumulative_return_rate": (1.003 * (1 + 3_000 / 10_030_000) - 1) * 100,
     "net_external_cashflow": 0, "deposit": 0},
]


class _Db:
    def __init__(self):
        self.cost_rows = list(COST_ROWS)
        self.trades = list(TRADES)
        self.perf = [dict(r) for r in PERF]
        self.pairs = [dict(p) for p in PAIRS]
        self.history_trades: list[dict] = []
        self.fail_costs = False


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
        if st.fail_costs:
            raise RuntimeError("db down")
        return [r for r in st.cost_rows if start <= r["trad_dt"] <= end]

    async def get_trades_by_status(start, end, statuses=("COMPLETED", "PARTIAL")):
        if st.fail_costs:
            raise RuntimeError("db down")
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


# ── D: /api/performance/daily ────────────────────────────────────────────────

def test_d1_daily_rows_carry_cost_fields_and_keep_gross(db):
    rows = _ok(_client("src.routes.performance").get("/api/performance/daily?days=30"))
    by = {r["date"]: r for r in rows}
    d1, d2, d3 = by["2026-10-06"], by["2026-10-07"], by["2026-10-08"]
    # 기존 칸 불변
    assert d2["daily_profit_rate"] == pytest.approx(0.3)
    assert d2["cumulative_return_rate"] == pytest.approx(0.3)
    assert d2["daily_realized_pnl"] == pytest.approx(30_000)
    # 새 칸
    assert d1["daily_fee"] == pytest.approx(99, abs=1)
    assert d1["daily_tax"] == pytest.approx(0, abs=1)
    assert d1["cost_status"] == "settled"
    assert d2["daily_fee"] == pytest.approx(102 + 183, abs=1)
    assert d2["daily_tax"] == pytest.approx(1433 + 1015, abs=1)
    net2 = 30_000 - (102 + 183) - (1433 + 1015)
    assert d2["daily_net_pnl"] == pytest.approx(net2, abs=1)
    assert d2["net_daily_profit_rate"] == pytest.approx(net2 / 10_000_000 * 100, abs=1e-4)
    cum2 = ((1 - 99 / 10_000_000) * (1 + net2 / 10_000_000) - 1) * 100
    assert d2["net_cumulative_return_rate"] == pytest.approx(cum2, abs=1e-4)
    assert d2["cost_status"] == "settled"
    assert d3["cost_status"] == "estimated"
    assert d3["daily_tax"] == pytest.approx(0)  # ETF 매도세 0
    assert d3["daily_fee"] > 0


def test_d2_strategy_filter_scopes_costs(db):
    rows = _ok(_client("src.routes.performance").get(
        "/api/performance/daily?days=30&strategy=momentum"))
    d2 = {r["date"]: r for r in rows}["2026-10-07"]
    assert d2["daily_fee"] == pytest.approx(102, abs=1)
    assert d2["daily_tax"] == pytest.approx(1433, abs=1)


# ── S: /api/performance/summary ──────────────────────────────────────────────

def test_s1_summary_adds_net_rates_and_keeps_gross(db):
    data = _ok(_client("src.routes.performance").get("/api/performance/summary"))
    gross_cum = PERF[-1]["cumulative_return_rate"]
    assert data["total_profit_rate"] == round(gross_cum, 2)
    assert data["total_days"] == 4
    assert "net_total_profit_rate" in data and "net_avg_daily_profit_rate" in data
    assert data["net_total_profit_rate"] < data["total_profit_rate"]
    assert data["net_avg_daily_profit_rate"] < data["avg_daily_profit_rate"]


# ── H: /api/history ──────────────────────────────────────────────────────────

def test_h1_history_rows_carry_fee_tax_net(db):
    db.history_trades = [
        {k: v for k, v in TRADES[1].items() if k != "trade_date"},
        {k: v for k, v in TRADES[0].items() if k != "trade_date"},
    ]
    data = _ok(_client("src.routes.history").get("/api/history"))
    sell, buy = data["trades"]
    assert sell["trade_type"] == "SELL" and buy["trade_type"] == "BUY"
    # 기존 칸 불변
    assert sell["profit_loss"] == 20000.0
    assert sell["price"] == 72000.0
    # 새 칸
    assert sell["fee"] == pytest.approx(102, abs=1)
    assert sell["tax"] == pytest.approx(1433, abs=1)
    assert sell["net_profit_loss"] == pytest.approx(20000 - 102 - 1433, abs=1)
    assert sell["cost_status"] == "settled"
    assert buy["fee"] == pytest.approx(99, abs=1)
    assert buy["cost_status"] == "settled"


# ── P: /api/history/pnl ──────────────────────────────────────────────────────

def _pnl(db):
    data = _ok(_client("src.routes.history").get("/api/history/pnl?size=200"))
    return data, {p["pair_key"]: p for p in data["pairs"]}


def test_p1_settled_single_pair_costs_bp_slippage(db):
    _, by = _pnl(db)
    p = by["momentum:005930:O1"]
    assert p["profit_loss"] == 20000 and p["profit_rate"] == pytest.approx(2.8571)
    assert p["fee"] == pytest.approx(99 + 102, abs=1)
    assert p["tax"] == pytest.approx(1433, abs=1)
    net = 20000 - 201 - 1433
    assert p["net_profit_loss"] == pytest.approx(net, abs=1)
    assert p["net_profit_rate"] == pytest.approx(net / 700000 * 100, abs=0.01)
    assert p["cost_bp"] == pytest.approx((201 + 1433) / ((700000 + 720000) / 2) * 1e4, abs=0.05)
    assert p["slippage_won"] == pytest.approx((70000 - 69900) * 10 + (72100 - 72000) * 10)
    assert p["cost_status"] == "settled"
    assert p["allocated"] is False


def test_p2_split_day_pair_is_allocated_and_sums_to_kis(db):
    _, by = _pnl(db)
    p = by["volatility_breakout:000660:O3"]
    total = 500000 + 300000 + 510000
    fee = 183 * 500000 / total + 183 * 510000 / total
    assert p["fee"] == pytest.approx(fee, abs=1)
    assert p["tax"] == pytest.approx(1015, abs=1)
    assert p["net_profit_loss"] == pytest.approx(10000 - fee - 1015, abs=1)
    assert p["allocated"] is True
    assert p["cost_status"] == "settled"


def test_p3_unreconciled_etf_pair_estimated_with_zero_tax(db):
    _, by = _pnl(db)
    p = by["etf_trend:069500:O6"]
    assert p["cost_status"] == "estimated"
    assert p["tax"] == 0
    assert p["fee"] > 0
    assert p["net_profit_loss"] == pytest.approx(3000 - p["fee"], abs=1)


def test_p3b_open_pair_paid_buy_fee_plus_estimated_sell_cost(db):
    _, by = _pnl(db)
    p = by["kojiro:000660:O4"]
    assert p["status"] == "open" and p["profit_loss"] == 600
    paid_buy_fee = 183 * 300000 / (500000 + 300000 + 510000)
    assert p["cost_status"] == "estimated"
    assert p["fee"] + p["tax"] > paid_buy_fee  # 예상 매도비용이 더해진다
    assert p["net_profit_loss"] == pytest.approx(600 - p["fee"] - p["tax"], abs=1)


def test_p4_summary_adds_net_totals_and_slippage_count(db):
    data, by = _pnl(db)
    s = data["summary"]
    # 기존 칸 불변
    assert s["realized_total_krw"] == pytest.approx(33000)
    assert s["closed_count"] == 3
    closed = [p for p in by.values() if p["status"] == "closed"]
    assert s["fee_sum"] == pytest.approx(sum(p["fee"] for p in closed), abs=1)
    assert s["tax_sum"] == pytest.approx(1433 + 1015, abs=1)
    assert s["realized_net_total_krw"] == pytest.approx(
        sum(p["net_profit_loss"] for p in closed), abs=1)
    buy_amt = 70000 * 10 + 100000 * 5 + 30000 * 10  # closed 3페어 매수금액(기존 realized_rate_pct 와 같은 분모)
    assert s["realized_net_rate_pct"] == pytest.approx(
        s["realized_net_total_krw"] / buy_amt * 100, abs=0.01)
    assert s["slippage_n"] == 2


# ── F: 비용 조회 실패 = 기존 응답 유지 ─────────────────────────────────────────

def test_f1_cost_failure_keeps_existing_response(db):
    db.fail_costs = True
    data, by = _pnl(db)
    p = by["momentum:005930:O1"]
    assert p["profit_loss"] == 20000
    assert p.get("net_profit_loss") is None
    assert data["summary"]["realized_total_krw"] == pytest.approx(33000)
    rows = _ok(_client("src.routes.performance").get("/api/performance/daily?days=30"))
    assert {r["date"]: r for r in rows}["2026-10-07"]["daily_profit_rate"] == pytest.approx(0.3)


# ── T: /api/strategies/te ────────────────────────────────────────────────────

def test_t1_te_verdict_uses_net(db, monkeypatch):
    strat_route = importlib.import_module("src.routes.strategies")
    strat_route.invalidate_te_cache()
    today = datetime.now(KST).date()
    sd = today - timedelta(days=5)
    trades, pairs = [], []
    for i in range(20):
        b, s = 1000 + 2 * i, 1001 + 2 * i
        trades += [_t(b, "momentum", "BUY", 70000, 10, sd, ticker=f"{100000 + i}"),
                   _t(s, "momentum", "SELL", 70070, 10, sd, ticker=f"{100000 + i}", pl=700)]
        pairs.append(_pair(buy_date=sd.isoformat(), sell_date=sd.isoformat(),
                           ticker=f"{100000 + i}", buy_price=70000, buy_qty=10, sell_price=70070,
                           sell_qty=10, profit_loss=700, profit_rate=0.1,
                           pair_key=f"momentum:{100000 + i}:O{b}", buy_trade_ids=[b],
                           sell_trade_ids=[s]))
    db.trades, db.cost_rows, db.pairs = trades, [], pairs

    async def get_trade_pairs(strategy=None, ticker=None):
        return [dict(p) for p in pairs] if strategy == "momentum" else []

    monkeypatch.setattr(strat_route, "get_trade_pairs", get_trade_pairs)
    try:
        rows = _ok(_client("src.routes.strategies").get("/api/strategies/te?months=3"))
    finally:
        strat_route.invalidate_te_cache()
    m = {r["strategy_id"]: r for r in rows}["momentum"]
    assert m["n"] == 20
    assert m["te_pct_gross"] == pytest.approx(0.1)
    assert m["verdict"] == "inferior"
    assert m["te_pct"] < 0
    assert m["realized_sum_krw"] == pytest.approx(14000)
    assert m["realized_net_sum_krw"] < 0
    assert m["fee_sum"] > 0 and m["tax_sum"] > 0


# ── C: /api/costs/today · /api/costs/daily ───────────────────────────────────

def test_c1_costs_today_estimates_by_strategy(db):
    today = datetime.now(KST).date()
    db.cost_rows = []
    db.trades = [
        _t(41, "momentum", "BUY", 10000, 10, today, ticker="035720", name="카카오"),
        _t(42, "momentum", "SELL", 10100, 10, today, ticker="035720", name="카카오", pl=1000),
        _t(43, "volatility_breakout", "SELL", 20000, 5, today, ticker="035420", name="NAVER", pl=-500),
    ]
    data = _ok(_client("src.routes.costs").get("/api/costs/today"))
    assert data["date"] == today.isoformat()
    assert data["rate_source"] == "default"
    assert data["cost_status"] == "estimated"
    by = {r["strategy"]: r for r in data["strategies"]}
    mo = by["momentum"]
    assert mo["gross_pnl"] == pytest.approx(1000)
    assert mo["fee"] == pytest.approx((100000 + 101000) * 0.00142, abs=1)
    assert mo["tax"] == pytest.approx(101000 * 0.00199, abs=1)
    assert mo["net_pnl"] == pytest.approx(1000 - mo["fee"] - mo["tax"], abs=1)
    vb = by["volatility_breakout"]
    assert vb["net_pnl"] == pytest.approx(-500 - 100000 * (0.00142 + 0.00199), abs=1)
    assert data["total"]["gross_pnl"] == pytest.approx(500)
    assert data["total"]["net_pnl"] == pytest.approx(mo["net_pnl"] + vb["net_pnl"], abs=1)

    one = _ok(_client("src.routes.costs").get("/api/costs/today?strategy=momentum"))
    assert [r["strategy"] for r in one["strategies"]] == ["momentum"]
    assert one["total"]["net_pnl"] == pytest.approx(mo["net_pnl"], abs=1)


def test_c2_costs_daily_series(db):
    data = _ok(_client("src.routes.costs").get("/api/costs/daily?from=2026-10-06&to=2026-10-08"))
    assert data["from"] == "2026-10-06" and data["to"] == "2026-10-08"
    by = {r["date"]: r for r in data["days"]}
    assert [r["date"] for r in data["days"]] == sorted(by)
    assert by["2026-10-06"]["fee"] == pytest.approx(99, abs=1)
    assert by["2026-10-06"]["slippage_won"] == pytest.approx(1000)
    assert by["2026-10-06"]["slippage_n"] == 1
    assert by["2026-10-07"]["fee"] == pytest.approx(285, abs=1)
    assert by["2026-10-07"]["tax"] == pytest.approx(2448, abs=1)
    assert by["2026-10-07"]["cost_status"] == "settled"
    assert by["2026-10-08"]["cost_status"] == "estimated"
    assert by["2026-10-08"]["tax"] == pytest.approx(0)


@pytest.mark.parametrize("qs", ["from=2026-10-08&to=2026-10-06", "from=20261006&to=2026-10-08"])
def test_c2b_costs_daily_bad_range_is_422(db, qs):
    r = _client("src.routes.costs").get(f"/api/costs/daily?{qs}")
    assert r.status_code == 422


# ── B: /api/balance ──────────────────────────────────────────────────────────

def test_b1_balance_holdings_carry_sell_cost_rate(db, monkeypatch):
    from src.models.balance import AccountSummary, StockHolding

    db.cost_rows = []
    holdings = [
        StockHolding(ticker="005930", name="삼성전자", quantity=10, sellable_quantity=10,
                     avg_price=70000, purchase_amount=700000, current_price=72000,
                     eval_amount=720000, eval_profit_loss=20000, eval_profit_rate=2.86),
        StockHolding(ticker="069500", name="KODEX 200", quantity=10, sellable_quantity=10,
                     avg_price=30000, purchase_amount=300000, current_price=30300,
                     eval_amount=303000, eval_profit_loss=3000, eval_profit_rate=1.0),
    ]
    summary = AccountSummary(deposit=0, stock_eval_amount=1023000, total_eval_amount=1023000,
                             net_asset=1023000, purchase_total=1000000, eval_total=1023000,
                             profit_loss_total=23000)
    bal = importlib.import_module("src.routes.balance")
    monkeypatch.setattr(bal, "get_balance", AsyncMock(return_value=(holdings, summary)))
    monkeypatch.setattr(bal, "stock_master_get", AsyncMock(return_value=None))
    monkeypatch.setattr(bal, "resolve_sector_name", AsyncMock(return_value="미분류"))
    data = _ok(_client("src.routes.balance").get("/api/balance"))
    by = {h["ticker"]: h for h in data["holdings"]}
    assert by["005930"]["eval_profit_loss"] == 20000  # 기존 칸 불변
    assert by["005930"]["sell_cost_rate"] == pytest.approx(0.00142 + 0.00199)
    assert by["069500"]["sell_cost_rate"] == pytest.approx(0.00142)
    assert by["005930"]["cost_status"] == "estimated"
    assert data["summary"]["profit_loss_total"] == 23000
