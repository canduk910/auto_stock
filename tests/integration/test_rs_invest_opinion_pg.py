"""RS 1단계 Red — migration 051 `invest_opinion_history`·`estimate_perform_snapshot` 실 Postgres 확인.

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase1.md` §D. 파일명 가정 =
`supabase/migrations/051_invest_opinion.sql`(🔴 병합 직전 main 마지막 번호 + 1 로 재확정 — 바뀌면
이 상수만 고친다).

| # | 계약 |
|---|---|
| M1 | 가산형 — `CREATE TABLE/INDEX IF NOT EXISTS` 만, `ALTER/DROP/UPDATE/DELETE/INSERT/GRANT` 0 (docker 없이) |
| M2 | 두 번 적용 오류 0 · 두 표의 PK 가 명세대로 · PK 중복 거부 (실 Postgres) |

운영 DB 에는 실행하지 않는다 — 로컬 pg 하네스(docker) 또는 CI `DATABASE_URL_TEST` 만.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_ROOT = Path(__file__).resolve().parents[2]
_MIG = _ROOT / "supabase" / "migrations" / "051_invest_opinion.sql"
_TABLES = ("invest_opinion_history", "estimate_perform_snapshot")


def _sql_code(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return "\n".join(ln.split("--", 1)[0] for ln in text.splitlines())


def test_m1_migration_is_additive_only():
    assert _MIG.is_file(), "supabase/migrations/051_invest_opinion.sql 이 없다"
    code = _sql_code(_MIG.read_text(encoding="utf-8"))
    creates = re.findall(r"\bCREATE\s+(?:UNIQUE\s+)?(TABLE|INDEX)\b(.{0,40})", code, re.I | re.S)
    assert creates, "CREATE 가 없다"
    for kind, tail in creates:
        assert re.match(r"\s+IF\s+NOT\s+EXISTS\b", tail, re.I), f"CREATE {kind} 에 IF NOT EXISTS 가 없다"
    for kw in ("ALTER", "DROP", "UPDATE", "DELETE", "INSERT", "TRUNCATE", "GRANT", "REVOKE"):
        assert not re.search(rf"\b{kw}\b", code, re.I), f"051 에 {kw} — 가산형만"
    for t in _TABLES:
        assert re.search(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{t}\b", code, re.I), t


async def test_m2_migration_applies_twice_and_primary_keys_match_spec(pg_migrated):
    import asyncpg

    conn = await asyncpg.connect(pg_migrated)
    try:
        await conn.execute(_MIG.read_text(encoding="utf-8"))  # 하네스가 이미 1회 — 두 번째
        for t in _TABLES:
            await conn.execute(f"DELETE FROM {t}")
        pk = {}
        for t in _TABLES:
            cols = await conn.fetch(
                """
                SELECT a.attname FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = $1::regclass AND i.indisprimary
                ORDER BY array_position(i.indkey::int2[], a.attnum)
                """, t)
            pk[t] = [r["attname"] for r in cols]
        assert pk == {
            "invest_opinion_history": ["ticker", "bsop_date", "mbcr_name"],
            "estimate_perform_snapshot": ["ticker", "snapshot_month"],
        }
        ins = ("INSERT INTO invest_opinion_history (ticker, bsop_date, mbcr_name, hts_goal_prc, raw)"
               " VALUES ($1, $2, $3, $4, $5::jsonb)")
        d = date(2026, 10, 13)
        await conn.execute(ins, "005930", d, "SK", 105000, json.dumps({"k": 1}))
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(ins, "005930", d, "SK", 110000, json.dumps({"k": 2}))
        for t in _TABLES:
            await conn.execute(f"DELETE FROM {t}")
    finally:
        await conn.close()
