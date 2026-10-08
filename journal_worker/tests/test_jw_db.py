"""cycle412 Red — 워커 DB 는 자동커밋 단문만(설계 관찰자안 5절 ④ RDS 잠금 대기열).

배포 때마다 `deploy.yml` 이 `ALTER TABLE trade_history` 를 다시 돈다. 워커 트랜잭션이 열린 채면
ALTER 가 그 뒤에서 기다리고, 그 뒤로 backend 의 `trade_history` 쓰기(체결통보 처리)가 줄을 선다.

| # | 계약 |
|---|---|
| B1 | 메서드마다 `execute/fetch/fetchrow/fetchval` 정확히 1번 · `transaction()` 0 |
| B2 | SQL 은 문장 1개(끝 `;` 말고 `;` 0) · `BEGIN/COMMIT/ROLLBACK` 0 |
| B3 | 주문 행 = `ON CONFLICT (order_date, order_no, side) DO NOTHING` · 주문구분 채우기 = `order_division IS NULL` 일 때만 |
| B4 | jw/ 어디에도 `.transaction(` · `BEGIN` 없음 · `jw/db.py` 는 httpx·sleep 을 모른다(트랜잭션 안 HTTP·sleep 원천 차단) |
| B5 | JSONB 칸(signal·params·inputs)은 dict 그대로 넘기거나 json 문자열 — 어느 쪽이든 인자 수가 SQL 자리표시자 수와 같다 |
| B7 | (보완2 N1) `insert_order` 는 새로 넣었는지를 돌려준다 — `INSERT 0 1` → True · `INSERT 0 0`(이미 있음) → False |
| B8 | (보완2 N1) `promote_order(row)` = 단문 `UPDATE trade_journal_orders` 1개 — 같은 키의 행이 `unmatched`·`external` 일 때만(WHERE), 빈 칸만 채운다(COALESCE · 전략 `'unknown'` 은 빈 칸) · source 는 로그 행 것 · `UPDATE 1` → True · `UPDATE 0` → False |
"""
from __future__ import annotations

import ast
import asyncio
import re
from datetime import date

import pytest

from jw_testkit import jw, jw_sources, kst

pytestmark = pytest.mark.unit


class FakeConn:
    def __init__(self, fetchrow_result=None, fetch_result=None, status=None):
        self.calls: list[tuple[str, str, tuple]] = []
        self._row = fetchrow_result
        self._rows = fetch_result or []
        self._status = status

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        if self._status is not None:
            return self._status
        return "UPDATE 1" if sql.lstrip().upper().startswith("UPDATE") else "INSERT 0 1"

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return self._rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        return self._row

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        return None

    def transaction(self, *a, **k):  # pragma: no cover — 불리면 실패
        raise AssertionError("transaction() 금지 — 자동커밋 단문만")


ROW = {"order_date": date(2026, 10, 13), "order_no": "0000300100", "side": "SELL", "strategy": "kojiro",
       "ticker": "005930", "source": "log_harvest", "reason_code": "STOP_LOSS", "reason_sub": None,
       "judge_price": 9180, "order_price": None, "order_division": None, "exchange": None,
       "parent_order_no": None, "fired_line": 9200, "effective_line": 9500,
       "signal": {"signal_name": "STOP_LOSS", "snapshot_age_s": 10}, "params": None,
       "noted_at": kst(2026, 10, 13, 10, 0, 10)}

EVENT = {"strategy": "kojiro", "ticker": "005930", "buy_date": date(2026, 10, 10),
         "pos_order_no": "0000100000", "observed_at": kst(2026, 10, 13, 10, 0), "event": "change",
         "stop_price": 9400, "stop_kind": "effective", "target_price": None, "target_hit": None,
         "arm_price": None, "inputs": {"buy_price": 10000}}


def _single_statement(sql: str) -> bool:
    body = sql.strip().rstrip(";")
    return ";" not in body


def _placeholders(sql: str) -> int:
    nums = {int(n) for n in re.findall(r"\$(\d+)", sql)}
    return max(nums) if nums else 0


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("method,args", [
    ("insert_order", (ROW,)),
    ("promote_order", (ROW,)),
    ("fill_order_division", (date(2026, 10, 13), "0000300100", "SELL", "01")),
    ("insert_stop", (EVENT,)),
    ("load_cursor", ()),
    ("save_cursor", ({"file_name": "auto_stock.log", "inode": 123, "byte_offset": 456},)),
    ("last_stop_rows", ()),
    ("trades_since", (kst(2026, 10, 13),)),
])
def test_b1_b2_each_method_is_one_autocommit_statement(method, args):
    conn = FakeConn()
    db = jw("db").JournalDB(conn)
    _run(getattr(db, method)(*args))
    assert len(conn.calls) == 1, conn.calls
    kind, sql, params = conn.calls[0]
    assert _single_statement(sql), sql
    assert not re.search(r"\b(BEGIN|COMMIT|ROLLBACK|START\s+TRANSACTION)\b", sql, re.I), sql
    assert len(params) == _placeholders(sql), (sql, params)


def test_b3_insert_order_keeps_first_value():
    conn = FakeConn()
    _run(jw("db").JournalDB(conn).insert_order(ROW))
    sql = " ".join(conn.calls[0][1].split())
    assert "trade_journal_orders" in sql
    assert re.search(r"ON CONFLICT \(order_date, order_no, side\) DO NOTHING", sql, re.I), sql


def test_b3b_fill_division_only_when_null():
    conn = FakeConn()
    _run(jw("db").JournalDB(conn).fill_order_division(date(2026, 10, 13), "0000300100", "SELL", "01"))
    sql = " ".join(conn.calls[0][1].split())
    assert sql.upper().startswith("UPDATE TRADE_JOURNAL_ORDERS")
    assert re.search(r"order_division IS NULL", sql, re.I), sql


def test_b3c_cursor_upsert_and_load_shape():
    conn = FakeConn(fetchrow_result={"file_name": "auto_stock.log", "inode": 7, "byte_offset": 99})
    db = jw("db").JournalDB(conn)
    assert _run(db.load_cursor()) == {"file_name": "auto_stock.log", "inode": 7, "byte_offset": 99}
    _run(db.save_cursor({"file_name": "auto_stock.log", "inode": 7, "byte_offset": 120}))
    sql = " ".join(conn.calls[-1][1].split())
    assert "trade_journal_cursor" in sql and re.search(r"ON CONFLICT \(name\) DO UPDATE", sql, re.I), sql


def test_b3d_trade_history_is_read_only():
    conn = FakeConn()
    _run(jw("db").JournalDB(conn).trades_since(kst(2026, 10, 13)))
    kind, sql, _ = conn.calls[0]
    assert kind == "fetch" and sql.strip().upper().startswith("SELECT")
    assert "trade_history" in sql and not re.search(r"\bFOR\s+UPDATE\b", sql, re.I)


def test_b4_no_transaction_anywhere_in_worker():
    srcs = jw_sources()
    assert srcs, "jw/ 가 없다"
    for rel, text in srcs.items():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "transaction":
                pytest.fail(f"{rel}:{node.lineno} .transaction — 자동커밋 단문만")
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(
                    r"^\s*(BEGIN|COMMIT|ROLLBACK|START\s+TRANSACTION)\b", node.value, re.I | re.M):
                pytest.fail(f"{rel}:{node.lineno} 트랜잭션 SQL")


def test_b4b_db_module_knows_no_http_or_sleep():
    srcs = jw_sources()
    assert "jw/db.py" in srcs, "jw/db.py 가 없다"
    tree = ast.parse(srcs["jw/db.py"])
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            assert not any(m.startswith(("httpx", "jw.http")) for m in mods), mods
        if isinstance(node, (ast.Name, ast.Attribute)):
            name = node.id if isinstance(node, ast.Name) else node.attr
            assert name != "sleep", f"jw/db.py:{node.lineno} sleep"


# ── cycle412 보완 Red — 결함 6: 이어 붙이기에 보유 주문번호가 필요하다 ─────────────

def test_b6_last_stop_rows_carries_pos_order_no():
    row = {"strategy": "kojiro", "ticker": "005930", "pos_order_no": "0000100000", "stop_price": 9500,
           "stop_kind": "effective", "target_price": None, "target_hit": None, "arm_price": None,
           "event": "eod", "observed_at": kst(2026, 10, 10, 15, 31)}
    conn = FakeConn(fetch_result=[row])
    got = _run(jw("db").JournalDB(conn).last_stop_rows())
    sql = " ".join(conn.calls[0][1].split())
    assert re.search(r"\bpos_order_no\b", sql.split("FROM")[0]), f"SELECT 칸에 pos_order_no 가 없다: {sql}"
    assert got[("kojiro", "005930")]["pos_order_no"] == "0000100000"


# ── cycle412 보완2 Red — N1: 쓴 행만 센다 · 빈 행을 실측으로 승격한다 ──────────────────

@pytest.mark.parametrize("status,expected", [("INSERT 0 1", True), ("INSERT 0 0", False)])
def test_b7_insert_order_reports_whether_a_row_was_added(status, expected):
    got = _run(jw("db").JournalDB(FakeConn(status=status)).insert_order(ROW))
    assert got is expected, f"{status} → {got!r} (기대 {expected!r}) — INSERT 0 0 을 쓴 행으로 세면 실측 행이 버려진 것을 못 본다"


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def test_b8_promote_order_fills_only_empty_cells_of_empty_rows():
    conn = FakeConn()
    got = _run(jw("db").JournalDB(conn).promote_order(ROW))
    assert got is True
    (kind, sql, args) = conn.calls[0]
    n = _norm(sql)
    assert kind == "execute" and n.upper().startswith("UPDATE TRADE_JOURNAL_ORDERS SET"), n
    where = re.split(r"\bWHERE\b", n, flags=re.I)
    assert len(where) == 2, n
    assert re.search(r"\border_date\s*=\s*\$\d+", where[1]) and re.search(r"\border_no\s*=\s*\$\d+", where[1]) \
        and re.search(r"\bside\s*=\s*\$\d+", where[1]), f"키 셋으로 한 행만: {n}"
    assert re.search(r"\bsource\s+IN\s*\(\s*'(unmatched|external)'\s*,\s*'(unmatched|external)'\s*\)", where[1], re.I), (
        f"빈 행(unmatched·external)만 바꾼다 — 이미 실측인 행은 건드리지 않는다: {n}")
    sets = where[0]
    for col in ("reason_code", "reason_sub", "judge_price", "order_price", "order_division", "exchange",
                "parent_order_no", "fired_line", "effective_line", "signal", "params"):
        assert re.search(rf"\b{col}\s*=\s*COALESCE\(\s*(trade_journal_orders\.)?{col}\s*,", sets, re.I), (
            f"{col} 은 빈 칸일 때만 채운다: {n}")
    assert re.search(r"\bsource\s*=\s*\$\d+", sets), f"source 는 로그 행 것으로: {n}"
    assert re.search(r"\bstrategy\s*=", sets) and "'unknown'" in sets, f"전략 'unknown' 은 빈 칸으로 본다: {n}"
    assert not re.search(r"\b(ticker|noted_at|order_date|order_no|side)\s*=", sets), f"키·종목·기록 시각은 바꾸지 않는다: {n}"
    pos = {int(x) for x in re.findall(r"\$(\d+)", n)}
    assert pos == set(range(1, len(args) + 1)), f"자리표시자 {sorted(pos)} ↔ 인자 {len(args)}개"


def test_b8b_promote_order_reports_no_change():
    assert _run(jw("db").JournalDB(FakeConn(status="UPDATE 0")).promote_order(ROW)) is False
