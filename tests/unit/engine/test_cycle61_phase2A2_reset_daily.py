"""사이클 61 Phase 2-A2 Red — E 카테고리: `_reset_daily_state` 동행 reset (1 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (Q2-G1)
> **선례**: 사이클 60 A1 G-1 (`StaleTrackerState` 7 필드 통합 reset) 답습.

A2 영향 3 필드 동행 reset 검증:
- `_silent_inactive_first_seen` (사이클 24)
- `_silent_inactive_recovery_count` (사이클 24) — KIS LMS/앱키 정지 위험 영역
- `_universe_excluded_today` (사이클 32 R4) — 영구 블랙리스트 금지

A2 4 함수가 사용하는 3 필드 모두 `StaleTrackerState` 통합 (사이클 48) → `_reset_daily_state`
의 `self._stale_state.reset_daily()` 단일 호출이 7 필드 일괄 clear.

Red 단계: stale_manager 미존재 영향은 없으나, 정상 인스턴스 동작 검증.

회귀 가드: CLAUDE.md 절대 깨지 말 것 — `_reset_daily_state` 동행 reset 의무.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def test_E1_reset_daily_state_clears_A2_three_fields():
    """E-1: `_reset_daily_state()` 호출 후 A2 영향 3 필드 동시 초기화 검증.

    검증:
    - `_silent_inactive_first_seen == {}` (5분 카운트 리셋)
    - `_silent_inactive_recovery_count == {}` (시간당 cap 리셋 — KIS LMS 위험 차단)
    - `_universe_excluded_today == set()` (영구 블랙리스트 금지)
    """
    from src.engine import stale_manager  # noqa: F401 — Green 시점 stale_manager 확장 가드
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()
    now = datetime(2026, 6, 5, 16, 0, 0, tzinfo=KST)

    # 사전 더미 데이터 3 필드 모두 주입
    sched._silent_inactive_first_seen["main"] = now
    sched._silent_inactive_first_seen["quote-1"] = now
    sched._silent_inactive_recovery_count["main"] = [now.timestamp()]
    sched._silent_inactive_recovery_count["quote-1"] = [
        now.timestamp(), now.timestamp() - 1000.0,
    ]
    sched._universe_excluded_today.add("005930")
    sched._universe_excluded_today.add("000660")

    # 호출 — `_reset_daily_state` 가 `_stale_state.reset_daily()` 위임 보장
    # registry/order_engine/risk_manager 등 다른 영역은 mock 으로 격리
    with patch.object(sched.registry, "all", return_value=[]), \
         patch.object(sched, "order_engine", MagicMock(
             _selling=set(), _filled_qty={}, _order_qty={},
             _order_strategy={}, _order_ticker={}, _pending_buy_orders={},
             _pending_cancel_tasks={},
             reset_daily_state=MagicMock(),
         )), \
         patch.object(sched, "risk_manager", MagicMock(reset_daily_state=MagicMock())):
        sched._reset_daily_state()

    # A2 3 필드 동시 검증
    assert sched._silent_inactive_first_seen == {}, (
        "silent_inactive_first_seen 초기화 누락 — 5분 카운트 다음 영업일까지 잔류 위험"
    )
    assert sched._silent_inactive_recovery_count == {}, (
        "silent_inactive_recovery_count 초기화 누락 — "
        "시간당 reconnect cap 위반 위험 (KIS LMS/앱키 정지)"
    )
    assert sched._universe_excluded_today == set(), (
        "universe_excluded_today 초기화 누락 — 영구 블랙리스트 금지 "
        "(다음 영업일 재진입 정책 위반)"
    )
