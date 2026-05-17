"""사이클 1 (2026-05-17) — parameter_recommendations 의 `weight_reasoning` 컬럼 round-trip.

마이그레이션 021 `ALTER TABLE ... ADD COLUMN weight_reasoning TEXT` 적용 후
`insert_recommendation()` 시그니처가 `weight_reasoning: str | None = None` 키워드를 받는다.

J4 (2026-05-12) 기존 시그니처 `recommended_weight` / `code_review_notes` 회귀 보존.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest


@pytest.fixture
def fake_supabase(monkeypatch):
    """supabase.table().insert/select/update().execute() 캡처용 가짜."""
    captured = SimpleNamespace(insert=None, update=None)

    class _Result:
        def __init__(self, data):
            self.data = data

    class _Query:
        def __init__(self):
            self._mode = None
            self._payload = None

        def select(self, *_):
            return self

        def eq(self, *_):
            return self

        def lt(self, *_):
            return self

        def gte(self, *_):
            return self

        def order(self, *_, **__):
            return self

        def limit(self, *_):
            return self

        def insert(self, payload):
            self._mode = "insert"
            self._payload = payload
            captured.insert = payload
            return self

        def update(self, payload):
            self._mode = "update"
            self._payload = payload
            captured.update = payload
            return self

        def execute(self):
            if self._mode == "insert":
                row = dict(self._payload or {})
                row.setdefault("id", "test-id")
                row.setdefault("created_at", "2026-05-17T20:00:00+09:00")
                return _Result([row])
            if self._mode == "update":
                return _Result([dict(self._payload or {})])
            return _Result([])

    class _Supabase:
        def table(self, _name):
            return _Query()

    import src.db.parameter_recommendations as mod
    monkeypatch.setattr(mod, "supabase", _Supabase())
    return captured


@pytest.mark.asyncio
async def test_insert_recommendation_with_weight_reasoning(fake_supabase):
    """Case A — insert_recommendation(weight_reasoning=...) 정상 저장."""
    from src.db.parameter_recommendations import insert_recommendation

    result = await insert_recommendation(
        target_date=date(2026, 5, 17),
        strategy_id="long_tail_volatility",
        current_params={"intraday_stop_loss": -3.0},
        recommended_params={"intraday_stop_loss": -2.5},
        reasoning="LTV 전략 점검",
        metrics={},
        recommended_weight=0.18,
        code_review_notes=None,
        weight_reasoning="peer 대비 손절률 높음 → 0.26 → 0.18 축소",
    )

    assert fake_supabase.insert is not None
    assert fake_supabase.insert["weight_reasoning"] == "peer 대비 손절률 높음 → 0.26 → 0.18 축소"
    assert fake_supabase.insert["recommended_weight"] == 0.18
    assert result is not None
    assert result["weight_reasoning"] == "peer 대비 손절률 높음 → 0.26 → 0.18 축소"


@pytest.mark.asyncio
async def test_insert_recommendation_weight_reasoning_null(fake_supabase):
    """Case B — weight_reasoning=None 정상 저장."""
    from src.db.parameter_recommendations import insert_recommendation

    await insert_recommendation(
        target_date=date(2026, 5, 17),
        strategy_id="momentum",
        current_params={},
        recommended_params={},
        reasoning="",
        metrics={},
        recommended_weight=None,
        code_review_notes=None,
        weight_reasoning=None,
    )

    assert fake_supabase.insert is not None
    assert fake_supabase.insert.get("weight_reasoning") is None


@pytest.mark.asyncio
async def test_insert_recommendation_j4_signature_regression(fake_supabase):
    """Case C — 기존 J4 시그니처(`recommended_weight`/`code_review_notes`) 회귀 보존.

    `weight_reasoning` kwarg 누락 호출에도 정상 작동, INSERT data 에 None 으로 포함되어야 함.
    """
    from src.db.parameter_recommendations import insert_recommendation

    # weight_reasoning 미지정 — 기본 None
    await insert_recommendation(
        target_date=date(2026, 5, 17),
        strategy_id="volatility_breakout",
        current_params={"k_value_krx_main": 0.5},
        recommended_params={"k_value_krx_main": 0.6},
        reasoning="VB 전략 점검",
        metrics={},
        recommended_weight=0.48,
        code_review_notes="신규 파라미터 도입 권고",
    )

    assert fake_supabase.insert is not None
    # J4 키 보존
    assert fake_supabase.insert["recommended_weight"] == 0.48
    assert fake_supabase.insert["code_review_notes"] == "신규 파라미터 도입 권고"
    # 사이클 1 신규 키는 None 으로 포함되거나 미포함 모두 수용
    assert fake_supabase.insert.get("weight_reasoning") is None


@pytest.mark.asyncio
async def test_insert_recommendation_weight_reasoning_default_is_none(fake_supabase):
    """Case D — kwarg default 값 검증. 명시적 미지정 ↔ None 명시 동일 동작."""
    from src.db.parameter_recommendations import insert_recommendation
    import inspect

    sig = inspect.signature(insert_recommendation)
    assert "weight_reasoning" in sig.parameters
    assert sig.parameters["weight_reasoning"].default is None
