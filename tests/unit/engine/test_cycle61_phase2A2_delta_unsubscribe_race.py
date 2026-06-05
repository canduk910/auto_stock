"""사이클 61 Phase 2-A2 Red — K 카테고리: delta unsubscribe race 시뮬레이션 (1 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (Q6-G1, best-effort)

`_delta_unsubscribe_dropped` 이 `_scan_loop` + `_board_transition_loop` 동시 발화 시
동일 종목 unsubscribe 충돌 — *현재 행위 기록 only*.

검증:
1. `asyncio.gather(call_a, call_b)` 동시 호출
2. `kis_ws_pool.unsubscribe` mock 호출 카운트 >= 1
   (현재 행위 = mutex 없음, 동일 종목 2회 unsubscribe 호출 가능 = KIS 무해)

본 테스트는 *행위 기록* 목적. 실제 mutex 도입은 별개 카드 #11 (본 사이클 *밖*).

Red 단계: stale_manager.delta_unsubscribe_dropped 미존재 → AttributeError 정상.

회귀 가드: KIS "비정상 케이스 2" (무한 등록/해제) 차단 — 행위 보존.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    return sched


@pytest.mark.asyncio
async def test_K1_delta_unsubscribe_race_records_current_behavior():
    """K-1: 현재 행위 = mutex 없음, 동일 종목 동시 호출 가능 (KIS 무해).

    `asyncio.gather` 로 2회 동시 호출 → unsubscribe 카운트 >= 1.
    별개 카드 #11 (보드 전환 mutex) 발의 근거.
    """
    from src.engine import stale_manager  # noqa: F401 — Red: AttributeError 가능

    sched = _make_scheduler()

    # kis_ws_pool.get_subscribed_tickers() = {"005930"} → delta_remove = {"005930"} (new_set = {} 시)
    with patch("src.realtime.websocket_pool.kis_ws_pool") as mock_pool, \
         patch("src.engine.scheduler.write_log", new=AsyncMock(return_value=None)):
        mock_pool.get_subscribed_tickers = MagicMock(return_value={"005930"})
        mock_pool.unsubscribe = AsyncMock(return_value=None)

        # 동시 호출 (race 시뮬레이션)
        results = await asyncio.gather(
            sched._delta_unsubscribe_dropped(set()),
            sched._delta_unsubscribe_dropped(set()),
        )

        # 현재 행위 = 2회 호출 가능 (mutex 없음). 별개 카드 #11 발의 근거.
        assert mock_pool.unsubscribe.call_count >= 1, (
            "동시 호출 시 최소 1회는 unsubscribe 발화 (mutex 도입 시 1회, 미도입 시 2회)"
        )

    # 결과 list 반환 형식 보존 (KIS "비정상 케이스 2" 차단 행위 보존)
    assert all(isinstance(r, list) for r in results), (
        "_delta_unsubscribe_dropped 반환 형식 = list[str] 보존 의무"
    )
