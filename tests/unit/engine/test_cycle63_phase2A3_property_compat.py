"""사이클 63 Phase 2-A3 Red — C 카테고리: property `is` 동일성 + 외부 호환 (3 케이스).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 C
> **선례**: 사이클 60 A1 / 사이클 61 A2 property 패턴 답습.

A3 위임 후 3 dict (`_stale_retry_count` / `_stale_last_resubscribe_at` /
`_stale_force_retry_history`) 의 (a) 외부 `getattr` 폴백 호환 + (b) `_stale_state` 와
`is` 동일성 보장 검증.

외부 접근 = `src/routes/realtime.py:88-89` 2 라인 — A3 추가 0.

Red 단계: 사이클 60+61 영속 → 정상 인스턴스 PASS 가능. A3 위임 후 동일 객체 갱신
보장 검증이 핵심.

회귀 가드: `getattr(trading_scheduler, "_stale_retry_count", {})` 호출 시 None/{} 폴백.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    return sched


# ===========================================================================
# C-1: _stale_retry_count 외부 getattr 호환 (routes/realtime.py:88)
# ===========================================================================
def test_C1_stale_retry_count_external_getattr_fallback_compat():
    """C-1: `getattr(sched, "_stale_retry_count", {})` 호환.

    `src/routes/realtime.py:88` 와 동일 패턴. 정상 인스턴스 → dict 반환,
    부재 인스턴스 → {} 폴백. A3 위임 후에도 property layer 보존 의무.
    """
    sched = _make_scheduler()
    result = getattr(sched, "_stale_retry_count", {})
    assert isinstance(result, dict), "dict 타입 보장"

    # 갱신 후 같은 객체 재참조 검증
    sched._stale_retry_count["005930"] = 3
    result2 = getattr(sched, "_stale_retry_count", {})
    assert result2["005930"] == 3, "외부 getattr 후 동일 dict 갱신 가시성 보장"


# ===========================================================================
# C-2: _stale_last_resubscribe_at 외부 getattr 호환 (routes/realtime.py:89)
# ===========================================================================
def test_C2_stale_last_resubscribe_at_external_getattr_fallback_compat():
    """C-2: `getattr(sched, "_stale_last_resubscribe_at", {})` 호환.

    `src/routes/realtime.py:89` 와 동일 패턴. A3 본체 L2604/L2641/L2769 의
    setter 호출 (dict[ticker] = datetime) 이 외부 진단 라우트 응답에 반영.
    """
    from datetime import datetime, timedelta, timezone
    KST = timezone(timedelta(hours=9))

    sched = _make_scheduler()
    result = getattr(sched, "_stale_last_resubscribe_at", {})
    assert isinstance(result, dict)

    now = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    sched._stale_last_resubscribe_at["005930"] = now
    result2 = getattr(sched, "_stale_last_resubscribe_at", {})
    assert result2["005930"] == now, "외부 getattr 후 동일 datetime 갱신 가시성"


# ===========================================================================
# C-3: 3 dict `is` 동일성 — _stale_state 직접 vs property 경유 동일 객체
# ===========================================================================
def test_C3_three_stale_dicts_is_identity_via_property_layer():
    """C-3: property 경유 dict 와 `_stale_state.*` 직접 접근 dict 가 `is` 동일.

    A3 위임 후에도 wrapper → stale_manager 함수가 `scheduler._stale_retry_count` 갱신 시
    동일 dict 객체 mutation 보장 (테스트 patch 호환 + 운영 동일성).

    domain Q1-G4: `assert id(scheduler._stale_state.retry_count) == id(scheduler._stale_retry_count)`.
    """
    sched = _make_scheduler()

    # 3 dict 모두 `is` 동일성 검증
    assert sched._stale_state.retry_count is sched._stale_retry_count, (
        "_stale_retry_count property 가 _stale_state.retry_count 와 다른 객체 — "
        "A3 위임 후 카운터 리셋 시 silent 실패 위험"
    )
    assert sched._stale_state.last_resubscribe_at is sched._stale_last_resubscribe_at, (
        "_stale_last_resubscribe_at property 가 _stale_state 와 다른 객체"
    )
    assert sched._stale_state.force_retry_history is sched._stale_force_retry_history, (
        "_stale_force_retry_history property 가 _stale_state 와 다른 객체"
    )
