"""사이클 63 Phase 2-A3 Red — F 카테고리: dataclass 필드 누락 가드 (2 케이스).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 F
> **선례**: 사이클 60 A1 G-1 정정 / 사이클 61 A2 F-1/F-2 답습.

A3 추가 dataclass 필드 0 — 사이클 48 정의 7 필드 그대로 유지 검증 (회귀 가드).

신규 필드 추가 시 본 케이스 FAIL → reset_daily() 동행 reset 강제 유도.

Red 단계: 사이클 48 정의 + 사이클 60/61 영속 → PASS 가능 (회귀 가드).
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def test_F1_stale_tracker_state_has_exactly_seven_fields():
    """F-1: `StaleTrackerState` 7 필드 정확 일치 (사이클 48 정의 + A3 추가 0 보존).

    사이클 60 G-1 정정 사례 영구 가드 — 명세 "6 필드" → 실측 7 필드.
    A3 신규 필드 추가 시 본 테스트 FAIL → reset_daily() 동행 reset 강제 유도.
    """
    from src.engine.stale_tracker import StaleTrackerState

    fields = dataclasses.fields(StaleTrackerState)
    field_names = {f.name for f in fields}
    expected = {
        "retry_count",
        "last_resubscribe_at",
        "force_retry_history",
        "silent_inactive_first_seen",
        "silent_inactive_recovery_count",
        "universe_excluded_today",
        "last_ccnl_cache",
    }
    assert field_names == expected, (
        f"StaleTrackerState 필드 불일치 — 사이클 48 정의 7 필드 + A3 추가 0 보존 의무. "
        f"실측: {field_names}, 기대: {expected}. "
        f"신규 필드 추가 시 reset_daily() 도 동행 갱신 필요."
    )


def test_F2_reset_daily_clears_all_seven_fields_auto_detect():
    """F-2: `StaleTrackerState.reset_daily()` 호출 후 7 필드 모두 empty.

    `dataclasses.fields()` 자동 비교 — A3 / 사이클 64+ 신규 필드 추가 시 reset 누락
    사고 즉시 차단.
    """
    from src.engine.stale_tracker import StaleTrackerState

    state = StaleTrackerState()
    now = datetime(2026, 6, 5, 16, 0, 0, tzinfo=KST)

    # 7 필드 모두 임의 mutation
    state.retry_count["005930"] = 3
    state.last_resubscribe_at["005930"] = now
    state.force_retry_history["005930"] = [now]
    state.silent_inactive_first_seen["main"] = now
    state.silent_inactive_recovery_count["main"] = [now.timestamp()]
    state.universe_excluded_today.add("005930")
    state.last_ccnl_cache["005930"] = {
        "fetched_at": now, "last_cntg_hour": "135000", "today_volume": 50000,
    }

    state.reset_daily()

    # 7 필드 자동 검증
    for f in dataclasses.fields(StaleTrackerState):
        val = getattr(state, f.name)
        if isinstance(val, dict):
            assert val == {}, (
                f"reset_daily() 가 신규 필드 {f.name} 초기화 누락 — "
                f"`StaleTrackerState.reset_daily()` 갱신 필요"
            )
        elif isinstance(val, set):
            assert val == set(), (
                f"reset_daily() 가 신규 필드 {f.name} 초기화 누락 (set)"
            )
        else:
            raise AssertionError(
                f"신규 필드 {f.name} 타입 처리 미정의 ({type(val).__name__}) — "
                f"본 테스트 갱신 필요"
            )
