"""사이클 61 Phase 2-A2 Red — L 카테고리: import sanity (1 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (L-1)
> **선례**: 사이클 60 A1 `test_H1_stale_manager_import_exposes_5_functions_5_constants_and_property_compat` 답습.

A2 4 함수 + A2 5 상수 노출 검증.

Red 단계: stale_manager 에 A2 4 함수 + A2 5 상수 미존재 → AssertionError 정상.

회귀 가드: A1 5 함수 + A1 5 상수 보존 + A2 4 함수 + A2 5 상수 추가 (총 9 함수 + 10 상수).
"""
from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.unit


def test_L1_stale_manager_exposes_a1_a2_all_9_functions_10_constants():
    """L-1: `from src.engine import stale_manager` 후 9 함수 + 10 상수 모두 노출.

    A1 (사이클 60) 5 함수 + 5 상수 — 보존 검증.
    A2 (사이클 61) 4 함수 + 5 상수 — 신규 추가 검증.
    """
    from src.engine import stale_manager

    # ── A1 5 함수 (사이클 60 이전 완료, 보존) ──
    a1_functions = (
        "build_session_subscription_view",
        "emit_stale_session_detail",
        "refresh_stale_ccnl_cache",
        "evict_expired_ccnl",
        "prune_force_retry_history",
    )
    for fname in a1_functions:
        assert hasattr(stale_manager, fname), (
            f"A1 함수 {fname} 노출 누락 — 사이클 60 보존 회귀"
        )
        assert callable(getattr(stale_manager, fname)), f"{fname} callable 의무"

    # ── A2 4 함수 (사이클 61 신규 추가) ──
    a2_functions = (
        "detect_silent_inactive_sessions",
        "force_reconnect_session",
        "delta_unsubscribe_dropped",
        "evaluate_universe_guard",
    )
    for fname in a2_functions:
        assert hasattr(stale_manager, fname), (
            f"A2 함수 {fname} 노출 누락 — 사이클 61 Green 단계 추가 의무"
        )
        assert callable(getattr(stale_manager, fname)), f"{fname} callable 의무"

    # async 함수 가드 — A2 3 함수는 async
    assert asyncio.iscoroutinefunction(
        stale_manager.force_reconnect_session
    ), "force_reconnect_session 는 async 여야 함"
    assert asyncio.iscoroutinefunction(
        stale_manager.delta_unsubscribe_dropped
    ), "delta_unsubscribe_dropped 는 async 여야 함"
    assert asyncio.iscoroutinefunction(
        stale_manager.evaluate_universe_guard
    ), "evaluate_universe_guard 는 async 여야 함"

    # ── A1 5 상수 (사이클 60 이전 완료, 보존) ──
    assert stale_manager.MAX_STALE_RETRIES == 5
    assert stale_manager.STALE_FORCE_RETRY_AFTER_SECS == 300
    assert stale_manager.STALE_FORCE_RETRY_HOURLY_CAP == 12
    assert stale_manager.UNIVERSE_LOW_VOLUME_THRESHOLD == 10_000
    assert stale_manager.SILENT_INACTIVE_FRESH_RATIO_THRESHOLD == 0.2

    # ── A2 5 상수 (사이클 61 신규 추가) ──
    assert stale_manager.SILENT_INACTIVE_MIN_SUBSCRIBED == 5, (
        "A2 신규 상수 SILENT_INACTIVE_MIN_SUBSCRIBED 미정의 또는 값 불일치"
    )
    assert stale_manager.SILENT_INACTIVE_PERSIST_SECS == 300.0, (
        "A2 신규 상수 SILENT_INACTIVE_PERSIST_SECS 미정의 또는 값 불일치"
    )
    assert stale_manager.SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR == 2, (
        "A2 신규 상수 SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR 미정의 또는 값 불일치 "
        "— KIS LMS/앱키 정지 위험 차단 상수"
    )
    assert stale_manager.SILENT_INACTIVE_RECOVERY_WINDOW_SECS == 3600.0, (
        "A2 신규 상수 SILENT_INACTIVE_RECOVERY_WINDOW_SECS 미정의 또는 값 불일치"
    )
    assert stale_manager.STALE_FRESHNESS_SECS == 60, (
        "A2 신규 상수 STALE_FRESHNESS_SECS 미정의 또는 값 불일치 "
        "— A1 lazy import 패턴 자연 해소 의무"
    )
