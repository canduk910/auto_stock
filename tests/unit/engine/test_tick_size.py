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

from src.engine.util.tick_size import (
    get_tick_size,
    round_to_tick,
    step_down,
    step_up,
)

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


# ---------------------------------------------------------------------------
# P2 Red — `step_up` (시장가 거부 시 매수 지정가 폴백 5호가 위)
# ---------------------------------------------------------------------------
# 정책(step_down 대칭): 시작 가격의 호가단위로 step, 결과가 더 높은 구간에 진입해도
# 그대로 사용한다 (구간 경계 통과 시 새 호가단위 강제 적용은 별도 검증 케이스).


@pytest.mark.parametrize(
    "price,steps,expected",
    [
        # 1원 단위 구간
        (1000, 1, 1001),
        (1998, 1, 1999),
        # 5원 단위 구간 (2000~4999)
        (2000, 1, 2005),
        (2000, 5, 2025),
        (4990, 1, 4995),
        # 10원 단위 구간 (5000~19999)
        (5000, 1, 5010),
        (15003, 1, 15010),   # 15003 → round 15000 → +10
        (15003, 5, 15050),   # 5호가 = +50
        # 50원 단위 구간 (20000~49999)
        (20000, 1, 20050),
        (20000, 5, 20250),
        (49950, 1, 50000),   # 50원 step 으로 50000 도달 (다음 구간 진입)
        # 100원 단위 구간 (50000~199999)
        (50000, 1, 50100),
        (50000, 5, 50500),   # 5호가 위 — 매수 지정가 폴백 기본 케이스
        # 500원 단위 구간 (200000~499999)
        (200000, 1, 200500),
        (200000, 5, 202500),
        # 1000원 단위 구간 (500000+)
        (500000, 1, 501000),
        (500000, 5, 505000),
    ],
)
def test_step_up_n_ticks(price, steps, expected):
    """가격 구간의 호가단위로 위쪽 N호가."""
    assert step_up(price, steps=steps) == expected


def test_step_up_when_zero_then_zero():
    """0 원은 step_up 도 0 — 안전 가드."""
    assert step_up(0, steps=1) == 0


def test_step_up_when_negative_then_zero():
    """음수 가격도 안전 가드."""
    assert step_up(-100, steps=1) == 0


def test_step_up_when_zero_steps_then_returns_price_or_zero():
    """steps=0 또는 음수면 step_down 과 동일하게 0 반환 (가드)."""
    # step_down 은 steps<=0 일 때 0 을 반환 — step_up 도 대칭으로 동일 정책
    assert step_up(15000, steps=0) == 0
    assert step_up(15000, steps=-1) == 0


def test_step_up_is_symmetric_with_step_down():
    """동일 가격에서 step_down → step_up 왕복이면 시작 가격(또는 round_to_tick)과 일치."""
    # 50000 (100원 단위) → step_down 1 = 49950 (50원 단위) → step_up 1 = 50000
    # 시작 가격의 단위로 내려갔다 올라오면 구간 경계 효과로 일부는 시작값과 다를 수 있어
    # round_to_tick(시작값) 기준으로만 일치를 확인
    for price in (15000, 20000, 50100, 200500):
        down = step_down(price, steps=1)
        up_back = step_up(down, steps=1)
        assert up_back == round_to_tick(price), (
            f"price={price} → step_down={down} → step_up={up_back} != round_to_tick={round_to_tick(price)}"
        )
