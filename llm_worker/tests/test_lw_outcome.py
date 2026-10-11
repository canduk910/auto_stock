"""cycle446 — 사후 채움(`lw/outcome.py`, 설계 §5.3). 가짜 DB 로 검증(실 Postgres 왕복은
C1 통합 테스트가 맡는다)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from lw import outcome

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


class _FakeDB:
    def __init__(self):
        self.missing_next_open = []
        self.open_prices = {}
        self.filled_next_open = []
        self.open_evaluations = []
        self.sell_trades = {}
        self.journal_rows = {}
        self.filled_outcomes = []
        self.raise_on_list_missing = False

    async def list_open_missing_next_open(self, *, before):
        if self.raise_on_list_missing:
            raise RuntimeError("boom")
        return self.missing_next_open

    async def fetch_open_price(self, ticker, bas_dd):
        return self.open_prices.get((ticker, bas_dd))

    async def fill_next_open(self, eval_id, open_price, now):
        self.filled_next_open.append((eval_id, open_price))

    async def list_open_evaluations(self):
        return self.open_evaluations

    async def fetch_sell_trades(self, strategy_id, ticker, since):
        return self.sell_trades.get((strategy_id, ticker), [])

    async def fetch_journal_order(self, order_date, order_no, side):
        return self.journal_rows.get((order_date, order_no, side))

    async def fill_outcome(self, eval_id, **kw):
        self.filled_outcomes.append({"id": eval_id, **kw})


@pytest.mark.asyncio
async def test_fill_next_open_fills_when_price_available():
    db = _FakeDB()
    db.missing_next_open = [{"id": 1, "ticker": "005930", "act_date": date(2026, 10, 13)}]
    db.open_prices[("005930", date(2026, 10, 13))] = 70000
    n = await outcome.fill_next_open(db, today=date(2026, 10, 14))
    assert n == 1
    assert db.filled_next_open == [(1, 70000)]


@pytest.mark.asyncio
async def test_fill_next_open_skips_when_price_missing():
    db = _FakeDB()
    db.missing_next_open = [{"id": 1, "ticker": "005930", "act_date": date(2026, 10, 13)}]
    n = await outcome.fill_next_open(db, today=date(2026, 10, 14))
    assert n == 0
    assert db.filled_next_open == []


@pytest.mark.asyncio
async def test_fill_next_open_list_error_is_absorbed():
    db = _FakeDB()
    db.raise_on_list_missing = True
    n = await outcome.fill_next_open(db, today=date(2026, 10, 14))
    assert n == 0


@pytest.mark.asyncio
async def test_fill_outcomes_skips_still_held_positions():
    db = _FakeDB()
    row = {"id": 1, "strategy_id": "kojiro", "ticker": "005930", "buy_date": date(2026, 10, 10),
          "buy_order_no": "1", "quantity": 10, "act_date": date(2026, 10, 13)}
    db.open_evaluations = [row]
    held_keys = {("kojiro", "005930", date(2026, 10, 10), "1")}
    n = await outcome.fill_outcomes(db, today=date(2026, 10, 14), held_keys=held_keys)
    assert n == 0
    assert db.filled_outcomes == []


@pytest.mark.asyncio
async def test_fill_outcomes_closes_position_when_sold_matches_quantity():
    db = _FakeDB()
    row = {"id": 1, "strategy_id": "kojiro", "ticker": "005930", "buy_date": date(2026, 10, 10),
          "buy_order_no": "1", "quantity": 10, "act_date": date(2026, 10, 13)}
    db.open_evaluations = [row]
    db.sell_trades[("kojiro", "005930")] = [
        {"order_no": "999", "quantity": 10, "price": 71000, "timestamp": datetime(2026, 10, 13, 9, 5, tzinfo=KST)},
    ]
    n = await outcome.fill_outcomes(db, today=date(2026, 10, 14), held_keys=set())
    assert n == 1
    assert db.filled_outcomes[0]["outcome_status"] == "closed"
    assert db.filled_outcomes[0]["sold_qty_after"] == 10
    assert db.filled_outcomes[0]["exit_vwap_after_won"] == 71000


@pytest.mark.asyncio
async def test_fill_outcomes_marks_manual_exit_from_journal_source():
    db = _FakeDB()
    row = {"id": 1, "strategy_id": "kojiro", "ticker": "005930", "buy_date": date(2026, 10, 10),
          "buy_order_no": "1", "quantity": 5, "act_date": date(2026, 10, 13)}
    db.open_evaluations = [row]
    db.sell_trades[("kojiro", "005930")] = [
        {"order_no": "999", "quantity": 5, "price": 71000, "timestamp": datetime(2026, 10, 13, 9, 5, tzinfo=KST)},
    ]
    db.journal_rows[(date(2026, 10, 13), "999", "SELL")] = {"source": "external", "reason_code": None}
    await outcome.fill_outcomes(db, today=date(2026, 10, 14), held_keys=set())
    assert db.filled_outcomes[0]["exit_is_manual"] is True


@pytest.mark.asyncio
async def test_fill_outcomes_leaves_open_when_not_enough_sold_and_within_window():
    db = _FakeDB()
    row = {"id": 1, "strategy_id": "kojiro", "ticker": "005930", "buy_date": date(2026, 10, 10),
          "buy_order_no": "1", "quantity": 10, "act_date": date(2026, 10, 13)}
    db.open_evaluations = [row]
    n = await outcome.fill_outcomes(db, today=date(2026, 10, 14), held_keys=set())
    assert n == 0
    assert db.filled_outcomes == []


@pytest.mark.asyncio
async def test_fill_outcomes_marks_unknown_after_window_with_no_evidence():
    db = _FakeDB()
    row = {"id": 1, "strategy_id": "kojiro", "ticker": "005930", "buy_date": date(2026, 10, 10),
          "buy_order_no": "1", "quantity": 10, "act_date": date(2026, 9, 1)}
    db.open_evaluations = [row]
    n = await outcome.fill_outcomes(db, today=date(2026, 10, 14), held_keys=set())
    assert n == 1
    assert db.filled_outcomes[0]["outcome_status"] == "unknown"


@pytest.mark.asyncio
async def test_fill_outcomes_one_row_error_does_not_stop_others():
    db = _FakeDB()
    bad = {"id": 1, "strategy_id": "kojiro", "ticker": "005930", "buy_date": date(2026, 10, 10),
          "buy_order_no": "1", "quantity": 10, "act_date": None}  # act_date None → since 계산 실패
    good = {"id": 2, "strategy_id": "kojiro", "ticker": "000660", "buy_date": date(2026, 10, 10),
           "buy_order_no": "2", "quantity": 5, "act_date": date(2026, 10, 13)}
    db.open_evaluations = [bad, good]
    db.sell_trades[("kojiro", "000660")] = [
        {"order_no": "888", "quantity": 5, "price": 1000, "timestamp": datetime(2026, 10, 13, 9, 5, tzinfo=KST)},
    ]
    n = await outcome.fill_outcomes(db, today=date(2026, 10, 14), held_keys=set())
    assert n == 1
    assert db.filled_outcomes[0]["id"] == 2
