"""P1(B) Red — KRX 표준 호가단위 헬퍼.

NXT 익일 청산 시 지정가(직전가 -1호가) 매도가 필요하므로 호가단위 변환 헬퍼를 추가한다.

KRX 호가단위(2023-01-25 개편 후):
- 0 ~ 1,999원      → 1원
- 2,000 ~ 4,999    → 5원
- 5,000 ~ 19,999   → 10원
- 20,000 ~ 49,999  → 50원
- 50,000 ~ 199,999 → 100원
- 200,000 ~ 499,999 → 500원
- 500,000원 이상    → 1,000원

(KOSPI 표준 — 2026-05 기준. KOSDAQ 도 동일 적용. NXT 도 동일 단위 사용 가정.)

요구 행위:
1. `get_tick_size(price)` 가 각 구간의 단위를 정확히 반환한다.
2. `round_to_tick(price)` 가 가까운 호가단위로 내림(floor) 한다.
3. `step_down(price, steps=1)` 가 직전가에서 N호가 하향 가격을 반환한다 (지정가 매도용).
4. 0 이하 가격은 0 반환 (안전 가드).
"""

from __future__ import annotations

import pytest

from src.engine.util.tick_size import get_tick_size, round_to_tick, step_down

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "price,expected",
    [
        (1, 1), (1999, 1),
        (2000, 5), (4999, 5),
        (5000, 10), (19999, 10),
        (20000, 50), (49999, 50),
        (50000, 100), (199999, 100),
        (200000, 500), (499999, 500),
        (500000, 1000), (1234567, 1000),
    ],
)
def test_get_tick_size_returns_band_unit(price, expected):
    assert get_tick_size(price) == expected


def test_get_tick_size_when_zero_or_negative_then_zero():
    assert get_tick_size(0) == 0
    assert get_tick_size(-100) == 0


@pytest.mark.parametrize(
    "price,expected",
    [
        (15003, 15000),   # 10원 단위 → 15000
        (15007, 15000),
        (15010, 15010),
        (49980, 49950),   # 50원 단위 → 49950
        (50050, 50000),   # 100원 단위 → 50000
        (200300, 200000), # 500원 단위 → 200000
        (500999, 500000), # 1000원 단위 → 500000
    ],
)
def test_round_to_tick_floors_to_band_unit(price, expected):
    assert round_to_tick(price) == expected


@pytest.mark.parametrize(
    "price,steps,expected",
    [
        # 015003원에서 1호가 하향 = 14990 (10원 단위)
        (15003, 1, 14990),
        # 50000원에서 1호가 하향 = 49950 (50000은 100원 단위지만 49950은 50원 단위)
        #   ※ 정책: 시작 가격 기준 단위로 step, 결과가 더 낮은 구간 진입해도 그대로 사용
        (50000, 1, 49900),
        # 20000원에서 1호가 하향 = 19950 (시작 50원 단위)
        (20000, 1, 19950),
        # 5000원에서 1호가 하향 = 4990 (시작 10원 단위)
        (5000, 1, 4990),
        # 직전가 1999원에서 1호가 하향 = 1998 (1원 단위)
        (1999, 1, 1998),
        # 2호가 하향
        (15000, 2, 14980),
    ],
)
def test_step_down_n_ticks(price, steps, expected):
    assert step_down(price, steps=steps) == expected


def test_step_down_when_zero_then_zero():
    assert step_down(0, steps=1) == 0
