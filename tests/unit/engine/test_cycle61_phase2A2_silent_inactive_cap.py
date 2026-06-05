"""사이클 61 Phase 2-A2 Red — G 카테고리: silent inactive 시간당 cap (1 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (G-1)
> **위험 등급**: MEDIUM (cap dict + freezegun 시각 동결)

`_force_reconnect_session` 3번째 호출 시 cap=2 도달 → False 반환 + WARNING 로그.

검증:
1. 1회 호출 = True (시도 성공)
2. 2회 호출 = True (cap=2 도달 전)
3. 3회 호출 = False (cap=2 초과 skip)
4. `[silent_inactive_recovery_cap]` WARNING 로그 emit
5. cap 초과 시 history 증가 안 함 (in-place evict 정합)

Red 단계: stale_manager.force_reconnect_session 미존재 → AttributeError 정상.

회귀 가드: CLAUDE.md 절대 깨지 말 것 — silent inactive 시간당 세션당 2회 cap
(KIS LMS/앱키 정지 위험 차단).
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit


def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init (사이클 60 A1 패턴 답습)."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    return sched


@pytest.mark.asyncio
@freeze_time("2026-06-05 10:00:00")
async def test_G1_silent_inactive_cap_60min_window_third_call_blocked(caplog):
    """G-1: cap 도달 시 reconnect skip (freezegun, 60분 window 내 3회 호출).

    1회 = True / 2회 = True / 3회 = False (cap=2 초과).
    `[silent_inactive_recovery_cap]` WARNING 로그 emit.
    """
    # caplog logger 명시 binding (사이클 60 I1 영구 가드)
    caplog.set_level(logging.WARNING, logger="src.engine.scheduler")

    sched = _make_scheduler()

    # kis_ws._ws.close() mock — AsyncMock (CI hang 차단)
    mock_ws = MagicMock()
    mock_ws.close = AsyncMock(return_value=None)

    # write_log mock — fire-and-forget DB 호출 격리
    with patch("src.engine.scheduler.kis_ws") as mock_kis_ws, \
         patch("src.engine.scheduler.write_log", new=AsyncMock(return_value=None)):
        mock_kis_ws._ws = mock_ws

        # 1회 호출 — 성공 (cap 도달 전)
        result1 = await sched._force_reconnect_session("main")
        assert result1 is True, "1회 호출은 cap=0/2 → 성공"
        assert len(sched._silent_inactive_recovery_count["main"]) == 1

        # 2회 호출 — 성공 (cap=2 도달 직전, 시각 동결 → 같은 wall clock)
        result2 = await sched._force_reconnect_session("main")
        assert result2 is True, "2회 호출은 cap=1/2 → 성공"
        assert len(sched._silent_inactive_recovery_count["main"]) == 2

        # 3회 호출 — cap 도달 skip
        result3 = await sched._force_reconnect_session("main")
        assert result3 is False, (
            "3회 호출은 cap=2/2 도달 → False (skip) — KIS LMS 위험 차단"
        )
        # cap 초과 시 history 증가 안 함 (in-place evict 정합)
        assert len(sched._silent_inactive_recovery_count["main"]) == 2, (
            "cap 초과 시 history 증가 금지 — 동일 dict 참조 mutation 정합성"
        )

    # WARNING 로그 emit 검증 — logger 명시 binding 가드 (사이클 60 I1)
    assert "[silent_inactive_recovery_cap]" in caplog.text, (
        "cap 도달 시 `[silent_inactive_recovery_cap]` WARNING 로그 emit 의무 "
        "— logger 명시 binding `src.engine.scheduler` 필수 (caplog 미캡처 시 fail)"
    )
