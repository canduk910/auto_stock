"""cycle444 — 섀도 전략 후보의 stale 재구독 경로 최후순위화.

사용자 지시(2026-10-11) 「섀도전략들은 웹소켓 시세구독 우선순위를 낮춰야해」.

대상 2곳:
- `resubscribe_stale_priority`(5분, cap 있음) — LOW 안에서 섀도 전용 후보는
  실전 LOW 가 cap 을 먼저 쓴 뒤에만 남은 cap 을 받는다.
- `check_and_resubscribe_stale`(120s, cap 없음) — 처리 **순서**만 섀도가 최후순위.

픽스처는 `test_cycle216_priority_throttle_call_auction.py` 의 것을 그대로
재사용한다(cycle240 선례 — 중복 정의 금지).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from tests.unit.engine.stale_manager.test_cycle216_priority_throttle_call_auction import (  # noqa: F401
    _make_scheduler_with_high_tickers,
    _make_spy_pool,
    _session_tracker_mock,
)

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_FROZEN = "2026-10-11 10:00:00"
_BASE = datetime(2026, 10, 11, 10, 0, 0, tzinfo=KST)
_STALE = _BASE - timedelta(seconds=120)


def _arm_breakout(sched, tickers):
    sched._collect_breakout_tickers = lambda: list(tickers)


def _arm_shadow_breakout(sched, tickers):
    sched._collect_shadow_breakout_tickers = lambda: list(tickers)


def _subscribed_tickers(pool) -> list[str]:
    return [c.args[1] for c in pool.subscribe.await_args_list]


# ===========================================================================
# 1) resubscribe_stale_priority — 섀도 LOW 는 실전 LOW 가 cap 을 다 쓴 뒤에만
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_shadow_low_only_fills_remaining_cap_after_live_low():
    """실전 2 + 섀도 3, cap=3 → 실전 2 전부 + 섀도 1 만(잔여 cap)."""
    from src.engine import stale_manager

    sched = _make_scheduler_with_high_tickers()  # HIGH 0
    _arm_breakout(sched, ["000100", "000200"])            # 실전 desired
    _arm_shadow_breakout(sched, ["000300", "000400", "000500"])  # 섀도 desired

    ticker_last_tick = {
        t: _STALE for t in ("000100", "000200", "000300", "000400", "000500")
    }
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=3)

    assert set(result) == {"000100", "000200", "000300"} or set(result) == {
        "000100", "000200", "000400",
    } or set(result) == {"000100", "000200", "000500"}, (
        f"실전 2개는 반드시 포함, 섀도는 1개만 — 실제: {result}"
    )
    assert "000100" in result and "000200" in result, "실전 LOW 는 전량 생존해야 한다"
    shadow_subscribed = [t for t in result if t in ("000300", "000400", "000500")]
    assert len(shadow_subscribed) == 1, (
        f"잔여 cap(3-2=1) 만큼만 섀도가 받아야 한다. 실제: {shadow_subscribed}"
    )


# ===========================================================================
# 2) 겹침 — 같은 종목이 실전·섀도 둘 다의 desired 면 실전 취급(최후순위 제외)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_shadow_low_overlap_with_live_desired_treated_as_live():
    """000100 이 실전·섀도 둘 다의 desired → 실전 취급되어 cap 소진 순서에서 뒤로 밀리지 않는다."""
    from src.engine import stale_manager

    sched = _make_scheduler_with_high_tickers()
    _arm_breakout(sched, ["000100"])             # 실전 desired 에도 있음
    _arm_shadow_breakout(sched, ["000100", "000900"])  # 섀도 desired 에도 있음(겹침) + 섀도 전용

    ticker_last_tick = {"000100": _STALE, "000900": _STALE}
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=1)

    assert result == ["000100"], (
        f"겹치는 종목은 실전으로 취급돼 cap=1 을 차지해야 한다(섀도 전용 000900 은 밀린다). "
        f"실제: {result}"
    )


# ===========================================================================
# 3) check_and_resubscribe_stale(120s) — 처리 순서만 섀도 최후, HIGH 는 무관
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_k_watcher_processes_shadow_low_last():
    """HIGH 1(보유) + 실전 LOW 1 + 섀도 LOW 1, cap 없음(전부 처리) — 그래도 처리
    순서(= subscribe 호출 순서)는 HIGH/실전이 섀도보다 앞선다."""
    from src.engine import stale_manager

    sched = _make_scheduler_with_high_tickers(positions=["H001"])
    _arm_breakout(sched, ["L001"])
    _arm_shadow_breakout(sched, ["SH001"])

    ticker_last_tick = {"H001": _STALE, "L001": _STALE, "SH001": _STALE}
    pool, call_log = _make_spy_pool()
    pool.get_subscribed_tickers = lambda: {"H001", "L001", "SH001"}

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick), \
         patch("src.engine.market_operation_monitor.is_ticker_stale_excluded", return_value=False):
        await stale_manager.check_and_resubscribe_stale(sched)

    subscribed_order = [t for (kind, _tr, t, *_rest) in call_log if kind == "sub"]
    assert set(subscribed_order) == {"H001", "L001", "SH001"}, (
        f"3종목 전부 재구독돼야 한다(섀도도 끊지 않는다). 실제: {subscribed_order}"
    )
    assert subscribed_order.index("SH001") > subscribed_order.index("L001"), (
        f"섀도(SH001) 는 실전(L001) 보다 뒤에 처리돼야 한다. 순서: {subscribed_order}"
    )
