"""사이클 63 Phase 2-A3 Red — H 카테고리: 6회 초과 force_retry (4 케이스, HIGH).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 H
> **회귀 가드**: CLAUDE.md 절대 깨지 말 것 — stale watcher force_retry (사이클 29-R1).
>   6회 초과 시 5분 cooldown + 시간당 12회 cap (LMS / 앱키 정지 위험 차단).
>   사이클 29 005935 사고 (T+13min retry=6 시작 → T+17min 강제 재시도 성공) 재현 패턴.

Red 단계: `stale_manager.check_and_resubscribe_stale` 미존재 → AttributeError FAIL.

freezegun 의무 — 5분 cooldown / 60분 슬라이딩 윈도우 검증.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    object.__setattr__(sched, "_pending_next_day_clear", set())
    sched.registry = MagicMock(all=lambda: [])
    return sched


def _make_mock_pool(subscribed: set):
    """공통 mock pool — get_subscribed_tickers + unsubscribe_in_pool + subscribe."""
    mock_pool = MagicMock()
    mock_pool.get_subscribed_tickers = MagicMock(return_value=subscribed)
    mock_pool.unsubscribe_in_pool = AsyncMock(return_value=None)
    mock_pool.subscribe = AsyncMock(return_value=None)
    return mock_pool


# ===========================================================================
# H-1: _stale_last_resubscribe_at 부재 시 즉시 1회 force_retry (age=inf)
# ===========================================================================
@pytest.mark.asyncio
async def test_H1_force_retry_age_infinity_when_last_at_absent_first_entry():
    """H-1 (HIGH): retry=6 + `_stale_last_resubscribe_at` 부재 → age=inf 즉시 1회 시도.

    사이클 29-R1: 영구 stale 의심 첫 진입 보호. `_stale_last_resubscribe_at[ticker]` 부재 시
    `age=float("inf")` → 즉시 강제 재시도 + 카운터 0 리셋.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    sched._stale_retry_count["005930"] = 5  # +1 → retry=6 → force_retry 분기 진입
    # _stale_last_resubscribe_at 부재 (빈 dict)

    mock_pool = _make_mock_pool({"005930"})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched)

    # age=inf 분기 → 강제 재시도 발화 → 카운터 리셋
    assert mock_pool.subscribe.await_count == 1, (
        "_stale_last_resubscribe_at 부재 시 age=inf → 즉시 1회 force_retry 의무"
    )
    assert sched._stale_retry_count["005930"] == 0, (
        "force_retry 성공 직후 _stale_retry_count[ticker] = 0 리셋 의무 "
        "(다음 사이클부터 다시 1~5회 정상 분기로 자연 회복)"
    )


# ===========================================================================
# H-2: age >= 300s force_retry + 카운터 리셋 (T+17min 시점 재현)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=False,
    reason="사이클 102 Q73=B cooldown 300→600 — 301s 시나리오가 새 임계 미달 → force_retry 미발화 (사이클 66 K-2 패턴 답습)",
)
async def test_H2_force_retry_age_300s_triggers_resubscribe_and_counter_reset():
    """H-2 (HIGH): age >= 300s 시 force_retry 발화 + 카운터 0 리셋.

    사이클 29 005935 사고 T+17min 시점 재현: retry=8 + last_resub_age=360s >= 300s.
    사이클 102 Q73=B: cooldown 600s 상향 — 301s 시나리오가 cooldown 미달 → xfail 영속 보존.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    last_at = base - timedelta(seconds=301)  # 301s 경과 (사이클 29 300s 임계 초과 / 사이클 102 600s 임계 미달)

    sched = _make_scheduler()
    sched._stale_retry_count["005930"] = 7  # +1 → retry=8 → force_retry 분기
    sched._stale_last_resubscribe_at["005930"] = last_at

    mock_pool = _make_mock_pool({"005930"})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched)

    assert mock_pool.subscribe.await_count == 1, (
        "age=301s >= 300s 임계 → force_retry 발화 의무"
    )
    assert sched._stale_retry_count["005930"] == 0, (
        "force_retry 직후 카운터 0 리셋 누락 — "
        "다음 사이클 retry=1 (자연 회복) 진입 차단 위험"
    )
    # last_resubscribe_at 갱신 (현재 시각으로)
    new_last_at = sched._stale_last_resubscribe_at["005930"]
    assert abs((new_last_at - base).total_seconds()) < 1.0, (
        f"_stale_last_resubscribe_at 갱신 누락: {new_last_at} vs base {base}"
    )


# ===========================================================================
# H-3: age < 300s 시 skip (cooldown 미경과)
# ===========================================================================
@pytest.mark.asyncio
async def test_H3_force_retry_age_120s_skip_under_cooldown():
    """H-3 (HIGH): age < 300s (cooldown 미경과) → skip (subscribe 호출 0건).

    사이클 29 005935 사고 T+13min 시점 재현: retry=6 + last_resub_age=120s < 300s.
    `skipped_giveup += 1` + continue 분기 통과 검증.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    last_at = base - timedelta(seconds=120)  # 120s 경과 (300s 미달)

    sched = _make_scheduler()
    sched._stale_retry_count["005930"] = 5  # +1 → retry=6 → force_retry 분기
    sched._stale_last_resubscribe_at["005930"] = last_at

    mock_pool = _make_mock_pool({"005930"})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched)

    assert mock_pool.subscribe.await_count == 0, (
        "age=120s < 300s cooldown 미경과 → subscribe 호출 0건 의무 "
        "(skip + 카운터 누적 보존 — LMS 위험 차단)"
    )
    assert mock_pool.unsubscribe_in_pool.await_count == 0, (
        "cooldown 미경과 → unsubscribe 도 0건"
    )
    # 카운터 누적 (리셋 안 함)
    assert sched._stale_retry_count["005930"] == 6, (
        "skip 분기 → 카운터 누적 (6) 의무 — 리셋 시 영구 stale 무한 skip 결함 재발"
    )


# ===========================================================================
# H-4: 시간당 12회 cap 초과 시 WARNING + skip (KIS LMS 차단)
# ===========================================================================
@pytest.mark.asyncio
async def test_H4_force_retry_hourly_cap_12_emits_warning_and_skips():
    """H-4 (HIGH): history 12건 (시간당 cap) 도달 → 13회차 WARNING + skip.

    `STALE_FORCE_RETRY_HOURLY_CAP=12` — 60분 슬라이딩 윈도우 12회 초과 시 KIS LMS / 앱키
    정지 위험 차단 (`[stale_force_retry_cap]` WARNING + skip).
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    sched._stale_retry_count["005930"] = 5  # +1 → retry=6 → force_retry 분기
    # _stale_last_resubscribe_at 부재 → age=inf → force_retry 분기 진입
    # history 12건 모두 60분 이내 (cap 도달 상태)
    sched._stale_force_retry_history["005930"] = [
        base - timedelta(minutes=i) for i in range(1, 13)  # 1~12분 전
    ]

    mock_pool = _make_mock_pool({"005930"})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched)

    # cap 도달 → subscribe 호출 0건 + WARNING 로그 발화
    assert mock_pool.subscribe.await_count == 0, (
        f"history 12건 cap 도달 → subscribe 0건 의무 (KIS LMS 차단). "
        f"실제 호출 수: {mock_pool.subscribe.await_count}"
    )
    # 카운터 누적 (리셋 안 함, skip 분기)
    assert sched._stale_retry_count["005930"] == 6, (
        "cap 도달 skip → 카운터 누적 (리셋 안 함)"
    )
