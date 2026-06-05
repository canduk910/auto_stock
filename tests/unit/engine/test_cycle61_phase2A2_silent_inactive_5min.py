"""사이클 61 Phase 2-A2 Red — H 카테고리: silent inactive 5분 지속 판정 (1 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (H-1)
> **선례**: 기존 `tests/unit/engine/test_session_silent_inactive_ratio.py` 답습.

`_detect_silent_inactive_sessions` — 4분 30s = 미감지 / 5분 = 감지.

검증:
1. first_seen=10:00:00 - 4분 30s, fresh_ratio < 0.2 + sub >= 5 시나리오 → silent_labels 미포함
2. first_seen=10:00:00 - 5분, 같은 시나리오 → silent_labels 포함
   (SILENT_INACTIVE_PERSIST_SECS=300.0 임계)

Red 단계: A2 4 함수 미이주 상태 → 본 케이스는 기존 함수 동작에 의존 (사이클 24 기존
로직 보존 검증).

회귀 가드: CLAUDE.md 절대 깨지 말 것 — 5분 지속 임계 보존 (단발 끊김 즉시 close 차단).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    return sched


def _make_silent_session_status(label: str, subscribed_tickers: list[str]):
    """silent inactive 의심 세션 status (sub>=5, fresh=0 — last_tick 없음 시나리오)."""
    return [{
        "label": label,
        "subscribed": len(subscribed_tickers),
        "tickers": {"subscribed": subscribed_tickers},
    }]


def test_H1_silent_inactive_5min_threshold_boundary_freezegun():
    """H-1: 4분 30s = 미감지 / 5분 정각 = 감지 (SILENT_INACTIVE_PERSIST_SECS=300.0 임계).

    단일 케이스 — 두 시각의 임계 boundary 동시 검증.
    """
    from src.engine import stale_manager  # noqa: F401 — Red: AttributeError 가능 (위임 시점)

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    subscribed_tickers = ["005930", "000660", "009150", "035720", "035420"]
    session_status = _make_silent_session_status("main", subscribed_tickers)

    # 분기 1 — 4분 30s 경과 (5분 미달)
    sched1 = _make_scheduler()
    sched1._silent_inactive_first_seen["main"] = base - timedelta(minutes=4, seconds=30)

    with freeze_time(base), \
         patch("src.engine.scheduler.kis_ws_pool") as mock_pool, \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        mock_pool.get_session_status = MagicMock(return_value=session_status)
        silent_labels_4m30s = sched1._detect_silent_inactive_sessions()

    assert "main" not in silent_labels_4m30s, (
        "4분 30s 경과 시 silent_labels 미포함 (5분 임계 미달 — 단발 끊김 즉시 close 차단)"
    )

    # 분기 2 — 5분 정각 경과 (임계 도달)
    sched2 = _make_scheduler()
    sched2._silent_inactive_first_seen["main"] = base - timedelta(seconds=300)

    with freeze_time(base), \
         patch("src.engine.scheduler.kis_ws_pool") as mock_pool, \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        mock_pool.get_session_status = MagicMock(return_value=session_status)
        silent_labels_5m = sched2._detect_silent_inactive_sessions()

    assert "main" in silent_labels_5m, (
        "5분 정각 경과 시 silent_labels 포함 (SILENT_INACTIVE_PERSIST_SECS=300.0 임계)"
    )
