"""사이클 161 Red — `_handle_buy_fill` 체결단가 정합 시정.

## 사고 (사용자 보고 2026-06-16 005940)

- 005940 NH투자증권 BUY trade_history.price = 33,400원 + HTS 실제 체결 33,350원 (+50원 차이)
- 근본 원인 = `_handle_buy_fill` 의 `update_trade_status(BUY, COMPLETED, strategy=strategy_id)` 호출 시 `price` 인자 누락
  → PENDING INSERT 시점 `record_price` (주문가 LIMIT or scanner `current_price` MARKET) 잔존
  → 체결단가 (`CNTG_UNPR`, KIS 정본 H0STCNI0 idx 10) 미반영

## KIS MCP 정본 (사이클 161 검증)

- 체결통보 H0STCNI0 26 컬럼: `CNTG_UNPR` (체결단가, idx 10) = 실제 체결가
- `src/realtime/handler.py:166` = `price = int(fields[10])` 정합
- `_handle_buy_fill(price=...)` 인자 = 체결단가

## 시정 (Green)

- `_handle_buy_fill` 의 `update_trade_status(BUY, COMPLETED, strategy=strategy_id, price=price)` 추가
- 보정 INSERT UniqueViolation 시 `_update_trade_status_by_order_no(price=price)` 강제 UPDATE
  (사이클 147 `_handle_sell_fill` 패턴 100% 답습)

## 회귀 가드

- G-161-K-1 (HIGH): `_handle_buy_fill` 전량 체결 → `update_trade_status` price 인자 명시
- G-161-K-2 (HIGH): trade_history.price = CNTG_UNPR (체결단가)
- G-161-K-3: 보정 INSERT UniqueViolation → 강제 UPDATE (사이클 147 패턴)
- G-161-K-4: 부분 체결 (PARTIAL) BUY price 인자 명시
- G-161-K-5 (HIGH): `_handle_sell_fill` price 인자 보존 (회귀 0)
- G-161-K-6: AST 정적 가드 = `_handle_buy_fill` 의 `update_trade_status` 호출 시 `price=` keyword 의무
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import (
    Position,
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 더미 전략 — 사이클 161 공용
# ---------------------------------------------------------------------------
class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = "momentum") -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id,
                name=f"{strategy_id}-dummy",
                enabled=True,
                weight=1.0,
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

    def calc_buy_quantity(self, current_price: int) -> int:
        return 0


@pytest.fixture
def registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    reg.register(_DummyStrategy(strategy_id="momentum"))
    reg.register(_DummyStrategy(strategy_id="long_tail_volatility"))
    return reg


@pytest.fixture
def engine(registry: StrategyRegistry) -> OrderEngine:
    return OrderEngine(registry)


@pytest.fixture
def mock_insert_trade(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "insert_trade", mock)
    return mock


@pytest.fixture
def mock_save_position(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """save_position lazy import patch."""
    mock = AsyncMock(return_value=None)
    import src.db.positions as _positions

    monkeypatch.setattr(_positions, "save_position", mock)
    return mock


# ---------------------------------------------------------------------------
# G-161-K-1 (HIGH) — `_handle_buy_fill` update_trade_status price 인자 명시
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G161_K_1_HIGH_buy_fill_update_with_price(
    engine: OrderEngine,
    registry: StrategyRegistry,
    mock_insert_trade: AsyncMock,
    mock_save_position: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """전량 체결 시 update_trade_status 호출에 `price=체결단가` 인자.

    005940 BUY 사고 정합 = scanner current_price 33,400원 매수 → 체결단가 33,350원
    → trade_history.price = 33,350원 (UPDATE 시점 체결단가 반영).
    """
    mock_update = AsyncMock(return_value=1)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", mock_update)

    order_no = "0000004701"
    # 매핑 dict 사전 등록 (정상 케이스 — 사이클 147 폴백 미진입)
    engine._order_qty[order_no] = 10
    engine._order_strategy[order_no] = "long_tail_volatility"
    engine._order_ticker[order_no] = "005940"

    # 체결단가 33,350원, 수량 10주
    await engine.handle_execution_notice(
        ticker="005940",
        order_no=order_no,
        side="BUY",
        price=33_350,
        quantity=10,
    )

    # update_trade_status = price=33_350 인자 검증
    assert mock_update.await_count >= 1
    # COMPLETED 분기 호출에 price 인자 명시 의무
    completed_calls = [
        c
        for c in mock_update.await_args_list
        if c.args and len(c.args) >= 3 and c.args[2] == TradeStatus.COMPLETED
    ]
    assert len(completed_calls) >= 1, "COMPLETED 호출 부재"
    completed_kwargs = completed_calls[0].kwargs
    assert "price" in completed_kwargs, (
        "G-161-K-1: update_trade_status(BUY, COMPLETED) 호출에 price 인자 누락 — 사이클 161 시정 의무"
    )
    assert completed_kwargs["price"] == 33_350, (
        f"G-161-K-1: price 인자 값 = {completed_kwargs.get('price')} (기대=33,350 체결단가)"
    )


# ---------------------------------------------------------------------------
# G-161-K-2 (HIGH) — 체결단가가 trade_history.price 로 반영
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G161_K_2_HIGH_price_consistency_with_cntg_unpr(
    engine: OrderEngine,
    mock_insert_trade: AsyncMock,
    mock_save_position: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KIS CNTG_UNPR (체결단가) = trade_history.price.

    handler.py:166 = `price = int(fields[10])` = CNTG_UNPR 정합
    → `_handle_buy_fill(price=...)` 인자 → update_trade_status(price=...) chain.
    """
    mock_update = AsyncMock(return_value=1)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", mock_update)

    order_no = "0000004702"
    engine._order_qty[order_no] = 5
    engine._order_strategy[order_no] = "momentum"
    engine._order_ticker[order_no] = "005930"

    # KIS CNTG_UNPR = 71_500원 (체결단가)
    await engine.handle_execution_notice(
        ticker="005930",
        order_no=order_no,
        side="BUY",
        price=71_500,
        quantity=5,
    )

    completed_calls = [
        c
        for c in mock_update.await_args_list
        if c.args and len(c.args) >= 3 and c.args[2] == TradeStatus.COMPLETED
    ]
    assert len(completed_calls) >= 1
    assert completed_calls[0].kwargs.get("price") == 71_500


# ---------------------------------------------------------------------------
# G-161-K-3 — 보정 INSERT UniqueViolation 강제 UPDATE (사이클 147 패턴 답습)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G161_K_3_correction_unique_violation_forced_update(
    engine: OrderEngine,
    mock_save_position: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """보정 INSERT UniqueViolation 시 강제 UPDATE (사이클 147 sell_fill 패턴).

    update_trade_status affected=0 + insert_trade UniqueViolation chain
    → `_update_trade_status_by_order_no(price=체결단가)` 강제 UPDATE.
    """
    # affected=0 (PENDING row strategy 불일치)
    mock_update = AsyncMock(return_value=0)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", mock_update)

    # insert_trade UniqueViolation (사이클 30 부분 UNIQUE 인덱스)
    mock_insert = AsyncMock(side_effect=Exception("UniqueViolation"))
    monkeypatch.setattr("src.engine.order_engine.insert_trade", mock_insert)

    # `_update_trade_status_by_order_no` 강제 UPDATE
    mock_forced_update = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "src.engine.order_engine._update_trade_status_by_order_no",
        mock_forced_update,
    )

    order_no = "0000004703"
    engine._order_qty[order_no] = 3
    engine._order_strategy[order_no] = "long_tail_volatility"
    engine._order_ticker[order_no] = "005940"

    await engine.handle_execution_notice(
        ticker="005940",
        order_no=order_no,
        side="BUY",
        price=33_350,
        quantity=3,
    )

    # 강제 UPDATE 호출 검증
    assert mock_forced_update.await_count >= 1, (
        "G-161-K-3: 보정 INSERT UniqueViolation 후 _update_trade_status_by_order_no 호출 부재"
    )
    forced_kwargs = mock_forced_update.await_args_list[0].kwargs
    assert forced_kwargs.get("price") == 33_350, (
        "G-161-K-3: 강제 UPDATE price 인자 누락 (체결단가 정합 의무)"
    )


# ---------------------------------------------------------------------------
# G-161-K-4 — 부분 체결 (PARTIAL) BUY price 인자 명시
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G161_K_4_partial_buy_with_price(
    engine: OrderEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """부분 체결 BUY 의 update_trade_status(PARTIAL, price=체결단가)."""
    mock_update = AsyncMock(return_value=1)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", mock_update)

    # `_schedule_cancel` 호출 차단 (asyncio.create_task 회피)
    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._schedule_cancel",
        lambda *a, **kw: None,
    )

    order_no = "0000004704"
    engine._order_qty[order_no] = 10
    engine._order_strategy[order_no] = "momentum"
    engine._order_ticker[order_no] = "005940"

    # 5주만 체결 (부분 체결)
    await engine.handle_execution_notice(
        ticker="005940",
        order_no=order_no,
        side="BUY",
        price=33_350,
        quantity=5,
    )

    partial_calls = [
        c
        for c in mock_update.await_args_list
        if c.args and len(c.args) >= 3 and c.args[2] == TradeStatus.PARTIAL
    ]
    assert len(partial_calls) >= 1, "PARTIAL UPDATE 호출 부재"
    assert "price" in partial_calls[0].kwargs, (
        "G-161-K-4: PARTIAL BUY UPDATE 에 price 인자 누락"
    )
    assert partial_calls[0].kwargs["price"] == 33_350


# ---------------------------------------------------------------------------
# G-161-K-5 (HIGH) — `_handle_sell_fill` price 인자 보존 (회귀 0 보장)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G161_K_5_HIGH_sell_fill_price_preserved(
    engine: OrderEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_handle_sell_fill` price 인자 보존 (사이클 147 회귀 0 검증)."""
    mock_update = AsyncMock(return_value=1)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", mock_update)
    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._unsubscribe_if_no_other_strategy",
        AsyncMock(return_value=None),
    )
    import src.db.positions as _positions

    monkeypatch.setattr(_positions, "delete_position", AsyncMock(return_value=None))

    order_no = "0000004705"
    engine._order_qty[order_no] = 10
    engine._order_strategy[order_no] = "long_tail_volatility"
    engine._order_ticker[order_no] = "005940"

    # 매도 체결
    await engine.handle_execution_notice(
        ticker="005940",
        order_no=order_no,
        side="SELL",
        price=33_250,  # KIS CNTG_UNPR
        quantity=10,
    )

    completed_calls = [
        c
        for c in mock_update.await_args_list
        if c.args and len(c.args) >= 3 and c.args[2] == TradeStatus.COMPLETED
    ]
    assert len(completed_calls) >= 1
    # 사이클 147 = price + profit_loss 인자 모두 명시
    assert completed_calls[0].kwargs.get("price") == 33_250
    assert "profit_loss" in completed_calls[0].kwargs


# ---------------------------------------------------------------------------
# G-161-K-6 — AST 정적 가드 = `_handle_buy_fill` update_trade_status price keyword 의무
# ---------------------------------------------------------------------------
def test_G161_K_6_ast_buy_fill_update_has_price_keyword() -> None:
    """AST 정적 가드 = `_handle_buy_fill` 의 update_trade_status 호출 시 `price=` keyword 의무.

    미래 silent 결함 (price 인자 누락) 재발 차단.
    """
    source = Path("src/engine/order_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    # `_handle_buy_fill` async 함수 추출
    buy_fill_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_handle_buy_fill":
            buy_fill_func = node
            break

    assert buy_fill_func is not None, "`_handle_buy_fill` 함수 부재"

    # update_trade_status 호출 추출 (전체)
    update_calls = []
    for node in ast.walk(buy_fill_func):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "update_trade_status":
                update_calls.append(node)
            elif isinstance(func, ast.Attribute) and func.attr == "update_trade_status":
                update_calls.append(node)

    assert len(update_calls) >= 1, (
        "`_handle_buy_fill` 의 update_trade_status 호출 부재"
    )

    # 각 호출에 price keyword 명시 의무
    for call in update_calls:
        kwarg_names = [kw.arg for kw in call.keywords if kw.arg]
        assert "price" in kwarg_names, (
            f"G-161-K-6 AST: `_handle_buy_fill` 의 update_trade_status 호출 line={call.lineno} "
            f"price keyword 부재 → 사이클 161 시정 의무. "
            f"keywords={kwarg_names}"
        )


# ---------------------------------------------------------------------------
# G-161-SAFETY-1 (HIGH) — `_handle_sell_fill` 시그너처 보존 검증
# ---------------------------------------------------------------------------
def test_G161_SAFETY_1_HIGH_no_changes_to_hot_path() -> None:
    """매매 안전성 = order_engine 영역 시정만 + `_handle_sell_fill` 회귀 0.

    AST 정적 검증 = 사이클 147 핵심 chain 보존 (price 인자 + 강제 UPDATE).
    """
    sell_fill = inspect.getsource(OrderEngine._handle_sell_fill)
    assert "strategy_id" in sell_fill
    assert "price" in sell_fill
    # 사이클 147 강제 UPDATE chain 보존
    assert "_update_trade_status_by_order_no" in sell_fill or "forced_affected" in sell_fill
