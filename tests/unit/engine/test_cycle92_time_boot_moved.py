"""사이클 92 H-1 — TIME_BOOT 07:50 → 07:55 이동 + TIME_PRESUBSCRIBE 동행 이동 (HIGH).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A1-Q3 영속:
- Q28=E TIME_BOOT 07:50 → 07:55 (KIS 강제 중단 후 5분 마진)
- Q32=B TIME_PRESUBSCRIBE 07:55 → 07:59 (_boot 완료 후 4분 마진, race 회피)
- Q29=A TIME_AUTO_START 07:45 영속 (Python loop 영역, L-2 별개 가드)
- Q28=A 안전 마진 정적 검증 (TIME_BOOT - TIME_AUTO_START >= 10분)

기대 동작 (Green, 사이클 92):
- TIME_BOOT == time(7, 55) — KIS 강제 중단 (07:50) 후 5분 마진
- TIME_PRESUBSCRIBE == time(7, 59) — _boot 완료 후 4분 마진 race 회피
- TIME_BOOT < TIME_PRE_NXT_OPEN — NXT 프리 진입 (08:00) 이전 보장
- TIME_PRESUBSCRIBE < TIME_PRE_NXT_OPEN — 사전 구독 완료 보장

Red 상태 (사이클 92, production 변경 0):
- TIME_BOOT == time(7, 50) ≠ time(7, 55) → AssertionError
- TIME_PRESUBSCRIBE == time(7, 55) ≠ time(7, 59) → AssertionError

영속 의무:
- 사이클 88 G-REJECT-1 (4중 안전망 영속) — 시간 상수 변경은 4중 안전망 구조 무영향
- 사이클 38 명문화 (tradable_boards 매수 진입 전용) — 시간 영역 영향 0
- TIME_AUTO_START 07:45 영속 (L-2 별개 가드)
- TIME_PRE_NXT_OPEN 08:00 영속 (NXT 프리 진입 hot path)
"""
from __future__ import annotations

from datetime import time

import pytest

pytestmark = pytest.mark.unit


def test_h1_time_boot_moved_to_755():
    """H-1: TIME_BOOT == time(7, 55) 정합 (사이클 92 Q28=E 영속 확인).

    검증:
    - `src/engine/scheduler.py::TIME_BOOT` == time(7, 55)
    - KIS 강제 중단 (07:50) 후 5분 마진 영속 정합

    Red 상태 (사이클 92): TIME_BOOT == time(7, 50) → AssertionError.
    Green (사이클 92 시정): backend-dev L52 `TIME_BOOT = time(7, 55)` → PASS.

    영속 의무:
    - 사이클 88 G-REJECT-1 (4중 안전망 영속) — 시간 상수 변경 4중 안전망 구조 무영향
    - 사이클 38 명문화 — 시간 영역 영향 0
    """
    from src.engine.scheduler import TIME_BOOT
    assert TIME_BOOT == time(7, 55), (
        f"\n사이클 92 H-1 위반 — TIME_BOOT 영구 이동 누락:\n"
        f"  현재값: {TIME_BOOT}\n"
        f"  기대값: time(7, 55) (Q28=E 영속)\n"
        f"  근거: KIS 07:50 강제 중단 + 5분 마진 의무 (Phase 1 §5.2 chain)"
    )


def test_h1_time_presubscribe_moved_to_759():
    """H-1: TIME_PRESUBSCRIBE == time(7, 59) 정합 (사이클 92 Q32=B 영속 확인).

    검증:
    - `src/engine/scheduler.py::TIME_PRESUBSCRIBE` == time(7, 59)
    - `_boot()` 완료 후 4분 마진 영속 (race 회피)

    Red 상태 (사이클 92): TIME_PRESUBSCRIBE == time(7, 55) → AssertionError.
    Green (사이클 92 시정): backend-dev L53 `TIME_PRESUBSCRIBE = time(7, 59)` → PASS.

    영속 의무 (domain-expert A1-Q3 권고):
    - _boot() 완료 후 사전 구독 분리 = 명시적 단계 분리 (트레이더 본능)
    - 사이클 88 G-REJECT-1 영속 (4중 안전망 구조 무영향)
    """
    from src.engine.scheduler import TIME_PRESUBSCRIBE
    assert TIME_PRESUBSCRIBE == time(7, 59), (
        f"\n사이클 92 H-1 위반 — TIME_PRESUBSCRIBE 동행 이동 누락:\n"
        f"  현재값: {TIME_PRESUBSCRIBE}\n"
        f"  기대값: time(7, 59) (Q32=B 영속, domain-expert P1 권고)\n"
        f"  근거: _boot() 완료 후 4분 마진 race 회피"
    )


def test_h1_time_boot_safety_margin_from_auto_start():
    """H-1: TIME_BOOT - TIME_AUTO_START >= 10분 안전 마진 (정적 AST).

    검증:
    - TIME_AUTO_START 07:45 + 10분 = 07:55 ≤ TIME_BOOT
    - 즉 (TIME_BOOT.hour, TIME_BOOT.minute) >= (7, 55)
    - KIS 강제 중단 안전 마진 보장 (07:50 + 5분 마진 = 07:55)

    Red 상태 (사이클 92): TIME_BOOT == time(7, 50) → margin = 5분 < 10분 → AssertionError.
    Green (사이클 92 시정): TIME_BOOT == time(7, 55) → margin = 10분 == 10분 → PASS.

    영속 의무: 사이클 92 시정 영속 후에도 자동 검증 (미래 시간 변경 시 회귀 차단).
    """
    from src.engine.scheduler import TIME_AUTO_START, TIME_BOOT

    # 분 단위 계산
    auto_start_min = TIME_AUTO_START.hour * 60 + TIME_AUTO_START.minute
    boot_min = TIME_BOOT.hour * 60 + TIME_BOOT.minute
    margin_min = boot_min - auto_start_min

    assert margin_min >= 10, (
        f"\n사이클 92 H-1 위반 — TIME_BOOT 안전 마진 부족:\n"
        f"  TIME_AUTO_START={TIME_AUTO_START}, TIME_BOOT={TIME_BOOT}\n"
        f"  현재 margin: {margin_min}분 < 10분\n"
        f"  근거: KIS 07:50 강제 중단 + 5분 마진 = 07:55 (Q28=E)"
    )


def test_h1_time_boot_before_pre_nxt_open():
    """H-1: TIME_BOOT < TIME_PRE_NXT_OPEN (NXT 프리 진입 이전 보장).

    검증:
    - TIME_PRE_NXT_OPEN 08:00 (영속) > TIME_BOOT
    - _boot() 가 NXT 프리 진입 (08:00) *전* 완료 의무

    영속 의무 (domain-expert A1-Q4):
    - TIME_PRE_NXT_OPEN 08:00 영속 (NXT 프리 hot path 영향 0)
    - _boot() 동기 영역 → TIME_PRESUBSCRIBE/TIME_PRE_NXT_OPEN 자동 대기 → race 0
    """
    from src.engine.scheduler import TIME_BOOT, TIME_PRE_NXT_OPEN

    assert TIME_BOOT < TIME_PRE_NXT_OPEN, (
        f"\n사이클 92 H-1 위반 — TIME_BOOT >= TIME_PRE_NXT_OPEN (NXT 프리 race 위험):\n"
        f"  TIME_BOOT={TIME_BOOT}, TIME_PRE_NXT_OPEN={TIME_PRE_NXT_OPEN}\n"
        f"  근거: _boot() 가 NXT 프리 진입 *전* 완료 의무"
    )


def test_h1_time_presubscribe_before_pre_nxt_open():
    """H-1: TIME_PRESUBSCRIBE < TIME_PRE_NXT_OPEN (사전 구독 완료 보장).

    검증:
    - TIME_PRESUBSCRIBE 07:59 < TIME_PRE_NXT_OPEN 08:00
    - 사전 구독 (TIME_PRESUBSCRIBE) → NXT 프리 (TIME_PRE_NXT_OPEN) 순서 영속
    """
    from src.engine.scheduler import TIME_PRE_NXT_OPEN, TIME_PRESUBSCRIBE

    assert TIME_PRESUBSCRIBE < TIME_PRE_NXT_OPEN, (
        f"\n사이클 92 H-1 위반 — TIME_PRESUBSCRIBE >= TIME_PRE_NXT_OPEN:\n"
        f"  TIME_PRESUBSCRIBE={TIME_PRESUBSCRIBE}, TIME_PRE_NXT_OPEN={TIME_PRE_NXT_OPEN}\n"
        f"  근거: 사전 구독 → NXT 프리 순서 영속 의무"
    )
