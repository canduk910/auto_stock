"""cycle413 Red — 거래일지 라우트 `GET /api/history/journal` · `PUT /api/history/journal/notes/{anchor_trade_id}`.

명세 = `_workspace/red/cycle413/journal_view_spec.md` 1절 · 계약 = `_workspace/red/cycle413/journal_view_contract.md` 2·3절.
응답 키 정본 = `tests/fixtures/cycle413_journal_shape.json`(프론트 MSW 정직성 테스트와 같은 파일).

| # | 계약 |
|---|---|
| R1 | 기본값 = 최근 30일·20건·all/all/net/recent · `filters` 는 서버가 해석한 값 · `record_start` = `get_record_start()` |
| R2 | 422 — 날짜 형식·from>to·366일 초과·status/outcome/basis/sort 값·page/size 범위 |
| R3 | 기간 = 보유 기간이 [from, to] 와 겹치는 페어(전에 사서 안에 판 것 포함 · 뒤에 산 것 제외 · 보유 중은 매수일만) |
| R4 | status · counts(필터 뒤 total/open/closed) · strategy/ticker 는 `get_trade_pairs` 로 넘긴다 |
| R5 | outcome × basis — net(없으면 gross) 손익 > 0 win · < 0 loss · 모름은 all 에서만 |
| R6 | 정렬 — recent = 보유 중 먼저(매수 시각 ↓) 뒤 청산 시각 ↓ · pnl_asc/pnl_desc · 모름은 맨 뒤 |
| R7 | 페이지 — 카드 세부(체결 행·일지·손절선·메모·종가)는 그 페이지 카드만, 원천마다 1번 |
| R8 | 비용 원천 1번 읽기(`trade_cost.get_trades_by_status` 1회 / 요청) |
| R9 | 실패 격리 — 비용·일지 주문·손절선·메모·종가·AI평가 실패 = 200 + 그 칸만 `lookup_failed` |
| R10 | 응답 키 = shape.json(객체마다 정확히) |
| R11 | `/api/history/pnl` 과 같은 페어의 세후·수수료·세금·체결오차가 같다 |
| N1~N9 | 메모 PUT — 4,000자(코드포인트, strip 뒤)·공백만 = 삭제·UUID 아님 422·BUY 행 없음 404·리포터 키 403·GET 반영 |

DB 경계는 **모듈 속성**으로 갈아 끼운다: `src.routes.history.get_trade_pairs` · `src.db.trade_cost.{get_daily_range,
get_trades_by_status}` · `src.db.trade_journal.*` · `src.db.trade_history.get_trades_by_ids` ·
`src.db.stock_master_daily.{get_closes_in_range,list_business_days}` · `src.db.llm_buy_evaluations.list_by_order_nos`.
시계 = freezegun **2026-10-09 10:00 KST**.
"""

from __future__ import annotations

import importlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
FROZEN = "2026-10-09T01:00:00Z"   # = 10-09 10:00 KST
_ROOT = Path(__file__).resolve().parents[3]
SHAPE = json.loads((_ROOT / "tests" / "fixtures" / "cycle413_journal_shape.json").read_text(encoding="utf-8"))

RS = {"orders_restored": "2026-09-17", "orders_live": "2026-10-01", "stops": "2026-10-01",
      "order_price": "2026-10-01"}


def _u(n: int) -> str:
    return f"7a7a7a7a-0000-4000-8000-{n:012d}"


T = {i: _u(i) for i in range(1, 12)}


def _t(n, strategy, tt, price, qty, ts, *, ticker, name, order_no, pl=None, order_price=None):
    return {
        "id": T[n], "trade_date": date.fromisoformat(ts[:10]), "ticker": ticker, "ticker_name": name,
        "trade_type": tt, "strategy": strategy, "price": Decimal(str(price)), "quantity": qty,
        "profit_loss": Decimal(str(pl)) if pl is not None else (Decimal(0) if tt == "BUY" else None),
        "order_no": order_no, "order_price": None if order_price is None else Decimal(str(order_price)),
        "status": "COMPLETED", "timestamp": f"{ts}.000000+09:00",
    }


# P1 BFB 247540 (10-05→10-08, +44,000 정산) · P2 momentum 005930 (09-01→09-20, 세전 +4,000 / 세후 −160 정산)
# P3 VB 000660 (09-10→09-12, −10,000 추정) · P4 kojiro 035720 보유 중(시세 대기) · P5 donchian 111111 (08-01→08-05, 기간 밖)
# P6 VCP 222222 (09-05→09-15, +3,000 추정)
TRADES = [
    _t(1, "bull_flag_breakout", "BUY", 12350, 40, "2026-10-05T09:12:03", ticker="247540", name="에코프로비엠",
       order_no="B1", order_price=12340),
    _t(2, "bull_flag_breakout", "SELL", 13450, 40, "2026-10-08T14:31:20", ticker="247540", name="에코프로비엠",
       order_no="S1", order_price=13450, pl=44000),
    _t(3, "momentum", "BUY", 10000, 1, "2026-09-01T10:00:00", ticker="005930", name="삼성전자", order_no="B2"),
    _t(4, "momentum", "SELL", 14000, 1, "2026-09-20T10:00:00", ticker="005930", name="삼성전자", order_no="S2",
       pl=4000),
    _t(5, "volatility_breakout", "BUY", 100000, 5, "2026-09-10T09:05:00", ticker="000660", name="SK하이닉스",
       order_no="B3"),
    _t(6, "volatility_breakout", "SELL", 98000, 5, "2026-09-12T15:20:00", ticker="000660", name="SK하이닉스",
       order_no="S3", pl=-10000),
    _t(7, "kojiro", "BUY", 50000, 10, "2026-10-06T10:00:00", ticker="035720", name="카카오", order_no="B4"),
    _t(8, "donchian_swing", "BUY", 10000, 10, "2026-08-01T10:00:00", ticker="111111", name="옛종목", order_no="B5"),
    _t(9, "donchian_swing", "SELL", 10500, 10, "2026-08-05T10:00:00", ticker="111111", name="옛종목", order_no="S5",
       pl=5000),
    _t(10, "vcp_breakout", "BUY", 30000, 10, "2026-09-05T10:00:00", ticker="222222", name="베이스", order_no="B6"),
    _t(11, "vcp_breakout", "SELL", 30300, 10, "2026-09-15T10:00:00", ticker="222222", name="베이스", order_no="S6",
       pl=3000),
]


def _cost(pdno, d, **over):
    row = {"trad_dt": d, "pdno": pdno, "prdt_name": "", "buy_qty": Decimal(0), "buy_amt": Decimal(0),
           "sll_qty": Decimal(0), "sll_amt": Decimal(0), "rlzt_pfls": Decimal(0), "fee": Decimal(0),
           "tl_tax": Decimal(0), "row_count": 1, "raw": []}
    row.update({k: Decimal(str(v)) for k, v in over.items()})
    return row


COST_ROWS = [
    _cost("247540", date(2026, 10, 5), buy_amt=494000, fee=701),
    _cost("247540", date(2026, 10, 8), sll_amt=538000, fee=764, tl_tax=1071),
    # P2 매수 수수료를 크게(요율 창 09-09~ 밖이라 추정 요율은 흔들지 않는다) — 세전 +4,000 / 세후 −160.
    _cost("005930", date(2026, 9, 1), buy_amt=10000, fee=4030),
    _cost("005930", date(2026, 9, 20), sll_amt=14000, fee=20, tl_tax=110),
]


def _pair(buy, sells, *, open_pl=None):
    """`get_trade_pairs()` 한 행(비용 칸 없음 — overlay 가 채운다)."""
    b = next(t for t in TRADES if t["id"] == T[buy])
    ss = [next(t for t in TRADES if t["id"] == T[s]) for s in sells]
    p = {
        "buy_date": b["timestamp"][:10], "buy_time": b["timestamp"][11:19], "ticker": b["ticker"],
        "ticker_name": b["ticker_name"], "buy_price": int(b["price"]), "strategy": b["strategy"],
        "buy_order_nos": [b["order_no"]], "pair_key": f"{b['strategy']}:{b['ticker']}:{b['order_no']}",
        "buy_trade_ids": [b["id"]],
    }
    if ss:
        s = ss[-1]
        pl = int(sum(x["profit_loss"] for x in ss))
        p.update({"sell_date": s["timestamp"][:10], "sell_time": s["timestamp"][11:19], "buy_qty": b["quantity"],
                  "sell_price": int(s["price"]), "sell_qty": s["quantity"], "profit_loss": pl,
                  "profit_rate": round(pl / (int(b["price"]) * b["quantity"]) * 100, 4), "status": "closed",
                  "sell_order_nos": [x["order_no"] for x in ss], "sell_trade_ids": [x["id"] for x in ss],
                  "partial_sell_trade_ids": []})
    else:
        p.update({"sell_date": None, "sell_time": None, "buy_qty": b["quantity"], "sell_price": None,
                  "sell_qty": None, "profit_loss": open_pl, "profit_rate": None, "status": "open",
                  "sell_order_nos": [], "sell_trade_ids": [], "partial_sell_trade_ids": []})
    return p


PAIRS = [_pair(7, []), _pair(1, [2]), _pair(10, [11]), _pair(5, [6]), _pair(3, [4]), _pair(8, [9])]

ORDERS = [
    {"order_date": date(2026, 10, 5), "order_no": "B1", "side": "BUY", "strategy": "bull_flag_breakout",
     "ticker": "247540", "source": "log_harvest", "reason_code": "ENTRY", "reason_sub": None, "judge_price": 12340,
     "order_price": 12340, "order_division": "01", "exchange": None, "parent_order_no": None, "fired_line": None,
     "effective_line": None, "params": {"atr_period": 20}, "noted_at": "2026-10-05T09:12:03+09:00",
     "signal": {"flag_high": 12300, "target_price": 13450, "atr": 410, "price": 12340, "signal_src": "ring",
                "path": "accept"}},
    {"order_date": date(2026, 10, 8), "order_no": "S1", "side": "SELL", "strategy": "bull_flag_breakout",
     "ticker": "247540", "source": "log_harvest", "reason_code": "TAKE_PROFIT", "reason_sub": None,
     "judge_price": 13460, "order_price": None, "order_division": "01", "exchange": None, "parent_order_no": None,
     "fired_line": None, "effective_line": 12350, "params": None, "noted_at": "2026-10-08T14:31:20+09:00",
     "signal": {"signal_name": "TAKE_PROFIT", "reason_line": None, "phrase": "bfb_measured_target",
                "judge_src": "log_price", "current_price": 13460, "target": 13450, "snapshot_age_s": 8,
                "stop_kind": "effective", "path": "accept"}},
    {"order_date": date(2026, 9, 20), "order_no": "S2", "side": "SELL", "strategy": "momentum", "ticker": "005930",
     "source": "log_restore", "reason_code": "TRAILING_STOP", "reason_sub": None, "judge_price": None,
     "order_price": None, "order_division": None, "exchange": None, "parent_order_no": None, "fired_line": None,
     "effective_line": None, "params": None, "noted_at": "2026-09-20T10:00:00+09:00",
     "signal": {"signal_name": "TRAILING_STOP", "reason_line": None, "phrase": None, "judge_src": None,
                "path": "accept"}},
]

STOPS = [
    {"strategy": "bull_flag_breakout", "ticker": "247540", "buy_date": date(2026, 10, 5), "pos_order_no": "B1",
     "observed_at": "2026-10-05T09:12:20+09:00", "event": "first", "stop_price": 11530, "stop_kind": "effective",
     "target_price": 13450, "target_hit": False, "arm_price": None,
     "inputs": {"buy_price": 12350, "quantity": 40, "high_since_buy": 12350}},
    {"strategy": "bull_flag_breakout", "ticker": "247540", "buy_date": date(2026, 10, 5), "pos_order_no": "B1",
     "observed_at": "2026-10-08T14:31:20+09:00", "event": "exit", "stop_price": 12350, "stop_kind": "effective",
     "target_price": 13450, "target_hit": True, "arm_price": None,
     "inputs": {"snapshot_age_s": 8, "sell_order_no": "S1"}},
]

DAYS = [date(2026, 10, d) for d in (1, 2, 5, 6, 7, 8)] + [date(2026, 9, d) for d in (1, 2, 3, 4, 5, 8, 9, 10, 11,
                                                                                      12, 15, 16, 17, 18, 19)]
CLOSES = [
    {"ticker": "247540", "bas_dd": date(2026, 10, d), "close_price": px,
     "updated_at": f"2026-10-{d + 1:02d}T07:50:00+09:00", "flng_cls_code": "00", "prtt_rate": Decimal(0)}
    for d, px in ((5, 12450), (6, 12900), (7, 13120), (8, 13500))
]


class _Db:
    def __init__(self):
        self.pairs = [dict(p) for p in PAIRS]
        self.notes: dict[str, dict] = {}
        self.calls: dict[str, list] = {}
        self.fail: set[str] = set()

    def rec(self, name, *a, **kw):
        self.calls.setdefault(name, []).append((a, kw))
        if name in self.fail:
            raise RuntimeError(f"{name} down")


def _patch(monkeypatch, routes, modname, name, fn):
    mod = importlib.import_module(modname)
    monkeypatch.setattr(mod, name, fn, raising=False)
    # 라우트가 이름으로 import 했어도 같은 가짜를 보게 한다(모듈 속성 경유가 계약이지만 관대하게).
    if hasattr(routes, name):
        monkeypatch.setattr(routes, name, fn)


@pytest.fixture
def db(monkeypatch):
    st = _Db()
    pg = importlib.import_module("src.db.pg")
    monkeypatch.setattr(pg, "fetch", AsyncMock(return_value=[]))
    monkeypatch.setattr(pg, "fetchrow", AsyncMock(return_value=None))
    monkeypatch.setattr(pg, "fetchval", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(pg, "execute", AsyncMock(return_value=None))
    routes = importlib.import_module("src.routes.history")

    async def get_trade_pairs(strategy=None, ticker=None):
        st.rec("get_trade_pairs", strategy=strategy, ticker=ticker)
        return [dict(p) for p in st.pairs
                if (strategy is None or p["strategy"] == strategy) and (ticker is None or p["ticker"] == ticker)]

    monkeypatch.setattr(routes, "get_trade_pairs", get_trade_pairs)

    async def get_daily_range(start, end):
        st.rec("get_daily_range", start, end)
        if "costs" in st.fail:
            raise RuntimeError("db down")
        return [r for r in COST_ROWS if start <= r["trad_dt"] <= end]

    async def get_trades_by_status(start, end, statuses=("COMPLETED", "PARTIAL")):
        st.rec("get_trades_by_status", start, end)
        if "costs" in st.fail:
            raise RuntimeError("db down")
        return [dict(t) for t in TRADES if start <= t["trade_date"] <= end and t["status"] in statuses]

    _patch(monkeypatch, routes, "src.db.trade_cost", "get_daily_range", get_daily_range)
    _patch(monkeypatch, routes, "src.db.trade_cost", "get_trades_by_status", get_trades_by_status)
    monkeypatch.setattr(importlib.import_module("src.db.stock_master"), "get_etf_group_codes",
                        AsyncMock(return_value={}), raising=False)

    async def get_trades_by_ids(ids):
        st.rec("get_trades_by_ids", list(ids))
        want = set(ids)
        return [{k: v for k, v in t.items() if k != "trade_date"} for t in TRADES if t["id"] in want]

    _patch(monkeypatch, routes, "src.db.trade_history", "get_trades_by_ids", get_trades_by_ids)

    async def list_orders(order_nos, *, date_from, date_to):
        st.rec("list_orders", list(order_nos), date_from=date_from, date_to=date_to)
        want = set(order_nos)
        return [dict(o) for o in ORDERS if o["order_no"] in want and date_from <= o["order_date"] <= date_to]

    async def list_stops(keys, *, since, until):
        st.rec("list_stops", list(keys), since=since, until=until)
        want = {tuple(k) for k in keys}
        return [dict(s) for s in STOPS if (s["strategy"], s["ticker"]) in want]

    async def list_notes(anchor_ids):
        st.rec("list_notes", list(anchor_ids))
        return [dict(st.notes[a]) for a in anchor_ids if a in st.notes]

    async def get_record_start():
        st.rec("get_record_start")
        return dict(RS)

    async def upsert_note(anchor_trade_id, body, *, strategy, ticker, buy_date):
        st.rec("upsert_note", anchor_trade_id, body, strategy=strategy, ticker=ticker, buy_date=buy_date)
        prev = st.notes.get(anchor_trade_id)
        row = {"anchor_trade_id": anchor_trade_id, "body": body,
               "created_at": prev["created_at"] if prev else "2026-10-09T10:00:00+09:00",
               "updated_at": "2026-10-09T10:00:01+09:00"}
        st.notes[anchor_trade_id] = row
        return dict(row)

    async def delete_note(anchor_trade_id):
        st.rec("delete_note", anchor_trade_id)
        return st.notes.pop(anchor_trade_id, None) is not None

    for name, fn in (("list_orders", list_orders), ("list_stops", list_stops), ("list_notes", list_notes),
                     ("get_record_start", get_record_start), ("upsert_note", upsert_note),
                     ("delete_note", delete_note)):
        _patch(monkeypatch, routes, "src.db.trade_journal", name, fn)

    async def get_closes_in_range(tickers, start, end):
        st.rec("get_closes_in_range", list(tickers), start, end)
        want = set(tickers)
        return [dict(c) for c in CLOSES if c["ticker"] in want and start <= c["bas_dd"] <= end]

    async def list_business_days(start, end):
        st.rec("list_business_days", start, end)
        return sorted(d for d in DAYS if start <= d <= end)

    _patch(monkeypatch, routes, "src.db.stock_master_daily", "get_closes_in_range", get_closes_in_range)
    _patch(monkeypatch, routes, "src.db.stock_master_daily", "list_business_days", list_business_days)

    async def list_by_order_nos(order_nos, *, trade_date=None):
        st.rec("list_by_order_nos", list(order_nos))
        return []

    _patch(monkeypatch, routes, "src.db.llm_buy_evaluations", "list_by_order_nos", list_by_order_nos)
    return st


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(importlib.import_module("src.routes.history").router)
    return TestClient(app, raise_server_exceptions=False)


def _get(path="/api/history/journal", **params):
    with freeze_time(FROZEN):
        return _client().get(path, params=params)


def _ok(r):
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True, body
    return body["data"]


def _anchors(data):
    return [c["anchor_trade_id"] for c in data["cards"]]


# ── R1 기본값 ────────────────────────────────────────────────────────────────

def test_r1_defaults(db):
    data = _ok(_get())
    assert data["filters"] == {"from": "2026-09-09", "to": "2026-10-09", "strategy": None, "ticker": None,
                               "status": "all", "outcome": "all", "basis": "net", "sort": "recent"}
    assert (data["page"], data["size"], data["total"], data["total_pages"]) == (1, 20, 5, 1)
    assert data["counts"] == {"total": 5, "open": 1, "closed": 4}
    assert data["cost_available"] is True
    assert data["record_start"] == RS
    assert len(db.calls["get_record_start"]) == 1


# ── R2 422 ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("params", [
    {"from": "2026-9-01", "to": "2026-10-09"},
    {"from": "2026-10-09", "to": "2026-10-01"},
    {"from": "2025-10-08", "to": "2026-10-09"},          # 367일
    {"status": "holding"}, {"outcome": "even"}, {"basis": "after_tax"}, {"sort": "oldest"},
    {"page": 0}, {"size": 0}, {"size": 101},
])
def test_r2_invalid_query_is_422(db, params):
    assert _get(**params).status_code == 422


def test_r2_366_days_is_allowed(db):
    _ok(_get(**{"from": "2025-10-09", "to": "2026-10-09"}))


# ── R3 기간 겹침 ──────────────────────────────────────────────────────────────

def test_r3_period_overlap_includes_spanning_excludes_later_buys(db):
    data = _ok(_get(**{"from": "2026-09-01", "to": "2026-10-01"}))
    assert set(_anchors(data)) == {T[3], T[5], T[10]}      # P1·P4 는 기간 뒤 매수, P5 는 기간 전 청산
    data2 = _ok(_get(**{"from": "2026-08-03", "to": "2026-08-31"}))
    assert _anchors(data2) == [T[8]]                       # 기간 전(08-01)에 사서 기간 안(08-05)에 판 것


# ── R4 상태·건수·전략/종목 ─────────────────────────────────────────────────────

def test_r4_status_and_counts(db):
    op = _ok(_get(status="open"))
    assert _anchors(op) == [T[7]] and op["counts"] == {"total": 1, "open": 1, "closed": 0}
    cl = _ok(_get(status="closed"))
    assert set(_anchors(cl)) == {T[1], T[3], T[5], T[10]}
    assert cl["counts"] == {"total": 4, "open": 0, "closed": 4} and cl["filters"]["status"] == "closed"


def test_r4_strategy_and_ticker_go_to_get_trade_pairs(db):
    data = _ok(_get(strategy="bull_flag_breakout", ticker="247540"))
    assert _anchors(data) == [T[1]]
    assert db.calls["get_trade_pairs"][-1][1] == {"strategy": "bull_flag_breakout", "ticker": "247540"}
    assert data["filters"]["strategy"] == "bull_flag_breakout" and data["filters"]["ticker"] == "247540"
    empty = _ok(_get(strategy="no_such_strategy"))
    assert empty["cards"] == [] and empty["counts"] == {"total": 0, "open": 0, "closed": 0}


# ── R5 이익/손실 × 세후/세전 ───────────────────────────────────────────────────

@pytest.mark.parametrize("outcome,basis,expect", [
    ("win", "gross", {1, 3, 10}),
    ("win", "net", {1, 10}),         # P2 = 세전 +4,000 / 세후 −160
    ("loss", "net", {3, 5}),
    ("loss", "gross", {5}),
])
def test_r5_outcome_by_basis(db, outcome, basis, expect):
    data = _ok(_get(outcome=outcome, basis=basis))
    assert set(_anchors(data)) == {T[i] for i in expect}
    assert T[7] not in _anchors(data)    # 보유 중 시세 대기(모름)는 all 에서만


def test_r5_net_falls_back_to_gross_when_costs_failed(db):
    db.fail.add("costs")
    data = _ok(_get(outcome="win", basis="net"))
    assert data["cost_available"] is False
    assert set(_anchors(data)) == {T[1], T[3], T[10]}


# ── R6 정렬 ──────────────────────────────────────────────────────────────────

def test_r6_recent_is_open_first_then_close_time_desc(db):
    # /pnl(매수 시각 순)이면 P3(09-10 매수)가 P2(09-01 매수, 09-20 청산)보다 앞이다 — 일지는 청산 시각 순.
    assert _anchors(_ok(_get())) == [T[7], T[1], T[3], T[10], T[5]]


@pytest.mark.parametrize("sort,basis,expect", [
    ("pnl_asc", "net", [5, 3, 10, 1, 7]),      # P3 −12.5k · P2 −160 · P6 +1.5k · P1 +41k · P4 모름
    ("pnl_desc", "net", [1, 10, 3, 5, 7]),
    ("pnl_asc", "gross", [5, 10, 3, 1, 7]),    # P3 −10k · P6 +3k · P2 +4k · P1 +44k — basis 가 순서를 바꾼다
    ("pnl_desc", "gross", [1, 3, 10, 5, 7]),
])
def test_r6_pnl_sorts_unknown_last(db, sort, basis, expect):
    assert _anchors(_ok(_get(sort=sort, basis=basis))) == [T[i] for i in expect]


# ── R7 페이지 · 카드 세부는 그 페이지만 ────────────────────────────────────────

def test_r7_page_slices_and_details_read_only_page_cards(db):
    data = _ok(_get(size=2, page=2))
    assert _anchors(data) == [T[3], T[10]]
    assert (data["page"], data["size"], data["total"], data["total_pages"]) == (2, 2, 5, 3)
    assert data["counts"] == {"total": 5, "open": 1, "closed": 4}
    assert len(db.calls["get_trades_by_ids"]) == 1
    assert set(db.calls["get_trades_by_ids"][0][0][0]) == {T[3], T[4], T[10], T[11]}
    assert len(db.calls["list_orders"]) == 1
    assert set(db.calls["list_orders"][0][0][0]) == {"B2", "S2", "B6", "S6"}
    assert len(db.calls["list_stops"]) == 1
    assert {tuple(k) for k in db.calls["list_stops"][0][0][0]} <= {("momentum", "005930"),
                                                                   ("vcp_breakout", "222222")}
    assert len(db.calls["list_notes"]) == 1 and set(db.calls["list_notes"][0][0][0]) <= {T[3], T[10]}
    assert len(db.calls["get_closes_in_range"]) == 1
    assert set(db.calls["get_closes_in_range"][0][0][0]) <= {"005930", "222222"}


# ── R8 비용 원천 1번 ──────────────────────────────────────────────────────────

def test_r8_cost_source_read_once_per_request(db):
    _ok(_get(size=100))
    assert len(db.calls["get_trades_by_status"]) == 1, "c411 F8 — 비용 원천(체결 행)을 두 번 읽지 않는다"


# ── R9 실패 격리 ──────────────────────────────────────────────────────────────

def _card(data, n):
    return next(c for c in data["cards"] if c["anchor_trade_id"] == T[n])


def test_r9_cost_failure_marks_only_cost_cells(db):
    db.fail.add("costs")
    data = _ok(_get())
    assert data["cost_available"] is False
    for c in data["cards"]:
        assert c["costs"]["na"] == "lookup_failed"
        assert c["costs"]["entry_fee"] is None and c["costs"]["paid_total"] is None
        assert c["pnl"]["net_krw"] is None and c["pnl"]["net_na"] == "lookup_failed"
    p1 = _card(data, 1)
    assert p1["pnl"]["gross_krw"] == 44000
    assert p1["entry"]["reason"]["text"] == "깃발 상단 12,300 돌파 · 측정 목표 13,450 · ATR 410"


@pytest.mark.parametrize("source,check", [
    ("list_orders", lambda c: c["entry"]["reason"]["na"] == "lookup_failed"
     and c["exits"][0]["reason"]["na"] == "lookup_failed" and c["stop_track"]["na"] is None),
    ("list_stops", lambda c: c["stop_track"]["na"] == "lookup_failed"
     and c["entry"]["initial_stop"]["na"] == "lookup_failed" and c["entry"]["reason"]["na"] is None),
    ("get_closes_in_range", lambda c: c["excursion"]["na"] == "lookup_failed"
     and c["entry"]["reason"]["na"] is None and c["stop_track"]["na"] is None),
    ("list_business_days", lambda c: c["excursion"]["na"] == "lookup_failed"),
    ("list_notes", lambda c: c["note"] is None and c["entry"]["reason"]["na"] is None),
    ("list_by_order_nos", lambda c: c["entry"]["reason"]["text"] is not None),
    ("get_trades_by_ids", lambda c: c["pnl"]["gross_krw"] == 44000),
])
def test_r9_each_source_failure_is_200_and_local(db, source, check):
    db.fail.add(source)
    data = _ok(_get())
    assert len(data["cards"]) == 5
    assert check(_card(data, 1)), source


# ── R10 응답 키 = shape.json ──────────────────────────────────────────────────

def _keys(obj, kind, path, bad):
    if obj is None:
        return
    got, want = sorted(obj), sorted(SHAPE[kind])
    if got != want:
        bad.append(f"{path} ({kind}): +{sorted(set(got) - set(want))} −{sorted(set(want) - set(got))}")


def _check_shape(data):
    bad: list[str] = []
    _keys(data, "response", "data", bad)
    for k in ("record_start", "filters", "counts"):
        _keys(data[k], k, k, bad)
    for i, c in enumerate(data["cards"]):
        p = f"cards[{i}]"
        _keys(c, "card", p, bad)
        _keys(c["pnl"], "pnl", f"{p}.pnl", bad)
        e = c["entry"]
        _keys(e, "entry", f"{p}.entry", bad)
        for j, ln in enumerate(e["orders"]):
            _keys(ln, "order_line", f"{p}.entry.orders[{j}]", bad)
            _keys(ln["judge"], "judge", f"{p}.entry.orders[{j}].judge", bad)
            _keys(ln["slip_order"], "slip", f"{p}.entry.orders[{j}].slip_order", bad)
            _keys(ln["slip_judge"], "slip", f"{p}.entry.orders[{j}].slip_judge", bad)
        _keys(e["reason"], "reason", f"{p}.entry.reason", bad)
        _keys(e["initial_stop"], "stop_point", f"{p}.entry.initial_stop", bad)
        _keys(e["initial_stop"]["first_seen"], "first_seen", f"{p}.entry.initial_stop.first_seen", bad)
        _keys(e["target"], "target", f"{p}.entry.target", bad)
        for j, x in enumerate(c["exits"]):
            _keys(x, "exit_line", f"{p}.exits[{j}]", bad)
            _keys(x["judge"], "judge", f"{p}.exits[{j}].judge", bad)
            _keys(x["slip_order"], "slip", f"{p}.exits[{j}].slip_order", bad)
            _keys(x["slip_judge"], "slip", f"{p}.exits[{j}].slip_judge", bad)
            _keys(x["reason"], "reason", f"{p}.exits[{j}].reason", bad)
        _keys(c["stop_track"], "stop_track", f"{p}.stop_track", bad)
        for j, r in enumerate(c["stop_track"]["rows"]):
            _keys(r, "stop_row", f"{p}.stop_track.rows[{j}]", bad)
        _keys(c["costs"], "costs", f"{p}.costs", bad)
        for j, x in enumerate(c["costs"]["exits"]):
            _keys(x, "cost_exit", f"{p}.costs.exits[{j}]", bad)
        _keys(c["excursion"], "excursion", f"{p}.excursion", bad)
        _keys(c["excursion"]["mfe"], "ex_point", f"{p}.excursion.mfe", bad)
        _keys(c["excursion"]["mae"], "ex_point", f"{p}.excursion.mae", bad)
        _keys(c["note"], "note", f"{p}.note", bad)
    assert not bad, "응답 키가 shape.json 과 다르다:\n  " + "\n  ".join(bad)


def test_r10_response_keys_match_shape_file(db):
    db.notes[T[1]] = {"anchor_trade_id": T[1], "body": "메모", "created_at": "2026-10-08T15:00:00+09:00",
                      "updated_at": "2026-10-08T15:05:00+09:00"}
    data = _ok(_get())
    _check_shape(data)
    p1 = _card(data, 1)
    assert p1["note"] == {"body": "메모", "updated_at": "2026-10-08T15:05:00+09:00"}
    assert p1["stop_track"]["rows"] and p1["excursion"]["mfe"] is not None   # 빈 껍데기로 통과하지 않게
    assert p1["entry"]["orders"][0]["slip_order"] is not None


def test_r10_shape_also_holds_when_every_source_failed(db):
    db.fail.update({"costs", "list_orders", "list_stops", "list_notes", "get_closes_in_range",
                    "list_business_days", "list_by_order_nos"})
    _check_shape(_ok(_get()))


# ── R11 /pnl 패리티 ───────────────────────────────────────────────────────────

def test_r11_parity_with_pnl_route(db):
    j = _ok(_get(size=100))
    with freeze_time(FROZEN):
        pairs = {p["pair_key"]: p for p in _ok(_client().get("/api/history/pnl", params={"size": 200}))["pairs"]}
    checked = 0
    for c in j["cards"]:
        if c["status"] != "closed":
            continue
        p = pairs[c["pair_key"]]
        assert c["pnl"]["gross_krw"] == p["profit_loss"]
        assert c["pnl"]["net_krw"] == pytest.approx(p["net_profit_loss"], abs=0.01), c["pair_key"]
        co = c["costs"]
        assert co["entry_fee"] + sum(x["fee"] for x in co["exits"]) == pytest.approx(p["fee"], abs=0.01)
        assert sum(x["tax"] for x in co["exits"]) == pytest.approx(p["tax"], abs=0.01)
        slips = [ln["slip_order"]["total_won"] for ln in c["entry"]["orders"] + c["exits"]
                 if ln["slip_order"] and ln["slip_order"]["ref_src"] == "trade"]
        if p["slippage_won"] is None:
            assert slips == []
        else:
            assert sum(slips) == pytest.approx(p["slippage_won"], abs=1)
        checked += 1
    assert checked == 4


# ── N 메모 PUT ───────────────────────────────────────────────────────────────

def _put(anchor, payload):
    with freeze_time(FROZEN):
        return _client().put(f"/api/history/journal/notes/{anchor}", json=payload)


def test_n1_4000_chars_ok_with_dup_columns_from_buy_row(db):
    body = "가" * 4000
    data = _ok(_put(T[1], {"body": body}))
    assert sorted(data) == sorted(SHAPE["note_put"])
    assert data["anchor_trade_id"] == T[1] and data["body"] == body
    assert data["updated_at"].endswith("+09:00") and data["created_at"].endswith("+09:00")
    (args, kw), = db.calls["upsert_note"]
    assert args == (T[1], body)
    assert kw == {"strategy": "bull_flag_breakout", "ticker": "247540", "buy_date": date(2026, 10, 5)}


def test_n2_strip_then_count_codepoints(db):
    body = "😀" * 4000   # 코드포인트 4,000 (UTF-16 으로는 8,000)
    _ok(_put(T[1], {"body": "  \n" + body + "\t "}))
    assert db.calls["upsert_note"][0][0] == (T[1], body)
    _ok(_put(T[1], {"body": "  메모 한 줄\n둘째 줄  "}))
    assert db.calls["upsert_note"][1][0] == (T[1], "메모 한 줄\n둘째 줄")


@pytest.mark.parametrize("payload", [{"body": "가" * 4001}, {"body": 123}, {"body": None}, {}])
def test_n3_invalid_body_is_422_and_writes_nothing(db, payload):
    assert _put(T[1], payload).status_code == 422
    assert "upsert_note" not in db.calls and "delete_note" not in db.calls


def test_n4_whitespace_only_deletes(db):
    db.notes[T[1]] = {"anchor_trade_id": T[1], "body": "x", "created_at": "c", "updated_at": "u"}
    r = _put(T[1], {"body": "  \n\t "})
    assert r.status_code == 200 and r.json()["success"] is True and r.json()["data"] is None
    assert db.calls["delete_note"] == [((T[1],), {})]
    assert "upsert_note" not in db.calls


def test_n5_not_uuid_is_422(db):
    assert _put("not-a-uuid", {"body": "x"}).status_code == 422
    assert "upsert_note" not in db.calls


@pytest.mark.parametrize("anchor", [_u(999), T[2]])   # 없는 id · 매도 행 id
def test_n6_no_buy_row_is_404(db, anchor):
    assert _put(anchor, {"body": "x"}).status_code == 404
    assert "upsert_note" not in db.calls


def test_n7_get_reflects_saved_note(db):
    _ok(_put(T[1], {"body": "재진입 금지"}))
    assert _card(_ok(_get()), 1)["note"]["body"] == "재진입 금지"
    _ok(_put(T[1], {"body": " "}))
    assert _card(_ok(_get()), 1)["note"] is None


# ── N8 리포터 키 403 (실제 미들웨어) ──────────────────────────────────────────

@pytest.mark.real_api_auth
async def test_n8_reporter_key_put_note_is_403_operator_passes(monkeypatch):
    from tests.unit.middleware.test_cycle243_api_auth import _drive, _scope, _status_of
    from tests.unit.middleware.test_cycle249_reporter_scope import OPERATOR_KEY, REPORTER_KEY, _app, _hdr

    path = f"/api/history/journal/notes/{T[1]}"
    app = _app(monkeypatch)
    sent = await _drive(app, _scope(method="PUT", path=path, headers=_hdr(REPORTER_KEY)))
    assert _status_of(sent) == 403
    app = _app(monkeypatch)
    sent = await _drive(app, _scope(method="PUT", path=path, headers=_hdr(OPERATOR_KEY)))
    assert _status_of(sent) == 200
    app = _app(monkeypatch)
    sent = await _drive(app, _scope(method="GET", path="/api/history/journal", headers=_hdr(REPORTER_KEY)))
    assert _status_of(sent) == 200   # 읽기는 리포터도 된다(cycle249 규약)
