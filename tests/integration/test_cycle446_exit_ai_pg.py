"""cycle446 Red — migration 050 `exit_ai_evaluations`/`exit_ai_runs` + 워커 전용 DB 역할
(`llm_worker/ops/role.sql`) 실 Postgres 검증.

패턴 = `tests/integration/test_cycle412_trade_journal_pg.py`(journal_worker 선례)와 동형.

| # | 계약 |
|---|---|
| M1 | 050 은 가산형 — `CREATE TABLE/INDEX IF NOT EXISTS` 만, `ALTER/DROP/UPDATE/DELETE/INSERT/GRANT` 0 |
| M2 | 두 번 적용해도 오류 0 |
| M3 | `UNIQUE(bar_date, strategy_id, ticker, buy_date, buy_order_no)` |
| R1 | `llm_worker/ops/role.sql` — 마이그레이션 디렉터리 밖 · 비밀번호는 psql 변수 `:'llm_pw'` 하나 |
| R2 | 두 번 실행해도 오류 0 · 로그인 가능 · 슈퍼유저/역할생성/DB생성/RLS우회 아님 |
| R3 | 역할 수준 `statement_timeout=5s` · `lock_timeout=1s` · `idle_in_transaction_session_timeout=5s` |
| R4 | `stock_master_daily`·`trade_history`·`trade_journal_orders` = SELECT 만 |
| R5 | `exit_ai_evaluations`·`exit_ai_runs` = SELECT·INSERT·UPDATE, DELETE 거부 |
| R6 | `positions`·`system_config`·`strategy_config`·`kis_quote_accounts`·`system_logs` 거부 |

운영 DB 에는 실행하지 않는다 — 로컬 pg 하네스(docker) 또는 CI `DATABASE_URL_TEST` 만.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_ROOT = Path(__file__).resolve().parents[2]
_MIG = _ROOT / "supabase" / "migrations" / "050_exit_ai_evaluations.sql"
_ROLE = _ROOT / "llm_worker" / "ops" / "role.sql"
_PW = "cycle446-test-pw"
_TABLES = ("exit_ai_evaluations", "exit_ai_runs")


def _sql_code(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return "\n".join(ln.split("--", 1)[0] for ln in text.splitlines())


def _role_sql() -> str:
    text = _ROLE.read_text(encoding="utf-8")
    return text.replace(":'llm_pw'", f"'{_PW}'")


def _as_role(dsn: str) -> str:
    u = urlsplit(dsn)
    host = u.hostname + (f":{u.port}" if u.port else "")
    return urlunsplit((u.scheme, f"llm_worker:{_PW}@{host}", u.path, u.query, u.fragment))


# ── 정적(docker 없이) ─────────────────────────────────────────────────────────

def test_m1_migration_is_additive_only():
    assert _MIG.is_file(), "supabase/migrations/050_exit_ai_evaluations.sql 이 없다"
    code = _sql_code(_MIG.read_text(encoding="utf-8"))
    creates = re.findall(r"\bCREATE\s+(?:UNIQUE\s+)?(TABLE|INDEX)\b(.{0,40})", code, re.I | re.S)
    assert creates, "CREATE 가 없다"
    for kind, tail in creates:
        assert re.match(r"\s+IF\s+NOT\s+EXISTS\b", tail, re.I), f"CREATE {kind} 에 IF NOT EXISTS 가 없다: {tail!r}"
    for kw in ("ALTER", "DROP", "UPDATE", "DELETE", "INSERT", "TRUNCATE", "GRANT", "REVOKE"):
        assert not re.search(rf"\b{kw}\b", code, re.I), f"050 에 {kw} — 가산형만"
    for t in _TABLES:
        assert re.search(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{t}\b", code, re.I), t


def test_r1_role_script_is_outside_migrations_and_has_no_literal_password():
    assert _ROLE.is_file(), "llm_worker/ops/role.sql 이 없다"
    assert not list((_ROOT / "supabase" / "migrations").glob("*role*")), "역할은 마이그레이션이 아니다"
    text = _ROLE.read_text(encoding="utf-8")
    code = _sql_code(text)
    assert code.count(":'llm_pw'") == 1, "비밀번호는 psql 변수 :'llm_pw' 한 곳"
    assert not re.search(r"PASSWORD\s+'", code, re.I), "리터럴 비밀번호 금지"
    assert not re.search(r"^\s*\\", code, re.M), "psql 메타명령 금지(테스트·운영 모두 같은 SQL)"
    assert re.search(r"\bllm_worker\b", code)
    assert "openssl rand -hex" in text


# ── 실 Postgres ───────────────────────────────────────────────────────────────

@pytest.fixture
async def admin(pg_migrated):
    import asyncpg

    conn = await asyncpg.connect(pg_migrated)
    try:
        for t in _TABLES:
            await conn.execute(f"DELETE FROM {t}")
        yield conn
        for t in _TABLES:
            await conn.execute(f"DELETE FROM {t}")
    finally:
        await conn.close()


@pytest.fixture
async def role_conn(admin, pg_migrated):
    import asyncpg

    await admin.execute(_role_sql())
    conn = await asyncpg.connect(_as_role(pg_migrated))
    try:
        yield conn
    finally:
        await conn.close()
        await admin.execute("DROP OWNED BY llm_worker")
        await admin.execute("DROP ROLE IF EXISTS llm_worker")


async def test_m2_migration_applies_twice(admin):
    await admin.execute(_MIG.read_text(encoding="utf-8"))
    await admin.execute(_MIG.read_text(encoding="utf-8"))


_INS = ("INSERT INTO exit_ai_evaluations (bar_date, act_date, strategy_id, ticker, buy_date, result, mode)"
        " VALUES ($1,$2,$3,$4,$5,'ok','shadow')")


async def test_m3_unique_rejects_duplicate(admin):
    import asyncpg

    d = date(2026, 10, 13)
    await admin.execute(_INS, d, d, "kojiro", "005930", d)
    with pytest.raises(asyncpg.UniqueViolationError):
        await admin.execute(_INS, d, d, "kojiro", "005930", d)
    assert await admin.fetchval("SELECT count(*) FROM exit_ai_evaluations") == 1


async def test_r2_role_script_runs_twice_and_role_is_minimal(admin, role_conn):
    await admin.execute(_role_sql())  # 두 번째 실행
    r = await admin.fetchrow("SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin"
                             " FROM pg_roles WHERE rolname='llm_worker'")
    assert dict(r) == {"rolsuper": False, "rolcreaterole": False, "rolcreatedb": False,
                       "rolbypassrls": False, "rolcanlogin": True}
    assert await role_conn.fetchval("SELECT current_user") == "llm_worker"


@pytest.mark.parametrize("name,value", [("statement_timeout", "5s"), ("lock_timeout", "1s"),
                                        ("idle_in_transaction_session_timeout", "5s")])
async def test_r3_role_level_timeouts(role_conn, name, value):
    assert await role_conn.fetchval(f"SHOW {name}") == value


async def test_r4_read_only_tables(role_conn):
    import asyncpg

    await role_conn.fetch("SELECT ticker, bas_dd FROM stock_master_daily LIMIT 1")
    await role_conn.fetch("SELECT id, order_no, strategy, status FROM trade_history LIMIT 1")
    await role_conn.fetch("SELECT id, order_no, side FROM trade_journal_orders LIMIT 1")
    for sql in ("UPDATE trade_history SET status = status", "DELETE FROM trade_history",
                "UPDATE stock_master_daily SET close_price = close_price",
                "UPDATE trade_journal_orders SET order_division = order_division"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await role_conn.execute(sql)


async def test_r5_own_tables_select_insert_update_but_no_delete(role_conn):
    import asyncpg

    d = date(2026, 10, 13)
    await role_conn.execute(_INS, d, d, "kojiro", "005930", d)
    await role_conn.execute("UPDATE exit_ai_evaluations SET result='failed' WHERE ticker='005930'")
    await role_conn.execute("INSERT INTO exit_ai_runs (run_date, status) VALUES ($1, 'done')", d)
    await role_conn.execute("UPDATE exit_ai_runs SET n_ok = 1 WHERE run_date = $1", d)
    await role_conn.fetch("SELECT * FROM exit_ai_evaluations")
    for t in _TABLES:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await role_conn.execute(f"DELETE FROM {t}")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM positions",
    "SELECT params FROM strategy_config",
    "SELECT value FROM system_config",
    "SELECT app_key FROM kis_quote_accounts",
    "INSERT INTO system_logs (log_level, message) VALUES ('INFO','x')",
])
async def test_r6_other_tables_denied(role_conn, sql):
    import asyncpg

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await role_conn.execute(sql) if sql.strip().upper().startswith("INSERT") else await role_conn.fetch(sql)
