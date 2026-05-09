"""통합 테스트용 공용 fixture.

OrderEngine + RiskManager + 4개 전략을 등록한 environment 를 제공한다.
외부 의존성(KIS API, Supabase, scanner 전역)은 모두 모킹하고
호출 인자를 ``calls`` 추적기에 누적해 어설션에 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from types import SimpleNamespace
from typing import Any

import pytest

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.risk import RiskManager
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.balance import BuyableInfo
from src.models.order import OrderResult, OrderSide


# ---------------------------------------------------------------------------
# 호출 추적기
# ---------------------------------------------------------------------------
@dataclass
class CallTracker:
    place_order: list = field(default_factory=list)
    cancel_order: list = field(default_factory=list)
    insert_trade: list = field(default_factory=list)
    update_trade_status: list = field(default_factory=list)
    save_position: list = field(default_factory=list)
    delete_position: list = field(default_factory=list)
    get_buyable: list = field(default_factory=list)
    system_logs: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# 동적 응답/오류 제어 상태
# ---------------------------------------------------------------------------
@dataclass
class EnvState:
    next_buy_seq: count = field(default_factory=lambda: count(1))
    next_sell_seq: count = field(default_factory=lambda: count(1))
    update_status_affected: int = 1   # 0 으로 두면 race 시나리오 (COMPLETED 직접 INSERT 발생)
    buyable_max_qty: int = 999
    buyable_max_amount: int = 999_000_000
    buyable_cash: int = 999_000_000
    place_order_error: KisApiError | None = None  # 한번 던지고 자동 클리어
    place_order_raises_persist: bool = False
    get_buyable_error: KisApiError | None = None


# ---------------------------------------------------------------------------
# 메인 fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def order_env(monkeypatch):
    """OrderEngine + RiskManager + 4 전략 + 외부 의존성 모킹."""

    # scanner 전역 dict 격리
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자", "000660": "SK하이닉스"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 70000, "000660": 100000})
    monkeypatch.setattr(scanner, "ticker_prices", {})

    # session_tracker 격리
    from src.engine.session import session_tracker, MarketBoard
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))

    registry = StrategyRegistry()

    # 4 전략 등록
    momentum = MomentumStrategy(StrategyConfig(strategy_id="momentum", name="모멘텀", weight=0.4))
    vb = VolatilityBreakoutStrategy(StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3))
    ltv = LongTailVolatilityStrategy(StrategyConfig(strategy_id="long_tail_volatility", name="LTV", weight=0.2))
    donchian = DonchianSwingStrategy(StrategyConfig(strategy_id="donchian_swing", name="Donchian", weight=0.1))
    for s in (momentum, vb, ltv, donchian):
        registry.register(s)
    registry.allocate_funds(total_asset=100_000_000)

    engine = OrderEngine(registry)
    risk = RiskManager(registry, engine)
    calls = CallTracker()
    state = EnvState()

    # ---- KIS API 모킹 ----
    async def fake_place_order(ticker, side, quantity, price=0, **kwargs):
        calls.place_order.append({
            "ticker": ticker, "side": side, "quantity": quantity, "price": price,
            "exchange": kwargs.get("exchange", "KRX"),
        })
        if state.place_order_error is not None:
            err = state.place_order_error
            if not state.place_order_raises_persist:
                state.place_order_error = None
            raise err
        seq = next(state.next_buy_seq) if side == OrderSide.BUY else next(state.next_sell_seq)
        prefix = "BUY" if side == OrderSide.BUY else "SELL"
        return OrderResult(order_no=f"{prefix}-{seq:06d}", order_time="153012", krx_org_no="00950")

    async def fake_cancel_order(*args, **kwargs):
        calls.cancel_order.append({"args": args, "kwargs": kwargs})
        return OrderResult(order_no="CXL-00001", order_time="153100", krx_org_no="00950")

    async def fake_get_buyable(ticker, price):
        calls.get_buyable.append({"ticker": ticker, "price": price})
        if state.get_buyable_error is not None:
            err = state.get_buyable_error
            state.get_buyable_error = None
            raise err
        return BuyableInfo(
            cash_available=state.buyable_cash,
            max_buy_amount=state.buyable_max_amount,
            max_buy_quantity=state.buyable_max_qty,
        )

    monkeypatch.setattr("src.engine.order_engine.place_order", fake_place_order)
    monkeypatch.setattr("src.engine.order_engine.cancel_order", fake_cancel_order)
    monkeypatch.setattr("src.engine.order_engine.get_buyable", fake_get_buyable)

    # ---- DB 모킹 ----
    async def fake_insert_trade(record):
        calls.insert_trade.append(record)

    async def fake_update_trade_status(ticker, trade_type, status, strategy=None, price=None, profit_loss=None):
        calls.update_trade_status.append({
            "ticker": ticker, "trade_type": trade_type, "status": status,
            "strategy": strategy, "price": price, "profit_loss": profit_loss,
        })
        return state.update_status_affected

    async def fake_save_position(ticker, ticker_name, buy_price, quantity, order_no, strategy_id, buy_date):
        calls.save_position.append({
            "ticker": ticker, "buy_price": buy_price, "quantity": quantity,
            "order_no": order_no, "strategy_id": strategy_id,
        })

    async def fake_delete_position(ticker):
        calls.delete_position.append({"ticker": ticker})

    async def fake_write_log(level, message):
        calls.system_logs.append({"level": level, "message": message})

    monkeypatch.setattr("src.engine.order_engine.insert_trade", fake_insert_trade)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", fake_update_trade_status)
    monkeypatch.setattr("src.engine.order_engine.write_log", fake_write_log)
    # _handle_buy_fill 안에서 동적 import 되는 save_position
    import src.db.positions as positions_mod
    monkeypatch.setattr(positions_mod, "save_position", fake_save_position)
    monkeypatch.setattr(positions_mod, "delete_position", fake_delete_position)

    # ---- _schedule_cancel/_schedule_cancel_and_reorder 의 background task 무력화 ----
    # asyncio.create_task 안의 30초 sleep 이 테스트를 늦추므로, 단순히 task 만 생성하고
    # 실제 wait 는 패치된 sleep 으로 즉시 진행되도록.
    monkeypatch.setattr("src.engine.order_engine.PARTIAL_FILL_WAIT", 0)

    return SimpleNamespace(
        registry=registry, engine=engine, risk=risk, calls=calls, state=state,
        momentum=momentum, vb=vb, ltv=ltv, donchian=donchian,
    )


@pytest.fixture
def kis_error():
    """KisApiError 인스턴스 팩토리."""

    def _make(code: str = "APBK0919", msg: str = "주문가능금액이 부족합니다."):
        return KisApiError(rt_cd="1", msg_cd=code, msg1=msg)

    return _make


# ---------------------------------------------------------------------------
# Scheduler fixture — Phase D
# ---------------------------------------------------------------------------
@dataclass
class SchedulerCalls:
    execute_sell: list = field(default_factory=list)
    write_log: list = field(default_factory=list)
    ws_subscribe: list = field(default_factory=list)
    fetch_stock_detail: list = field(default_factory=list)
    on_open_price_confirmed: list = field(default_factory=list)


@pytest.fixture
def scheduler_env(monkeypatch):
    """TradingScheduler 인스턴스 + 외부 의존성 모킹.

    scheduler 가 자체적으로 4개 전략 + OrderEngine + RiskManager 를 생성하므로
    그것들을 그대로 사용하고, 외부 호출(write_log/kis_ws/execute_sell/fetch_stock_detail)만
    가짜로 치환한다.
    """
    from src.engine import scanner
    from src.engine.scheduler import TradingScheduler
    from src.engine.session import MarketBoard, session_tracker

    # scanner 전역 dict 격리
    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자", "000660": "SK하이닉스"})
    monkeypatch.setattr(scanner, "ticker_prices", {})
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 70000, "000660": 100000})
    monkeypatch.setattr(scanner, "ticker_market_info", {})

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))

    sched = TradingScheduler()
    calls = SchedulerCalls()

    # write_log 호출 추적
    async def fake_write_log(level, message):
        calls.write_log.append({"level": level, "message": message})

    monkeypatch.setattr("src.engine.scheduler.write_log", fake_write_log)

    # kis_ws.subscribe 호출 추적
    async def fake_subscribe(tr_id, tr_key):
        calls.ws_subscribe.append({"tr_id": tr_id, "tr_key": tr_key})

    monkeypatch.setattr("src.engine.scheduler.kis_ws", SimpleNamespace(subscribe=fake_subscribe))

    # OrderEngine.execute_sell 호출 추적
    async def fake_execute_sell(ticker, signal, strategy_id):
        calls.execute_sell.append({"ticker": ticker, "signal": signal, "strategy_id": strategy_id})
        # 메모리 포지션 제거 (정상 매도 시뮬)
        strat = sched.registry.get(strategy_id)
        if strat:
            strat.state.positions.pop(ticker, None)
            strat.state.sold_today.add(ticker)

    sched.order_engine.execute_sell = fake_execute_sell

    # asyncio.sleep 무력화 (NEXT_DAY_STABILIZE_SECS 등)
    async def no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr("src.engine.scheduler.asyncio", SimpleNamespace(
        sleep=no_sleep, Task=__import__("asyncio").Task,
    ))

    return SimpleNamespace(scheduler=sched, calls=calls, monkeypatch=monkeypatch)
