"""cycle413 Red — 범위 가드: 거래일지 화면(1b)은 **읽기 화면 + 메모 쓰기 하나**다.

명세 = `_workspace/red/cycle413/journal_view_spec.md` 머리 「금기」 · 계약 = `_workspace/red/cycle413/journal_view_contract.md` 0절.

| # | 계약 |
|---|---|
| S1 | 8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py`·`src/api/order.py`·`src/realtime/**`·`src/auth/**`) + `scheduler.py` 내용 sha = 기준 main `8c28e9a6` 그대로 · 그 디렉터리에 새 `.py` 0 |
| S2 | `journal_worker/` 0줄 — 파일 (경로, 내용 sha) digest 그대로(계약 차이는 보고만, 명세 7절) |
| S3 | 마이그레이션 0 — 001~047 이름·내용 그대로, 048 없음(메모 표는 047 에 있다) |
| S4 | `src/engine/journal_view.py` 는 순수 leaf — `async def`·`await` 0 · `src.db`·`src.api`·`src.realtime`·`src.auth`·`src.services`·`scheduler`·8영역·`asyncpg`·`httpx` import 0 |
| S5 | KIS 호출 0 — `journal_view.py`·`src/db/trade_journal.py`·`src/routes/history.py` 가 `src.api`·`src.auth` 를 import 하지 않는다 |
| S6 | `stock_master_daily.get_closes_in_range`·`list_business_days` 는 SELECT 만 · `trade_journal.py` 의 쓰기 SQL 대상은 `trade_journal_notes` 하나 |

왜 내용 sha 인가 — `ast.dump` 는 3.12(CI)/3.13(로컬) 출력이 달라 핀하지 않는다(cycle256·259).
스캔은 `Path.rglob` — `git ls-files` 는 미추적 새 파일을 못 본다(cycle259 S4b). SQL 검사는 문자열 상수만 본다(주석·docstring 제외 —
docstring 은 함수 본문 첫 문장 상수라 걷어낸다).

⚠️ **사이클 한정 — cycle413 병합 후 S1·S2 삭제.** 이 dict 들은 기준 `8c28e9a6` blob 이라 cycle413 의 무접촉 증거로만
유효하다. 다음 사이클이 정당하게 바꾸면 지운다(고아 가드 방지). dict 이름을 `*_CONTENT_SHA` 로 짓지 않는다
(`test_cycle223g3` `_PIN_GUARD_FILES` 관례). S4~S6 은 이 모듈들의 영구 성질이라 남겨도 된다.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_BASE_SHA = {
    "src/engine/risk.py": "a2187b8270446379988d24dfbe39b902d6ab37b112d4b6ce7330ee171434e222",
    "src/engine/order_engine.py": "08c479841352fb579f767c109de3e8f901d1c27bdce705b39b5ba6556fc0b3e1",
    "src/engine/session.py": "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    # cycle417 사용자 승인 10-09 — 일봉 증분 적재 구멍(병합 재핀, 직전 611568c0…)
    "src/engine/scanner.py": "b570762dfd92df49471dab261d44ecd364d376300ffe9e2f5b7ac19cceb9efcc",
    "src/engine/strategy_registry.py": "3b6366c3cdb6e83907428435b95611880f1b8223e572c361a1cad2d00b13a067",
    "src/api/order.py": "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    "src/engine/scheduler.py": "f53d41a11fe162f80e113c6ff48cf6d235581769be7979499c5782ff11d49646",
    "src/auth/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py": "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    "src/auth/token.py": "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
    "src/realtime/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/realtime/handler.py": "e1a484e9ac82d43f0fa85cba693ea5a206ecfbae1076dfee0f4e6bf6d4f2a2d4",
    "src/realtime/websocket.py": "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py": "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
}

#: 기준 `8c28e9a6` 의 `journal_worker/` 파일(캐시 제외) — (경로, 내용 sha) 연쇄 digest.
_JW_FILE_COUNT = 36
_JW_DIGEST = "150cbc5cdfd87dbc7bccafdeadddb534644cb902fb51ce8b8f248e0623d6e898"

#: 기준 `8c28e9a6` 의 `supabase/migrations/*.sql` 47개 — (이름, 내용 sha) 연쇄 digest.
_MIG_COUNT = 47
_MIG_DIGEST = "139124d7b24c0bf16ffa0614c700afaffe68be6b98df4b0645d02793e32c6b4a"

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


def _sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


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


# ── S1 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_s1_eight_areas_and_scheduler_unchanged(rel):
    assert _sha(rel) == _BASE_SHA[rel], f"{rel} 가 바뀌었다 — cycle413 은 8영역·scheduler.py 0줄"


def test_s1_no_new_py_in_eight_area_dirs():
    found = {p.relative_to(_ROOT).as_posix() for d in ("src/realtime", "src/auth")
             for p in (_ROOT / d).rglob("*.py") if "__pycache__" not in p.parts}
    assert found == {k for k in _BASE_SHA if k.startswith(("src/realtime/", "src/auth/"))}


# ── S2 ──────────────────────────────────────────────────────────────────────

def test_s2_journal_worker_untouched():
    files = sorted(p for p in (_ROOT / "journal_worker").rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts)
    h = hashlib.sha256()
    for p in files:
        rel = p.relative_to(_ROOT).as_posix()
        h.update(rel.encode() + b"\0" + hashlib.sha256(p.read_bytes()).hexdigest().encode() + b"\n")
    assert len(files) == _JW_FILE_COUNT and h.hexdigest() == _JW_DIGEST, (
        "journal_worker/ 가 바뀌었다 — 1b 는 워커를 고치지 않는다(계약 차이는 명세 7절에 보고만)")


# ── S3 ──────────────────────────────────────────────────────────────────────

def test_s3_no_migration_change():
    files = sorted((_ROOT / "supabase" / "migrations").glob("*.sql"))
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode() + b"\0" + hashlib.sha256(f.read_bytes()).hexdigest().encode() + b"\n")
    assert len(files) == _MIG_COUNT, f"마이그레이션 {len(files)}개 — 1b 는 마이그레이션 0(메모 표는 047)"
    assert h.hexdigest() == _MIG_DIGEST, "기존 마이그레이션을 고치지 않는다"


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
