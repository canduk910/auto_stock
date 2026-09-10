# DEST: tests/unit/engine/test_cycle273a_partial_row_full_fill_no_correction.py
"""cycle273a Red — PARTIAL 행 위 전량 체결이 **보정 3단 우회를 타지 않는다**.

명세 = `_workspace/red/cycle273a_c235v2_cancel_timer_and_partial_spec.md`
정본 = `_workspace/analysis/2026-09-10_cycle273_UA_order_engine.md` §3.2·§4

`FakeDb` 는 실 WHERE 의 **거울**이다(`tests/unit/engine/test_cycle271_execute_buy_fill_during_insert.py`
`FakeDb.update_status` 선례). 거울을 실 SQL 계약에 맞춰 두어야 "초록인 채로 낡은
계약을 검증" 하는 사고를 피한다.

## HEAD 기준 RED / GREEN

| 테스트 | HEAD | 이유 |
|---|---|---|
| `test_b1_buy_full_fill_on_partial_row_updates_directly` | **RED** | 1차 UPDATE 가 `affected=0` → 보정 INSERT → UniqueViolation → 강제 UPDATE |
| `test_b1b_sell_full_fill_on_partial_row_updates_directly` | **RED** | 매도 축 동일 |
| `test_b1c_true_notice_first_race_still_inserts` | GREEN(회귀 가드) | 행 자체가 없는 진짜 선행 race 는 보정 INSERT 경로 **보존** |
| `test_b1d_stale_partial_row_of_other_order_untouched` | GREEN(회귀 가드) | 직전 검증 HIGH#1 — 실 WHERE 에 order_no 도 날짜 경계도 없어 다른 order_no 의 좌초 PARTIAL 행까지 잡히던 것을, 이 사이클이 추가한 KST 당일 하한(`src/db/trade_history.py`)이 어제 이전 좌초 행을 제외한다 |

`test_b1` 이 `_completed_orders` 까지 보는 이유 = cycle271 F-271-1 누수의
**유일한 관측 입구**가 이 가짜 `affected=0` 이기 때문이다(UA §4). 트리거가 닫히면
누수 관측도 사라진다 — 다만 누수 자체(`except` 분기 미소비 + 일일 clear 부재)는
별건이며 이 사이클 범위 밖이다(승인 필요).
"""

from __future__ import annotations

import logging

import pytest
from asyncpg.exceptions import UniqueViolationError
from unittest.mock import AsyncMock

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.trade import TradeStatus

pytestmark = pytest.mark.unit

TICKER = "004990"
ORDER_NO = "0000305100"


class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = "kojiro") -> None:
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
    """`trade_history` 의 **WHERE 거울**.

    - status 필터: 기본 `PENDING` 단독 / `match_partial=True` 면 `PENDING∪PARTIAL`
    - `order_no` 인자가 오면 WHERE 에 AND 로 더한다(cycle273b F-1 과 호환 — 실
      call-site 는 아직 이 인자를 넘기지 않으므로 오늘은 사실상 비활성 분기다)
    - `match_partial=True` 는 KST 당일 하한(`timestamp >= _today_kst_iso()`)도 겸한다
      (cycle273a 회귀가드, 직전 검증 HIGH#1 — `src/db/trade_history.py` 실 WHERE 거울).
      `timestamp="yesterday"` 로 표시한 행은 오늘의 좌초 보호 대상이다.
    - `insert_trade` 는 migration 029 부분 UNIQUE `(ticker, order_no, trade_type)` 재현
    """

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.inserts: list[dict] = []
        self.forced: list[tuple] = []

    def add_row(self, *, ticker, trade_type, strategy, order_no, status, price=0, timestamp="today"):
        self.rows.append({
            "ticker": ticker, "trade_type": trade_type, "strategy": strategy,
            "order_no": order_no, "status": status, "price": price,
            "timestamp": timestamp,
        })

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
        for row in self.rows:
            if row["ticker"] != ticker or row["trade_type"] != trade_type.value:
                continue
            if row["strategy"] != strategy or row["status"] not in allowed:
                continue
            if order_no is not None and row["order_no"] != order_no:
                continue
            # cycle273a 회귀가드(직전 검증 HIGH#1) — match_partial=True 인 실 WHERE 는
            # KST 당일 하한도 함께 건다(§trade_history.py). order_no 필터(위)는 실
            # call-site 가 아직 넘기지 않아 비활성이므로, 오늘은 날짜 하한이 유일한
            # 좌초-행 보호막이다.
            if match_partial and row.get("timestamp", "today") != "today":
                continue
            row["status"] = status.value
            if price is not None:
                row["price"] = price
            affected += 1
        return affected

    async def insert_trade(self, record) -> None:
        key = (record.ticker, record.order_no, record.trade_type.value)
        for row in self.rows:
            if (row["ticker"], row["order_no"], row["trade_type"]) == key:
                raise UniqueViolationError(
                    "duplicate key value violates unique constraint "
                    "\"uq_trade_history_ticker_order_no_type\""
                )
        self.inserts.append({"ticker": record.ticker, "order_no": record.order_no})
        self.add_row(
            ticker=record.ticker, trade_type=record.trade_type.value,
            strategy=record.strategy, order_no=record.order_no,
            status=record.status.value, price=record.price,
        )

    async def forced_update(self, order_no, trade_type, status, price=None, profit_loss=None) -> int:
        self.forced.append((order_no, trade_type.value, status.value))
        affected = 0
        for row in self.rows:
            if row["order_no"] != order_no or row["trade_type"] != trade_type.value:
                continue
            if row["status"] not in (TradeStatus.PENDING.value, TradeStatus.PARTIAL.value):
                continue
            row["status"] = status.value
            if price is not None:
                row["price"] = price
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
    monkeypatch.setattr(_oe, "cancel_order", AsyncMock(return_value={"rt_cd": "0"}))
    monkeypatch.setattr(_oe, "place_order", AsyncMock(return_value={"rt_cd": "0"}))
    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(_positions, "save_position", AsyncMock(return_value=None))
    monkeypatch.setattr(_positions, "delete_position", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 30)
    return fake


@pytest.fixture
def registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    reg.register(_DummyStrategy("kojiro"))
    return reg


@pytest.fixture
def engine(registry: StrategyRegistry, db: FakeDb) -> OrderEngine:
    eng = OrderEngine(registry)
    eng._unsubscribe_if_no_other_strategy = AsyncMock(return_value=None)
    yield eng
    for task in list(eng._pending_cancel_tasks.values()):
        task.cancel()
    eng._pending_cancel_tasks.clear()


def _warns(caplog, prefix: str) -> list[str]:
    """caplog 단언은 **WARNING 이상 + prefix** 로 한정한다(CI 루트 로거 DEBUG)."""
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)
    ]


@pytest.mark.asyncio
async def test_b1_buy_full_fill_on_partial_row_updates_directly(engine, db, caplog):
    """RED (HEAD) — PARTIAL 행 위 매수 전량 체결은 1차 UPDATE 로 끝나야 한다."""
    db.add_row(
        ticker=TICKER, trade_type="BUY", strategy="kojiro",
        order_no=ORDER_NO, status=TradeStatus.PARTIAL.value, price=24_700,
    )
    engine._order_qty[ORDER_NO] = 5
    engine._order_strategy[ORDER_NO] = "kojiro"
    engine._order_ticker[ORDER_NO] = TICKER

    caplog.set_level(logging.DEBUG)
    await engine.handle_execution_notice(
        ticker=TICKER, order_no=ORDER_NO, side="BUY", price=24_800, quantity=5,
    )

    row = db.rows[0]
    assert row["status"] == TradeStatus.COMPLETED.value
    assert row["price"] == 24_800, "체결단가 정합(사이클 161) 불변"

    assert db.inserts == [], "PARTIAL 행이 있는데 보정 INSERT 를 시도했다"
    assert db.forced == [], "강제 UPDATE(자기치유) 우회를 탔다"
    assert _warns(caplog, "[buy_fill_correction_unique_violation]") == []
    assert engine._completed_orders == set(), (
        "가짜 affected=0 이 `_completed_orders` 에 스테일 order_no 를 남겼다 "
        "(cycle271 F-271-1 누수의 유일한 관측 입구)"
    )


@pytest.mark.asyncio
async def test_b1b_sell_full_fill_on_partial_row_updates_directly(
    engine, db, registry, caplog,
):
    """RED (HEAD) — 매도 축도 같은 계약."""
    sell_order = "0000400100"
    db.add_row(
        ticker=TICKER, trade_type="SELL", strategy="kojiro",
        order_no=sell_order, status=TradeStatus.PARTIAL.value, price=24_700,
    )
    registry.get("kojiro").state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=24_000, quantity=5, order_no="B-1", strategy_id="kojiro",
    )
    engine._order_qty[sell_order] = 5
    engine._order_strategy[sell_order] = "kojiro"
    engine._order_ticker[sell_order] = TICKER

    caplog.set_level(logging.DEBUG)
    await engine.handle_execution_notice(
        ticker=TICKER, order_no=sell_order, side="SELL", price=24_800, quantity=5,
    )

    assert db.rows[0]["status"] == TradeStatus.COMPLETED.value
    assert db.inserts == []
    assert db.forced == []
    assert _warns(caplog, "[sell_fill_correction_unique_violation]") == []
    assert engine._completed_orders == set()


@pytest.mark.asyncio
async def test_b1c_true_notice_first_race_still_inserts(engine, db, caplog):
    """GREEN(회귀 가드) — 행 자체가 없는 **진짜** 선행 race 는 보정 INSERT 를 유지한다.

    C235-V2-b 가 닫는 것은 "행은 있는데 status 가 PARTIAL 이라 못 잡는" 가짜
    `affected=0` 뿐이다. 진짜 race(= `execute_buy` 의 PENDING INSERT 전에 체결통보
    도착)는 여전히 `affected=0` 이고 보정 INSERT 로 복구돼야 한다.
    """
    engine._order_qty[ORDER_NO] = 5
    engine._order_strategy[ORDER_NO] = "kojiro"
    engine._order_ticker[ORDER_NO] = TICKER

    caplog.set_level(logging.DEBUG)
    await engine.handle_execution_notice(
        ticker=TICKER, order_no=ORDER_NO, side="BUY", price=24_800, quantity=5,
    )

    assert len(db.inserts) == 1, "진짜 선행 race 의 보정 INSERT 경로가 사라졌다"
    assert db.rows[0]["status"] == TradeStatus.COMPLETED.value
    assert ORDER_NO in engine._completed_orders, (
        "`execute_buy` 측 PENDING INSERT 생략 신호가 사라졌다"
    )


@pytest.mark.asyncio
async def test_b1d_stale_partial_row_of_other_order_untouched(engine, db, caplog):
    """회귀 가드(직전 검증 HIGH#1) — **다른** order_no 의 좌초 PARTIAL 행은 건드리지 않는다.

    실 `update_trade_status(match_partial=True)` 의 WHERE 는 ticker+trade_type+
    strategy+status 뿐이라 order_no 자체로는 구분하지 못한다(order_no 필터 신설은
    cycle273b F-1 범위, 이 사이클 밖). 대신 이 사이클은 같은 인자에 KST 당일
    하한(`timestamp >= _today_kst_iso()`)을 실었다 — **어제** 좌초된 PARTIAL 행은
    오늘 다른 주문의 전량 체결 COMPLETED UPDATE 에 휩쓸리지 않는다.
    """
    OLD_ORDER_NO = "OLD-X"
    db.add_row(
        ticker=TICKER, trade_type="BUY", strategy="kojiro",
        order_no=OLD_ORDER_NO, status=TradeStatus.PARTIAL.value, price=20_000,
        timestamp="yesterday",
    )
    new_order_no = "NEW-Y"
    db.add_row(
        ticker=TICKER, trade_type="BUY", strategy="kojiro",
        order_no=new_order_no, status=TradeStatus.PENDING.value, price=24_800,
        timestamp="today",
    )
    engine._order_qty[new_order_no] = 5
    engine._order_strategy[new_order_no] = "kojiro"
    engine._order_ticker[new_order_no] = TICKER

    caplog.set_level(logging.DEBUG)
    await engine.handle_execution_notice(
        ticker=TICKER, order_no=new_order_no, side="BUY", price=24_800, quantity=5,
    )

    stale_row = next(r for r in db.rows if r["order_no"] == OLD_ORDER_NO)
    assert stale_row["status"] == TradeStatus.PARTIAL.value, (
        "어제 좌초된 PARTIAL 행이 오늘 다른 주문의 전량체결 UPDATE 에 휩쓸렸다"
    )
    assert stale_row["price"] == 20_000

    new_row = next(r for r in db.rows if r["order_no"] == new_order_no)
    assert new_row["status"] == TradeStatus.COMPLETED.value
    assert new_row["price"] == 24_800
    assert db.inserts == [], "보호된 좌초 행 때문에 불필요한 보정 INSERT 가 나갔다"
