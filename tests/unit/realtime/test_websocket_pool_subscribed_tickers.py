"""사이클 11 Red (2026-05-18) — `WebsocketPool` 풀 전체 헬퍼 통합 검증.

배경 (결함 A1):
- `scanner.get_scan_status()` 가 `kis_ws._subscriptions` (메인 단일) 만 카운트.
- 사이클 7-C 풀 통합 후 보조 세션(quote-1 등) 31 종목이 가시화되지 않는 결함.
- 본 사이클은 `kis_ws_pool.get_subscribed_tickers()` / `get_acked_tickers()` 가
  메인 + 보조 합집합을 정확히 반환한다는 사양을 명시적으로 가드한다.

기존 `tests/unit/realtime/test_websocket_pool.py::test_get_subscribed_tickers_*` 가
일부 합집합을 다루지만, 사이클 11 은 다음 5 케이스를 추가 검증한다:

1. 메인 only (보조 0개) → set 정확
2. 보조 only (메인 0개) → set 정확
3. 메인 + 보조 양쪽 모두 있을 때 합집합 정확
4. 메인 + 보조에 같은 ticker 중복 → 단일 set 원소 (dedupe)
5. `_subscriptions` vs `_subscriptions_acked` 분리 (SEND vs ACK)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


def _make_quote_session(ticks: set[str] | None = None, acks: set[str] | None = None):
    """보조 세션 mock — `_subscriptions` / `_subscriptions_acked` set 보유."""
    from src.engine.scanner import TICK_TR_ID

    ws = MagicMock(name="quote-session")
    ws._subscriptions = {(TICK_TR_ID, t) for t in (ticks or set())}
    ws._subscriptions_acked = {(TICK_TR_ID, t) for t in (acks or set())}
    return ws


@pytest.fixture
def fresh_pool(monkeypatch):
    """매 테스트마다 격리된 WebsocketPool — 메인 세션 mock 으로 교체."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    # 메인 세션도 mock 으로 교체 — 실 websocket 인스턴스의 글로벌 상태 오염 차단
    main_mock = MagicMock(name="main-session")
    main_mock._subscriptions = set()
    main_mock._subscriptions_acked = set()
    pool._main = main_mock
    return pool


# ---------------------------------------------------------------------------
# Case 1: 메인 only (보조 0개) → 메인 _subscriptions 가 그대로 노출
# ---------------------------------------------------------------------------
def test_get_subscribed_tickers_main_only(fresh_pool):
    """보조 0개 + 메인에 3 종목 → set 3개."""
    from src.engine.scanner import TICK_TR_ID

    pool = fresh_pool
    pool._main._subscriptions = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
        (TICK_TR_ID, "035720"),
    }
    pool._quotes = []

    result = pool.get_subscribed_tickers()
    assert result == {"005930", "000660", "035720"}


# ---------------------------------------------------------------------------
# Case 2: 보조 only (메인 0개) → 보조 _subscriptions 가 노출
# ---------------------------------------------------------------------------
def test_get_subscribed_tickers_quotes_only(fresh_pool):
    """메인 빈 set + 보조 1개에 31 종목 → set 31개 (운영 실측 케이스)."""
    pool = fresh_pool
    quote_tickers = {f"00{i:04d}" for i in range(31)}
    pool._quotes = [_make_quote_session(ticks=quote_tickers)]

    result = pool.get_subscribed_tickers()
    assert len(result) == 31
    assert result == quote_tickers


# ---------------------------------------------------------------------------
# Case 3: 메인 + 보조 합집합
# ---------------------------------------------------------------------------
def test_get_subscribed_tickers_main_plus_quotes_union(fresh_pool):
    """메인 10 + 보조1 15 + 보조2 5 → 합집합 30 (중복 없음 가정)."""
    from src.engine.scanner import TICK_TR_ID

    pool = fresh_pool
    main_ticks = {f"M{i:05d}" for i in range(10)}
    quote1_ticks = {f"Q1_{i:04d}" for i in range(15)}
    quote2_ticks = {f"Q2_{i:04d}" for i in range(5)}

    pool._main._subscriptions = {(TICK_TR_ID, t) for t in main_ticks}
    pool._quotes = [
        _make_quote_session(ticks=quote1_ticks),
        _make_quote_session(ticks=quote2_ticks),
    ]

    result = pool.get_subscribed_tickers()
    assert len(result) == 30
    assert result == main_ticks | quote1_ticks | quote2_ticks


# ---------------------------------------------------------------------------
# Case 4: 같은 ticker 중복 → set dedupe
# ---------------------------------------------------------------------------
def test_get_subscribed_tickers_dedupe_when_same_in_main_and_quote(fresh_pool):
    """메인에 005930, 보조에도 005930 → set 원소 1개 (정상 dedupe).

    실 운영에서는 풀이 `_ticker_to_session` 으로 중복 방지하지만, set 합집합 헬퍼는
    원소 단위 dedupe 가 책임. 외부에서 직접 모의 중복 set 을 만들어도 안전해야 함.
    """
    from src.engine.scanner import TICK_TR_ID

    pool = fresh_pool
    pool._main._subscriptions = {(TICK_TR_ID, "005930"), (TICK_TR_ID, "000660")}
    pool._quotes = [_make_quote_session(ticks={"005930", "035720"})]

    result = pool.get_subscribed_tickers()
    assert result == {"005930", "000660", "035720"}
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Case 5: ACK set 분리 — _subscriptions vs _subscriptions_acked
# ---------------------------------------------------------------------------
def test_get_acked_tickers_separates_send_vs_ack(fresh_pool):
    """`get_acked_tickers()` 는 ACK 받은 set 만 합집합 — SEND 만 한 set 제외.

    G1 ACK 추적 정책상 SEND 한 종목은 _subscriptions, 응답 받은 종목은
    _subscriptions_acked. 풀 헬퍼도 이 분리를 유지해야 함.
    """
    from src.engine.scanner import TICK_TR_ID

    pool = fresh_pool
    # 메인: SEND 3, ACK 2
    pool._main._subscriptions = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
        (TICK_TR_ID, "035720"),
    }
    pool._main._subscriptions_acked = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
    }
    # 보조: SEND 2, ACK 1
    pool._quotes = [_make_quote_session(
        ticks={"068270", "012330"},
        acks={"068270"},
    )]

    subscribed = pool.get_subscribed_tickers()
    acked = pool.get_acked_tickers()

    assert subscribed == {"005930", "000660", "035720", "068270", "012330"}
    assert acked == {"005930", "000660", "068270"}
    assert acked < subscribed  # 진부분집합 — SEND 후 미응답 종목 존재
