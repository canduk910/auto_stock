"""사이클 147 Red — `_lookup_strategy_from_trade_history` + `_update_trade_status_by_order_no` 신규 헬퍼.

## 영역 영구 영속

영역 1: `_lookup_strategy_from_trade_history(ticker, order_no, trade_type) -> Optional[str]`
- PENDING/PARTIAL row 영역 영구 영속에서 strategy 영역 조회
- order_no 단일 키 영역 (사이클 30 UNIQUE 인덱스 정합)
- 0건 / 예외 → None graceful

영역 2: `_update_trade_status_by_order_no(order_no, trade_type, status, price=None, profit_loss=None) -> int`
- strategy 필터 영역 폐기 영구 영속 (order_no 단일 키)
- 보정 INSERT UniqueViolation 영역 영속 → 강제 UPDATE
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.db.trade_history import (
    _lookup_strategy_from_trade_history,
    _update_trade_status_by_order_no,
)
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# G-147-LOOKUP-1 — PENDING row 영역 strategy 정상 영구 영속 반환
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G147_LOOKUP_1_pending_row_returns_strategy() -> None:
    """trade_history PENDING row 1건 → strategy 영역 영구 영속 반환."""
    with patch("src.db.trade_history.supabase") as mock_sb:
        mock_result = MagicMock()
        mock_result.data = [{"strategy": "long_tail_volatility"}]
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = mock_result

        result = await _lookup_strategy_from_trade_history(
            "005940", "0000004700", TradeType.SELL
        )

        assert result == "long_tail_volatility"


# ---------------------------------------------------------------------------
# G-147-LOOKUP-2 — 0건 / 예외 → None graceful
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G147_LOOKUP_2_miss_or_exception_returns_none() -> None:
    """0건 → None. supabase 예외 → None graceful (호출자 보호 영역)."""
    # 0건 영역 영구 영속
    with patch("src.db.trade_history.supabase") as mock_sb:
        mock_result = MagicMock()
        mock_result.data = []
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = mock_result

        result = await _lookup_strategy_from_trade_history(
            "999999", "UNKNOWN", TradeType.SELL
        )
        assert result is None

    # 예외 영역 영구 영속
    with patch("src.db.trade_history.supabase") as mock_sb:
        mock_sb.table.side_effect = Exception("Supabase connection error")

        result = await _lookup_strategy_from_trade_history(
            "005940", "0000004700", TradeType.SELL
        )
        assert result is None, "예외 graceful → None 영역 영구 영속 의무"


# ---------------------------------------------------------------------------
# G-147-UPDATE-BY-ORDER-1 — strategy 무관 강제 UPDATE 영역 영구 영속
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G147_UPDATE_BY_ORDER_1_strategy_agnostic_update() -> None:
    """`_update_trade_status_by_order_no` 영역 영구 영속 = order_no 단일 키 + strategy 필터 영역 폐기 영구 영속."""
    with patch("src.db.trade_history.supabase") as mock_sb:
        mock_result = MagicMock()
        mock_result.data = [{"id": "uuid-001", "status": "COMPLETED"}]
        # 체이닝 영역 영구 영속 = update().eq().eq().eq().execute()
        chain = mock_sb.table.return_value.update.return_value
        chain.eq.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_result
        )

        affected = await _update_trade_status_by_order_no(
            "0000004700",
            TradeType.SELL,
            TradeStatus.COMPLETED,
            price=33250,
            profit_loss=0,
        )

        assert affected == 1
        # G-UPDATE-BY-ORDER-1-A: update_data 영역 영구 영속 영역 status + price + profit_loss
        update_call = mock_sb.table.return_value.update.call_args[0][0]
        assert update_call["status"] == "COMPLETED"
        assert update_call["price"] == 33250.0
        assert update_call["profit_loss"] == 0.0
