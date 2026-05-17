"""Cycle 7-C Red — scanner 분배 명시화.

`subscribe_filtered_stocks(priority_groups=...)` 가 priority 카테고리별로
`kis_ws_pool.subscribe(tr_id, tr_key, priority='HIGH'|'LOW', bypass_limit=...)` 호출.

기존 `kis_ws.subscribe` 직접 호출은 풀 wrapper 로 위임.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner as scanner_module

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_pool_subscribe(monkeypatch):
    """`kis_ws_pool.subscribe` 를 spy AsyncMock 으로 교체."""
    from src.realtime import websocket_pool as wp_mod

    # 풀의 분배 추적 초기화 (이전 테스트 잔재 차단)
    wp_mod.kis_ws_pool._ticker_to_session.clear()

    spy = AsyncMock(return_value="main")
    # 풀 인스턴스 + scanner 모듈 import 양쪽
    monkeypatch.setattr(wp_mod.kis_ws_pool, "subscribe", spy, raising=False)
    if hasattr(scanner_module, "kis_ws_pool"):
        monkeypatch.setattr(scanner_module.kis_ws_pool, "subscribe", spy, raising=False)
    # 사이즈/슬롯 시뮬레이션을 위해 _subscriptions 도 노출 — scanner 가 잔여 슬롯 계산 시 활용
    monkeypatch.setattr(scanner_module.kis_ws, "_subscriptions", set(), raising=False)

    async def _fake_legacy_subscribe(tr_id, tr_key, *, bypass_limit=False):
        # legacy 경로 — priority_groups=None fallback 검증용
        scanner_module.kis_ws._subscriptions.add((tr_id, tr_key))

    monkeypatch.setattr(
        scanner_module.kis_ws, "subscribe",
        AsyncMock(side_effect=_fake_legacy_subscribe), raising=False,
    )
    return spy


# ---------------------------------------------------------------------------
# C-1. positions → priority='HIGH'
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_positions_dispatched_with_high_priority(mock_pool_subscribe):
    """priority_groups.positions ticker 는 pool.subscribe(priority='HIGH')."""
    priority_groups = {
        "positions": ["005930"],
        "next_day_clear": [],
        "swing": [], "momentum": [], "breakout": [],
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    # mock_pool_subscribe call_args 중 '005930' 호출이 priority='HIGH' 인지 확인
    found_high = False
    for call in mock_pool_subscribe.call_args_list:
        args, kwargs = call
        if "005930" in args:
            assert kwargs.get("priority") == "HIGH", (
                f"positions ticker 는 HIGH priority 로 전달되어야 함: kwargs={kwargs}"
            )
            found_high = True
    assert found_high, "positions ticker 가 pool.subscribe 로 전달되지 않음"


# ---------------------------------------------------------------------------
# C-2. next_day_clear → priority='HIGH'
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_next_day_clear_dispatched_with_high_priority(mock_pool_subscribe):
    """priority_groups.next_day_clear ticker 는 priority='HIGH'."""
    priority_groups = {
        "positions": [], "next_day_clear": ["000660"],
        "swing": [], "momentum": [], "breakout": [],
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    found_high = False
    for call in mock_pool_subscribe.call_args_list:
        args, kwargs = call
        if "000660" in args:
            assert kwargs.get("priority") == "HIGH"
            found_high = True
    assert found_high


# ---------------------------------------------------------------------------
# C-3, C-4, C-5. swing/momentum/breakout → priority='LOW'
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("group,ticker", [
    ("momentum", "012345"),
    ("breakout", "234567"),
    ("swing", "345678"),
])
async def test_low_priority_groups_dispatched_with_low(mock_pool_subscribe, group, ticker):
    """LOW 그룹(swing/momentum/breakout) 는 priority='LOW' 전달."""
    pg = {
        "positions": [], "next_day_clear": [],
        "swing": [], "momentum": [], "breakout": [],
    }
    pg[group] = [ticker]

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=pg,
    )

    found_low = False
    for call in mock_pool_subscribe.call_args_list:
        args, kwargs = call
        if ticker in args:
            assert kwargs.get("priority") == "LOW", (
                f"{group} ticker 는 LOW priority 로 전달: kwargs={kwargs}"
            )
            found_low = True
    assert found_low, f"{group} ticker 미 dispatch"


# ---------------------------------------------------------------------------
# C-6. priority_groups=None — 외부 호환 fallback
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flat_subscribe_when_priority_groups_none(mock_pool_subscribe, monkeypatch):
    """`priority_groups=None` 이면 평탄 처리 — pool.subscribe 또는 legacy 경로 1회."""
    legacy_spy = AsyncMock()
    monkeypatch.setattr(scanner_module.kis_ws, "subscribe", legacy_spy, raising=False)

    await scanner_module.subscribe_filtered_stocks(
        ["005930"], extra_tickers=[],
    )

    # legacy 경로 또는 pool 경로 중 하나로 등록되어야
    total_called = legacy_spy.await_count + mock_pool_subscribe.await_count
    assert total_called >= 1, "priority_groups=None 평탄 처리 경로에서 1회 이상 구독되어야 함"


# ---------------------------------------------------------------------------
# C-7. HIGH 는 bypass_limit=True
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_high_priority_uses_bypass_limit_true(mock_pool_subscribe):
    """positions / next_day_clear 호출은 bypass_limit=True."""
    pg = {
        "positions": ["005930"], "next_day_clear": ["000660"],
        "swing": [], "momentum": [], "breakout": [],
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=pg,
    )

    high_calls = [
        c for c in mock_pool_subscribe.call_args_list
        if c.kwargs.get("priority") == "HIGH"
    ]
    assert len(high_calls) == 2, f"HIGH 호출 2회 기대, 실제={len(high_calls)}"
    for call in high_calls:
        assert call.kwargs.get("bypass_limit") is True, (
            f"HIGH 는 bypass_limit=True 보장: {call.kwargs}"
        )


# ---------------------------------------------------------------------------
# C-8. 중복 ticker — HIGH 만 1회, LOW skip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_ticker_dispatches_high_only_once(mock_pool_subscribe):
    """positions + momentum 양쪽에 있어도 HIGH 1회만 호출, LOW skip."""
    pg = {
        "positions": ["005930"], "next_day_clear": [],
        "swing": [], "momentum": ["005930"], "breakout": [],
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=pg,
    )

    # 005930 호출은 정확히 1회, priority='HIGH'
    matching = [
        c for c in mock_pool_subscribe.call_args_list
        if "005930" in c.args
    ]
    assert len(matching) == 1, f"중복 ticker 는 1회만 호출, 실제={len(matching)}"
    assert matching[0].kwargs.get("priority") == "HIGH", (
        f"중복 ticker HIGH 우선 보장: {matching[0].kwargs}"
    )
