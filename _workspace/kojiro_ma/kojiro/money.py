"""자금관리 — 터틀식 유닛 계산과 포트폴리오 한도 (설계서 §5)."""
import math
from dataclasses import dataclass


@dataclass
class UnitPlan:
    qty: int          # 주문 수량
    risk_amount: int  # 이 유닛이 감수하는 리스크 금액(원)


def unit_size(total_capital: float, atr_value: float, cfg, fraction: float = 1.0) -> UnitPlan:
    """1유닛 수량 = floor(총자금×1% ÷ ATR) × fraction.

    ATR이 큰(변동성 높은) 종목일수록 수량이 줄어 리스크가 균등해진다.
    fraction=0.5 → 조기 진입용 절반 유닛.
    """
    if atr_value <= 0:
        return UnitPlan(0, 0)
    risk_budget = total_capital * cfg.risk_pct
    qty = math.floor(risk_budget / atr_value * fraction)
    return UnitPlan(qty=max(qty, 0), risk_amount=int(qty * atr_value))


def can_add_unit(units_in_stock: float, units_total: float, cfg,
                 add: float = 1.0) -> tuple[bool, str]:
    """유닛 한도 검사 — 종목당/계좌 전체."""
    if units_in_stock + add > cfg.max_units_per_stock:
        return False, f"종목 한도 초과 ({units_in_stock}+{add} > {cfg.max_units_per_stock})"
    if units_total + add > cfg.max_units_total:
        return False, f"계좌 한도 초과 ({units_total}+{add} > {cfg.max_units_total})"
    return True, ""


def affordable(qty: int, price: float, cash_available: float,
               fee_rate: float = 0.00015) -> int:
    """주문가능현금 내에서 실제 체결 가능한 수량으로 절삭."""
    cost_per_share = price * (1 + fee_rate)
    max_qty = int(cash_available // cost_per_share)
    return min(qty, max_qty)
