"""RS 2단계 Red — migration 052 `candidate_score_snapshots` + 관찰 DB 함수 실 Postgres 왕복.

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase2.md` §B 「테이블」. 파일명 가정 =
`supabase/migrations/052_candidate_score_snapshots.sql`(🔴 병합 직전 main 마지막 번호 + 1 로 재확정 —
바뀌면 이 상수만 고친다).

| # | 계약 |
|---|---|
| M1 | 가산형 — `CREATE TABLE/INDEX IF NOT EXISTS` 만, `ALTER/DROP/UPDATE/DELETE/INSERT/GRANT` 0 (docker 없이) |
| M2 | 두 번 적용 오류 0 · PK `(target_date, strategy_id, ticker)` · 칸 타입 · 점수 칸 NULL 허용 · `computed_at` NOT NULL |
| M3 | `candidate_scores.upsert_scores` 왕복 — NULL 은 NULL 로, 같은 PK 재기록은 덮기 |
| M4 | `score_inputs.recent_closes_bulk` 왕복 — `bas_dd < before` · 최근 n봉 · 오래된→최신 |

운영 DB 에는 실행하지 않는다 — 로컬 pg 하네스(docker) 또는 CI `DATABASE_URL_TEST` 만.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_ROOT = Path(__file__).resolve().parents[2]
_MIG = _ROOT / "supabase" / "migrations" / "052_candidate_score_snapshots.sql"
_TABLE = "candidate_score_snapshots"
KST = timezone(timedelta(hours=9))

_TYPES = {
    "target_date": "date", "strategy_id": "text", "ticker": "text", "role": "text",
    "rs_raw": "double precision", "rs_pct": "integer", "sector_key": "text",
    "vs_sector": "double precision", "sector_pct": "integer", "in_sector_pct": "integer",
    "revision_breadth": "double precision", "target_median_change": "double precision",
    "opinion_brokers": "integer", "fin_quarter": "text", "op_income_q": "double precision",
    "op_income_q_yoy": "double precision", "op_turnaround": "boolean",
    "op_yoy_growth": "double precision", "revenue_yoy_growth": "double precision",
    "net_turnaround": "boolean", "roe": "double precision", "debt_ratio_latest": "double precision",
    "debt_ratio_down_years": "integer", "ttm_op_to_max_ratio": "double precision",
    "rs_population": "integer", "computed_at": "timestamp with time zone",
}
_NOT_NULL_ALLOWED = {"target_date", "strategy_id", "ticker", "role", "computed_at"}


def _sql_code(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return "\n".join(ln.split("--", 1)[0] for ln in text.splitlines())


def test_m1_migration_is_additive_only():
    assert _MIG.is_file(), f"{_MIG.relative_to(_ROOT)} 이 없다"
    code = _sql_code(_MIG.read_text(encoding="utf-8"))
    creates = re.findall(r"\bCREATE\s+(?:UNIQUE\s+)?(TABLE|INDEX)\b(.{0,40})", code, re.I | re.S)
    assert creates, "CREATE 가 없다"
    for kind, tail in creates:
        assert re.match(r"\s+IF\s+NOT\s+EXISTS\b", tail, re.I), f"CREATE {kind} 에 IF NOT EXISTS 가 없다"
    for kw in ("ALTER", "DROP", "UPDATE", "DELETE", "INSERT", "TRUNCATE", "GRANT", "REVOKE"):
        assert not re.search(rf"\b{kw}\b", code, re.I), f"052 에 {kw} — 가산형만"
    assert re.search(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{_TABLE}\b", code, re.I)
    assert re.search(r"PRIMARY\s+KEY\s*\(\s*target_date\s*,\s*strategy_id\s*,\s*ticker\s*\)", code, re.I)
    for col in _TYPES:
        assert re.search(rf"^\s*{col}\s", code, re.I | re.M), f"칸 {col} 누락"


def test_m1b_migration_number_is_next_after_051():
    nums = sorted(int(p.name[:3]) for p in (_ROOT / "supabase" / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
    assert nums.count(52) == 1, "052 번호가 하나여야 한다"


async def test_m2_applies_twice_pk_types_nullability(pg_migrated):
    import asyncpg

    conn = await asyncpg.connect(pg_migrated)
    try:
        await conn.execute(_MIG.read_text(encoding="utf-8"))  # 하네스가 이미 1회 — 두 번째
        pk = [r["attname"] for r in await conn.fetch(
            """
            SELECT a.attname FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = $1::regclass AND i.indisprimary
            ORDER BY array_position(i.indkey::int2[], a.attnum)
            """, _TABLE)]
        assert pk == ["target_date", "strategy_id", "ticker"]
        cols = {r["column_name"]: (r["data_type"], r["is_nullable"]) for r in await conn.fetch(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = $1",
            _TABLE)}
        assert set(cols) == set(_TYPES), set(cols) ^ set(_TYPES)
        for c, t in _TYPES.items():
            assert cols[c][0] == t, f"{c}: {cols[c][0]} != {t}"
            if c not in _NOT_NULL_ALLOWED:
                assert cols[c][1] == "YES", f"점수 칸 {c} 는 NULL 허용(모름 = NULL)"
        assert cols["computed_at"][1] == "NO"
    finally:
        await conn.close()


async def test_m3_upsert_scores_roundtrip_null_and_overwrite(pg_pool):
    from src.db import candidate_scores

    await pg_pool.execute(f"DELETE FROM {_TABLE}")
    try:
        d = date(2026, 10, 13)
        base = {c: None for c in _TYPES}
        base.update({"target_date": d, "strategy_id": "donchian_swing", "ticker": "005930",
                     "role": "candidate", "rs_raw": 0.25, "rs_pct": 70, "op_turnaround": True,
                     "rs_population": 1200, "computed_at": datetime(2026, 10, 13, 8, 5, tzinfo=KST)})
        assert await candidate_scores.upsert_scores([base]) == 1
        row = await pg_pool.fetchrow(f"SELECT * FROM {_TABLE} WHERE ticker = '005930'")
        assert row["rs_pct"] == 70 and row["op_turnaround"] is True
        assert row["roe"] is None and row["revision_breadth"] is None, "결측은 NULL 그대로"
        again = dict(base, rs_pct=80, role="held", rs_raw=None)
        assert await candidate_scores.upsert_scores([again]) == 1
        rows = await pg_pool.fetch(f"SELECT * FROM {_TABLE}")
        assert len(rows) == 1, "같은 PK 재기록 = 덮기(멱등)"
        assert rows[0]["rs_pct"] == 80 and rows[0]["role"] == "held" and rows[0]["rs_raw"] is None
    finally:
        await pg_pool.execute(f"DELETE FROM {_TABLE}")


async def test_m4_recent_closes_bulk_roundtrip(clean_stock_master_daily):
    from src.db import score_inputs

    pg = clean_stock_master_daily
    before = date(2026, 10, 13)
    days = [before - timedelta(days=i) for i in range(0, 8)]  # before 당일 포함 8일
    for i, d in enumerate(sorted(days)):
        await pg.execute(
            "INSERT INTO stock_master_daily (ticker, bas_dd, close_price) VALUES ($1, $2, $3)",
            "005930", d, 1000 + i)
    await pg.execute(
        "INSERT INTO stock_master_daily (ticker, bas_dd, close_price) VALUES ($1, $2, $3)",
        "000660", before - timedelta(days=1), 500)
    out = await score_inputs.recent_closes_bulk(before, n=3)
    # before 당일(1007) 제외 · 최근 3봉 = 1004, 1005, 1006 (오래된→최신)
    assert out["005930"] == [1004.0, 1005.0, 1006.0]
    assert out["000660"] == [500.0]
