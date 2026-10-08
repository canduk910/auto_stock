"""cycle412 Red — G1 순수성 AST (설계 관찰자안 5절 ② 「G1 변이 금지」, 계획서 7절 ①·⑤ 를 G1 로 바꾼 것).

G1 범위 = `src/routes/balance.py` 의 `exit_lines` 핸들러 + 이름이 `_exit_lines` 로 시작하는 모듈 함수.
호출 허용 목록만으로는 `x[k] = …`·`obj.a = …`·`del` 을 못 막는다 — 그래서 대입 대상·변이 메서드를 따로 막는다.

| # | 계약 |
|---|---|
| A1 | `@router.get("/exit-lines")` 핸들러 `exit_lines` 는 `async def` 이고 `await` 0(스냅샷이 한 번에 읽힌다) · `_exit_lines_snapshot` 을 부른다 |
| A2 | 허용 호출만(이름·속성 목록 + G1 범위 함수 `_exit_lines*`) — 그 밖의 호출 0 |
| A3 | 금지 호출: `check_*`·`on_*`·`prepare`·`calc_*`·`_apply_budget_limit`·`_market_unit_*`·`_effective_setup`·`vars`·`setattr`·`delattr`·`exec`·`eval` · 변이 메서드 |
| A4 | `_kk` 는 리터럴 `"kk_breakeven_r"` 로만 |
| A5 | 대입·증분대입 대상은 이름(튜플)만 · `del` 0 · `__dict__` 0 · `global` 은 `_exit_lines_cache` 만 |
| A6 | 직렬화(`json.dumps`)는 핸들러의 `try` 본문 안 · 그 `try` 는 예외를 받는다 · 응답에 `default=str` |
| A7 | 엔진 8영역 모듈은 이 파일 최상단에서 import 하지 않는다(G1 은 `trading_scheduler` 를 함수 안에서 얻는다) |

선례 = `test_cycle328_sell_pending_helper.py::test_g328_3b`(try 모양 고정) · cycle274 허용 import 목록.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_BALANCE = _ROOT / "src" / "routes" / "balance.py"

_ALLOWED_NAMES = {
    "getattr", "isinstance", "list", "dict", "tuple", "int", "float", "str", "bool", "len", "round",
    "sorted", "max", "min", "abs", "ceil", "isfinite", "resolve_exit_lines", "build_exit_line_map",
    "_exit_lines_snapshot", "_exit_lines_clock", "Response", "ApiResponse", "now_kst_iso",
}
_ALLOWED_ATTRS = {
    "all", "items", "keys", "values", "get", "monotonic", "now", "isoformat", "dumps", "debug",
    "_kk_exit_lines", "_kk", "model_dump", "ceil", "isfinite",
}
_MUTATORS = {"pop", "popitem", "clear", "update", "setdefault", "sort", "append", "extend", "remove",
             "insert", "add", "discard"}
_FORBIDDEN_EXACT = {"prepare", "_apply_budget_limit", "_effective_setup", "vars", "setattr", "delattr",
                    "exec", "eval", "__import__"}
_FORBIDDEN_PREFIX = ("check_", "on_", "calc_", "_market_unit_")


def _tree():
    return ast.parse(_BALANCE.read_text(encoding="utf-8"))


def _g1_functions():
    tree = _tree()
    fns = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and (n.name == "exit_lines" or n.name.startswith("_exit_lines"))]
    names = {f.name for f in fns}
    assert "exit_lines" in names, "G1 핸들러 `exit_lines` 가 없다"
    assert "_exit_lines_snapshot" in names, "스냅샷 조립 함수 `_exit_lines_snapshot` 이 없다"
    return fns


def _handler():
    return next(f for f in _g1_functions() if f.name == "exit_lines")


def _call_name(node: ast.Call) -> tuple[str, str]:
    f = node.func
    if isinstance(f, ast.Name):
        return "name", f.id
    if isinstance(f, ast.Attribute):
        return "attr", f.attr
    return "other", ast.dump(f)[:40]


def _calls():
    for fn in _g1_functions():
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                yield fn.name, node


def test_a1_handler_is_async_route_without_await():
    h = _handler()
    assert isinstance(h, ast.AsyncFunctionDef), "G1 핸들러는 async def"
    decos = [d for d in h.decorator_list if isinstance(d, ast.Call)]
    assert any(isinstance(d.func, ast.Attribute) and d.func.attr == "get" and d.args
               and isinstance(d.args[0], ast.Constant) and d.args[0].value == "/exit-lines" for d in decos)
    for fn in _g1_functions():
        assert not any(isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith)) for n in ast.walk(fn)), (
            f"{fn.name} 에 await — 스냅샷 구간에 양보점이 생기면 한 번에 읽히지 않는다")
    assert any(_call_name(c) == ("name", "_exit_lines_snapshot") for c in ast.walk(h)
               if isinstance(c, ast.Call)), "핸들러가 `_exit_lines_snapshot` 을 부르지 않는다"


def test_a2_only_allowed_calls():
    bad = []
    for fname, c in _calls():
        kind, name = _call_name(c)
        ok = ((kind == "name" and (name in _ALLOWED_NAMES or name.startswith("_exit_lines")))
              or (kind == "attr" and name in _ALLOWED_ATTRS))
        if not ok:
            bad.append(f"{fname}:{c.lineno} {kind} {name}")
    assert bad == [], bad


def test_a3_forbidden_calls_absent():
    bad = []
    for fname, c in _calls():
        _, name = _call_name(c)
        if name in _FORBIDDEN_EXACT or name.startswith(_FORBIDDEN_PREFIX) or name in _MUTATORS:
            bad.append(f"{fname}:{c.lineno} {name}")
    assert bad == [], bad


def test_a4_kk_only_with_breakeven_literal():
    kk = [c for _, c in _calls() if _call_name(c) == ("attr", "_kk")]
    assert kk, "donchian 무장가는 `_kk(\"kk_breakeven_r\")` 로 읽는다"
    for c in kk:
        assert len(c.args) == 1 and not c.keywords
        assert isinstance(c.args[0], ast.Constant) and c.args[0].value == "kk_breakeven_r", ast.dump(c)


def _targets(node):
    if isinstance(node, (ast.Tuple, ast.List)):
        for e in node.elts:
            yield from _targets(e)
    elif isinstance(node, ast.Starred):
        yield from _targets(node.value)
    else:
        yield node


def test_a5_assignment_targets_are_local_names_only():
    bad = []
    for fn in _g1_functions():
        for node in ast.walk(fn):
            tgts = []
            if isinstance(node, ast.Assign):
                tgts = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                tgts = [node.target]
            elif isinstance(node, ast.Delete):
                bad.append(f"{fn.name}:{node.lineno} del")
            elif isinstance(node, ast.Attribute) and node.attr == "__dict__":
                bad.append(f"{fn.name}:{node.lineno} __dict__")
            elif isinstance(node, ast.Global):
                if set(node.names) - {"_exit_lines_cache"}:
                    bad.append(f"{fn.name}:{node.lineno} global {node.names}")
            elif isinstance(node, ast.Nonlocal):
                bad.append(f"{fn.name}:{node.lineno} nonlocal")
            for t in tgts:
                for leaf in _targets(t):
                    if not isinstance(leaf, ast.Name):
                        bad.append(f"{fn.name}:{node.lineno} 대입 대상 {type(leaf).__name__}")
    assert bad == [], bad


def test_a6_serialization_inside_handler_try():
    h = _handler()
    tries = [n for n in ast.walk(h) if isinstance(n, ast.Try)]
    found = False
    for t in tries:
        body_calls = [c for s in t.body for c in ast.walk(s) if isinstance(c, ast.Call)]
        dumps = [c for c in body_calls if _call_name(c) == ("attr", "dumps")]
        if dumps:
            found = True
            assert t.handlers, "직렬화 try 에 except 가 없다"
            assert any(kw.arg == "default" and isinstance(kw.value, ast.Name) and kw.value.id == "str"
                       for c in dumps for kw in c.keywords), "json.dumps(..., default=str)"
            assert any(_call_name(c) == ("name", "_exit_lines_snapshot") for c in body_calls), (
                "스냅샷 조립도 같은 try 안에서")
    assert found, "json.dumps 가 핸들러의 try 본문 안에 없다"


def test_a7_no_engine_core_import_at_module_top():
    tree = _tree()
    eight = ("src.engine.risk", "src.engine.order_engine", "src.engine.session", "src.engine.scanner",
             "src.engine.strategy_registry", "src.engine.scheduler", "src.api.order", "src.realtime",
             "src.auth")
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith(eight), node.module
        if isinstance(node, ast.Import):
            for a in node.names:
                assert not a.name.startswith(eight), a.name
