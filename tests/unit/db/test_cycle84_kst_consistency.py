"""사이클 84 Red — L-1 (LOW): `changed_at` KST `+09:00` 영속 (사이클 68 답습).

migration 032 trigger 함수가 `changed_at TIMESTAMPTZ DEFAULT now()` (PostgreSQL TIMESTAMPTZ 모델
= UTC instant 저장 + 표시 시점 변환, 사이클 69 명문화 영속). 응답 시점 표시 형식은 KST `+09:00` 영속.

본 테스트는 migration SQL 정적 검증으로 `changed_at TIMESTAMPTZ` 명시 + Python 헬퍼 응답 시점
KST `+09:00` 표시 정합성 검증.

위험 등급 LOW (사이클 68 영속 가드 영역 확장).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "supabase" / "migrations" / "032_stock_master_history.sql"
)


def test_L1_changed_at_timestamptz_with_default_now():
    """L-1: `changed_at` 컬럼이 TIMESTAMPTZ 타입 + DEFAULT now() 명시.

    사이클 69 명문화: PostgreSQL TIMESTAMPTZ = UTC instant 저장 + 표시 시점 변환.
    DEFAULT now() = Supabase PG UTC = Python datetime.now() (TZ=Asia/Seoul) instant 동일.
    """
    assert MIGRATION_PATH.exists(), (
        f"migration 032 미작성: {MIGRATION_PATH} — backend-dev Green 단계 의무"
    )
    sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
    assert "changed_at" in sql, "changed_at 컬럼 정의 부재"
    assert "timestamptz" in sql, (
        "changed_at TIMESTAMPTZ 타입 명시 의무 (사이클 68 KST 영속 + 사이클 69 명문화)"
    )
    # DEFAULT now() 명시 (auto-set)
    assert "default" in sql and "now()" in sql, (
        "changed_at DEFAULT now() 명시 의무"
    )
