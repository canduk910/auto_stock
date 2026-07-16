"""사이클 147 Red — `_lookup_strategy_from_trade_history` + `_update_trade_status_by_order_no` 신규 헬퍼.

## 영역 영구 영속

영역 1: `_lookup_strategy_from_trade_history(ticker, order_no, trade_type) -> Optional[str]`
- PENDING/PARTIAL row 영역 영구 영속에서 strategy 영역 조회
- order_no 단일 키 영역 (사이클 30 UNIQUE 인덱스 정합)
- 0건 / 예외 → None graceful

영역 2: `_update_trade_status_by_order_no(order_no, trade_type, status, price=None, profit_loss=None) -> int`
- strategy 필터 영역 폐기 영구 영속 (order_no 단일 키)
- 보정 INSERT UniqueViolation 영역 영속 → 강제 UPDATE

사이클 M2a (2026-07-16) 의미 전환 — trade_history 가 supabase-py → src.db.pg(asyncpg)
전환. 기존 `.table().select()...` 체인 mock → `pg.fetch`/`pg.execute` mock 으로 대체.
"""

from __future__ import annotations

from unittest.mock import patch

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
    with patch("src.db.trade_history.pg", create=True) as pg_mock:
        async def _fetch(sql, *args):
            return [{"strategy": "long_tail_volatility"}]

        pg_mock.fetch = _fetch

        result = await _lookup_strategy_from_trade_history(
            "005940", "0000004700", TradeType.SELL
        )

        assert result == "long_tail_volatility"


# ---------------------------------------------------------------------------
# G-147-LOOKUP-2 — 0건 / 예외 → None graceful
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G147_LOOKUP_2_miss_or_exception_returns_none() -> None:
    """0건 → None. pg 예외 → None graceful (호출자 보호 영역)."""
    # 0건 영역 영구 영속
    with patch("src.db.trade_history.pg", create=True) as pg_mock:
        async def _fetch_empty(sql, *args):
            return []

        pg_mock.fetch = _fetch_empty

        result = await _lookup_strategy_from_trade_history(
            "999999", "UNKNOWN", TradeType.SELL
        )
        assert result is None

    # 예외 영역 영구 영속
    with patch("src.db.trade_history.pg", create=True) as pg_mock:
        async def _fetch_raises(sql, *args):
            raise Exception("DB connection error")

        pg_mock.fetch = _fetch_raises

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
    with patch("src.db.trade_history.pg", create=True) as pg_mock:
        execute_calls: list[tuple] = []

        async def _execute(sql, *args):
            execute_calls.append((sql, args))
            return "UPDATE 1"

        pg_mock.execute = _execute

        affected = await _update_trade_status_by_order_no(
            "0000004700",
            TradeType.SELL,
            TradeStatus.COMPLETED,
            price=33250,
            profit_loss=0,
        )

        assert affected == 1
        # G-UPDATE-BY-ORDER-1-A: UPDATE 바인딩 영역 영구 영속 = status + price + profit_loss
        assert len(execute_calls) == 1
        sql, args = execute_calls[0]
        assert "UPDATE trade_history" in sql
        assert "COMPLETED" in args
        assert 33250.0 in args
        assert 0.0 in args
