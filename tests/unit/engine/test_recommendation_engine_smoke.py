"""recommendation_engine.py 복구 smoke 테스트.

2026-05-09 TDD 하네스 커밋(53ddde2)에서 실수로 삭제된 모듈을 복구한 직후의
import 가능성과 핵심 시그니처 + 검증 헬퍼(_validate_recommendations) 동작만 검증한다.

복구 모듈 자체에 대한 deep test 는 이번 PR 범위 밖.
"""

from __future__ import annotations

import inspect


def test_recommendation_engine_importable():
    """모듈 import 자체가 성공해야 한다 (4일째 미생성 결함 차단)."""
    from src.engine import recommendation_engine

    assert recommendation_engine is not None


def test_generate_recommendations_is_async_callable():
    """generate_recommendations 가 async 함수이고 인자 없이 호출 가능해야 한다."""
    from src.engine.recommendation_engine import generate_recommendations

    assert callable(generate_recommendations)
    assert inspect.iscoroutinefunction(generate_recommendations)
    sig = inspect.signature(generate_recommendations)
    # 인자 없는 코루틴
    assert len(sig.parameters) == 0


def test_param_ranges_present_and_bounded():
    """PARAM_RANGES 화이트리스트가 보존되어야 한다 (LLM 출력 검증 핵심)."""
    from src.engine.recommendation_engine import PARAM_RANGES, INT_PARAMS

    # 핵심 키 존재 + (min<max) 검증
    # 사이클 212 의미 전환: buy_threshold 는 진입 임계라 PARAM_RANGES 에서 제거됨
    # (AI 자동튜닝 제외) → expected_keys 에서 삭제.
    expected_keys = {
        "stop_loss_rate", "position_ratio",
        "max_positions", "k_period",
    }
    assert expected_keys.issubset(PARAM_RANGES.keys())
    for key, (lo, hi) in PARAM_RANGES.items():
        assert lo < hi, f"{key}: invalid range ({lo}, {hi})"

    # INT_PARAMS 는 PARAM_RANGES 의 부분집합
    assert INT_PARAMS.issubset(PARAM_RANGES.keys())


def test_validate_recommendations_filters_unknown_key():
    """비화이트리스트 키는 제외 + 화이트리스트 키는 통과.

    사이클 212 의미 전환: buy_threshold 가 PARAM_RANGES 에서 제거됨 → ghost_param
    과 동일하게 드롭. 화이트리스트 잔존 키(position_ratio)로 통과 계약 검증.
    """
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {"position_ratio": 0.3, "ghost_param": 99},
        "reasoning": "test",
    }
    current = {"position_ratio": 0.2}
    validated, reasoning, _weight, _notes, _wr = _validate_recommendations(raw, current)

    assert "ghost_param" not in validated
    assert validated["position_ratio"] == 0.3
    assert reasoning == "test"


def test_validate_recommendations_clamps_out_of_range():
    """허용 범위 벗어난 값은 제외되어야 한다.

    사이클 212 의미 전환: buy_threshold 제거 → 화이트리스트 잔존 float 키
    k_value_krx_main 허용 (0.5, 2.0) 로 범위 밖(2.5) 제외 검증.
    """
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {"k_value_krx_main": 2.5},
        "reasoning": "",
    }
    current = {"k_value_krx_main": 1.0}
    validated, _, _w, _n, _wr = _validate_recommendations(raw, current)
    assert "k_value_krx_main" not in validated


def test_validate_recommendations_casts_int_params():
    """INT_PARAMS 키는 정수로 캐스트되어야 한다."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {"max_positions": 5.4},
        "reasoning": "",
    }
    current = {"max_positions": 3}
    validated, _, _w, _n, _wr = _validate_recommendations(raw, current)
    assert validated["max_positions"] == 5
    assert isinstance(validated["max_positions"], int)
