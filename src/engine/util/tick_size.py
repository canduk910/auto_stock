"""KRX 표준 호가단위 헬퍼.

2023-01-25 호가단위 개편 이후 KOSPI/KOSDAQ 공통 7구간 (KOSPI 기준):

| 가격 구간             | 호가단위 |
|----------------------|---------|
| 0 ~ 1,999            | 1       |
| 2,000 ~ 4,999        | 5       |
| 5,000 ~ 19,999       | 10      |
| 20,000 ~ 49,999      | 50      |
| 50,000 ~ 199,999     | 100     |
| 200,000 ~ 499,999    | 500     |
| 500,000 이상         | 1,000   |

용도:
- 익일 청산 지정가 매도 시 직전가에서 N호가 하향한 가격 산출 (`step_down`)
- 매수/매도 모두 KIS 가 호가단위 검증을 강하므로 입력 가격을 항상 단위 정렬 (`round_to_tick`)

NXT 도 KRX 와 동일 호가단위를 사용한다고 가정 (별도 NXT 단위 명세 미공개).
"""

from __future__ import annotations

# 구간 상한(미만) → 호가단위
_TICK_BANDS: tuple[tuple[int, int], ...] = (
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
)
# 500_000 이상 1000원
_TOP_TICK = 1_000


def get_tick_size(price: int) -> int:
    """가격에 해당하는 호가단위를 반환.

    0 이하는 0 반환 (안전 가드).
    """
    if price <= 0:
        return 0
    for upper, unit in _TICK_BANDS:
        if price < upper:
            return unit
    return _TOP_TICK


def round_to_tick(price: int) -> int:
    """가격을 가까운 호가단위로 내림(floor) 한다.

    예: 15007 → 15000 (10원 단위), 49980 → 49950 (50원 단위)
    """
    unit = get_tick_size(price)
    if unit == 0:
        return 0
    return (price // unit) * unit


def step_down(price: int, steps: int = 1) -> int:
    """직전가에서 N호가 하향 가격을 반환.

    시작 가격의 호가단위 기준으로 step 한다. 결과가 더 낮은 가격 구간에 진입해도
    해당 가격 그대로 반환(0 이하 floor).
    """
    if price <= 0 or steps <= 0:
        return 0
    unit = get_tick_size(price)
    base = round_to_tick(price)
    result = base - unit * steps
    return max(result, 0)


def step_up(price: int, steps: int = 1) -> int:
    """직전가에서 N호가 상향 가격을 반환.

    각 step 마다 현재 위치의 호가단위로 올라간다 — step_down 의 대칭 함수.

    구간 전환 시 특례: 상위 구간 단위가 현재 단위의 5배 이상이고,
    상위 단위 1 step 으로 정확히 구간 경계에 닿는 경우 경계로 snap 한다.
    (KRX 7구간 테이블에서 비율 5 구간: [5000,20000)→[20000,50000) / [50000,200000)→[200000,500000))
    이 특례로 step_down → step_up 왕복 대칭이 보장된다.

    0 이하 가격 또는 steps <= 0 이면 0 반환 (안전 가드).
    시장가 거부 시 매수 지정가 폴백(N호가 위)에 사용된다.
    """
    if price <= 0 or steps <= 0:
        return 0
    current = round_to_tick(price)
    for _ in range(steps):
        current_unit = get_tick_size(current)
        # 상위 구간 경계와 단위 조회
        upper_boundary: int | None = None
        upper_unit: int | None = None
        for upper, _ in _TICK_BANDS:
            if current < upper:
                upper_boundary = upper
                upper_unit = get_tick_size(upper)
                break
        # 상위 단위 / 현재 단위 비율이 5 이상이고 상위 단위로 정확히 경계에 닿는 경우 snap
        if (
            upper_boundary is not None
            and upper_unit is not None
            and current + upper_unit == upper_boundary
            and upper_unit // current_unit >= 5
        ):
            current = upper_boundary
        else:
            current = current + current_unit
    return current
