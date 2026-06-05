"""사이클 61 Phase 2-A2 Red — C 카테고리: cap dict `is` 동일성 (HIGH, 1 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (Q1-G2)
> **선례**: 사이클 60 A1 의 `_last_ccnl_cache` 동일성 가드 패턴 답습.
> **위험 등급**: **HIGH** — KIS LMS/앱키 정지 위험 영구 차단

`_force_reconnect_session` 의 시간당 cap dict `_silent_inactive_recovery_count` 가
이주 후에도 *동일 dict 참조* 유지 — KIS 측 무한 재연결 회피 보장.

A2 이주 시 stale_manager 함수가 `scheduler._silent_inactive_recovery_count[label]`
경로로 접근하면, property layer 가 `_stale_state.silent_inactive_recovery_count` 직접 노출
→ 동일 dict 참조 보장. mutation 후에도 `is` 동일성 유지 의무.

Red 단계: stale_manager.force_reconnect_session 미존재 → AttributeError 정상.

회귀 가드: CLAUDE.md 절대 깨지 말 것 — silent inactive 시간당 세션당 2회 cap.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init (사이클 60 A1 패턴 답습)."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    return sched


@pytest.mark.asyncio
async def test_C1_silent_inactive_recovery_count_dict_identity_preserved_across_delegation():
    """C-1 (HIGH): cap dict `is` 동일성 보장 — 이주 후에도 동일 참조.

    검증:
    1. `scheduler._silent_inactive_recovery_count is scheduler._stale_state.silent_inactive_recovery_count`
    2. stale_manager.force_reconnect_session 호출 후에도 동일 dict 참조 유지
       (mutation 후 같은 dict — KIS 측 무한 재연결 회피 가드)

    Red: stale_manager.force_reconnect_session 미존재 → AttributeError.
    Green: 동일성 보장.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    sched = _make_scheduler()
    # property 경로로 dict 참조 획득
    dict_before = sched._silent_inactive_recovery_count
    state_dict = sched._stale_state.silent_inactive_recovery_count

    # 사전 검증 — property layer 가 _stale_state 필드 직접 노출
    assert dict_before is state_dict, (
        "property layer 가 _stale_state.silent_inactive_recovery_count 를 "
        "직접 노출해야 함 (`is` 동일성)"
    )

    # mutation — 임의 데이터 주입
    dict_before["main"] = [100.0, 200.0]

    # stale_manager 함수 호출 (mock 으로 차단 — 본 케이스는 dict 동일성만 검증)
    with patch.object(
        stale_manager, "force_reconnect_session", new=AsyncMock(return_value=True)
    ):
        await sched._force_reconnect_session("main")

    # 호출 후에도 dict 참조 동일 (KIS LMS/앱키 정지 위험 차단)
    dict_after = sched._silent_inactive_recovery_count
    assert dict_after is dict_before, (
        "stale_manager 호출 후에도 `_silent_inactive_recovery_count` dict 참조 동일 의무 "
        "— 새 dict 생성 시 cap 카운트 누락 → 시간당 2회 cap 위반 → KIS LMS 위험"
    )
    assert dict_after is sched._stale_state.silent_inactive_recovery_count, (
        "_stale_state.silent_inactive_recovery_count 와도 동일 참조 유지 의무"
    )
    # mutation 결과 보존
    assert dict_after["main"] == [100.0, 200.0], (
        "mutation 데이터가 보존되어야 함 (새 dict 생성 시 누락)"
    )
