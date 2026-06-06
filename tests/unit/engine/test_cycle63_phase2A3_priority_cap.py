"""사이클 63 Phase 2-A3 Red — K 카테고리: `_resubscribe_stale_priority` cap=10 (2 케이스).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 K
> **회귀 가드**: 사이클 25-B — `_scan_loop` 5분 우선 재구독 cap=10 + sorted 결정성.
> **Q5-3 결함 확인 의무**: cap 적용이 priority 분리 *전* (`stale_tickers[:cap]` L2748).
>   stale 30 종목 중 sorted "0..." 우선 LOW 후보 10건 cap 채우면 HIGH 005935 cap 밖.

Red 단계: `stale_manager.resubscribe_stale_priority` 미존재 → AttributeError FAIL.

K-2 = 현재 코드 결함 confirm 케이스 — Green 단계에서 K-2 결함 재현 시 사이클 64+ 카드 #5 발의.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _make_scheduler_with_high_tickers(positions: list[str] = None, ndc: set = None):
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    object.__setattr__(sched, "_pending_next_day_clear", ndc or set())

    strategy_state = MagicMock()
    strategy_state.positions = {t: MagicMock() for t in (positions or [])}
    strategy = MagicMock(state=strategy_state)
    sched.registry = MagicMock(all=lambda: [strategy] if positions else [])
    return sched


# ===========================================================================
# K-1: stale 30 종목 중 cap=10 만 재구독 + sorted 결정성
# ===========================================================================
@pytest.mark.asyncio
async def test_K1_cap_10_limits_resubscribe_targets_with_sorted_determinism():
    """K-1: stale 30 종목 → sorted 결정성 + cap=10 → subscribe 호출 10회.

    `stale_tickers = sorted(...)` → `targets = stale_tickers[:cap]`
    결정적 순서 (알파벳 ascending) + cap 적용.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers()

    # 30 종목 stale — ticker_last_tick 30 종목 모두 base - 120s (60s threshold 초과)
    stale_30 = [f"{i:06d}" for i in range(30)]  # 000000, 000001, ..., 000029
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {t: stale_dt for t in stale_30}

    mock_pool = MagicMock()
    mock_pool.subscribe = AsyncMock(return_value=None)

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert mock_pool.subscribe.await_count == 10, (
        f"cap=10 적용 → subscribe 정확 10회 의무. 실제: {mock_pool.subscribe.await_count}"
    )
    # sorted 결정성 → "000000" ~ "000009" 우선
    expected_targets = [f"{i:06d}" for i in range(10)]
    assert result == expected_targets, (
        f"sorted 결정성 위반 — 기대: {expected_targets}, 실제: {result}"
    )


# ===========================================================================
# K-2: Q5-3 cap=10 결함 가능성 — HIGH 005935 cap 밖 잘림 시나리오 (현재 결함 confirm)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 66 시정 완료 — K-2 의미 전환: 결함 confirm PASS → 시정 confirm (XFAIL expected). "
        "HIGH 005930 이 이제 cap 우선 보장되어 'not in result' assertion 이 자연히 FAIL. "
        "본 파일은 사이클 63 당시 결함 영속 기록으로 보존 (삭제 금지)."
    ),
)
async def test_K2_cap_10_defect_high_ticker_excluded_by_sorted_order_currently_buggy():
    """K-2 (Q5-3 결함 confirm): HIGH 005930 이 sorted "0..." 우선 LOW 10건에 밀려 cap 밖.

    domain Q5-3 자문 발견 — 현재 코드 결함 가능성:
    - cap=10 적용이 priority 분리 *전*  (`stale_tickers[:cap]` L2748)
    - stale 11 종목 중 sorted 결과 "000000..000009" (LOW 후보 10건) + "005930" (HIGH)
    - cap=10 적용 시 "005930" (HIGH) 가 잘림 → HIGH 종목 재구독 누락

    본 케이스는 **현재 결함 confirm** — backend-dev Green 단계에서 결함 재현 확인 시
    사이클 64+ 카드 #5 별도 발의 의무.

    Green 단계 예상 결과: subscribe 호출 10회 모두 LOW 후보 ("000000..000009"),
    HIGH "005930" 은 cap 밖 → 호출 안 됨 (결함 confirm = PASS).

    시정 후 (카드 #5 채택 시): HIGH 우선 보장 → "005930" 포함 보장.
    """
    from src.engine import stale_manager  # Red: AttributeError 가능

    base = datetime(2026, 6, 5, 10, 0, 0, tzinfo=KST)
    # 005930 = positions 소속 → HIGH
    sched = _make_scheduler_with_high_tickers(positions=["005930"])

    # stale 11 종목: "000000" ~ "000009" (LOW 10건) + "005930" (HIGH 1건)
    low_tickers = [f"{i:06d}" for i in range(10)]
    stale_tickers_all = low_tickers + ["005930"]
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {t: stale_dt for t in stale_tickers_all}

    mock_pool = MagicMock()
    mock_pool.subscribe = AsyncMock(return_value=None)

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    # 현재 결함 confirm — HIGH "005930" 이 cap 밖으로 잘림
    # sorted 결과: ["000000", ..., "000009", "005930"] → cap=10 → "000000..000009"
    assert "005930" not in result, (
        "Q5-3 결함 confirm 케이스: 현재 코드는 HIGH 종목 005930 이 sorted '0...' 우선 "
        "LOW 10건에 밀려 cap 밖 잘림. 본 assertion PASS = 결함 confirm "
        "→ 사이클 64+ 카드 #5 발의 의무. 본 assertion FAIL = 결함 시정 완료 "
        "(예상치 못한 PASS)"
    )
    assert len(result) == 10, (
        f"cap=10 정확 적용. 실제: {len(result)}"
    )
    # 현재 결함 결과: LOW 후보 10건만 재구독, HIGH 005930 누락
    assert set(result) == set(low_tickers), (
        f"현재 결함 결과 — LOW 후보 10건만 재구독. 실제: {result}"
    )
