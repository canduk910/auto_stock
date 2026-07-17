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
