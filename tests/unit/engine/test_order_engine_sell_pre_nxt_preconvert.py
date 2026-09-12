"""execute_sell — NXT 프리 시장가 매도 사전 지정가 변환 (매수 PR-F 대칭).

## 배경 (2026-08-06)

프리장 시장가 매도는 KIS 가 100% 거부한다(APBK0918 "[프리마켓] 시장가 매매 불가").
매수는 PR-F(2026-05-15)가 `place_order` 직전 `step_up` 지정가로 사전 변환해
거부 자체를 막았는데 **매도에는 대칭 코드가 없었다**. 실측: 07-30 LTV
지엔씨에너지 당일 손절이 08:27 거부 → 09:00 까지 지연(손절선 ~29,780 →
체결 29,050).

risk 게이트(`test_risk_pre_market_exit_gate.py`)가 LTV 외 전략의 프리장 매도를
원천 차단하므로, 이 변환의 실효 대상은 **LTV**(프리장 매매가 설계 의도)다.
구조적으로는 미래의 어떤 프리장 매도도 거부 대신 지정가로 나가게 하는 방어선.

## 계약 (매수 PR-F 와 대칭)

- 조건: `PRE_NXT ∈ active AND MAIN ∉ active` + exchange NXT/SOR + 시장가 매도
- 변환: `step_down(current_price, 5)` 지정가 — 매도는 호가 깊이로 **내려** 체결률 확보
- 현재가 미수신(0) → 변환하지 않고 기존 시장가 경로(거부 → market_closed 보류가 안전망)
- 명시적 `limit_price > 0` 지정가 매도는 이미 지정가 — 미접촉
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.order_engine import OrderEngine
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.engine.util.tick_size import step_down

pytestmark = pytest.mark.unit


class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id="long_tail_volatility"):
        super().__init__(StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=0.1))

    async def prepare(self):
        pass

    def check_buy_signal(self, *a):
        return Signal.NONE

    def check_exit_signal(self, *a):
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


def _success_result(order_no: str):
    r = MagicMock()
    r.order_no = order_no
    return r


@pytest.fixture
def registry():
    reg = StrategyRegistry()
    strat = _DummyStrategy()
    reg.register(strat)
    strat.state.positions["119850"] = Position(
        ticker="119850", buy_price=30_700, quantity=1, order_no="O",
        strategy_id="long_tail_volatility", buy_date=date(2026, 7, 30),
    )
    return reg


@pytest.fixture
def engine(registry):
    return OrderEngine(registry)


@pytest.fixture
def mock_place_order(monkeypatch):
    mock = AsyncMock(return_value=_success_result("SELL-PRECONV-1"))
    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


@pytest.fixture
def mock_io(monkeypatch):
    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock())
    monkeypatch.setattr(_oe, "write_log", AsyncMock())
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock())


@pytest.fixture
def _active(monkeypatch):
    def _set(boards):
        monkeypatch.setattr(session_tracker, "_active", frozenset(boards))
    return _set


@pytest.fixture
def _exchange_nxt(monkeypatch):
    async def _fake(self, strategy_id, *, ticker=None, side="sell"):
        return "NXT"
    monkeypatch.setattr(OrderEngine, "_strategy_exchange_async", _fake)


@pytest.fixture
def _price(monkeypatch):
    def _set(price):
        from src.engine import scanner
        monkeypatch.setitem(scanner.ticker_prices, "119850", {"current_price": price})
    return _set


@pytest.mark.asyncio
async def test_pre_nxt_market_sell_preconverts_to_limit(
    engine, mock_place_order, mock_io, _active, _exchange_nxt, _price,
):
    """프리장 단독 + NXT + 시장가 → `step_down(현재가,5)` 지정가 발사."""
    _active({MarketBoard.PRE_NXT})
    _price(29_800)

    await engine.execute_sell("119850", Signal.STOP_LOSS, "long_tail_volatility")

    call = mock_place_order.await_args.kwargs
    assert str(call["order_division"]).endswith("LIMIT") or "LIMIT" in str(call["order_division"]).upper()
    assert call["price"] == step_down(29_800, steps=5)


@pytest.mark.asyncio
async def test_main_active_keeps_market_sell(
    engine, mock_place_order, mock_io, _active, _exchange_nxt, _price,
):
    """09:00 이후(MAIN 활성)는 기존 시장가 그대로 — byte 동일."""
    _active({MarketBoard.PRE_NXT, MarketBoard.MAIN})
    _price(29_800)

    await engine.execute_sell("119850", Signal.STOP_LOSS, "long_tail_volatility")

    call = mock_place_order.await_args.kwargs
    assert "MARKET" in str(call["order_division"]).upper()
    assert call["price"] == 0


@pytest.mark.asyncio
async def test_krx_exchange_keeps_market_sell(
    engine, mock_place_order, mock_io, _active, _price, monkeypatch,
):
    """KRX 라우팅은 변환 대상 아님 (프리장 KRX 주문은 다른 규약)."""
    async def _krx(self, strategy_id, *, ticker=None, side="sell"):
        return "KRX"
    monkeypatch.setattr(OrderEngine, "_strategy_exchange_async", _krx)
    _active({MarketBoard.PRE_NXT})
    _price(29_800)

    await engine.execute_sell("119850", Signal.STOP_LOSS, "long_tail_volatility")

    call = mock_place_order.await_args.kwargs
    assert "MARKET" in str(call["order_division"]).upper()


@pytest.mark.asyncio
async def test_missing_price_falls_back_to_market(
    engine, mock_place_order, mock_io, _active, _exchange_nxt,
):
    """현재가 미수신 → 변환 불가 → 기존 시장가 경로 (거부 → 보류가 안전망).

    임의 가격으로 지정가를 만들면 안 된다 — 잘못된 가격의 지정가가 더 위험.
    """
    _active({MarketBoard.PRE_NXT})

    await engine.execute_sell("119850", Signal.STOP_LOSS, "long_tail_volatility")

    call = mock_place_order.await_args.kwargs
    assert "MARKET" in str(call["order_division"]).upper()


@pytest.mark.asyncio
async def test_empty_session_keeps_market_sell(
    engine, mock_place_order, mock_io, _active, _exchange_nxt, _price,
):
    """세션 미확정(단위 테스트 기본 = 빈 frozenset) → 무변환 (기존 테스트 무영향 계약)."""
    _active(set())
    _price(29_800)

    await engine.execute_sell("119850", Signal.STOP_LOSS, "long_tail_volatility")

    call = mock_place_order.await_args.kwargs
    assert "MARKET" in str(call["order_division"]).upper()


def test_buy_side_pr_f_untouched():
    """매수측 PR-F(step_up 변환)는 이 작업으로 변경되지 않는다."""
    import inspect

    src = inspect.getsource(OrderEngine.execute_buy)
    assert "market_order_preconvert_pre_nxt" in src
    assert "step_up" in src
