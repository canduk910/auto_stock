"""cycle412 Red — migration 047 `trade_journal_*` 와 워커 전용 DB 역할(사용자 결정 E1c · D2) 실 Postgres 검증.

정본 = 계획서 4절 저장 구조 + 관찰자안 6절(칸 추가) · 5절 ①(전용 역할) · 5절 ④(잠금 대기열).
계약 문서 = `_workspace/red/cycle412/journal_contract.md` 1절.

| # | 계약 |
|---|---|
| M1 | 047 은 가산형 — `CREATE TABLE/INDEX IF NOT EXISTS` 만, `ALTER/DROP/UPDATE/DELETE/INSERT/GRANT` 0 (정적, docker 없이도 돈다) |
| M2 | 두 번 적용해도 오류 0 |
| M3 | 네 표의 칸·형식·NULL 허용이 계약과 같다 |
| M4 | `UNIQUE(order_date, order_no, side)` + `ON CONFLICT DO NOTHING` = 처음 값 유지 · 주문구분은 NULL 일 때만 채움 |
| M5 | 커서 `ON CONFLICT (name) DO UPDATE` · 메모 `anchor_trade_id` UNIQUE · 손절선 인덱스 `(strategy, ticker, observed_at)` |
| R1 | `journal_worker/ops/role.sql` — 마이그레이션 디렉터리 밖 · 비밀번호는 psql 변수 `:'journal_pw'` 하나 · 메타명령 0 (정적) |
| R2 | 두 번 실행해도 오류 0 · 로그인 가능 · 슈퍼유저/역할생성/DB생성/RLS우회 아님 |
| R3 | 역할 수준 `statement_timeout=5s` · `lock_timeout=1s` · `idle_in_transaction_session_timeout=5s` |
| R4 | `trade_history` = SELECT 만(UPDATE·INSERT·`SELECT … FOR UPDATE` 거부) · `llm_buy_evaluations` SELECT |
| R5 | `trade_journal_*` = SELECT·INSERT·UPDATE, DELETE 거부 |
| R6 | `kis_quote_accounts`(앱키 평문)·`strategy_config`·`positions`·`system_config`·`system_logs`·`pending_next_day_clear` 거부 |

운영 DB 에는 실행하지 않는다 — 로컬 pg 하네스(docker) 또는 CI `DATABASE_URL_TEST` 만.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

KST = timezone(timedelta(hours=9))
_ROOT = Path(__file__).resolve().parents[2]
_MIG = _ROOT / "supabase" / "migrations" / "047_trade_journal.sql"
_ROLE = _ROOT / "journal_worker" / "ops" / "role.sql"
_PW = "cycle412-test-pw"
_TABLES = ("trade_journal_orders", "trade_journal_stops", "trade_journal_notes", "trade_journal_cursor")


def _sql_code(text: str) -> str:
    """주석을 뺀 SQL(정적 검사용)."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return "\n".join(ln.split("--", 1)[0] for ln in text.splitlines())


def _role_sql() -> str:
    text = _ROLE.read_text(encoding="utf-8")
    return text.replace(":'journal_pw'", f"'{_PW}'")


def _as_role(dsn: str) -> str:
    u = urlsplit(dsn)
    host = u.hostname + (f":{u.port}" if u.port else "")
    return urlunsplit((u.scheme, f"journal_worker:{_PW}@{host}", u.path, u.query, u.fragment))


# ── 정적(docker 없이) ─────────────────────────────────────────────────────────

def test_m1_migration_is_additive_only():
    assert _MIG.is_file(), "supabase/migrations/047_trade_journal.sql 이 없다"
    code = _sql_code(_MIG.read_text(encoding="utf-8"))
    creates = re.findall(r"\bCREATE\s+(?:UNIQUE\s+)?(TABLE|INDEX)\b(.{0,40})", code, re.I | re.S)
    assert creates, "CREATE 가 없다"
    for kind, tail in creates:
        assert re.match(r"\s+IF\s+NOT\s+EXISTS\b", tail, re.I), f"CREATE {kind} 에 IF NOT EXISTS 가 없다: {tail!r}"
    for kw in ("ALTER", "DROP", "UPDATE", "DELETE", "INSERT", "TRUNCATE", "GRANT", "REVOKE"):
        assert not re.search(rf"\b{kw}\b", code, re.I), f"047 에 {kw} — 가산형만"
    for t in _TABLES:
        assert re.search(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{t}\b", code, re.I), t


def test_r1_role_script_is_outside_migrations_and_has_no_literal_password():
    assert _ROLE.is_file(), "journal_worker/ops/role.sql 이 없다"
    assert not list((_ROOT / "supabase" / "migrations").glob("*role*")), "역할은 마이그레이션이 아니다"
    text = _ROLE.read_text(encoding="utf-8")
    code = _sql_code(text)
    assert code.count(":'journal_pw'") == 1, "비밀번호는 psql 변수 :'journal_pw' 한 곳"
    assert not re.search(r"PASSWORD\s+'", code, re.I), "리터럴 비밀번호 금지"
    assert not re.search(r"^\s*\\", code, re.M), "psql 메타명령 금지(테스트·운영 모두 같은 SQL)"
    assert re.search(r"\bjournal_worker\b", code)


# ── 실 Postgres ───────────────────────────────────────────────────────────────

@pytest.fixture
async def admin(pg_migrated):
    import asyncpg

    conn = await asyncpg.connect(pg_migrated)
    try:
        await conn.execute(_MIG.read_text(encoding="utf-8"))
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
        await admin.execute("DROP OWNED BY journal_worker")
        await admin.execute("DROP ROLE IF EXISTS journal_worker")


async def test_m2_migration_applies_twice(admin):
    await admin.execute(_MIG.read_text(encoding="utf-8"))
    await admin.execute(_MIG.read_text(encoding="utf-8"))


_COLS = {
    "trade_journal_orders": {
        "id": ("bigint", "NO"), "order_date": ("date", "NO"), "order_no": ("text", "NO"),
        "side": ("text", "NO"), "strategy": ("text", "NO"), "ticker": ("text", "NO"),
        "source": ("text", "NO"), "reason_code": ("text", "YES"), "reason_sub": ("text", "YES"),
        "judge_price": ("integer", "YES"), "order_price": ("integer", "YES"),
        "order_division": ("text", "YES"), "exchange": ("text", "YES"), "parent_order_no": ("text", "YES"),
        "fired_line": ("integer", "YES"), "effective_line": ("integer", "YES"), "signal": ("jsonb", "YES"),
        "params": ("jsonb", "YES"), "noted_at": ("timestamp with time zone", "NO"),
    },
    "trade_journal_stops": {
        "id": ("bigint", "NO"), "strategy": ("text", "NO"), "ticker": ("text", "NO"),
        "buy_date": ("date", "YES"), "pos_order_no": ("text", "YES"),
        "observed_at": ("timestamp with time zone", "NO"), "event": ("text", "NO"),
        "stop_price": ("integer", "YES"), "stop_kind": ("text", "YES"), "target_price": ("integer", "YES"),
        "target_hit": ("boolean", "YES"), "arm_price": ("integer", "YES"), "inputs": ("jsonb", "YES"),
    },
    "trade_journal_notes": {
        "id": ("bigint", "NO"), "anchor_trade_id": ("uuid", "NO"), "strategy": ("text", "YES"),
        "ticker": ("text", "YES"), "buy_date": ("date", "YES"), "body": ("text", "NO"),
        "created_at": ("timestamp with time zone", "NO"), "updated_at": ("timestamp with time zone", "NO"),
    },
    "trade_journal_cursor": {
        "name": ("text", "NO"), "file_name": ("text", "NO"), "inode": ("bigint", "NO"),
        "byte_offset": ("bigint", "NO"), "updated_at": ("timestamp with time zone", "NO"),
    },
}


@pytest.mark.parametrize("table", sorted(_COLS))
async def test_m3_columns(admin, table):
    rows = await admin.fetch(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name=$1",
        table)
    got = {r["column_name"]: (r["data_type"], r["is_nullable"]) for r in rows}
    assert got == _COLS[table]


_NOW = datetime(2026, 10, 13, 10, 0, 10, tzinfo=KST)
_INS = ("INSERT INTO trade_journal_orders (order_date, order_no, side, strategy, ticker, source, reason_code,"
        " order_division, noted_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)"
        " ON CONFLICT (order_date, order_no, side) DO NOTHING")


async def test_m4_unique_keeps_first_and_fills_division_only_when_null(admin):
    d = date(2026, 10, 13)
    await admin.execute(_INS, d, "0000300100", "SELL", "kojiro", "005930", "log_harvest", "STOP_LOSS", None, _NOW)
    await admin.execute(_INS, d, "0000300100", "SELL", "kojiro", "005930", "log_harvest", "FORCE_CLEAR", "01", _NOW)
    await admin.execute(_INS, d, "0000300100", "BUY", "kojiro", "005930", "log_harvest", "ENTRY", "01", _NOW)
    await admin.execute(_INS, date(2026, 10, 14), "0000300100", "SELL", "kojiro", "005930", "log_harvest",
                        "STOP_LOSS", None, _NOW)
    assert await admin.fetchval("SELECT count(*) FROM trade_journal_orders") == 3
    row = await admin.fetchrow("SELECT reason_code, order_division FROM trade_journal_orders"
                               " WHERE order_date=$1 AND order_no=$2 AND side='SELL'", d, "0000300100")
    assert row["reason_code"] == "STOP_LOSS" and row["order_division"] is None
    upd = ("UPDATE trade_journal_orders SET order_division=$4 WHERE order_date=$1 AND order_no=$2 AND side=$3"
           " AND order_division IS NULL")
    await admin.execute(upd, d, "0000300100", "SELL", "01")
    await admin.execute(upd, d, "0000300100", "SELL", "44")
    assert await admin.fetchval("SELECT order_division FROM trade_journal_orders WHERE order_date=$1"
                                " AND order_no=$2 AND side='SELL'", d, "0000300100") == "01"


async def test_m5_cursor_upsert_notes_unique_stops_index(admin):
    up = ("INSERT INTO trade_journal_cursor (name, file_name, inode, byte_offset) VALUES ('main',$1,$2,$3)"
          " ON CONFLICT (name) DO UPDATE SET file_name=EXCLUDED.file_name, inode=EXCLUDED.inode,"
          " byte_offset=EXCLUDED.byte_offset, updated_at=now()")
    await admin.execute(up, "auto_stock.log", 7, 10)
    await admin.execute(up, "auto_stock.log", 8, 20)
    rows = await admin.fetch("SELECT inode, byte_offset FROM trade_journal_cursor")
    assert [(r["inode"], r["byte_offset"]) for r in rows] == [(8, 20)]

    import uuid

    import asyncpg

    a = uuid.uuid4()
    await admin.execute("INSERT INTO trade_journal_notes (anchor_trade_id, body) VALUES ($1, 'x')", a)
    with pytest.raises(asyncpg.UniqueViolationError):
        await admin.execute("INSERT INTO trade_journal_notes (anchor_trade_id, body) VALUES ($1, 'y')", a)

    defs = [r["indexdef"] for r in await admin.fetch(
        "SELECT indexdef FROM pg_indexes WHERE tablename='trade_journal_stops'")]
    assert any(re.search(r"\(strategy, ticker, observed_at\)", d) for d in defs), defs


async def test_r2_role_script_runs_twice_and_role_is_minimal(admin, role_conn):
    await admin.execute(_role_sql())  # 두 번째 실행
    r = await admin.fetchrow("SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin"
                             " FROM pg_roles WHERE rolname='journal_worker'")
    assert dict(r) == {"rolsuper": False, "rolcreaterole": False, "rolcreatedb": False,
                       "rolbypassrls": False, "rolcanlogin": True}
    assert await role_conn.fetchval("SELECT current_user") == "journal_worker"


@pytest.mark.parametrize("name,value", [("statement_timeout", "5s"), ("lock_timeout", "1s"),
                                        ("idle_in_transaction_session_timeout", "5s")])
async def test_r3_role_level_timeouts(role_conn, name, value):
    assert await role_conn.fetchval(f"SHOW {name}") == value


async def test_r4_trade_history_is_select_only(role_conn):
    import asyncpg

    await role_conn.fetch("SELECT id, order_no, strategy, status FROM trade_history LIMIT 1")
    await role_conn.fetch("SELECT 1 FROM llm_buy_evaluations LIMIT 1")
    for sql in ("UPDATE trade_history SET status = status",
                "SELECT 1 FROM trade_history FOR UPDATE",
                "INSERT INTO trade_history (ticker, trade_type, price, quantity, status)"
                " VALUES ('005930','BUY',1,1,'PENDING')",
                "DELETE FROM trade_history"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await role_conn.execute(sql)


async def test_r5_journal_tables_select_insert_update_but_no_delete(role_conn):
    import asyncpg

    d = date(2026, 10, 13)
    await role_conn.execute(_INS, d, "0000300900", "SELL", "kojiro", "005930", "log_harvest", "STOP_LOSS",
                            None, _NOW)
    await role_conn.execute("UPDATE trade_journal_orders SET order_division='01' WHERE order_no='0000300900'"
                            " AND order_division IS NULL")
    await role_conn.execute("INSERT INTO trade_journal_stops (strategy, ticker, observed_at, event)"
                            " VALUES ('kojiro','005930',now(),'first')")
    await role_conn.execute("INSERT INTO trade_journal_cursor (name, file_name, inode, byte_offset)"
                            " VALUES ('main','auto_stock.log',1,0) ON CONFLICT (name) DO UPDATE SET"
                            " byte_offset=EXCLUDED.byte_offset")
    await role_conn.fetch("SELECT * FROM trade_journal_notes")
    for t in _TABLES:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await role_conn.execute(f"DELETE FROM {t}")


@pytest.mark.parametrize("sql", [
    "SELECT app_key FROM kis_quote_accounts",
    "UPDATE kis_quote_accounts SET label = label",
    "SELECT params FROM strategy_config",
    "UPDATE strategy_config SET params = params",
    "SELECT * FROM positions",
    "UPDATE positions SET quantity = quantity",
    "SELECT * FROM system_config",
    "SELECT * FROM system_logs",
    "SELECT * FROM pending_next_day_clear",
])
async def test_r6_everything_else_is_denied(role_conn, sql):
    import asyncpg

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await role_conn.execute(sql)


# ── cycle412 보완 Red — 결함 8: 과거분 적재는 멱등(실 Postgres · 워커 전용 역할로 쓴다) ──────
#
# | # | 계약 |
# |---|---|
# | K10 | `jw.backfill.run_backfill` 을 같은 골든 파일로 두 번 — 행 수 145 그대로 · 전부 `log_restore` · 손절선 사건 0 · 워커 역할 권한(SELECT·INSERT)만으로 된다 |

_GOLDEN = _ROOT / "journal_worker" / "tests" / "fixtures" / "golden_2026-09-17_10-07.log"


def _jw(module: str):
    import importlib
    import sys

    root = str(_ROOT / "journal_worker")
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(f"jw.{module}")


async def test_k10_backfill_twice_keeps_rows_as_worker_role(admin, role_conn):
    db = _jw("db").JournalDB(role_conn)
    run = _jw("backfill").run_backfill
    first = await run([_GOLDEN], db, max_bytes_per_sec=10**12, sleep=lambda s: None)
    n1 = await admin.fetchval("SELECT count(*) FROM trade_journal_orders")
    second = await run([_GOLDEN], db, max_bytes_per_sec=10**12, sleep=lambda s: None)
    n2 = await admin.fetchval("SELECT count(*) FROM trade_journal_orders")
    assert (first["rows"], second["rows"], n1, n2) == (145, 145, 145, 145)
    sources = [r["source"] for r in await admin.fetch("SELECT DISTINCT source FROM trade_journal_orders")]
    assert sources == ["log_restore"]
    assert await admin.fetchval("SELECT count(*) FROM trade_journal_stops") == 0



# ── cycle412 보완2 Red — N1: 쓴 행만 센다 · 빈 행을 실측으로 승격한다 ─────────────────────
#
# | # | 계약 |
# |---|---|
# | K11 | 워커 역할로 — `insert_order` 는 새로 넣었는지 돌려준다(True → 같은 키 False) · `promote_order` 는 같은 키의 `unmatched`·`external` 행만, 빈 칸(NULL · 전략 `'unknown'`)만 채우고 source 를 로그 행 것으로 바꾼다(이미 있는 값·`noted_at` 은 그대로) → True · 이미 실측인 행·없는 키 → False, 행 그대로 |

_ORDER_COLS = ("order_date", "order_no", "side", "strategy", "ticker", "source", "reason_code", "reason_sub",
               "judge_price", "order_price", "order_division", "exchange", "parent_order_no", "fired_line",
               "effective_line", "signal", "params", "noted_at")


def _order(**kw):
    row = {k: None for k in _ORDER_COLS}
    row.update(order_date=date(2026, 10, 13), ticker="005930", noted_at=_NOW)
    row.update(kw)
    return row


async def _get(admin, no, side):
    import json

    r = await admin.fetchrow("SELECT * FROM trade_journal_orders WHERE order_date=$1 AND order_no=$2 AND side=$3",
                             date(2026, 10, 13), no, side)
    out = dict(r)
    for k in ("signal", "params"):
        if isinstance(out[k], str):
            out[k] = json.loads(out[k])
    return out


async def test_k11_insert_reports_and_promote_fills_only_empty_rows(admin, role_conn):
    db = _jw("db").JournalDB(role_conn)
    sell_empty = _order(order_no="0000300100", side="SELL", strategy="unknown", source="unmatched",
                        order_price=70100)
    assert await db.insert_order(sell_empty) is True
    assert await db.insert_order(sell_empty) is False

    measured = _order(order_no="0000300100", side="SELL", strategy="kojiro", source="log_harvest",
                      reason_code="STOP_LOSS", judge_price=9180, order_price=70000, fired_line=9200,
                      effective_line=9500, signal={"signal_name": "STOP_LOSS", "path": "accept"},
                      noted_at=_NOW + timedelta(seconds=1))
    assert await db.insert_order(measured) is False, "빈 행이 이미 있다 — INSERT 0 0"
    assert await db.promote_order(measured) is True
    r = await _get(admin, "0000300100", "SELL")
    assert (r["source"], r["strategy"], r["reason_code"], r["judge_price"], r["fired_line"], r["effective_line"]) == (
        "log_harvest", "kojiro", "STOP_LOSS", 9180, 9200, 9500), r
    assert r["signal"] == {"signal_name": "STOP_LOSS", "path": "accept"}
    assert r["order_price"] == 70100 and r["noted_at"] == _NOW, "이미 있는 값은 그대로 — 빈 칸만 채운다"

    again = dict(measured, source="fallback_inferred", reason_code="TRAILING_STOP", order_division="01")
    assert await db.promote_order(again) is False, "이미 실측인 행은 승격 대상이 아니다"
    r2 = await _get(admin, "0000300100", "SELL")
    assert (r2["source"], r2["reason_code"], r2["order_division"]) == ("log_harvest", "STOP_LOSS", None)

    assert await db.promote_order(dict(measured, order_no="0000999999")) is False, "없는 키"

    ext = _order(order_no="0000200100", side="BUY", strategy="kojiro", source="external")
    assert await db.insert_order(ext) is True
    assert await db.promote_order(_order(order_no="0000200100", side="BUY", strategy="kojiro",
                                         source="fallback_inferred", reason_code="ENTRY",
                                         signal={"path": "fallback", "strategy_src": "trade_history"})) is True
    r3 = await _get(admin, "0000200100", "BUY")
    assert (r3["source"], r3["reason_code"]) == ("fallback_inferred", "ENTRY")
    assert await admin.fetchval("SELECT count(*) FROM trade_journal_orders") == 2
