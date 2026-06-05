"""사이클 63 Phase 2-A3 Red — E 카테고리: `_reset_daily_state` 동행 reset (2 케이스).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 E
> **선례**: 사이클 60 A1 G-1 + 사이클 61 A2 E-1 답습.

A3 영향 3 dict (`_stale_retry_count` / `_stale_last_resubscribe_at` /
`_stale_force_retry_history`) 모두 `StaleTrackerState` (사이클 48) 통합 →
`_reset_daily_state` 의 `self._stale_state.reset_daily()` 단일 호출이 일괄 clear.

Red 단계: stale_manager 미존재 영향 0 — 정상 인스턴스 동작 검증 (사이클 60+61 영속).

회귀 가드: CLAUDE.md 절대 깨지 말 것 — `_reset_daily_state` 동행 reset 의무.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def test_E1_reset_daily_state_clears_A3_three_dicts():
    """E-1: `_reset_daily_state()` 호출 후 A3 3 dict 모두 빈 dict.

    검증:
    - `_stale_retry_count == {}` (1~5회 카운터 리셋 — 다음 영업일 신규 사이클 시작)
    - `_stale_last_resubscribe_at == {}` (사이클 28 진단 시각 리셋)
    - `_stale_force_retry_history == {}` (사이클 29-R1 60분 슬라이딩 cap 리셋)
    """
    from src.engine import stale_manager  # noqa: F401 — Green 시점 stale_manager 확장 가드
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()
    now = datetime(2026, 6, 5, 16, 0, 0, tzinfo=KST)

    # 사전 더미 데이터 3 dict 모두 주입
    sched._stale_retry_count["005930"] = 3
    sched._stale_retry_count["000660"] = 1
    sched._stale_last_resubscribe_at["005930"] = now
    sched._stale_force_retry_history["005930"] = [now, now - timedelta(minutes=10)]

    # `_reset_daily_state` 호출 — 외부 영역 격리
    with patch.object(sched.registry, "all", return_value=[]), \
         patch.object(sched, "order_engine", MagicMock(
             _selling=set(), _filled_qty={}, _order_qty={},
             _order_strategy={}, _order_ticker={}, _pending_buy_orders={},
             _pending_cancel_tasks={},
             reset_daily_state=MagicMock(),
         )), \
         patch.object(sched, "risk_manager", MagicMock(reset_daily_state=MagicMock())):
        sched._reset_daily_state()

    # A3 3 dict 동시 검증
    assert sched._stale_retry_count == {}, (
        "_stale_retry_count 초기화 누락 — 다음 영업일 카운터 잔류 위험"
    )
    assert sched._stale_last_resubscribe_at == {}, (
        "_stale_last_resubscribe_at 초기화 누락 — 사이클 28 진단 시각 잔류"
    )
    assert sched._stale_force_retry_history == {}, (
        "_stale_force_retry_history 초기화 누락 — 사이클 29-R1 60분 슬라이딩 cap "
        "잔류 위험 (LMS / 앱키 정지 위험)"
    )


def test_E2_reset_daily_state_clears_force_retry_history_only_via_stale_state():
    """E-2: `_reset_daily_state` 가 `_stale_state.reset_daily()` 위임으로 일괄 clear.

    명시적으로 `_stale_state.reset_daily` 호출 mock 으로 single-entry-point 검증.
    A3 신규 dict 가 `StaleTrackerState` 외부 (예: scheduler 직접 dict) 로 추가될 경우
    본 케이스가 reset 누락 영구 차단.
    """
    from src.engine import stale_manager  # noqa: F401
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()

    with patch.object(sched._stale_state, "reset_daily") as mock_reset, \
         patch.object(sched.registry, "all", return_value=[]), \
         patch.object(sched, "order_engine", MagicMock(
             _selling=set(), _filled_qty={}, _order_qty={},
             _order_strategy={}, _order_ticker={}, _pending_buy_orders={},
             _pending_cancel_tasks={},
             reset_daily_state=MagicMock(),
         )), \
         patch.object(sched, "risk_manager", MagicMock(reset_daily_state=MagicMock())):
        sched._reset_daily_state()

    mock_reset.assert_called_once_with()
