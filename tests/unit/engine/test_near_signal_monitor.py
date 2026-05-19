"""near_signal_monitor 단위 테스트 (사이클 15-B-1, 2026-05-19).

5 전략 임박 판단 + 시간 윈도우 검증. fetch_stock_detail mock.

12 케이스:
1. calc_distance_pct 양수 (미돌파)
2. calc_distance_pct 음수 (돌파 후)
3. calc_distance_pct target_price=0 → inf
4. extract_target_price VB (boards.main.target_price 우선)
5. extract_target_price VB fallback (top-level)
6. extract_target_price BFB (flag_high)
7. check_breakout_strategy 임박 (0.3% 이내) 종목 식별
8. check_breakout_strategy 거리 0.5% (미달) skip
9. check_breakout_strategy 시간 윈도우 외 skip
10. check_momentum_strategy change_rate 28.5% 이상 식별
11. check_donchian_strategy 시간 윈도우 안 (09:15) — 후보 전체
12. check_donchian_strategy 시간 윈도우 외 (08:00) — 빈 결과
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest

from src.engine import near_signal_monitor as nsm
from src.engine.near_signal_monitor import (
    BFB_WINDOW,
    DONCHIAN_WINDOW,
    calc_distance_pct,
    check_breakout_strategy,
    check_donchian_strategy,
    check_momentum_strategy,
    extract_target_price,
)

pytestmark = pytest.mark.unit

KST_TZ = timezone(timedelta(hours=9))


# ===========================================================================
# Case 1-3: calc_distance_pct
# ===========================================================================
def test_calc_distance_pct_positive():
    """target=10000, current=9970 → distance=0.3%."""
    assert calc_distance_pct(10000, 9970) == pytest.approx(0.3, abs=0.01)


def test_calc_distance_pct_negative_already_breakout():
    """target=10000, current=10050 → distance=-0.5% (돌파 후)."""
    assert calc_distance_pct(10000, 10050) == pytest.approx(-0.5, abs=0.01)


def test_calc_distance_pct_target_zero():
    assert calc_distance_pct(0, 9000) == float("inf")


# ===========================================================================
# Case 4-6: extract_target_price
# ===========================================================================
def test_extract_target_price_vb_boards_main_priority():
    info = {
        "boards": {"main": {"target_price": 15830, "open_price": 15500}},
        "target_price": 15400,  # fallback (덜 정확)
    }
    assert extract_target_price("volatility_breakout", info) == 15830


def test_extract_target_price_vb_fallback_top_level():
    info = {
        "boards": {},  # 활성 보드 없음
        "target_price": 15400,
    }
    assert extract_target_price("volatility_breakout", info) == 15400


def test_extract_target_price_bfb_uses_flag_high():
    info = {"flag_high": 12500, "target_price": 0}
    assert extract_target_price("bull_flag_breakout", info) == 12500


# ===========================================================================
# Case 7-9: check_breakout_strategy
# ===========================================================================
@pytest.mark.asyncio
async def test_check_breakout_identifies_near_signal(monkeypatch):
    """target=10000, current=9975 → distance=0.25% (임박 0.3% 이내)."""
    targets = {"005930": {"target_price": 10000, "boards": {"main": {"target_price": 10000}}}}

    async def _fetch(ticker):
        return 9975

    monkeypatch.setattr(nsm, "fetch_current_price", _fetch)

    results = await check_breakout_strategy(
        "volatility_breakout", targets, threshold_pct=0.3,
    )
    assert len(results) == 1
    assert results[0][0] == "005930"
    assert "distance_pct" in results[0][1]


@pytest.mark.asyncio
async def test_check_breakout_skips_far_distance(monkeypatch):
    """target=10000, current=9900 → distance=1.0% (0.3% 초과 → skip)."""
    targets = {"005930": {"target_price": 10000, "boards": {"main": {"target_price": 10000}}}}

    async def _fetch(ticker):
        return 9900

    monkeypatch.setattr(nsm, "fetch_current_price", _fetch)

    results = await check_breakout_strategy(
        "volatility_breakout", targets, threshold_pct=0.3,
    )
    assert results == []


@pytest.mark.asyncio
async def test_check_breakout_outside_time_window_skips(monkeypatch):
    """time_window=BFB_WINDOW(09:05~13:00). 14:00 호출 → 모두 skip."""
    targets = {"005930": {"flag_high": 10000, "target_price": 10000}}

    async def _fetch(ticker):
        return 9975  # 임박이지만 시간 외

    monkeypatch.setattr(nsm, "fetch_current_price", _fetch)

    outside = datetime(2026, 5, 19, 14, 0, tzinfo=KST_TZ)
    results = await check_breakout_strategy(
        "bull_flag_breakout", targets, threshold_pct=0.4,
        time_window=BFB_WINDOW, now=outside,
    )
    assert results == []


# ===========================================================================
# Case 10: check_momentum_strategy
# ===========================================================================
@pytest.mark.asyncio
async def test_check_momentum_identifies_high_change_rate(monkeypatch):
    """28.5% 이상은 임박 식별."""
    async def _fetch_detail(ticker):
        if ticker == "A001":
            return {"prdy_ctrt": 28.7, "stck_prpr": 13000}
        if ticker == "A002":
            return {"prdy_ctrt": 25.0, "stck_prpr": 12000}
        if ticker == "A003":
            return {"prdy_ctrt": 29.5, "stck_prpr": 14000}
        return None

    monkeypatch.setattr(
        "src.api.condition.fetch_stock_detail", _fetch_detail, raising=False,
    )

    results = await check_momentum_strategy(["A001", "A002", "A003"])
    found = {t for t, _ in results}
    assert found == {"A001", "A003"}, f"28.5% 이상만 식별. 실제={found}"


# ===========================================================================
# Case 11-12: check_donchian_strategy
# ===========================================================================
def test_check_donchian_within_time_window_returns_all():
    """09:15 (09:05~09:30 안) → 모든 후보 임박."""
    now = datetime(2026, 5, 19, 9, 15, tzinfo=KST_TZ)
    results = check_donchian_strategy(["005930", "000660"], now=now)
    assert {t for t, _ in results} == {"005930", "000660"}


def test_check_donchian_outside_time_window_returns_empty():
    """08:00 (시간 윈도우 외) → 빈 결과."""
    now = datetime(2026, 5, 19, 8, 0, tzinfo=KST_TZ)
    results = check_donchian_strategy(["005930"], now=now)
    assert results == []
