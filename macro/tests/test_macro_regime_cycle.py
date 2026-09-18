"""macro_lite.regime.get_regime_params(regime, cycle_phase) 16셀 매트릭스 단위 테스트.

원본: tests/unit/test_macro_regime_cycle.py — `from services import macro_regime`
를 `from macro_lite import regime as macro_regime`로 교체 (요건서 REQ-PKG-01).
본문은 원본 그대로 유지.
"""
from __future__ import annotations

import pytest

from macro_lite import regime as macro_regime


# ── 16셀 single_cap 매트릭스 ───────────────────────────────────────────


@pytest.mark.parametrize("regime,cycle,expected_cap", [
    # accumulation
    ("accumulation", "recovery", 7),
    ("accumulation", "expansion", 6),
    ("accumulation", "overheating", 5),
    ("accumulation", "contraction", 5),
    # selective
    ("selective", "recovery", 5),
    ("selective", "expansion", 4),
    ("selective", "overheating", 3),
    ("selective", "contraction", 4),
    # cautious
    ("cautious", "recovery", 4),
    ("cautious", "expansion", 3),
    ("cautious", "overheating", 2),
    ("cautious", "contraction", 3),
    # defensive (핵심: 회복/확장에서 0이 아님)
    ("defensive", "recovery", 7),
    ("defensive", "expansion", 5),
    ("defensive", "overheating", 2),
    ("defensive", "contraction", 0),
])
def test_get_regime_params_single_cap_16cells(regime, cycle, expected_cap):
    params = macro_regime.get_regime_params(regime, cycle)
    assert params["single_cap"] == expected_cap, (
        f"{regime}+{cycle}: expected single_cap={expected_cap}, got {params['single_cap']}"
    )
    # cycle_phase 키 부착 확인
    assert params["cycle_phase"] == cycle


def test_get_regime_params_no_cycle_falls_back_to_base():
    """cycle_phase=None이면 기존 REGIME_PARAMS 그대로 반환."""
    base = macro_regime.REGIME_PARAMS["defensive"]
    p = macro_regime.get_regime_params("defensive", None)
    assert p["single_cap"] == base["single_cap"]
    assert "cycle_phase" not in p


def test_get_regime_params_returns_copy_not_reference():
    """반환값을 수정해도 원본 REGIME_PARAMS에 영향 없음."""
    p = macro_regime.get_regime_params("defensive", "recovery")
    original_cap = macro_regime.REGIME_PARAMS["defensive"]["single_cap"]
    p["single_cap"] = 999
    assert macro_regime.REGIME_PARAMS["defensive"]["single_cap"] == original_cap


# ── 16셀 margin 매트릭스 ───────────────────────────────────────────────


@pytest.mark.parametrize("regime,cycle,expected_margin", [
    # MarginAnalyst 자문 핵심 셀: 강세장에서 정량 벽 완화
    ("accumulation", "recovery", 18),
    ("accumulation", "expansion", 20),
    ("selective", "recovery", 25),
    ("cautious", "recovery", 30),
    ("cautious", "overheating", 40),
    ("defensive", "contraction", 999),  # 사실상 진입 차단 유지
    ("defensive", "recovery", 35),
])
def test_get_margin_requirement_cycle_corrections(regime, cycle, expected_margin):
    margin = macro_regime.get_margin_requirement(regime, cycle)
    assert margin == expected_margin


def test_get_margin_requirement_no_cycle_uses_base():
    """cycle_phase=None이면 REGIME_PARAMS[regime]['margin'] 사용."""
    margin = macro_regime.get_margin_requirement("cautious", None)
    assert margin == macro_regime.REGIME_PARAMS["cautious"]["margin"]


# ── 백워드 호환성 ──────────────────────────────────────────────────────


def test_existing_determine_regime_unchanged():
    """determine_regime() 시그니처는 변경 없음 — 기존 호출 영향 없어야 함."""
    sentiment = {
        "fear_greed": {"score": 50},
        "vix": {"value": 18},
        "buffett_indicator": {"ratio": 1.0},
    }
    result = macro_regime.determine_regime(sentiment)
    assert "regime" in result
    assert "regime_desc" in result
    assert "params" in result
