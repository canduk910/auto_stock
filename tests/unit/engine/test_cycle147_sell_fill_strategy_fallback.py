"""사이클 147 Red — _handle_sell_fill strategy 폴백 race + 보정 INSERT UniqueViolation 시정.

## 사고 영역 (Supabase MCP READ-ONLY 진단 확정)

005940 NH투자증권 LTV SELL trade_history PENDING ~6h 영구 잔존 사고.

- 6/16 08:00:33 LTV `_execute_next_day_clear` NXT 지정가 33,250 청산 → order_no=0000004700 + 매핑 dict 등록 + insert_trade(SELL, PENDING, strategy="long_tail_volatility")
- 6/16 09:09 KIS reboot → Python process 재기동 → `_order_qty/_order_strategy/_order_ticker` 메모리 dict clear
- 6/16 09:18:06 KRX 체결통보 도착 → `_handle_sell_fill` 진입 → `_order_strategy.get(order_no, "momentum")` = "momentum" (잘못된 폴백)
- `_handle_sell_fill(strategy_id="momentum")` → momentum positions miss → "포지션 없음 손익 계산 생략" WARNING + `update_trade_status(strategy="momentum")` PENDING row strategy="long_tail_volatility" 미매칭 → affected=0
- 보정 INSERT `strategy="momentum"` → 사이클 30 UNIQUE `(ticker, order_no, trade_type)` → 이미 PENDING row 존재 → UniqueViolation → callback_exception → handler.py raise → 재연결 trigger
- 결과: PENDING row strategy="long_tail_volatility" 영구 잔존 (~6h+)

## 시정 영역

영역 1 (HIGH): `_handle_sell_fill` strategy 영역 = trade_history PENDING row 폴백 (order_no 단일 키)
영역 2 (MEDIUM): `_handle_buy_fill` 동일 패턴 영구 방어
영역 3 (HIGH): 보정 INSERT UniqueViolation → `_update_trade_status_by_order_no` 강제 COMPLETED UPDATE (strategy 무관)

## 회귀 가드 영역

- G-147-FALLBACK-1 (HIGH): _order_strategy miss + trade_history LTV PENDING → LTV 복구
- G-147-FALLBACK-2 (HIGH): _order_strategy miss + trade_history miss → "momentum" 최종 폴백 + WARNING
- G-147-FALLBACK-3: _order_strategy hit → trade_history 호출 0건
- G-147-UNIQUE-1 (HIGH): affected=0 + 보정 INSERT UniqueViolation → order_no 단일 키 UPDATE
- G-147-005940-REPRO: 005940 시나리오 통합 재현 → 최종 COMPLETED + strategy="long_tail_volatility" 영속
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

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
# 더미 전략 — 사이클 147 5 케이스 공용
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
    """005940 LTV 영역 강제 영구 영속 (사고 정합)."""
    reg = StrategyRegistry()
    # momentum (잘못된 폴백 결과 strategy)
    reg.register(_DummyStrategy(strategy_id="momentum"))
    # long_tail_volatility (PENDING row 영역 정합 strategy)
    ltv = _DummyStrategy(strategy_id="long_tail_volatility")
    reg.register(ltv)
    return reg


@pytest.fixture
def engine(registry: StrategyRegistry) -> OrderEngine:
    eng = OrderEngine(registry)
    # 005940 사고 시점 = LTV positions 영역에서 delete_position 이미 처리됨 (reboot 후 미복구)
    # → _handle_sell_fill 진입 시 양 strategy positions 영역 모두 005940 미존재
    return eng


@pytest.fixture
def mock_insert_trade(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "insert_trade", mock)
    return mock


@pytest.fixture
def mock_delete_position(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """delete_position 영역 lazy import 영역 patch (src.db.positions 모듈)."""
    mock = AsyncMock(return_value=None)
    import src.db.positions as _positions

    monkeypatch.setattr(_positions, "delete_position", mock)
    return mock


@pytest.fixture
def mock_unsubscribe(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """_unsubscribe_if_no_other_strategy 영역 분리 (kis_ws_pool 의존성 회피)."""
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._unsubscribe_if_no_other_strategy",
        mock,
    )
    return mock


# ---------------------------------------------------------------------------
# G-147-FALLBACK-1 (HIGH) — _order_strategy miss + trade_history LTV PENDING 폴백
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G147_FALLBACK_1_HIGH_lookup_from_trade_history(
    engine: OrderEngine,
    registry: StrategyRegistry,
    mock_insert_trade: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_unsubscribe: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """매핑 dict miss 영역 → trade_history PENDING row 영역 영구 영속 strategy 복구."""
    # _lookup_strategy_from_trade_history 영역 = "long_tail_volatility" 반환 (PENDING row 영속)
    mock_lookup = AsyncMock(return_value="long_tail_volatility")
    monkeypatch.setattr(
        "src.engine.order_engine._lookup_strategy_from_trade_history",
        mock_lookup,
    )
    # update_trade_status 영역 = 1건 매칭 (LTV strategy 정합 영구 영속)
    mock_update = AsyncMock(return_value=1)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", mock_update)

    # _order_strategy 영역 dict miss (reboot 영역 시뮬레이션)
    assert "0000004700" not in engine._order_strategy

    import logging

    with caplog.at_level(logging.INFO):
        await engine.handle_execution_notice(
            ticker="005940",
            order_no="0000004700",
            side="SELL",
            price=33250,
            quantity=1,
        )

    # G-147-FALLBACK-1-A: trade_history lookup 1회 호출
    mock_lookup.assert_awaited_once_with("005940", "0000004700", TradeType.SELL)
    # G-147-FALLBACK-1-B: update_trade_status strategy="long_tail_volatility" 영속
    mock_update.assert_awaited()
    update_call_kwargs = mock_update.await_args.kwargs
    update_call_args = mock_update.await_args.args
    # strategy 영역 = positional or kwarg
    strategy_arg = update_call_kwargs.get("strategy")
    if strategy_arg is None and len(update_call_args) >= 4:
        strategy_arg = update_call_args[3]
    assert strategy_arg == "long_tail_volatility", (
        f"LTV 복구 영역 영구 영속 의무: strategy_arg={strategy_arg}"
    )
    # G-147-FALLBACK-1-C: [sell_fill_strategy_lookup_recovered] INFO emit
    assert any(
        "sell_fill_strategy_lookup_recovered" in r.getMessage()
        and "long_tail_volatility" in r.getMessage()
        for r in caplog.records
    ), "복구 영역 INFO emit 영구 영속 의무"


# ---------------------------------------------------------------------------
# G-147-FALLBACK-2 (HIGH) — _order_strategy miss + trade_history miss → momentum 최종 폴백
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G147_FALLBACK_2_HIGH_lookup_miss_momentum_final(
    engine: OrderEngine,
    mock_insert_trade: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_unsubscribe: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """매핑 dict miss + trade_history miss = 수동 매매 사전 등 → momentum 최종 폴백 + WARNING."""
    mock_lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.engine.order_engine._lookup_strategy_from_trade_history",
        mock_lookup,
    )
    mock_update = AsyncMock(return_value=1)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", mock_update)

    import logging

    with caplog.at_level(logging.WARNING):
        await engine.handle_execution_notice(
            ticker="999999",
            order_no="UNKNOWN-001",
            side="SELL",
            price=10000,
            quantity=1,
        )

    # G-147-FALLBACK-2-A: lookup 호출 영구 영속
    mock_lookup.assert_awaited_once()
    # G-147-FALLBACK-2-B: [sell_fill_strategy_lookup_fallback] WARNING emit
    assert any(
        "sell_fill_strategy_lookup_fallback" in r.getMessage()
        for r in caplog.records
    ), "최종 폴백 영역 WARNING emit 영구 영속 의무"
    # G-147-FALLBACK-2-C: update_trade_status strategy="momentum" 영속
    update_call_kwargs = mock_update.await_args.kwargs
    update_call_args = mock_update.await_args.args
    strategy_arg = update_call_kwargs.get("strategy")
    if strategy_arg is None and len(update_call_args) >= 4:
        strategy_arg = update_call_args[3]
    assert strategy_arg == "momentum"


# ---------------------------------------------------------------------------
# G-147-FALLBACK-3 — _order_strategy hit 정상 영역 → trade_history 호출 0건
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G147_FALLBACK_3_order_strategy_hit_no_lookup(
    engine: OrderEngine,
    registry: StrategyRegistry,
    mock_insert_trade: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_unsubscribe: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """정상 매핑 dict 영역 hit → trade_history fallback 영역 호출 안 함 (성능 영역)."""
    # 매핑 dict 영역에 직접 등록 (정상 영역)
    engine._order_strategy["ORDER-NORMAL"] = "long_tail_volatility"
    engine._order_ticker["ORDER-NORMAL"] = "005940"
    engine._order_qty["ORDER-NORMAL"] = 1

    # LTV positions 영역에 005940 등록 (정상 매도)
    ltv = registry.get("long_tail_volatility")
    ltv.state.positions["005940"] = Position(
        ticker="005940",
        buy_price=30000,
        quantity=1,
        order_no="ORDER-PRE",
        strategy_id="long_tail_volatility",
        buy_date=date.today(),
    )

    mock_lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.engine.order_engine._lookup_strategy_from_trade_history",
        mock_lookup,
    )
    mock_update = AsyncMock(return_value=1)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", mock_update)

    await engine.handle_execution_notice(
        ticker="005940",
        order_no="ORDER-NORMAL",
        side="SELL",
        price=33250,
        quantity=1,
    )

    # G-147-FALLBACK-3-A: trade_history lookup 영역 호출 0건 (성능 영역)
    mock_lookup.assert_not_awaited()
    # G-147-FALLBACK-3-B: update_trade_status strategy="long_tail_volatility" 영속
    update_call_kwargs = mock_update.await_args.kwargs
    update_call_args = mock_update.await_args.args
    strategy_arg = update_call_kwargs.get("strategy")
    if strategy_arg is None and len(update_call_args) >= 4:
        strategy_arg = update_call_args[3]
    assert strategy_arg == "long_tail_volatility"


# ---------------------------------------------------------------------------
# G-147-UNIQUE-1 (HIGH) — affected=0 + 보정 INSERT UniqueViolation → order_no UPDATE
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G147_UNIQUE_1_HIGH_correction_insert_unique_violation(
    engine: OrderEngine,
    mock_delete_position: AsyncMock,
    mock_unsubscribe: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """보정 INSERT UniqueViolation = 005940 사고 정합 영구 영속 → strategy 무관 강제 COMPLETED UPDATE."""
    # 매핑 dict 영역 hit (정상) — 하지만 update_trade_status affected=0 (PENDING row strategy 불일치 시뮬레이션)
    engine._order_strategy["0000004700"] = "momentum"  # 잘못된 strategy (사고 시점 폴백)
    engine._order_ticker["0000004700"] = "005940"
    engine._order_qty["0000004700"] = 1

    mock_update = AsyncMock(return_value=0)  # PENDING row strategy 불일치 → affected=0
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", mock_update)

    # 보정 INSERT 영역 = UniqueViolation 영역 시뮬레이션 (사이클 30 UNIQUE 인덱스)
    mock_insert = AsyncMock(
        side_effect=Exception("duplicate key value violates unique constraint")
    )
    monkeypatch.setattr("src.engine.order_engine.insert_trade", mock_insert)

    # _update_trade_status_by_order_no 영역 신규 헬퍼 = 1건 매칭 (order_no 단일 키 영구 영속)
    mock_update_by_order = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "src.engine.order_engine._update_trade_status_by_order_no",
        mock_update_by_order,
    )

    import logging

    with caplog.at_level(logging.WARNING):
        await engine.handle_execution_notice(
            ticker="005940",
            order_no="0000004700",
            side="SELL",
            price=33250,
            quantity=1,
        )

    # G-147-UNIQUE-1-A: 보정 INSERT 1회 호출 영구 영속
    mock_insert.assert_awaited()
    # G-147-UNIQUE-1-B: UniqueViolation 후 강제 UPDATE 영역 1회 호출
    mock_update_by_order.assert_awaited_once()
    call_args = mock_update_by_order.await_args
    # order_no positional or kwarg
    if "order_no" in call_args.kwargs:
        assert call_args.kwargs["order_no"] == "0000004700"
    else:
        assert call_args.args[0] == "0000004700"
    # G-147-UNIQUE-1-C: [sell_fill_correction_unique_violation] WARNING emit
    assert any(
        "sell_fill_correction_unique_violation" in r.getMessage()
        for r in caplog.records
    ), "UniqueViolation 영역 WARNING emit 영구 영속 의무"


# ---------------------------------------------------------------------------
# G-147-005940-REPRO — 005940 시나리오 통합 재현 (HIGH 매매 안전성 직접 검증)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G147_005940_REPRO_full_scenario(
    engine: OrderEngine,
    registry: StrategyRegistry,
    mock_insert_trade: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_unsubscribe: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """005940 NH투자증권 사고 시나리오 영역 영구 영속 통합 재현.

    조건:
    - LTV strategy 영역에 005940 보유 (사고 시점 = delete_position 이미 처리됨, 그러나 시나리오 단순화)
    - _order_qty/_order_strategy/_order_ticker 영역 모두 dict miss (reboot 영역 시뮬레이션)
    - trade_history PENDING row strategy="long_tail_volatility" 영속

    영역 영구 영속 의무:
    - trade_history lookup → "long_tail_volatility" 복구
    - update_trade_status strategy="long_tail_volatility" 영속 → affected=1
    - 보정 INSERT 호출 0건 (affected≥1 영역 영속)
    """
    # 매핑 dict 영역 = miss (reboot 시뮬레이션)
    assert "0000004700" not in engine._order_strategy
    assert "0000004700" not in engine._order_ticker

    # trade_history lookup 영역 = LTV 복구
    mock_lookup = AsyncMock(return_value="long_tail_volatility")
    monkeypatch.setattr(
        "src.engine.order_engine._lookup_strategy_from_trade_history",
        mock_lookup,
    )

    # update_trade_status 영역 = LTV strategy 정합 매칭 1건
    mock_update = AsyncMock(return_value=1)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", mock_update)

    await engine.handle_execution_notice(
        ticker="005940",
        order_no="0000004700",
        side="SELL",
        price=33250,
        quantity=1,
    )

    # G-147-005940-A: LTV 복구 영구 영속
    mock_lookup.assert_awaited_once_with("005940", "0000004700", TradeType.SELL)
    # G-147-005940-B: update_trade_status strategy="long_tail_volatility" 정합
    update_call_kwargs = mock_update.await_args.kwargs
    update_call_args = mock_update.await_args.args
    strategy_arg = update_call_kwargs.get("strategy")
    if strategy_arg is None and len(update_call_args) >= 4:
        strategy_arg = update_call_args[3]
    assert strategy_arg == "long_tail_volatility"
    # G-147-005940-C: 보정 INSERT 호출 0건 (affected=1 영속)
    mock_insert_trade.assert_not_awaited()
    # G-147-005940-D: sold_today LTV 영역 영속 (005940 영속 영역)
    ltv = registry.get("long_tail_volatility")
    assert "005940" in ltv.state.sold_today, (
        "LTV sold_today 영역 영구 영속 의무 (재매수 차단 영역 정합)"
    )
