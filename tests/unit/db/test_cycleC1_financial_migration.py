"""사이클 C1 — migration 041_stock_master_financial.sql 스키마 Red 가드.

Red 명세: `_workspace/red/cycleC1_financial_infra.md`

퀀트 재무필터 (마법공식 + F-Score-7) 데이터 계층. `stock_master_daily` 일봉형
별도 테이블 100% 미러. PK `(ticker, stac_yymm, div_cls)` 시계열 + 5 TR 정규화 컬럼
+ raw JSONB (사이클 81 G-AST1) + refreshed_at.

가드:
- 파일 존재 (034/039 답습, IF NOT EXISTS idempotent)
- CREATE TABLE IF NOT EXISTS stock_master_financial
- PK 3키 (ticker, stac_yymm, div_cls)
- 5 TR 정규화 컬럼 18종 전수 존재
- raw JSONB + refreshed_at TIMESTAMPTZ
- 인덱스 ix_smf_ticker_div
- idempotent (IF NOT EXISTS)

이 파일은 production migration 미작성 상태에서 전부 FAIL (Red).
매매 안전성 무영향 (scanner 매수 진입 전, 사이클 38).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / ".."
    / "supabase"
    / "migrations"
    / "041_stock_master_financial.sql"
).resolve()


def _sql() -> str:
    assert _MIGRATION.exists(), (
        f"migration 041 파일 부재: {_MIGRATION} — production 미작성 (Red). "
        f"034/039 답습 (IF NOT EXISTS idempotent)."
    )
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_lower() -> str:
    # SQL 키워드 대소문자/공백 무관 매칭용 (공백 정규화)
    return re.sub(r"\s+", " ", _sql().lower())


# ---------------------------------------------------------------------------
# G-C1-MIG-1 — 파일 존재
# ---------------------------------------------------------------------------
def test_migration_file_exists():
    """041 migration 파일 존재 (034/039 답습)."""
    assert _MIGRATION.exists(), f"migration 041 부재: {_MIGRATION}"


# ---------------------------------------------------------------------------
# G-C1-MIG-2 — CREATE TABLE IF NOT EXISTS stock_master_financial
# ---------------------------------------------------------------------------
def test_create_table_idempotent():
    """CREATE TABLE IF NOT EXISTS stock_master_financial (034/039 idempotent 답습)."""
    sql = _sql_lower()
    assert "create table if not exists stock_master_financial" in sql, (
        "CREATE TABLE IF NOT EXISTS stock_master_financial 부재 — idempotent 재적용 안전 의무."
    )


# ---------------------------------------------------------------------------
# G-C1-MIG-3 — PK 3키 (ticker, stac_yymm, div_cls)
# ---------------------------------------------------------------------------
def test_primary_key_three_columns():
    """PRIMARY KEY (ticker, stac_yymm, div_cls) 복합 3키."""
    sql = _sql_lower()
    # PRIMARY KEY (ticker, stac_yymm, div_cls) — 공백 무관 매칭
    m = re.search(r"primary key\s*\(([^)]*)\)", sql)
    assert m is not None, "PRIMARY KEY 선언 부재"
    pk_cols = {c.strip() for c in m.group(1).split(",")}
    assert pk_cols == {"ticker", "stac_yymm", "div_cls"}, (
        f"PK 3키 불일치: {pk_cols} != {{ticker, stac_yymm, div_cls}} — "
        f"upsert on_conflict 정합 의무."
    )


# ---------------------------------------------------------------------------
# G-C1-MIG-4 — 5 TR 정규화 컬럼 18종 전수
# ---------------------------------------------------------------------------
def test_all_five_tr_normalized_columns_present():
    """손익 5 + 대차 7 + 수익성 2 + 안정성 2 + 기타 2 = 18 정규화 컬럼 전수 존재."""
    sql = _sql_lower()
    required_columns = [
        # 손익 FHKST66430200
        "sale_account", "sale_totl_prfi", "bsop_prti", "thtr_ntin", "depr_cost",
        # 대차 FHKST66430100
        "cras", "fxas", "total_aset", "flow_lblt", "total_lblt", "total_cptl", "cpfn",
        # 수익성 FHKST66430400
        "cptl_ntin_rate", "sale_totl_rate",
        # 안정성 FHKST66430600
        "lblt_rate", "crnt_rate",
        # 기타 FHKST66430500
        "ebitda", "ev_ebitda",
    ]
    missing = [c for c in required_columns if c not in sql]
    assert not missing, (
        f"정규화 컬럼 부재: {missing} — 5 TR 필드 전수 적재 의무 (F-Score-7 + 마법공식 산식)."
    )


# ---------------------------------------------------------------------------
# G-C1-MIG-5 — raw JSONB + refreshed_at (사이클 81 G-AST1 + 사이클 68 KST)
# ---------------------------------------------------------------------------
def test_raw_jsonb_and_refreshed_at():
    """raw JSONB NOT NULL DEFAULT '{}' (사이클 81) + refreshed_at TIMESTAMPTZ."""
    sql = _sql_lower()
    assert "raw jsonb" in sql, "raw JSONB 컬럼 부재 — 사이클 81 G-AST1 원본 보존 의무."
    assert "refreshed_at timestamptz" in sql, (
        "refreshed_at TIMESTAMPTZ 부재 — 신선도 게이트 (백필/증분) 의무."
    )


# ---------------------------------------------------------------------------
# G-C1-MIG-6 — 인덱스 ix_smf_ticker_div (idempotent)
# ---------------------------------------------------------------------------
def test_index_present_and_idempotent():
    """CREATE INDEX IF NOT EXISTS ix_smf_ticker_div ON (ticker, div_cls, stac_yymm DESC)."""
    sql = _sql_lower()
    assert "create index if not exists ix_smf_ticker_div" in sql, (
        "인덱스 ix_smf_ticker_div (IF NOT EXISTS) 부재 — 시계열 조회 최적화 + idempotent."
    )
    # (ticker, div_cls, stac_yymm DESC) 순서 정합
    m = re.search(r"ix_smf_ticker_div\s+on\s+stock_master_financial\s*\(([^)]*)\)", sql)
    assert m is not None, "인덱스 컬럼 선언 부재"
    idx_body = m.group(1)
    assert "ticker" in idx_body and "div_cls" in idx_body and "stac_yymm" in idx_body, (
        f"인덱스 컬럼 (ticker, div_cls, stac_yymm DESC) 정합 부재: {idx_body!r}"
    )


# ---------------------------------------------------------------------------
# G-C1-MIG-7 — idempotent (전체 create 문 IF NOT EXISTS)
# ---------------------------------------------------------------------------
def test_all_create_statements_idempotent():
    """모든 CREATE TABLE / CREATE INDEX 가 IF NOT EXISTS (034/039 답습, 재적용 안전)."""
    sql = _sql_lower()
    for m in re.finditer(r"create\s+(table|index)\s+(if not exists\s+)?", sql):
        assert m.group(2) is not None, (
            f"CREATE {m.group(1).upper()} 에 IF NOT EXISTS 누락 — "
            f"deploy migration 자동 적용 재적용 안전 위반 (034/039 답습 의무)."
        )
