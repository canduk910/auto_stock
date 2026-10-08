"""cycle411 보완 Red — 통합 검증이 찾은 라우트 결함 고정 (메인 세션 결정 10-08 「보완 결정」).

계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「보완 결정」 절.
재현 원본 = tester 합성 시나리오 x1~x10.

| # | 계약 |
|---|---|
| H1 | 세후 누적수익률은 **개시 이래** 축 — 창 첫 행부터 다시 쌓지 않는다. 비용 0 이면 net = gross (daily 1e-9 · summary 는 4자리 반올림이라 1e-4) |
| H2 | 배분 모집단 = 그 날짜 범위 **전체 COMPLETED+PARTIAL 체결** — id·전략·페이지로는 배분 **뒤에** 거른다. CANCELLED·PENDING 은 비용 없음 |
| M1 | `/api/balance` 보유 종목마다 `buy_fee_paid`(정산 실측 → 없으면 추정) + `buy_fee_status` |
| M2 | 추정 요율 창 = **서버 오늘(KST) 기준 최근 30달력일** `[today−30, today]` 정산 행 — 모든 라우트 공통(화면 날짜 범위 아님) |
| M3 | ETF 판정 = `stock_master` 구분 코드(`is_etf_like(raw, name)`) — `BNK금융지주`(주식) 매도세 > 0 · `KIWOOM 200`(ETF) 0 |
| M4 | 「모름」 ≠ 0 — 비용 조회 실패 시 `/api/history/pnl` summary 의 net·fee·tax 합 = None · `order_price` 가 하나도 없는 페어 `slippage_won` = None |
| L2 | 분할 매도 뒤 보유 중 페어 — 매수 수수료는 남은 수량 비율만, 판 몫의 비용은 `partial_fee`·`partial_tax` (총합 보존) |

DB 경계(모듈 속성만 갈아 끼운다 — 구현은 모듈 경유로 부른다):
`src.db.trade_cost.{get_daily_range,get_trades_by_status}` · `src.db.daily_performance.get_performance`
(라우트 모듈 속성 `src.routes.performance.get_performance` 포함) · `src.db.trade_history.get_trade_pairs`
(잔고 M1) · `src.db.stock_master.get`(ETF 판정 M3). 시계 = freezegun 으로 **2026-10-07 12:00 KST** 고정.
"""

from __future__ import annotations

import importlib
import logging
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from freezegun import freeze_time

pytestmark = pytest.mark.unit

D1 = date(2026, 10, 6)
D2 = date(2026, 10, 7)  # 고정된 「오늘」
FROZEN = "2026-10-07T03:00:00Z"  # = 2026-10-07 12:00 KST


def _cost(pdno, trad_dt, **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "",
        "buy_qty": Decimal(0), "buy_amt": Decimal(0), "sll_qty": Decimal(0),
        "sll_amt": Decimal(0), "rlzt_pfls": Decimal(0), "fee": Decimal(0),
        "tl_tax": Decimal(0), "row_count": 1, "raw": [],
    }
    row.update({k: Decimal(str(v)) for k, v in over.items()})
    return row


def _t(tid, strategy, tt, price, qty, d, *, ticker="000660", name="SK하이닉스", pl=0,
       order_price=None, status="COMPLETED") -> dict:
    return {
        "id": tid, "trade_date": d, "ticker": ticker, "ticker_name": name, "trade_type": tt,
        "strategy": strategy, "price": Decimal(str(price)), "quantity": qty,
        "profit_loss": Decimal(str(pl)), "order_no": f"O{tid}",
        "order_price": None if order_price is None else Decimal(str(order_price)),
        "status": status,
        "timestamp": f"{d.isoformat()}T10:00:{tid % 60:02d}+09:00",
    }


def _hist(t: dict) -> dict:
    """`get_trades` 가 돌려주는 raw 행 모양 — `trade_date` 칸이 없다."""
    return {k: v for k, v in t.items() if k != "trade_date"}


def _pair(**kw) -> dict:
    base = {
        "buy_date": None, "buy_time": "09:01:00", "sell_date": None, "sell_time": "10:00:00",
        "ticker": "000660", "ticker_name": "SK하이닉스", "buy_price": 0, "buy_qty": 0,
        "sell_price": None, "sell_qty": None, "profit_loss": 0, "profit_rate": 0.0,
        "status": "closed", "strategy": "volatility_breakout", "buy_order_nos": [],
        "sell_order_nos": [], "pair_key": None, "buy_trade_ids": [], "sell_trade_ids": [],
        "partial_sell_trade_ids": [],
    }
    base.update(kw)
    return base


class _Db:
    def __init__(self):
        self.cost_rows: list[dict] = []
        self.trades: list[dict] = []
        self.perf: list[dict] = []
        self.pairs: list[dict] = []
        self.history_trades: list[dict] = []
        self.stock_raw: dict[str, dict] = {}
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
        return [dict(t) for t in st.trades
                if start <= t["trade_date"] <= end and t["status"] in statuses]

    monkeypatch.setattr(tcdb, "get_daily_range", get_daily_range)
    monkeypatch.setattr(tcdb, "get_trades_by_status", get_trades_by_status)

    async def get_performance(days=30, strategy="total"):
        return [dict(r) for r in st.perf if r["strategy"] == strategy][-days:]

    async def get_latest_performance(strategy="total"):
        rows = [r for r in st.perf if r["strategy"] == strategy]
        return dict(rows[-1]) if rows else None

    dp = importlib.import_module("src.db.daily_performance")
    monkeypatch.setattr(dp, "get_performance", get_performance)
    monkeypatch.setattr(dp, "get_latest_performance", get_latest_performance)
    perf_route = importlib.import_module("src.routes.performance")
    monkeypatch.setattr(perf_route, "get_performance", get_performance)
    monkeypatch.setattr(perf_route, "get_latest_performance", get_latest_performance)

    async def get_trade_pairs(strategy=None, ticker=None):
        return [dict(p) for p in st.pairs
                if (strategy is None or p["strategy"] == strategy)
                and (ticker is None or p["ticker"] == ticker)]

    async def get_trades(limit=20, offset=0, ticker=None, strategy=None):
        rows = [dict(t) for t in st.history_trades if strategy is None or t["strategy"] == strategy]
        return rows[offset:offset + limit], len(rows)

    th = importlib.import_module("src.db.trade_history")
    monkeypatch.setattr(th, "get_trade_pairs", get_trade_pairs)
    hist_route = importlib.import_module("src.routes.history")
    monkeypatch.setattr(hist_route, "get_trade_pairs", get_trade_pairs)
    monkeypatch.setattr(hist_route, "get_trades", get_trades)

    from src.models.stock import StockBasics

    async def sm_get(ticker):
        raw = st.stock_raw.get(ticker)
        return None if raw is None else StockBasics(ticker=ticker, raw=raw)

    sm = importlib.import_module("src.db.stock_master")
    monkeypatch.setattr(sm, "get_master_raw", AsyncMock(return_value=None))
    monkeypatch.setattr(sm, "get", sm_get)

    # cycle411 2차 보완 F1 — ETF 판정 일괄 조회(`get_etf_group_codes`)도 같은 원천을 본다.
    async def sm_codes(tickers):
        return {t: (st.stock_raw.get(t) or {}).get("scty_grp_id_cd") for t in tickers}

    monkeypatch.setattr(sm, "get_etf_group_codes", sm_codes, raising=False)

    with freeze_time(FROZEN):
        yield st


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


# ── H1: 세후 누적 = 개시 이래 ────────────────────────────────────────────────────

_START = date(2026, 8, 1)
_N = 40


def _asset(i: int) -> float:
    """i 번째 행의 정산 자산 — 매일 +0.5% (i = −1 이 개시 원금 1,000만)."""
    return 10_000_000 * 1.005 ** (i + 1)


def _perf_40(strategy="total") -> list[dict]:
    rows = []
    for i in range(_N):
        rows.append({
            "date": _START + timedelta(days=i), "strategy": strategy, "total_asset": _asset(i),
            "daily_realized_pnl": _asset(i - 1) * 0.005, "daily_profit_rate": 0.5,
            "cumulative_return_rate": (1.005 ** (i + 1) - 1) * 100,
            "net_external_cashflow": 0, "deposit": 0,
        })
    return rows


def test_h1a_daily_net_cumulative_equals_gross_when_no_cost(db):
    """비용 0 — 창(30행)의 net 누적이 개시 이래 gross 누적과 같다(창 첫 행부터 다시 쌓지 않는다)."""
    db.perf = _perf_40()
    rows = _ok(_client("src.routes.performance").get("/api/performance/daily?days=30"))
    assert len(rows) == 30
    for r in rows:
        assert r["net_cumulative_return_rate"] == pytest.approx(r["cumulative_return_rate"], abs=1e-9), r


def test_h1b_summary_net_total_equals_gross_since_inception_when_no_cost(db):
    db.perf = _perf_40()
    data = _ok(_client("src.routes.performance").get("/api/performance/summary"))
    latest_gross = db.perf[-1]["cumulative_return_rate"]
    assert data["total_profit_rate"] == round(latest_gross, 2)  # 기존 칸 불변
    # summary net 은 4자리 반올림 — 반올림 오차 안에서 개시 이래 gross 와 같아야 한다
    assert data["net_total_profit_rate"] == pytest.approx(latest_gross, abs=1e-4)


def test_h1c_net_cumulative_chains_prewindow_with_in_window_cost(db):
    """창 안 하루(35번째 행)에 비용 5,000원 — 그 날부터 net 누적은 개시 이래 gross 축에서 그만큼 낮다."""
    db.perf = _perf_40()
    cost_day = _START + timedelta(days=35)
    db.trades = [_t(1, "momentum", "BUY", 100_000, 5, cost_day)]
    db.cost_rows = [_cost("000660", cost_day, buy_amt=500_000, fee=5_000)]

    factor_35 = 1.005 - 5_000 / _asset(34)

    def expect_cum(i: int) -> float:
        if i < 35:
            return (1.005 ** (i + 1) - 1) * 100
        return (1.005 ** i * factor_35 - 1) * 100

    rows = _ok(_client("src.routes.performance").get("/api/performance/daily?days=30"))
    for r in rows:
        i = (date.fromisoformat(r["date"]) - _START).days
        assert r["net_cumulative_return_rate"] == pytest.approx(expect_cum(i), abs=1e-9), (i, r)

    data = _ok(_client("src.routes.performance").get("/api/performance/summary"))
    assert data["net_total_profit_rate"] == pytest.approx(expect_cum(_N - 1), abs=1e-4)


# ── H2: 배분 모집단 = 날짜 범위 전체 체결 ───────────────────────────────────────

_TOT = 500_000 + 300_000 + 510_000  # 같은 날·종목 3주문(2전략)의 체결금액 합


def _three_orders(db):
    db.trades = [
        _t(1, "volatility_breakout", "BUY", 100_000, 5, D2),
        _t(2, "kojiro", "BUY", 100_000, 3, D2),
        _t(3, "volatility_breakout", "SELL", 102_000, 5, D2, pl=10_000),
    ]
    db.cost_rows = [_cost("000660", D2, buy_amt=800_000, sll_amt=510_000, fee=183, tl_tax=1015)]


_FEE = {1: 183 * 500_000 / _TOT, 2: 183 * 300_000 / _TOT, 3: 183 * 510_000 / _TOT}


def test_h2a_history_page_slice_gets_full_population_share(db):
    """페이지에 1행만 있어도 그 행 몫은 날짜 범위 전체 체결 기준 배분 몫이다(정산 1행 전부를 떠안지 않는다)."""
    _three_orders(db)
    db.history_trades = [_hist(t) for t in db.trades]
    c = _client("src.routes.history")
    full = {t["id"]: t for t in _ok(c.get("/api/history?page=1&size=100"))["trades"]}
    assert sum(t["fee"] for t in full.values()) == pytest.approx(183, abs=1e-6)
    for tid, fee in _FEE.items():
        assert full[tid]["fee"] == pytest.approx(fee, abs=1e-6), full[tid]

    for page in (1, 2, 3):
        (row,) = _ok(c.get(f"/api/history?page={page}&size=1"))["trades"]
        assert row["fee"] == pytest.approx(_FEE[row["id"]], abs=1e-6), (page, row)
    (sell,) = [t for t in _ok(c.get("/api/history?page=3&size=1"))["trades"]]
    assert sell["tax"] == pytest.approx(1015, abs=1e-6)


def test_h2b_history_strategy_filter_keeps_full_population_share(db):
    _three_orders(db)
    db.history_trades = [_hist(t) for t in db.trades]
    rows = _ok(_client("src.routes.history").get(
        "/api/history?page=1&size=100&strategy=volatility_breakout"))["trades"]
    assert {r["id"] for r in rows} == {1, 3}
    for r in rows:
        assert r["fee"] == pytest.approx(_FEE[r["id"]], abs=1e-6), r


@pytest.mark.parametrize("status", ["CANCELLED", "PENDING"])
def test_h2c_history_cancelled_pending_rows_carry_no_cost(db, status):
    """CANCELLED·PENDING 행은 배분 대상이 아니다 — 비용 칸 None, 다른 행 몫도 그대로."""
    _three_orders(db)
    ghost = _t(9, "kojiro", "BUY", 100_000, 7, D2, status=status)
    db.history_trades = [_hist(t) for t in db.trades] + [_hist(ghost)]
    rows = {t["id"]: t for t in _ok(_client("src.routes.history").get(
        "/api/history?page=1&size=100"))["trades"]}
    assert rows[9]["status"] == status
    assert rows[9].get("fee") is None and rows[9].get("cost_status") is None, rows[9]
    for tid, fee in _FEE.items():
        assert rows[tid]["fee"] == pytest.approx(fee, abs=1e-6), rows[tid]


def test_h2d_performance_daily_strategy_filter_gets_its_share_only(db):
    _three_orders(db)
    for d in (D1, D2):
        db.perf.append({"date": d, "strategy": "kojiro", "total_asset": 1_000_000,
                        "daily_realized_pnl": 0, "daily_profit_rate": 0.0,
                        "cumulative_return_rate": 0.0, "net_external_cashflow": 0, "deposit": 0})
    rows = _ok(_client("src.routes.performance").get("/api/performance/daily?strategy=kojiro"))
    d2 = {r["date"]: r for r in rows}["2026-10-07"]
    assert d2["daily_fee"] == pytest.approx(_FEE[2], abs=1e-6), d2
    assert d2["daily_tax"] == pytest.approx(0, abs=1e-9), d2


def test_h2e_costs_today_strategy_filter_equals_its_share_in_full(db):
    _three_orders(db)
    c = _client("src.routes.costs")
    allv = _ok(c.get("/api/costs/today"))
    kj_in_all = {s["strategy"]: s for s in allv["strategies"]}["kojiro"]
    assert kj_in_all["fee"] == pytest.approx(_FEE[2], abs=1e-6)
    kj = _ok(c.get("/api/costs/today?strategy=kojiro"))
    assert [s["strategy"] for s in kj["strategies"]] == ["kojiro"]
    assert kj["total"]["fee"] == pytest.approx(_FEE[2], abs=1e-6), kj
    assert kj["total"]["tax"] == pytest.approx(0, abs=1e-9), kj


# ── M2: 추정 요율 창 = 서버 오늘 기준 최근 30달력일 ─────────────────────────────

# 창 안(09-20) 정산 표본 → 수수료율 0.003 · 세율 0.004
_IN_WINDOW = _cost("111111", date(2026, 9, 20), buy_amt=1_000_000, sll_amt=1_000_000,
                   fee=6_000, tl_tax=4_000)
# 창 밖(08-20, 오늘−48일) — 섞이면 수수료율이 0.05 로 튄다
_OUT_WINDOW = _cost("222222", date(2026, 8, 20), buy_amt=100_000, fee=100_000)


def _m2_setup(db, d=D2):
    db.cost_rows = [_IN_WINDOW, _OUT_WINDOW]
    db.trades = [
        _t(49, "momentum", "BUY", 9_990, 10, d, ticker="035720", name="카카오"),
        _t(50, "momentum", "SELL", 10_000, 10, d, ticker="035720", name="카카오", pl=100),
    ]


def test_m2a_costs_daily_uses_today_window_rates_not_screen_range(db):
    _m2_setup(db)
    data = _ok(_client("src.routes.costs").get("/api/costs/daily?from=2026-10-07&to=2026-10-07"))
    (day,) = data["days"]
    assert day["cost_status"] == "estimated"
    assert day["fee"] == pytest.approx((99_900 + 100_000) * 0.003, abs=1e-6), day
    assert day["tax"] == pytest.approx(100_000 * 0.004, abs=1e-6), day


def test_m2b_costs_today_reports_window_rates(db):
    _m2_setup(db)
    data = _ok(_client("src.routes.costs").get("/api/costs/today"))
    assert data["rate_source"] == "measured"
    assert data["fee_rate"] == pytest.approx(0.003)
    assert data["tax_rate"] == pytest.approx(0.004)


def test_m2c_history_old_rows_estimated_with_today_window_rates(db):
    """화면 날짜 범위(08-01)에 표본이 없어도 요율은 오늘 기준 30일 창에서 온다."""
    old = date(2026, 8, 1)
    _m2_setup(db, d=old)
    db.history_trades = [_hist(t) for t in db.trades]
    rows = {t["id"]: t for t in _ok(_client("src.routes.history").get("/api/history"))["trades"]}
    assert rows[50]["cost_status"] == "estimated"
    assert rows[50]["fee"] == pytest.approx(100_000 * 0.003, abs=1e-6), rows[50]
    assert rows[50]["tax"] == pytest.approx(100_000 * 0.004, abs=1e-6), rows[50]
    assert rows[49]["fee"] == pytest.approx(99_900 * 0.003, abs=1e-6), rows[49]


def test_m2d_performance_daily_uses_today_window_rates(db):
    _m2_setup(db)
    for d in (D1, D2):
        db.perf.append({"date": d, "strategy": "total", "total_asset": 10_000_000,
                        "daily_realized_pnl": 100 if d == D2 else 0,
                        "daily_profit_rate": 0.001 if d == D2 else 0.0,
                        "cumulative_return_rate": 0.001 if d == D2 else 0.0,
                        "net_external_cashflow": 0, "deposit": 0})
    rows = _ok(_client("src.routes.performance").get("/api/performance/daily"))
    d2 = {r["date"]: r for r in rows}["2026-10-07"]
    assert d2["daily_fee"] == pytest.approx((99_900 + 100_000) * 0.003, abs=1e-6), d2


def test_m2e_pnl_pair_uses_today_window_rates(db):
    _m2_setup(db)
    db.pairs = [_pair(buy_date="2026-10-07", sell_date="2026-10-07", ticker="035720",
                      ticker_name="카카오", buy_price=9_990, buy_qty=10, sell_price=10_000,
                      sell_qty=10, profit_loss=100, profit_rate=0.1, strategy="momentum",
                      pair_key="momentum:035720:O49", buy_trade_ids=[49], sell_trade_ids=[50])]
    (p,) = _ok(_client("src.routes.history").get("/api/history/pnl"))["pairs"]
    assert p["fee"] == pytest.approx((99_900 + 100_000) * 0.003, abs=1e-6), p
    assert p["tax"] == pytest.approx(100_000 * 0.004, abs=1e-6), p


# ── M3: ETF 판정 = stock_master 구분 코드 ──────────────────────────────────────

def _m3_setup(db):
    db.trades = [
        _t(61, "momentum", "SELL", 10_000, 10, D2, ticker="138930", name="BNK금융지주"),
        _t(62, "etf_trend", "SELL", 10_000, 20, D2, ticker="999999", name="KIWOOM 200"),
    ]
    db.stock_raw = {"138930": {"scty_grp_id_cd": "ST"}, "999999": {"scty_grp_id_cd": "EF"}}


def test_m3a_history_sell_tax_follows_stock_master_group_code(db):
    _m3_setup(db)
    db.history_trades = [_hist(t) for t in db.trades]
    rows = {t["id"]: t for t in _ok(_client("src.routes.history").get("/api/history"))["trades"]}
    # 이름에 'BNK' 가 들어간 주식 — 매도세가 붙는다
    assert rows[61]["tax"] == pytest.approx(100_000 * 0.00199, abs=1e-6), rows[61]
    # 이름 키워드가 없는 개명 ETF — 매도세 0
    assert rows[62]["tax"] == pytest.approx(0, abs=1e-9), rows[62]


def test_m3b_costs_daily_tax_follows_stock_master_group_code(db):
    _m3_setup(db)
    data = _ok(_client("src.routes.costs").get("/api/costs/daily?from=2026-10-07&to=2026-10-07"))
    (day,) = data["days"]
    # 주식 10주(10만원)분만 매도세 — ETF 20주(20만원)는 0
    assert day["tax"] == pytest.approx(100_000 * 0.00199, abs=1e-6), day


# ── M4: 「모름」 ≠ 0 ────────────────────────────────────────────────────────────

def _closed_pair(**kw):
    base = dict(buy_date="2026-10-06", sell_date="2026-10-07", buy_price=100_000, buy_qty=5,
                sell_price=102_000, sell_qty=5, profit_loss=10_000, profit_rate=2.0,
                pair_key="volatility_breakout:000660:O1", buy_trade_ids=[1], sell_trade_ids=[3])
    base.update(kw)
    return _pair(**base)


def test_m4a_pnl_summary_cost_sums_are_none_when_costs_unavailable(db):
    db.trades = [_t(1, "volatility_breakout", "BUY", 100_000, 5, D1),
                 _t(3, "volatility_breakout", "SELL", 102_000, 5, D2, pl=10_000)]
    db.pairs = [_closed_pair()]
    db.fail_costs = True
    data = _ok(_client("src.routes.history").get("/api/history/pnl"))
    s = data["summary"]
    assert s["realized_total_krw"] == pytest.approx(10_000)  # 기존 칸 불변
    for k in ("realized_net_total_krw", "realized_net_rate_pct", "fee_sum", "tax_sum"):
        assert s[k] is None, (k, s)


def test_m4b_pair_slippage_is_none_without_any_order_price(db):
    db.trades = [_t(1, "volatility_breakout", "BUY", 100_000, 5, D1),
                 _t(3, "volatility_breakout", "SELL", 102_000, 5, D2, pl=10_000),
                 _t(4, "momentum", "BUY", 50_000, 2, D1, ticker="005930", name="삼성전자",
                    order_price=49_900),
                 _t(5, "momentum", "SELL", 51_000, 2, D2, ticker="005930", name="삼성전자",
                    pl=2_000)]
    db.pairs = [
        _closed_pair(),
        _closed_pair(ticker="005930", ticker_name="삼성전자", buy_price=50_000, buy_qty=2,
                     sell_price=51_000, sell_qty=2, profit_loss=2_000, strategy="momentum",
                     pair_key="momentum:005930:O4", buy_trade_ids=[4], sell_trade_ids=[5]),
    ]
    by = {p["pair_key"]: p for p in _ok(_client("src.routes.history").get("/api/history/pnl"))["pairs"]}
    assert by["volatility_breakout:000660:O1"]["slippage_won"] is None
    # 한 행이라도 덮이면 숫자(덮인 행만 합산)
    assert by["momentum:005930:O4"]["slippage_won"] == pytest.approx((50_000 - 49_900) * 2)


# ── M1: 잔고 buy_fee_paid ──────────────────────────────────────────────────────

def _balance_client(db, monkeypatch, holdings):
    from src.models.balance import AccountSummary

    summary = AccountSummary(deposit=0, stock_eval_amount=0, total_eval_amount=0, net_asset=0,
                             purchase_total=0, eval_total=0, profit_loss_total=0)
    bal = importlib.import_module("src.routes.balance")
    monkeypatch.setattr(bal, "get_balance", AsyncMock(return_value=(holdings, summary)))
    monkeypatch.setattr(bal, "stock_master_get", AsyncMock(return_value=None))
    monkeypatch.setattr(bal, "resolve_sector_name", AsyncMock(return_value="미분류"))
    return _client("src.routes.balance")


def test_m1_balance_holdings_carry_buy_fee_paid(db, monkeypatch):
    from src.engine import cost_overlay
    from src.models.balance import StockHolding

    db.trades = [_t(1, "kojiro", "BUY", 70_000, 10, D1, ticker="005930", name="삼성전자")]
    db.cost_rows = [_cost("005930", D1, buy_amt=700_000, fee=99)]
    db.pairs = [_pair(buy_date="2026-10-06", ticker="005930", ticker_name="삼성전자",
                      buy_price=70_000, buy_qty=10, profit_loss=20_000, profit_rate=2.86,
                      status="open", strategy="kojiro", pair_key="kojiro:005930:O1",
                      buy_trade_ids=[1], sell_trade_ids=[])]
    holdings = [
        StockHolding(ticker="005930", name="삼성전자", quantity=10, sellable_quantity=10,
                     avg_price=70_000, purchase_amount=700_000, current_price=72_000,
                     eval_amount=720_000, eval_profit_loss=20_000, eval_profit_rate=2.86),
        # 엔진 페어가 없는 보유(수동 매수 등) — 매입금액 × 추정 수수료율
        StockHolding(ticker="000660", name="SK하이닉스", quantity=5, sellable_quantity=5,
                     avg_price=100_000, purchase_amount=500_000, current_price=101_000,
                     eval_amount=505_000, eval_profit_loss=5_000, eval_profit_rate=1.0),
    ]
    data = _ok(_balance_client(db, monkeypatch, holdings).get("/api/balance"))
    by = {h["ticker"]: h for h in data["holdings"]}
    assert by["005930"]["eval_profit_loss"] == 20_000  # 기존 칸 불변
    assert by["005930"]["buy_fee_paid"] == pytest.approx(99, abs=1e-6), by["005930"]
    assert by["005930"]["buy_fee_status"] == "settled"
    fee_rate = cost_overlay.estimate_rates(db.cost_rows)["fee_rate"]
    assert by["000660"]["buy_fee_paid"] == pytest.approx(500_000 * fee_rate, abs=1e-6), by["000660"]
    assert by["000660"]["buy_fee_status"] == "estimated"


# ── L2: 분할 매도 뒤 보유 중 페어 ───────────────────────────────────────────────

def test_l2_open_pair_after_partial_sell_splits_buy_fee_and_keeps_total(db):
    """10주 매수(수수료 140) → 6주 매도(수수료 93·세금 1,300) → 4주 보유.

    보유 페어 `fee` = 매수 수수료 × 4/10 + 남은 4주 예상 매도수수료, `tax` = 남은 4주 예상 매도세.
    판 6주 몫 = `partial_fee`(매수 수수료 × 6/10 + 매도 수수료) · `partial_tax`(매도세).
    """
    from src.engine import cost_overlay

    db.trades = [_t(1, "kojiro", "BUY", 100_000, 10, D1),
                 _t(2, "kojiro", "SELL", 110_000, 6, D2, pl=60_000)]
    db.cost_rows = [_cost("000660", D1, buy_amt=1_000_000, fee=140),
                    _cost("000660", D2, sll_amt=660_000, fee=93, tl_tax=1300)]
    db.pairs = [_pair(buy_date="2026-10-06", sell_date=None, sell_time=None, buy_price=100_000,
                      buy_qty=4, profit_loss=40_000, profit_rate=10.0, status="open",
                      strategy="kojiro", pair_key="kojiro:000660:O1", buy_trade_ids=[1],
                      sell_trade_ids=[], partial_sell_trade_ids=[2])]
    (p,) = _ok(_client("src.routes.history").get("/api/history/pnl"))["pairs"]

    rates = cost_overlay.estimate_rates(db.cost_rows)
    remaining_sell_amt = 110_000 * 4  # 현재가(페어 안에서 역산) × 남은 수량
    est_fee = remaining_sell_amt * rates["fee_rate"]
    est_tax = remaining_sell_amt * rates["tax_rate"]
    assert p["fee"] == pytest.approx(140 * 0.4 + est_fee, abs=1e-6), p
    assert p["tax"] == pytest.approx(est_tax, abs=1e-6), p
    assert p["partial_fee"] == pytest.approx(140 * 0.6 + 93, abs=1e-6), p
    assert p["partial_tax"] == pytest.approx(1300, abs=1e-6), p
    # 총합 보존 — 낸 비용(정산) = 보유 몫 낸 수수료 + 판 몫
    paid = (p["fee"] - est_fee) + p["partial_fee"] + p["partial_tax"]
    assert paid == pytest.approx(140 + 93 + 1300, abs=1e-6)


def test_l2b_tax_unallocated_warning_marker_is_prefixed(db, caplog):
    """매도 체결이 없는데 정산 세금이 있는 날 — 세금을 매수 행에 몰지 않고 경고 1줄."""
    db.trades = [_t(1, "kojiro", "BUY", 100_000, 3, D2)]
    db.cost_rows = [_cost("000660", D2, buy_amt=300_000, fee=40, tl_tax=50)]
    db.history_trades = [_hist(t) for t in db.trades]
    with caplog.at_level(logging.DEBUG):
        (row,) = _ok(_client("src.routes.history").get("/api/history"))["trades"]
    assert row["fee"] == pytest.approx(40, abs=1e-6)
    assert row.get("tax") in (None, 0) or row["tax"] == pytest.approx(0)
    warns = [r for r in caplog.records
             if r.levelno >= logging.WARNING and r.getMessage().startswith("[cost_overlay_tax_unallocated] ")]
    assert len(warns) >= 1
