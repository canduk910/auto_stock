"""StreamPoolManager 단위 테스트 (사이클 15-B-1, 2026-05-19).

상태 전이 + 안정성 정책 검증. 단독 모듈이라 외부 의존 0.

11 케이스:
1. promote 첫 호출 — rest_watch 없어도 ws_active 진입
2. promote 후 mark_demoted — min_ws_hold_secs 전이면 거부
3. promote 후 min_ws_hold_secs 경과 → demote OK + cooldown 진입
4. cooldown 중 재승격 거부 — ws_rejoin_cooldown_secs 만료까지
5. cooldown 만료 → rest_watch 복귀 가능
6. positions 종목은 demote 절대 불가 (protected)
7. next_day_clear 종목 protected 동일
8. max_promote_per_cycle=5 초과 거부
9. max_demote_per_cycle=5 초과 거부
10. snapshot() 응답 3 카테고리 분리
11. reset_cycle() 후 배치 카운터 초기화
"""
from __future__ import annotations

import pytest

from src.engine.stream_pool_manager import (
    MIN_WS_HOLD_SECS,
    WS_REJOIN_COOLDOWN_SECS,
    StreamPoolManager,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def pool():
    return StreamPoolManager()


# ===========================================================================
# Case 1: 첫 promote
# ===========================================================================
def test_promote_first_call_enters_ws_active(pool):
    ok = pool.mark_promoted("005930", "volatility_breakout", "distance_pct=0.2%", now=1000.0)
    assert ok is True
    slot = pool.get_slot("005930")
    assert slot is not None
    assert slot.state == "ws_active"
    assert slot.ws_hold_until == 1000.0 + MIN_WS_HOLD_SECS


# ===========================================================================
# Case 2: min_ws_hold_secs 전 demote 거부
# ===========================================================================
def test_demote_before_min_hold_rejected(pool):
    pool.mark_promoted("005930", "volatility_breakout", "near", now=1000.0)
    # 50초 후 demote 시도
    ok, reason = pool.can_demote("005930", now=1050.0)
    assert ok is False
    assert reason == "min_ws_hold_not_expired"


# ===========================================================================
# Case 3: min_ws_hold_secs 경과 → demote OK + cooldown 진입
# ===========================================================================
def test_demote_after_min_hold_enters_cooldown(pool):
    pool.mark_promoted("005930", "volatility_breakout", "near", now=1000.0)
    # 200초 후 (MIN_WS_HOLD_SECS=180 초과)
    now = 1000.0 + MIN_WS_HOLD_SECS + 20
    ok = pool.mark_demoted("005930", reason="signal_faded", now=now)
    assert ok is True
    slot = pool.get_slot("005930")
    assert slot.state == "cooldown"
    assert slot.cooldown_until == now + WS_REJOIN_COOLDOWN_SECS


# ===========================================================================
# Case 4: cooldown 중 재승격 거부
# ===========================================================================
def test_promote_during_cooldown_rejected(pool):
    pool.mark_promoted("005930", "volatility_breakout", "near", now=1000.0)
    demote_time = 1000.0 + MIN_WS_HOLD_SECS + 20
    pool.mark_demoted("005930", "signal_faded", now=demote_time)

    pool.reset_cycle()
    # cooldown 중 (cooldown_until = demote_time + 300)
    ok, reason = pool.can_promote("005930", now=demote_time + 100)
    assert ok is False
    assert reason == "cooldown_not_expired"


# ===========================================================================
# Case 5: cooldown 만료 → rest_watch 복귀
# ===========================================================================
def test_cooldown_expiry_returns_to_rest_watch(pool):
    pool.mark_promoted("005930", "volatility_breakout", "near", now=1000.0)
    demote_time = 1000.0 + MIN_WS_HOLD_SECS + 20
    pool.mark_demoted("005930", "signal_faded", now=demote_time)

    # cooldown 만료 직후
    expire_time = demote_time + WS_REJOIN_COOLDOWN_SECS + 1
    expired = pool.expire_cooldowns(now=expire_time)

    assert "005930" in expired
    slot = pool.get_slot("005930")
    assert slot.state == "rest_watch"


# ===========================================================================
# Case 6: positions 종목 demote 불가
# ===========================================================================
def test_positions_protected_from_demote(pool):
    pool.mark_promoted("005930", "positions", "held", now=1000.0)
    # min_ws_hold 경과해도 demote 불가
    now = 1000.0 + MIN_WS_HOLD_SECS + 100
    ok, reason = pool.can_demote("005930", now=now)
    assert ok is False
    assert reason == "protected_strategy"


# ===========================================================================
# Case 7: next_day_clear 종목 demote 불가
# ===========================================================================
def test_next_day_clear_protected(pool):
    pool.mark_promoted("079550", "next_day_clear", "익일 청산 대기", now=1000.0)
    now = 1000.0 + MIN_WS_HOLD_SECS + 100
    ok, reason = pool.can_demote("079550", now=now)
    assert ok is False
    assert reason == "protected_strategy"


# ===========================================================================
# Case 8: max_promote_per_cycle 초과 거부
# ===========================================================================
def test_max_promote_per_cycle_limit(pool):
    base = 1000.0
    for i in range(5):  # 5건은 OK
        ok = pool.mark_promoted(f"00{i:04d}", "volatility_breakout", "near", now=base)
        assert ok is True
    # 6번째는 배치 제한 초과
    ok = pool.mark_promoted("999999", "volatility_breakout", "near", now=base)
    assert ok is False
    ok_check, reason = pool.can_promote("999999", now=base)
    assert ok_check is False
    assert reason == "max_promote_per_cycle_reached"


# ===========================================================================
# Case 9: max_demote_per_cycle 초과 거부
# ===========================================================================
def test_max_demote_per_cycle_limit(pool):
    base = 1000.0
    # 6 종목 승격
    for i in range(6):
        pool.mark_promoted(f"D{i:05d}", "volatility_breakout", "near", now=base)
    # 동일 사이클 내 demote 시도 (min_hold 지난 시점으로 가정)
    demote_time = base + MIN_WS_HOLD_SECS + 1
    pool.reset_cycle()
    success = 0
    for i in range(6):
        if pool.mark_demoted(f"D{i:05d}", "signal_faded", now=demote_time):
            success += 1
    assert success == 5, f"max_demote_per_cycle=5 — 6번째는 거부, 실제={success}"


# ===========================================================================
# Case 10: snapshot() 3 카테고리 분리
# ===========================================================================
def test_snapshot_three_categories(pool):
    base = 1000.0
    pool.mark_promoted("WS001", "volatility_breakout", "near", now=base)
    pool.mark_rest_watch("RW001", "long_tail_volatility")
    # demote 까지 시뮬레이션
    pool.mark_promoted("CD001", "bull_flag_breakout", "near", now=base)
    pool.reset_cycle()
    demote_time = base + MIN_WS_HOLD_SECS + 1
    pool.mark_demoted("CD001", "signal_faded", now=demote_time)

    snap = pool.snapshot()
    assert {e["ticker"] for e in snap["ws"]} == {"WS001"}
    assert {e["ticker"] for e in snap["rest"]} == {"RW001"}
    assert {e["ticker"] for e in snap["dropped"]} == {"CD001"}


# ===========================================================================
# Case 11: reset_cycle 후 배치 카운터 초기화
# ===========================================================================
def test_reset_cycle_clears_batch_counters(pool):
    base = 1000.0
    for i in range(5):
        pool.mark_promoted(f"X{i:05d}", "volatility_breakout", "near", now=base)
    # 6번째 거부
    assert pool.mark_promoted("X99999", "volatility_breakout", "near", now=base) is False

    # 사이클 reset
    pool.reset_cycle()
    # 새 사이클에서 5건 다시 가능
    ok = pool.mark_promoted("Y99999", "volatility_breakout", "near", now=base + 60)
    assert ok is True
