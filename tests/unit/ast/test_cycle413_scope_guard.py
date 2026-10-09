"""cycle413 Red — 범위 가드: 거래일지 화면(1b)은 **읽기 화면 + 메모 쓰기 하나**다.

명세 = `_workspace/red/cycle413/journal_view_spec.md` 머리 「금기」 · 계약 = `_workspace/red/cycle413/journal_view_contract.md` 0절.

| # | 계약 |
|---|---|
| S4 | `src/engine/journal_view.py` 는 순수 leaf — `async def`·`await` 0 · `src.db`·`src.api`·`src.realtime`·`src.auth`·`src.services`·`scheduler`·8영역·`asyncpg`·`httpx` import 0 |
| S5 | KIS 호출 0 — `journal_view.py`·`src/db/trade_journal.py`·`src/routes/history.py` 가 `src.api`·`src.auth` 를 import 하지 않는다 |
| S6 | `stock_master_daily.get_closes_in_range`·`list_business_days` 는 SELECT 만 · `trade_journal.py` 의 쓰기 SQL 대상은 `trade_journal_notes` 하나 |

스캔은 `Path.rglob` — `git ls-files` 는 미추적 새 파일을 못 본다(cycle259 S4b). SQL 검사는 문자열 상수만 본다(주석·docstring 제외 —
docstring 은 함수 본문 첫 문장 상수라 걷어낸다).

S1·S2·S3(8영역·`scheduler.py` 파일 sha · `journal_worker/` digest · 마이그레이션 digest)은 사이클 한정
범위 가드였다 — 병합 뒤 역할이 끝나 걷었다(cycle419). 8영역·`scheduler.py` 무접촉은 정본
`test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` 가, `journal_worker` 격리는
`journal_worker/tests/test_jw_isolation.py` 가 진다. S4~S6 은 이 모듈들의 영구 성질이다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_LEAF = "src/engine/journal_view.py"
_JOURNAL_DB = "src/db/trade_journal.py"
_ROUTE = "src/routes/history.py"
_SMD = "src/db/stock_master_daily.py"

_EIGHT_AREA_MODULES = {
    "src.engine.risk", "src.engine.order_engine", "src.engine.session", "src.engine.scanner",
    "src.engine.strategy_registry", "src.engine.scheduler", "src.api.order",
}
_LEAF_BANNED_PREFIXES = ("src.db", "src.api", "src.realtime", "src.auth", "src.services", "src.routes",
                         "asyncpg", "httpx", "aiohttp", "requests")


def _tree(rel: str) -> ast.Module:
    path = _ROOT / rel
    assert path.is_file(), f"{rel} 이 없다"
    return ast.parse(path.read_text(encoding="utf-8"))


def _imports(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
    return out


def _sql_strings(fn: ast.AST) -> list[str]:
    """함수 본문의 문자열 상수(docstring 제외)."""
    body = list(getattr(fn, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    out: list[str] = []
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append(node.value)
    return out


def _module_sql_strings(tree: ast.Module) -> list[str]:
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out += _sql_strings(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.append(sub.value)
    return out


# ── S4 ──────────────────────────────────────────────────────────────────────

def test_s4_leaf_is_pure():
    tree = _tree(_LEAF)
    asyncs = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
    awaits = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Await)]
    assert not asyncs and not awaits, f"journal_view 는 순수 함수만 — async {asyncs} await@{awaits}"
    bad = sorted(m for m in _imports(tree)
                 if m in _EIGHT_AREA_MODULES or m.startswith(_LEAF_BANNED_PREFIXES)
                 or any(m == x or m.startswith(x + ".") for x in _EIGHT_AREA_MODULES))
    assert not bad, f"journal_view 금지 import: {bad}"
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert "build_card" in names


# ── S5 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", [_LEAF, _JOURNAL_DB, _ROUTE])
def test_s5_no_kis_imports(rel):
    bad = sorted(m for m in _imports(_tree(rel)) if m.startswith(("src.api", "src.auth", "src.realtime")))
    assert not bad, f"{rel} — KIS 호출 경로 import 금지: {bad}"


# ── S6 ──────────────────────────────────────────────────────────────────────

_WRITE_RE = re.compile(r"\b(INSERT|UPDATE|DELETE|UPSERT|TRUNCATE|ALTER|DROP|CREATE)\b", re.I)


@pytest.mark.parametrize("fn_name", ["get_closes_in_range", "list_business_days"])
def test_s6_stock_master_daily_new_reads_are_select_only(fn_name):
    tree = _tree(_SMD)
    fn = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == fn_name), None)
    assert fn is not None, f"{_SMD}::{fn_name} 가 없다"
    # 모듈 상수로 SQL 을 뺐다면 그 이름이 본문에 나온다 — 상수까지 따라간다.
    consts = {t.id: node.value.value for node in tree.body if isinstance(node, ast.Assign)
              and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
              for t in node.targets if isinstance(t, ast.Name)}
    used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id in consts}
    sql = " ".join(_sql_strings(fn) + [consts[u] for u in used])
    assert re.search(r"\bSELECT\b", sql, re.I), f"{fn_name} 에 SELECT 가 없다"
    assert not _WRITE_RE.search(sql), f"{fn_name} 는 읽기 전용 — 쓰기 SQL: {_WRITE_RE.findall(sql)}"


def test_s6_trade_journal_writes_only_notes():
    # upsert 의 `ON CONFLICT … DO UPDATE SET` 은 같은 표다 — 대상 추출 전에 걷어낸다.
    sql = [re.sub(r"\bDO\s+UPDATE\s+SET\b", " ", s, flags=re.I) for s in _module_sql_strings(_tree(_JOURNAL_DB))]
    writes = [s for s in sql if re.search(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b", s, re.I)]
    assert writes, "메모 upsert/delete SQL 이 없다"
    for s in writes:
        targets = re.findall(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-z_]+)", s, re.I)
        assert targets and set(t.lower() for t in targets) <= {"trade_journal_notes"}, (
            f"trade_journal.py 의 쓰기 대상은 trade_journal_notes 하나 — {targets}: {s[:120]!r}")
    for s in sql:
        assert not re.search(r"\b(TRUNCATE|ALTER|DROP)\b", s, re.I), s[:120]
