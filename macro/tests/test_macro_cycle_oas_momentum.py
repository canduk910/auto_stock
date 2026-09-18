"""macro_lite/cycle.py — oas_momentum_6m 입력 추가 (Phase 3).

원본: tests/unit/test_macro_cycle_oas_momentum.py — import 경로만
macro_lite.cycle로 교체 (요건서 REQ-PKG-01). 본문은 원본 그대로 유지.

R4 (P3): HY OAS 6개월 변화율을 cycle 판정 보조 입력으로 추가.
16셀 매트릭스 미터치 (입력만 정밀화).
"""

from __future__ import annotations

from macro_lite.cycle import determine_cycle_phase, _score_credit


def _baseline_inputs():
    """중립 baseline — yield/credit/vix/sector/dollar 모두 stable."""
    return {
        "yield_spread": 1.0,
        "yield_direction": "stable",
        "credit_direction": "stable",
        "vix_value": 20.0,
        "vix_level": "normal",
        "sector_rotation": "mixed",
        "dollar_strength": "stable",
    }


# ── _score_credit: oas_momentum 가중 ──────────────────────────

def test_score_credit_widening_momentum_contraction_boost():
    """momentum > +50% → contraction 점수 가중 (+0.3)."""
    base = _score_credit("stable")
    boosted = _score_credit("stable", oas_momentum_6m=60.0)
    assert boosted["contraction"] > base["contraction"]
    # 가중치 0.3 부여 검증
    assert boosted["contraction"] >= base["contraction"] + 0.29


def test_score_credit_narrowing_momentum_recovery_boost():
    """momentum < -30% → recovery 점수 가중 (+0.3)."""
    base = _score_credit("stable")
    boosted = _score_credit("stable", oas_momentum_6m=-40.0)
    assert boosted["recovery"] > base["recovery"]
    assert boosted["recovery"] >= base["recovery"] + 0.29


def test_score_credit_no_momentum_backward_compat():
    """momentum=None → 기존 score 결과와 동일 (회귀)."""
    base = _score_credit("widening")
    nomom = _score_credit("widening", oas_momentum_6m=None)
    assert base == nomom


def test_score_credit_neutral_momentum_no_change():
    """momentum=0% → 가중 없음."""
    base = _score_credit("stable")
    zero = _score_credit("stable", oas_momentum_6m=0.0)
    assert base == zero


# ── determine_cycle_phase: oas_momentum 통합 ──────────────────

def test_determine_cycle_widening_with_high_momentum_increases_contraction_score():
    """credit widening + momentum=+70% → contraction 점수가 momentum 없을 때보다 높음."""
    inputs = _baseline_inputs()
    inputs["credit_direction"] = "widening"
    no_mom = determine_cycle_phase(inputs)
    inputs["oas_momentum_6m"] = 70.0
    with_mom = determine_cycle_phase(inputs)
    # contraction 신호가 momentum 가중으로 더 강해져야 함
    no_mom_credit = no_mom["scores"]["credit_spread"]["score"]
    with_mom_credit = with_mom["scores"]["credit_spread"]["score"]
    # widening 시 top_phase일 가능성이 큰 contraction의 credit 점수가 momentum 가중으로 증가
    # (단, top_phase가 변경되지 않을 수도 있으므로 점수만 비교)
    assert with_mom_credit >= no_mom_credit


def test_determine_cycle_no_momentum_backward_compat():
    """oas_momentum_6m 미제공 시 기존 동작 (회귀)."""
    inputs = _baseline_inputs()
    inputs["credit_direction"] = "widening"
    a = determine_cycle_phase(inputs)
    b = determine_cycle_phase(inputs)
    assert a["phase"] == b["phase"]
