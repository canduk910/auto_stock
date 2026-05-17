"""사이클 9 (2026-05-18) — `WebsocketPool.disable_quote_session(label)` 회귀.

배경:
- `QuoteSessionHealthMonitor` 가 5회 연속 실패 / 5분 50% 실패율 감지 시 메모리 풀에서
  해당 보조 세션을 즉시 제거해야 함 (DB active=false 와 별개로).
- 다음 ``subscribe`` 호출은 자동 라운드로빈 (남은 보조 또는 메인 fallback).

검증 사양 (5 케이스):
- A: `disable_quote_session("quote-1")` → 첫 번째 보조 disconnect + `_quotes` 제거
- B: 추적 ticker 정리 — `_ticker_to_session` 에서 해당 세션 담당 ticker 모두 제거
- C: 없는 label → noop (idempotent)
- D: 메인 label ("main") → noop (안전 가드, 메인 비활성 절대 금지)
- E: 두 번째 호출 idempotent — 이미 제거됐어도 예외 없음
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def pool_with_two_quotes():
    """보조 2개 등록된 WebsocketPool 인스턴스 + mock disconnect."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    # 보조 세션 2개 mock — disconnect AsyncMock
    q1 = MagicMock()
    q1.disconnect = AsyncMock()
    q1._subscriptions = set()
    q2 = MagicMock()
    q2.disconnect = AsyncMock()
    q2._subscriptions = set()
    pool._quotes = [q1, q2]
    return pool, q1, q2


# ---------------------------------------------------------------------------
# 사양 A — quote-1 비활성
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disable_quote_session_removes_target_from_quotes(pool_with_two_quotes):
    """`disable_quote_session("quote-1")` → 첫 보조 disconnect + `_quotes`에서 제거."""
    pool, q1, q2 = pool_with_two_quotes

    await pool.disable_quote_session("quote-1")

    q1.disconnect.assert_awaited_once()
    assert q1 not in pool._quotes
    assert q2 in pool._quotes  # 다른 보조는 보존
    assert len(pool._quotes) == 1


# ---------------------------------------------------------------------------
# 사양 B — 추적 ticker 정리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disable_quote_session_clears_tracked_tickers(pool_with_two_quotes):
    """`_ticker_to_session` 에서 비활성 세션 담당 ticker 모두 제거."""
    pool, q1, q2 = pool_with_two_quotes
    pool._ticker_to_session = {
        "005930": q1,
        "000660": q1,
        "035420": q2,  # 다른 보조는 보존
    }

    await pool.disable_quote_session("quote-1")

    assert "005930" not in pool._ticker_to_session
    assert "000660" not in pool._ticker_to_session
    assert pool._ticker_to_session.get("035420") is q2


# ---------------------------------------------------------------------------
# 사양 C — 없는 label 은 noop
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disable_quote_session_unknown_label_noop(pool_with_two_quotes):
    """존재하지 않는 label → 예외 없이 noop."""
    pool, q1, q2 = pool_with_two_quotes

    await pool.disable_quote_session("quote-99")  # 없는 label

    q1.disconnect.assert_not_called()
    q2.disconnect.assert_not_called()
    assert len(pool._quotes) == 2


# ---------------------------------------------------------------------------
# 사양 D — 메인 라벨 보호 가드
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disable_quote_session_main_label_noop(pool_with_two_quotes):
    """메인 라벨 ("main") → noop. 메인 세션 절대 비활성 안 됨."""
    pool, q1, q2 = pool_with_two_quotes
    main_disconnect = AsyncMock()
    pool._main.disconnect = main_disconnect

    await pool.disable_quote_session("main")

    main_disconnect.assert_not_called()
    # 보조 세션은 그대로
    assert len(pool._quotes) == 2


# ---------------------------------------------------------------------------
# 사양 E — 두 번째 호출 idempotent
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disable_quote_session_idempotent(pool_with_two_quotes):
    """두 번째 호출 — 이미 제거됐어도 예외 없음."""
    pool, q1, q2 = pool_with_two_quotes

    await pool.disable_quote_session("quote-1")
    await pool.disable_quote_session("quote-1")  # 두 번째 호출

    # 첫 호출에서 1회 disconnect, 두 번째는 noop
    assert q1.disconnect.await_count == 1
    assert q1 not in pool._quotes
