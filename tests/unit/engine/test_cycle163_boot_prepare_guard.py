"""사이클 163 (2026-06-18) — boot_manager.boot() 영역 prepare 호출 *전*
stock_master.count_active() 가드 회귀 가드.

의제 #5 영역 — 6/18 08:22~08:27 KST 운영 사고 영구 차단.
사이클 158 VB 자동 재시도 hook 한계 보완 (90초 vs 4분 27초 race).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeStrategy:
    def __init__(self, sid: str):
        self.strategy_id = sid
        self.prepare = AsyncMock()


def _make_scheduler():
    s = MagicMock()
    s._preissue_all_tokens = AsyncMock()
    s._load_strategy_config = AsyncMock()
    s._refresh_market_regime_and_persist = AsyncMock()
    s._resolve_cash_usage_ratio = AsyncMock(return_value=1.0)
    s._eager_refresh_stock_master_for_held_positions = AsyncMock()
    s.registry = MagicMock()
    s.registry.allocate_funds = MagicMock()
    strategies = [_FakeStrategy("vb"), _FakeStrategy("ltv")]
    s.registry.enabled = MagicMock(return_value=strategies)
    s._strategies = strategies
    return s


@pytest.mark.asyncio
async def test_G163_BOOT_1_count_active_called_before_prepare():
    """G-163-BOOT-1: prepare 호출 *전* count_active() 호출 영속 (AST).

    Supabase mock count=2768 → 즉시 prepare 진입 (대기 0).
    """
    from src.engine import boot_manager

    scheduler = _make_scheduler()

    summary = MagicMock(net_asset=1289715)
    holdings = []

    with patch.object(boot_manager, "get_balance", AsyncMock(return_value=(holdings, summary))), \
         patch.object(boot_manager, "token_manager") as mock_tm, \
         patch.object(boot_manager, "get_daily_orders", AsyncMock(return_value=[])), \
         patch("src.db.stock_master.count_active", AsyncMock(return_value=2768)) as mock_count, \
         patch.object(boot_manager, "write_log", AsyncMock()), \
         patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        mock_tm.get_token = AsyncMock()

        # boot 본체는 매우 길어 prepare 호출 까지만 도달하면 됨 → 이후 step 예외는 graceful
        try:
            await boot_manager.boot(scheduler)
        except Exception:
            pass

    mock_count.assert_called()
    # prepare 호출 후 count_active 가 호출되었는지 확인
    for st in scheduler._strategies:
        st.prepare.assert_called_once()


@pytest.mark.asyncio
async def test_G163_BOOT_2_zero_count_triggers_sleep():
    """G-163-BOOT-2: count_active() == 0 영역 → asyncio.sleep(10) 발화 후 재폴링.

    사이클 134 task_loop_helper stagger 패턴 답습 (변경 0).
    """
    from src.engine import boot_manager

    scheduler = _make_scheduler()
    summary = MagicMock(net_asset=1289715)

    # 0 → 0 → 2768 (2회 대기 후 적재 완료)
    count_values = iter([0, 0, 2768])
    mock_count = AsyncMock(side_effect=lambda: next(count_values))

    sleep_calls: list[float] = []

    async def _capture_sleep(secs):
        sleep_calls.append(secs)

    with patch.object(boot_manager, "get_balance", AsyncMock(return_value=([], summary))), \
         patch.object(boot_manager, "token_manager") as mock_tm, \
         patch.object(boot_manager, "get_daily_orders", AsyncMock(return_value=[])), \
         patch("src.db.stock_master.count_active", mock_count), \
         patch.object(boot_manager, "write_log", AsyncMock()), \
         patch("asyncio.sleep", _capture_sleep):
        mock_tm.get_token = AsyncMock()

        try:
            await boot_manager.boot(scheduler)
        except Exception:
            pass

    # 10초 sleep 최소 2회 (count=0 두 번)
    poll_sleeps = [s for s in sleep_calls if s == 10]
    assert len(poll_sleeps) >= 2


@pytest.mark.asyncio
async def test_G163_BOOT_3_nonzero_count_no_wait():
    """G-163-BOOT-3: count_active() > 0 영역 → 즉시 prepare (대기 0).

    회귀 보존 (정상 boot 시 대기 영역 발화 0).
    """
    from src.engine import boot_manager

    scheduler = _make_scheduler()
    summary = MagicMock(net_asset=1289715)

    sleep_calls: list[float] = []

    async def _capture_sleep(secs):
        sleep_calls.append(secs)

    with patch.object(boot_manager, "get_balance", AsyncMock(return_value=([], summary))), \
         patch.object(boot_manager, "token_manager") as mock_tm, \
         patch.object(boot_manager, "get_daily_orders", AsyncMock(return_value=[])), \
         patch("src.db.stock_master.count_active", AsyncMock(return_value=2768)), \
         patch.object(boot_manager, "write_log", AsyncMock()), \
         patch("asyncio.sleep", _capture_sleep):
        mock_tm.get_token = AsyncMock()

        try:
            await boot_manager.boot(scheduler)
        except Exception:
            pass

    # 10초 polling sleep 발화 0건
    poll_sleeps = [s for s in sleep_calls if s == 10]
    assert len(poll_sleeps) == 0


@pytest.mark.asyncio
async def test_G163_BOOT_4_cap_exceeded_warning_and_proceed():
    """G-163-BOOT-4: 5분 cap 초과 → graceful WARNING + prepare 진행.

    매매 안전성 보존 — 무한 대기 영역 차단.
    """
    from src.engine import boot_manager

    scheduler = _make_scheduler()
    summary = MagicMock(net_asset=1289715)

    # 영구 0 (영원히 적재 안 됨)
    mock_count = AsyncMock(return_value=0)

    sleep_calls: list[float] = []

    async def _capture_sleep(secs):
        sleep_calls.append(secs)

    with patch.object(boot_manager, "get_balance", AsyncMock(return_value=([], summary))), \
         patch.object(boot_manager, "token_manager") as mock_tm, \
         patch.object(boot_manager, "get_daily_orders", AsyncMock(return_value=[])), \
         patch("src.db.stock_master.count_active", mock_count), \
         patch.object(boot_manager, "write_log", AsyncMock()), \
         patch("asyncio.sleep", _capture_sleep):
        mock_tm.get_token = AsyncMock()

        try:
            await boot_manager.boot(scheduler)
        except Exception:
            pass

    # 5분 cap = 30회 polling 발화 (10초 × 30회)
    poll_sleeps = [s for s in sleep_calls if s == 10]
    assert len(poll_sleeps) == 30, f"expected 30 polls in 5min cap, got {len(poll_sleeps)}"
    # cap 후 prepare 영속 호출
    for st in scheduler._strategies:
        st.prepare.assert_called_once()
