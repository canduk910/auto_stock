"""사이클 101 G-TIME1 — `TIME_FULL_UNIVERSE_LOAD == time(20, 0, 5)` AST + Q67=B 영속 (HIGH).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사용자 결정 Q67=B 영속**:
- 20:00:05 (자문 직후 + NXT 마감 동행)
- 19:55 (자문 *전*) 비채택 — 사이클 89 5분 주기 task 충돌 위험
- 20:08 (정산 *전*) 비채택 — 정산 race 위험 HIGH

검증 매트릭스:
- G-TIME1-A: `TIME_FULL_UNIVERSE_LOAD` 상수 영속 (Red = AttributeError)
- G-TIME1-B: time(20, 0, 5) 정확 영속 (Q67=B 정본)
- G-TIME1-C: AI 자문 영역 (TIME_RECOMMENDATION 20:00:00) *후* 영역 영속 race 0

Red 상태: 신규 상수 부재 → AttributeError.
Green (backend-dev): scheduler.py 모듈 전역 `TIME_FULL_UNIVERSE_LOAD = time(20, 0, 5)` 정의.

영속 의무:
- TIME_NXT_POST_CLOSE 20:00 동행 (NXT 마감 race 0)
- TIME_SETTLEMENT 20:10 *전* 완료 의무 (정산 race 차단)
- 사이클 78 G-AST1 영속 (flush 호출 사이트)
- 사이클 79 G-AST2 영속 (task cancel)
"""
from __future__ import annotations

from datetime import time

import pytest

pytestmark = pytest.mark.unit


def test_g_time1_a_time_full_universe_load_exists() -> None:
    """G-TIME1-A: `TIME_FULL_UNIVERSE_LOAD` 상수 영속 (HIGH).

    Red 상태: 신규 상수 부재 → AttributeError.
    Green (backend-dev): scheduler.py 모듈 전역 정의 의무.
    """
    from src.engine import scheduler

    assert hasattr(scheduler, "TIME_FULL_UNIVERSE_LOAD"), (
        "\n사이클 101 G-TIME1-A Red 상태 — `TIME_FULL_UNIVERSE_LOAD` 부재.\n"
        "  Green (backend-dev): src/engine/scheduler.py 모듈 전역 상수 정의.\n"
        "  Q67=B 영속: time(20, 0, 5) — 자문 직후 + NXT 마감 동행"
    )


def test_g_time1_b_time_full_universe_load_exact_value() -> None:
    """G-TIME1-B: time(20, 0, 5) 정확 영속 (HIGH).

    검증 매트릭스 (Q67=B 채택 영속):
    - 20:00:00 = TIME_RECOMMENDATION (AI 자문 영역)
    - 20:00:05 = TIME_FULL_UNIVERSE_LOAD (사이클 101 신규)
    - 20:10:00 = TIME_SETTLEMENT (정산 영역)

    Red 상태: 잘못된 시각 (예: 19:55 또는 20:08) → race 위험.
    Green (backend-dev): time(20, 0, 5) 정확 영속.
    """
    from src.engine import scheduler

    if not hasattr(scheduler, "TIME_FULL_UNIVERSE_LOAD"):
        pytest.fail(
            "G-TIME1-B Red — `TIME_FULL_UNIVERSE_LOAD` 부재 (G-TIME1-A 영속).\n"
            "  Green: scheduler.py 상수 정의 의무"
        )

    expected = time(20, 0, 5)
    actual = scheduler.TIME_FULL_UNIVERSE_LOAD

    assert actual == expected, (
        f"\n사이클 101 G-TIME1-B 위반 — Q67=B 영속 위반:\n"
        f"  기대: time(20, 0, 5) (Q67=B 채택 영속)\n"
        f"  실제: {actual!r}\n"
        f"  Red 결함 가설: 시점 잘못 (19:55 = 5분 주기 충돌 / 20:08 = 정산 race)\n"
        f"  Green (backend-dev): time(20, 0, 5) 정확 영속 의무"
    )


def test_g_time1_c_time_full_universe_load_after_recommendation() -> None:
    """G-TIME1-C: AI 자문 영역 *후* 영역 영속 race 0 (HIGH).

    검증 매트릭스 (domain-expert A2 영속):
    - TIME_RECOMMENDATION (20:00:00) < TIME_FULL_UNIVERSE_LOAD (20:00:05)
    - TIME_FULL_UNIVERSE_LOAD < TIME_SETTLEMENT (20:10:00)

    Red 상태: 순서 잘못 → AI 자문/정산 영역 race.
    Green (backend-dev): 순서 영속.
    """
    from src.engine import scheduler

    if not hasattr(scheduler, "TIME_FULL_UNIVERSE_LOAD"):
        pytest.fail("G-TIME1-C Red — 상수 부재 (G-TIME1-A 영속)")

    assert (
        scheduler.TIME_RECOMMENDATION
        <= scheduler.TIME_FULL_UNIVERSE_LOAD
        < scheduler.TIME_SETTLEMENT
    ), (
        f"\n사이클 101 G-TIME1-C 위반 — 시점 순서 위반:\n"
        f"  기대 순서: TIME_RECOMMENDATION ≤ TIME_FULL_UNIVERSE_LOAD < TIME_SETTLEMENT\n"
        f"  실제:\n"
        f"    TIME_RECOMMENDATION    = {scheduler.TIME_RECOMMENDATION}\n"
        f"    TIME_FULL_UNIVERSE_LOAD = {scheduler.TIME_FULL_UNIVERSE_LOAD}\n"
        f"    TIME_SETTLEMENT        = {scheduler.TIME_SETTLEMENT}\n"
        f"  domain-expert A2 영속: 자문 → 적재 → 정산 순서 race 0"
    )
