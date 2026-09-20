# DEST: tests/unit/engine/test_cycle273b_161580_cross_order_overwrite.py
"""cycle273b Red — F-1 본 사건 재현: 한 주문의 체결이 **다른 주문 행**을 덮는다.

명세 = `_workspace/red/cycle273b_philoptics_no_behavior_3_spec.md`
정본 = `_workspace/analysis/2026-09-10_161580_root_cause.md`

같은 ticker·같은 strategy 의 PENDING 행이 둘(다른 order_no) 있을 때, 주문 A 의
전량 체결이 `update_trade_status(ticker, BUY, COMPLETED, strategy=...)` 로
**두 행 모두** COMPLETED 로 만든다. 주문 B 는 아직 체결되지도 않았는데 완결 상태가
되어 (a) 정산에 이중 계상되고 (b) 뒤늦게 도착한 B 의 체결통보는 1차 UPDATE 0건 →
보정 INSERT → UniqueViolation → 강제 UPDATE(PENDING∪PARTIAL) 도 못 잡는다.

## 🔴 이 사이클 최대 위험 (§6.2) — 이 파일이 함께 지키는 것

REST `ODNO`(`src/api/order.py:75`)와 체결통보 `fields[2]`(`src/realtime/handler.py:682`)
는 **둘 다 정규화가 없다**. 표기가 다르면 `AND order_no = $n` 이 항상 0건이 되어
**모든 체결이 보정 INSERT 로 낙하**하고, 그때는 UniqueViolation 이 아니라 새 order_no
로 **중복 행이 조용히 INSERT** 된다(정산 이중계상). `test_f2_order_no_mismatch_...`
가 그 실패 모드를 명시적으로 고정한다 — 고치는 것이 아니라 **보이게** 만든다.

## HEAD 기준 RED / GREEN

| 테스트 | HEAD |
|---|---|
| `test_f1_full_fill_updates_only_its_own_order_row` | **RED** |
| `test_f1_sell_full_fill_updates_only_its_own_order_row` | **RED** |
| `test_f1_cancel_after_wait_updates_only_its_own_order_row` | **RED** (직전 검증 HIGH#1 companion — C5 행위 증거) |
| `test_f2_order_no_mismatch_falls_back_to_correction_insert` | **RED** (위험 고정) |
"""

from __future__ import annotations

import pytest
from asyncpg.exceptions import UniqueViolationError
from unittest.mock import AsyncMock

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.trade import TradeStatus

pytestmark = pytest.mark.unit

TICKER = "161580"
STRATEGY = "donchian_swing"
ORDER_A = "0000123456"
ORDER_B = "0000123499"


class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = STRATEGY) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id, name=strategy_id, enabled=True, weight=1.0,
                params={"exchange": "KRX"},
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


class FakeDb:
    """`trade_history` WHERE 거울 — `order_no` 인자가 오면 그 주문으로 좁힌다."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.inserts: list[tuple] = []

    def add_row(self, *, order_no, trade_type="BUY", status=TradeStatus.PENDING.value,
                ticker=TICKER, strategy=STRATEGY, price=0):
        self.rows.append({
            "ticker": ticker, "trade_type": trade_type, "strategy": strategy,
            "order_no": order_no, "status": status, "price": price,
        })

    def row(self, order_no: str) -> dict:
        return next(r for r in self.rows if r["order_no"] == order_no)

    async def update_trade_status(
        self, ticker, trade_type, status, strategy="momentum",
        price=None, profit_loss=None, **kwargs,
    ) -> int:
        match_partial = bool(kwargs.get("match_partial", False))
        order_no = kwargs.get("order_no")
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
            r["status"] = status.value
            if price is not None:
                r["price"] = price
            affected += 1
        return affected

    async def insert_trade(self, record) -> None:
        key = (record.ticker, record.order_no, record.trade_type.value)
        for r in self.rows:
            if (r["ticker"], r["order_no"], r["trade_type"]) == key:
                raise UniqueViolationError("uq_trade_history_ticker_order_no_type")
        self.inserts.append(key)
        self.add_row(
            order_no=record.order_no, trade_type=record.trade_type.value,
            status=record.status.value, ticker=record.ticker,
            strategy=record.strategy, price=record.price,
        )

    async def forced_update(self, order_no, trade_type, status, price=None, profit_loss=None) -> int:
        affected = 0
        for r in self.rows:
            if r["order_no"] != order_no or r["trade_type"] != trade_type.value:
                continue
            if r["status"] not in (TradeStatus.PENDING.value, TradeStatus.PARTIAL.value):
                continue
            r["status"] = status.value
            affected += 1
        return affected


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDb:
    import src.db.positions as _positions
    import src.engine.order_engine as _oe

    fake = FakeDb()
    monkeypatch.setattr(_oe, "update_trade_status", fake.update_trade_status)
    monkeypatch.setattr(_oe, "insert_trade", fake.insert_trade)
    monkeypatch.setattr(_oe, "_update_trade_status_by_order_no", fake.forced_update)
    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(_positions, "save_position", AsyncMock(return_value=None))
    monkeypatch.setattr(_positions, "delete_position", AsyncMock(return_value=None))
    return fake


@pytest.fixture
def registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    reg.register(_DummyStrategy())
    return reg


@pytest.fixture
def engine(registry: StrategyRegistry, db: FakeDb) -> OrderEngine:
    eng = OrderEngine(registry)
    eng._unsubscribe_if_no_other_strategy = AsyncMock(return_value=None)
    return eng


@pytest.mark.asyncio
async def test_f1_full_fill_updates_only_its_own_order_row(engine, db):
    """RED (HEAD) — 161580 재현. 주문 A 체결이 주문 B 행까지 COMPLETED 로 만든다."""
    db.add_row(order_no=ORDER_A)
    db.add_row(order_no=ORDER_B)

    engine._order_qty[ORDER_A] = 2
    engine._order_strategy[ORDER_A] = STRATEGY
    engine._order_ticker[ORDER_A] = TICKER

    await engine.handle_execution_notice(
        ticker=TICKER, order_no=ORDER_A, side="BUY", price=25_000, quantity=2,
    )

    assert db.row(ORDER_A)["status"] == TradeStatus.COMPLETED.value
    assert db.row(ORDER_B)["status"] == TradeStatus.PENDING.value, (
        "주문 A 의 체결이 아직 체결되지도 않은 주문 B 의 행을 COMPLETED 로 덮었다 "
        "(161580 본 사건 — 정산 이중계상 + B 체결통보의 자기치유 불능)"
    )


@pytest.mark.asyncio
async def test_f1_sell_full_fill_updates_only_its_own_order_row(engine, db, registry):
    """RED (HEAD) — 매도 축도 같다."""
    sell_a, sell_b = "0000900001", "0000900002"
    db.add_row(order_no=sell_a, trade_type="SELL")
    db.add_row(order_no=sell_b, trade_type="SELL")
    registry.get(STRATEGY).state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=24_000, quantity=2, order_no="B-1", strategy_id=STRATEGY,
    )

    engine._order_qty[sell_a] = 2
    engine._order_strategy[sell_a] = STRATEGY
    engine._order_ticker[sell_a] = TICKER

    await engine.handle_execution_notice(
        ticker=TICKER, order_no=sell_a, side="SELL", price=25_000, quantity=2,
    )

    assert db.row(sell_a)["status"] == TradeStatus.COMPLETED.value
    assert db.row(sell_b)["status"] == TradeStatus.PENDING.value


@pytest.mark.asyncio
async def test_f1_cancel_after_wait_updates_only_its_own_order_row(engine, db, monkeypatch):
    """직전 검증 HIGH#1 companion — C5(`_cancel_after_wait`) 행위 케이스.

    AST1 은 `order_no=order_no` 가 **구조적으로** 넘어가는지만 본다 — 이 테스트는
    그 결과가 실제로 옳은지(다른 주문 행을 건드리지 않는지)를 실행해서 본다.
    부분체결 주문 A 의 30초 잔여취소 타이머가 만료돼 CANCELLED 로 갱신될 때, 같은
    ticker·strategy 의 **다른 주문 B**(아직 PENDING)까지 함께 뒤집으면 정본 §2-b 가
    "가장 위험"으로 지목한 결함(B 의 체결통보가 1차 UPDATE 0 → 보정 INSERT →
    UniqueViolation → 강제 UPDATE 도 CANCELLED 를 못 집어 B 가 영구 CANCELLED)이 된다.
    """
    import src.engine.order_engine as _oe

    db.add_row(order_no=ORDER_A)
    db.add_row(order_no=ORDER_B)
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)
    monkeypatch.setattr(_oe, "cancel_order", AsyncMock(return_value=None))

    engine._schedule_cancel(TICKER, ORDER_A, 5, STRATEGY)
    task = engine._pending_cancel_tasks[(TICKER, "buy")]
    await task

    assert db.row(ORDER_A)["status"] == TradeStatus.CANCELLED.value
    assert db.row(ORDER_B)["status"] == TradeStatus.PENDING.value, (
        "주문 A 의 잔여취소가 아직 체결되지도 않은 주문 B 의 PENDING 행까지 CANCELLED "
        "로 뒤집었다(C5 — 정본 §2-b '가장 위험' 자리, B 는 이후 어느 경로로도 회복 불가)"
    )


@pytest.mark.asyncio
async def test_f2_order_no_mismatch_falls_back_to_correction_insert(engine, db):
    """RED (HEAD, 위험 고정) — order_no 표기가 어긋나면 무슨 일이 일어나는가.

    HEAD 는 WHERE 가 넓어 **엉뚱한 행(0000123456)을 잡아 "성공"** 하므로 이 단언이
    붉다. 그 "성공" 이 바로 161580 결함이다.

    DB 행은 `0000123456`, 체결통보는 `123456`(zero-padding 상이) 인 상황.
    F-1 이후에는 `AND order_no = $n` 이 0건 → 보정 INSERT 로 낙하하고,
    부분 UNIQUE 키가 `(ticker, order_no, trade_type)` 라 **중복 행이 조용히 INSERT** 된다.
    ⇒ 이 테스트는 시정이 아니라 **경보의 근거**다. D+1 서명
    `"체결통보 선행 race — COMPLETED 직접 INSERT"` 의 **증가 0** 이 배포 후
    표기 동일성의 실측 증거이며, 증가하면 즉시 롤백한다(§6.2).
    """
    db.add_row(order_no="0000123456")

    unpadded = "123456"
    engine._order_qty[unpadded] = 2
    engine._order_strategy[unpadded] = STRATEGY
    engine._order_ticker[unpadded] = TICKER

    await engine.handle_execution_notice(
        ticker=TICKER, order_no=unpadded, side="BUY", price=25_000, quantity=2,
    )

    # 표기 불일치의 서명 = 새 order_no 로 별도 행이 생긴다(UniqueViolation 이 아니다).
    assert (TICKER, unpadded, "BUY") in db.inserts
    assert len(db.rows) == 2, (
        "표기 불일치 시 중복 행이 생기는 경로 — 이 사실이 D+1 서명(선행 race INSERT 증가 0)의 근거다"
    )
