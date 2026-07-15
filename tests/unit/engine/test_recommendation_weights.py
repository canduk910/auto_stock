"""Phase J4 — recommendation_engine 의 weight + code_review_notes 검증 헬퍼 테스트.

`_validate_recommendations()` 는 LLM 응답에서 다음 신규 필드를 검증해야 한다:
- `recommended_weight`: float, [0.0, 1.0] 범위. 범위 외면 None + WARNING 로그
- `code_review_notes`: str, len <= 2000. 초과 시 2000자로 잘라냄. 비-str 이면 None

기존 `recommended_params` + `reasoning` 시그니처와 호환되며,
신규 키 둘 다 None 일 때도 정상 처리해야 한다.
"""

from __future__ import annotations

import logging

import pytest


def test_validate_returns_weight_in_range():
    """0.0~1.0 범위의 weight 는 그대로 반환된다."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {},
        "reasoning": "비중을 올리는 것을 추천",
        "recommended_weight": 0.35,
        "code_review_notes": None,
    }
    validated, reasoning, weight, notes, _wr = _validate_recommendations(raw, {})

    assert validated == {}
    assert reasoning == "비중을 올리는 것을 추천"
    assert weight == 0.35
    assert notes is None


def test_validate_weight_out_of_range_returns_none_and_warns(caplog):
    """1.5 같은 범위 외 weight 는 None 으로 무시되고 WARNING 로그가 남는다."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {},
        "reasoning": "test",
        "recommended_weight": 1.5,
        "code_review_notes": None,
    }
    with caplog.at_level(logging.WARNING):
        _, _, weight, _, _ = _validate_recommendations(raw, {})

    assert weight is None
    # WARNING 로그 1개 이상에 weight 관련 메시지 존재
    assert any("weight" in rec.message.lower() for rec in caplog.records)


def test_validate_weight_negative_returns_none():
    """음수 weight 도 None 으로 무시된다."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {},
        "reasoning": "",
        "recommended_weight": -0.1,
        "code_review_notes": None,
    }
    _, _, weight, _, _ = _validate_recommendations(raw, {})
    assert weight is None


def test_validate_weight_non_numeric_returns_none():
    """문자열·null 등 비-숫자 weight 는 None."""
    from src.engine.recommendation_engine import _validate_recommendations

    for bad in ["foo", None, [], {}]:
        raw = {"recommended_params": {}, "recommended_weight": bad}
        _, _, weight, _, _ = _validate_recommendations(raw, {})
        assert weight is None, f"입력 {bad!r} 에서 None 이 아님: {weight!r}"


def test_validate_notes_truncates_over_2000_chars():
    """2500자 notes 는 2000자로 잘려야 한다."""
    from src.engine.recommendation_engine import _validate_recommendations

    long_text = "가" * 2500
    raw = {
        "recommended_params": {},
        "recommended_weight": None,
        "code_review_notes": long_text,
    }
    _, _, _, notes, _ = _validate_recommendations(raw, {})

    assert notes is not None
    assert len(notes) == 2000


def test_validate_notes_preserves_under_2000_chars():
    """2000자 이내 notes 는 그대로 보존된다."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {},
        "recommended_weight": None,
        "code_review_notes": "신규 파라미터 ATR-trailing 도입 권고",
    }
    _, _, _, notes, _ = _validate_recommendations(raw, {})
    assert notes == "신규 파라미터 ATR-trailing 도입 권고"


def test_validate_notes_non_string_returns_none():
    """비-str notes (숫자/리스트 등) 는 None."""
    from src.engine.recommendation_engine import _validate_recommendations

    for bad in [123, [], {"a": 1}]:
        raw = {"recommended_params": {}, "code_review_notes": bad}
        _, _, _, notes, _ = _validate_recommendations(raw, {})
        assert notes is None, f"입력 {bad!r} 에서 None 이 아님: {notes!r}"


def test_validate_signature_has_five_return_values_for_weight_reasoning():
    """사이클 1 (2026-05-17) — 시그니처 5-tuple 확장 회귀 가드.

    `_validate_recommendations` 가 weight_reasoning 을 5번째 요소로 반환.
    기존 J4 의 4-tuple 시그니처 가정은 invalid.
    """
    from src.engine.recommendation_engine import _validate_recommendations

    result = _validate_recommendations({"recommended_params": {}}, {})
    assert isinstance(result, tuple)
    assert len(result) == 5


def test_validate_both_none_returns_normally():
    """둘 다 null/누락이어도 기존 흐름 정상 처리 (params 검증만)."""
    from src.engine.recommendation_engine import _validate_recommendations

    # 사이클 212 — buy_threshold 는 PARAM_RANGES 제외(진입 임계 화이트리스트 폐기) →
    # 표본 키를 잔존 키(stop_loss_rate)로 교체. 테스트 의도(params 검증 통과 시
    # reasoning/weight/notes/weight_reasoning 필드 계약)는 불변.
    raw = {"recommended_params": {"stop_loss_rate": -5.0}, "reasoning": "test"}
    validated, reasoning, weight, notes, weight_reasoning = _validate_recommendations(
        raw, {"stop_loss_rate": -3.0},
    )

    assert validated == {"stop_loss_rate": -5.0}
    assert reasoning == "test"
    assert weight is None
    assert notes is None
    assert weight_reasoning is None


def test_validate_signature_has_five_return_values_post_cycle1():
    """사이클 1 (2026-05-17) — J4 4-tuple 에서 weight_reasoning 추가된 5-tuple 로 확장.

    (validated_params, reasoning, weight, notes, weight_reasoning)
    """
    from src.engine.recommendation_engine import _validate_recommendations

    result = _validate_recommendations({"recommended_params": {}}, {})
    assert isinstance(result, tuple)
    assert len(result) == 5
