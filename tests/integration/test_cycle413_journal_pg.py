"""cycle413 Red — 거래일지 읽기·메모 DB 함수 + 라우트 왕복을 실 Postgres(047 표)로 검증한다.

계약 = `_workspace/red/cycle413/journal_view_contract.md` 2·3절 · 명세 = `_workspace/red/cycle413/journal_view_spec.md`.

| # | 계약 |
|---|---|
| P1 | `trade_history.get_trades_by_ids` — id 문자열 · 시각 KST ISO · `profit_loss` NULL 은 None(「모름 ≠ 0」) |
| P2 | `trade_journal.list_orders` — 주문번호 ∩ 날짜 범위 · `signal`/`params` dict · `order_date` date · `noted_at` KST ISO |
| P3 | `trade_journal.list_stops` — (전략, 종목) ∩ [since, until] · `observed_at` KST ISO · `inputs` dict |
| P4 | `trade_journal.get_record_start` — 날짜는 **KST** 로 자른다(UTC 날짜와 갈리는 행으로 검증) |
| P5 | 메모 upsert(같은 키 두 번 = 1행, body·updated_at 갱신) · list · delete |
| P6 | `stock_master_daily.get_closes_in_range`(종목·기간) · `list_business_days`(DISTINCT 오름차순) |
| P7 | 라우트 왕복 — 047 표에 합성 행 → `GET /api/history/journal` 카드 · `PUT …/notes/{id}` → GET 반영 → 공백 PUT = 행 삭제 · 없는 id 404 |

운영 DB 에는 실행하지 않는다 — 로컬 pg 하네스(docker) 또는 CI `DATABASE_URL_TEST` 만.
라우트는 `TestClient` 가 아니라 `httpx.ASGITransport` 로 같은 이벤트 루프에서 부른다(풀이 이 루프에 귀속 — cycle297 G5-3 관례).
"""

from __future__ import annotations

import importlib
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

KST = timezone(timedelta(hours=9))
_TABLES = ("trade_journal_notes", "trade_journal_stops", "trade_journal_orders", "trade_history",
           "stock_master_daily", "trade_cost_daily", "llm_buy_evaluations")
_BFB, _TK = "bull_flag_breakout", "247540"


@pytest.fixture
async def clean_journal(pg_pool):
    for t in _TABLES:
        await pg_pool.execute(f"DELETE FROM {t}")
    yield pg_pool
    for t in _TABLES:
        await pg_pool.execute(f"DELETE FROM {t}")


async def _trade(pool, *, ticker, name, strategy, side, price, qty, ts, order_no, order_price=None,
                 profit_loss="default", status="COMPLETED") -> str:
    if profit_loss == "default":
        row = await pool.fetchrow(
            "INSERT INTO trade_history (ticker, ticker_name, strategy, trade_type, price, quantity, status, "
            "order_no, order_price, timestamp) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id",
            ticker, name, strategy, side, price, qty, status, order_no, order_price, ts)
    else:
        row = await pool.fetchrow(
            "INSERT INTO trade_history (ticker, ticker_name, strategy, trade_type, price, quantity, status, "
            "order_no, order_price, timestamp, profit_loss) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id",
            ticker, name, strategy, side, price, qty, status, order_no, order_price, ts, profit_loss)
    return str(row["id"])


async def _order(pool, **r):
    await pool.execute(
        "INSERT INTO trade_journal_orders (order_date, order_no, side, strategy, ticker, source, reason_code, "
        "reason_sub, judge_price, order_price, order_division, exchange, parent_order_no, fired_line, "
        "effective_line, signal, params, noted_at) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NULL,$12,$13,$14,$15,$16,$17)",
        r["order_date"], r["order_no"], r["side"], r["strategy"], r["ticker"], r["source"], r.get("reason_code"),
        r.get("reason_sub"), r.get("judge_price"), r.get("order_price"), r.get("division"), r.get("parent"),
        r.get("fired"), r.get("eff"), r.get("signal"), r.get("params"), r["noted_at"])


async def _stop(pool, **r):
    await pool.execute(
        "INSERT INTO trade_journal_stops (strategy, ticker, buy_date, pos_order_no, observed_at, event, stop_price, "
        "stop_kind, target_price, target_hit, arm_price, inputs) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
        r["strategy"], r["ticker"], r.get("buy_date"), r.get("pos"), r["observed_at"], r["event"], r.get("price"),
        r.get("kind", "effective"), r.get("target"), r.get("hit"), r.get("arm"), r.get("inputs"))


async def _bar(pool, ticker, d, close, *, updated_at=None):
    await pool.execute(
        "INSERT INTO stock_master_daily (ticker, bas_dd, open_price, high_price, low_price, close_price, updated_at) "
        "VALUES ($1,$2,$3,$3,$3,$3,$4)",
        ticker, d, close, updated_at or datetime(2026, 10, 9, 7, 50, tzinfo=KST))


async def _seed(pool) -> dict:
    ids = {
        "buy": await _trade(pool, ticker=_TK, name="에코프로비엠", strategy=_BFB, side="BUY", price=12350, qty=40,
                            ts=datetime(2026, 10, 5, 9, 12, 3, tzinfo=KST), order_no="B1", order_price=12340),
        "sell": await _trade(pool, ticker=_TK, name="에코프로비엠", strategy=_BFB, side="SELL", price=13450, qty=40,
                             ts=datetime(2026, 10, 8, 14, 31, 20, tzinfo=KST), order_no="S1", order_price=13450,
                             profit_loss=44000),
        # KST 10-01 00:20 = UTC 09-30 — 주문가 기록 시작일을 KST 로 자르는지 가른다(다른 전략·당일 청산).
        "vb_buy": await _trade(pool, ticker="000660", name="SK하이닉스", strategy="volatility_breakout", side="BUY",
                               price=100, qty=1, ts=datetime(2026, 10, 1, 0, 20, tzinfo=KST), order_no="V1",
                               order_price=100),
        "vb_sell": await _trade(pool, ticker="000660", name="SK하이닉스", strategy="volatility_breakout",
                                side="SELL", price=101, qty=1, ts=datetime(2026, 10, 1, 9, 0, tzinfo=KST),
                                order_no="V2", profit_loss=1),
        # 실현손익 NULL 행(모름) — 0 으로 접히면 안 된다.
        "null_pl": await _trade(pool, ticker="035720", name="카카오", strategy="kojiro", side="SELL", price=50000,
                                qty=1, ts=datetime(2026, 10, 2, 10, 0, tzinfo=KST), order_no="K9",
                                profit_loss=None, status="CANCELLED"),
    }
    await _order(pool, order_date=date(2026, 10, 5), order_no="B1", side="BUY", strategy=_BFB, ticker=_TK,
                 source="log_harvest", reason_code="ENTRY", judge_price=12340, order_price=12340, division="01",
                 signal={"flag_high": 12300, "target_price": 13450, "atr": 410, "price": 12340,
                         "signal_src": "ring", "path": "accept"},
                 params={"atr_period": 20}, noted_at=datetime(2026, 10, 5, 9, 12, 3, tzinfo=KST))
    await _order(pool, order_date=date(2026, 10, 8), order_no="S1", side="SELL", strategy=_BFB, ticker=_TK,
                 source="log_harvest", reason_code="TAKE_PROFIT", judge_price=13460, division="01", eff=12350,
                 signal={"signal_name": "TAKE_PROFIT", "reason_line": None, "phrase": "bfb_measured_target",
                         "judge_src": "log_price", "current_price": 13460, "target": 13450, "snapshot_age_s": 8,
                         "stop_kind": "effective", "path": "accept"},
                 noted_at=datetime(2026, 10, 8, 14, 31, 20, tzinfo=KST))
    await _order(pool, order_date=date(2026, 9, 20), order_no="R9", side="BUY", strategy="momentum",
                 ticker="005930", source="log_restore", reason_code="ENTRY", judge_price=70000,
                 signal={"signal_src": "log_only", "path": "accept"},
                 noted_at=datetime(2026, 9, 20, 9, 1, tzinfo=KST))
    # KST 10-05 00:30 = UTC 10-04 — 손절선 기록 시작일도 KST 로 자른다.
    await _stop(pool, strategy="kojiro", ticker="035720", observed_at=datetime(2026, 10, 5, 0, 30, tzinfo=KST),
                event="first", price=45000)
    await _stop(pool, strategy=_BFB, ticker=_TK, buy_date=date(2026, 10, 5), pos="B1",
                observed_at=datetime(2026, 10, 5, 9, 12, 20, tzinfo=KST), event="first", price=11530,
                target=13450, hit=False,
                inputs={"buy_price": 12350, "quantity": 40, "high_since_buy": 12350, "entry_atr": 410})
    await _stop(pool, strategy=_BFB, ticker=_TK, buy_date=date(2026, 10, 5), pos="B1",
                observed_at=datetime(2026, 10, 8, 14, 31, 20, tzinfo=KST), event="exit", price=12350,
                target=13450, hit=True, inputs={"snapshot_age_s": 8, "sell_order_no": "S1"})
    for d, px in ((2, 11000), (5, 12450), (6, 12900), (7, 13120), (8, 13500)):
        await _bar(pool, _TK, date(2026, 10, d), px)
    await _bar(pool, "000660", date(2026, 10, 5), 100)
    return ids


def _mod(name):
    return importlib.import_module(name)


# ── P1~P6 DB 함수 ────────────────────────────────────────────────────────────

async def test_p1_trades_by_ids(clean_journal):
    ids = await _seed(clean_journal)
    rows = await _mod("src.db.trade_history").get_trades_by_ids([ids["buy"], ids["null_pl"], str(uuid.uuid4())])
    by = {r["id"]: r for r in rows}
    assert set(by) == {ids["buy"], ids["null_pl"]}
    b = by[ids["buy"]]
    assert b["timestamp"].startswith("2026-10-05T09:12:03") and b["timestamp"].endswith("+09:00")
    assert float(b["price"]) == 12350 and b["quantity"] == 40 and float(b["order_price"]) == 12340
    assert b["order_no"] == "B1" and b["trade_type"] == "BUY"
    assert by[ids["null_pl"]]["profit_loss"] is None


async def test_p2_list_orders(clean_journal):
    await _seed(clean_journal)
    jd = _mod("src.db.trade_journal")
    rows = await jd.list_orders(["B1", "S1", "R9"], date_from=date(2026, 10, 1), date_to=date(2026, 10, 9))
    assert sorted(r["order_no"] for r in rows) == ["B1", "S1"]
    b1 = next(r for r in rows if r["order_no"] == "B1")
    assert b1["order_date"] == date(2026, 10, 5)
    assert isinstance(b1["signal"], dict) and b1["signal"]["flag_high"] == 12300
    assert b1["params"] == {"atr_period": 20}
    assert b1["noted_at"].startswith("2026-10-05T09:12:03") and b1["noted_at"].endswith("+09:00")


async def test_p3_list_stops(clean_journal):
    await _seed(clean_journal)
    rows = await _mod("src.db.trade_journal").list_stops(
        [(_BFB, _TK)], since=datetime(2026, 10, 5, 9, 0, tzinfo=KST), until=datetime(2026, 10, 8, 9, 0, tzinfo=KST))
    assert [r["event"] for r in rows] == ["first"]
    r = rows[0]
    assert r["observed_at"].startswith("2026-10-05T09:12:20") and r["observed_at"].endswith("+09:00")
    assert r["inputs"]["high_since_buy"] == 12350 and r["stop_price"] == 11530 and r["target_hit"] is False


async def test_p4_record_start_cut_by_kst(clean_journal):
    await _seed(clean_journal)
    assert await _mod("src.db.trade_journal").get_record_start() == {
        "orders_restored": "2026-09-20", "orders_live": "2026-10-05", "stops": "2026-10-05",
        "order_price": "2026-10-01",
    }


async def test_p4_record_start_empty_tables_is_none(clean_journal):
    assert await _mod("src.db.trade_journal").get_record_start() == {
        "orders_restored": None, "orders_live": None, "stops": None, "order_price": None}


async def test_p5_note_upsert_list_delete(clean_journal):
    ids = await _seed(clean_journal)
    jd = _mod("src.db.trade_journal")
    a = await jd.upsert_note(ids["buy"], "첫 메모", strategy=_BFB, ticker=_TK, buy_date=date(2026, 10, 5))
    b = await jd.upsert_note(ids["buy"], "고친 메모", strategy=_BFB, ticker=_TK, buy_date=date(2026, 10, 5))
    assert a["anchor_trade_id"] == b["anchor_trade_id"] == ids["buy"]
    assert b["body"] == "고친 메모" and b["created_at"] == a["created_at"] and b["updated_at"] >= a["updated_at"]
    assert b["updated_at"].endswith("+09:00")
    n = await clean_journal.fetchval("SELECT count(*) FROM trade_journal_notes")
    assert n == 1
    row = await clean_journal.fetchrow("SELECT strategy, ticker, buy_date FROM trade_journal_notes")
    assert (row["strategy"], row["ticker"], row["buy_date"]) == (_BFB, _TK, date(2026, 10, 5))
    listed = await jd.list_notes([ids["buy"], str(uuid.uuid4())])
    assert [x["body"] for x in listed] == ["고친 메모"] and listed[0]["anchor_trade_id"] == ids["buy"]
    assert await jd.delete_note(ids["buy"]) is True
    assert await jd.delete_note(ids["buy"]) is False
    assert await jd.list_notes([ids["buy"]]) == []


async def test_p6_closes_and_business_days(clean_journal):
    await _seed(clean_journal)
    smd = _mod("src.db.stock_master_daily")
    rows = await smd.get_closes_in_range([_TK], date(2026, 10, 5), date(2026, 10, 8))
    assert sorted((r["bas_dd"], r["close_price"]) for r in rows) == [
        (date(2026, 10, 5), 12450), (date(2026, 10, 6), 12900), (date(2026, 10, 7), 13120),
        (date(2026, 10, 8), 13500)]
    assert all(r["ticker"] == _TK for r in rows)
    assert all(str(r["updated_at"]).endswith("+09:00") for r in rows)
    assert {"flng_cls_code", "prtt_rate"} <= set(rows[0])
    assert await smd.list_business_days(date(2026, 10, 1), date(2026, 10, 8)) == [
        date(2026, 10, d) for d in (2, 5, 6, 7, 8)]


# ── P7 라우트 왕복 ────────────────────────────────────────────────────────────

def _app():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(_mod("src.routes.history").router)
    return app


async def _call(method, path, **kw):
    import httpx

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test") as c:
        return await c.request(method, path, **kw)


async def test_p7_route_roundtrip_card_and_note(clean_journal):
    ids = await _seed(clean_journal)
    q = {"from": "2026-10-01", "to": "2026-10-09", "strategy": _BFB}
    r = await _call("GET", "/api/history/journal", params=q)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["record_start"]["stops"] == "2026-10-05"
    assert [c["anchor_trade_id"] for c in data["cards"]] == [ids["buy"]]
    c = data["cards"][0]
    assert c["status"] == "closed" and c["pnl"]["gross_krw"] == 44000
    assert c["entry"]["reason"]["text"] == "깃발 상단 12,300 돌파 · 측정 목표 13,450 · ATR 410"
    assert c["entry"]["initial_stop"]["price"] == 11530
    assert c["entry"]["orders"][0]["slip_order"]["per_share_won"] == 10
    assert c["exits"][0]["reason"]["text"] == "측정 목표 13,450 도달 — 전량 익절 (현재가 13,460)"
    assert [row["event"] for row in c["stop_track"]["rows"]] == ["first", "exit"]
    ex = c["excursion"]
    assert (ex["closes_k"], ex["closes_n"]) == (3, 3) and ex["mfe"]["date"] == "2026-10-07"
    assert c["costs"]["status"] == "estimated" and c["costs"]["entry_fee"] > 0
    assert c["note"] is None

    put = await _call("PUT", f"/api/history/journal/notes/{ids['buy']}", json={"body": "  계획대로 익절\n"})
    assert put.status_code == 200, put.text
    assert put.json()["data"]["body"] == "계획대로 익절"
    c2 = (await _call("GET", "/api/history/journal", params=q)).json()["data"]["cards"][0]
    assert c2["note"]["body"] == "계획대로 익절" and c2["note"]["updated_at"].endswith("+09:00")

    gone = await _call("PUT", f"/api/history/journal/notes/{ids['buy']}", json={"body": "   "})
    assert gone.status_code == 200 and gone.json()["data"] is None
    assert await clean_journal.fetchval("SELECT count(*) FROM trade_journal_notes") == 0

    assert (await _call("PUT", f"/api/history/journal/notes/{uuid.uuid4()}", json={"body": "x"})).status_code == 404
    assert (await _call("PUT", f"/api/history/journal/notes/{ids['sell']}", json={"body": "x"})).status_code == 404
