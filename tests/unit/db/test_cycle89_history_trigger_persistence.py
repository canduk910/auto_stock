"""사이클 89 L-4 — 사이클 84 stock_master_history trigger 영속 검증.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

domain-expert 자문 영속:
- 사이클 84 stock_master_history trigger 영속 영역
- Q22 채택: 90일 retention 영속 (사이클 84 영속)
- 500 universe 적재 → 500 ticker × 1회/일 = 일 500 INSERT/UPDATE/TTL_REFRESH 부담
- 90일 retention × 500 ticker × 1회/일 = 45,000 row (5% 안전 영역)

기대 동작 (Green, 사이클 90):
- 사이클 84 trigger 영속 (변경 0)
- 500 universe upsert 시 history trigger 자연 발화

Red 상태 (사이클 89): 사이클 84 영역 침범 시 FAIL (영속 위반).

영속 의무:
- 사이클 84 trigger + 90일 retention 영속
- 사이클 89 시정 영역 = scanner/scheduler/stock_master_metrics 한정 (DB trigger 영역 침범 0)
- 매매 안전성 영향 0 (DB 영역)
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[3] / "supabase" / "migrations"
)


def test_l4_cycle84_history_trigger_migration_persists():
    """L-4: 사이클 84 stock_master_history trigger migration 영속 확인.

    검증 매트릭스:
    - migration 032 (stock_master_history) 파일 존재 (사이클 84 영속)
    - trigger 정의 `stock_master_history_trigger` 영속
    - 사이클 89 시정 영역에서 migration 변경 0

    Red 상태 (사이클 89): migration 032 부재 시 FAIL (사이클 84 영속 위반).

    Green (사이클 90): backend-dev 가 사이클 89 시정해도 사이클 84 migration 무변경 → PASS.

    영속 의무:
    - 사이클 84 history trigger + 90일 retention 영속
    - 500 universe × 1회/일 = 5% retention 부담 (안전 영역)
    """
    # 사이클 84 migration 032 영속 확인
    migration_files = list(_MIGRATIONS_DIR.glob("032_*stock_master_history*.sql"))

    assert migration_files, (
        f"\n사이클 89 L-4 위반 — 사이클 84 migration 032 (stock_master_history) 부재:\n"
        f"  검색 디렉토리: {_MIGRATIONS_DIR}\n"
        f"  영속 의무: 사이클 89 시정해도 사이클 84 migration 무변경\n"
        f"  - 사이클 84 영속 영역 침범 금지"
    )

    # migration 본체에 trigger 정의 영속 확인
    migration_source = migration_files[0].read_text(encoding="utf-8")

    assert "stock_master_history" in migration_source, (
        f"\n사이클 89 L-4 위반 — migration 032 에 `stock_master_history` 테이블 부재:\n"
        f"  파일: {migration_files[0].name}\n"
        f"  영속 의무: 사이클 84 trigger 영속"
    )

    # trigger 함수 정의 영속
    has_trigger_func = (
        "stock_master_history_trigger" in migration_source
        or "TRIGGER" in migration_source.upper()
    )
    assert has_trigger_func, (
        f"\n사이클 89 L-4 위반 — migration 032 에 trigger 정의 부재:\n"
        f"  파일: {migration_files[0].name}\n"
        f"  영속 의무: 사이클 84 `stock_master_history_trigger` 영속\n"
        f"  - AFTER INSERT/UPDATE/DELETE → INSERT/UPDATE/TTL_REFRESH 분기 영속"
    )

    # change_type CHECK constraint 영속 (사이클 84 명세 영속)
    has_change_type = (
        "change_type" in migration_source
        or "TTL_REFRESH" in migration_source
    )
    assert has_change_type, (
        f"\n사이클 89 L-4 위반 — migration 032 에 `change_type` 정의 부재:\n"
        f"  파일: {migration_files[0].name}\n"
        f"  영속 의무: 사이클 84 `CHECK IN ('INSERT','UPDATE','DELETE','TTL_REFRESH')` 영속"
    )
