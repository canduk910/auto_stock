"""사이클 26 — _BOARD_SCHEDULE 변경 검증.

계획서 H 영역: 5 케이스
- 08:00 → PRE_NXT 단독
- 09:00 → MAIN 단독 (KRX_OPEN 제거됨)
- 15:40 → POST_NXT 단독
- 갭 시간 (15:30~15:39) 직전 보드(MAIN) 유지 확인
- KRX_OPEN / KRX_AFTER 보드 제거 확인 (08:30~09:00 구간, 15:30~18:00 구간)
"""

from __future__ import annotations

from datetime import time

import pytest

from src.engine.session import MarketBoard, boards_at

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 1. 08:00 → PRE_NXT 단독
# ---------------------------------------------------------------------------
def test_boards_at_0800_is_pre_nxt_only():
    """08:00 은 PRE_NXT 만 활성이어야 한다 (사이클 26: KRX_OPEN 구간 제거)."""
    boards = boards_at(time(8, 0))
    assert boards == frozenset({MarketBoard.PRE_NXT})
    assert MarketBoard.KRX_OPEN not in boards


# ---------------------------------------------------------------------------
# 2. 09:00 → MAIN 단독 (KRX_OPEN 제거)
# ---------------------------------------------------------------------------
def test_boards_at_0900_is_main_only():
    """09:00 은 MAIN 만 활성이어야 한다 (KRX_OPEN 구간 제거, 사이클 26)."""
    boards = boards_at(time(9, 0))
    assert boards == frozenset({MarketBoard.MAIN})
    assert MarketBoard.KRX_OPEN not in boards
    assert MarketBoard.PRE_NXT not in boards


# ---------------------------------------------------------------------------
# 3. 15:40 → POST_NXT 단독
# ---------------------------------------------------------------------------
def test_boards_at_1540_is_post_nxt():
    """15:40 은 POST_NXT 가 활성이어야 한다 (사이클 26: KRX_MAIN_CLOSE → 15:40)."""
    boards = boards_at(time(15, 40))
    assert MarketBoard.POST_NXT in boards
    assert MarketBoard.MAIN not in boards
    assert MarketBoard.KRX_AFTER not in boards


# ---------------------------------------------------------------------------
# 4. 갭 구간(15:30~15:39:59) — MAIN 유지 (종가 흡수 마진)
# ---------------------------------------------------------------------------
def test_boards_at_gap_15_30_to_15_39_is_main():
    """15:30~15:39:59 구간은 MAIN 이 유지되어야 한다 (종가 흡수 10분 마진, 사이클 26)."""
    for t in (time(15, 30), time(15, 35), time(15, 39, 59)):
        boards = boards_at(t)
        assert MarketBoard.MAIN in boards, f"{t} 에서 MAIN 이 유지되어야 한다"
        assert MarketBoard.KRX_AFTER not in boards, f"{t} 에서 KRX_AFTER 제거 확인"
        assert MarketBoard.POST_NXT not in boards, f"{t} 에서 POST_NXT 미진입 확인"


# ---------------------------------------------------------------------------
# 5. KRX_OPEN (08:30~09:00) / KRX_AFTER (15:30~18:00) 제거 확인
# ---------------------------------------------------------------------------
def test_krx_open_board_removed_from_schedule():
    """사이클 26: KRX_OPEN 보드는 어느 시각에도 활성화되지 않아야 한다."""
    probe_times = [
        time(8, 30), time(8, 45), time(8, 59),
    ]
    for t in probe_times:
        boards = boards_at(t)
        assert MarketBoard.KRX_OPEN not in boards, (
            f"KRX_OPEN 은 {t} 에서 제거되어야 한다 (사이클 26)"
        )


def test_krx_after_board_removed_from_schedule():
    """사이클 26: KRX_AFTER 보드는 어느 시각에도 활성화되지 않아야 한다."""
    probe_times = [
        time(15, 30), time(16, 0), time(17, 0), time(17, 59),
    ]
    for t in probe_times:
        boards = boards_at(t)
        assert MarketBoard.KRX_AFTER not in boards, (
            f"KRX_AFTER 는 {t} 에서 제거되어야 한다 (사이클 26)"
        )
