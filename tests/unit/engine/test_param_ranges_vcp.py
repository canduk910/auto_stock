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
# P1-1: P2 신규 키 존재 + 범위 확인
# 사이클 208 의미 전환 — box_contraction_period / max_box_volatility_pct 제거
# (donchian 박스 수축 필터 폐기 = 전략 정체성 상수 → AI 자동튜닝 화이트리스트 제외).
# 사이클 209 의미 전환 — max_breakout_extension_pct 제거 (extension 가드 = 진입 정체성
# 상수 → AI 자동튜닝이 0.5 로 과튜닝해 donchian 매수 상시 차단, 사이클 208/198 선례 계승).
# 사이클 223 의미 전환 — breakout_fail_n_days 제거 (**청산 정체성 상수**). 라이브 값 2 가
# 구 범위 (2, 20) 의 하한에 정확히 고착 = 209 와 동형 서명이었고, 그 값이 달력일 계산과
# 결합해 금요일 매수를 월요일에 청산시켰다. 아래 `test_box_keys_removed_from_param_ranges`
# 목록으로 이동한다. 근거: `_workspace/domain_consult/donchian_exit_retune.md` C9.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key,lo,hi", [
    ("breakout_retention_minutes", 1, 30),
])
def test_p2_key_ranges(key, lo, hi):
    """P2 신규 키가 PARAM_RANGES 에 올바른 범위로 등록되어 있어야 한다."""
    pr = _get_param_ranges()
    assert key in pr, f"PARAM_RANGES 에 '{key}' 키 없음"
    actual_lo, actual_hi = pr[key]
    assert actual_lo == pytest.approx(lo), f"{key} 하한 불일치: {actual_lo} != {lo}"
    assert actual_hi == pytest.approx(hi), f"{key} 상한 불일치: {actual_hi} != {hi}"


# ---------------------------------------------------------------------------
# 사이클 208 — box 2 키 PARAM_RANGES / INT_PARAMS 부재 (제거 확정)
# 사이클 209 — max_breakout_extension_pct PARAM_RANGES 부재 (제거 확정)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", [
    "box_contraction_period",
    "max_box_volatility_pct",
    "max_breakout_extension_pct",
    # 사이클 223 — donchian 청산 2키 (보유기간 정체성 상수)
    "breakout_fail_n_days",
    "atr_trail_mult",
])
def test_box_keys_removed_from_param_ranges(key):
    """사이클 208/209/223 — 제거된 키가 PARAM_RANGES 에서 부재해야 한다."""
    assert key not in _get_param_ranges(), (
        f"PARAM_RANGES 에 '{key}' 잔존 금지 (사이클 208/209/223 제거)"
    )


# ---------------------------------------------------------------------------
# INT_PARAMS: P2 정수 키 포함 (box_contraction_period 는 사이클 208 제거)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", [
    "breakout_retention_minutes",
])
def test_int_params_contains_p2_keys(key):
    """P2 신규 정수 키가 INT_PARAMS 에 포함되어 있어야 한다.

    사이클 223 의미 전환: `breakout_fail_n_days` 는 PARAM_RANGES 와 함께 INT_PARAMS
    에서도 제거됐다 (INT_PARAMS ⊆ PARAM_RANGES 규약 유지). 부재 단언은 아래로 이동.
    """
    assert key in _get_int_params(), f"INT_PARAMS 에 '{key}' 키 없음"


def test_breakout_fail_n_days_removed_from_int_params():
    """사이클 223 — breakout_fail_n_days 가 INT_PARAMS 에서 제거되어야 한다."""
    assert "breakout_fail_n_days" not in _get_int_params(), (
        "INT_PARAMS 에 breakout_fail_n_days 잔존 금지 (사이클 223 제거)"
    )


def test_box_contraction_period_removed_from_int_params():
    """사이클 208 — box_contraction_period 가 INT_PARAMS 에서 제거되어야 한다."""
    assert "box_contraction_period" not in _get_int_params(), (
        "INT_PARAMS 에 box_contraction_period 잔존 금지 (사이클 208 제거)"
    )
