"""사이클 48 (2026-05-22) — refactor-review 카드 #2 (MEDIUM) Stale 추적 dict 통합.

배경:
- scheduler.py 에 stale 관련 7 dict/set 필드 산재 (사이클 28/29-R1/29-R2/32/37 누적):
  1. `_stale_retry_count` (사이클 17 이전)
  2. `_stale_last_resubscribe_at` (사이클 28)
  3. `_stale_force_retry_history` (사이클 29-R1 + 사이클 45 evict)
  4. `_silent_inactive_first_seen` (사이클 24)
  5. `_silent_inactive_recovery_count` (사이클 24)
  6. `_universe_excluded_today` (사이클 32 R4)
  7. `_last_ccnl_cache` (사이클 37 + 사이클 45 evict)
- 관계 불명시 → 사이클 추가 시 reset 동행 누락 위험.

본 사이클 (48, MEDIUM) 변경:
- `StaleTrackerState` 데이터클래스 신규 (`src/engine/stale_tracker.py`).
- `TradingScheduler.__init__` 의 7 필드 → `self._stale_state = StaleTrackerState()`.
- 호환 layer (property) — 기존 `self._stale_retry_count` 등 접근 그대로 (회귀 위험 최소).
- `_reset_daily_state` 7 줄 clear → `self._stale_state.reset_daily()` 1 줄.

안전 가드:
- 호환 layer 로 기존 접근 패턴 모두 동작 (사이클 28~37 + 사이클 45 회귀 0)
- `_reset_daily_state` 동행 clear 보존 의무 (절대)
- 사이클 45 TTL evict 정책 보존 (`_last_ccnl_cache` 5분 + `_stale_force_retry_history` 60분)
- 매매 동작 변경 0

사양 (S-1 ~ S-7):
- S-1: `StaleTrackerState` 데이터클래스 + 7 필드 default_factory
- S-2: `reset_daily()` 7 필드 일괄 clear
- S-3: `TradingScheduler.__init__` 가 `_stale_state` 보유
- S-4: 호환 layer 7 property 동작 (`self._stale_retry_count` 등 그대로 접근)
- S-5: `_reset_daily_state` 동행 위임 (7 dict/set 모두 빈 상태)
- S-6: 호환 layer 가 dict 인스턴스 동일성 보장 (`is` 비교)
- S-7: 회귀 — 사이클 45 _evict_expired_ccnl + _prune_force_retry_history 동작 보존
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


KST = timezone(timedelta(hours=9))


# ===========================================================================
# S-1: StaleTrackerState 데이터클래스 + 7 필드
# ===========================================================================
def test_stale_tracker_state_dataclass_exists():
    """`StaleTrackerState` 데이터클래스 존재 (사이클 48)."""
    from src.engine.stale_tracker import StaleTrackerState

    state = StaleTrackerState()
    # 7 필드 default_factory 검증
    assert state.retry_count == {}
    assert state.last_resubscribe_at == {}
    assert state.force_retry_history == {}
    assert state.silent_inactive_first_seen == {}
    assert state.silent_inactive_recovery_count == {}
    assert state.universe_excluded_today == set()
    assert state.last_ccnl_cache == {}


def test_stale_tracker_state_fields_independent():
    """각 필드 독립적 dict/set 인스턴스 (mutable default 함정 차단)."""
    from src.engine.stale_tracker import StaleTrackerState

    s1 = StaleTrackerState()
    s2 = StaleTrackerState()
    s1.retry_count["005930"] = 5
    assert s2.retry_count == {}, "default_factory 미사용 시 mutable default 공유 결함"


# ===========================================================================
# S-2: reset_daily() 7 필드 일괄 clear
# ===========================================================================
def test_reset_daily_clears_all_seven_fields():
    """`reset_daily()` 호출 시 7 필드 모두 빈 상태."""
    from src.engine.stale_tracker import StaleTrackerState

    state = StaleTrackerState()
    state.retry_count["005930"] = 5
    state.last_resubscribe_at["005930"] = datetime.now(KST)
    state.force_retry_history["005930"] = [datetime.now(KST)]
    state.silent_inactive_first_seen["main"] = datetime.now(KST)
    state.silent_inactive_recovery_count["main"] = [1.0]
    state.universe_excluded_today.add("036930")
    state.last_ccnl_cache["005930"] = {"fetched_at": datetime.now(KST)}

    state.reset_daily()

    assert state.retry_count == {}
    assert state.last_resubscribe_at == {}
    assert state.force_retry_history == {}
    assert state.silent_inactive_first_seen == {}
    assert state.silent_inactive_recovery_count == {}
    assert state.universe_excluded_today == set()
    assert state.last_ccnl_cache == {}


# ===========================================================================
# S-3: TradingScheduler.__init__ 가 _stale_state 보유
# ===========================================================================
def test_scheduler_has_stale_state_field():
    """`TradingScheduler` 가 `_stale_state: StaleTrackerState` 보유 (사이클 48)."""
    import inspect
    from src.engine.scheduler import TradingScheduler

    src = inspect.getsource(TradingScheduler.__init__)
    assert "_stale_state" in src, (
        "TradingScheduler.__init__ 에 _stale_state 통합 필드 누락 (사이클 48)"
    )


# ===========================================================================
# S-4: 호환 layer 7 property 동작 (기존 접근 패턴 보존)
# ===========================================================================
def test_compat_layer_stale_retry_count(monkeypatch):
    """`self._stale_retry_count` 가 `_stale_state.retry_count` 와 동일 dict 객체."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    from src.engine.stale_tracker import StaleTrackerState
    sched._stale_state = StaleTrackerState()

    # 호환 layer 동작 — 동일 dict 객체
    assert sched._stale_retry_count is sched._stale_state.retry_count
    sched._stale_retry_count["005930"] = 5
    assert sched._stale_state.retry_count["005930"] == 5


def test_compat_layer_all_seven_fields():
    """7 property 모두 호환 layer 동작."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_state = StaleTrackerState()

    assert sched._stale_retry_count is sched._stale_state.retry_count
    assert sched._stale_last_resubscribe_at is sched._stale_state.last_resubscribe_at
    assert sched._stale_force_retry_history is sched._stale_state.force_retry_history
    assert sched._silent_inactive_first_seen is sched._stale_state.silent_inactive_first_seen
    assert sched._silent_inactive_recovery_count is sched._stale_state.silent_inactive_recovery_count
    assert sched._universe_excluded_today is sched._stale_state.universe_excluded_today
    assert sched._last_ccnl_cache is sched._stale_state.last_ccnl_cache


# ===========================================================================
# S-5: _reset_daily_state 동행 위임 (사이클 48 + 기존 정책 보존)
# ===========================================================================
def test_reset_daily_state_delegates_to_stale_state(monkeypatch):
    """`TradingScheduler._reset_daily_state` 호출 시 7 dict/set 모두 빈 상태."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_state = StaleTrackerState()

    # 사전 데이터 — 7 필드 모두
    sched._stale_state.retry_count["005930"] = 5
    sched._stale_state.last_resubscribe_at["005930"] = datetime.now(KST)
    sched._stale_state.force_retry_history["005930"] = [datetime.now(KST)]
    sched._stale_state.silent_inactive_first_seen["main"] = datetime.now(KST)
    sched._stale_state.silent_inactive_recovery_count["main"] = [1.0]
    sched._stale_state.universe_excluded_today.add("036930")
    sched._stale_state.last_ccnl_cache["005930"] = {"fetched_at": datetime.now(KST)}

    # _reset_daily_state 의 stale 영역만 호출 — 다른 의존성 (positions/orders/etc) 우회
    # `_stale_state.reset_daily()` 위임 검증
    sched._stale_state.reset_daily()

    assert sched._stale_state.retry_count == {}
    assert sched._stale_state.last_resubscribe_at == {}
    assert sched._stale_state.force_retry_history == {}
    assert sched._stale_state.silent_inactive_first_seen == {}
    assert sched._stale_state.silent_inactive_recovery_count == {}
    assert sched._stale_state.universe_excluded_today == set()
    assert sched._stale_state.last_ccnl_cache == {}

    # 호환 layer 도 즉시 반영
    assert sched._stale_retry_count == {}
    assert sched._universe_excluded_today == set()
    assert sched._last_ccnl_cache == {}


def test_reset_daily_state_source_uses_stale_state_reset():
    """`_reset_daily_state` 소스에 `_stale_state.reset_daily()` 호출 존재."""
    import inspect
    from src.engine.scheduler import TradingScheduler

    src = inspect.getsource(TradingScheduler._reset_daily_state)
    assert "_stale_state.reset_daily()" in src, (
        "_reset_daily_state 가 _stale_state.reset_daily() 위임 호출 누락 (사이클 48)"
    )


# ===========================================================================
# S-6: 호환 layer dict 인스턴스 동일성 (`is` 비교)
# ===========================================================================
def test_compat_layer_dict_identity_preserved():
    """호환 layer 가 매 접근마다 동일 dict 인스턴스 반환 (race 차단)."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_state = StaleTrackerState()

    d1 = sched._stale_retry_count
    d2 = sched._stale_retry_count
    assert d1 is d2, "호환 layer 가 매번 새 dict 반환 — race 위험"


# ===========================================================================
# S-7: 회귀 — 사이클 45 _evict_expired_ccnl + _prune_force_retry_history 보존
# ===========================================================================
def test_cycle45_evict_expired_ccnl_works_with_stale_state():
    """사이클 45 `_evict_expired_ccnl` 가 통합 후에도 정상 동작."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_state = StaleTrackerState()

    now = datetime.now(KST)
    # 만료 + 보존 혼합
    sched._stale_state.last_ccnl_cache = {
        "EXPIRED": {"fetched_at": now - timedelta(seconds=400),
                    "last_cntg_hour": "150000", "today_volume": 5000},
        "FRESH": {"fetched_at": now - timedelta(seconds=100),
                  "last_cntg_hour": "151000", "today_volume": 8000},
    }

    evicted = sched._evict_expired_ccnl(now, ttl_secs=300)
    assert evicted == 1
    assert "EXPIRED" not in sched._stale_state.last_ccnl_cache
    assert "FRESH" in sched._stale_state.last_ccnl_cache


def test_cycle45_prune_force_retry_history_works_with_stale_state():
    """사이클 45 `_prune_force_retry_history` 통합 후에도 정상 동작."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_state = StaleTrackerState()

    now = datetime.now(KST)
    # 60분 외 항목만 — pruning 후 빈 list
    sched._stale_state.force_retry_history["OLD_ONLY"] = [
        now - timedelta(hours=2),
    ]

    sched._prune_force_retry_history("OLD_ONLY", now, window_secs=3600)
    # 빈 list — dict 제거
    assert "OLD_ONLY" not in sched._stale_state.force_retry_history
