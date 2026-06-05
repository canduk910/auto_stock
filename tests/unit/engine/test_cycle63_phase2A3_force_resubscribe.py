"""사이클 63 Phase 2-A3 Red — G 카테고리: 1~5회 즉시 강제 재등록 (3 케이스, HIGH).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 G
> **회귀 가드**: CLAUDE.md 절대 깨지 말 것 — stale watcher force_retry (사이클 17 보강).
>   KIS 공식 답변 인용: "기등록한 사항을 재등록하지 않도록 (다수 요청 시 LMS + 앱정보 이용중지)"
>   → 1~5회 첫 stale 즉시 `unsubscribe_in_pool` + `subscribe(HIGH/LOW, bypass=...)` 강제 재등록.
>   재SEND 0건 (KIS 정상 "신규 등록" 패턴).

Red 단계: `stale_manager.check_and_resubscribe_stale` 미존재 → AttributeError FAIL.

Green 단계: 본체 이주 후 mock pool 호출 검증 통과.
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
    # registry / _pending_next_day_clear 격리 (HIGH/LOW 분기 검증은 I 카테고리)
    object.__setattr__(sched, "_pending_next_day_clear", set())
    sched.registry = MagicMock(all=lambda: [])
    return sched


# ===========================================================================
# G-1: 첫 stale (retry=1) → 즉시 unsubscribe + 50ms sleep + subscribe (HIGH)
# ===========================================================================
@pytest.mark.asyncio
async def test_G1_first_stale_retry_1_triggers_immediate_unsubscribe_then_subscribe():
    """G-1 (HIGH): 첫 stale → unsubscribe_in_pool + subscribe (KIS 정상 신규 등록 패턴).

    사이클 17 보강: KIS 공식 답변 반영, `resend_subscribe_for_ticker` (재SEND) 분기 완전 폐기.
    첫 stale 즉시 unsubscribe + subscribe 강제 재등록.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    # _stale_retry_count 빈 dict — 첫 stale → retry=1 (1~5회 분기)

    # pool mock — get_subscribed_tickers + unsubscribe_in_pool + subscribe
    mock_pool = MagicMock()
    mock_pool.get_subscribed_tickers = MagicMock(return_value={"005930"})
    mock_pool.unsubscribe_in_pool = AsyncMock(return_value=None)
    mock_pool.subscribe = AsyncMock(return_value=None)
    # stale 판정: ticker_last_tick 빈 dict → min_dt → infinite stale
    stale_ticker_last_tick: dict = {}

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=stale_ticker_last_tick):
        await stale_manager.check_and_resubscribe_stale(sched)

    # 검증: unsubscribe + subscribe 1회 호출
    assert mock_pool.unsubscribe_in_pool.await_count == 1, (
        "첫 stale → unsubscribe_in_pool 1회 호출 의무 (KIS 정상 신규 등록 패턴)"
    )
    assert mock_pool.subscribe.await_count == 1, (
        "첫 stale → subscribe 1회 호출 의무"
    )
    # retry_count 갱신 검증
    assert sched._stale_retry_count.get("005930") == 1, (
        "첫 stale → _stale_retry_count[ticker] = 1"
    )


# ===========================================================================
# G-2: retry=5 (마지막 1~5회 분기) → 동일 즉시 강제 재등록
# ===========================================================================
@pytest.mark.asyncio
async def test_G2_retry_5_still_in_1to5_branch_triggers_immediate_resubscribe():
    """G-2 (HIGH): retry=5 (1~5회 마지막) → 동일 강제 재등록 분기 통과.

    MAX_STALE_RETRIES=5 — `retry > MAX_STALE_RETRIES` 분기는 retry==6 시작.
    retry==5 까지는 1~5회 즉시 강제 재등록 (G-1 동일 분기).
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    sched._stale_retry_count["005930"] = 4  # +1 → retry=5

    mock_pool = MagicMock()
    mock_pool.get_subscribed_tickers = MagicMock(return_value={"005930"})
    mock_pool.unsubscribe_in_pool = AsyncMock(return_value=None)
    mock_pool.subscribe = AsyncMock(return_value=None)

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched)

    assert mock_pool.unsubscribe_in_pool.await_count == 1, (
        "retry=5 (1~5회 마지막) → 즉시 강제 재등록 (force_retry 분기 진입 안 함)"
    )
    assert sched._stale_retry_count["005930"] == 5, (
        "retry=5 누적 (force_retry 분기 진입 안 함 → 카운터 리셋 안 함)"
    )


# ===========================================================================
# G-3: 강제 재등록 직후 _stale_last_resubscribe_at[ticker] 갱신 (사이클 28)
# ===========================================================================
@pytest.mark.asyncio
async def test_G3_after_force_resubscribe_last_resubscribe_at_updated():
    """G-3 (HIGH): 강제 재등록 성공 직후 `_stale_last_resubscribe_at[ticker]` 갱신.

    사이클 28 — 진단 로그 (`[stale_watcher_detail]`) + 사이클 29-R1 force_retry age 계산
    출처. 부재 시 force_retry 분기에서 `age=float("inf")` 즉시 1회 시도 결함 차단.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    # _stale_last_resubscribe_at 빈 dict — 첫 stale 후 갱신 의무

    mock_pool = MagicMock()
    mock_pool.get_subscribed_tickers = MagicMock(return_value={"005930"})
    mock_pool.unsubscribe_in_pool = AsyncMock(return_value=None)
    mock_pool.subscribe = AsyncMock(return_value=None)

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await stale_manager.check_and_resubscribe_stale(sched)

    assert "005930" in sched._stale_last_resubscribe_at, (
        "강제 재등록 직후 _stale_last_resubscribe_at[ticker] 갱신 누락 — "
        "사이클 28 진단 로그 + 사이클 29-R1 force_retry age 계산 결함"
    )
    # 갱신 시각이 base (freezegun) 와 일치 (offset 허용)
    recorded = sched._stale_last_resubscribe_at["005930"]
    assert abs((recorded - base).total_seconds()) < 1.0, (
        f"_stale_last_resubscribe_at 시각 불일치: {recorded} vs base {base}"
    )
