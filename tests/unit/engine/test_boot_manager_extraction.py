"""사이클 51 회귀 가드 — `_boot()` 의 boot_manager 위임 + 행위 보존.

검증 포인트:
1. `boot_manager.boot` 함수가 존재 + async callable
2. `scheduler._boot()` 호출 시 `boot_manager.boot(self)` 가 정확히 1회 호출
3. boot_manager 가 scheduler 의 핵심 호출 순서 (token → preissue → load_strategy_config
   → balance → regime → cash_ratio → allocate_funds → prepare → eager refresh) 를 보존
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import boot_manager
from src.engine.scheduler import TradingScheduler


def test_boot_manager_module_exposes_async_boot():
    """boot_manager.boot 가 모듈에 정의되어 있어야 한다."""
    assert hasattr(boot_manager, "boot")
    assert asyncio.iscoroutinefunction(boot_manager.boot)


@pytest.mark.asyncio
async def test_scheduler_boot_delegates_to_boot_manager():
    """scheduler._boot() 는 boot_manager.boot(self) 위임 1회 + 다른 부수 동작 0건."""
    scheduler = TradingScheduler.__new__(TradingScheduler)

    with patch("src.engine.boot_manager.boot", new=AsyncMock()) as mock_boot:
        await scheduler._boot()

    mock_boot.assert_awaited_once_with(scheduler)


@pytest.mark.asyncio
async def test_boot_calls_preissue_before_token_and_load_config():
    """boot 호출 순서 보존: preissue → token → load_strategy_config → balance.

    행위 보존 검증의 핵심 — 토큰 사전 발급 후에만 KIS REST 호출 (잔고) 진입.
    """
    call_order: list[str] = []

    scheduler = MagicMock()
    scheduler._preissue_all_tokens = AsyncMock(side_effect=lambda: call_order.append("preissue"))
    scheduler._load_strategy_config = AsyncMock(side_effect=lambda: call_order.append("load_config"))
    scheduler._refresh_market_regime_and_persist = AsyncMock(
        side_effect=lambda: call_order.append("regime")
    )
    scheduler._resolve_cash_usage_ratio = AsyncMock(
        side_effect=lambda: (call_order.append("ratio") or 1.0)
    )
    scheduler._sync_orders_to_db = AsyncMock()
    scheduler._eager_refresh_stock_master_for_held_positions = AsyncMock(
        side_effect=lambda: call_order.append("eager")
    )
    scheduler.registry = MagicMock()
    scheduler.registry.enabled.return_value = []
    scheduler.registry.all.return_value = []
    scheduler.registry.is_ticker_held_by_any.return_value = False
    scheduler.registry.get.return_value = None
    scheduler.registry.allocate_funds = MagicMock()
    scheduler.order_engine = MagicMock()
    scheduler.order_engine._pending_buy_orders = {}
    scheduler.order_engine._order_qty = {}
    scheduler.order_engine._order_strategy = {}
    scheduler.order_engine._order_ticker = {}

    summary = MagicMock()
    summary.net_asset = 1_000_000

    with patch("src.engine.boot_manager.token_manager") as tm, \
         patch("src.engine.boot_manager.get_balance", new=AsyncMock(
             side_effect=lambda: (call_order.append("balance") or ([], summary))
         )), \
         patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(return_value=[])), \
         patch("src.engine.boot_manager.write_log", new=AsyncMock()), \
         patch("src.db.positions.load_all", new=AsyncMock(return_value=[])):
        tm.get_token = AsyncMock(side_effect=lambda: call_order.append("token"))
        await boot_manager.boot(scheduler)

    assert call_order.index("preissue") < call_order.index("token")
    assert call_order.index("token") < call_order.index("load_config")
    assert call_order.index("load_config") < call_order.index("balance")
    assert call_order.index("balance") < call_order.index("regime")
    assert call_order.index("regime") < call_order.index("ratio")
    assert "eager" in call_order
    scheduler.registry.allocate_funds.assert_called_once_with(1_000_000)
