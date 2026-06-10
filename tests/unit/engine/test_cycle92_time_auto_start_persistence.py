"""사이클 92 L-2 — TIME_AUTO_START 07:45 영속 (LOW, Q29=A).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A1 + Q29=A 영속:
- TIME_AUTO_START 07:45 영속 (Python loop 영역, KIS 무관)
- run_daily() 기상은 KIS 영향 0
- 시정 영역 = TIME_BOOT (사이클 92) + TIME_PRESUBSCRIBE (사이클 92) 한정

기대 동작 (Green, 사이클 92):
- TIME_AUTO_START == time(7, 45) 영속 (변경 0)

Red 상태 (사이클 92, production 변경 0):
- 현재 영속 → PASS (영속 가드)

영속 의무:
- Q29=A TIME_AUTO_START 07:45 영속 (Python loop 영역)
- 사이클 92 시정 영역 = TIME_BOOT + TIME_PRESUBSCRIBE 한정
"""
from __future__ import annotations

from datetime import time

import pytest

pytestmark = pytest.mark.unit


def test_l2_time_auto_start_persists_at_745():
    """L-2-1: TIME_AUTO_START == time(7, 45) 영속 (Q29=A).

    검증:
    - `src/engine/scheduler.py::TIME_AUTO_START` == time(7, 45)
    - 사이클 92 시정 후에도 영속 (Python loop 영역, KIS 무관)

    영속 의무: Q29=A 사용자 결정 (TIME_AUTO_START 변경 X).
    """
    from src.engine.scheduler import TIME_AUTO_START
    assert TIME_AUTO_START == time(7, 45), (
        f"\n사이클 92 L-2-1 위반 — TIME_AUTO_START 변경 (Q29=A 위반):\n"
        f"  현재값: {TIME_AUTO_START}\n"
        f"  기대값: time(7, 45) (Q29=A 영속)\n"
        f"  근거: Python loop 영역 영속, 시정 영역 = TIME_BOOT/TIME_PRESUBSCRIBE 한정"
    )


def test_l2_time_pre_nxt_open_persists_at_800():
    """L-2-2: TIME_PRE_NXT_OPEN == time(8, 0) 영속 (NXT 프리 hot path).

    검증:
    - `src/engine/scheduler.py::TIME_PRE_NXT_OPEN` == time(8, 0)
    - 사이클 92 시정 후에도 영속 (NXT 프리 hot path 영향 0)

    영속 의무 (domain-expert A1-Q4): NXT 프리 진입 영역 영향 0.
    """
    from src.engine.scheduler import TIME_PRE_NXT_OPEN
    assert TIME_PRE_NXT_OPEN == time(8, 0), (
        f"\n사이클 92 L-2-2 위반 — TIME_PRE_NXT_OPEN 변경 (NXT hot path 위반):\n"
        f"  현재값: {TIME_PRE_NXT_OPEN}\n"
        f"  기대값: time(8, 0) (영속)\n"
        f"  근거: NXT 프리 진입 hot path 영속"
    )


def test_l2_time_krx_open_confirm_persists():
    """L-2-3: TIME_KRX_OPEN_CONFIRM 영속 (KRX 메인 hot path).

    검증:
    - TIME_KRX_OPEN_CONFIRM == time(9, 0, 5) 영속

    영속 의무: KRX 09:00 시가 확정 영역 영속.
    """
    from src.engine.scheduler import TIME_KRX_OPEN_CONFIRM
    assert TIME_KRX_OPEN_CONFIRM == time(9, 0, 5), (
        f"\n사이클 92 L-2-3 위반 — TIME_KRX_OPEN_CONFIRM 변경:\n"
        f"  현재값: {TIME_KRX_OPEN_CONFIRM}\n"
        f"  기대값: time(9, 0, 5) (영속)"
    )
