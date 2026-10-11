"""cycle446 — `test_lw_exit_shadow.py` 전용 가짜(G0/G1 클라이언트·DB·OpenAI). 실 I/O 0."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


class FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class FakeHttpClient:
    def __init__(self, responses: dict):
        self.responses = responses  # path -> FakeResp | Exception

    async def get(self, path):
        r = self.responses.get(path)
        if isinstance(r, Exception):
            raise r
        return r


def ok_body(data):
    return FakeResp(200, {"success": True, "data": data})


class FakeDB:
    def __init__(self):
        self.daily_rows = {}  # ticker -> list[dict] (DESC)
        self.head_rows = {}  # ticker -> dict
        self.existing = {}  # key -> dict
        self.upserts = []
        self.runs = []
        # outcome 쪽(쓰지 않지만 Runner.run_once 가 outcome 모듈을 호출한다)
        self.missing_next_open = []
        self.open_prices = {}
        self.open_evaluations = []
        self.sell_trades = {}
        self.journal_rows = {}

    async def fetch_recent_daily(self, ticker, limit):
        return list(self.daily_rows.get(ticker, []))[:limit]

    async def fetch_head_row(self, ticker):
        return self.head_rows.get(ticker)

    async def get_existing_evaluation(self, *, bar_date, strategy_id, ticker, buy_date, buy_order_no):
        return self.existing.get((bar_date, strategy_id, ticker, buy_date, buy_order_no or ""))

    async def upsert_evaluation(self, row: dict) -> None:
        self.upserts.append(dict(row))
        key = (row["bar_date"], row["strategy_id"], row["ticker"], row["buy_date"], row["buy_order_no"] or "")
        self.existing[key] = {"id": len(self.upserts), "attempts": row["attempts"], "result": row["result"]}

    async def upsert_run(self, row: dict) -> None:
        self.runs.append(dict(row))

    # ---- outcome 모듈용(간단 위임) ----
    async def list_open_missing_next_open(self, *, before):
        return self.missing_next_open

    async def fetch_open_price(self, ticker, bas_dd):
        return self.open_prices.get((ticker, bas_dd))

    async def fill_next_open(self, eval_id, open_price, now):
        pass

    async def list_open_evaluations(self):
        return self.open_evaluations

    async def fetch_sell_trades(self, strategy_id, ticker, since):
        return self.sell_trades.get((strategy_id, ticker), [])

    async def fetch_journal_order(self, order_date, order_no, side):
        return self.journal_rows.get((order_date, order_no, side))

    async def fill_outcome(self, eval_id, **kw):
        pass


class FakeOpenAI:
    def __init__(self, content=None, finish_reason="stop", raise_exc=None, hang=False):
        self.content = content
        self.finish_reason = finish_reason
        self.raise_exc = raise_exc
        self.hang = hang
        self.calls = 0
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.calls += 1
        if self.hang:
            import asyncio
            await asyncio.sleep(999)
        if self.raise_exc:
            raise self.raise_exc

        class _Usage:
            prompt_tokens = 10
            completion_tokens = 20

        class _Msg:
            def __init__(self, content):
                self.content = content

        class _Choice:
            def __init__(self, content, finish_reason):
                self.message = _Msg(content)
                self.finish_reason = finish_reason

        class _Resp:
            def __init__(self, content, finish_reason):
                self.choices = [_Choice(content, finish_reason)]
                self.usage = _Usage()

        return _Resp(self.content, self.finish_reason)


def daily_row(bas_dd, *, close=1000, open_=1000, high=1010, low=990, volume=10000, updated_at=None):
    return {
        "bas_dd": bas_dd, "open_price": open_, "high_price": high, "low_price": low,
        "close_price": close, "volume": volume, "updated_at": updated_at or datetime.now(KST),
    }


def g1_item(*, strategy_id="kojiro", ticker="005930", buy_date="2026-10-10", quantity=10,
           buy_price=1000, order_no="1", stop_price=900, stop_source="hard_pct",
           target_price=None, entry_atr=20.0, high_since_buy=1050, kk_armed=None):
    return {
        "strategy_id": strategy_id, "ticker": ticker, "stop_price": stop_price,
        "stop_source": stop_source, "target_price": target_price, "buy_price": buy_price,
        "quantity": quantity, "high_since_buy": high_since_buy, "buy_date": buy_date,
        "order_no": order_no, "entry_atr": entry_atr, "kk_armed": kk_armed, "kk_arm_price": None,
    }
