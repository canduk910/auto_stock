"""사이클 61 Phase 2-A2 Red — F 카테고리: dataclass 필드 누락 가드 (2 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (Q2-G2)
> **선례**: 사이클 60 A1 G-1 정정 사례 답습 (명세 "6 필드" → 실측 7 필드 정정).

`StaleTrackerState` (사이클 48) 의 7 필드 정확명 + reset_daily() 동행 reset 검증.

A1 정정 사례 영구 가드: 신규 필드 추가 시 `reset_daily()` 누락 사고 차단.

Red 단계: stale_manager 미존재 영향은 없으나, `StaleTrackerState` 의 7 필드 정의 +
`reset_daily()` 동작은 사이클 48 부터 정상 → 본 케이스는 Red 시점 *이미 PASS 가능*.
단, F-1/F-2 는 회귀 가드 — 사이클 62+ 신규 필드 추가 시 검증 강제.

회귀 가드: CLAUDE.md 절대 깨지 말 것 — `_reset_daily_state` 동행 reset 7 필드.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def test_F1_stale_tracker_state_has_exactly_seven_fields():
    """F-1: `StaleTrackerState` 필드 7 종 정확 일치 (사이클 48 정의 보존).

    사이클 60 G-1 정정 사례 영구 가드 — 명세 "6 필드" → 실측 7 필드 정정.
    신규 필드 추가 시 본 테스트 FAIL → reset_daily() 동행 reset 강제 유도.
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
        f"StaleTrackerState 필드 불일치 — 사이클 48 정의 7 필드 보존 의무. "
        f"실측: {field_names}, 기대: {expected}. "
        f"신규 필드 추가 시 reset_daily() 도 동행 갱신 필요."
    )


def test_F2_reset_daily_clears_all_seven_fields():
    """F-2: `StaleTrackerState.reset_daily()` 호출 후 7 필드 모두 빈 dict/set.

    `dataclasses.fields()` 자동 비교 — 신규 필드 추가 시 reset 누락 사고 차단.
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

    # 7 필드 자동 검증 — 신규 필드 추가 시 reset 누락 즉시 발견
    for f in dataclasses.fields(StaleTrackerState):
        val = getattr(state, f.name)
        if isinstance(val, dict):
            assert val == {}, (
                f"reset_daily() 가 신규 필드 {f.name} 초기화 누락 — "
                f"`StaleTrackerState.reset_daily()` 갱신 필요"
            )
        elif isinstance(val, set):
            assert val == set(), (
                f"reset_daily() 가 신규 필드 {f.name} 초기화 누락 (set) — "
                f"`StaleTrackerState.reset_daily()` 갱신 필요"
            )
        else:
            raise AssertionError(
                f"신규 필드 {f.name} 타입 처리 미정의 ({type(val).__name__}) — "
                f"본 테스트 갱신 필요"
            )
