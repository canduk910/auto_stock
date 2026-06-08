"""사이클 84 Red — M-1 (HIGH): migration 032 SQL 정적 검증.

Green 단계 backend-dev 가 `supabase/migrations/032_stock_master_history.sql` 작성 의무.

검증 영역:
- 파일 존재
- 테이블 `stock_master_history` CREATE 정의
- 6 컬럼 정의 (id, ticker, change_type, before_raw, after_raw, changed_at)
- change_type CHECK IN ('INSERT','UPDATE','DELETE','TTL_REFRESH')
- 인덱스 2종 (idx_smh_ticker_changed_at + idx_smh_changed_at)
- trigger 함수 + trigger 정의

위험 등급 HIGH (DB 스키마 결함 영구 차단).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "supabase" / "migrations" / "032_stock_master_history.sql"
)


def _sql() -> str:
    assert MIGRATION_PATH.exists(), (
        f"migration 032 미작성: {MIGRATION_PATH} 부재 — backend-dev Green 단계 작성 의무"
    )
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_M1_migration_032_file_exists():
    """M-1-A: 파일 존재."""
    assert MIGRATION_PATH.exists(), f"migration 032 SQL 파일 부재: {MIGRATION_PATH}"


def test_M1_table_stock_master_history_defined():
    """M-1-B: `stock_master_history` 테이블 정의 존재."""
    sql = _sql().lower()
    assert "create table" in sql and "stock_master_history" in sql, (
        "CREATE TABLE stock_master_history 정의 부재"
    )


def test_M1_six_columns_defined():
    """M-1-C: 6 컬럼 정의 — id / ticker / change_type / before_raw / after_raw / changed_at."""
    sql = _sql().lower()
    required = ["id", "ticker", "change_type", "before_raw", "after_raw", "changed_at"]
    missing = [c for c in required if c not in sql]
    assert not missing, f"필수 컬럼 누락: {missing}"


def test_M1_change_type_check_constraint():
    """M-1-D: change_type CHECK IN 4 ENUM 명시."""
    sql = _sql().upper()
    for enum_val in ("'INSERT'", "'UPDATE'", "'DELETE'", "'TTL_REFRESH'"):
        assert enum_val in sql, f"change_type ENUM {enum_val} CHECK 제약 누락"


def test_M1_two_indexes_defined():
    """M-1-E: 2 인덱스 정의 (ticker+changed_at / changed_at)."""
    sql = _sql().lower()
    assert "create index" in sql, "CREATE INDEX 정의 0건"
    # 최소 2회 등장
    assert sql.count("create index") >= 2, (
        f"인덱스 2개 의무 (현재 {sql.count('create index')}개)"
    )


def test_M1_trigger_function_and_trigger_defined():
    """M-1-F: trigger 함수 + trigger 정의 존재."""
    sql = _sql().lower()
    assert "create" in sql and "function" in sql and "stock_master_history_trigger" in sql, (
        "trigger 함수 stock_master_history_trigger() 정의 부재"
    )
    assert "create trigger" in sql, "CREATE TRIGGER 정의 부재"
    assert "after insert or update or delete" in sql or (
        "after insert" in sql and "after update" in sql and "after delete" in sql
    ), "trigger AFTER INSERT/UPDATE/DELETE 3종 정의 부재"
