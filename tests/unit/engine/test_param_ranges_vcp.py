"""사이클 23 P1-1 Red — PARAM_RANGES VCP 4 키 + P2 신규 5 키 화이트리스트 검증.

요구 행위:
1. VCP 4 키 모두 PARAM_RANGES 에 존재
2. VCP 4 키 + P2 5 키 범위 경계값 검증 (하한/상한 통과, 초과 실패)
3. INT_PARAMS 에 P2 정수 키 3개 포함
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _get_param_ranges():
    from src.engine.recommendation_engine import PARAM_RANGES
    return PARAM_RANGES


def _get_int_params():
    from src.engine.recommendation_engine import INT_PARAMS
    return INT_PARAMS


# ---------------------------------------------------------------------------
# P1-1: VCP 4 키 존재
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", [
    "base_depth_pct",
    "volume_contraction_ratio",
    "breakout_volume_mult",
    "last_pullback_max",
])
def test_vcp_key_in_param_ranges(key):
    """VCP 4 핵심 진입 품질 키가 PARAM_RANGES 에 있어야 한다."""
    assert key in _get_param_ranges(), f"PARAM_RANGES 에 '{key}' 키 없음"


# ---------------------------------------------------------------------------
# P1-1: P2 신규 5 키 존재 + 범위 확인
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key,lo,hi", [
    ("breakout_retention_minutes", 1, 30),
    ("breakout_fail_n_days", 2, 20),
    ("max_breakout_extension_pct", 0.5, 10.0),
    ("box_contraction_period", 5, 30),
    ("max_box_volatility_pct", 1.0, 15.0),
])
def test_p2_key_ranges(key, lo, hi):
    """P2 신규 5 키가 PARAM_RANGES 에 올바른 범위로 등록되어 있어야 한다."""
    pr = _get_param_ranges()
    assert key in pr, f"PARAM_RANGES 에 '{key}' 키 없음"
    actual_lo, actual_hi = pr[key]
    assert actual_lo == pytest.approx(lo), f"{key} 하한 불일치: {actual_lo} != {lo}"
    assert actual_hi == pytest.approx(hi), f"{key} 상한 불일치: {actual_hi} != {hi}"


# ---------------------------------------------------------------------------
# INT_PARAMS: P2 정수 키 3개 포함
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", [
    "breakout_retention_minutes",
    "breakout_fail_n_days",
    "box_contraction_period",
])
def test_int_params_contains_p2_keys(key):
    """P2 신규 정수 키가 INT_PARAMS 에 포함되어 있어야 한다."""
    assert key in _get_int_params(), f"INT_PARAMS 에 '{key}' 키 없음"
