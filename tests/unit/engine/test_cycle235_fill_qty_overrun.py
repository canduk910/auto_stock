"""cycle235 R2~R5 — 체결 수량 overrun 클램프 (257720 실사고 재현·방어).

주문수량 초과 체결은 물리적으로 불가 — 누적이 주문수량을 넘으면 파싱/중복 이상이다.
`_order_qty` 매핑이 있을 때만 클램프(수동/외부 주문의 ordered=quantity 폴백 경로는
다중 통보를 오캡하면 안 된다). BUY·SELL 공통 방어.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = "volatility_breakout") -> None:
        super().__init__(StrategyConfig(
            strategy_id=strategy_id, name=strategy_id, enabled=True,
            weight=1.0, params={"exchange": "KRX"},
        ))
        self.state.total_investment = 10_000_000

    async def prepare(self):
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 0


@pytest.fixture
def registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    reg.register(_DummyStrategy("volatility_breakout"))
    return reg


@pytest.fixture
def engine(registry: StrategyRegistry) -> OrderEngine:
    return OrderEngine(registry)


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch):
    import src.engine.order_engine as _oe
    import src.db.positions as _positions

    monkeypatch.setattr(_oe, "update_trade_status", AsyncMock(return_value=1))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_positions, "save_position", AsyncMock(return_value=None))
    monkeypatch.setattr(_positions, "delete_position", AsyncMock(return_value=None))
    monkeypatch.setattr(
        _oe, "_lookup_strategy_from_trade_history", AsyncMock(return_value=None))
    return _oe


def _arm(engine: OrderEngine, order_no: str, ticker: str, qty: int,
         strategy_id: str = "volatility_breakout") -> None:
    engine._order_qty[order_no] = qty
    engine._order_strategy[order_no] = strategy_id
    engine._order_ticker[order_no] = ticker


class TestR2Reproduce257720:
    @pytest.mark.asyncio
    async def test_overrun_notices_clamped_to_ordered(
        self, engine, registry, mock_db, caplog,
    ):
        """실사고 재현 — 주문 2주, 통보 quantity (1, 2) 오독 유입.

        현행: 1+2=3 → positions.quantity=3 → 익일 3주 매도 APBK0400.
        기대: ordered=2 로 클램프 + `[fill_qty_overrun]` WARNING + pos=2.
        """
        vb = registry.get("volatility_breakout")
        _arm(engine, "0000411400", "257720", 2)
        with caplog.at_level(logging.WARNING):
            await engine.handle_execution_notice(
                ticker="257720", order_no="0000411400", side="BUY",
                price=51_100, quantity=1)
            await engine.handle_execution_notice(
                ticker="257720", order_no="0000411400", side="BUY",
                price=51_000, quantity=2)
        pos = vb.state.positions.get("257720")
        assert pos is not None
        assert pos.quantity == 2, "주문수량 초과 누적이 positions 를 오염 (257720 실사고)"
        assert any("[fill_qty_overrun]" in r.message for r in caplog.records)


class TestR3NormalPartialFill:
    @pytest.mark.asyncio
    async def test_incremental_fills_no_overrun_warning(
        self, engine, registry, mock_db, caplog,
    ):
        vb = registry.get("volatility_breakout")
        _arm(engine, "0000000001", "005930", 2)
        with caplog.at_level(logging.WARNING):
            await engine.handle_execution_notice(
                ticker="005930", order_no="0000000001", side="BUY",
                price=70_000, quantity=1)
            assert vb.state.positions["005930"].quantity == 1
            await engine.handle_execution_notice(
                ticker="005930", order_no="0000000001", side="BUY",
                price=70_100, quantity=1)
        assert vb.state.positions["005930"].quantity == 2
        assert not [r for r in caplog.records if "[fill_qty_overrun]" in r.message]


class TestR4UnknownOrderNoClampExempt:
    @pytest.mark.asyncio
    async def test_fallback_ordered_qty_behavior_preserved(
        self, engine, registry, mock_db, caplog,
    ):
        """매핑 부재(`_order_qty` 미등록) — 클램프 미적용 + 기존 계약 보존.

        기존 계약: ordered=quantity 폴백이라 1차 통보가 곧 전량 처리되고
        2차는 P1-B 멱등 가드가 무시한다. 클램프가 이 경로에 개입해
        `[fill_qty_overrun]` 을 만들면 안 된다(폴백 ordered 는 신뢰 불가 값).
        """
        vb = registry.get("volatility_breakout")
        engine._order_ticker["0000000009"] = "005930"
        engine._order_strategy["0000000009"] = "volatility_breakout"
        # _order_qty 만 의도적으로 미등록 → ordered = quantity 폴백
        with caplog.at_level(logging.INFO):
            await engine.handle_execution_notice(
                ticker="005930", order_no="0000000009", side="BUY",
                price=70_000, quantity=1)
            await engine.handle_execution_notice(
                ticker="005930", order_no="0000000009", side="BUY",
                price=70_000, quantity=1)
        assert vb.state.positions["005930"].quantity == 1  # 1차 전량 처리 (기존 계약)
        assert any("[buy_fill_duplicate_ignored]" in r.message
                   for r in caplog.records)  # 2차 멱등 무시 (P1-B 보존)
        assert not [r for r in caplog.records if "[fill_qty_overrun]" in r.message]


class TestR5SellSideClamp:
    @pytest.mark.asyncio
    async def test_sell_overrun_clamped_and_position_cleared(
        self, engine, registry, mock_db, caplog,
    ):
        vb = registry.get("volatility_breakout")
        vb.state.positions["005930"] = Position(
            ticker="005930", buy_price=70_000, quantity=3, order_no="B1",
            strategy_id="volatility_breakout",
        )
        _arm(engine, "S0000001", "005930", 3)
        with caplog.at_level(logging.WARNING):
            await engine.handle_execution_notice(
                ticker="005930", order_no="S0000001", side="SELL",
                price=71_000, quantity=2)
            await engine.handle_execution_notice(
                ticker="005930", order_no="S0000001", side="SELL",
                price=71_000, quantity=2)
        # total 4 → 3 캡 → 전량 매도 판정 → 포지션 제거
        assert "005930" not in vb.state.positions
        assert any("[fill_qty_overrun]" in r.message for r in caplog.records)
        # C235-R1 — 손익 증분도 캡: (71,000−70,000)×3주치만 누적 (4주치 왜곡 금지.
        # daily_realized_pnl 은 일일손실 게이트가 소비하는 값이라 왜곡 = 게이트 오작동)
        assert vb.state.daily_realized_pnl == (71_000 - 70_000) * 3


class TestF1ZeroQuantityDrop:
    @pytest.mark.asyncio
    async def test_zero_quantity_notice_dropped(
        self, engine, registry, mock_db, caplog,
    ):
        """C235-F1 — CNTG_QTY 비양수 통보는 drop (fail-closed).

        매핑 부재 폴백(ordered=quantity=0)과 결합하면 `0 >= 0` 전량 판정으로
        BUY 0주 포지션 봉인·SELL 포지션 무단 삭제가 가능하던 잔존 리스크.
        """
        vb = registry.get("volatility_breakout")
        vb.state.positions["005930"] = Position(
            ticker="005930", buy_price=70_000, quantity=3, order_no="B1",
            strategy_id="volatility_breakout",
        )
        engine._order_ticker["Z0000001"] = "005930"
        engine._order_strategy["Z0000001"] = "volatility_breakout"
        with caplog.at_level(logging.WARNING):
            await engine.handle_execution_notice(
                ticker="005930", order_no="Z0000001", side="SELL",
                price=71_000, quantity=0)
        # 포지션 무단 삭제 금지 + drop 관측
        assert "005930" in vb.state.positions
        assert vb.state.positions["005930"].quantity == 3
        assert any("[fill_qty_zero]" in r.message for r in caplog.records)
        assert engine._filled_qty.get("Z0000001") is None  # 누적 오염 0
