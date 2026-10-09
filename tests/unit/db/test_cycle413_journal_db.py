"""cycle413 Red — 거래일지 읽기·메모 DB 함수의 경계 성질 (pg 는 가짜, 실 SQL 은 통합 테스트).

계약 = `_workspace/red/cycle413/journal_view_contract.md` 2절. 실 Postgres 왕복 = `tests/integration/test_cycle413_journal_pg.py`.

| # | 계약 |
|---|---|
| D1 | 빈 목록 인자 = **쿼리 없이** `[]` (빈 배치가 전체 스캔으로 번지지 않게) |
| D2 | 예외를 삼키지 않는다 — 라우트가 「조회 실패」와 「행 없음」을 가른다(빈 목록으로 접으면 `lookup_failed` 가 `unknown` 으로 둔갑) |
| D3 | `get_trades_by_ids` — `profit_loss` NULL 은 None 그대로(「모름 ≠ 0」 · `get_trades_by_status` 의 COALESCE 와 다르다) |
"""

from __future__ import annotations

import importlib
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
D0, D1 = date(2026, 10, 1), date(2026, 10, 9)
T0, T1 = datetime(2026, 10, 1, tzinfo=KST), datetime(2026, 10, 9, 23, 59, tzinfo=KST)


@pytest.fixture
def pg(monkeypatch):
    mod = importlib.import_module("src.db.pg")
    mocks = {n: AsyncMock(return_value=[] if n == "fetch" else None) for n in ("fetch", "fetchrow", "fetchval")}
    mocks["execute"] = AsyncMock(return_value="DELETE 0")
    for n, m in mocks.items():
        monkeypatch.setattr(mod, n, m)
    return mocks


def _calls(pg) -> int:
    return sum(m.await_count for m in pg.values())


_EMPTY_CASES = [
    ("src.db.trade_journal", "list_orders", ([],), {"date_from": D0, "date_to": D1}),
    ("src.db.trade_journal", "list_stops", ([],), {"since": T0, "until": T1}),
    ("src.db.trade_journal", "list_notes", ([],), {}),
    ("src.db.trade_history", "get_trades_by_ids", ([],), {}),
    ("src.db.stock_master_daily", "get_closes_in_range", ([], D0, D1), {}),
]


@pytest.mark.parametrize("mod,name,args,kw", _EMPTY_CASES, ids=[c[1] for c in _EMPTY_CASES])
async def test_d1_empty_input_returns_empty_without_query(pg, mod, name, args, kw):
    fn = getattr(importlib.import_module(mod), name)
    assert await fn(*args, **kw) == []
    assert _calls(pg) == 0


_RAISE_CASES = [
    ("src.db.trade_journal", "list_orders", (["B1"],), {"date_from": D0, "date_to": D1}),
    ("src.db.trade_journal", "list_stops", ([("kojiro", "005930")],), {"since": T0, "until": T1}),
    ("src.db.trade_journal", "list_notes", ([str(uuid.uuid4())],), {}),
    ("src.db.trade_journal", "get_record_start", (), {}),
    ("src.db.trade_history", "get_trades_by_ids", ([str(uuid.uuid4())],), {}),
    ("src.db.stock_master_daily", "get_closes_in_range", (["005930"], D0, D1), {}),
    ("src.db.stock_master_daily", "list_business_days", (D0, D1), {}),
]


@pytest.mark.parametrize("mod,name,args,kw", _RAISE_CASES, ids=[c[1] for c in _RAISE_CASES])
async def test_d2_db_errors_propagate(pg, mod, name, args, kw):
    boom = RuntimeError("db down")
    for m in pg.values():
        m.side_effect = boom
    fn = getattr(importlib.import_module(mod), name)
    with pytest.raises(Exception):
        await fn(*args, **kw)


async def test_d3_trades_by_ids_keeps_null_profit_loss(pg):
    tid = uuid.uuid4()
    pg["fetch"].return_value = [{
        "id": tid, "order_no": "S1", "trade_type": "SELL", "timestamp": "2026-10-08T14:31:20.000000+09:00",
        "price": Decimal("13450"), "quantity": 40, "order_price": None, "profit_loss": None,
        "strategy": "bull_flag_breakout", "ticker": "247540", "status": "COMPLETED",
    }]
    rows = await importlib.import_module("src.db.trade_history").get_trades_by_ids([str(tid)])
    assert len(rows) == 1
    r = rows[0]
    assert str(r["id"]) == str(tid)   # 문자열 보장은 실 DB 왕복(통합 P1)이 잰다 — SQL 캐스트든 파이썬 변환이든 무관
    assert r["profit_loss"] is None, "NULL 실현손익을 0 으로 접지 않는다(「모름 ≠ 0」)"
    assert r["order_price"] is None
    sql = pg["fetch"].await_args.args[0]
    assert "coalesce(profit_loss" not in sql.lower().replace(" ", "").replace("t.", "")

