"""cycle271 Red — 체결통보가 `execute_buy` 의 `insert_trade` **await 도중** 착지하는 race.

명세 = `_workspace/red/cycle271_execute_buy_fill_during_insert_spec.md`

## 무엇을 재는가

`OrderEngine.execute_buy` 는 `place_order` 응답 직후 주문번호 매핑을 **동기**로 등록한 뒤
(`order_engine.py:377~385`), `already_completed = result.order_no in self._completed_orders`
(`:388`) 로 "체결통보가 REST 응답보다 **먼저** 도착한" race 만 검사하고
`await insert_trade(record)` (`:407`) 로 PENDING 행을 넣는다.

그런데 그 `await` 는 이벤트 루프에 제어를 넘긴다. 그 사이에 WS 체결통보가 착지하면
`_handle_buy_fill` (`:1109`) 이 먼저 완주하고 — 전량 체결이면 `update_trade_status` 가
0건(아직 PENDING 행이 없다)이라 보정 INSERT 경로(`:1250~1266`)로 COMPLETED 행을 **먼저**
넣는다. 뒤이어 재개된 `execute_buy` 의 PENDING INSERT 는 같은
`(ticker, order_no, trade_type)` 이라 migration 029 부분 UNIQUE 인덱스
(`uq_trade_history_ticker_order_no_type`)를 위반하고 `UniqueViolationError` 를 던진다.

`src/db/trade_history.py::insert_trade` (`:65~85`) 는 `pg.execute` 를 감싸지 않으므로
예외가 그대로 전파되고, `execute_buy` 의 `except Exception:` (`:489`) 이 `raise` 로
호출자에게 올린다. 결과 = 매수·DB 는 정상인데 호출자는 **실패로 기록**한다.

## 계약 (명세 C1~C5)

- C1: 예외 없이 성공 반환
- C2: trade_history 정확히 1행 + 포지션 수량 정확 + 매핑 정리 + `cached_buyable_at == 0.0`
- C3: 기존 "체결통보 선행" race(사이클 30 `_completed_orders`) 회귀 보존
- C4: 시장가 경로 · 지정가 폴백 경로 양쪽 동일 계약
- C5: `[buy_fill_during_insert]` INFO 마커 1행

## Red 유효성 (작성 시점)

RED = C1-1 · C1-2(폴백) · C2-3(`_completed_orders` 누수) · C5-1 · C5-2
GREEN(회귀 가드) = C2-1 · C2-2 · C3-1 · C3-2 · C6-1 · C7-1 · B-1
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from itertools import count
from types import SimpleNamespace

import pytest
from asyncpg.exceptions import UniqueViolationError

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.balance import BuyableInfo
from src.models.order import OrderResult, OrderSide
from src.models.trade import TradeStatus, TradeType

# C5 — 접두 토큰은 명세가 고정한다. 서식(뒤따르는 key=value)은 Green 이 정한다.
MARKER = "[buy_fill_during_insert]"

TICKER = "004990"
PRICE = 20_000


# ---------------------------------------------------------------------------
# trade_history 부분 UNIQUE 인덱스 재현
# ---------------------------------------------------------------------------
class FakeTradeHistory:
    """`trade_history` + migration 029 부분 UNIQUE 인덱스를 재현하는 인메모리 표.

    `uq_trade_history_ticker_order_no_type ON (ticker, order_no, trade_type)
     WHERE order_no IS NOT NULL AND order_no != ''`

    실 DB 를 쓰지 않고도 "두 번째 INSERT 가 UniqueViolationError 로 거부된다" 는
    이 결함의 **유일한 전제**를 결정적으로 재현하기 위한 최소 모형이다.
    """

    def __init__(self) -> None:
        self.rows: list[dict] = []

    @staticmethod
    def _key(row: dict) -> tuple[str, str, str]:
        return (row["ticker"], row["order_no"], row["trade_type"])

    def insert(self, record) -> None:
        row = {
            "ticker": record.ticker,
            "order_no": record.order_no or "",
            "trade_type": record.trade_type.value,
            "status": record.status.value,
            "price": float(record.price),
            "quantity": record.quantity,
            "strategy": record.strategy,
        }
        if row["order_no"]:
            if any(self._key(r) == self._key(row) for r in self.rows):
                raise UniqueViolationError(
                    'duplicate key value violates unique constraint '
                    '"uq_trade_history_ticker_order_no_type"'
                )
        self.rows.append(row)

    def update_status(self, ticker, trade_type, status, strategy, price, *, match_partial=False) -> int:
        """`src/db/trade_history.py::update_trade_status` 의 WHERE 절 중 **status/strategy 축만** 거울 — `match_partial` 의 KST timestamp 하한은 실 SQL 레벨 테스트(`tests/unit/db/test_cycle273a_update_trade_status_match_partial.py::test_b2d`)와 실 PG 왕복(`test_cycleM2a_hotpath_roundtrip`)이 별도로 지킨다(cycle273a r2 MEDIUM).

        WHERE ticker AND trade_type AND status = 'PENDING' AND strategy
        (기본 = PENDING 단독). cycle273a `match_partial=True` 는 PENDING∪PARTIAL 을
        함께 잡는다 — 이 거울이 현행 그대로면 "초록인 채로 낡은 계약을 검증" 하게 된다.
        """
        allowed = {TradeStatus.PENDING.value}
        if match_partial:
            allowed.add(TradeStatus.PARTIAL.value)
        affected = 0
        for r in self.rows:
            if (
                r["ticker"] == ticker
                and r["trade_type"] == trade_type.value
                and r["status"] in allowed
                and r["strategy"] == strategy
            ):
                r["status"] = status.value
                if price is not None:
                    r["price"] = float(price)
                affected += 1
        return affected

    def force_update_by_order_no(self, order_no, trade_type, status, price) -> int:
        """`_update_trade_status_by_order_no` — cycle235 N1-b 로 PENDING·PARTIAL 포괄."""
        affected = 0
        in_progress = {TradeStatus.PENDING.value, TradeStatus.PARTIAL.value}
        for r in self.rows:
            if (
                r["order_no"] == order_no
                and r["trade_type"] == trade_type.value
                and r["status"] in in_progress
            ):
                r["status"] = status.value
                if price is not None:
                    r["price"] = float(price)
                affected += 1
        return affected

    def rows_for(self, ticker: str, order_no: str, trade_type: TradeType) -> list[dict]:
        return [
            r for r in self.rows
            if r["ticker"] == ticker
            and r["order_no"] == order_no
            and r["trade_type"] == trade_type.value
        ]


# ---------------------------------------------------------------------------
# 체결통보 주입기 — insert_trade 의 await 지점에 정확히 끼워 넣는다
# ---------------------------------------------------------------------------
@dataclass
class FillInjector:
    """`await insert_trade(PENDING)` 이 제어를 넘긴 그 순간 체결통보를 착지시킨다.

    실운영에서는 두 INSERT 가 DB 에서 경합하지만, 테스트에서는 "체결통보 처리가
    완주한 뒤 execute_buy 의 INSERT 가 도달" 하는 **결정적 순서**로 고정한다.
    이 순서가 결함이 발현되는 순서다(반대 순서면 `_handle_buy_fill` 쪽 보정 INSERT 가
    `[buy_fill_correction_unique_violation]` 로 이미 자체 복구한다).
    """

    engine: OrderEngine = None
    armed: bool = False
    fill_ratio: float = 1.0          # 1.0 = 전량, <1.0 = 부분
    fired_order_no: str | None = None
    fired_quantity: int = 0

    async def maybe_fire(self, record) -> None:
        if not self.armed:
            return
        if record.trade_type is not TradeType.BUY:
            return
        if record.status is not TradeStatus.PENDING:
            return
        self.armed = False
        qty = max(1, int(record.quantity * self.fill_ratio))
        self.fired_order_no = record.order_no
        self.fired_quantity = qty
        await self.engine.handle_execution_notice(
            ticker=record.ticker,
            order_no=record.order_no,
            side="BUY",
            price=int(record.price),
            quantity=qty,
        )


@dataclass
class EnvState:
    next_order_seq: count = field(default_factory=lambda: count(1))
    place_order_error: KisApiError | None = None
    buyable_max_qty: int = 999_999
    update_status_forced: int | None = None


def make_env(monkeypatch):
    """`OrderEngine` + momentum 1전략 + FakeTradeHistory 로 격리된 환경."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {TICKER: "테스트종목"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {TICKER: PRICE})
    monkeypatch.setattr(scanner, "ticker_prices", {})

    from src.engine.session import MarketBoard, session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))

    registry = StrategyRegistry()
    momentum = MomentumStrategy(
        StrategyConfig(
            strategy_id="momentum", name="모멘텀", weight=1.0,
            params={"exchange": "KRX"},   # stock_master 조회 경로 진입 차단
        )
    )
    registry.register(momentum)
    registry.allocate_funds(total_asset=100_000_000)

    engine = OrderEngine(registry)
    db = FakeTradeHistory()
    state = EnvState()
    injector = FillInjector(engine=engine)
    calls = SimpleNamespace(place_order=[], cancel_order=[], save_position=[], logs=[])

    async def fake_place_order(ticker, side, quantity, price=0, **kwargs):
        calls.place_order.append(
            {"ticker": ticker, "side": side, "quantity": quantity, "price": price}
        )
        if state.place_order_error is not None:
            err = state.place_order_error
            state.place_order_error = None
            raise err
        seq = next(state.next_order_seq)
        prefix = "BUY" if side == OrderSide.BUY else "SELL"
        return OrderResult(order_no=f"{prefix}-{seq:06d}", order_time="090501",
                           krx_org_no="00950")

    async def fake_cancel_order(*args, **kwargs):
        calls.cancel_order.append({"args": args, "kwargs": kwargs})
        return OrderResult(order_no="CXL-00001", order_time="090530", krx_org_no="00950")

    async def fake_get_buyable(ticker, price):
        return BuyableInfo(
            cash_available=999_000_000,
            max_buy_amount=999_000_000,
            max_buy_quantity=state.buyable_max_qty,
        )

    async def fake_insert_trade(record):
        # await 지점 = 체결통보가 끼어들 수 있는 유일한 창.
        await injector.maybe_fire(record)
        db.insert(record)

    async def fake_update_trade_status(ticker, trade_type, status, strategy=None,
                                       price=None, profit_loss=None,
                                       *, order_no=None, match_partial=False):
        # cycle273a — 실 시그니처가 keyword-only match_partial 을 받으므로(order_no 는
        # cycle273b 대비 선반영) 이 fake 도 받아야 한다 — 안 받으면 TypeError.
        if state.update_status_forced is not None:
            return state.update_status_forced
        return db.update_status(ticker, trade_type, status, strategy, price,
                                 match_partial=match_partial)

    async def fake_force_update(order_no, trade_type, status, price=None,
                               profit_loss=None):
        return db.force_update_by_order_no(order_no, trade_type, status, price)

    async def fake_save_position(ticker, ticker_name, buy_price, quantity, order_no,
                                 strategy_id, buy_date):
        calls.save_position.append(
            {"ticker": ticker, "quantity": quantity, "buy_price": buy_price,
             "order_no": order_no, "strategy_id": strategy_id}
        )

    async def fake_write_log(level, message):
        calls.logs.append({"level": level, "message": message})

    monkeypatch.setattr("src.engine.order_engine.place_order", fake_place_order)
    monkeypatch.setattr("src.engine.order_engine.cancel_order", fake_cancel_order)
    monkeypatch.setattr("src.engine.order_engine.get_buyable", fake_get_buyable)
    monkeypatch.setattr("src.engine.order_engine.insert_trade", fake_insert_trade)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status",
                        fake_update_trade_status)
    monkeypatch.setattr("src.engine.order_engine._update_trade_status_by_order_no",
                        fake_force_update)
    monkeypatch.setattr("src.engine.order_engine.write_log", fake_write_log)
    monkeypatch.setattr("src.engine.order_engine.PARTIAL_FILL_WAIT", 0)

    import src.db.positions as positions_mod

    monkeypatch.setattr(positions_mod, "save_position", fake_save_position)

    return SimpleNamespace(
        engine=engine, registry=registry, momentum=momentum,
        db=db, state=state, injector=injector, calls=calls,
    )


@pytest.fixture
def env(monkeypatch):
    e = make_env(monkeypatch)
    yield e
    # `_schedule_cancel` 백그라운드 task 정리 (부분 체결 케이스)
    for task in list(e.engine._pending_cancel_tasks.values()):
        task.cancel()


def _marker_records(caplog) -> list[str]:
    """C5 마커 행만 — 레벨(INFO 이상) + 접두 토큰으로 한정.

    CI 루트 로거는 DEBUG 라 무관한 debug 행이 섞인다(cycle252 T2 교훈).
    """
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.INFO and r.getMessage().startswith(MARKER)
    ]


# ---------------------------------------------------------------------------
# C1 — 예외 없이 성공한다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c1_1_market_path_when_full_fill_lands_during_insert_then_no_exception(env):
    """시장가 경로: 전량 체결통보가 insert_trade await 도중 착지해도 예외 없음. [RED]"""
    env.injector.armed = True
    env.injector.fill_ratio = 1.0

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)


@pytest.mark.asyncio
async def test_c1_2_fallback_path_when_full_fill_lands_during_insert_then_no_exception(env):
    """지정가 5호가 폴백 경로도 동일 계약 (C4). [RED]

    시장가 거부(APBK1943) → 폴백 place_order → 그 PENDING INSERT 도중 전량 체결 착지.
    ⚠️ 폴백 INSERT(`order_engine.py:471`)는 `except KisApiError as e:` **핸들러 안**이라
    바깥 `except Exception:` (`:489`) 이 잡지 못한다 — 예외가 호출자로 직행한다.
    """
    env.state.place_order_error = KisApiError("1", "APBK1943", "시장가매매불가 종목입니다")
    env.injector.armed = True
    env.injector.fill_ratio = 1.0

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)


# ---------------------------------------------------------------------------
# C2 — 최종 상태 정합
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c2_1_when_full_fill_during_insert_then_exactly_one_completed_row(env):
    """trade_history 에 그 주문 정확히 1행 COMPLETED. [GREEN — UNIQUE 인덱스가 방어]"""
    env.injector.armed = True
    env.injector.fill_ratio = 1.0

    try:
        await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)
    except UniqueViolationError:
        pass  # C1-1 이 잠그는 축 — 여기서는 DB 최종 상태만 본다

    order_no = env.injector.fired_order_no
    assert order_no, "체결통보 주입이 일어나지 않았다 — 픽스처 결함"
    rows = env.db.rows_for(TICKER, order_no, TradeType.BUY)
    assert len(rows) == 1, f"그 주문의 trade_history 행이 {len(rows)}개다 (기대 1)"
    assert rows[0]["status"] == TradeStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_c2_2_when_full_fill_during_insert_then_position_and_pending_are_correct(env):
    """포지션 수량 정확 + pending 정리 + `cached_buyable_at` 무효화.

    [GREEN] — `_handle_buy_fill` 전량 분기(`order_engine.py:1216~1219`, `:1318`)가
    pending 정리와 `cached_buyable_at = 0.0` 을 이미 수행한다. 시정이 이 성질을
    깨뜨리지 않는지 지키는 회귀 가드다.
    """
    env.injector.armed = True
    env.injector.fill_ratio = 1.0

    try:
        await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)
    except UniqueViolationError:
        pass

    state = env.momentum.state
    pos = state.positions.get(TICKER)
    assert pos is not None, "포지션이 등록되지 않았다"
    assert pos.quantity == env.injector.fired_quantity
    assert TICKER not in state.pending_buys
    assert TICKER not in state.pending_buy_amounts
    assert env.injector.fired_order_no not in env.engine._pending_buy_orders
    assert state.cached_buyable_at == 0.0, "가용액 캐시가 무효화되지 않았다"


@pytest.mark.asyncio
async def test_c2_3_when_full_fill_during_insert_then_completed_orders_is_not_leaked(env):
    """`_completed_orders` 에 order_no 가 남지 않는다. [RED]

    `_handle_buy_fill:1250` 이 `add` 하지만, `execute_buy:388` 의 검사는 이미 지나갔으므로
    `:390` 의 `discard` 가 실행되지 않는다 → set 에 영구 잔류.
    같은 order_no 가 재활용되면 다음 주문의 PENDING INSERT 가 조용히 생략된다.
    """
    env.injector.armed = True
    env.injector.fill_ratio = 1.0

    try:
        await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)
    except UniqueViolationError:
        pass

    order_no = env.injector.fired_order_no
    assert order_no not in env.engine._completed_orders, (
        f"_completed_orders 에 {order_no} 가 잔류한다 — 소비(discard) 되어야 한다"
    )


@pytest.mark.asyncio
async def test_c2_4_fallback_when_full_fill_during_insert_then_position_and_pending_are_correct(env):
    """지정가 폴백 경로도 C2 계열 상태 정합 계약을 만족한다. [GREEN — 검증 NO-GO #2 처리]

    `test_c2_2` 는 시장가 경로만 검증해 커버리지가 비대칭이었다(검증 NO-GO #2, LOW/비차단
    — order_engine.py:518 `state.cached_buyable_at = 0.0` 에 대응 가드 부재, 뮤테이션 m11
    ESCAPED). 시정 지점(`_insert_pending_buy_or_absorb_race`)은 두 경로가 공유하므로
    시장가에서 검증된 포지션/pending/캐시 무효화 성질이 폴백에서도 성립함을 실증한다.
    순수 테스트 전용 추가 — `order_engine.py` 는 1 byte 도 바뀌지 않는다.
    """
    env.state.place_order_error = KisApiError("1", "APBK1943", "시장가매매불가 종목입니다")
    env.injector.armed = True
    env.injector.fill_ratio = 1.0

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    state = env.momentum.state
    pos = state.positions.get(TICKER)
    assert pos is not None, "포지션이 등록되지 않았다"
    assert pos.quantity == env.injector.fired_quantity
    assert TICKER not in state.pending_buys
    assert TICKER not in state.pending_buy_amounts
    assert env.injector.fired_order_no not in env.engine._pending_buy_orders
    assert state.cached_buyable_at == 0.0, "가용액 캐시가 무효화되지 않았다 (폴백 경로)"

    order_no = env.injector.fired_order_no
    rows = env.db.rows_for(TICKER, order_no, TradeType.BUY)
    assert len(rows) == 1, f"그 주문의 trade_history 행이 {len(rows)}개다 (기대 1)"
    assert rows[0]["status"] == TradeStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_c2_5_fallback_without_fill_then_buyable_cache_is_invalidated_by_fallback_path_itself(env):
    """race 없는 지정가 폴백 경로 단독으로 가용액 캐시를 무효화한다. [GREEN — 검증 r2 NO-GO #1 처리]

    `test_c2_4` 는 체결통보를 INSERT 도중 착지시키는 race 시나리오라 `_handle_buy_fill` 이
    같은 `state` 에 `cached_buyable_at = 0.0` 을 먼저 수행한다 — 그래서 폴백 성공 후처리
    (`order_engine.py` 폴백 분기의 `state.cached_buyable_at = 0.0`)를 지워도 단언이 통과하는
    **공허한 가드**였다(뮤테이션 m4b ESCAPED, 핀 가드만 잡음). 여기서는 체결통보를 **착지시키지
    않는다**(`injector.armed=False`) — 그러면 그 값을 0.0 으로 만들 수 있는 코드는 폴백 분기
    한 줄뿐이므로, 그 줄이 사라지면 이 단언이 반드시 실패한다. 시장가 경로의 기존 가드
    `tests/integration/test_buy_flow.py` 와 대칭. 순수 테스트 전용 — 소스 무접촉.
    """
    env.state.place_order_error = KisApiError("1", "APBK1943", "시장가매매불가 종목입니다")
    assert env.injector.armed is False, "이 테스트는 race 없이 폴백 경로만 재야 한다"

    state = env.momentum.state
    state.cached_buyable_at = 1.0e12   # 센티널 — 0.0 으로 되돌아오는지 본다

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    # 폴백 지정가 주문이 접수됐고(체결 전) PENDING 1행 + pending_buys 등록 상태
    assert len(env.calls.place_order) == 2, "시장가 거부 → 지정가 폴백 재시도 1회가 아니다"
    assert env.calls.place_order[1]["price"] > 0, "폴백 주문이 지정가가 아니다"
    assert TICKER in state.pending_buys
    assert TICKER not in state.positions
    assert len(env.db.rows) == 1 and env.db.rows[0]["status"] == TradeStatus.PENDING.value
    assert state.cached_buyable_at == 0.0, (
        "폴백 성공 후처리가 가용액 캐시를 무효화하지 않았다 (order_engine 폴백 분기 한 줄)"
    )


# ---------------------------------------------------------------------------
# C3 — 기존 "체결통보 선행" race 회귀 보존 (사이클 30)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c3_1_when_order_no_already_in_completed_orders_then_pending_insert_skipped(env):
    """체결통보가 REST 응답보다 **먼저** 온 기존 race — PENDING INSERT 생략. [GREEN]"""
    expected_order_no = "BUY-000001"
    env.engine._completed_orders.add(expected_order_no)

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert env.db.rows == [], "PENDING INSERT 가 생략되지 않았다"
    assert expected_order_no not in env.engine._completed_orders, "set 이 소비되지 않았다"
    assert env.engine._order_strategy[expected_order_no] == "momentum"
    assert env.engine._order_ticker[expected_order_no] == TICKER


@pytest.mark.asyncio
async def test_c3_2_fallback_when_order_no_already_completed_then_pending_insert_skipped(env):
    """지정가 폴백 경로의 기존 선행 race 가드(`:452~458`)도 보존. [GREEN]"""
    env.state.place_order_error = KisApiError("1", "APBK1943", "시장가매매불가 종목입니다")
    env.engine._completed_orders.add("BUY-000001")

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert env.db.rows == [], "폴백 경로에서 PENDING INSERT 가 생략되지 않았다"
    assert "BUY-000001" not in env.engine._completed_orders


# ---------------------------------------------------------------------------
# C5 — 관측 마커
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c5_1_when_full_fill_during_insert_then_marker_emitted_once(env, caplog):
    """`[buy_fill_during_insert]` INFO 1행 + ticker/order_no 포함. [RED]"""
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    env.injector.armed = True
    env.injector.fill_ratio = 1.0

    try:
        await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)
    except UniqueViolationError:
        pass

    msgs = _marker_records(caplog)
    assert len(msgs) == 1, f"마커 {MARKER} 가 {len(msgs)}행 (기대 1행): {msgs}"
    assert TICKER in msgs[0]
    assert str(env.injector.fired_order_no) in msgs[0]


@pytest.mark.asyncio
async def test_c5_2_fallback_when_full_fill_during_insert_then_marker_emitted_once(env, caplog):
    """폴백 경로도 같은 마커를 남긴다. [RED]"""
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    env.state.place_order_error = KisApiError("1", "APBK1943", "시장가매매불가 종목입니다")
    env.injector.armed = True
    env.injector.fill_ratio = 1.0

    try:
        await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)
    except UniqueViolationError:
        pass

    msgs = _marker_records(caplog)
    assert len(msgs) == 1, f"마커 {MARKER} 가 {len(msgs)}행 (기대 1행): {msgs}"


@pytest.mark.asyncio
async def test_c5_3_when_no_race_then_marker_not_emitted(env, caplog):
    """평시 매수에는 마커가 찍히지 않는다 (마커의 신호 대 잡음). [GREEN]"""
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert _marker_records(caplog) == []


# ---------------------------------------------------------------------------
# C7 위험 봉인 — 다른 원인의 UniqueViolation 은 삼키지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c7_1_when_unique_violation_without_fill_then_still_raises(env, caplog):
    """체결통보가 없었는데 난 UniqueViolation 은 **그대로 전파**한다. [GREEN — 시정 후에도 유지]

    Green 후보 (a) "insert_trade 를 통째로 try/except UniqueViolationError 로 감싸
    성공 경로로 합류" 는 이 테스트를 깨뜨린다. 판별자는 `_completed_orders` 에 그
    order_no 가 실제로 등록됐는지다 — 즉 "체결통보가 먼저 INSERT 했다"는 **증거**가
    있을 때만 복구해야 한다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    # 체결통보 주입 없이, DB 에 같은 키의 행을 미리 심어 둔다 (다른 원인의 위반).
    env.db.rows.append({
        "ticker": TICKER, "order_no": "BUY-000001", "trade_type": TradeType.BUY.value,
        "status": TradeStatus.CANCELLED.value, "price": float(PRICE),
        "quantity": 1, "strategy": "momentum",
    })

    with pytest.raises(UniqueViolationError):
        await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert _marker_records(caplog) == [], "체결통보 증거 없이 복구 마커가 찍혔다"


@pytest.mark.asyncio
async def test_c7_2_when_non_unique_violation_with_fill_evidence_then_still_raises(
    env, monkeypatch, caplog,
):
    """체결통보 증거(`order_no ∈ _completed_orders`)가 있어도, 난 예외가
    `UniqueViolationError` 가 **아니면** 흡수하지 않고 그대로 전파한다. [검증 NO-GO #1 처리]

    (UniqueViolation ∧ 증거 없음) 은 `test_c7_1` 이 이미 덮는다. 이 테스트는 그 대각의
    빠진 사분면 — **(UniqueViolation 아님 ∧ 증거 있음)** — 을 채운다. `except
    UniqueViolationError:` 를 `except Exception:` 로 넓히는 뮤테이션(m7)이 표적 13케이스 +
    광역 회귀 5,443건 전부를 통과시키던 구멍을 이 케이스가 닫는다 — `insert_trade` 가
    연결 두절 등 **진짜 DB 장애**로 실패했는데 그 order_no 가 (다른 경로로) 우연히
    `_completed_orders` 에 있으면, 넓힌 except 는 그 진짜 실패를 "체결통보가 먼저
    INSERT 했다"로 오독해 흡수하고 성공을 보고한다 — 체결된 주문이 trade_history 에
    한 행도 없이 조용히 사라지는 경로다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")

    async def fake_insert_trade_conn_error(record):
        # await 지점에서 체결통보를 착지시켜 _completed_orders 에 "증거"를 남긴 뒤,
        # UniqueViolationError 가 **아닌** DB 예외로 실패한다 (연결 두절 등 재현).
        await env.injector.maybe_fire(record)
        raise ConnectionResetError("connection reset by peer")

    monkeypatch.setattr(
        "src.engine.order_engine.insert_trade", fake_insert_trade_conn_error,
    )
    env.injector.armed = True
    env.injector.fill_ratio = 1.0

    with pytest.raises(ConnectionResetError, match="connection reset by peer"):
        await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert env.injector.fired_order_no in env.engine._completed_orders, (
        "픽스처 결함 — 체결통보 증거(_completed_orders 등록)가 실제로 발생하지 않았다"
    )
    assert _marker_records(caplog) == [], (
        "UniqueViolationError 가 아닌데 복구 마커(성공 흡수)가 찍혔다"
    )


# ---------------------------------------------------------------------------
# C6 — 8영역 순수성 (기존 AST 가드가 계속 GREEN)
# ---------------------------------------------------------------------------
def test_c6_1_a_atomic_guard_still_holds():
    """`calc_buy_quantity` ~ `pending_buys.add` 구간 await 0건. [GREEN]

    시정 지점(`insert_trade` 전후)이 그 구간 **밖**임을 사이클마다 재확인한다.
    정본 가드는 `tests/unit/ast/test_budget_limit_ast.py::test_execute_buy_sizing_to_pending_is_await_free`
    이며 여기서는 그 가드를 직접 호출해 이 파일 단독 실행으로도 깨짐을 감지한다.
    """
    from tests.unit.ast.test_budget_limit_ast import (
        test_execute_buy_sizing_to_pending_is_await_free as _guard,
    )

    _guard()


# ---------------------------------------------------------------------------
# B — 경계 (부분 체결이 insert 도중 착지하는 경우는 예외가 나지 않는다)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b_1_when_partial_fill_during_insert_then_no_exception_and_single_row(env):
    """부분 체결만 착지한 경우 — 예외 없음, 행 1개. [GREEN — 계약 경계 문서화]

    `_handle_buy_fill` 부분 분기(`order_engine.py:1320~1328`)는 보정 INSERT 를 하지
    않으므로 UNIQUE 위반이 발생하지 않는다. 즉 **이 결함은 전량 체결(또는 그 통보로
    `total_filled >= ordered_qty` 가 되는 통보) 축에서만 발현**한다.
    ⚠️ 다만 그 행은 PENDING 으로 남는다(`update_trade_status` 가 PENDING 행을 찾지
    못해 affected=0) — 별건 후속, 명세 §6 참조.
    """
    env.injector.armed = True
    env.injector.fill_ratio = 0.5

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)
    await asyncio.sleep(0)

    order_no = env.injector.fired_order_no
    rows = env.db.rows_for(TICKER, order_no, TradeType.BUY)
    assert len(rows) == 1
