"""Cycle 7-C Red — K stale watcher 의 풀 통합.

`_check_and_resubscribe_stale` 가 단일 세션 직접 호출 대신
`kis_ws_pool.resend_subscribe_for_ticker` / `kis_ws_pool.unsubscribe_in_pool` 사용.

분배 추적 dict(`_ticker_to_session`) 활용해 정확한 세션에 재전송.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def reset_stale_state():
    """매 테스트 시작 시 scanner.ticker_last_tick 초기화."""
    from src.engine import scanner

    saved = dict(scanner.ticker_last_tick)
    scanner.ticker_last_tick.clear()
    yield
    scanner.ticker_last_tick.clear()
    scanner.ticker_last_tick.update(saved)


# ---------------------------------------------------------------------------
# D-1. 보조 0개 — resend_subscribe_for_ticker 가 메인으로 폴백
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_calls_pool_resend(monkeypatch, reset_stale_state):
    """stale ticker 1회 → `pool.resend_subscribe_for_ticker(tr_id, ticker)` 호출."""
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.realtime import websocket_pool as wp_mod

    # subscribed 1개, stale 상태
    monkeypatch.setattr(
        sched_mod.kis_ws, "get_subscribed_tickers",
        lambda: {"005930"}, raising=False,
    )
    # 60초 이전 마지막 tick → stale
    from src.engine.scanner import KST_TZ
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ) - timedelta(seconds=120)

    pool_resend_spy = AsyncMock()
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "resend_subscribe_for_ticker", pool_resend_spy, raising=False,
    )
    # 일반 _send_subscribe 도 mock (legacy 경로 차단 검증용)
    legacy_spy = AsyncMock()
    monkeypatch.setattr(sched_mod.kis_ws, "_send_subscribe", legacy_spy, raising=False)

    sched = sched_mod.TradingScheduler()
    await sched._check_and_resubscribe_stale()

    # pool 경로 1회 호출
    assert pool_resend_spy.await_count >= 1, (
        f"풀의 resend_subscribe_for_ticker 가 호출되어야 함, 실제={pool_resend_spy.await_count}"
    )


# ---------------------------------------------------------------------------
# D-2. 분배 추적 활용 — 보조 세션에 등록된 ticker 는 해당 세션으로 재전송
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_uses_ticker_to_session_routing(monkeypatch, reset_stale_state):
    """`_ticker_to_session[ticker]` 가 quote-1 세션이면 그 세션 `_send_subscribe` 호출."""
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.realtime import websocket_pool as wp_mod
    from src.engine.scanner import KST_TZ

    monkeypatch.setattr(
        sched_mod.kis_ws, "get_subscribed_tickers",
        lambda: {"005930"}, raising=False,
    )
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ) - timedelta(seconds=120)

    # 풀 분배 추적 — 005930 은 가짜 quote-1 세션에 등록되었음
    fake_quote_session = type("FakeWS", (), {})()
    fake_quote_session._send_subscribe = AsyncMock()
    fake_quote_session._subscriptions = {("H0UNCNT0", "005930")}

    wp_mod.kis_ws_pool._ticker_to_session = {"005930": fake_quote_session}

    # 실제 resend_subscribe_for_ticker 가 호출되어야
    sched = sched_mod.TradingScheduler()
    await sched._check_and_resubscribe_stale()

    # quote-1 의 _send_subscribe 가 호출됨
    assert fake_quote_session._send_subscribe.await_count >= 1, (
        "분배 추적된 세션의 _send_subscribe 가 호출되어야 함"
    )

    # cleanup
    wp_mod.kis_ws_pool._ticker_to_session.clear()


# ---------------------------------------------------------------------------
# D-3. 강제 재등록 (retry > 5) — unsubscribe_in_pool + subscribe(priority)
# 사이클 13 (2026-05-18): 임계 STALE_FORCE_REREGISTER_AFTER 10 → 5 단축
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_force_reregister_via_pool(monkeypatch, reset_stale_state):
    """retry > 5 시 `pool.unsubscribe_in_pool` + `pool.subscribe(priority='HIGH', bypass_limit=True)` 호출."""
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.realtime import websocket_pool as wp_mod
    from src.engine.scanner import KST_TZ

    monkeypatch.setattr(
        sched_mod.kis_ws, "get_subscribed_tickers",
        lambda: {"005930"}, raising=False,
    )
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ) - timedelta(seconds=120)

    pool_unsub_spy = AsyncMock()
    pool_sub_spy = AsyncMock()
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "unsubscribe_in_pool", pool_unsub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "subscribe", pool_sub_spy, raising=False,
    )

    sched = sched_mod.TradingScheduler()
    # retry 6회로 시작 (사이클 13 임계 5 → 6 진입 force 트리거)
    sched._stale_retry_count["005930"] = 5
    await sched._check_and_resubscribe_stale()

    # pool 의 unsubscribe + subscribe 호출
    assert pool_unsub_spy.await_count >= 1, "강제 재등록 시 pool.unsubscribe_in_pool 호출 필요"
    assert pool_sub_spy.await_count >= 1, "강제 재등록 시 pool.subscribe(priority=...) 호출 필요"


# ---------------------------------------------------------------------------
# D-4. retry > 10 → skip
# 사이클 13 (2026-05-18): 임계 *2 = 20 → 10 단축
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_skips_when_retry_exceeds_6(monkeypatch, reset_stale_state):
    """retry > STALE_FORCE_REREGISTER_AFTER*2 (=10) 시 skip — 호출 0."""
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.realtime import websocket_pool as wp_mod
    from src.engine.scanner import KST_TZ

    monkeypatch.setattr(
        sched_mod.kis_ws, "get_subscribed_tickers",
        lambda: {"005930"}, raising=False,
    )
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ) - timedelta(seconds=120)

    pool_unsub_spy = AsyncMock()
    pool_sub_spy = AsyncMock()
    pool_resend_spy = AsyncMock()
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "unsubscribe_in_pool", pool_unsub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "subscribe", pool_sub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "resend_subscribe_for_ticker", pool_resend_spy, raising=False,
    )

    sched = sched_mod.TradingScheduler()
    sched._stale_retry_count["005930"] = 11  # >10 — skip
    await sched._check_and_resubscribe_stale()

    # 모든 풀 호출이 0
    assert pool_unsub_spy.await_count == 0
    assert pool_sub_spy.await_count == 0
    assert pool_resend_spy.await_count == 0


# ---------------------------------------------------------------------------
# D-5. 전체 fresh — _stale_retry_count.clear()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_clears_retry_when_all_fresh(monkeypatch, reset_stale_state):
    """전체 fresh 일 때 누적 retry 카운터 자동 리셋."""
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.engine.scanner import KST_TZ

    monkeypatch.setattr(
        sched_mod.kis_ws, "get_subscribed_tickers",
        lambda: {"005930", "000660"}, raising=False,
    )
    # 모두 fresh (방금 tick)
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ)
    scanner.ticker_last_tick["000660"] = datetime.now(KST_TZ)

    sched = sched_mod.TradingScheduler()
    sched._stale_retry_count = {"005930": 2, "000660": 1}

    await sched._check_and_resubscribe_stale()

    assert sched._stale_retry_count == {}, (
        f"전체 fresh 시 retry 카운터 clear, 실제={sched._stale_retry_count}"
    )
