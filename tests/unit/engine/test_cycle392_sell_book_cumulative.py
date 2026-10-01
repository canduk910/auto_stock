"""cycle392 — 매도 주문 하나가 체결통보 여러 건으로 끝나면 **장부가 마지막 통보로 덮이던** 결함.

명세 = 세션 scratchpad `c392/spec.md` §6.1 (T1~T16) · 사용자 결정 4(2026-10-02 「손익 결함 수정하자」)

## 결함 (base `9df058d`)

`_handle_sell_fill` 은 통보 1건의 **증분**으로 손익을 잰다 —

```
profit_loss = (price - buy_price) * quantity      # 이 통보분
pos_strategy.state.daily_realized_pnl += profit_loss   # 메모리는 누적 — 맞다
...
update_trade_status(..., price=price, profit_loss=profit_loss)   # 장부는 대입 — 마지막 통보가 이긴다
```

`src/db/trade_history.py` 의 `UPDATE … SET price = $n, profit_loss = $m` 이 **대입**이라, 두 번에
나뉘어 체결된 주문은 장부에 「마지막 통보 체결가 · 마지막 통보 수량분 손익」 만 남는다.
실사고 2026-10-01 CJ ENM(035760) kojiro 주문 `0000501000` 5주 — 1주@36,150 + 4주@36,100,
매수가 39,400 → 장부 −13,200 · 36,100 / 실제 **−16,450 · 36,110**.

## 시정 계약 (이 파일이 지키는 것)

- 장부 `profit_loss` = 그 주문의 손익 증분 합 = 그 주문이 `daily_realized_pnl` 에 더한 합(I2)
- 장부 `price` = 그 주문의 체결 가중평균, 소수 둘째 자리 **ROUND_HALF_UP**
- 통보 1건 주문은 결과 불변(I3) · 메모리 손익·보유 축·`_selling`·주문 축 불변(I1·I6)
- 장부 쓰기 네 곳(COMPLETED UPDATE · PARTIAL UPDATE · 보정 INSERT · 강제 UPDATE)은 `await` 앞
  동기 영역에서 잡은 값을 쓴다 — 같은 주문의 다음 통보가 끼어들어도 섞이지 않는다(I5, T10)

## 하네스

`FakeLedger` 는 `src/db/trade_history.py` 의 **실 WHERE·SET 거울**이다(cycle273a `FakeDb` 선례).
덮어쓰기는 mock kwargs 가 아니라 **행 상태**에서만 드러나므로 단언은 최종 행으로 한다.
- `update_trade_status`: ticker·trade_type·strategy·status(기본 PENDING, `match_partial=True` 면
  PENDING∪PARTIAL)·`order_no`(주면) 일치 행에 status/price/profit_loss **대입**(실 SQL 이 `float()` 바인딩)
- `insert_trade`: migration 029 부분 UNIQUE `(ticker, order_no, trade_type)` 재현
- `_update_trade_status_by_order_no`: order_no·trade_type·PENDING∪PARTIAL 행에 대입

🔴 caplog 단언은 WARNING 이상 + prefix 로 센다(CI 루트 로거 DEBUG). 「매도 전량 체결:」 INFO
한 줄(T16)만 예외로, 레벨 **정확히 INFO** + 메시지 **앞머리**로 한정한다(B7 선례).
"""
from __future__ import annotations

import inspect
import logging
import random
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncio
import pytest
from asyncpg.exceptions import UniqueViolationError

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit

_OE_LOGGER = "src.engine.order_engine"

TICKER = "035760"
NAME = "CJ ENM"
BUY = 39_400
ORDER_NO = "0000501000"
BUY_DATE = date(2026, 9, 30)

_SIDS = ("momentum", "kojiro", "volatility_breakout", "long_tail_volatility", "bull_flag_breakout")


class _Strat(StrategyBase):
    def __init__(self, strategy_id: str) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id, name=f"{strategy_id}-dummy", enabled=True,
                weight=0.25, params={"exchange": "KRX"},
            )
        )
        self.state.total_investment = 10_000_000

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 0


class FakeLedger:
    """`trade_history` 의 WHERE·SET 거울(위 모듈 docstring)."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.calls: list[dict] = []

    def add_pending(self, *, order_no: str, strategy: str, quantity: int,
                    ticker: str = TICKER, price: float = 0.0) -> None:
        """`execute_sell` 의 PENDING INSERT 가 남긴 행(price = 주문 시점 값)."""
        self.rows.append({
            "ticker": ticker, "trade_type": TradeType.SELL.value, "strategy": strategy,
            "order_no": order_no, "status": TradeStatus.PENDING.value,
            "price": float(price), "quantity": quantity, "profit_loss": None,
        })

    def row(self, order_no: str) -> dict:
        hits = [r for r in self.rows if r["order_no"] == order_no]
        assert len(hits) == 1, f"order_no={order_no} 행 {len(hits)}개 (기대 1)"
        return hits[0]

    def writes(self, kind: str, status: TradeStatus | None = None) -> list[dict]:
        return [
            c for c in self.calls
            if c["kind"] == kind and (status is None or c["status"] == status.value)
        ]

    @staticmethod
    def _set(row: dict, status: TradeStatus, price, profit_loss) -> None:
        row["status"] = status.value
        if price is not None:
            row["price"] = float(price)
        if profit_loss is not None:
            row["profit_loss"] = float(profit_loss)

    async def update_trade_status(
        self, ticker, trade_type, status, strategy="momentum",
        price=None, profit_loss=None, *, order_no=None, match_partial=False,
    ) -> int:
        allowed = (
            {TradeStatus.PENDING.value, TradeStatus.PARTIAL.value}
            if match_partial else {TradeStatus.PENDING.value}
        )
        affected = 0
        for r in self.rows:
            if r["ticker"] != ticker or r["trade_type"] != trade_type.value:
                continue
            if r["strategy"] != strategy or r["status"] not in allowed:
                continue
            if order_no is not None and r["order_no"] != order_no:
                continue
            self._set(r, status, price, profit_loss)
            affected += 1
        self.calls.append({
            "kind": "update", "status": status.value, "price": price,
            "profit_loss": profit_loss, "order_no": order_no, "affected": affected,
        })
        return affected

    async def insert_trade(self, record) -> None:
        key = (record.ticker, record.order_no, record.trade_type.value)
        self.calls.append({
            "kind": "insert", "status": record.status.value, "price": record.price,
            "profit_loss": record.profit_loss, "order_no": record.order_no,
            "quantity": record.quantity,
        })
        if record.order_no:
            for r in self.rows:
                if (r["ticker"], r["order_no"], r["trade_type"]) == key:
                    raise UniqueViolationError(
                        "duplicate key value violates unique constraint "
                        "\"uq_trade_history_ticker_order_no_type\""
                    )
        self.rows.append({
            "ticker": record.ticker, "trade_type": record.trade_type.value,
            "strategy": record.strategy, "order_no": record.order_no,
            "status": record.status.value, "price": float(record.price),
            "quantity": record.quantity,
            "profit_loss": None if record.profit_loss is None else float(record.profit_loss),
        })

    async def forced_update(self, order_no, trade_type, status,
                            price=None, profit_loss=None) -> int:
        affected = 0
        for r in self.rows:
            if r["order_no"] != order_no or r["trade_type"] != trade_type.value:
                continue
            if r["status"] not in (TradeStatus.PENDING.value, TradeStatus.PARTIAL.value):
                continue
            self._set(r, status, price, profit_loss)
            affected += 1
        self.calls.append({
            "kind": "forced", "status": status.value, "price": price,
            "profit_loss": profit_loss, "order_no": order_no, "affected": affected,
        })
        return affected


_ENGINES: list[OrderEngine] = []


@pytest.fixture(autouse=True)
def _drain_timers():
    """남은 30초 잔여취소/재주문 타이머 정리 — 'Task was destroyed' 경고 차단."""
    _ENGINES.clear()
    yield
    for eng in _ENGINES:
        for task in list(eng._pending_cancel_tasks.values()):
            task.cancel()
        eng._pending_cancel_tasks.clear()
    _ENGINES.clear()


def _env(monkeypatch, *, holdings: dict[str, tuple[int, int]] | None = None,
         names: dict[str, str] | None = None):
    """매도 체결 환경. `holdings` = {strategy_id: (보유수량, 매수가)} (ticker = TICKER)."""
    import src.db.positions as positions_mod
    import src.db.stock_master as _sm
    import src.engine.order_engine as _oe
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", dict(names or {TICKER: NAME}), raising=False)

    registry = StrategyRegistry()
    strats: dict[str, _Strat] = {}
    for sid in _SIDS:
        s = _Strat(sid)
        registry.register(s)
        strats[sid] = s
    for sid, (qty, bp) in (holdings or {}).items():
        strats[sid].state.positions[TICKER] = Position(
            ticker=TICKER, buy_price=bp, quantity=qty, order_no="BUY-1",
            strategy_id=sid, buy_date=BUY_DATE, high_since_buy=bp,
        )

    engine = OrderEngine(registry)
    engine._unsubscribe_if_no_other_strategy = AsyncMock(return_value=None)
    _ENGINES.append(engine)

    ledger = FakeLedger()
    env = SimpleNamespace(
        engine=engine, registry=registry, s=strats, ledger=ledger,
        saves=[], deletes=[], save_gate=None,
    )

    _save_sig = inspect.signature(positions_mod.save_position)

    async def fake_save(*args, **kwargs):
        bound = _save_sig.bind(*args, **kwargs)
        bound.apply_defaults()
        env.saves.append(dict(bound.arguments))
        gate = env.save_gate
        if gate is not None:
            env.save_gate = None  # 첫 저장 한 번만 붙잡는다(T10)
            await gate.wait()
        return None

    async def fake_delete(ticker, *a, **k):
        env.deletes.append(ticker)
        return None

    noop = AsyncMock(return_value=None)
    monkeypatch.setattr(_oe, "update_trade_status", ledger.update_trade_status)
    monkeypatch.setattr(_oe, "insert_trade", ledger.insert_trade)
    monkeypatch.setattr(_oe, "_update_trade_status_by_order_no", ledger.forced_update)
    monkeypatch.setattr(_oe, "_lookup_strategy_from_trade_history",
                        AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "write_log", noop)
    monkeypatch.setattr(_oe, "safe_write_log", noop)
    monkeypatch.setattr(_oe, "cancel_order", AsyncMock(return_value={"rt_cd": "0"}))
    monkeypatch.setattr(_oe, "place_order", AsyncMock(return_value={"rt_cd": "0"}))
    monkeypatch.setattr(positions_mod, "save_position", fake_save)
    monkeypatch.setattr(positions_mod, "delete_position", fake_delete)
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    return env


def _map(env, order_no: str, qty: int, sid: str, *, ticker: str = TICKER) -> None:
    """우리가 낸 매도 주문의 매핑(`execute_sell`/manual-sell 이 발사 직후 등록하는 것)."""
    env.engine._order_qty[order_no] = qty
    env.engine._order_strategy[order_no] = sid
    env.engine._order_ticker[order_no] = ticker


async def _notice(env, order_no: str, qty: int, price: int, *, ticker: str = TICKER) -> None:
    await env.engine.handle_execution_notice(
        ticker=ticker, order_no=order_no, side="SELL", price=price, quantity=qty,
    )


def _vwap(fills: list[tuple[int, int]]) -> float:
    """기대 가중평균 — Σ(가격×수량)/Σ수량, 소수 둘째 자리 ROUND_HALF_UP."""
    v = sum(q * p for q, p in fills)
    n = sum(q for q, _ in fills)
    return float((Decimal(v) / Decimal(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _warns(caplog, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)
    ]


# ---------------------------------------------------------------------------
# T1 — 회귀 기준(10-01 CJ ENM 실사고)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t1_cj_enm_two_notices_book_is_order_cumulative(monkeypatch):
    """1주@36,150 → 4주@36,100 (매수 39,400). 장부 = −16,450 · 36,110 · 5주 · COMPLETED.

    base: COMPLETED UPDATE 가 마지막 통보분(4주 × −3,300 = −13,200, 36,100)을 대입한다.
    """
    env = _env(monkeypatch, holdings={"kojiro": (5, BUY)})
    _map(env, ORDER_NO, 5, "kojiro")
    env.ledger.add_pending(order_no=ORDER_NO, strategy="kojiro", quantity=5, price=36_150)

    await _notice(env, ORDER_NO, 1, 36_150)
    row = env.ledger.row(ORDER_NO)
    assert row["status"] == TradeStatus.PARTIAL.value
    assert row["price"] == 36_150
    assert row["profit_loss"] == -3_250, "첫 통보 뒤 PARTIAL 행 = 그 시점 누적(1주분)"

    await _notice(env, ORDER_NO, 4, 36_100)
    row = env.ledger.row(ORDER_NO)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["quantity"] == 5
    assert row["profit_loss"] == -16_450, (
        f"장부 손익 {row['profit_loss']} — 주문 누적 −16,450 이어야 한다 "
        "(−13,200 이면 마지막 통보 4주분으로 덮인 것 = 결함)"
    )
    assert row["price"] == 36_110.0, (
        f"장부 가격 {row['price']} — 체결 가중평균 180,550/5 = 36,110 이어야 한다"
    )
    # I1 — 메모리는 원래 누적이다(불변).
    assert env.s["kojiro"].state.daily_realized_pnl == -16_450


# ---------------------------------------------------------------------------
# T2 — 아바텍형(09-22 BFB) · T2b 반올림 규약
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t2_avatec_shape_vwap_two_decimals(monkeypatch):
    """14주 @13,040 — 3@12,380 → 11@12,350. 장부 12,356.43 · −9,570 (기록은 12,350 · −7,590)."""
    env = _env(monkeypatch, holdings={"bull_flag_breakout": (14, 13_040)},
               names={TICKER: "아바텍"})
    order = "0001637700"
    _map(env, order, 14, "bull_flag_breakout")
    env.ledger.add_pending(order_no=order, strategy="bull_flag_breakout", quantity=14)

    await _notice(env, order, 3, 12_380)
    await _notice(env, order, 11, 12_350)

    row = env.ledger.row(order)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["profit_loss"] == -9_570
    assert row["price"] == 12_356.43


@pytest.mark.asyncio
async def test_t2b_vwap_rounds_half_up_not_bankers(monkeypatch):
    """199@100 + 1@101 → 20,001/200 = 100.005 → ROUND_HALF_UP **100.01**.

    `round(100.005, 2)` 는 float 표현(100.00499…) 때문에 100.0, Decimal 은행가 반올림도
    100.00 이다 — 명세 §4.2 의 `quantize(Decimal("0.01"), ROUND_HALF_UP)` 만 100.01 을 낸다.
    """
    env = _env(monkeypatch, holdings={"kojiro": (200, 100)})
    order = "0000900100"
    _map(env, order, 200, "kojiro")
    env.ledger.add_pending(order_no=order, strategy="kojiro", quantity=200)

    await _notice(env, order, 199, 100)
    await _notice(env, order, 1, 101)

    row = env.ledger.row(order)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["profit_loss"] == 1
    assert row["price"] == 100.01, f"장부 가격 {row['price']} — ROUND_HALF_UP 100.01 이어야 한다"


# ---------------------------------------------------------------------------
# T3 — 통보 1건은 결과 불변(I3) — base 에서도 초록
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t3_single_notice_unchanged(monkeypatch):
    env = _env(monkeypatch, holdings={"long_tail_volatility": (10, 33_000)})
    order = "0000004705"
    _map(env, order, 10, "long_tail_volatility")
    env.ledger.add_pending(order_no=order, strategy="long_tail_volatility", quantity=10)

    await _notice(env, order, 10, 33_250)

    row = env.ledger.row(order)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["price"] == 33_250
    assert row["profit_loss"] == 2_500
    assert env.s["long_tail_volatility"].state.daily_realized_pnl == 2_500


# ---------------------------------------------------------------------------
# T4 — 통보 3건(가운데 PARTIAL UPDATE 는 0건 — 현행)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t4_three_notices(monkeypatch):
    """1@100 → 1@110 → 3@95, 매수 100, 주문 5 → 손익 0+10−15 = −5, 가격 495/5 = 99.0."""
    env = _env(monkeypatch, holdings={"kojiro": (5, 100)})
    order = "0000900200"
    _map(env, order, 5, "kojiro")
    env.ledger.add_pending(order_no=order, strategy="kojiro", quantity=5)

    await _notice(env, order, 1, 100)
    await _notice(env, order, 1, 110)
    await _notice(env, order, 3, 95)

    row = env.ledger.row(order)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["profit_loss"] == -5
    assert row["price"] == 99.0
    assert env.s["kojiro"].state.daily_realized_pnl == -5
    # 둘째 통보의 PARTIAL 쓰기는 이미 PARTIAL 인 행을 못 잡아 0건이지만(현행 — 명세 §4.3), 그 인자도
    # 그 시점 누적이어야 한다(2주 · 210/2 = 105.0 · 0+10). 첫 통보는 증분 = 누적이라 이 단언만이
    # 「PARTIAL 쓰기만 증분으로 되돌림」(M4)을 행위로 드러낸다.
    partials = env.ledger.writes("update", TradeStatus.PARTIAL)
    assert [(c["price"], c["profit_loss"], c["affected"]) for c in partials] == [
        (100, 0, 1), (105.0, 10, 0),
    ], partials


# ---------------------------------------------------------------------------
# T5 — 체결통보 선행 race → 보정 INSERT
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t5_notice_first_race_correction_insert_is_cumulative(monkeypatch, caplog):
    """PENDING 행 없음 → 첫 통보 PARTIAL 0건 → 둘째 통보 COMPLETED 0건 → 보정 INSERT.

    INSERT 행 = 수량 total_filled · 가중평균 · 누적(첫 통보 몫 포함). race WARNING 의 손익도 누적.
    """
    env = _env(monkeypatch, holdings={"kojiro": (5, BUY)})
    _map(env, ORDER_NO, 5, "kojiro")
    caplog.set_level(logging.DEBUG)

    await _notice(env, ORDER_NO, 1, 36_150)
    assert env.ledger.rows == [], "PENDING 행이 없으니 PARTIAL UPDATE 는 0건이어야 한다"
    await _notice(env, ORDER_NO, 4, 36_100)

    inserts = env.ledger.writes("insert")
    assert len(inserts) == 1
    row = env.ledger.row(ORDER_NO)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["quantity"] == 5
    assert row["profit_loss"] == -16_450, (
        f"보정 INSERT 손익 {row['profit_loss']} — 첫 통보 몫(−3,250)이 빠지면 −13,200"
    )
    assert row["price"] == 36_110.0
    assert ORDER_NO in env.engine._completed_orders
    races = _warns(caplog, "체결통보 선행 race")
    assert len(races) == 1 and "손익: -16450" in races[0], races


# ---------------------------------------------------------------------------
# T6 — 보정 INSERT UniqueViolation → 강제 UPDATE
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t6_forced_update_after_unique_violation_is_cumulative(monkeypatch, caplog):
    """PENDING 행의 strategy 가 매핑과 어긋난 경우(005940 계열): UPDATE 0건 → INSERT 충돌 → 강제 UPDATE."""
    env = _env(monkeypatch, holdings={"kojiro": (5, BUY)})
    _map(env, ORDER_NO, 5, "kojiro")
    env.ledger.add_pending(order_no=ORDER_NO, strategy="momentum", quantity=5)
    caplog.set_level(logging.DEBUG)

    await _notice(env, ORDER_NO, 1, 36_150)
    await _notice(env, ORDER_NO, 4, 36_100)

    assert len(_warns(caplog, "[sell_fill_correction_unique_violation]")) == 1
    forced = env.ledger.writes("forced")
    assert len(forced) == 1
    assert forced[0]["profit_loss"] == -16_450
    assert forced[0]["price"] == 36_110.0
    row = env.ledger.row(ORDER_NO)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["profit_loss"] == -16_450
    assert row["price"] == 36_110.0


# ---------------------------------------------------------------------------
# T7 — 부분 체결 뒤 잔량 취소(종료 통보 없음)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t7_partial_then_remaining_cancelled_keeps_first_partial(monkeypatch):
    """행은 PARTIAL · 첫 PARTIAL 쓰기 값 그대로(현행). 누적기는 남고 일일 리셋에서 빈다."""
    env = _env(monkeypatch, holdings={"kojiro": (5, BUY)})
    _map(env, ORDER_NO, 5, "kojiro")
    env.ledger.add_pending(order_no=ORDER_NO, strategy="kojiro", quantity=5)

    await _notice(env, ORDER_NO, 1, 36_150)

    row = env.ledger.row(ORDER_NO)
    assert row["status"] == TradeStatus.PARTIAL.value
    assert row["price"] == 36_150
    assert row["profit_loss"] == -3_250
    book = env.engine._sell_fill_book
    assert book.get(ORDER_NO) == (1, 36_150, -3_250), (
        f"누적기 {book.get(ORDER_NO)!r} — (체결수량 합, 체결금액 합, 손익 증분 합) 이어야 한다"
    )
    env.engine.reset_daily_state()
    assert env.engine._sell_fill_book == {}


# ---------------------------------------------------------------------------
# T8 — overrun 클램프(증분 2 로 깎인 통보)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t8_overrun_clamped_increment_is_what_the_book_counts(monkeypatch):
    """주문 5 · 통보 3@36,150 → 3@36,100(누적 6 → 5 클램프, 증분 2).

    장부 = 3·(−3,250) + 2·(−3,300) = −16,350 · (108,450 + 72,200)/5 = 36,130.0 — 클램프 전
    수량(6)으로 가중하면 가격이 36,125 로 틀린다.
    """
    env = _env(monkeypatch, holdings={"kojiro": (5, BUY)})
    _map(env, ORDER_NO, 5, "kojiro")
    env.ledger.add_pending(order_no=ORDER_NO, strategy="kojiro", quantity=5)

    await _notice(env, ORDER_NO, 3, 36_150)
    await _notice(env, ORDER_NO, 3, 36_100)

    row = env.ledger.row(ORDER_NO)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert env.s["kojiro"].state.daily_realized_pnl == -16_350
    assert row["profit_loss"] == -16_350
    assert row["price"] == 36_130.0


# ---------------------------------------------------------------------------
# T9 — 같은 종목 두 주문(원주문 부분 체결 → 재주문)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t9_two_orders_same_ticker_do_not_mix(monkeypatch):
    """원주문 A 5주 중 2@36,150 만 체결 → 재주문 B 3주가 1@36,100 + 2@36,050 으로 끝남.

    B 행 = B 의 통보만(−10,000 · 36,066.67). A 행 = PARTIAL(36,150 · −6,500) 그대로.
    누적기 키가 종목이면 B 에 A 몫이 섞인다.
    """
    env = _env(monkeypatch, holdings={"kojiro": (5, BUY)})
    a, b = "0000600100", "0000600200"
    _map(env, a, 5, "kojiro")
    env.ledger.add_pending(order_no=a, strategy="kojiro", quantity=5)
    await _notice(env, a, 2, 36_150)

    _map(env, b, 3, "kojiro")
    env.ledger.add_pending(order_no=b, strategy="kojiro", quantity=3)
    await _notice(env, b, 1, 36_100)
    await _notice(env, b, 2, 36_050)

    row_a = env.ledger.row(a)
    assert row_a["status"] == TradeStatus.PARTIAL.value
    assert (row_a["price"], row_a["profit_loss"]) == (36_150, -6_500)
    row_b = env.ledger.row(b)
    assert row_b["status"] == TradeStatus.COMPLETED.value
    assert row_b["profit_loss"] == -10_000
    assert row_b["price"] == _vwap([(1, 36_100), (2, 36_050)]) == 36_066.67
    assert env.s["kojiro"].state.daily_realized_pnl == -16_500


# ---------------------------------------------------------------------------
# T10 — 끼어들기(I5)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t10_interleaved_notice_does_not_mix_into_earlier_write(monkeypatch):
    """통보1(부분)이 `save_position` await 에 붙잡힌 동안 통보2(전량)가 끝까지 진행된다.

    - 통보2 의 COMPLETED 쓰기 = 2통보 누적(−16,450 · 36,110)
    - 통보1 이 깨어나 내는 PARTIAL 쓰기 인자 = **통보1 시점** 누적(1주분 · 36,150 · −3,250) —
      await 뒤에 누적기를 다시 읽으면 섞이거나(통보2 몫) 사라진다(종료 분기 pop)
    - PARTIAL 쓰기는 PENDING 만 잡으므로 COMPLETED 뒤 착지는 0건 → 최종 행 = 누적값
    """
    env = _env(monkeypatch, holdings={"kojiro": (5, BUY)})
    _map(env, ORDER_NO, 5, "kojiro")
    env.ledger.add_pending(order_no=ORDER_NO, strategy="kojiro", quantity=5)
    gate = asyncio.Event()
    env.save_gate = gate

    t1 = asyncio.create_task(_notice(env, ORDER_NO, 1, 36_150))
    for _ in range(20):
        await asyncio.sleep(0)
        if env.saves:
            break
    assert env.saves and not t1.done(), "통보1 이 save_position 에서 붙잡히지 않았다(하네스 전제)"
    assert env.ledger.writes("update") == [], "통보1 이 붙잡히기 전에 장부를 썼다(하네스 전제)"

    await _notice(env, ORDER_NO, 4, 36_100)
    completed = env.ledger.writes("update", TradeStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0]["profit_loss"] == -16_450
    assert completed[0]["price"] == 36_110.0

    gate.set()
    await t1
    partial = env.ledger.writes("update", TradeStatus.PARTIAL)
    assert len(partial) == 1
    assert partial[0]["affected"] == 0, "COMPLETED 뒤 착지한 PARTIAL 은 PENDING 만 잡아 0건이어야 한다"
    assert (partial[0]["price"], partial[0]["profit_loss"]) == (36_150, -3_250), (
        f"통보1 PARTIAL 쓰기 인자 {partial[0]} — 통보1 시점 누적이어야 한다(I5)"
    )
    row = env.ledger.row(ORDER_NO)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert (row["price"], row["profit_loss"]) == (36_110.0, -16_450)


# ---------------------------------------------------------------------------
# T11 — 주문 도중 추적 포지션이 사라진다(뒤 통보 증분 0)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t11_position_vanishes_mid_order_book_equals_memory(monkeypatch):
    """추적 보유 1주인데 주문 3주(운영자 초과분). 1@36,150 → 보유 닫힘 → 2@36,100 은 포지션
    없음(`buy_price = price` → 증분 0). 장부 = 증분 합 −3,250 = 메모리 합(I2), 가격 = 3주 가중평균.
    """
    env = _env(monkeypatch, holdings={"kojiro": (1, BUY)})
    order = "0000700300"
    _map(env, order, 3, "kojiro")
    env.ledger.add_pending(order_no=order, strategy="kojiro", quantity=3)

    await _notice(env, order, 1, 36_150)
    assert TICKER not in env.s["kojiro"].state.positions
    await _notice(env, order, 2, 36_100)

    mem = env.s["kojiro"].state.daily_realized_pnl
    assert mem == -3_250
    row = env.ledger.row(order)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["profit_loss"] == mem
    assert row["price"] == _vwap([(1, 36_150), (2, 36_100)]) == 36_116.67


# ---------------------------------------------------------------------------
# T12 — B7 분할 매도(보유 10 · 수동 4주가 2통보)
# ---------------------------------------------------------------------------
async def _t12_split(monkeypatch, caplog):
    env = _env(monkeypatch, holdings={"kojiro": (10, BUY)})
    order = "0000700100"
    _map(env, order, 4, "kojiro")
    env.ledger.add_pending(order_no=order, strategy="kojiro", quantity=4)
    env.engine._selling.add(TICKER)  # manual-sell 이 발사 앞에서 세우는 표식
    caplog.set_level(logging.DEBUG)
    await _notice(env, order, 2, 36_150)
    await _notice(env, order, 2, 36_100)
    return env, order


@pytest.mark.asyncio
async def test_t12a_split_sell_b7_axes_unchanged(monkeypatch, caplog):
    """보유 축·`_selling`·성공 서명 불변(I6) — base 에서도 초록."""
    env, _ = await _t12_split(monkeypatch, caplog)
    pos = env.s["kojiro"].state.positions.get(TICKER)
    assert pos is not None and pos.quantity == 6
    assert env.deletes == []
    assert env.saves and env.saves[-1]["quantity"] == 6
    assert len(_warns(caplog, "[sell_fill_holding_remains]")) == 1
    assert TICKER not in env.engine._selling
    assert env.s["kojiro"].state.daily_realized_pnl == 2 * (36_150 - BUY) + 2 * (36_100 - BUY)


@pytest.mark.asyncio
async def test_t12b_split_sell_book_is_four_share_cumulative(monkeypatch, caplog):
    """장부 = 4주 누적 −13,100 · 144,500/4 = 36,125.0."""
    env, order = await _t12_split(monkeypatch, caplog)
    row = env.ledger.row(order)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["profit_loss"] == -13_100
    assert row["price"] == 36_125.0


# ---------------------------------------------------------------------------
# T13 — 보유자 모호([sell_fill_owner_ambiguous])
# ---------------------------------------------------------------------------
async def _t13_ambiguous(monkeypatch, caplog):
    env = _env(monkeypatch, holdings={"momentum": (5, BUY), "volatility_breakout": (5, BUY)})
    order = "0000700200"
    _map(env, order, 4, "kojiro")  # 장부 전략은 보유하지 않는다 + 보유자 2
    env.ledger.add_pending(order_no=order, strategy="kojiro", quantity=4)
    caplog.set_level(logging.DEBUG)
    await _notice(env, order, 2, 36_150)
    await _notice(env, order, 2, 36_100)
    return env, order


@pytest.mark.asyncio
async def test_t13a_ambiguous_owner_unchanged(monkeypatch, caplog):
    """현행 그대로(I6) — 어느 보유도 안 건드리고 증분 0. base 에서도 초록."""
    env, order = await _t13_ambiguous(monkeypatch, caplog)
    assert len(_warns(caplog, "[sell_fill_owner_ambiguous]")) == 2
    for sid in ("momentum", "volatility_breakout"):
        assert env.s[sid].state.positions[TICKER].quantity == 5
        assert env.s[sid].state.daily_realized_pnl == 0
    assert env.s["kojiro"].state.daily_realized_pnl == 0
    row = env.ledger.row(order)
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["profit_loss"] == 0, "장부 손익 = 증분 합(0)"


@pytest.mark.asyncio
async def test_t13b_ambiguous_owner_book_price_is_vwap(monkeypatch, caplog):
    """손익이 0 이어도 가격은 그 주문 체결 가중평균(36,125.0)."""
    env, order = await _t13_ambiguous(monkeypatch, caplog)
    assert env.ledger.row(order)["price"] == 36_125.0


# ---------------------------------------------------------------------------
# T14 — 불변식 I2(무작위 통보 열, 시드 고정)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t14_book_equals_memory_for_random_fill_sequences(monkeypatch):
    """주문 20개 · 2~4통보 · 수량 1~5 · 가격 ±3틱(50원). 주문마다 종료 시
    장부 손익 == 그 주문이 `daily_realized_pnl` 에 더한 합, |장부가격×수량 − Σ체결금액| ≤ 0.005×수량.
    """
    rng = random.Random(392)
    orders = []
    for i in range(20):
        ticker = f"39{i:04d}"
        b = rng.randint(200, 800) * 50
        s0 = b + rng.randint(-20, 20) * 50
        fills = [
            (rng.randint(1, 5), s0 + rng.randint(-3, 3) * 50)
            for _ in range(rng.randint(2, 4))
        ]
        orders.append((ticker, f"00{i:08d}", b, fills))

    env = _env(monkeypatch, names={t: f"N{t}" for t, *_ in orders})
    strat = env.s["kojiro"]
    failures = []
    for ticker, order, b, fills in orders:
        total = sum(q for q, _ in fills)
        strat.state.positions[ticker] = Position(
            ticker=ticker, buy_price=b, quantity=total, order_no="BUY-1",
            strategy_id="kojiro", buy_date=BUY_DATE, high_since_buy=b,
        )
        _map(env, order, total, "kojiro", ticker=ticker)
        env.ledger.add_pending(order_no=order, strategy="kojiro", quantity=total, ticker=ticker)
        before = strat.state.daily_realized_pnl
        for q, p in fills:
            await _notice(env, order, q, p, ticker=ticker)
        mem = strat.state.daily_realized_pnl - before
        row = env.ledger.row(order)
        value = sum(q * p for q, p in fills)
        if row["status"] != TradeStatus.COMPLETED.value:
            failures.append((order, "status", row["status"]))
        if row["profit_loss"] != mem:
            failures.append((order, "pnl", row["profit_loss"], mem))
        if abs(row["price"] * total - value) > 0.005 * total + 1e-6:
            failures.append((order, "price", row["price"], value / total))
    assert failures == [], f"I2 위반 {len(failures)}건: {failures[:6]}"


# ---------------------------------------------------------------------------
# T15 — 일일 정리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t15_reset_daily_state_clears_the_book(monkeypatch):
    env = _env(monkeypatch, holdings={"kojiro": (5, BUY)})
    _map(env, ORDER_NO, 5, "kojiro")
    env.ledger.add_pending(order_no=ORDER_NO, strategy="kojiro", quantity=5)
    await _notice(env, ORDER_NO, 2, 36_150)
    assert ORDER_NO in env.engine._sell_fill_book, "부분 체결 주문의 누적기가 없다"
    env.engine.reset_daily_state()
    assert env.engine._sell_fill_book == {}


# ---------------------------------------------------------------------------
# T16 — 로그
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t16_full_fill_log_reports_order_cumulative(monkeypatch, caplog):
    """「매도 전량 체결:」 INFO — `@` 는 마지막 통보 체결가, `손익:` 은 누적, 끝에 `avg=` 가중평균."""
    env = _env(monkeypatch, holdings={"kojiro": (5, BUY)})
    _map(env, ORDER_NO, 5, "kojiro")
    env.ledger.add_pending(order_no=ORDER_NO, strategy="kojiro", quantity=5)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)

    await _notice(env, ORDER_NO, 1, 36_150)
    await _notice(env, ORDER_NO, 4, 36_100)

    lines = [
        r.getMessage() for r in caplog.records
        if r.name == _OE_LOGGER and r.levelno == logging.INFO
        and r.getMessage().startswith("매도 전량 체결:")
    ]
    assert len(lines) == 1, lines
    msg = lines[0]
    assert re.search(r"\b5주 @ 36100\b", msg), msg
    assert re.search(r"손익: -16450\b", msg), f"손익이 주문 누적이 아니다: {msg}"
    assert re.search(r"avg=36110\.00\b", msg), f"avg= 가중평균이 없다: {msg}"
