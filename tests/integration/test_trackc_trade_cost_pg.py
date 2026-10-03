"""트랙 C(실비용 산출) — 실 Postgres 왕복: 마이그레이션 045 + `src/db/trade_cost.py`.

명세 = `_workspace/design/2026-10-01_mean_reversion_handoff.md` §4.2-1

| # | 계약 |
|---|---|
| I1 | 045 를 두 번 실행해도 오류 0(가산형 · `IF NOT EXISTS`) |
| I2 | `upsert_daily` 왕복 — DATE·NUMERIC·JSONB 가 제 타입으로 돌아온다, 같은 키 재실행 = 덮어쓰기 |
| I3 | `upsert_period_total` 왕복 — 합계 숫자 칸 + raw JSONB |
| I4 | `get_completed_trades` — COMPLETED 만, 날짜는 **KST** 기준(00:30 KST 체결은 그날) |
| I5 | `get_buy_order_prices` — `llm_buy_evaluations` 의 주문가를 기간으로 읽는다 |

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

KST = timezone(timedelta(hours=9))
_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = _ROOT / "supabase" / "migrations" / "045_trade_cost_daily.sql"
D = date(2026, 9, 30)


@pytest.fixture
async def clean(pg_pool):
    async def _wipe():
        for t in ("trade_cost_daily", "trade_cost_period_totals", "trade_history",
                  "llm_buy_evaluations"):
            try:
                await pg_pool.execute(f"DELETE FROM {t}")
            except Exception:
                pass

    await _wipe()
    yield pg_pool
    await _wipe()


def _agg(pdno="035760", fee=27, tl_tax=270) -> dict:
    return {
        "trad_dt": D, "pdno": pdno, "prdt_name": "CJ ENM",
        "buy_qty": Decimal(0), "buy_amt": Decimal(0), "sll_qty": Decimal(5),
        "sll_amt": Decimal("180550"), "rlzt_pfls": Decimal("-16980"),
        "fee": Decimal(fee), "tl_tax": Decimal(tl_tax), "row_count": 1,
        "raw": [{"trad_dt": "20260930", "pdno": pdno, "fee": str(fee)}],
    }


async def test_i1_migration_045_applies_twice(clean):
    sql = _MIGRATION.read_text(encoding="utf-8")
    await clean.execute(sql)
    await clean.execute(sql)


async def test_i2_upsert_daily_roundtrip_and_overwrite(clean):
    from src.db import trade_cost

    n = await trade_cost.upsert_daily([_agg(), _agg(pdno="149950", fee=5, tl_tax=0)])
    assert n == 2
    rows = await trade_cost.get_daily_range(D, D)
    by = {r["pdno"]: r for r in rows}
    a = by["035760"]
    assert a["trad_dt"] == D and isinstance(a["trad_dt"], date)
    assert a["fee"] == Decimal(27) and a["tl_tax"] == Decimal(270)
    assert a["sll_amt"] == Decimal("180550")
    assert a["raw"] == [{"trad_dt": "20260930", "pdno": "035760", "fee": "27"}]
    assert isinstance(a["raw"], list)

    await trade_cost.upsert_daily([_agg(fee=30)])
    rows = await trade_cost.get_daily_range(D, D)
    assert {r["pdno"]: r["fee"] for r in rows}["035760"] == Decimal(30)
    assert len(rows) == 2

    assert await trade_cost.get_daily_range(date(2026, 10, 1), date(2026, 10, 2)) == []


async def test_i3_upsert_period_total_roundtrip(clean):
    from src.db import trade_cost

    summary = {"tot_fee": "57", "tot_tltx": "270", "buy_fee_smtl": "30", "sll_fee_smtl": "27",
               "sll_tltx_smtl": "270", "buy_tax_smtl": "0", "tot_rlzt_pfls": "-16980"}
    await trade_cost.upsert_period_total(date(2026, 9, 1), D, summary)
    await trade_cost.upsert_period_total(date(2026, 9, 1), D, dict(summary, tot_fee="58"))
    row = await clean.fetchrow(
        "SELECT * FROM trade_cost_period_totals WHERE from_dt=$1 AND to_dt=$2",
        date(2026, 9, 1), D,
    )
    assert row["tot_fee"] == Decimal(58)
    assert row["tot_tltx"] == Decimal(270)
    assert row["raw"]["tot_fee"] == "58"


async def _insert_trade(pg, ts, ticker, trade_type, price, qty, status, strategy, order_no,
                        profit_loss=0):
    await pg.execute(
        "INSERT INTO trade_history (timestamp, ticker, trade_type, price, quantity, profit_loss,"
        " status, strategy, order_no) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        ts, ticker, trade_type, Decimal(price), qty, Decimal(profit_loss), status, strategy,
        order_no,
    )


async def test_i4_completed_trades_kst_dates(clean):
    from src.db import trade_cost

    await _insert_trade(clean, datetime(2026, 9, 30, 0, 30, tzinfo=KST), "035760", "SELL",
                        36110, 5, "COMPLETED", "kojiro", "S1", -16450)
    await _insert_trade(clean, datetime(2026, 9, 30, 10, 0, tzinfo=KST), "035760", "BUY",
                        39400, 5, "CANCELLED", "kojiro", "B9")
    await _insert_trade(clean, datetime(2026, 10, 1, 0, 0, tzinfo=KST), "005930", "BUY",
                        70000, 1, "COMPLETED", "momentum", "B1")
    rows = await trade_cost.get_completed_trades(D, D)
    assert len(rows) == 1
    r = rows[0]
    assert r["trade_date"] == D
    assert r["ticker"] == "035760" and r["trade_type"] == "SELL"
    assert r["strategy"] == "kojiro" and r["order_no"] == "S1"
    assert r["price"] == Decimal(36110) and r["quantity"] == 5
    assert r["profit_loss"] == Decimal(-16450)


async def test_i5_buy_order_prices(clean):
    from src.db import trade_cost

    await clean.execute(
        "INSERT INTO llm_buy_evaluations (trade_date, account_no, ticker, order_no, eval_kind,"
        " account_product, strategy_id, mode, result, order_kst, order_price_won, ordered_qty,"
        " order_notional_won, order_division, min_score, order_path, board) VALUES"
        " ($1,'12345678','035760','B1','order','01','kojiro','shadow','ok',$2,39400,5,197000,"
        "'MARKET',70,'market','main')",
        D, datetime(2026, 9, 30, 9, 1, tzinfo=KST),
    )
    rows = await trade_cost.get_buy_order_prices(D, D)
    assert rows == [{"trade_date": D, "ticker": "035760", "order_no": "B1",
                     "order_price_won": 39400}]
