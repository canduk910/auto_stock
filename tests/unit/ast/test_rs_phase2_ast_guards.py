"""RS 2단계 Red — 구조 가드 (import 경계 · 전략 객체 쓰기 0 · 부팅 배선).

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase2.md` §B 🔴 · §C.
AST 로만 센다(주석·docstring 무관). `ast.dump` sha 핀 없음.

| # | 계약 |
|---|---|
| G1 | 새 모듈 4개의 import 에 8영역·`scheduler`·`src.realtime`·`src.auth` 0 |
| G1b | 예외 하나 — `fundamental_load_tasks` 는 `scanner` 의 유니버스 상수 2개(`_DAILY_LOAD_MIN_MCAP_EOK`·`_DAILY_LOAD_MIN_TRADE_WON`)만 `from src.engine.scanner import` 로 읽을 수 있다(명세 §A 「읽기만 import」). 명세 §C 「8영역 import 0」 과 이 한 줄이 충돌해 상수 2개로 좁혔다 |
| G2 | `rs_fundamental_observe` 에 `src.api` import 0 (KIS 0 — DB 만) |
| G3 | `rs_fundamental_observe` 에 속성 대입·`setattr`·속성 사슬 위 변이 메서드 호출 0 (`self` 제외) |
| G4 | `boot_manager.boot` — `account_cluster.spawn_boot_assign` 을 감싼 `try` **바로 다음 문장**이 `rs_fundamental_observe.spawn_boot_observe(scheduler)` 를 부르는 `try/except Exception`(await 없음) |

8영역·`scheduler.py` 파일 내용 무변경은 정본 `test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` 가 맡는다
(여기서 다시 핀하지 않는다). 전략 파일·`strategy_base.py` 는 `test_rs_phase2_untouched_pins.py`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_NEW = {
    "fundamental_load_tasks": _ROOT / "src" / "engine" / "fundamental_load_tasks.py",
    "rs_fundamental_observe": _ROOT / "src" / "engine" / "rs_fundamental_observe.py",
    "score_inputs": _ROOT / "src" / "db" / "score_inputs.py",
    "candidate_scores": _ROOT / "src" / "db" / "candidate_scores.py",
}
_FORBIDDEN = (
    "src.engine.risk", "src.engine.order_engine", "src.engine.session", "src.engine.scanner",
    "src.engine.strategy_registry", "src.api.order", "src.realtime", "src.auth", "src.engine.scheduler",
)
_SCANNER_CONSTS = {"_DAILY_LOAD_MIN_MCAP_EOK", "_DAILY_LOAD_MIN_TRADE_WON"}
_MUTATORS = {"pop", "popitem", "update", "add", "discard", "clear", "append", "extend", "remove",
             "setdefault", "insert", "__setitem__", "__delitem__"}


def _hit(mod: str, prefixes) -> bool:
    return any(mod == p or mod.startswith(p + ".") for p in prefixes)


def _imports(tree: ast.AST):
    """(모듈 전체 이름, ImportFrom 노드|None, 가져온 이름) 목록. `from a import b` 는 `a.b` 로도 본다."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(a.name, None, None) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                out.append((mod, node, a.name))
                out.append((f"{mod}.{a.name}", node, a.name))
    return out


def _tree(name: str) -> ast.AST:
    path = _NEW[name]
    assert path.is_file(), f"{path.relative_to(_ROOT)} 가 없다"
    return ast.parse(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(_NEW))
def test_g1_no_forbidden_imports(name):
    bad = []
    for mod, node, imported in _imports(_tree(name)):
        if not _hit(mod, _FORBIDDEN):
            continue
        if (name == "fundamental_load_tasks" and node is not None
                and node.module == "src.engine.scanner" and imported in _SCANNER_CONSTS):
            continue  # G1b
        bad.append(mod)
    assert bad == [], f"{name} 금지 import: {sorted(set(bad))}"


def test_g1b_scanner_import_only_two_constants():
    names = set()
    for mod, node, imported in _imports(_tree("fundamental_load_tasks")):
        if node is not None and node.module == "src.engine.scanner":
            names.add(imported)
    assert names <= _SCANNER_CONSTS, f"scanner 에서 상수 2개 밖을 가져온다: {names - _SCANNER_CONSTS}"


def test_g2_observe_has_no_src_api_import():
    bad = [m for m, _n, _i in _imports(_tree("rs_fundamental_observe")) if _hit(m, ("src.api",))]
    assert bad == [], f"rs_fundamental_observe 는 KIS 를 부르지 않는다: {sorted(set(bad))}"


def _root_name(expr: ast.AST) -> str | None:
    while isinstance(expr, (ast.Attribute, ast.Subscript)):
        expr = expr.value
    return expr.id if isinstance(expr, ast.Name) else None


def _is_attr_chain(expr: ast.AST) -> bool:
    cur = expr
    while isinstance(cur, ast.Subscript):
        cur = cur.value
    return isinstance(cur, ast.Attribute)


def test_g3_observe_never_writes_to_objects():
    tree = _tree("rs_fundamental_observe")
    bad = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = node.targets
        for t in targets:
            for sub in ast.walk(t):
                if isinstance(sub, (ast.Attribute, ast.Subscript)) and _is_attr_chain(sub) \
                        and _root_name(sub) != "self" and isinstance(getattr(sub, "ctx", None), (ast.Store, ast.Del)):
                    bad.append(f"대입 L{node.lineno}")
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in ("setattr", "delattr"):
                bad.append(f"{f.id} L{node.lineno}")
            if isinstance(f, ast.Attribute) and f.attr in _MUTATORS and _is_attr_chain(f.value) \
                    and _root_name(f.value) != "self":
                bad.append(f".{f.attr}() L{node.lineno}")
    assert bad == [], f"전략 객체에 쓰지 않는다: {bad}"


# ---------------------------------------------------------------------------
# G4 — boot_manager 배선
# ---------------------------------------------------------------------------
def _calls(node: ast.AST, owner: str, attr: str):
    return [c for c in ast.walk(node)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == attr
            and isinstance(c.func.value, ast.Name) and c.func.value.id == owner]


def _boot_fn() -> ast.AST:
    path = _ROOT / "src" / "engine" / "boot_manager.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "boot":
            return n
    raise AssertionError("boot_manager.boot 을 찾지 못함")


def _find_stmt_list_with(fn: ast.AST, predicate):
    for node in ast.walk(fn):
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(node, field, None)
            if isinstance(stmts, list):
                for i, s in enumerate(stmts):
                    if predicate(s):
                        return stmts, i
    return None, None


def test_g4_boot_spawns_observe_right_after_account_cluster():
    fn = _boot_fn()
    stmts, i = _find_stmt_list_with(
        fn, lambda s: isinstance(s, ast.Try) and _calls(s, "account_cluster", "spawn_boot_assign"))
    assert stmts is not None, "account_cluster.spawn_boot_assign 을 감싼 try 가 없다"
    assert i + 1 < len(stmts), "그 try 뒤에 문장이 없다"
    nxt = stmts[i + 1]
    assert isinstance(nxt, ast.Try), f"바로 다음 문장이 try 가 아니다: {type(nxt).__name__} L{nxt.lineno}"
    body = ast.Module(body=nxt.body, type_ignores=[])
    calls = _calls(body, "rs_fundamental_observe", "spawn_boot_observe")
    assert len(calls) == 1, "try 본문에 rs_fundamental_observe.spawn_boot_observe(...) 1회"
    args = calls[0].args
    assert len(args) == 1 and isinstance(args[0], ast.Name) and args[0].id == "scheduler"
    assert not any(isinstance(x, ast.Await) for x in ast.walk(nxt)), "부팅을 막지 않는다 — await 0"
    assert nxt.handlers and all(
        isinstance(h.type, ast.Name) and h.type.id == "Exception" for h in nxt.handlers
    ), "except Exception 로 감싼다"
    assert all(not any(isinstance(x, ast.Raise) for x in ast.walk(h)) for h in nxt.handlers), "다시 올리지 않는다"


def test_g4b_observe_spawned_once_in_boot():
    assert len(_calls(_boot_fn(), "rs_fundamental_observe", "spawn_boot_observe")) == 1
