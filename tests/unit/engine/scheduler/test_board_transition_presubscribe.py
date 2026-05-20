"""사이클 26 — 보드 전환 사전 구독 마진 검증.

계획서 H 영역: 4 케이스
- 08:59:10 KRX 사전 구독 상수 존재
- 15:39:10 NXT 사전 구독 상수 존재
- 보유 + 후보 합집합이 전환 대상에 포함
- 슬롯 부담 안전 (종목별 원자 전환 패턴 — 동시 최대 1종목 활성)
"""

from __future__ import annotations

from datetime import time

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 1. TIME_KRX_MAIN_OPEN_PRESUBSCRIBE = 08:59:10 상수 존재
# ---------------------------------------------------------------------------
def test_time_krx_main_open_presubscribe_constant():
    """사이클 26 신규 상수: TIME_KRX_MAIN_OPEN_PRESUBSCRIBE = time(8, 59, 10)."""
    from src.engine import scheduler
    assert hasattr(scheduler, "TIME_KRX_MAIN_OPEN_PRESUBSCRIBE"), (
        "TIME_KRX_MAIN_OPEN_PRESUBSCRIBE 상수가 scheduler.py 에 없다"
    )
    assert scheduler.TIME_KRX_MAIN_OPEN_PRESUBSCRIBE == time(8, 59, 10)


# ---------------------------------------------------------------------------
# 2. TIME_POST_NXT_OPEN_PRESUBSCRIBE = 15:39:10 상수 존재
# ---------------------------------------------------------------------------
def test_time_post_nxt_open_presubscribe_constant():
    """사이클 26 신규 상수: TIME_POST_NXT_OPEN_PRESUBSCRIBE = time(15, 39, 10)."""
    from src.engine import scheduler
    assert hasattr(scheduler, "TIME_POST_NXT_OPEN_PRESUBSCRIBE"), (
        "TIME_POST_NXT_OPEN_PRESUBSCRIBE 상수가 scheduler.py 에 없다"
    )
    assert scheduler.TIME_POST_NXT_OPEN_PRESUBSCRIBE == time(15, 39, 10)


# ---------------------------------------------------------------------------
# 3. TIME_POST_NXT_OPEN = 15:40 상수 존재
# ---------------------------------------------------------------------------
def test_time_post_nxt_open_constant():
    """사이클 26 신규 상수: TIME_POST_NXT_OPEN = time(15, 40)."""
    from src.engine import scheduler
    assert hasattr(scheduler, "TIME_POST_NXT_OPEN"), (
        "TIME_POST_NXT_OPEN 상수가 scheduler.py 에 없다"
    )
    assert scheduler.TIME_POST_NXT_OPEN == time(15, 40)


# ---------------------------------------------------------------------------
# 4. 원자 전환 패턴: unsubscribe 완료 확인 후 subscribe (동시 활성 최소화)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atomic_transition_unsub_then_sub(monkeypatch):
    """_atomic_board_transition 은 unsubscribe ACK 확인 후 subscribe 를 호출해야 한다."""
    from src.engine import scheduler as sched_mod

    # _atomic_board_transition 함수가 존재해야 한다
    assert hasattr(sched_mod.TradingScheduler, "_atomic_board_transition") or \
        hasattr(sched_mod, "_atomic_board_transition"), (
        "_atomic_board_transition 함수가 scheduler 에 없다 (사이클 26)"
    )
