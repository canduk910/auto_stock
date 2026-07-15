"""PARAM_RANGES 화이트리스트 확장 (2026-05-17, Phase B) 회귀 가드.

5/15 첫 자문 발화에서 4 전략의 `code_review_notes` 가 강하게 권고한 키 8 종을
PARAM_RANGES 에 추가해 OpenAI 가 다음 자문 사이클(5/18) 부터 자동 튜닝할 수 있게
한다. 본 테스트는 다음 5 케이스를 강제한다:

  A: 신규 8 키 모두 PARAM_RANGES 에 등록 + 범위(lo<hi) 정합성
  B: `_validate_recommendations` 가 신규 키 추천값을 정상 통과
  C: 범위 밖 값은 무시 (WARNING 로그)
  D: `long_ma_period` 가 INT_PARAMS 에 등록 → 정수 캐스트
     (사이클 212: donchian_period 는 진입 임계라 PARAM_RANGES/INT_PARAMS 에서 제거)
  E: 기존 키 회귀 보존 (position_ratio / max_positions / stop_loss_rate)

본 사이클에서는 `min_prdy_rate` 는 이미 등록되어 있어 중복 추가 금지 — 회귀 보존
케이스로 함께 검증.
"""

from __future__ import annotations

import logging


# 신규 키 명세 (단, min_prdy_rate 는 이미 PARAM_RANGES 에 존재 → 회귀 보존만 검증)
# 사이클 212 의미 전환: donchian_period 는 PARAM_RANGES/INT_PARAMS 에서 제거됨
# (진입 임계 = 전략 정체성 상수, AI 자동튜닝 제외) → 본 목록에서 삭제.
_NEW_RANGE_KEYS = {
    "k_value_krx_main": (0.5, 2.0),
    "k_value_nxt_pre": (0.5, 2.0),
    "k_value_nxt_post": (0.5, 2.0),
    "long_ma_period": (20, 120),
    "volume_multiplier": (1.0, 5.0),
    "atr_trail_mult": (1.0, 5.0),
}

# 사이클 212 의미 전환: donchian_period 제거 → long_ma_period 단독 INT 캐스트 잔존.
_NEW_INT_KEYS = {"long_ma_period"}


# ---------------------------------------------------------------------------
# A. 신규 키 등록 + 범위 정합성
# ---------------------------------------------------------------------------
def test_param_ranges_includes_new_eight_keys():
    """신규 8 키(k_value_* 3 + donchian_period + long_ma_period + volume_multiplier
    + atr_trail_mult + min_prdy_rate) 가 모두 PARAM_RANGES 에 등록되어야 한다.

    `min_prdy_rate` 는 사이클 진입 시점에 이미 등록되어 있어 별도 변경 없음.
    """
    from src.engine.recommendation_engine import PARAM_RANGES

    expected_keys = set(_NEW_RANGE_KEYS.keys()) | {"min_prdy_rate"}
    assert expected_keys.issubset(PARAM_RANGES.keys()), (
        f"누락된 키: {expected_keys - set(PARAM_RANGES.keys())}"
    )


def test_param_ranges_new_keys_bounds_match_spec():
    """신규 7 키 범위가 leader 명세와 정확히 일치해야 한다."""
    from src.engine.recommendation_engine import PARAM_RANGES

    for key, (lo, hi) in _NEW_RANGE_KEYS.items():
        assert PARAM_RANGES[key] == (lo, hi), (
            f"{key}: 범위 불일치 — 명세 {(lo, hi)} vs 실제 {PARAM_RANGES[key]}"
        )
        assert lo < hi, f"{key}: invalid range ({lo}, {hi})"


def test_int_params_includes_donchian_and_long_ma_period():
    """long_ma_period 가 INT_PARAMS 에 등록되어 정수 캐스트 대상.

    사이클 212 의미 전환: donchian_period 는 진입 임계라 PARAM_RANGES/INT_PARAMS
    에서 제거됨 → INT_PARAMS 부재 단언 (long_ma_period 만 잔존).
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert _NEW_INT_KEYS.issubset(INT_PARAMS), (
        f"INT_PARAMS 누락: {_NEW_INT_KEYS - INT_PARAMS}"
    )
    assert "donchian_period" not in INT_PARAMS, (
        "사이클 212 — donchian_period 는 INT_PARAMS 에서 제거됨 (진입 임계 제외)"
    )
    # 그리고 PARAM_RANGES 부분집합 규약 보존
    assert INT_PARAMS.issubset(PARAM_RANGES.keys())


# ---------------------------------------------------------------------------
# B. 정상 추천값 통과
# ---------------------------------------------------------------------------
def test_validate_recommendations_accepts_new_float_keys():
    """k_value_krx_main / volume_multiplier / atr_trail_mult 정상 범위 통과."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {
            "k_value_krx_main": 1.2,
            "k_value_nxt_pre": 0.8,
            "k_value_nxt_post": 1.5,
            "volume_multiplier": 2.0,
            "atr_trail_mult": 2.5,
        },
        "reasoning": "5/15 자문 권고 반영",
    }
    current = {
        "k_value_krx_main": 1.0,
        "k_value_nxt_pre": 1.0,
        "k_value_nxt_post": 1.0,
        "volume_multiplier": 1.5,
        "atr_trail_mult": 2.0,
    }
    validated, reasoning, _w, _n, _wr = _validate_recommendations(raw, current)

    assert validated["k_value_krx_main"] == 1.2
    assert validated["k_value_nxt_pre"] == 0.8
    assert validated["k_value_nxt_post"] == 1.5
    assert validated["volume_multiplier"] == 2.0
    assert validated["atr_trail_mult"] == 2.5
    assert reasoning == "5/15 자문 권고 반영"


# ---------------------------------------------------------------------------
# C. 범위 밖 값은 무시 + WARNING 로그
# ---------------------------------------------------------------------------
def test_validate_recommendations_rejects_out_of_range_new_keys(caplog):
    """k_value_krx_main 범위(0.5, 2.0) 밖 값(2.5) 은 무시 + WARNING 로그."""
    from src.engine.recommendation_engine import _validate_recommendations

    caplog.set_level(logging.WARNING, logger="src.engine.recommendation_engine")
    # 사이클 212 의미 전환: donchian_period 제거 (진입 임계) → 범위 밖 케이스에서
    # 화이트리스트 float 2 키만 WARNING 발화 (donchian_period 는 비화이트리스트 =
    # WARNING 없이 debug 드롭).
    raw = {
        "recommended_params": {
            "k_value_krx_main": 2.5,  # 상한 초과
            "atr_trail_mult": 0.5,    # 하한 미달
        },
        "reasoning": "",
    }
    current = {
        "k_value_krx_main": 1.0,
        "atr_trail_mult": 2.0,
    }
    validated, _, _w, _n, _wr = _validate_recommendations(raw, current)

    assert "k_value_krx_main" not in validated
    assert "atr_trail_mult" not in validated
    # WARNING 2건 (각 키 1건씩) — 메시지 prefix "추천 값 범위 초과"
    warning_msgs = [
        r.message for r in caplog.records
        if r.levelno == logging.WARNING and "범위 초과" in r.message
    ]
    assert len(warning_msgs) == 2, (
        f"WARNING 누락 — 실제 메시지: {warning_msgs}"
    )


# ---------------------------------------------------------------------------
# D. INT_PARAMS 캐스트
# ---------------------------------------------------------------------------
def test_validate_recommendations_casts_donchian_period_to_int():
    """사이클 212 의미 전환: donchian_period 는 PARAM_RANGES 제거로 이제 드롭됨.

    이전(사이클 23~211): 25.7 → 26 정수 캐스트. 사이클 212 이후: 진입 임계라
    비화이트리스트 → ghost_param 과 동일 취급 (validated 에 부재).
    long_ma_period(잔존 INT 키)로 정수 캐스트 계약 자체는 별도 테스트가 보존.
    """
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {"donchian_period": 25.7},
        "reasoning": "",
    }
    current = {"donchian_period": 20}
    validated, _, _w, _n, _wr = _validate_recommendations(raw, current)

    assert "donchian_period" not in validated, (
        "사이클 212 — donchian_period 는 PARAM_RANGES 제거로 드롭 (자동튜닝 제외)"
    )


def test_validate_recommendations_casts_long_ma_period_to_int():
    """long_ma_period 60.4 → 60."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {"long_ma_period": 60.4},
        "reasoning": "",
    }
    current = {"long_ma_period": 60}
    validated, _, _w, _n, _wr = _validate_recommendations(raw, current)

    assert validated["long_ma_period"] == 60
    assert isinstance(validated["long_ma_period"], int)


# ---------------------------------------------------------------------------
# E. 기존 키 회귀 보존
# ---------------------------------------------------------------------------
def test_existing_keys_preserved():
    """기존 키(position_ratio, max_positions, stop_loss_rate, min_prdy_rate) 보존."""
    from src.engine.recommendation_engine import PARAM_RANGES, INT_PARAMS

    for key in (
        "position_ratio", "max_positions", "stop_loss_rate",
        "min_prdy_rate", "k_period",
    ):
        assert key in PARAM_RANGES, f"기존 키 누락: {key}"
    # max_positions / k_period 는 정수
    assert "max_positions" in INT_PARAMS
    assert "k_period" in INT_PARAMS


def test_existing_validate_flow_still_works():
    """화이트리스트 키 통과 + 비화이트리스트 제거 계약 보존.

    사이클 212 의미 전환: buy_threshold 는 이제 PARAM_RANGES 밖 (진입 임계 제외)
    → ghost_param 과 동일하게 드롭. position_ratio(화이트리스트 잔존)는 통과.
    """
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {
            "buy_threshold": 25.0,
            "position_ratio": 0.3,
            "ghost_param": 99,
        },
        "reasoning": "regression",
    }
    current = {"buy_threshold": 29.0, "position_ratio": 0.2}
    validated, reasoning, _w, _n, _wr = _validate_recommendations(raw, current)

    assert "buy_threshold" not in validated, (
        "사이클 212 — buy_threshold 는 PARAM_RANGES 제거로 드롭 (자동튜닝 제외)"
    )
    assert validated["position_ratio"] == 0.3
    assert "ghost_param" not in validated
    assert reasoning == "regression"
