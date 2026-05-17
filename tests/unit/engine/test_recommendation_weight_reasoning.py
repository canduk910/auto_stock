"""사이클 1 (2026-05-17) — recommendation_engine 의 `weight_reasoning` 분리 검증.

J4 (2026-05-12) 의 통합 `reasoning` 에 묻혀 있던 비중 변경 사유를 별도 필드로 분리.
`_validate_recommendations()` 반환 5-tuple `(validated_params, reasoning, weight, notes, weight_reasoning)`:

- weight 가 null 이면 weight_reasoning 도 null (자동 정리)
- weight 있는데 weight_reasoning 누락 → fallback `(사유 미제공)` + WARNING 로그
- 1000자 초과 시 truncate + WARNING
- 비-str 이면 None fallback

`_workspace/00_leader_trading_rules.md` 참조 — 다음 자문 사이클(5/18 월 20:00) 부터 적용.
"""

from __future__ import annotations

import logging

import pytest


def test_validate_signature_has_five_return_values():
    """확장된 시그니처: 5-tuple `(validated_params, reasoning, weight, notes, weight_reasoning)`."""
    from src.engine.recommendation_engine import _validate_recommendations

    result = _validate_recommendations({"recommended_params": {}}, {})
    assert isinstance(result, tuple)
    assert len(result) == 5


def test_validate_weight_with_reasoning_returns_both():
    """Case B — weight + weight_reasoning 정상이면 둘 다 반환된다."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {},
        "reasoning": "전략 전반 점검",
        "recommended_weight": 0.18,
        "weight_reasoning": "최근 30일 손절률 증가로 보수적 비중 권고",
        "code_review_notes": None,
    }
    validated, reasoning, weight, notes, weight_reasoning = _validate_recommendations(
        raw, {},
    )

    assert validated == {}
    assert reasoning == "전략 전반 점검"
    assert weight == 0.18
    assert notes is None
    assert weight_reasoning == "최근 30일 손절률 증가로 보수적 비중 권고"


def test_validate_weight_missing_reasoning_fallback(caplog):
    """Case C — weight 있는데 weight_reasoning 누락 → `(사유 미제공)` fallback + WARNING."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {},
        "recommended_weight": 0.35,
        # weight_reasoning 키 누락
    }
    with caplog.at_level(logging.WARNING):
        _, _, weight, _, weight_reasoning = _validate_recommendations(raw, {})

    assert weight == 0.35
    assert weight_reasoning == "(사유 미제공)"
    assert any(
        "weight_reasoning" in rec.message.lower() or "사유" in rec.message
        for rec in caplog.records
    )


def test_validate_weight_missing_reasoning_null_fallback_too(caplog):
    """Case C-2 — weight 있는데 weight_reasoning 이 명시적으로 null 이어도 동일 fallback."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {},
        "recommended_weight": 0.5,
        "weight_reasoning": None,
    }
    with caplog.at_level(logging.WARNING):
        _, _, weight, _, weight_reasoning = _validate_recommendations(raw, {})

    assert weight == 0.5
    assert weight_reasoning == "(사유 미제공)"


def test_validate_weight_null_clears_reasoning():
    """Case D — weight 가 null 이면 weight_reasoning 도 null 로 자동 정리."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {},
        "recommended_weight": None,
        # LLM 이 변경 권고 없으면서 사유만 남기는 비정상 출력에도 None 으로 정리해야 함
        "weight_reasoning": "사유 텍스트 (weight 변경 없는데 채워짐)",
    }
    _, _, weight, _, weight_reasoning = _validate_recommendations(raw, {})

    assert weight is None
    assert weight_reasoning is None


def test_validate_weight_reasoning_truncates_over_1000_chars(caplog):
    """Case E — 1000자 초과 시 truncate + WARNING."""
    from src.engine.recommendation_engine import _validate_recommendations

    long_text = "가" * 1500
    raw = {
        "recommended_params": {},
        "recommended_weight": 0.25,
        "weight_reasoning": long_text,
    }
    with caplog.at_level(logging.WARNING):
        _, _, _, _, weight_reasoning = _validate_recommendations(raw, {})

    assert weight_reasoning is not None
    assert len(weight_reasoning) == 1000
    assert any(
        "weight_reasoning" in rec.message.lower() or "1000" in rec.message
        for rec in caplog.records
    )


def test_validate_weight_reasoning_non_string_fallback():
    """Case F — weight_reasoning 이 비-str 이면 fallback `(사유 미제공)`."""
    from src.engine.recommendation_engine import _validate_recommendations

    for bad in [123, [], {"a": 1}, 0.5]:
        raw = {
            "recommended_params": {},
            "recommended_weight": 0.3,
            "weight_reasoning": bad,
        }
        _, _, weight, _, weight_reasoning = _validate_recommendations(raw, {})
        assert weight == 0.3
        # 비-str 은 `(사유 미제공)` fallback (필드는 있지만 형식 불일치)
        assert weight_reasoning == "(사유 미제공)", (
            f"입력 {bad!r} 에서 fallback 안 됨: {weight_reasoning!r}"
        )


def test_validate_weight_reasoning_preserves_under_1000_chars():
    """1000자 이내 weight_reasoning 은 그대로 보존된다."""
    from src.engine.recommendation_engine import _validate_recommendations

    text = "peer 전략 momentum 이 더 우수해 본 전략 비중 축소"
    raw = {
        "recommended_params": {},
        "recommended_weight": 0.18,
        "weight_reasoning": text,
    }
    _, _, _, _, weight_reasoning = _validate_recommendations(raw, {})
    assert weight_reasoning == text


def test_validate_weight_reasoning_empty_string_fallback():
    """빈 문자열도 사유 미제공으로 처리 (LLM 빈 문자열 출력 케이스)."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {},
        "recommended_weight": 0.2,
        "weight_reasoning": "",
    }
    _, _, weight, _, weight_reasoning = _validate_recommendations(raw, {})
    assert weight == 0.2
    assert weight_reasoning == "(사유 미제공)"


def test_validate_515_ltv_fixture_separation():
    """Case G — 5/15 실측 LTV 자문 fixture 재현.

    원본 (J4): weight 0.26 → 0.18, reasoning 에 비중 사유가 통합되어 있음.
    개선 후: weight_reasoning 별도 필드에서 분리 검증.
    """
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {"intraday_stop_loss": -2.5},
        "reasoning": (
            "LTV는 최근 30일 손절률이 높고 누적 수익률이 부진합니다. "
            "intraday_stop_loss 를 -3 → -2.5 로 조이고, 비중도 조정합니다."
        ),
        "recommended_weight": 0.18,
        "weight_reasoning": (
            "peer momentum/donchian 대비 누적 수익률 열위 + 손절률 증가로 "
            "본 전략 비중 0.26 → 0.18 로 축소 권고"
        ),
        "code_review_notes": None,
    }
    validated, reasoning, weight, notes, weight_reasoning = _validate_recommendations(
        raw, {"intraday_stop_loss": -3.0},
    )

    assert validated == {"intraday_stop_loss": -2.5}
    assert "LTV는 최근 30일" in reasoning
    assert weight == 0.18
    assert notes is None
    assert weight_reasoning is not None
    assert "0.26" in weight_reasoning and "0.18" in weight_reasoning


def test_validate_both_none_returns_normally():
    """둘 다 null/누락이어도 기존 흐름 정상 처리 (params 검증만)."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {"recommended_params": {"buy_threshold": 25.0}, "reasoning": "test"}
    validated, reasoning, weight, notes, weight_reasoning = _validate_recommendations(
        raw, {"buy_threshold": 29.0},
    )

    assert validated == {"buy_threshold": 25.0}
    assert reasoning == "test"
    assert weight is None
    assert notes is None
    assert weight_reasoning is None
