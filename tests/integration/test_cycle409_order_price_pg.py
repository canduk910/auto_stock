"""cycle409 — 사용자 결정 10-04 Q4: 실 Postgres 왕복 — migration 046 `trade_history.order_price`.

| # | 계약 |
|---|---|
| J1 | 046 을 두 번 실행해도 오류 0(가산형 · `IF NOT EXISTS`) · 칸은 NULL 허용 NUMERIC |
| J2 | PENDING BUY INSERT → 체결 UPDATE(`price`=체결가) 뒤에도 `order_price` 는 주문가 그대로 |
| J3 | 명시값 없는 PENDING SELL · COMPLETED(보정 INSERT) 는 `order_price` NULL |
| J4 | `trade_cost.get_completed_trades` 가 `order_price` 를 돌려준다(NULL 은 None) |
| J5 | 새 칸이 기존 읽기를 깨지 않는다 — `get_trade_pairs` 가 그대로 짝을 만든다 |
| J7 | 매도 PENDING → 체결 → `build_summary` 의 매도 슬리피지 `slippage_n > 0`(실 PG 왕복, 부호 = 주문가 − 체결가) |
| J6 | 매도 PENDING 에 명시한 `order_price` 는 기록되고 체결 UPDATE 뒤에도 남는다(8영역 승인 — `price` 는 매수가 장부 그대로) |

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.models.trade import TradeRecord, TradeStatus, TradeType

pytestmark = [pytest.mark.integration, pytest.mark.slow]

KST = timezone(timedelta(hours=9))
_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = _ROOT / "supabase" / "migrations" / "046_trade_history_order_price.sql"


@pytest.fixture
async def clean(pg_pool):
    await pg_pool.execute("DELETE FROM trade_history")
    yield pg_pool
    await pg_pool.execute("DELETE FROM trade_history")


def _rec(trade_type, status, price, order_no, qty=5):
    return TradeRecord(ticker="035760", ticker_name="CJ ENM", trade_type=trade_type,
                       price=price, quantity=qty, status=status, strategy="kojiro",
                       order_no=order_no)


async def test_j1_migration_applies_twice(clean):
    sql = _MIGRATION.read_text(encoding="utf-8")
    await clean.execute(sql)
    await clean.execute(sql)
    row = await clean.fetchrow(
        "SELECT data_type, is_nullable FROM information_schema.columns"
        " WHERE table_name='trade_history' AND column_name='order_price'"
    )
    assert row["data_type"] == "numeric" and row["is_nullable"] == "YES"


async def test_j2_fill_update_keeps_order_price(clean):
    from src.db import trade_history

    await trade_history.insert_trade(_rec(TradeType.BUY, TradeStatus.PENDING, 39400, "B1"))
    n = await trade_history.update_trade_status(
        "035760", TradeType.BUY, TradeStatus.COMPLETED, "kojiro", price=39450,
        order_no="B1", match_partial=True,
    )
    assert n == 1
    row = await clean.fetchrow("SELECT price, order_price FROM trade_history WHERE order_no='B1'")
    assert row["price"] == Decimal(39450)
    assert row["order_price"] == Decimal(39400)

    # 두 번째 체결 UPDATE 경로(order_no 단일 키 강제 UPDATE)도 주문가를 덮지 않는다
    await trade_history.insert_trade(_rec(TradeType.BUY, TradeStatus.PENDING, 20000, "B3"))
    n = await trade_history._update_trade_status_by_order_no(
        "B3", TradeType.BUY, TradeStatus.COMPLETED, price=20050,
    )
    assert n == 1
    row = await clean.fetchrow("SELECT price, order_price FROM trade_history WHERE order_no='B3'")
    assert row["price"] == Decimal(20050)
    assert row["order_price"] == Decimal(20000)


async def test_j3_pending_sell_and_completed_are_null(clean):
    from src.db import trade_history

    await trade_history.insert_trade(_rec(TradeType.SELL, TradeStatus.PENDING, 39400, "S1"))
    await trade_history.insert_trade(_rec(TradeType.BUY, TradeStatus.COMPLETED, 39450, "B2"))
    rows = await clean.fetch("SELECT order_no, order_price FROM trade_history ORDER BY order_no")
    assert {r["order_no"]: r["order_price"] for r in rows} == {"B2": None, "S1": None}


async def test_j4_completed_trades_returns_order_price(clean):
    from src.db import trade_cost, trade_history

    await trade_history.insert_trade(_rec(TradeType.BUY, TradeStatus.PENDING, 39400, "B1"))
    await trade_history.update_trade_status(
        "035760", TradeType.BUY, TradeStatus.COMPLETED, "kojiro", price=39450, order_no="B1",
    )
    await trade_history.insert_trade(_rec(TradeType.SELL, TradeStatus.COMPLETED, 36110, "S1"))
    today = datetime.now(KST).date()
    rows = await trade_cost.get_completed_trades(today, today)
    by = {r["order_no"]: r for r in rows}
    assert by["B1"]["order_price"] == Decimal(39400)
    assert by["B1"]["price"] == Decimal(39450)
    assert by["S1"]["order_price"] is None


async def test_j5_trade_pairs_still_pair(clean):
    from src.db import trade_history

    await trade_history.insert_trade(_rec(TradeType.BUY, TradeStatus.PENDING, 39400, "B1"))
    await trade_history.update_trade_status(
        "035760", TradeType.BUY, TradeStatus.COMPLETED, "kojiro", price=39450, order_no="B1",
    )
    await trade_history.insert_trade(_rec(TradeType.SELL, TradeStatus.COMPLETED, 36110, "S1"))
    pairs = await trade_history.get_trade_pairs(ticker="035760")
    assert len(pairs) == 1
    assert float(pairs[0]["buy_price"]) == pytest.approx(39450)


async def test_j6_explicit_sell_order_price_survives_fill(clean):
    from src.db import trade_history

    rec = TradeRecord(ticker="035760", ticker_name="CJ ENM", trade_type=TradeType.SELL,
                      price=39400, quantity=5, status=TradeStatus.PENDING, strategy="kojiro",
                      order_no="S9", order_price=36200)
    await trade_history.insert_trade(rec)
    n = await trade_history.update_trade_status(
        "035760", TradeType.SELL, TradeStatus.COMPLETED, "kojiro", price=36110,
        profit_loss=-16450, order_no="S9", match_partial=True,
    )
    assert n == 1
    row = await clean.fetchrow("SELECT price, order_price FROM trade_history WHERE order_no='S9'")
    assert row["price"] == Decimal(36110)
    assert row["order_price"] == Decimal(36200)


async def test_j7_sell_slippage_counts_end_to_end(clean):
    from src.db import trade_history
    from src.engine import trade_cost

    rec = TradeRecord(ticker="035760", ticker_name="CJ ENM", trade_type=TradeType.SELL,
                      price=39400, quantity=5, status=TradeStatus.PENDING, strategy="kojiro",
                      order_no="S7", order_price=36200)
    await trade_history.insert_trade(rec)
    await trade_history.update_trade_status(
        "035760", TradeType.SELL, TradeStatus.COMPLETED, "kojiro", price=36110,
        profit_loss=-16450, order_no="S7", match_partial=True,
    )
    today = datetime.now(KST).date()
    out = await trade_cost.build_summary(today, today)
    (k,) = out["strategies"]
    assert k["strategy"] == "kojiro"
    assert k["slippage_n"] == 1
    assert k["slippage_won"] == pytest.approx((36200 - 36110) * 5)
