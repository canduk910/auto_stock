"""cycle455 — migration 053 `domestic_index_daily` + `src/db/domestic_index.py` 실 Postgres 왕복.

| # | 계약 |
|---|---|
| M1 | 가산형 — `CREATE TABLE/INDEX IF NOT EXISTS` 만 · 053 번호 하나 |
| M2 | 두 번 적용 오류 0 · PK `(index_code, bas_dd)` |
| M3 | `upsert_many` 멱등(같은 날짜 덮기) · `get_recent_closes` 오름차순·limit · `max_bas_dd` · `count` |
| M4 | `stock_master.get_market_map` = `{ticker: excg_dvsn_cd}` |

운영 DB 에는 실행하지 않는다 — 로컬 pg 하네스(docker) 또는 CI `DATABASE_URL_TEST` 만.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_ROOT = Path(__file__).resolve().parents[2]
_MIG = _ROOT / "supabase" / "migrations" / "053_domestic_index_daily.sql"


def _sql_code(text: str) -> str:
    return "\n".join(ln.split("--", 1)[0] for ln in text.splitlines())


def test_m1_migration_is_additive_only():
    code = _sql_code(_MIG.read_text(encoding="utf-8"))
    for kind, tail in re.findall(r"\bCREATE\s+(?:UNIQUE\s+)?(TABLE|INDEX)\b(.{0,40})", code, re.I | re.S):
        assert re.match(r"\s+IF\s+NOT\s+EXISTS\b", tail, re.I), f"CREATE {kind} 에 IF NOT EXISTS 가 없다"
    for kw in ("ALTER", "DROP", "UPDATE", "DELETE", "INSERT", "TRUNCATE", "GRANT", "REVOKE"):
        assert not re.search(rf"\b{kw}\b", code, re.I), f"053 에 {kw} — 가산형만"
    nums = sorted(int(p.name[:3]) for p in (_ROOT / "supabase" / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
    assert nums.count(53) == 1


async def test_m2_applies_twice_and_pk(pg_migrated):
    import asyncpg

    conn = await asyncpg.connect(pg_migrated)
    try:
        await conn.execute(_MIG.read_text(encoding="utf-8"))
        pk = [r["attname"] for r in await conn.fetch(
            """
            SELECT a.attname FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = 'domestic_index_daily'::regclass AND i.indisprimary
            ORDER BY array_position(i.indkey::int2[], a.attnum)
            """)]
        assert pk == ["index_code", "bas_dd"]
    finally:
        await conn.close()


async def test_m3_upsert_and_read_roundtrip(pg_pool):
    from src.db import domestic_index as di

    await pg_pool.execute("DELETE FROM domestic_index_daily")
    try:
        rows = [("20261010", 2500.5), ("20261013", 2510.0), ("20261014", 2520.0)]
        assert await di.upsert_many("0001", rows) == 3
        assert await di.upsert_many("0001", [("20261014", 2525.25)]) == 1     # 덮기
        assert await di.upsert_many("1001", [("20261014", 800.0)]) == 1
        assert await di.count("0001") == 3 and await di.count("1001") == 1
        assert await di.max_bas_dd("0001") == date(2026, 10, 14)
        got = await di.get_recent_closes("0001", limit=2)
        assert got == [(date(2026, 10, 13), 2510.0), (date(2026, 10, 14), 2525.25)]
        assert await di.max_bas_dd("9999") is None and await di.get_recent_closes("9999", limit=5) == []
    finally:
        await pg_pool.execute("DELETE FROM domestic_index_daily")


async def test_m4_get_market_map(pg_pool):
    from src.db import stock_master

    await pg_pool.execute("DELETE FROM stock_master WHERE ticker IN ('990455', '990456')")
    try:
        await pg_pool.execute(
            "INSERT INTO stock_master (ticker, name, excg_dvsn_cd, nxt_tradable) "
            "VALUES ('990455', 'a', '03', false), ('990456', 'b', '02', false)")
        m = await stock_master.get_market_map()
        assert m["990455"] == "03" and m["990456"] == "02"
    finally:
        await pg_pool.execute("DELETE FROM stock_master WHERE ticker IN ('990455', '990456')")
