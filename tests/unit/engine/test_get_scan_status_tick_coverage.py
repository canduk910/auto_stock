"""scanner.get_scan_status() tick_coverage 4종 키 노출 (G3 백엔드, 2026-05-12).

배경: `/api/trading/status` 의 `scan` 필드는 scanner.get_scan_status() 가 만든다.
G1/G2 로 가시화된 ACK/fresh/stale 카운트를 status 응답에도 동봉해 프론트가
별도 호출 없이 사용 가능하도록 한다.

추가 키:
- `tick_coverage_total: int`  — TICK 구독 size (= subscribed_count 와 동일 값이지만 의미 분리)
- `tick_coverage_acked: int`  — _subscriptions_acked TICK 필터 size
- `tick_coverage_fresh: int`  — 최근 60s 내 tick 수신 카운트
- `tick_coverage_stale: int`  — 60s 미수신 카운트

기존 `subscribed_count` / `subscribed_tickers` / `filtered_tickers` 등 보존.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit


KST = timezone(timedelta(hours=9))


@pytest.fixture(autouse=True)
def _reset_scanner_state():
    """ticker_last_tick + ws subscriptions 격리."""
    from src.engine import scanner as scanner_module
    from src.realtime.websocket import kis_ws

    orig_last = dict(scanner_module.ticker_last_tick)
    orig_subs = set(kis_ws._subscriptions)
    orig_acked = set(getattr(kis_ws, "_subscriptions_acked", set()))

    scanner_module.ticker_last_tick.clear()
    kis_ws._subscriptions = set()
    if hasattr(kis_ws, "_subscriptions_acked"):
        kis_ws._subscriptions_acked.clear()
    else:
        kis_ws._subscriptions_acked = set()

    yield

    scanner_module.ticker_last_tick.clear()
    scanner_module.ticker_last_tick.update(orig_last)
    kis_ws._subscriptions = orig_subs
    kis_ws._subscriptions_acked = orig_acked


# ---------------------------------------------------------------------------
# Case J — 4개 신규 키 모두 존재 + 정확한 값
# ---------------------------------------------------------------------------
def test_case_j_get_scan_status_includes_tick_coverage_keys():
    from src.engine import scanner as scanner_module
    from src.engine.scanner import TICK_TR_ID, get_scan_status
    from src.realtime.websocket import kis_ws

    now = datetime.now(KST)
    kis_ws._subscriptions = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
        (TICK_TR_ID, "035720"),
    }
    kis_ws._subscriptions_acked = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
    }
    scanner_module.ticker_last_tick["005930"] = now - timedelta(seconds=10)  # fresh
    scanner_module.ticker_last_tick["000660"] = now - timedelta(seconds=120)  # stale (>60s)
    # 035720 은 ticker_last_tick 없음 → stale

    status = get_scan_status()

    # 4개 신규 키 모두 존재
    assert "tick_coverage_total" in status
    assert "tick_coverage_acked" in status
    assert "tick_coverage_fresh" in status
    assert "tick_coverage_stale" in status

    # 정확한 값
    assert status["tick_coverage_total"] == 3
    assert status["tick_coverage_acked"] == 2
    assert status["tick_coverage_fresh"] == 1
    assert status["tick_coverage_stale"] == 2


# ---------------------------------------------------------------------------
# Case K — 기존 `subscribed_count` / `subscribed_tickers` 키 보존
# ---------------------------------------------------------------------------
def test_case_k_existing_subscribed_count_preserved():
    """G3 추가가 기존 `subscribed_count` / `subscribed_tickers` 의 의미를
    바꾸지 않아야 함 (프론트 호환성)."""
    from src.engine.scanner import TICK_TR_ID, get_scan_status
    from src.realtime.websocket import kis_ws

    kis_ws._subscriptions = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
    }

    status = get_scan_status()

    # 기존 키 존재
    assert "subscribed_count" in status
    assert "subscribed_tickers" in status
    assert "filtered_count" in status
    assert "filtered_tickers" in status

    assert status["subscribed_count"] == 2
    # tick_coverage_total 과 subscribed_count 는 동일 값
    assert status["tick_coverage_total"] == status["subscribed_count"]


# ---------------------------------------------------------------------------
# Case 추가 — 빈 구독 상태에서도 키 4개 모두 0 으로 노출
# ---------------------------------------------------------------------------
def test_empty_subscription_returns_zero_coverage_keys():
    from src.engine.scanner import get_scan_status

    status = get_scan_status()
    assert status["tick_coverage_total"] == 0
    assert status["tick_coverage_acked"] == 0
    assert status["tick_coverage_fresh"] == 0
    assert status["tick_coverage_stale"] == 0
