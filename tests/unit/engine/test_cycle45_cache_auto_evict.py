"""사이클 45 (2026-05-22) — refactor-review 카드 #5 (MEDIUM) TTL 캐시 자동 evict.

Phase 1 진단:
- `_last_ccnl_cache` (TTL 5분, 사이클 37): **자동 evict 부재**.
  TTL hit 판정만 있고, 만료 후 dict 에서 제거되는 분기 없음.
  stale watcher 가 더 이상 평가 안 하는 ticker (회복/R4 제외) 영구 잔존 위험.
- `_stale_force_retry_history` (60분 sliding window, 사이클 29-R1): **부분 evict**.
  매 force_retry 진입 시 해당 ticker history in-place evict 있음.
  그러나 빈 list 가 dict 에서 제거되지 않아 잔존 위험.
  다른 ticker stale 인 사이에는 해당 ticker history 도 갱신 안 됨.

본 사이클 (45, MEDIUM) 변경:
- `scheduler._evict_expired_ccnl(now, ttl_secs=300) -> int`: 신규 헬퍼.
  `_refresh_stale_ccnl_cache` 진입 시 호출 → TTL 만료 항목 일괄 제거.
- `scheduler._prune_force_retry_history(ticker, now, window_secs=3600)`: 신규 헬퍼.
  cap 비교 직전 호출 → 빈 list 자동 dict 제거.

안전 가드:
- 캐시 hit/miss 정책 변경 없음 (TTL 5분 정의 보존, sliding window 60분 보존)
- `_reset_daily_state` 동행 clear 보존 (이중 안전망)
- evict 실패 graceful (한 종목 실패 → 다른 종목 계속)
- 사이클 29-R1 force_retry cap 12회/시간 보존
- 매매 동작 변경 0 (lookup 결과 동일성 보존)

사양 (E-1 ~ E-7):
- E-1: `_evict_expired_ccnl` 신규 헬퍼 존재 + 반환값 (제거 수)
- E-2: TTL 만료 항목 dict 에서 제거
- E-3: TTL 이내 항목 보존
- E-4: `_refresh_stale_ccnl_cache` 진입 시 자동 호출
- E-5: `_prune_force_retry_history` 신규 헬퍼 — 빈 list ticker dict 제거
- E-6: 60분 외 항목 제거 + 빈 list 잔존 안 됨
- E-7: 매매 동작 동일성 (캐시 hit/miss 정책 + cap 12회 비교 동일)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


KST = timezone(timedelta(hours=9))


def _make_sched():
    """`__new__` 기반 minimal scheduler — _last_ccnl_cache + _stale_force_retry_history."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._last_ccnl_cache = {}
    sched._stale_force_retry_history = {}
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._pending_next_day_clear = set()
    sched._universe_excluded_today = set()

    # registry mock — empty
    fake_registry = MagicMock()
    fake_registry.all = MagicMock(return_value=[])
    sched.registry = fake_registry
    return sched


# ===========================================================================
# E-1: _evict_expired_ccnl 헬퍼 존재 + 반환값
# ===========================================================================
def test_evict_expired_ccnl_helper_exists():
    """`scheduler._evict_expired_ccnl(now, ttl_secs=300) -> int` 헬퍼 존재."""
    from src.engine.scheduler import TradingScheduler

    assert hasattr(TradingScheduler, "_evict_expired_ccnl"), (
        "_evict_expired_ccnl 헬퍼 누락 (사이클 45)"
    )


# ===========================================================================
# E-2: TTL 만료 항목 제거
# ===========================================================================
def test_evict_expired_ccnl_removes_expired_entries():
    """TTL 5분 경과 항목 dict 에서 제거."""
    sched = _make_sched()
    now = datetime.now(KST)

    sched._last_ccnl_cache = {
        "EXPIRED1": {"fetched_at": now - timedelta(seconds=400),
                     "last_cntg_hour": "150045", "today_volume": 5000},
        "EXPIRED2": {"fetched_at": now - timedelta(seconds=600),
                     "last_cntg_hour": "145000", "today_volume": 3000},
        "FRESH": {"fetched_at": now - timedelta(seconds=100),
                  "last_cntg_hour": "151000", "today_volume": 8000},
    }

    evicted = sched._evict_expired_ccnl(now, ttl_secs=300)

    assert evicted == 2
    assert "EXPIRED1" not in sched._last_ccnl_cache
    assert "EXPIRED2" not in sched._last_ccnl_cache
    assert "FRESH" in sched._last_ccnl_cache


# ===========================================================================
# E-3: TTL 이내 항목 보존
# ===========================================================================
def test_evict_expired_ccnl_preserves_fresh_entries():
    """TTL 이내 항목은 보존 (캐시 hit 정책 보존)."""
    sched = _make_sched()
    now = datetime.now(KST)

    sched._last_ccnl_cache = {
        "FRESH1": {"fetched_at": now - timedelta(seconds=100),
                   "last_cntg_hour": "150000", "today_volume": 5000},
        "FRESH2": {"fetched_at": now - timedelta(seconds=200),
                   "last_cntg_hour": "150100", "today_volume": 6000},
        "FRESH3": {"fetched_at": now - timedelta(seconds=299),  # 임계 직전
                   "last_cntg_hour": "150200", "today_volume": 7000},
    }

    evicted = sched._evict_expired_ccnl(now, ttl_secs=300)

    assert evicted == 0
    assert len(sched._last_ccnl_cache) == 3


def test_evict_expired_ccnl_empty_cache_safe():
    """빈 캐시 → 0 반환 + 예외 X."""
    sched = _make_sched()
    now = datetime.now(KST)

    evicted = sched._evict_expired_ccnl(now)

    assert evicted == 0
    assert sched._last_ccnl_cache == {}


# ===========================================================================
# E-4: _refresh_stale_ccnl_cache 진입 시 자동 호출
# ===========================================================================
@pytest.mark.asyncio
async def test_refresh_stale_ccnl_cache_auto_evicts_expired(monkeypatch):
    """`_refresh_stale_ccnl_cache` 진입 시 expired 항목 자동 제거."""
    sched = _make_sched()
    now = datetime.now(KST)

    # 만료된 캐시 항목 사전 등록
    sched._last_ccnl_cache = {
        "EXPIRED": {"fetched_at": now - timedelta(seconds=400),
                    "last_cntg_hour": "150000", "today_volume": 5000},
    }

    # _refresh_stale_ccnl_cache 진입 — 빈 candidates 전달 (KIS 호출 분기 차단)
    # 진입 직후 evict 만 호출되도록
    await sched._refresh_stale_ccnl_cache([])

    # EXPIRED 항목 제거됨
    assert "EXPIRED" not in sched._last_ccnl_cache


# ===========================================================================
# E-5: _prune_force_retry_history 빈 list ticker dict 제거
# ===========================================================================
def test_prune_force_retry_history_removes_empty_list_ticker():
    """sliding window 외 항목 모두 제거 → 빈 list 종목 dict 에서 제거."""
    from src.engine.scheduler import TradingScheduler

    assert hasattr(TradingScheduler, "_prune_force_retry_history"), (
        "_prune_force_retry_history 헬퍼 누락 (사이클 45)"
    )

    sched = _make_sched()
    now = datetime.now(KST)

    # 60분 외 항목만 — pruning 후 빈 list
    sched._stale_force_retry_history = {
        "OLD_ONLY": [now - timedelta(hours=2), now - timedelta(hours=3)],
        "MIXED": [now - timedelta(hours=2), now - timedelta(minutes=30)],
    }

    sched._prune_force_retry_history("OLD_ONLY", now, window_secs=3600)

    # OLD_ONLY 는 빈 list → dict 에서 제거
    assert "OLD_ONLY" not in sched._stale_force_retry_history


def test_prune_force_retry_history_preserves_in_window_entries():
    """sliding window 내 항목은 보존."""
    sched = _make_sched()
    now = datetime.now(KST)

    sched._stale_force_retry_history = {
        "ACTIVE": [now - timedelta(hours=2),  # 60분 외 → 제거
                   now - timedelta(minutes=30),  # 보존
                   now - timedelta(minutes=10)],  # 보존
    }

    sched._prune_force_retry_history("ACTIVE", now, window_secs=3600)

    # ACTIVE 는 2개만 잔존
    history = sched._stale_force_retry_history.get("ACTIVE", [])
    assert len(history) == 2


def test_prune_force_retry_history_unknown_ticker_noop():
    """없는 ticker 호출 — 예외 X (idempotent)."""
    sched = _make_sched()
    now = datetime.now(KST)

    # 호출 자체 graceful
    sched._prune_force_retry_history("NON-EXISTENT", now)

    # 변경 없음
    assert sched._stale_force_retry_history == {}


# ===========================================================================
# E-6: 빈 list 잔존 안 됨 (영업일 누적 메모리 누수 차단)
# ===========================================================================
def test_force_retry_history_no_empty_lists_after_prune():
    """대량 ticker pruning 후 빈 list 잔존 0."""
    sched = _make_sched()
    now = datetime.now(KST)

    # 30 ticker 의 OLD_ONLY (모두 60분 외)
    for i in range(30):
        sched._stale_force_retry_history[f"{i:06d}"] = [
            now - timedelta(hours=2 + (i % 3)),
        ]

    # 모두 prune
    for ticker in list(sched._stale_force_retry_history.keys()):
        sched._prune_force_retry_history(ticker, now)

    # 빈 list 모두 제거됨
    assert sched._stale_force_retry_history == {}


# ===========================================================================
# E-7: 매매 동작 동일성 (캐시 hit/miss 정책 + cap 12회 비교)
# ===========================================================================
@pytest.mark.asyncio
async def test_refresh_stale_ccnl_cache_hit_policy_preserved(monkeypatch):
    """evict 후에도 TTL hit 종목은 재호출되지 않음 (정책 보존)."""
    sched = _make_sched()
    now = datetime.now(KST)

    # FRESH 종목 + 만료 종목 혼합
    sched._last_ccnl_cache = {
        "FRESH": {"fetched_at": now - timedelta(seconds=100),
                  "last_cntg_hour": "150000", "today_volume": 5000},
        "EXPIRED": {"fetched_at": now - timedelta(seconds=400),
                    "last_cntg_hour": "145000", "today_volume": 3000},
    }
    sched._stale_retry_count = {"FRESH": 5, "EXPIRED": 5}

    call_log = []

    async def _fake_ccnl(ticker, market="J"):
        call_log.append(ticker)
        return {"last_cntg_hour": "151000", "last_price": 5000, "last_volume": 100,
                "last_relative_strength": 80.0, "today_volume": 8000, "raw_count": 5}

    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)

    await sched._refresh_stale_ccnl_cache(["FRESH", "EXPIRED"])

    # FRESH 는 TTL hit → 재호출 안 됨 (캐시 정책 보존)
    # EXPIRED 는 evict 후 재호출됨
    assert "FRESH" not in call_log, "TTL 이내 종목 재호출 — 캐시 hit 정책 위반"
    assert "EXPIRED" in call_log
