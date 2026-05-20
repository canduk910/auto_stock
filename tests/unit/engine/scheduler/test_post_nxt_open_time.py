"""사이클 26 — TIME_POST_NXT_OPEN = 15:40 + TIME_KRX_MAIN_CLOSE 분기 검증.

계획서 H 영역: 2 케이스
- TIME_POST_NXT_OPEN = 15:40 상수 확인
- TIME_KRX_MAIN_CLOSE 기반 _force_clear_main_only 시간 가드가 15:30 기준 유지
"""

from __future__ import annotations

from datetime import time

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 1. TIME_POST_NXT_OPEN = 15:40
# ---------------------------------------------------------------------------
def test_time_post_nxt_open_is_15_40():
    """사이클 26: TIME_POST_NXT_OPEN = time(15, 40) 이어야 한다."""
    from src.engine import scheduler
    assert hasattr(scheduler, "TIME_POST_NXT_OPEN"), "TIME_POST_NXT_OPEN 상수 없음"
    assert scheduler.TIME_POST_NXT_OPEN == time(15, 40), (
        f"TIME_POST_NXT_OPEN = {scheduler.TIME_POST_NXT_OPEN} (기대: time(15,40))"
    )


# ---------------------------------------------------------------------------
# 2. TIME_KRX_MAIN_CLOSE = 15:30 유지 (기존 _force_clear_main_only 시간 가드 기준)
# ---------------------------------------------------------------------------
def test_time_krx_main_close_still_1530():
    """TIME_KRX_MAIN_CLOSE 는 15:30 이어야 한다 (_force_clear_main_only 시간 가드 기준).

    POST_NXT 전환은 TIME_POST_NXT_OPEN(15:40) 로 변경되었지만,
    _force_clear_main_only 의 `now_t >= TIME_KRX_MAIN_CLOSE` 가드는 15:30 기준 유지.
    """
    from src.engine import scheduler
    assert scheduler.TIME_KRX_MAIN_CLOSE == time(15, 30), (
        f"TIME_KRX_MAIN_CLOSE = {scheduler.TIME_KRX_MAIN_CLOSE} (기대: time(15,30))"
    )
