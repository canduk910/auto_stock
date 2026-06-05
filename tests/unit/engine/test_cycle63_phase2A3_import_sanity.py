"""사이클 63 Phase 2-A3 Red — M 카테고리: import sanity (1 케이스).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 M
> **선례**: 사이클 60 A1 / 사이클 61 A2 `import_sanity` 답습.

A3 2 함수 (`check_and_resubscribe_stale` / `resubscribe_stale_priority`) 노출 +
async coroutine 검증. A3 추가 상수 0 (사이클 60+61 누적 10 상수 그대로).

Red 단계: stale_manager 에 A3 2 함수 미존재 → AssertionError 정상.

회귀 가드: A1 5 + A2 4 함수 보존 + A3 2 함수 신규 (총 11 함수) + 10 상수 보존.
"""
from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.unit


def test_M1_stale_manager_exposes_a3_two_async_functions():
    """M-1: `from src.engine import stale_manager` 후 A3 2 함수 노출 (async).

    A1 (사이클 60) 5 함수 + A2 (사이클 61) 4 함수 보존 + A3 (사이클 63) 2 함수 신규.
    A3 2 함수 모두 async coroutine 의무 (K stale watcher 본체 + 5분 우선 재구독).
    """
    from src.engine import stale_manager

    # ── A1 5 함수 (사이클 60 보존) ──
    a1_functions = (
        "build_session_subscription_view",
        "emit_stale_session_detail",
        "refresh_stale_ccnl_cache",
        "evict_expired_ccnl",
        "prune_force_retry_history",
    )
    for fname in a1_functions:
        assert hasattr(stale_manager, fname), (
            f"A1 함수 {fname} 노출 누락 — 사이클 60 영속 회귀"
        )

    # ── A2 4 함수 (사이클 61 보존) ──
    a2_functions = (
        "detect_silent_inactive_sessions",
        "force_reconnect_session",
        "delta_unsubscribe_dropped",
        "evaluate_universe_guard",
    )
    for fname in a2_functions:
        assert hasattr(stale_manager, fname), (
            f"A2 함수 {fname} 노출 누락 — 사이클 61 영속 회귀"
        )

    # ── A3 2 함수 (사이클 63 신규 추가) ──
    a3_functions = (
        "check_and_resubscribe_stale",
        "resubscribe_stale_priority",
    )
    for fname in a3_functions:
        assert hasattr(stale_manager, fname), (
            f"A3 함수 {fname} 노출 누락 — 사이클 63 Green 단계 추가 의무"
        )
        assert callable(getattr(stale_manager, fname)), f"{fname} callable 의무"
        assert asyncio.iscoroutinefunction(getattr(stale_manager, fname)), (
            f"{fname} async coroutine 의무 — K stale watcher 본체 + Rate Limit sleep"
        )

    # ── A1+A2 10 상수 보존 (A3 추가 상수 0) ──
    assert stale_manager.MAX_STALE_RETRIES == 5
    assert stale_manager.STALE_FORCE_RETRY_AFTER_SECS == 300
    assert stale_manager.STALE_FORCE_RETRY_HOURLY_CAP == 12
    assert stale_manager.UNIVERSE_LOW_VOLUME_THRESHOLD == 10_000
    assert stale_manager.SILENT_INACTIVE_FRESH_RATIO_THRESHOLD == 0.2
    assert stale_manager.STALE_FRESHNESS_SECS == 60
    assert stale_manager.SILENT_INACTIVE_MIN_SUBSCRIBED == 5
    assert stale_manager.SILENT_INACTIVE_PERSIST_SECS == 300.0
    assert stale_manager.SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR == 2
    assert stale_manager.SILENT_INACTIVE_RECOVERY_WINDOW_SECS == 3600.0
