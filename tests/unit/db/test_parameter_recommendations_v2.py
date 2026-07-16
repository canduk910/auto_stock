"""Phase J4 — parameter_recommendations 의 신규 3컬럼 round-trip 테스트.

- recommended_weight (NUMERIC, nullable)
- code_review_notes (TEXT, nullable, ~2000자)
- applied_weight (NUMERIC, nullable, apply 시점에 채워짐)

`insert_recommendation()` 시 신규 키 모두 INSERT data 에 포함되어야 하고,
`update_recommendation_status()` 가 `applied_weight` 키워드를 받아 update 페이로드에 반영해야 한다.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

# 사이클 M3a (Supabase→RDS asyncpg 전환) — 이 파일 전체 xfail.
# supabase 체인 mock 기반 검증인데 parameter_recommendations 가 pg(asyncpg) 단독
# 전환되어 supabase 심볼이 사라짐 → 체인 mock 라우팅 불가. 신규 3컬럼
# (recommended_weight/code_review_notes/applied_weight) round-trip 계약은 pg 레벨
# test_cycleM3a_parameter_recommendations_pg.py + 실 PG
# test_cycleM3a_three_modules_roundtrip.py 가 계승.
pytestmark = pytest.mark.xfail(
    reason=(
        "사이클 M3a (2026-07-16) 의미 전환 — parameter_recommendations 가 "
        "supabase-py 에서 src.db.pg(asyncpg) 로 전환되어 supabase 체인 mock 라우팅 "
        "불가. 신규 3컬럼 round-trip 계약은 "
        "test_cycleM3a_parameter_recommendations_pg.py + "
        "test_cycleM3a_three_modules_roundtrip.py 가 계승."
    ),
    strict=False,
)


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
            # insert/update 는 echo back, select 는 빈 리스트
            if self._mode == "insert":
                # PostgreSQL 응답 시뮬레이션: id/created_at 부여
                row = dict(self._payload or {})
                row.setdefault("id", "test-id")
                row.setdefault("created_at", "2026-05-12T16:00:00+09:00")
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
async def test_insert_recommendation_includes_new_columns(fake_supabase):
    """insert_recommendation 호출 시 신규 3컬럼이 INSERT data 에 포함되어야 한다."""
    from src.db.parameter_recommendations import insert_recommendation

    result = await insert_recommendation(
        target_date=date(2026, 5, 12),
        strategy_id="momentum",
        current_params={"position_ratio": 0.25},
        recommended_params={"position_ratio": 0.3},
        reasoning="weight 상향 권고",
        metrics={},
        recommended_weight=0.35,
        code_review_notes="신규 파라미터 도입 권고",
    )

    assert fake_supabase.insert is not None
    assert fake_supabase.insert["recommended_weight"] == 0.35
    assert fake_supabase.insert["code_review_notes"] == "신규 파라미터 도입 권고"
    # applied_weight 는 INSERT 시점에는 None (apply 시점에 채워짐)
    assert fake_supabase.insert.get("applied_weight") is None
    assert result is not None
    assert result["recommended_weight"] == 0.35


@pytest.mark.asyncio
async def test_insert_recommendation_with_null_new_columns(fake_supabase):
    """신규 컬럼 None 입력 시도 정상 처리 — 키 자체는 포함되거나 None 으로 유지."""
    from src.db.parameter_recommendations import insert_recommendation

    await insert_recommendation(
        target_date=date(2026, 5, 12),
        strategy_id="momentum",
        current_params={},
        recommended_params={},
        reasoning="",
        metrics={},
        recommended_weight=None,
        code_review_notes=None,
    )

    assert fake_supabase.insert is not None
    # None 명시 또는 키 미포함 모두 수용
    assert fake_supabase.insert.get("recommended_weight") is None
    assert fake_supabase.insert.get("code_review_notes") is None


@pytest.mark.asyncio
async def test_update_status_with_applied_weight(fake_supabase):
    """update_recommendation_status 가 applied_weight 키워드를 받아 update 페이로드에 반영."""
    from src.db.parameter_recommendations import update_recommendation_status

    await update_recommendation_status(
        "test-id", "applied",
        applied_params={"position_ratio": 0.3},
        applied_weight=0.4,
    )

    assert fake_supabase.update is not None
    assert fake_supabase.update["applied_weight"] == 0.4
    assert fake_supabase.update["status"] == "applied"


@pytest.mark.asyncio
async def test_update_status_without_applied_weight(fake_supabase):
    """applied_weight 누락 시 update 페이로드에 키 자체 미포함 (기존 동작 보존)."""
    from src.db.parameter_recommendations import update_recommendation_status

    await update_recommendation_status(
        "test-id", "applied", applied_params={"position_ratio": 0.3},
    )

    assert fake_supabase.update is not None
    # applied_weight 미포함 또는 None — 명시적 update 없음
    assert fake_supabase.update.get("applied_weight") is None
