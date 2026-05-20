"""사이클 25-B (2026-05-20) — VB/LTV 후보 LOW 강등 회귀 가드.

배경 (2026-05-20 14:58 운영 결함):
- 메인 세션 sub=11 fresh=0 stale=11 silent inactive
- VB/LTV 매수 후보 (8 종목) 모두 메인에 집중 → KIS silent inactive
- 근본 원인: _resubscribe_stale_priority 가 stale 종목에 무조건 HIGH+bypass_limit=True 재등록
  → VB/LTV 후보가 stale 되면 메인 승격 → 메인 과부하

해결:
- _resubscribe_stale_priority 가 보유(positions)/익일청산(next_day_clear) 종목만 HIGH 유지
- 그 외 후보 종목은 LOW + bypass_limit=False 로 보조 재분배
- subscribe_filtered_stocks 의 breakout 그룹 LOW 처리는 이미 올바름 (회귀 0 유지)

6 케이스:
1. _resubscribe_stale_priority: 후보 stale → LOW + bypass_limit=False
2. _resubscribe_stale_priority: positions stale → HIGH + bypass_limit=True 유지
3. _resubscribe_stale_priority: next_day_clear stale → HIGH + bypass_limit=True 유지
4. subscribe_filtered_stocks: breakout 그룹 → LOW + bypass_limit=False (기존 보존)
5. subscribe_filtered_stocks: positions 그룹 → HIGH + bypass_limit=True (기존 보존)
6. _resubscribe_stale_priority: 혼합 (positions 1 + 후보 3) → positions=HIGH, 후보=LOW 분리
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공용 헬퍼
# ---------------------------------------------------------------------------

def _make_scheduler(position_tickers: list[str], ndc_tickers: list[str]):
    """TradingScheduler 를 minimal 하게 세팅한다.

    positions / _pending_next_day_clear 만 필요한 케이스를 위한 헬퍼.
    """
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_registry import StrategyRegistry

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._pending_next_day_clear = {(t, "strategy") for t in ndc_tickers}

    # registry mock — positions만 반환
    class _FakeState:
        def __init__(self, tickers):
            self.positions = {t: object() for t in tickers}

    class _FakeStrategy:
        def __init__(self, tickers):
            self.state = _FakeState(tickers)

    class _FakeRegistry:
        def __init__(self, tickers):
            self._strat = _FakeStrategy(tickers)

        def all(self):
            return [self._strat]

    sched.registry = _FakeRegistry(position_tickers)
    return sched


async def _run_resubscribe_stale_priority(
    stale_tickers: list[str],
    position_tickers: list[str],
    ndc_tickers: list[str],
    fresh_tickers: list[str] | None = None,
    cap: int = 20,
) -> list[dict]:
    """_resubscribe_stale_priority 를 실행하고 subscribe 호출 목록을 반환한다."""
    import src.engine.scanner as scanner_mod
    from src.engine.scanner import KST_TZ, ticker_last_tick
    from src.engine.scheduler import STALE_FRESHNESS_SECS
    from src.engine import scheduler as scheduler_module
    from src.realtime import websocket_pool as wp_module

    ticker_last_tick.clear()
    now = datetime.now(KST_TZ)
    stale_dt = now - timedelta(seconds=STALE_FRESHNESS_SECS + 30)
    fresh_dt = now

    for t in (fresh_tickers or []):
        ticker_last_tick[t] = fresh_dt
    for t in stale_tickers:
        ticker_last_tick[t] = stale_dt

    sched = _make_scheduler(position_tickers, ndc_tickers)

    subscribe_calls: list[dict] = []

    async def fake_subscribe(tr_id, tr_key, *, priority="LOW", bypass_limit=False):
        subscribe_calls.append({
            "tr_id": tr_id, "tr_key": tr_key,
            "priority": priority, "bypass_limit": bypass_limit,
        })
        return priority.lower()

    original_subscribe = wp_module.kis_ws_pool.subscribe
    wp_module.kis_ws_pool.subscribe = fake_subscribe

    original_write_log = scheduler_module.write_log

    async def fake_write_log(level, message):
        pass

    scheduler_module.write_log = fake_write_log

    try:
        await sched._resubscribe_stale_priority(cap=cap)
    finally:
        wp_module.kis_ws_pool.subscribe = original_subscribe
        scheduler_module.write_log = original_write_log
        ticker_last_tick.clear()

    return subscribe_calls


# ===========================================================================
# Case 1: 후보 stale → LOW + bypass_limit=False
# ===========================================================================
@pytest.mark.asyncio
async def test_breakout_candidate_stale_gets_low_priority():
    """VB/LTV 후보 stale 종목 → LOW + bypass_limit=False 로 재구독.

    positions / next_day_clear 에 없는 종목은 후보로 간주해 LOW 재등록.
    """
    candidate_tickers = ["036930", "005935", "439960", "010170"]
    stale = candidate_tickers  # 후보가 stale

    calls = await _run_resubscribe_stale_priority(
        stale_tickers=stale,
        position_tickers=[],   # 보유 없음
        ndc_tickers=[],        # 익일청산 없음
    )

    assert len(calls) == len(stale), (
        f"stale 후보 {len(stale)}건 모두 재구독 호출 필요. got={len(calls)}"
    )

    for call in calls:
        assert call["priority"] == "LOW", (
            f"후보 종목 {call['tr_key']} 는 LOW 재구독 필요. got={call['priority']}"
        )
        assert call["bypass_limit"] is False, (
            f"후보 종목 {call['tr_key']} 는 bypass_limit=False 필요. got={call['bypass_limit']}"
        )


# ===========================================================================
# Case 2: positions stale → HIGH + bypass_limit=True 유지
# ===========================================================================
@pytest.mark.asyncio
async def test_positions_stale_keeps_high_priority():
    """보유 포지션 stale 종목 → HIGH + bypass_limit=True 절대 보장.

    보유 종목 시세 누락 시 손절·트레일링 평가 불가 → HIGH 필수.
    """
    position_tickers = ["253840", "142280"]
    stale = position_tickers

    calls = await _run_resubscribe_stale_priority(
        stale_tickers=stale,
        position_tickers=position_tickers,
        ndc_tickers=[],
    )

    assert len(calls) == len(stale), (
        f"positions stale {len(stale)}건 모두 재구독 호출 필요. got={len(calls)}"
    )

    for call in calls:
        assert call["priority"] == "HIGH", (
            f"positions 종목 {call['tr_key']} 는 HIGH 유지 필요. got={call['priority']}"
        )
        assert call["bypass_limit"] is True, (
            f"positions 종목 {call['tr_key']} 는 bypass_limit=True 필요. got={call['bypass_limit']}"
        )


# ===========================================================================
# Case 3: next_day_clear stale → HIGH + bypass_limit=True 유지
# ===========================================================================
@pytest.mark.asyncio
async def test_next_day_clear_stale_keeps_high_priority():
    """익일 청산 대상 stale 종목 → HIGH + bypass_limit=True 절대 보장.

    익일 청산 시가 수신 필수 — LOW 강등 금지.
    """
    ndc_tickers = ["066430", "011000"]
    stale = ndc_tickers

    calls = await _run_resubscribe_stale_priority(
        stale_tickers=stale,
        position_tickers=[],
        ndc_tickers=ndc_tickers,
    )

    assert len(calls) == len(stale), (
        f"next_day_clear stale {len(stale)}건 모두 재구독 호출 필요. got={len(calls)}"
    )

    for call in calls:
        assert call["priority"] == "HIGH", (
            f"next_day_clear 종목 {call['tr_key']} 는 HIGH 유지 필요. got={call['priority']}"
        )
        assert call["bypass_limit"] is True, (
            f"next_day_clear 종목 {call['tr_key']} 는 bypass_limit=True 필요. got={call['bypass_limit']}"
        )


# ===========================================================================
# Case 4: subscribe_filtered_stocks breakout 그룹 → LOW (기존 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_filtered_stocks_breakout_group_is_low():
    """subscribe_filtered_stocks 의 breakout 그룹은 LOW + bypass_limit=False.

    사이클 7-B 이후 기존 동작 — 회귀 0 확인.
    """
    from src.engine.scanner import subscribe_filtered_stocks
    from src.realtime import websocket_pool as wp_mod
    import src.engine.scanner as scanner_mod

    sub_calls: list[dict] = []

    async def fake_subscribe(tr_id, tr_key, *, priority="LOW", bypass_limit=False):
        sub_calls.append({
            "tr_id": tr_id, "tr_key": tr_key,
            "priority": priority, "bypass_limit": bypass_limit,
        })
        return priority.lower()

    original_sub = wp_mod.kis_ws_pool.subscribe
    wp_mod.kis_ws_pool.subscribe = fake_subscribe
    # kis_ws._subscriptions mock for remaining-slots check
    import src.engine.scanner as scanner_mod2
    original_subscriptions = getattr(scanner_mod2.kis_ws, "_subscriptions", set())
    scanner_mod2.kis_ws._subscriptions = set()

    try:
        # 풀 비어있음 (신규 구독)
        original_get_subscribed = wp_mod.kis_ws_pool.get_subscribed_tickers
        wp_mod.kis_ws_pool.get_subscribed_tickers = lambda: set()

        priority_groups = {
            "positions": [],
            "next_day_clear": [],
            "breakout": ["036930", "005935", "439960"],
            "momentum": [],
            "swing": [],
        }
        await subscribe_filtered_stocks(
            tickers=[], extra_tickers=[],
            priority_groups=priority_groups,
        )
    finally:
        wp_mod.kis_ws_pool.subscribe = original_sub
        wp_mod.kis_ws_pool.get_subscribed_tickers = original_get_subscribed
        scanner_mod2.kis_ws._subscriptions = original_subscriptions

    breakout_calls = [c for c in sub_calls if c["tr_key"] in {"036930", "005935", "439960"}]
    assert len(breakout_calls) == 3, (
        f"breakout 3건 모두 구독 호출 필요. got={len(breakout_calls)}"
    )
    for call in breakout_calls:
        assert call["priority"] == "LOW", (
            f"breakout 종목 {call['tr_key']} 는 LOW. got={call['priority']}"
        )
        assert call["bypass_limit"] is False, (
            f"breakout 종목 {call['tr_key']} 는 bypass_limit=False. got={call['bypass_limit']}"
        )


# ===========================================================================
# Case 5: subscribe_filtered_stocks positions 그룹 → HIGH (기존 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_filtered_stocks_positions_group_is_high():
    """subscribe_filtered_stocks 의 positions 그룹은 HIGH + bypass_limit=True.

    기존 동작 보존 — 회귀 0 확인.
    """
    from src.engine.scanner import subscribe_filtered_stocks
    from src.realtime import websocket_pool as wp_mod
    import src.engine.scanner as scanner_mod3

    sub_calls: list[dict] = []

    async def fake_subscribe(tr_id, tr_key, *, priority="LOW", bypass_limit=False):
        sub_calls.append({
            "tr_id": tr_id, "tr_key": tr_key,
            "priority": priority, "bypass_limit": bypass_limit,
        })
        return priority.lower()

    original_sub = wp_mod.kis_ws_pool.subscribe
    wp_mod.kis_ws_pool.subscribe = fake_subscribe
    original_subscriptions = getattr(scanner_mod3.kis_ws, "_subscriptions", set())
    scanner_mod3.kis_ws._subscriptions = set()

    try:
        original_get_subscribed = wp_mod.kis_ws_pool.get_subscribed_tickers
        wp_mod.kis_ws_pool.get_subscribed_tickers = lambda: set()

        priority_groups = {
            "positions": ["253840", "142280"],
            "next_day_clear": [],
            "breakout": [],
            "momentum": [],
            "swing": [],
        }
        await subscribe_filtered_stocks(
            tickers=[], extra_tickers=[],
            priority_groups=priority_groups,
        )
    finally:
        wp_mod.kis_ws_pool.subscribe = original_sub
        wp_mod.kis_ws_pool.get_subscribed_tickers = original_get_subscribed
        scanner_mod3.kis_ws._subscriptions = original_subscriptions

    pos_calls = [c for c in sub_calls if c["tr_key"] in {"253840", "142280"}]
    assert len(pos_calls) == 2, (
        f"positions 2건 모두 구독 호출 필요. got={len(pos_calls)}"
    )
    for call in pos_calls:
        assert call["priority"] == "HIGH", (
            f"positions 종목 {call['tr_key']} 는 HIGH. got={call['priority']}"
        )
        assert call["bypass_limit"] is True, (
            f"positions 종목 {call['tr_key']} 는 bypass_limit=True. got={call['bypass_limit']}"
        )


# ===========================================================================
# Case 6: 혼합 — positions HIGH + 후보 LOW 분리
# ===========================================================================
@pytest.mark.asyncio
async def test_mixed_stale_positions_high_candidates_low():
    """positions 1 + 후보 3 stale 혼합 → positions=HIGH, 후보=LOW 분리.

    사이클 25-B 핵심 시나리오: 2026-05-20 14:58 사고 재현 방지.
    positions 종목은 HIGH 메인 보장, 후보 종목은 LOW 보조 분산.
    """
    position_tickers = ["253840"]         # 보유 1건
    candidate_tickers = ["036930", "005935", "439960"]  # 후보 3건 (사고 종목 일부)
    stale = position_tickers + candidate_tickers

    calls = await _run_resubscribe_stale_priority(
        stale_tickers=stale,
        position_tickers=position_tickers,
        ndc_tickers=[],
    )

    assert len(calls) == len(stale), (
        f"stale {len(stale)}건 모두 재구독 호출 필요. got={len(calls)}"
    )

    call_by_ticker = {c["tr_key"]: c for c in calls}

    # positions → HIGH
    for t in position_tickers:
        assert t in call_by_ticker, f"positions {t} 미호출"
        assert call_by_ticker[t]["priority"] == "HIGH", (
            f"positions {t} 는 HIGH. got={call_by_ticker[t]['priority']}"
        )
        assert call_by_ticker[t]["bypass_limit"] is True, (
            f"positions {t} 는 bypass_limit=True. got={call_by_ticker[t]['bypass_limit']}"
        )

    # 후보 → LOW
    for t in candidate_tickers:
        assert t in call_by_ticker, f"후보 {t} 미호출"
        assert call_by_ticker[t]["priority"] == "LOW", (
            f"후보 {t} 는 LOW. got={call_by_ticker[t]['priority']}"
        )
        assert call_by_ticker[t]["bypass_limit"] is False, (
            f"후보 {t} 는 bypass_limit=False. got={call_by_ticker[t]['bypass_limit']}"
        )
