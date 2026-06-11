"""사이클 101 G-RATE1 — 환경 분리 Rate Limit (HIGH).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**domain-expert A3 영속**:
- 실전 (`KIS_ENV=real`): 50ms sleep + max_load_seconds=300 (5분)
- 모의 (`KIS_ENV=vts`): 200ms sleep + max_load_seconds=600 (10분, 정산 race 차단)

**근거 (Phase 1 B-3)**:
- 모의 환경 5건/초 = 2,800 / 5 = 560초 (9분 24초) → 20:09:24 종료 → 정산 (20:10) 직전 36초 마진
- 실전 환경 20건/초 = 2,800 / 20 = 140초 (2분 20초) → 안전 마진 7분 35초

검증 매트릭스:
- G-RATE1-A: `_FULL_UNIVERSE_SLEEP_REAL == 0.050` + `_FULL_UNIVERSE_SLEEP_VTS == 0.200` 상수 영속
- G-RATE1-B: `_FULL_UNIVERSE_MAX_LOAD_SECONDS_REAL == 300` + `_VTS == 600` 영속
- G-RATE1-C: 환경 분리 동작 — `KIS_ENV=real` 시 50ms sleep / `=vts` 시 200ms sleep

Red 상태: 신규 상수 부재 또는 환경 분기 미구현.
Green (backend-dev): 4 상수 정의 + 환경 분리 분기 영속.

영속 의무:
- 사이클 17/18/29/76 LMS chain 영속 매트릭스 (collector 흡수 영속)
- 사이클 88 G-REJECT graceful 영속
- 사이클 83 50ms sleep 영속 (실전)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def test_g_rate1_a_sleep_constants_exist() -> None:
    """G-RATE1-A: sleep 상수 영속 (HIGH).

    Red 상태: 상수 부재 → AttributeError.
    Green (backend-dev): scanner.py 모듈 전역 정의.
    """
    from src.engine import scanner

    assert hasattr(scanner, "_FULL_UNIVERSE_SLEEP_REAL"), (
        "\n사이클 101 G-RATE1-A Red — `_FULL_UNIVERSE_SLEEP_REAL` 부재.\n"
        "  Green: scanner.py 모듈 전역 0.050 (50ms 실전) 영속"
    )
    assert hasattr(scanner, "_FULL_UNIVERSE_SLEEP_VTS"), (
        "\n사이클 101 G-RATE1-A Red — `_FULL_UNIVERSE_SLEEP_VTS` 부재.\n"
        "  Green: scanner.py 모듈 전역 0.200 (200ms 모의) 영속"
    )

    assert scanner._FULL_UNIVERSE_SLEEP_REAL == 0.050, (
        f"\nG-RATE1-A 실전 sleep 잘못: 기대 0.050 / 실제 {scanner._FULL_UNIVERSE_SLEEP_REAL}"
    )
    assert scanner._FULL_UNIVERSE_SLEEP_VTS == 0.200, (
        f"\nG-RATE1-A 모의 sleep 잘못: 기대 0.200 / 실제 {scanner._FULL_UNIVERSE_SLEEP_VTS}"
    )


def test_g_rate1_b_max_load_seconds_constants_exist() -> None:
    """G-RATE1-B: max_load_seconds 상수 영속 (HIGH).

    Red 상태: 상수 부재 → 정산 race 차단 미구현.
    Green (backend-dev): 상수 + 타임아웃 가드 영속.
    """
    from src.engine import scanner

    assert hasattr(scanner, "_FULL_UNIVERSE_MAX_LOAD_SECONDS_REAL"), (
        "\nG-RATE1-B Red — `_FULL_UNIVERSE_MAX_LOAD_SECONDS_REAL` 부재.\n"
        "  Green: scanner.py 모듈 전역 300 (5분 실전) 영속"
    )
    assert hasattr(scanner, "_FULL_UNIVERSE_MAX_LOAD_SECONDS_VTS"), (
        "\nG-RATE1-B Red — `_FULL_UNIVERSE_MAX_LOAD_SECONDS_VTS` 부재.\n"
        "  Green: scanner.py 모듈 전역 600 (10분 모의, 정산 race 차단) 영속"
    )

    assert scanner._FULL_UNIVERSE_MAX_LOAD_SECONDS_REAL == 300, (
        f"\nG-RATE1-B 실전 max_load 잘못: 기대 300 / 실제 {scanner._FULL_UNIVERSE_MAX_LOAD_SECONDS_REAL}"
    )
    assert scanner._FULL_UNIVERSE_MAX_LOAD_SECONDS_VTS == 600, (
        f"\nG-RATE1-B 모의 max_load 잘못: 기대 600 / 실제 {scanner._FULL_UNIVERSE_MAX_LOAD_SECONDS_VTS}"
    )


def test_g_rate1_c_env_split_sleep_value_persisted() -> None:
    """G-RATE1-C: 환경 분리 sleep 값 영속 (HIGH).

    검증 매트릭스 (domain-expert A3 영속):
    - 실전: 50ms = Semaphore 20/s 일치 (1/20 = 0.050s)
    - 모의: 200ms = Semaphore 5/s 일치 (1/5 = 0.200s)

    Red 상태: 4 상수 부재.
    Green (backend-dev): 환경 분리 분기 영속 (scanner._full_universe_load_once 내부).
    """
    from src.engine import scanner

    # 단순 영속 가드: 4 상수가 매트릭스 정합 영속
    assert scanner._FULL_UNIVERSE_SLEEP_REAL * 20 == pytest.approx(1.0), (
        f"\nG-RATE1-C Red 실전 sleep × 20 ≠ 1.0:\n"
        f"  실제: {scanner._FULL_UNIVERSE_SLEEP_REAL} × 20 = {scanner._FULL_UNIVERSE_SLEEP_REAL * 20}\n"
        f"  기대: 50ms × 20 = 1.0s (Semaphore 20/s 영역 정합)\n"
        f"  domain-expert A3 영속 의무"
    )
    assert scanner._FULL_UNIVERSE_SLEEP_VTS * 5 == pytest.approx(1.0), (
        f"\nG-RATE1-C Red 모의 sleep × 5 ≠ 1.0:\n"
        f"  실제: {scanner._FULL_UNIVERSE_SLEEP_VTS} × 5 = {scanner._FULL_UNIVERSE_SLEEP_VTS * 5}\n"
        f"  기대: 200ms × 5 = 1.0s (Semaphore 5/s 영역 정합)\n"
        f"  domain-expert A3 영속 의무"
    )
