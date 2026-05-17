"""WebsocketPool 통합 분배 시뮬레이션 — 사이클 7-B (2026-05-17).

5 세션 mock 풀에 종목 100건 분산 → 메인 41 + 보조 라운드로빈 검증.
일부 세션 disconnect 시 graceful 처리.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.integration


def _make_mock_session(label: str) -> MagicMock:
    """라운드로빈/슬롯 카운트를 흉내내는 mock KisWebSocket."""
    ws = MagicMock(name=label)
    ws._subscriptions = set()
    ws._subscriptions_acked = set()
    ws._reconnect_count = 0
    ws._ws = object()

    async def fake_subscribe(tr_id: str, tr_key: str, *, bypass_limit: bool = False):
        from src.realtime.websocket import MAX_SUBSCRIPTIONS

        if not bypass_limit and len(ws._subscriptions) >= MAX_SUBSCRIPTIONS:
            return
        ws._subscriptions.add((tr_id, tr_key))
        ws._subscriptions_acked.add((tr_id, tr_key))

    async def fake_unsubscribe(tr_id: str, tr_key: str):
        ws._subscriptions.discard((tr_id, tr_key))
        ws._subscriptions_acked.discard((tr_id, tr_key))

    ws.subscribe = AsyncMock(side_effect=fake_subscribe)
    ws.unsubscribe = AsyncMock(side_effect=fake_unsubscribe)
    ws._send_subscribe = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_pool_5_sessions_distribute_100_tickers_round_robin():
    """메인 + 보조 4 = 5 세션. HIGH 10 + LOW 90 = 100 종목 분산.

    분배 정책:
    - HIGH 10 → 메인 (bypass)
    - LOW 90 → 보조 4 세션 라운드로빈 (각 22~23개)
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    # 메인 세션을 mock 으로 교체
    pool._main = _make_mock_session("main")
    pool._quotes = [_make_mock_session(f"quote-{i}") for i in range(1, 5)]

    # HIGH 10 종목 (보유 + 익일청산 통합)
    high_tickers = [f"H{i:03d}" for i in range(10)]
    for t in high_tickers:
        await pool.subscribe("H0UNCNT0", t, priority="HIGH")

    # LOW 90 종목 (스캐닝)
    low_tickers = [f"L{i:03d}" for i in range(90)]
    for t in low_tickers:
        await pool.subscribe("H0UNCNT0", t, priority="LOW")

    # 메인엔 10 종목만
    main_keys = {t for tr_id, t in pool._main._subscriptions if tr_id == "H0UNCNT0"}
    assert main_keys == set(high_tickers)

    # 보조 세션 4개 합계 = 90
    total_low = sum(
        len({t for tr_id, t in q._subscriptions if tr_id == "H0UNCNT0"})
        for q in pool._quotes
    )
    assert total_low == 90

    # 라운드로빈으로 거의 균등 분포 (22~23 종목)
    for q in pool._quotes:
        size = len({t for tr_id, t in q._subscriptions if tr_id == "H0UNCNT0"})
        assert 22 <= size <= 23, f"라운드로빈 균등 — {q} 가 {size}개"


@pytest.mark.asyncio
async def test_pool_total_slot_capacity_is_41_times_session_count():
    """총 슬롯 = 41 × (1 + N). 보조 5 면 246 슬롯."""
    from src.realtime.websocket import MAX_SUBSCRIPTIONS
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _make_mock_session("main")
    pool._quotes = [_make_mock_session(f"quote-{i}") for i in range(1, 6)]

    expected_total = MAX_SUBSCRIPTIONS * 6  # 246
    # 246 종목 LOW 시도 → 메인 + 5 보조 모두 가득
    for i in range(expected_total):
        await pool.subscribe("H0UNCNT0", f"T{i:04d}", priority="LOW")

    # 247번째는 drop
    label = await pool.subscribe("H0UNCNT0", "OVERFLOW", priority="LOW")
    assert label is None, "246 초과 시 drop"


@pytest.mark.asyncio
async def test_pool_disconnect_one_quote_session_graceful():
    """일부 보조 세션이 disconnect 되어도 다른 세션 정상 동작.

    정책: disconnect 된 세션을 재분배하지 않음 (다음 _scan_loop 자연 회복에 위임).
    `_ws is None` 인 세션은 라운드로빈에서 건너뛴다.
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _make_mock_session("main")
    quote1 = _make_mock_session("quote-1")
    quote2 = _make_mock_session("quote-2")
    quote3 = _make_mock_session("quote-3")
    pool._quotes = [quote1, quote2, quote3]

    # quote2 가 disconnect 됨 (예: 토큰 만료)
    quote2._ws = None

    # 10 종목 LOW 시도 → quote1, quote3 만 받음
    for i in range(10):
        await pool.subscribe("H0UNCNT0", f"T{i:03d}", priority="LOW")

    assert len(quote2._subscriptions) == 0, "disconnect 세션은 구독 받지 않음"
    # quote1 + quote3 만 사용
    total = (
        len({t for tr_id, t in quote1._subscriptions if tr_id == "H0UNCNT0"})
        + len({t for tr_id, t in quote3._subscriptions if tr_id == "H0UNCNT0"})
    )
    assert total == 10


@pytest.mark.asyncio
async def test_pool_high_priority_main_full_still_succeeds_via_bypass():
    """메인 가득 + HIGH 추가 → bypass 로 메인 super-cap 진입."""
    from src.realtime.websocket import MAX_SUBSCRIPTIONS
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _make_mock_session("main")
    pool._quotes = []
    # 메인을 LOW 로 가득 채움
    for i in range(MAX_SUBSCRIPTIONS):
        await pool.subscribe("H0UNCNT0", f"F{i:03d}", priority="LOW")

    # HIGH 1개 — bypass 로 추가 성공
    label = await pool.subscribe("H0UNCNT0", "HELD", priority="HIGH")
    assert label == "main"

    held_keys = {t for tr_id, t in pool._main._subscriptions if tr_id == "H0UNCNT0"}
    assert "HELD" in held_keys
    assert len(pool._main._subscriptions) == MAX_SUBSCRIPTIONS + 1


@pytest.mark.asyncio
async def test_pool_zero_quotes_is_backward_compatible():
    """보조 0개 = 사이클 7-A 이전 동작과 동일.

    - LOW 도 메인으로
    - 메인이 41 가득 차면 drop (기존 동작 회귀)
    """
    from src.realtime.websocket import MAX_SUBSCRIPTIONS
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _make_mock_session("main")
    pool._quotes = []

    # 41 종목 LOW → 메인 가득
    for i in range(MAX_SUBSCRIPTIONS):
        await pool.subscribe("H0UNCNT0", f"T{i:03d}", priority="LOW")

    assert len(pool._main._subscriptions) == MAX_SUBSCRIPTIONS

    # 42번째 LOW → drop
    label = await pool.subscribe("H0UNCNT0", "OVERFLOW", priority="LOW")
    assert label is None


@pytest.mark.asyncio
async def test_pool_get_subscribed_tickers_aggregate_with_100_tickers():
    """100 종목 분산 후 `get_subscribed_tickers()` 합집합 100."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _make_mock_session("main")
    pool._quotes = [_make_mock_session(f"quote-{i}") for i in range(1, 4)]

    for i in range(100):
        priority = "HIGH" if i < 5 else "LOW"
        await pool.subscribe("H0UNCNT0", f"T{i:03d}", priority=priority)

    aggregate = pool.get_subscribed_tickers()
    assert len(aggregate) == 100
    assert all(f"T{i:03d}" in aggregate for i in range(100))
