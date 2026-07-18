"""터틀 유닛 sizing 순수 함수 (`src/engine/turtle_sizing.py`) 골든 테스트.

성격: 순수 함수 (DB/HTTP/시계 미접촉) → mock/freeze 불필요.
레퍼런스 money.py::unit_size 이식 검증 + 불변식(유닛당 리스크 ≈ 예산×risk_pct).
"""

from __future__ import annotations

import math

import pytest

from src.engine.turtle_sizing import compute_unit_qty, compute_unit_qty_guarded


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


# ── compute_unit_qty_guarded (Phase 2A-2 게이트 0 갭/변동성 가드) ──

def test_guarded_matches_unguarded_when_no_clamp():
    # 정상 변동성 + 충분한 잔여 + notional 여유 → compute_unit_qty 와 동일
    budget, atr, price, rp = 100_000_000, 3000.0, 60_000, 0.005
    plain = compute_unit_qty(budget, atr, rp)  # 166
    guarded = compute_unit_qty_guarded(
        budget, atr, price, rp, remaining_budget=budget, min_vol_pct=1.0, position_ratio=0.20)
    # notional 상한 = budget×0.20//price = 20,000,000//60,000 = 333 > 166 → 클램프 없음
    assert guarded == plain == 166


def test_guarded_vol_floor_returns_zero():
    # atr/price = 0.5% < min_vol_pct 1% → 0 (position_ratio fallback 유도)
    q = compute_unit_qty_guarded(
        100_000_000, 500.0, 100_000, 0.005,
        remaining_budget=100_000_000, min_vol_pct=1.0, position_ratio=0.20)
    assert q == 0


def test_guarded_vol_floor_off_when_min_vol_zero():
    # min_vol_pct=0 → floor 미적용 (저변동도 통과)
    q = compute_unit_qty_guarded(
        100_000_000, 500.0, 100_000, 0.005,
        remaining_budget=100_000_000, min_vol_pct=0.0, position_ratio=0.0)
    assert q == compute_unit_qty(100_000_000, 500.0, 0.005)  # 1000


def test_guarded_remaining_budget_clamp():
    # 잔여 예산이 5주치뿐 → 5주로 클램프
    q = compute_unit_qty_guarded(
        100_000_000, 3000.0, 60_000, 0.005,
        remaining_budget=300_000, min_vol_pct=1.0, position_ratio=0.0)
    assert q == 300_000 // 60_000  # 5


def test_guarded_notional_cap_by_position_ratio():
    # 저ATR 대량 유닛 → notional 상한(position_ratio) 클램프로 단일종목 집중 차단
    budget, atr, price, rp = 100_000_000, 1200.0, 10_000, 0.005
    unit = compute_unit_qty(budget, atr, rp)  # 500000/1200=416
    pr_qty = int(budget * 0.20) // price       # 20,000,000//10,000 = 2000
    # 416 < 2000 이라 이 케이스는 클램프 안 됨 → 더 극단(atr 매우 작음)으로
    atr2 = 150.0                                # atr/price=1.5%>1% 통과
    unit2 = compute_unit_qty(budget, atr2, rp)  # 500000/150=3333
    q = compute_unit_qty_guarded(
        budget, atr2, price, rp, remaining_budget=budget, min_vol_pct=1.0, position_ratio=0.20)
    assert unit2 == 3333
    assert q == pr_qty == 2000  # notional 상한으로 클램프


@pytest.mark.parametrize("bad", [
    dict(atr_value=0.0), dict(atr_value=-1.0), dict(current_price=0),
    dict(strategy_budget=0), dict(risk_pct=0.0),
])
def test_guarded_non_positive_inputs_return_zero(bad):
    base = dict(strategy_budget=100_000_000, atr_value=3000.0, current_price=60_000, risk_pct=0.005)
    base.update(bad)
    assert compute_unit_qty_guarded(
        base["strategy_budget"], base["atr_value"], base["current_price"], base["risk_pct"],
        remaining_budget=100_000_000) == 0
