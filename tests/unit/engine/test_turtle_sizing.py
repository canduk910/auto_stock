"""터틀 유닛 sizing 순수 함수 (`src/engine/turtle_sizing.py`) 골든 테스트.

성격: 순수 함수 (DB/HTTP/시계 미접촉) → mock/freeze 불필요.
레퍼런스 money.py::unit_size 이식 검증 + 불변식(유닛당 리스크 ≈ 예산×risk_pct).
"""

from __future__ import annotations

import math

import pytest

from src.engine.turtle_sizing import compute_unit_qty


def test_basic_floor_formula():
    # 예산 100,000,000 × 0.5% = 500,000 리스크. ATR 3,000 → floor(500000/3000)=166
    assert compute_unit_qty(100_000_000, 3000.0, 0.005) == 166


def test_atr_inverse_scaling():
    # ATR 이 클수록 수량↓ (리스크 균등화)
    q_low_vol = compute_unit_qty(100_000_000, 1000.0, 0.005)   # 500
    q_high_vol = compute_unit_qty(100_000_000, 5000.0, 0.005)  # 100
    assert q_low_vol == 500
    assert q_high_vol == 100
    assert q_low_vol > q_high_vol


def test_fraction_half_unit():
    full = compute_unit_qty(100_000_000, 2000.0, 0.005)          # 250
    half = compute_unit_qty(100_000_000, 2000.0, 0.005, fraction=0.5)  # 125
    assert full == 250
    assert half == 125


@pytest.mark.parametrize("atr", [0.0, -1.0, -100.0])
def test_atr_non_positive_returns_zero(atr):
    assert compute_unit_qty(100_000_000, atr, 0.005) == 0


@pytest.mark.parametrize("risk_pct", [0.0, -0.01])
def test_risk_pct_non_positive_returns_zero(risk_pct):
    assert compute_unit_qty(100_000_000, 3000.0, risk_pct) == 0


@pytest.mark.parametrize("budget", [0, -1])
def test_budget_non_positive_returns_zero(budget):
    assert compute_unit_qty(budget, 3000.0, 0.005) == 0


def test_never_negative():
    assert compute_unit_qty(1000, 999999.0, 0.005) == 0  # floor < 1 → 0, 음수 아님


def test_invariant_qty_times_atr_approx_risk_budget():
    # 불변식: qty × ATR ≈ 예산 × risk_pct (floor 절삭 오차 < ATR 1개)
    budget, atr, rp = 100_000_000, 3333.0, 0.005
    qty = compute_unit_qty(budget, atr, rp)
    risk_budget = budget * rp
    assert abs(qty * atr - risk_budget) < atr
    assert qty == math.floor(risk_budget / atr)


def test_risk_normalization_property_vs_position_ratio():
    """핵심 검증: ATR 밴드 유니버스에서 터틀 유닛당 리스크 CV << position_ratio CV.

    유닛당 리스크 = 수량 × 2ATR(손절폭). 터틀은 변동성 무관 상수(예산×2×risk_pct),
    position_ratio 는 변동성(ATR/종가)에 비례해 흩어진다. (tools/validate_turtle_sizing 실증 고정)
    """
    import statistics
    budget, risk_pct, stop_atr, pos_ratio = 100_000_000, 0.005, 2.0, 0.20
    pr_amount = int(budget * pos_ratio)
    t_risks, p_risks = [], []
    for price in (10_000, 30_000, 50_000, 100_000, 300_000):
        for atr_ratio in (0.01, 0.02, 0.03, 0.045):  # kojiro 밴드
            atr = price * atr_ratio
            t_qty = compute_unit_qty(budget, atr, risk_pct)
            p_qty = pr_amount // price
            if t_qty > 0 and p_qty > 0:
                t_risks.append(t_qty * stop_atr * atr)
                p_risks.append(p_qty * stop_atr * atr)

    t_cv = statistics.pstdev(t_risks) / statistics.fmean(t_risks)
    p_cv = statistics.pstdev(p_risks) / statistics.fmean(p_risks)
    assert t_cv < 0.05, f"터틀 유닛당 리스크 정규화 실패 CV={t_cv}"   # 상수 (floor 오차만)
    assert p_cv > 0.20, f"position_ratio 는 변동성 비례 흩어져야 CV={p_cv}"
    assert t_cv < p_cv  # 터틀이 더 균등
