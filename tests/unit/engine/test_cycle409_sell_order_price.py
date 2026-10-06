"""cycle409 — 사용자 결정 10-04 Q4(8영역 승인): 매도 주문가 기록.

매도 주 경로 PENDING 의 `price` 는 매수가(`record_price=pos.buy_price` — 매도 장부 계약)라 그대로 두고,
주문가는 `TradeRecord.order_price` 로 따로 넘긴다. `insert_trade` 는 명시값이 있으면 그 값을 쓴다.

| # | 계약 |
|---|---|
| Q1 | `insert_trade` — `record.order_price` 명시값이 우선(매도 PENDING 도 기록) · 없으면 PENDING ∧ BUY 의 `price` |
| Q2 | 매도 주 경로 **시장가** = 주문 순간 현재가(`scanner.ticker_prices[t]["current_price"]`) — **매수가가 아니다** |
| Q3 | 매도 주 경로 시장가 + 현재가 캐시 없음(또는 0) = `order_price` None |
| Q4 | 매도 주 경로 **지정가** = `order_unpr`(= `limit_price`) |
| Q5 | 매도 폴백(시장가 거부 → 5호가 지정가) = `fallback_price` |
| Q6 | PENDING `price`(매도 장부 = 매수가) · `place_order` 인자 · 매핑은 그대로 |
| Q7 | `_sell_order_price` 는 never-raise(캐시가 이상해도 None) — 발사 뒤 경계 안에서 예외가 새면 PENDING 기록이 빠진다 |
| Q8 | 수동 매도 라우트 = 시장가라 주문 순간 현재가 · 캐시 없으면 None |
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.engine.util.tick_size import step_down
from src.models.order import OrderResult
from src.models.trade import TradeRecord, TradeStatus, TradeType

pytestmark = pytest.mark.unit

TICKER = "012200"
BUY_PRICE = 4500


class _Strat(StrategyBase):
    def __init__(self, sid: str = "momentum") -> None:
        super().__init__(StrategyConfig(strategy_id=sid, name=f"{sid}-dummy", enabled=True,
                                        weight=1.0, params={"exchange": "KRX"}))
        self.state.total_investment = 10_000_000

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 0


# ── Q1 ───────────────────────────────────────────────────────────────────────

async def _insert_cols(monkeypatch, record):
    from src.db import trade_history

    ex = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(trade_history.pg, "execute", ex)
    await trade_history.insert_trade(record)
    sql, *args = ex.await_args.args
    cols = [c.strip() for c in sql.split("(", 1)[1].split(")", 1)[0].split(",")]
    return dict(zip(cols, args))


def _rec(trade_type, price, order_price=None, status=TradeStatus.PENDING):
    return TradeRecord(ticker=TICKER, trade_type=trade_type, price=price, quantity=10,
                       status=status, strategy="momentum", order_no="X1",
                       order_price=order_price)


async def test_q1_explicit_order_price_wins_for_pending_sell(monkeypatch):
    row = await _insert_cols(monkeypatch, _rec(TradeType.SELL, BUY_PRICE, order_price=4600))
    assert row["price"] == pytest.approx(BUY_PRICE)
    assert row["order_price"] == pytest.approx(4600)


async def test_q1_explicit_order_price_wins_for_pending_buy(monkeypatch):
    row = await _insert_cols(monkeypatch, _rec(TradeType.BUY, 4500, order_price=4490))
    assert row["order_price"] == pytest.approx(4490)


async def test_q1_pending_sell_without_explicit_is_null(monkeypatch):
    row = await _insert_cols(monkeypatch, _rec(TradeType.SELL, BUY_PRICE))
    assert row["order_price"] is None


# ── execute_sell 하네스 ───────────────────────────────────────────────────────

@pytest.fixture
def env(monkeypatch):
    import src.engine.order_engine as _oe
    from src.engine import scanner

    reg = StrategyRegistry()
    strat = _Strat()
    strat.state.positions[TICKER] = Position(ticker=TICKER, buy_price=BUY_PRICE, quantity=10,
                                             order_no="PRE", strategy_id="momentum",
                                             buy_date=date.today())
    reg.register(strat)
    engine = OrderEngine(reg)
    insert = AsyncMock(return_value=None)
    place = AsyncMock(return_value=OrderResult(order_no="S-1", order_time="100000", krx_org_no=""))
    monkeypatch.setattr(_oe, "insert_trade", insert)
    monkeypatch.setattr(_oe, "place_order", place)
    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))

    async def _krx(self, strategy_id, *, ticker=None, side="sell"):  # noqa: ARG001
        return "KRX"

    monkeypatch.setattr(OrderEngine, "_strategy_exchange_async", _krx)
    monkeypatch.setattr(OrderEngine, "_apply_clock", lambda self, base, *a, **k: "KRX")
    prices: dict = {}
    monkeypatch.setattr(scanner, "ticker_prices", prices)
    return SimpleNamespace(engine=engine, insert=insert, place=place, prices=prices)


def _records(env) -> list[TradeRecord]:
    return [c.args[0] for c in env.insert.await_args_list]


async def test_q2_market_sell_order_price_is_current_price_not_buy_price(env):
    env.prices[TICKER] = {"current_price": 4620}
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "momentum")
    (rec,) = _records(env)
    assert rec.trade_type == TradeType.SELL and rec.status == TradeStatus.PENDING
    assert rec.order_price == 4620
    assert rec.order_price != BUY_PRICE
    assert rec.price == BUY_PRICE  # Q6 — 매도 장부 계약 그대로
    assert env.place.await_args.kwargs["price"] == 0
    assert env.engine._order_qty["S-1"] == 10


@pytest.mark.parametrize("cache", [{}, {TICKER: {}}, {TICKER: {"current_price": 0}}])
async def test_q3_market_sell_without_price_cache_is_none(env, cache):
    env.prices.update(cache)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "momentum")
    (rec,) = _records(env)
    assert rec.order_price is None


async def test_q4_limit_sell_order_price_is_limit(env):
    env.prices[TICKER] = {"current_price": 4620}
    await env.engine.execute_sell(TICKER, Signal.NEXT_DAY_CLEAR, "momentum", limit_price=4700)
    (rec,) = _records(env)
    assert env.place.await_args.kwargs["price"] == 4700
    assert rec.order_price == 4700


async def test_q5_fallback_order_price_is_fallback_price(env):
    env.prices[TICKER] = {"current_price": 4620}
    env.place.side_effect = [
        KisApiError(rt_cd="1", msg_cd="APBK1943", msg1="시장가호가불가로 주문이 불가합니다."),
        OrderResult(order_no="S-FB", order_time="100001", krx_org_no=""),
    ]
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "momentum")
    (rec,) = _records(env)
    assert rec.order_no == "S-FB"
    assert rec.order_price == step_down(4620, steps=5)
    assert rec.price == step_down(4620, steps=5)


# ── Q7 ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cache", [None, {TICKER: None}, {TICKER: {"current_price": "x"}},
                                   {TICKER: {"current_price": -5}}])
def test_q7_helper_never_raises(monkeypatch, cache):
    import src.engine.order_engine as _oe
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", cache)
    assert _oe._sell_order_price(TICKER, 0) is None
    assert _oe._sell_order_price(TICKER, 4700) == 4700


# ── Q8 수동 매도 ──────────────────────────────────────────────────────────────

@pytest.fixture
def manual(monkeypatch):
    import src.api.order as _api_order
    import src.db.trade_history as _th
    import src.engine.order_engine as _oe
    import src.engine.scanner as _scanner
    import src.routes.trading as _tr

    reg = StrategyRegistry()
    strat = _Strat("kojiro")
    strat.state.positions[TICKER] = Position(ticker=TICKER, buy_price=BUY_PRICE, quantity=10,
                                             order_no="PRE", strategy_id="kojiro",
                                             buy_date=date.today())
    reg.register(strat)
    engine = OrderEngine(reg)
    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_tr, "trading_scheduler", SimpleNamespace(registry=reg, order_engine=engine))
    prices: dict = {}
    monkeypatch.setattr(_scanner, "ticker_prices", prices)
    insert = AsyncMock(return_value=None)
    monkeypatch.setattr(_th, "insert_trade", insert)
    monkeypatch.setattr(_api_order, "place_order", AsyncMock(
        return_value=OrderResult(order_no="MAN-1", order_time="100000", krx_org_no="")))
    return SimpleNamespace(insert=insert, prices=prices)


async def _manual_sell():
    from src.routes.trading import ManualSellRequest, manual_sell

    return await manual_sell(ManualSellRequest(ticker=TICKER, quantity=3))


async def test_q8_manual_sell_records_current_price(manual):
    manual.prices[TICKER] = {"current_price": 4610}
    resp = await _manual_sell()
    assert resp.success is True, resp.message
    rec = manual.insert.await_args.args[0]
    assert rec.order_price == 4610
    assert rec.price == BUY_PRICE


async def test_q8_manual_sell_without_cache_is_none(manual):
    resp = await _manual_sell()
    assert resp.success is True, resp.message
    assert manual.insert.await_args.args[0].order_price is None
