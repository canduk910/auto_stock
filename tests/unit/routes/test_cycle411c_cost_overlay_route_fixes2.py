"""cycle411 2차 보완 Red — 2차 통합 검증이 찾은 라우트 결함 고정 (메인 세션 결정 10-08 「2차 보완 결정」).

계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「2차 보완 결정」 절.

| # | 계약 |
|---|---|
| B1 | 보유 중 페어인데 현재가를 모르면(`profit_loss=None` — 21:30 이후·재기동 직후·휴장일) `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp` = None. 이미 낸 `partial_fee`·`partial_tax` 는 유지 |
| B2 | `/api/performance/summary` net 두 칸은 비용 조회 실패 시 **None**(세전 값을 세후 칸에 담지 않는다). 개시 이래 재조회(`get_performance(days>30)`)만 실패해도 summary·daily 는 200 + net 칸 None |
| B4 | `/api/strategies/te` — 비용 조회 실패(None 반환·예외)면 `realized_net_sum_krw`·`fee_sum`·`tax_sum` = None, 그 전략 지표는 세전으로 그대로 계산. 실패 결과는 캐시하지 않는다(또는 60초 이하) |
| F1 | ETF 판정은 `stock_master.get_etf_group_codes(tickers)` 일괄 1회 — `stock_master.get` 직렬 호출 0 |
| F2 | 잔고 `buy_fee_paid` = open 페어 `buy_trade_ids` **전체 날짜**의 매수 수수료 |
| F3 | 잔고 비용 조회 실패 = `buy_fee_paid`·`buy_fee_status` None(0.0 아님) |
| F4 | `/api/history/pnl` 비용 조회 실패 = summary `slippage_n` None(0 아님) |
| F6 | `[cost_overlay_tax_unallocated] ` 경고는 (KST 오늘, trad_dt, pdno) 당 하루 1회 — 같은 요청 2회에 1줄 |
| F8 | 서버 오늘 기준 30일 요율은 하루 단위 메모리 캐시(같은 날 두 요청에 창 조회 1회) · 한 요청 안에서 같은 (start, end) 범위를 두 번 읽지 않는다 |
| F11 | 페어 `allocated` = 그 페어가 받은 정산 행이 **페어 밖** 체결에도 나뉘었을 때만 true(같은 날 사고 판 단일 페어는 false) |

DB 경계·시계는 `test_cycle411b_cost_overlay_route_fixes.py` 와 같다 — 시계 freezegun **2026-10-07 12:00 KST**.
DB 경계 호출은 `(start, end)` 를 기록해 F8 을 잰다.
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
WINDOW_START = D2 - timedelta(days=30)


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
        # 호출 기록 — F1·F8
        self.range_calls: list[tuple[date, date]] = []
        self.status_calls: list[tuple[date, date]] = []
        self.sm_get_calls: list[str] = []
        self.sm_codes_calls: list[list[str]] = []
        self.frozen = None

    def reset_calls(self):
        self.range_calls.clear()
        self.status_calls.clear()
        self.sm_get_calls.clear()
        self.sm_codes_calls.clear()


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
        st.range_calls.append((start, end))
        if st.fail_costs:
            raise RuntimeError("db down")
        return [r for r in st.cost_rows if start <= r["trad_dt"] <= end]

    async def get_trades_by_status(start, end, statuses=("COMPLETED", "PARTIAL")):
        st.status_calls.append((start, end))
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
        st.sm_get_calls.append(ticker)
        raw = st.stock_raw.get(ticker)
        return None if raw is None else StockBasics(ticker=ticker, raw=raw)

    async def sm_codes(tickers):
        st.sm_codes_calls.append(sorted(tickers))
        return {t: (st.stock_raw.get(t) or {}).get("scty_grp_id_cd") for t in tickers}

    sm = importlib.import_module("src.db.stock_master")
    monkeypatch.setattr(sm, "get_master_raw", AsyncMock(return_value=None))
    monkeypatch.setattr(sm, "get", sm_get)
    monkeypatch.setattr(sm, "get_etf_group_codes", sm_codes, raising=False)

    with freeze_time(FROZEN) as frozen:
        st.frozen = frozen
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


def _warns(caplog, prefix: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)]


# ── B1: 보유 중 페어의 현재가를 모르면 비용·순손익도 모른다 ─────────────────────

def test_b1_open_pair_without_current_price_has_unknown_cost(db):
    """10주 매수(수수료 140) → 6주 매도(수수료 93·세금 1,300) → 4주 보유, 현재가 모름(profit_loss=None).

    현재가가 없으면 예상 매도비용을 0 으로 치지 않는다 — fee·tax·순손익·순손익율·비용률 = None.
    판 몫(`partial_fee`·`partial_tax`)은 이미 낸 비용이라 그대로 나간다.
    """
    db.trades = [_t(1, "kojiro", "BUY", 100_000, 10, D1),
                 _t(2, "kojiro", "SELL", 110_000, 6, D2, pl=60_000)]
    db.cost_rows = [_cost("000660", D1, buy_amt=1_000_000, fee=140),
                    _cost("000660", D2, sll_amt=660_000, fee=93, tl_tax=1300)]
    db.pairs = [_pair(buy_date="2026-10-06", sell_date=None, sell_time=None, buy_price=100_000,
                      buy_qty=4, profit_loss=None, profit_rate=None, status="open",
                      strategy="kojiro", pair_key="kojiro:000660:O1", buy_trade_ids=[1],
                      sell_trade_ids=[], partial_sell_trade_ids=[2])]
    (p,) = _ok(_client("src.routes.history").get("/api/history/pnl"))["pairs"]
    assert p["profit_loss"] is None  # 기존 칸 불변
    for k in ("fee", "tax", "net_profit_loss", "net_profit_rate", "cost_bp"):
        assert p[k] is None, (k, p)
    assert p["partial_fee"] == pytest.approx(140 * 0.6 + 93, abs=1e-6), p
    assert p["partial_tax"] == pytest.approx(1300, abs=1e-6), p


# ── B2: summary net 칸 — 실패 = None ────────────────────────────────────────────

def _perf4() -> list[dict]:
    base = date(2026, 10, 2)
    out = []
    for i, (asset, pnl, dr, cum) in enumerate([
        (10_000_000, 0, 0.0, 0.0),
        (10_000_000, 0, 0.0, 0.0),
        (10_030_000, 30_000, 0.3, 0.3),
        (10_033_000, 3_000, 3_000 / 10_030_000 * 100, (1.003 * (1 + 3_000 / 10_030_000) - 1) * 100),
    ]):
        out.append({"date": base + timedelta(days=i), "strategy": "total", "total_asset": asset,
                    "daily_realized_pnl": pnl, "daily_profit_rate": dr,
                    "cumulative_return_rate": cum, "net_external_cashflow": 0, "deposit": 0})
    return out


def test_b2a_summary_net_is_none_when_costs_unavailable(db, caplog):
    db.perf = _perf4()
    db.fail_costs = True
    with caplog.at_level(logging.DEBUG):
        data = _ok(_client("src.routes.performance").get("/api/performance/summary"))
    # 기존 칸 불변
    assert data["total_profit_rate"] == round(db.perf[-1]["cumulative_return_rate"], 2)
    assert data["avg_daily_profit_rate"] == round(
        sum(r["daily_profit_rate"] for r in db.perf) / len(db.perf), 2)
    # 「세후」 칸에 세전 값을 담지 않는다
    assert data["net_total_profit_rate"] is None, data
    assert data["net_avg_daily_profit_rate"] is None, data
    assert _warns(caplog, "[cost_overlay_unavailable]"), [r.getMessage() for r in caplog.records]


def _fail_long_reads(monkeypatch, db):
    """창(30일) 조회는 성공, 개시 이래 재조회(days>30)만 실패."""
    perf_route = importlib.import_module("src.routes.performance")
    dp = importlib.import_module("src.db.daily_performance")
    orig = perf_route.get_performance

    async def flaky(days=30, strategy="total"):
        if days > 30:
            raise RuntimeError("since-inception read down")
        return await orig(days=days, strategy=strategy)

    monkeypatch.setattr(perf_route, "get_performance", flaky)
    monkeypatch.setattr(dp, "get_performance", flaky)


def test_b2b_summary_200_with_net_none_when_since_inception_read_fails(db, monkeypatch, caplog):
    db.perf = _perf4()
    _fail_long_reads(monkeypatch, db)
    with caplog.at_level(logging.DEBUG):
        data = _ok(_client("src.routes.performance").get("/api/performance/summary"))
    assert data["total_profit_rate"] == round(db.perf[-1]["cumulative_return_rate"], 2)
    assert data["net_total_profit_rate"] is None, data
    assert data["net_avg_daily_profit_rate"] is None, data
    assert _warns(caplog, "[cost_overlay_unavailable]")


def test_b2c_daily_200_with_net_none_when_since_inception_read_fails(db, monkeypatch):
    db.perf = _perf4()
    _fail_long_reads(monkeypatch, db)
    rows = _ok(_client("src.routes.performance").get("/api/performance/daily"))
    assert len(rows) == 4
    assert {r["date"]: r for r in rows}["2026-10-04"]["daily_profit_rate"] == pytest.approx(0.3)
    for r in rows:
        for k in ("daily_fee", "daily_tax", "daily_net_pnl", "net_daily_profit_rate",
                  "net_cumulative_return_rate", "cost_status"):
            assert r[k] is None, (k, r)


# ── B4: /api/strategies/te — 비용 모름 = net 전용 칸 None ───────────────────────

def _te_setup(db, monkeypatch):
    """momentum 20왕복(세전 +700원/건) — 추정 비용을 빼면 건마다 손실이다."""
    strat_route = importlib.import_module("src.routes.strategies")
    trades, pairs = [], []
    for i in range(20):
        b, s = 1000 + 2 * i, 1001 + 2 * i
        tk = f"{100000 + i}"
        trades += [_t(b, "momentum", "BUY", 70_000, 10, D1, ticker=tk, name="가나"),
                   _t(s, "momentum", "SELL", 70_070, 10, D2, ticker=tk, name="가나", pl=700)]
        pairs.append(_pair(buy_date=D1.isoformat(), sell_date=D2.isoformat(), ticker=tk,
                           ticker_name="가나", buy_price=70_000, buy_qty=10, sell_price=70_070,
                           sell_qty=10, profit_loss=700, profit_rate=0.1, strategy="momentum",
                           pair_key=f"momentum:{tk}:O{b}", buy_trade_ids=[b], sell_trade_ids=[s]))
    db.trades, db.cost_rows = trades, []

    async def get_trade_pairs(strategy=None, ticker=None):
        return [dict(p) for p in pairs] if strategy == "momentum" else []

    monkeypatch.setattr(strat_route, "get_trade_pairs", get_trade_pairs)
    strat_route.invalidate_te_cache()
    return strat_route


def _te_momentum(client) -> dict:
    rows = _ok(client.get("/api/strategies/te?months=3"))
    return {r["strategy_id"]: r for r in rows}["momentum"]


def test_b4a_te_net_only_fields_none_when_costs_unavailable(db, monkeypatch):
    strat_route = _te_setup(db, monkeypatch)
    db.fail_costs = True
    try:
        m = _te_momentum(_client("src.routes.strategies"))
    finally:
        strat_route.invalidate_te_cache()
    assert m["n"] == 20
    assert m["realized_sum_krw"] == pytest.approx(14_000)  # 세전 그대로
    for k in ("realized_net_sum_krw", "fee_sum", "tax_sum"):
        assert m[k] is None, (k, m)
    # 판정은 세전 값으로 계산된다(세후를 모르므로) — 세전 칸과 같다
    assert m["te_pct"] == pytest.approx(m["te_pct_gross"])


def test_b4b_failed_te_result_is_not_cached(db, monkeypatch):
    """실패 결과를 5분 캐시에 남기지 않는다 — 61초 뒤 비용 조회가 살아나면 세후 값이 나온다."""
    strat_route = _te_setup(db, monkeypatch)
    client = _client("src.routes.strategies")
    try:
        db.fail_costs = True
        _te_momentum(client)
        db.fail_costs = False
        db.frozen.tick(61)
        m = _te_momentum(client)
    finally:
        strat_route.invalidate_te_cache()
    assert m["realized_net_sum_krw"] is not None, m
    assert m["realized_net_sum_krw"] < 0, m
    assert m["fee_sum"] > 0 and m["tax_sum"] > 0, m


def test_b4c_overlay_exception_keeps_strategy_metrics(db, monkeypatch):
    """`overlay_pairs` 가 코드 결함으로 예외를 올려도 그 전략 지표가 통째로 비지 않는다."""
    strat_route = _te_setup(db, monkeypatch)
    co = importlib.import_module("src.engine.cost_overlay")

    async def boom(pairs):
        raise RuntimeError("overlay bug")

    monkeypatch.setattr(co, "overlay_pairs", boom)
    try:
        m = _te_momentum(_client("src.routes.strategies"))
    finally:
        strat_route.invalidate_te_cache()
    assert m["n"] == 20, m
    assert m["realized_sum_krw"] == pytest.approx(14_000)
    assert m["realized_net_sum_krw"] is None, m


# ── F1: stock_master 일괄 조회 ──────────────────────────────────────────────────

def test_f1_history_reads_stock_master_in_one_batch(db):
    db.trades = [
        _t(61, "momentum", "SELL", 10_000, 10, D2, ticker="138930", name="BNK금융지주"),
        _t(62, "etf_trend", "SELL", 10_000, 20, D2, ticker="999999", name="KIWOOM 200"),
        _t(63, "momentum", "SELL", 10_000, 5, D2, ticker="035720", name="카카오"),
        _t(64, "momentum", "BUY", 10_000, 5, D2, ticker="035720", name="카카오"),
    ]
    db.stock_raw = {"138930": {"scty_grp_id_cd": "ST"}, "999999": {"scty_grp_id_cd": "EF"}}
    db.history_trades = [_hist(t) for t in db.trades]
    rows = {t["id"]: t for t in _ok(_client("src.routes.history").get("/api/history"))["trades"]}
    # 판정 결과는 M3 그대로
    assert rows[61]["tax"] == pytest.approx(100_000 * 0.00199, abs=1e-6), rows[61]
    assert rows[62]["tax"] == pytest.approx(0, abs=1e-9), rows[62]
    # 종목마다 `SELECT *` 단건 조회를 하지 않는다 — 일괄 1회
    assert db.sm_get_calls == [], db.sm_get_calls
    assert db.sm_codes_calls == [["035720", "138930", "999999"]], db.sm_codes_calls


def test_f1b_pnl_reads_stock_master_in_one_batch(db):
    db.trades = [_t(1, "momentum", "BUY", 10_000, 10, D1, ticker="138930", name="BNK금융지주"),
                 _t(2, "momentum", "SELL", 10_100, 10, D2, ticker="138930", name="BNK금융지주",
                    pl=1_000),
                 _t(3, "etf_trend", "BUY", 10_000, 10, D1, ticker="999999", name="KIWOOM 200")]
    db.stock_raw = {"138930": {"scty_grp_id_cd": "ST"}, "999999": {"scty_grp_id_cd": "EF"}}
    db.pairs = [
        _pair(buy_date="2026-10-06", sell_date="2026-10-07", ticker="138930",
              ticker_name="BNK금융지주", buy_price=10_000, buy_qty=10, sell_price=10_100,
              sell_qty=10, profit_loss=1_000, profit_rate=1.0, strategy="momentum",
              pair_key="momentum:138930:O1", buy_trade_ids=[1], sell_trade_ids=[2]),
        _pair(buy_date="2026-10-06", ticker="999999", ticker_name="KIWOOM 200",
              buy_price=10_000, buy_qty=10, profit_loss=500, profit_rate=0.5, status="open",
              strategy="etf_trend", pair_key="etf_trend:999999:O3", buy_trade_ids=[3]),
    ]
    _ok(_client("src.routes.history").get("/api/history/pnl"))
    assert db.sm_get_calls == [], db.sm_get_calls
    assert len(db.sm_codes_calls) == 1, db.sm_codes_calls


# ── F2·F3: 잔고 매수 수수료 ─────────────────────────────────────────────────────

def _balance_client(monkeypatch, holdings):
    from src.models.balance import AccountSummary

    summary = AccountSummary(deposit=0, stock_eval_amount=0, total_eval_amount=0, net_asset=0,
                             purchase_total=0, eval_total=0, profit_loss_total=0)
    bal = importlib.import_module("src.routes.balance")
    monkeypatch.setattr(bal, "get_balance", AsyncMock(return_value=(holdings, summary)))
    monkeypatch.setattr(bal, "stock_master_get", AsyncMock(return_value=None))
    monkeypatch.setattr(bal, "resolve_sector_name", AsyncMock(return_value="미분류"))
    return _client("src.routes.balance")


def _holding(ticker, name, qty, avg, cur):
    from src.models.balance import StockHolding

    return StockHolding(ticker=ticker, name=name, quantity=qty, sellable_quantity=qty,
                        avg_price=avg, purchase_amount=int(avg * qty), current_price=cur,
                        eval_amount=cur * qty, eval_profit_loss=int((cur - avg) * qty),
                        eval_profit_rate=round((cur - avg) / avg * 100, 2))


def _f2_setup(db):
    """005930 — 10-06 3주 + 10-07 2주 매수(두 날 정산 수수료 30·25), 5주 보유."""
    db.trades = [_t(1, "kojiro", "BUY", 70_000, 3, D1, ticker="005930", name="삼성전자"),
                 _t(2, "kojiro", "BUY", 71_000, 2, D2, ticker="005930", name="삼성전자")]
    db.cost_rows = [_cost("005930", D1, buy_amt=210_000, fee=30),
                    _cost("005930", D2, buy_amt=142_000, fee=25)]
    db.pairs = [_pair(buy_date="2026-10-06", ticker="005930", ticker_name="삼성전자",
                      buy_price=70_400, buy_qty=5, profit_loss=8_000, profit_rate=2.27,
                      status="open", strategy="kojiro", pair_key="kojiro:005930:O1",
                      buy_trade_ids=[1, 2], sell_trade_ids=[])]
    return [_holding("005930", "삼성전자", 5, 70_400, 72_000)]


def test_f2_balance_buy_fee_paid_spans_all_buy_dates(db, monkeypatch):
    holdings = _f2_setup(db)
    data = _ok(_balance_client(monkeypatch, holdings).get("/api/balance"))
    (h,) = data["holdings"]
    assert h["buy_fee_paid"] == pytest.approx(30 + 25, abs=1e-6), h
    assert h["buy_fee_status"] == "settled", h


def test_f3_balance_buy_fee_paid_none_when_costs_unavailable(db, monkeypatch):
    holdings = _f2_setup(db)
    db.fail_costs = True
    data = _ok(_balance_client(monkeypatch, holdings).get("/api/balance"))
    (h,) = data["holdings"]
    assert h["eval_profit_loss"] == 8_000  # 기존 칸 불변
    assert h["sell_cost_rate"] is not None  # 요율은 기본값 fail-open(기존 계약)
    assert h["buy_fee_paid"] is None, h  # 「모름」 ≠ 0
    assert h["buy_fee_status"] is None, h


# ── F4: slippage_n 「모름」 ─────────────────────────────────────────────────────

def test_f4_pnl_summary_slippage_n_none_when_costs_unavailable(db):
    db.trades = [_t(1, "volatility_breakout", "BUY", 100_000, 5, D1, order_price=99_900),
                 _t(3, "volatility_breakout", "SELL", 102_000, 5, D2, pl=10_000)]
    db.pairs = [_pair(buy_date="2026-10-06", sell_date="2026-10-07", buy_price=100_000, buy_qty=5,
                      sell_price=102_000, sell_qty=5, profit_loss=10_000, profit_rate=2.0,
                      pair_key="volatility_breakout:000660:O1", buy_trade_ids=[1],
                      sell_trade_ids=[3])]
    db.fail_costs = True
    s = _ok(_client("src.routes.history").get("/api/history/pnl"))["summary"]
    assert s["closed_count"] == 1  # 기존 칸 불변
    assert s["slippage_n"] is None, s


# ── F6: 경고 하루 1회 ───────────────────────────────────────────────────────────

def test_f6_tax_unallocated_warning_once_for_two_identical_requests(db, caplog):
    db.trades = [_t(1, "kojiro", "BUY", 100_000, 3, D2)]
    db.cost_rows = [_cost("000660", D2, buy_amt=300_000, fee=40, tl_tax=50)]
    db.history_trades = [_hist(t) for t in db.trades]
    c = _client("src.routes.history")
    with caplog.at_level(logging.DEBUG):
        _ok(c.get("/api/history"))
        _ok(c.get("/api/history"))
    warns = _warns(caplog, "[cost_overlay_tax_unallocated] ")
    assert len(warns) == 1, [r.getMessage() for r in warns]


# ── F8: 요율 하루 캐시 · 같은 범위 재조회 없음 ─────────────────────────────────

def test_f8a_window_rates_read_once_per_day_across_requests(db):
    db.cost_rows = [_cost("111111", date(2026, 9, 20), buy_amt=1_000_000, sll_amt=1_000_000,
                          fee=6_000, tl_tax=4_000)]
    db.trades = [_t(41, "momentum", "SELL", 10_000, 10, D2, ticker="035720", name="카카오", pl=100)]
    c = _client("src.routes.costs")
    first = _ok(c.get("/api/costs/today"))
    second = _ok(c.get("/api/costs/today"))
    assert first["fee_rate"] == pytest.approx(0.003) and second["fee_rate"] == pytest.approx(0.003)
    window_reads = [r for r in db.range_calls if r == (WINDOW_START, D2)]
    assert len(window_reads) == 1, db.range_calls


def test_f8b_balance_does_not_read_same_range_twice_in_one_request(db, monkeypatch):
    """보유 3종목이 같은 날 샀다 — 한 요청 안에서 같은 (start, end) 를 두 번 읽지 않는다."""
    tickers = [("005930", "삼성전자"), ("000660", "SK하이닉스"), ("035720", "카카오")]
    holdings = []
    for i, (tk, nm) in enumerate(tickers, start=1):
        db.trades.append(_t(i, "kojiro", "BUY", 10_000, 10, D1, ticker=tk, name=nm))
        db.cost_rows.append(_cost(tk, D1, buy_amt=100_000, fee=14))
        db.pairs.append(_pair(buy_date="2026-10-06", ticker=tk, ticker_name=nm, buy_price=10_000,
                              buy_qty=10, profit_loss=1_000, profit_rate=1.0, status="open",
                              strategy="kojiro", pair_key=f"kojiro:{tk}:O{i}", buy_trade_ids=[i]))
        holdings.append(_holding(tk, nm, 10, 10_000, 10_100))
    data = _ok(_balance_client(monkeypatch, holdings).get("/api/balance"))
    assert {h["ticker"]: h["buy_fee_paid"] for h in data["holdings"]} == pytest.approx(
        {tk: 14.0 for tk, _ in tickers})
    assert len(db.range_calls) == len(set(db.range_calls)), db.range_calls
    assert len(db.status_calls) == len(set(db.status_calls)), db.status_calls


# ── F11: 배분 배지 = 페어 밖 체결과 나눴을 때만 ─────────────────────────────────

def test_f11a_same_day_round_trip_single_pair_is_not_allocated(db):
    db.trades = [_t(1, "momentum", "BUY", 70_000, 10, D2, ticker="005930", name="삼성전자"),
                 _t(2, "momentum", "SELL", 72_000, 10, D2, ticker="005930", name="삼성전자",
                    pl=20_000)]
    db.cost_rows = [_cost("005930", D2, buy_amt=700_000, sll_amt=720_000, fee=201, tl_tax=1433)]
    db.pairs = [_pair(buy_date="2026-10-07", sell_date="2026-10-07", ticker="005930",
                      ticker_name="삼성전자", buy_price=70_000, buy_qty=10, sell_price=72_000,
                      sell_qty=10, profit_loss=20_000, profit_rate=2.86, strategy="momentum",
                      pair_key="momentum:005930:O1", buy_trade_ids=[1], sell_trade_ids=[2])]
    (p,) = _ok(_client("src.routes.history").get("/api/history/pnl"))["pairs"]
    assert p["fee"] == pytest.approx(201, abs=1e-6) and p["tax"] == pytest.approx(1433, abs=1e-6)
    assert p["cost_status"] == "settled"
    assert p["allocated"] is False, p


def test_f11b_pair_sharing_settlement_with_another_pair_stays_allocated(db):
    """가드 — 같은 날·종목 정산 1행이 다른 전략 체결에도 나뉘면 배분(true) 그대로."""
    db.trades = [_t(1, "volatility_breakout", "BUY", 100_000, 5, D2),
                 _t(2, "kojiro", "BUY", 100_000, 3, D2),
                 _t(3, "volatility_breakout", "SELL", 102_000, 5, D2, pl=10_000)]
    db.cost_rows = [_cost("000660", D2, buy_amt=800_000, sll_amt=510_000, fee=183, tl_tax=1015)]
    db.pairs = [
        _pair(buy_date="2026-10-07", sell_date="2026-10-07", buy_price=100_000, buy_qty=5,
              sell_price=102_000, sell_qty=5, profit_loss=10_000, profit_rate=2.0,
              pair_key="volatility_breakout:000660:O1", buy_trade_ids=[1], sell_trade_ids=[3]),
        _pair(buy_date="2026-10-07", buy_price=100_000, buy_qty=3, profit_loss=600,
              profit_rate=0.2, status="open", strategy="kojiro", pair_key="kojiro:000660:O2",
              buy_trade_ids=[2]),
    ]
    by = {p["pair_key"]: p for p in _ok(_client("src.routes.history").get("/api/history/pnl"))["pairs"]}
    assert by["volatility_breakout:000660:O1"]["allocated"] is True
