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
    expected_keys = {
        "buy_threshold", "stop_loss_rate", "position_ratio",
        "max_positions", "k_period",
    }
    assert expected_keys.issubset(PARAM_RANGES.keys())
    for key, (lo, hi) in PARAM_RANGES.items():
        assert lo < hi, f"{key}: invalid range ({lo}, {hi})"

    # INT_PARAMS 는 PARAM_RANGES 의 부분집합
    assert INT_PARAMS.issubset(PARAM_RANGES.keys())


def test_validate_recommendations_filters_unknown_key():
    """현재 params 에 없는 키는 제외되어야 한다."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {"buy_threshold": 25.0, "ghost_param": 99},
        "reasoning": "test",
    }
    current = {"buy_threshold": 29.0}
    validated, reasoning, _weight, _notes, _wr = _validate_recommendations(raw, current)

    assert "ghost_param" not in validated
    assert validated["buy_threshold"] == 25.0
    assert reasoning == "test"


def test_validate_recommendations_clamps_out_of_range():
    """허용 범위 벗어난 값은 제외되어야 한다."""
    from src.engine.recommendation_engine import _validate_recommendations

    # buy_threshold 허용 (0, 30) — 31 은 범위 밖
    raw = {
        "recommended_params": {"buy_threshold": 31.0},
        "reasoning": "",
    }
    current = {"buy_threshold": 29.0}
    validated, _, _w, _n, _wr = _validate_recommendations(raw, current)
    assert "buy_threshold" not in validated


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
