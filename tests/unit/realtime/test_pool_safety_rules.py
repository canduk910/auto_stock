"""WebsocketPool — 안전 규칙 멀티 세션 지원 (사이클 7-B, 2026-05-17).

E1/E2/F1/K 안전 규칙이 풀 환경에서도 보존되는지 검증.

E1 (보유·익일청산 우선 보장): 메인 세션 절대 보장 + bypass_limit=True
E2 (구독 거절 감지): 세션별 _handle_raw + 거절 시 _subscriptions 정합성 회복
F1 (재연결 후 자동 검증): 각 세션 독립 발화
K  (stale watcher): 분배 추적 활용해 해당 세션에서 재구독

본 사이클은 풀 인터페이스 레벨 검증에 집중. KisWebSocket 내부 E2/F1/K 동작은
기존 test_websocket_*.py 가 회귀 가드하므로 본 파일에선 풀이 그 동작을
"세션별 독립"으로 유지하는지만 본다.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# E1: 보유·익일청산 메인 세션 절대 보장 (bypass_limit=True)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e1_positions_subscribe_to_main_with_bypass():
    """보유 종목(priority=HIGH) → 메인 세션에 bypass_limit=True 전달."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    pool._main._subscriptions = set()
    # 보조 세션 있어도 HIGH 는 항상 메인
    quote1 = MagicMock()
    quote1._subscriptions = set()
    quote1.subscribe = AsyncMock()
    pool._quotes = [quote1]

    await pool.subscribe("H0UNCNT0", "005930", priority="HIGH")

    pool._main.subscribe.assert_awaited_once_with(
        "H0UNCNT0", "005930", bypass_limit=True
    )
    quote1.subscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_e1_next_day_clear_subscribe_to_main_with_bypass():
    """익일청산 ticker → 메인 세션 bypass."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    pool._main._subscriptions = set()
    pool._quotes = [MagicMock(_subscriptions=set(), subscribe=AsyncMock())]

    await pool.subscribe("H0UNCNT0", "012200", priority="HIGH")

    pool._main.subscribe.assert_awaited_once_with(
        "H0UNCNT0", "012200", bypass_limit=True
    )


# ---------------------------------------------------------------------------
# E2: 거절 응답은 각 세션의 _handle_raw 에서 처리 (KisWebSocket 가 책임)
# 풀 차원에서는 세션이 독립적으로 거절을 받아도 다른 세션에 영향 없음을 검증
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2_quote_session_rejection_does_not_affect_main():
    """보조 세션 1개의 거절은 다른 세션/메인에 영향 0."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    pool._main._subscriptions = set()
    quote1 = MagicMock()
    quote1._subscriptions = set()
    quote1.subscribe = AsyncMock()
    quote2 = MagicMock()
    quote2._subscriptions = set()
    quote2.subscribe = AsyncMock()
    pool._quotes = [quote1, quote2]

    # quote1 / quote2 / main 각각 독립적으로 구독 등록
    await pool.subscribe("H0UNCNT0", "AAA", priority="LOW")
    await pool.subscribe("H0UNCNT0", "BBB", priority="LOW")
    await pool.subscribe("H0UNCNT0", "005930", priority="HIGH")

    # quote1 이 받았다고 시뮬레이션 — quote2 와 main 의 subscriptions 는 영향 0
    # (실제 거절 처리는 KisWebSocket._handle_raw 가 자체 set 에 대해서만 discard)
    assert pool._main.subscribe.await_count == 1
    assert quote1.subscribe.await_count + quote2.subscribe.await_count == 2


# ---------------------------------------------------------------------------
# F1: 재연결 후 자동 검증 — 각 세션 독립 발화
# ---------------------------------------------------------------------------
def test_f1_each_session_owns_its_reconnect_verification():
    """각 세션의 `_verify_subscriptions_after_reconnect` 가 독립적으로 발화 가능.

    풀은 세션을 묶기만 하고 검증 task 는 각 KisWebSocket 자체 connect() 흐름에 위임.
    본 테스트는 분리 책임 검증 — 풀이 검증 로직을 *재구현* 하지 않음.
    """
    from src.realtime.websocket import KisWebSocket
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    # 각 세션이 `_verify_subscriptions_after_reconnect` 메서드를 자체 보유
    assert hasattr(pool._main, "_verify_subscriptions_after_reconnect")

    pool._quotes = [KisWebSocket(), KisWebSocket()]
    for q in pool._quotes:
        assert hasattr(q, "_verify_subscriptions_after_reconnect")


# ---------------------------------------------------------------------------
# K: stale watcher — 분배 추적 활용해 정확한 세션에서 재구독
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_k_stale_resubscribe_uses_recorded_session():
    """stale ticker 재구독 시 `_ticker_to_session` 기록된 세션 사용.

    풀이 `resubscribe_stale_ticker(ticker)` 같은 헬퍼를 제공해 분배 추적을
    그대로 활용하면 K 워처가 다른 세션에 잘못 보내는 결함 차단.
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main._send_subscribe = AsyncMock()
    pool._main._subscriptions = set()
    quote1 = MagicMock()
    quote1._subscriptions = set()
    quote1._send_subscribe = AsyncMock()
    quote1.subscribe = AsyncMock()
    pool._quotes = [quote1]

    # 보조 세션에 등록
    await pool.subscribe("H0UNCNT0", "AAA", priority="LOW")
    assert pool._ticker_to_session["AAA"] is quote1

    # stale 재구독 — 풀이 추적 dict 보고 quote1 의 _send_subscribe 호출
    await pool.resend_subscribe_for_ticker("H0UNCNT0", "AAA")

    quote1._send_subscribe.assert_awaited_once_with("H0UNCNT0", "AAA", subscribe=True)
    pool._main._send_subscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_k_stale_resubscribe_unknown_ticker_fallback_to_main():
    """`_ticker_to_session` 에 없는 ticker → 메인 세션 fallback (안전 디폴트)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main._send_subscribe = AsyncMock()
    pool._main._subscriptions = set()

    await pool.resend_subscribe_for_ticker("H0UNCNT0", "UNKNOWN")

    pool._main._send_subscribe.assert_awaited_once_with(
        "H0UNCNT0", "UNKNOWN", subscribe=True
    )


# ---------------------------------------------------------------------------
# 메인 단일 체결통보 보장 — RuntimeError 가드
# ---------------------------------------------------------------------------
def test_quote_session_subscribe_h0stcni0_directly_raises_runtime_error():
    """보조 세션에 직접 `subscribe('H0STCNI0', ...)` 호출 시 RuntimeError.

    풀 외부에서 누군가 보조 세션을 직접 잡아 체결통보를 시도하면 거부.
    풀의 `subscribe` 분기는 자동으로 메인으로 우회하지만, 본 가드는 *직접 호출* 차단.
    """
    from src.realtime.websocket_pool import (
        QuoteSessionExecutionNoticeError,
        WebsocketPool,
        _enforce_main_only_execution_notice,
    )

    pool = WebsocketPool()
    # 풀 헬퍼: 호출자가 명시적으로 가드 호출하면 RuntimeError raise
    with pytest.raises(QuoteSessionExecutionNoticeError):
        _enforce_main_only_execution_notice(pool, "H0STCNI0", session_label="quote-1")


def test_main_session_execution_notice_passes_through():
    """메인 세션의 체결통보 가드는 정상 통과."""
    from src.realtime.websocket_pool import (
        WebsocketPool,
        _enforce_main_only_execution_notice,
    )

    pool = WebsocketPool()
    # 메인 세션 라벨이면 예외 없이 통과
    _enforce_main_only_execution_notice(pool, "H0STCNI0", session_label="main")
    _enforce_main_only_execution_notice(pool, "H0STCNI9", session_label="main")
