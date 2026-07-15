"""사이클 212 Red — 진입 임계 buy_threshold/donchian_period PARAM_RANGES 제외.

> 백로그 D — 208/209 논리: 진입 임계 = 전략 정체성 상수, AI 자동튜닝 부적합.
> 선례: 사이클 198(BFB flag_lookback) / 208(donchian box 2키) / 209(max_breakout_extension_pct).

G-212-1: recommendation_engine.PARAM_RANGES 에 buy_threshold 부재 (momentum 진입 임계).
G-212-2: recommendation_engine.PARAM_RANGES 에 donchian_period 부재 (donchian 진입 임계).
G-212-3: recommendation_engine.INT_PARAMS 에 donchian_period 부재 (정수 캐스트 대상 제거).
  buy_threshold 는 float — INT_PARAMS 에 애초 미등록 (본 사이클 무관).

Red 유효성 (production 미변경 = 키 잔존):
  - G-212-1 = FAIL (현재 PARAM_RANGES L68 `"buy_threshold": (0.0, 30.0)` 잔존)
  - G-212-2 = FAIL (현재 PARAM_RANGES L93 `"donchian_period": (10, 60)` 잔존)
  - G-212-3 = FAIL (현재 INT_PARAMS L114 `"donchian_period"` 잔존)
  - 불변식 (나머지 키 잔존 / 208·209 제외분 부재 / INT⊆PARAM 규약) = PASS
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# G-212-1/2/3 — 진입 임계 키 부재 (런타임 dict/set 기준)
# ===========================================================================
def test_g212_1_buy_threshold_absent_from_param_ranges():
    """PARAM_RANGES 에 buy_threshold 부재 (Red: 현재 L68 잔존 → FAIL)."""
    from src.engine.recommendation_engine import PARAM_RANGES
    assert "buy_threshold" not in PARAM_RANGES, (
        "PARAM_RANGES 에 'buy_threshold' 잔존 금지 (사이클 212 — momentum 진입 임계 "
        "= 전략 정체성 상수, AI 자동튜닝 제외)"
    )


def test_g212_2_donchian_period_absent_from_param_ranges():
    """PARAM_RANGES 에 donchian_period 부재 (Red: 현재 L93 잔존 → FAIL)."""
    from src.engine.recommendation_engine import PARAM_RANGES
    assert "donchian_period" not in PARAM_RANGES, (
        "PARAM_RANGES 에 'donchian_period' 잔존 금지 (사이클 212 — donchian 진입 임계 "
        "= 전략 정체성 상수, AI 자동튜닝 제외)"
    )


def test_g212_3_donchian_period_absent_from_int_params():
    """INT_PARAMS 에 donchian_period 부재 (Red: 현재 L114 잔존 → FAIL)."""
    from src.engine.recommendation_engine import INT_PARAMS
    assert "donchian_period" not in INT_PARAMS, (
        "INT_PARAMS 에 'donchian_period' 잔존 금지 (사이클 212 — PARAM_RANGES 제거 동반)"
    )


def test_g212_3_buy_threshold_not_in_int_params():
    """buy_threshold 는 float — INT_PARAMS 미등록 (제거 후에도 부재 유지)."""
    from src.engine.recommendation_engine import INT_PARAMS
    assert "buy_threshold" not in INT_PARAMS, (
        "'buy_threshold' 은 float — INT_PARAMS 미등록 (본 사이클 무관, 부재 유지)"
    )


# ===========================================================================
# 불변식 — 잔존 키 보존 (PASS 유지, 과제거 회귀 방지)
# ===========================================================================
def test_invariant_other_param_ranges_keys_remain():
    """나머지 PARAM_RANGES 키가 잔존 (진입 임계 2키만 제거)."""
    from src.engine.recommendation_engine import PARAM_RANGES
    for key in (
        "stop_loss_rate",
        "k_value_krx_main",
        "k_value_nxt_pre",
        "k_value_nxt_post",
        "long_ma_period",
        "volume_multiplier",
        "atr_trail_mult",
        "position_ratio",
        "max_positions",
        "k_period",
        "max_scan_stocks",
        "min_prdy_rate",
        "breakout_retention_minutes",
        "breakout_fail_n_days",
    ):
        assert key in PARAM_RANGES, f"잔존 의무 PARAM_RANGES 키 누락: {key}"


def test_invariant_other_int_params_keys_remain():
    """나머지 INT_PARAMS 키가 잔존 (donchian_period 만 제거)."""
    from src.engine.recommendation_engine import INT_PARAMS
    for key in (
        "max_positions",
        "k_period",
        "max_scan_stocks",
        "long_ma_period",
        "breakout_retention_minutes",
        "breakout_fail_n_days",
    ):
        assert key in INT_PARAMS, f"잔존 의무 INT_PARAMS 키 누락: {key}"


def test_invariant_int_params_subset_of_param_ranges():
    """INT_PARAMS ⊆ PARAM_RANGES 규약 보존 (donchian_period 동시 제거로 유지)."""
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES
    assert INT_PARAMS.issubset(PARAM_RANGES.keys()), (
        f"INT_PARAMS 가 PARAM_RANGES 밖: {INT_PARAMS - set(PARAM_RANGES.keys())}"
    )


def test_invariant_cycle208_209_exclusions_still_absent():
    """사이클 208/209 제외분(box/max_box/max_breakout_extension) 부재 유지."""
    from src.engine.recommendation_engine import PARAM_RANGES, INT_PARAMS
    for key in (
        "box_contraction_period",
        "max_box_volatility_pct",
        "max_breakout_extension_pct",
    ):
        assert key not in PARAM_RANGES, f"사이클 208/209 제외분 재유입: {key}"
        assert key not in INT_PARAMS, f"사이클 208 제외분 INT_PARAMS 재유입: {key}"
