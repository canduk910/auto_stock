"""사이클 11 Red (2026-05-18) — `scanner.get_scan_status()` 풀 전체 카운트 가시화.

배경 (결함 A1, 운영 사고 2026-05-18 09:00 KRX 진입):
- 대시보드 ScanMonitor 의 `subscribed_count=0` / `tick_coverage_total=0` 으로 표시.
- 실제로는 31 종목이 보조 세션(ISA, `quote-1`)에 정상 구독 중 (fresh=12, stale=19).
- 사이클 7-C 풀 통합 후 `scanner.get_scan_status()` 가 여전히 `kis_ws._subscriptions`
  (메인 세션 단일) 만 카운트해 보조 세션 종목이 가시화되지 않는 결함.
- 운영자가 "조건검색현황에 현재가가 표시가 되지 않고 있어" 라고 인지한 실 원인.

본 사이클은 `scanner.get_scan_status()` 가 `kis_ws_pool` 의 풀 전체 헬퍼를 사용해
보조 세션 종목도 카운트하도록 수정한다. 기존 응답 키는 100% 보존 (프론트 영향 0).

4 케이스:
1. 풀 전체 카운트 — 메인 + 보조 합집합 size 가 `subscribed_count` / `tick_coverage_total` 에 반영
2. 메인 only fallback — 보조 0개일 때 기존 동작 회귀
3. fresh/stale 분류 — 보조 세션 종목도 ticker_last_tick 기준 정확히 분류
4. 응답 키 회귀 — `subscribed_tickers` / `subscribed_count` / `tick_coverage_*` 4 키 보존
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _make_quote_session(ticks: set[str] | None = None, acks: set[str] | None = None):
    """보조 세션 mock — `_subscriptions` / `_subscriptions_acked` set."""
    from src.engine.scanner import TICK_TR_ID

    ws = MagicMock(name="quote-session")
    ws._subscriptions = {(TICK_TR_ID, t) for t in (ticks or set())}
    ws._subscriptions_acked = {(TICK_TR_ID, t) for t in (acks or set())}
    return ws


@pytest.fixture
def reset_pool_and_scanner(monkeypatch):
    """매 테스트마다 풀 + scanner ticker_last_tick 격리."""
    from src.engine import scanner as scanner_module
    from src.realtime.websocket_pool import kis_ws_pool

    orig_main_subs = set(kis_ws_pool._main._subscriptions)
    orig_main_acked = set(getattr(kis_ws_pool._main, "_subscriptions_acked", set()))
    orig_quotes = list(kis_ws_pool._quotes)
    orig_last = dict(scanner_module.ticker_last_tick)
    orig_scan_result = list(scanner_module._last_scan_result)

    # 메인 세션을 mock 으로 교체 — 글로벌 인스턴스 오염 차단
    main_mock = MagicMock(name="main-session")
    main_mock._subscriptions = set()
    main_mock._subscriptions_acked = set()
    kis_ws_pool._main = main_mock
    kis_ws_pool._quotes = []
    scanner_module.ticker_last_tick.clear()
    scanner_module._last_scan_result = []

    yield kis_ws_pool

    # 복원
    from src.realtime.websocket import kis_ws as real_kis_ws
    kis_ws_pool._main = real_kis_ws
    real_kis_ws._subscriptions = orig_main_subs
    if hasattr(real_kis_ws, "_subscriptions_acked"):
        real_kis_ws._subscriptions_acked = orig_main_acked
    else:
        real_kis_ws._subscriptions_acked = orig_main_acked
    kis_ws_pool._quotes = orig_quotes
    scanner_module.ticker_last_tick.clear()
    scanner_module.ticker_last_tick.update(orig_last)
    scanner_module._last_scan_result = orig_scan_result


# ---------------------------------------------------------------------------
# Case 1: 풀 전체 카운트 — 메인 + 보조 합집합
# ---------------------------------------------------------------------------
def test_scan_status_counts_pool_total_including_quote_sessions(reset_pool_and_scanner):
    """메인 5 + 보조1 31 → subscribed_count=36, tick_coverage_total=36.

    운영 실측 결함 재현: 메인 0 + 보조 31 케이스도 본 가드로 차단됨.
    """
    from src.engine.scanner import TICK_TR_ID, get_scan_status

    pool = reset_pool_and_scanner
    main_ticks = {f"M{i:05d}" for i in range(5)}
    quote_ticks = {f"Q{i:05d}" for i in range(31)}

    pool._main._subscriptions = {(TICK_TR_ID, t) for t in main_ticks}
    pool._quotes = [_make_quote_session(ticks=quote_ticks)]

    status = get_scan_status()

    # 결함: 기존 코드는 메인 5만 반환. fix 후 36 반환해야 함.
    assert status["subscribed_count"] == 36
    assert status["tick_coverage_total"] == 36
    assert set(status["subscribed_tickers"]) == main_ticks | quote_ticks


# ---------------------------------------------------------------------------
# Case 2: 메인 only fallback — 보조 0개일 때 기존 동작 회귀
# ---------------------------------------------------------------------------
def test_scan_status_main_only_no_quotes_regression(reset_pool_and_scanner):
    """보조 0개 + 메인 3 종목 → subscribed_count=3 (사이클 7-C 회귀 보존).

    DB `kis_quote_accounts` 미등록 환경(현재 운영 기본) 에서도 결과가 동일해야 함.
    """
    from src.engine.scanner import TICK_TR_ID, get_scan_status

    pool = reset_pool_and_scanner
    pool._main._subscriptions = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
        (TICK_TR_ID, "035720"),
    }
    pool._quotes = []

    status = get_scan_status()
    assert status["subscribed_count"] == 3
    assert status["tick_coverage_total"] == 3
    assert set(status["subscribed_tickers"]) == {"005930", "000660", "035720"}


# ---------------------------------------------------------------------------
# Case 3: fresh/stale 분류 — 보조 세션 종목도 ticker_last_tick 기준 정확히 분류
# ---------------------------------------------------------------------------
def test_scan_status_fresh_stale_classification_across_pool(reset_pool_and_scanner):
    """메인 1 fresh + 보조 1 fresh + 보조 1 stale + 보조 1 missing(=stale).

    fresh=2, stale=2 — 보조 세션 종목도 정확히 분류돼야 함 (G3 회귀 보존).
    """
    from src.engine import scanner as scanner_module
    from src.engine.scanner import TICK_TR_ID, get_scan_status

    pool = reset_pool_and_scanner
    now = datetime.now(KST)

    pool._main._subscriptions = {(TICK_TR_ID, "005930")}
    pool._quotes = [_make_quote_session(
        ticks={"000660", "035720", "068270"}
    )]

    # last_tick: 005930 fresh, 000660 fresh, 035720 stale (120s 전), 068270 없음
    scanner_module.ticker_last_tick["005930"] = now - timedelta(seconds=10)
    scanner_module.ticker_last_tick["000660"] = now - timedelta(seconds=20)
    scanner_module.ticker_last_tick["035720"] = now - timedelta(seconds=120)

    status = get_scan_status()
    assert status["tick_coverage_total"] == 4
    assert status["tick_coverage_fresh"] == 2  # 005930 + 000660
    assert status["tick_coverage_stale"] == 2  # 035720 + 068270


# ---------------------------------------------------------------------------
# Case 4: 응답 키 회귀 보존
# ---------------------------------------------------------------------------
def test_scan_status_response_keys_preserved(reset_pool_and_scanner):
    """기존 응답 4 키 + G3 tick_coverage 4 키 모두 보존되어야 함 (프론트 호환)."""
    from src.engine.scanner import TICK_TR_ID, get_scan_status

    pool = reset_pool_and_scanner
    pool._main._subscriptions = {(TICK_TR_ID, "005930")}
    pool._quotes = [_make_quote_session(ticks={"000660"})]

    status = get_scan_status()
    # 기존 키
    for key in (
        "filtered_tickers", "filtered_count",
        "subscribed_tickers", "subscribed_count",
        "last_scan_time", "ticker_names", "ticker_prices", "ticker_market_info",
    ):
        assert key in status, f"기존 응답 키 누락: {key}"
    # G3 키 4종
    for key in (
        "tick_coverage_total", "tick_coverage_acked",
        "tick_coverage_fresh", "tick_coverage_stale",
    ):
        assert key in status, f"tick_coverage 키 누락: {key}"

    # subscribed_count 와 tick_coverage_total 은 동일 값 (의미 분리지만 값 일치)
    assert status["subscribed_count"] == status["tick_coverage_total"]
