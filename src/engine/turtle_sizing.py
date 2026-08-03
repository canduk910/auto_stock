"""터틀식 유닛 자금관리 순수 함수 (Phase 2A — 유닛 sizing).

레퍼런스 `_workspace/kojiro_ma/kojiro/money.py` 이식. DB/HTTP/시계 절대 미접촉
순수 함수 모듈 (`quant_score.py`/`kojiro_indicators.py` 선례). 8영역
(risk/order_engine/realtime/auth/api.order/session/scanner매수경로/strategy_registry)
미접촉 — `calc_buy_quantity`(전략 파일)에서만 호출.

핵심: `unit = floor(strategy_budget × risk_pct / ATR × fraction)`.
ATR 이 큰(변동성 높은) 종목일수록 수량이 줄어 유닛당 리스크가 균등화된다.
total_capital = **전략 할당 예산**(`state.total_investment`) — 계좌 전체 아님
(per-strategy-budget 모델, weight 의미 보존 + allocate_funds 무변경).
"""

from __future__ import annotations

import math


def compute_unit_qty(
    strategy_budget: int,
    atr_value: float,
    risk_pct: float,
    *,
    fraction: float = 1.0,
) -> int:
    """1유닛 수량 = floor(전략예산 × risk_pct / ATR × fraction).

    - `atr_value <= 0` / `risk_pct <= 0` / `strategy_budget <= 0` → 0 (호출자가
      position_ratio 로 fail-open). fraction=0.5 → 조기진입용 절반 유닛.
    - 반환은 음수 방지(`max(0, ...)`). 현금/예산 잔여 클램프는 호출자 책임.
    """
    if atr_value <= 0 or risk_pct <= 0 or strategy_budget <= 0:
        return 0
    risk_budget = strategy_budget * risk_pct
    qty = math.floor(risk_budget / atr_value * fraction)
    return max(qty, 0)


def compute_unit_qty_guarded(
    strategy_budget: int,
    atr_value: float,
    current_price: int,
    risk_pct: float,
    *,
    remaining_budget: int,
    min_vol_pct: float = 1.0,
    position_ratio: float = 0.0,
    fraction: float = 1.0,
) -> int:
    """터틀 유닛 수량 + 갭/변동성 가드 (Phase 2A-2 게이트 0).

    `compute_unit_qty` 는 무상한이라 저ATR 종목에서 수량이 폭증(KR ±30% 갭이 손절선을
    한 봉에 관통 → 실현손실 ≫ 명목)한다. 본 함수는 3중 가드로 이를 차단하며,
    `qty == 0` 이면 호출자가 position_ratio 로 fail-open 한다.

    - **변동성 floor**: `atr/price < min_vol_pct%` → 0 (저변동/유동성 부족 = 터틀 부적합).
    - **잔여 자금 클램프**: `remaining_budget // price` 상한 (전략 잔여 예산 초과 매수 차단).
    - **notional 상한**: `position_ratio` notional (`budget × position_ratio // price`)
      상한 — 저ATR 종목이 유닛 수량 폭증으로 단일종목에 집중되는 것을 차단
      (`position_ratio <= 0` 이면 미적용).

    두 클램프는 **무조건 적용**한다. 구 구현은 `remaining_budget > 0` / `pr_qty > 0`
    조건부라, 정작 상한이 필요한 경계(예산 완전 소진 / 고가주라 notional 상한이
    1주에도 못 미침)에서 클램프가 해제되는 fail-open 반전이었다. 상한이 0 이면
    0 을 반환하고, 호출자가 position_ratio → 1주 폴백으로 낙하한다.
    """
    if (
        atr_value <= 0 or current_price <= 0
        or strategy_budget <= 0 or risk_pct <= 0
    ):
        return 0
    if min_vol_pct > 0 and atr_value / current_price < min_vol_pct / 100.0:
        return 0  # 저변동 → position_ratio fallback
    qty = compute_unit_qty(strategy_budget, atr_value, risk_pct, fraction=fraction)
    if qty <= 0:
        return 0
    qty = min(qty, max(0, remaining_budget) // current_price)
    if position_ratio > 0:
        qty = min(qty, int(strategy_budget * position_ratio) // current_price)
    return max(qty, 0)
