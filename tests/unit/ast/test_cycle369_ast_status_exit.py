"""cycle369 Red — 종목상태(관리 51·단기과열 59) 청산 + 당일 매수 차단 · 구조 봉인 (AST).

명세 정본 `_workspace/red/cycle369_status_exit_spec.md` §7·§8·§9-F/J/S.

| 가드 | 무엇 |
|---|---|
| F1 | leaf 에 `src.realtime` import 0 · `unsubscribe` 식별자 0 (K7 — 보유 구독 무접촉) |
| F2 | leaf 가 주문 엔진에서 쓰는 것은 `execute_sell` 호출과 `_selling` **읽기**뿐 |
| F3 | 8영역 파일에 `status_exit_watch`·`_status_buy_blocked` 토큰 0 (8영역 diff 0 의 정적 절반) |
| F4 | leaf 의 DB 쓰기는 `write_log` 뿐 — `pg.` 0 · `system_config` setter 호출 0. 🔁 R3 F7 — `src.db.system_logs`·`src.db.system_config` **모듈 핸들**로 닿는 속성(호출·참조·`getattr`)도 허용 목록만 |
| F6 | leaf 에 `kis_request`·`kis_get_quote`·`httpx` 류 0 — 조회는 `fetch_stock_detail` 만 |
| F7 | leaf 모듈 최상위 import = 표준 라이브러리만(순환 차단) |
| F8 | leaf 에 새 타이머·태스크 0 (K9 — `create_task`·`call_later` 등). 🔁 R3 F3 — R2 의 예외(`create_task(_write(...))`)도 걷혔다 = **0** |
| F8b | 🔁 R3 F3 — 청산 패스는 `system_logs` 를 **직접 쓰지 않는다**(await·fire-and-forget 모두). 영속은 루트 `_DbLogHandler` 한 줄 |
| F3b | 🔁 R3 F3 — 한 함수 안에 같은 메시지(같은 변수·같은 `[marker]`)의 `logger.*` + 영속 쓰기 쌍 0 (cycle72 G-6 의 이 leaf 판 — 래퍼·변수 메시지도 잡는다) |
| F8c | `execute_sell` 은 `asyncio.shield(...)` 안에서만(Q3 — `stop()` 이 주문 제출을 자르지 않게) |
| J16 | `condition._notify_status_observer` 호출이 `output` 대입 **뒤**·캐시 lock **앞**, 본문은 lazy import + `except Exception` |
| J23 | `buy_gate`·`observe_fhkst`·`record_read`·`classify` = 동기 · await/DB/HTTP/`write_log` 0 |
| J25 | `_account_soft_gate_blocked` 첫 문장(docstring 제외) = `if self._status_buy_blocked(ticker): return True` |
| S1 | `scheduler.start()` 가 `self._status_exit_task = asyncio.create_task(status_exit_watch.task_loop(self))` |
| R7 | `/status-exit` 라우트 함수에 `HH:MM` 시각 리터럴 0 (창은 leaf 상수에서 온다) |
| Y14 | 🔁 R3 F6 — `tests/conftest.py::_neutralize_status_watch` 가 autouse 이고, `real_status_watch` 마커가 없을 때 `task_loop`·`observe_fhkst`·`buy_gate` 를 leaf 모듈에서 바꾼다(메타 가드 — 벽시계 무관) |

## 스캔 규약 (가드 설계 금기 2026-09-05)

`Path.read_text` + AST(호출·정의·import 만 — 주석·docstring 제외). `git grep`/`git ls-files`
금지(미추적 신규 파일을 못 본다). `ast.dump` sha 핀 금지.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
LEAF = SRC / "engine" / "status_exit_watch.py"
STRATEGY_BASE = SRC / "engine" / "strategy_base.py"
CONDITION = SRC / "api" / "condition.py"
SCHEDULER = SRC / "engine" / "scheduler.py"
ORDER_ENGINE = SRC / "engine" / "order_engine.py"
ROUTES = SRC / "routes" / "system_integrations.py"

EIGHT_AREA_FILES = [
    SRC / "engine" / "risk.py",
    SRC / "engine" / "order_engine.py",
    SRC / "engine" / "session.py",
    SRC / "engine" / "scanner.py",
    SRC / "engine" / "strategy_registry.py",
    SRC / "api" / "order.py",
]
EIGHT_AREA_DIRS = [SRC / "realtime", SRC / "auth"]


def _leaf_tree() -> ast.Module:
    assert LEAF.exists(), "[Red] src/engine/status_exit_watch.py 미존재"
    return ast.parse(LEAF.read_text(encoding="utf-8"))


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_fn(tree: ast.AST, name: str, cls: str | None = None):
    scope = tree
    if cls is not None:
        scope = next((n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls), None)
        assert scope is not None, f"class {cls} 부재"
        for n in scope.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
                return n
        raise AssertionError(f"{cls}.{name} 부재")
    for n in ast.walk(scope):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"{name} 부재")


def _names_and_attrs(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.alias):
            out.add(n.name.split(".")[-1])
            if n.asname:
                out.add(n.asname)
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.update(n.module.split("."))
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.update(a.name.split("."))
    return out


def _body_wo_docstring(fn) -> list[ast.stmt]:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


# ===========================================================================
# F — leaf 비간섭
# ===========================================================================
def test_f7_leaf_top_level_imports_are_stdlib_only():
    tree = _leaf_tree()
    bad = []
    for node in tree.body:
        mods: list[str] = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                bad.append(f"상대 import level={node.level}")
                continue
            mods = [node.module or ""]
        for m in mods:
            root = m.split(".")[0]
            if root != "__future__" and root not in sys.stdlib_module_names:
                bad.append(m)
    assert not bad, (
        f"leaf 최상위 import 가 표준 라이브러리 밖: {bad} — `condition`·`strategy_base` 가 이 모듈을 "
        "lazy import 하므로 최상위 src import 는 순환을 만든다(명세 §7)"
    )


def test_f1_no_realtime_import_and_no_unsubscribe():
    tree = _leaf_tree()
    tokens = _names_and_attrs(tree)
    assert "realtime" not in tokens, "leaf 가 src.realtime 을 import 한다(K7)"
    unsub = sorted(t for t in tokens if "unsubscribe" in t.lower())
    assert not unsub, f"leaf 에 구독 해제 식별자: {unsub} — 보유 구독 무접촉(K7·K12)"


def _order_engine_member_names() -> set[str]:
    tree = _tree(ORDER_ENGINE)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OrderEngine")
    names = {f.name for f in cls.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for n in ast.walk(cls):
        if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self"
                and isinstance(n.ctx, ast.Store) and n.attr.startswith("_")):
            names.add(n.attr)
    return names


def test_f2_order_engine_surface_is_execute_sell_and_selling_read_only():
    tree = _leaf_tree()
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    overlap = used & _order_engine_member_names()
    assert overlap <= {"execute_sell", "_selling"}, (
        f"leaf 가 주문 엔진 내부를 만진다: {sorted(overlap - {'execute_sell', '_selling'})}"
    )
    assert "execute_sell" in used, "양성 — 발사는 공개 메서드 execute_sell 로만"
    mutators = {"add", "discard", "remove", "pop", "clear", "update", "difference_update"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr == "_selling" and not isinstance(n.ctx, ast.Load):
            pytest.fail("leaf 가 `_selling` 에 대입한다 — 읽기만 허용")
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in mutators
                and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == "_selling"):
            pytest.fail(f"leaf 가 `_selling.{n.func.attr}()` 를 부른다 — 읽기만 허용")


def test_f3_eight_areas_have_no_status_tokens():
    files = list(EIGHT_AREA_FILES)
    for d in EIGHT_AREA_DIRS:
        files.extend(sorted(d.rglob("*.py")))
    offenders = []
    for f in files:
        tokens = _names_and_attrs(_tree(f))
        for tok in ("status_exit_watch", "_status_buy_blocked", "STATUS_EXIT"):
            if tok in tokens:
                offenders.append(f"{f.relative_to(ROOT)}:{tok}")
    assert not offenders, f"8영역에 cycle369 토큰: {offenders} — 8영역 접촉 0 이 설계(명세 §7)"


_DB_MODULES = ("src.db.system_logs", "src.db.system_config")
#: 🔁 cycle369 R3 F7 — leaf 가 DB 모듈 핸들로 닿아도 되는 속성의 전부. 쓰기는 `write_log`·`safe_write_log`
#: 뿐이고, 나머지는 읽기(재시작 발사 횟수 시드 = `search_logs` · 킬스위치 getter 2종)와 상수 하나다.
#: `set_status_*` 는 넣지 않는다 — 저장은 라우트만 한다(아래 호출 이름 금지와 같은 계약).
_DB_HANDLE_ATTR_ALLOW = frozenset({
    "write_log", "safe_write_log", "search_logs", "SEARCH_MAX_LIMIT",
    "get_status_exit_mode_raw", "get_status_buy_block_mode_raw",
})


def _db_handle_bindings(tree: ast.AST) -> dict[str, str]:
    """로컬 이름 → 모듈 경로(`src`·`src.db`·`src.db.system_logs` …). 단순 재대입 별칭까지 따라간다."""
    bind: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and not n.level:
            for a in n.names:
                path = f"{n.module}.{a.name}"
                if path in _DB_MODULES or path in ("src.db",):
                    bind[a.asname or a.name] = path
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.asname and (a.name in _DB_MODULES or a.name in ("src", "src.db")):
                    bind[a.asname] = a.name
                elif not a.asname and a.name.split(".")[0] == "src":
                    bind["src"] = "src"
    changed = True
    while changed:
        changed = False
        for n in ast.walk(tree):
            if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Name) and n.value.id in bind):
                for t in n.targets:
                    if isinstance(t, ast.Name) and bind.get(t.id) != bind[n.value.id]:
                        bind[t.id] = bind[n.value.id]
                        changed = True
    return bind


def _resolve_path(expr: ast.AST, bind: dict[str, str]) -> str | None:
    if isinstance(expr, ast.Name):
        return bind.get(expr.id)
    if isinstance(expr, ast.Attribute):
        base = _resolve_path(expr.value, bind)
        return f"{base}.{expr.attr}" if base else None
    return None


def _enclosing_functions(tree: ast.AST) -> dict[int, ast.AST]:
    """노드 id → 가장 가까운 바깥 함수(없으면 모듈)."""
    out: dict[int, ast.AST] = {}

    def _visit(node, fn):
        for ch in ast.iter_child_nodes(node):
            nxt = ch if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            out[id(ch)] = fn
            _visit(ch, nxt)

    _visit(tree, tree)
    return out


def _db_handle_violations(tree: ast.AST) -> list[str]:
    """leaf 가 DB 모듈 핸들로 닿는 속성 중 허용 목록 밖의 것(호출이든 참조든 `getattr` 이든)."""
    import importlib

    bind = _db_handle_bindings(tree)
    encl = _enclosing_functions(tree)
    bad: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute):
            base = _resolve_path(n.value, bind)
            if base in _DB_MODULES and n.attr not in _DB_HANDLE_ATTR_ALLOW:
                bad.append(f"{base.rsplit('.', 1)[-1]}.{n.attr} (line {n.lineno})")
        if not isinstance(n, ast.Call):
            continue
        fname = _call_name(n)
        if fname in ("import_module", "__import__") and any(
            isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("src.db")
            for a in n.args
        ):
            bad.append(f"동적 import {ast.unparse(n)} (line {n.lineno})")
        if fname != "getattr" or len(n.args) < 2:
            continue
        base = _resolve_path(n.args[0], bind)
        if base not in _DB_MODULES:
            continue
        name = n.args[1]
        if isinstance(name, ast.Constant) and isinstance(name.value, str):
            if name.value not in _DB_HANDLE_ATTR_ALLOW:
                bad.append(f"getattr({base.rsplit('.', 1)[-1]}, {name.value!r}) (line {n.lineno})")
            continue
        # 동적 이름 — 둘러싼 함수의 문자열 상수 중 그 모듈의 함수 이름인 것 = 닿을 수 있는 후보(보수적)
        mod = importlib.import_module(base)
        scope = encl.get(id(n), tree)
        cands = {c.value for c in ast.walk(scope)
                 if isinstance(c, ast.Constant) and isinstance(c.value, str)
                 and callable(getattr(mod, c.value, None))}
        if not cands:
            bad.append(f"getattr({base.rsplit('.', 1)[-1]}, <해석 불가>) (line {n.lineno})")
        bad.extend(f"getattr({base.rsplit('.', 1)[-1]}, {c!r}) (line {n.lineno})"
                   for c in sorted(cands - _DB_HANDLE_ATTR_ALLOW))
    return bad


def test_f4_leaf_db_writes_are_write_log_only():
    tree = _leaf_tree()
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "pg":
            bad.append(f"pg.{n.attr}")
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("src.db"):
            mod = n.module or ""
            names = [a.name for a in n.names]
            if mod == "src.db":
                extra = [x for x in names if x not in ("system_config", "system_logs")]
                bad.extend(f"src.db.{x}" for x in extra)
            elif mod == "src.db.system_logs":
                # 🔁 cycle369 R2 Q4 — 재시작 때 오늘 `[status_exit_fire]` 행을 **읽기** 위한 조회 허용.
                # 🔁 R3 F7 — 쓰지 않는 `get_logs` 는 뺐다(허용 목록은 실제로 쓰는 것만).
                bad.extend(x for x in names if x not in ("write_log", "safe_write_log", "search_logs"))
            elif mod == "src.db.system_config":
                bad.extend(x for x in names if not x.startswith("get_"))
            else:
                bad.append(mod)
        if isinstance(n, ast.Import):
            bad.extend(a.name for a in n.names
                       if a.name.startswith("src.db") and a.name not in _DB_MODULES)
        if isinstance(n, ast.Call):
            name = _call_name(n)
            if name.startswith("set_status") or name in ("execute", "executemany", "_upsert_value"):
                bad.append(f"call {name}")
    # 🔁 cycle369 R3 F7 — `from src.db import system_logs` 로 받은 **모듈 핸들**의 속성은 위 import
    # 검사가 못 본다(R2 탐침: `await system_logs.purge_old_logs()` 를 심어도 통과했다 — DELETE).
    bad.extend(_db_handle_violations(tree))
    assert not bad, f"leaf 의 DB 접근이 write_log·조회 허용 목록을 넘는다: {bad} (쓰기는 라우트만)"


def test_f4b_db_handle_guard_catches_planted_destructive_calls():
    """F4 가 공허하지 않다 — 모듈 핸들로 심은 파괴적 호출 5모양을 전부 잡는다(대조 = 실제 leaf 통과).

    심는 자리 = 실제 leaf 의 `_load_fire_counts` 본문 맨 앞(AST 로 끼운다 — 텍스트 위치에 묶이지 않게).
    """
    plants = {
        "handle_call": "from src.db import system_logs\nawait system_logs.purge_old_logs()",
        "handle_alias": "from src.db import system_logs\n_sl = system_logs\nawait _sl.purge_old_logs()",
        "import_as": "import src.db.system_logs as _x\nawait _x.purge_old_logs()",
        "dotted": "import src.db.system_logs\nawait src.db.system_logs.purge_old_logs()",
        "getattr_dynamic": "_n = 'set_status_exit_mode'\nfrom src.db import system_config as _c\n"
                           "await getattr(_c, _n)('off')",
        "handle_ref_only": "from src.db import system_logs\n_f = system_logs.purge_old_logs",
    }
    assert _db_handle_violations(_leaf_tree()) == [], "실제 leaf 는 통과해야 한다(허용 목록 = 실제 사용)"
    for label, code in plants.items():
        tree = _leaf_tree()
        fn = _find_fn(tree, "_load_fire_counts")
        wrapper = ast.parse("async def _w():\n" + "\n".join("    " + ln for ln in code.splitlines()))
        fn.body[0:0] = wrapper.body[0].body
        assert _db_handle_violations(tree), f"{label}: 심은 파괴적 접근을 F4 가 못 잡는다"


_WRITE_CALLEES = ("_write", "_spawn_write", "write_log", "safe_write_log")


def _is_write_call(node) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) in _WRITE_CALLEES


def test_f8_leaf_creates_no_timers_or_tasks():
    """K9 — 새 타이머·태스크 0.

    🔁 cycle369 R3 F3 — R2 Q3 의 예외(`create_task(_write(...))` 1곳)도 걷혔다. 발사·giveup·would_fire
    의 영속은 루트 `_DbLogHandler` 가 logger 줄을 **큐**로 옮겨 적는다(동기·non-blocking = 발사 경로
    밖). 그래서 leaf 가 태스크를 만들 이유가 남지 않는다.
    """
    tree = _leaf_tree()
    timers = {"call_later", "call_at", "run_in_executor", "Timer"}
    tasks = {"create_task", "ensure_future", "gather", "TaskGroup"}
    bad = [f"{_call_name(n)} (line {n.lineno})" for n in ast.walk(tree)
           if isinstance(n, ast.Call) and _call_name(n) in (timers | tasks)]
    assert not bad, (
        f"leaf 가 태스크·타이머를 만든다: {bad} — 30분 단일가 대기를 새 타이머로 다루지 않고(K9), "
        "영속은 루트 핸들러가 한 줄로 한다(R3 F3)"
    )


def test_f8b_sell_pass_never_writes_system_logs_itself():
    """🔁 cycle369 R3 F3 — 청산 패스는 `system_logs` 를 **직접 쓰지 않는다**(await 든 fire-and-forget 이든).

    R2 Q3 는 await 만 막았다 — 그 옆 `_spawn_write` 가 logger 줄과 같은 메시지를 한 번 더 써서 사건당
    `system_logs` 두 줄이 됐다(cycle72 G-6). 발사 경로에서 DB 를 기다리지 않는다는 Q3 목표는 루트
    핸들러의 큐 적재가 그대로 지킨다.
    """
    fn = _find_fn(_leaf_tree(), "run_sell_pass")
    hits = [f"{_call_name(n)} (line {n.lineno})" for n in ast.walk(fn) if _is_write_call(n)]
    assert not hits, f"청산 패스가 system_logs 를 직접 쓴다: {hits} — 영속은 루트 핸들러 한 줄"


_LOGGER_PERSISTING = {"info", "warning", "error", "critical", "exception"}
_MARKER = re.compile(r"\[([a-z_][a-z0-9_]*)\]")


def _msg_keys(call: ast.Call) -> set[str]:
    keys: set[str] = set()
    for a in list(call.args) + [k.value for k in call.keywords]:
        if isinstance(a, ast.Name):
            keys.add(f"name:{a.id}")
        for c in ast.walk(a):
            if isinstance(c, ast.Constant) and isinstance(c.value, str):
                keys.update(f"marker:{m}" for m in _MARKER.findall(c.value))
    return keys


def test_f3b_no_logger_and_persist_pair_in_leaf():
    """🔁 cycle369 R3 F3 — cycle72 G-6(logger + write_log 동시 호출 금지)의 이 leaf 판.

    `src.*` 로거의 INFO+ 는 루트 `_DbLogHandler` 가 이미 `system_logs` 에 한 줄 적는다. 같은 함수에서
    같은 메시지(같은 변수 또는 같은 `[marker]`)를 영속 쓰기로 또 보내면 두 줄이다. 원 G-6 가드
    (`test_cycle72_ast_no_logger_write_log_pair.py`)는 줄 창 정규식이라 `logger.warning(msg)` +
    `_spawn_write("WARNING", msg)` 같은 래퍼·변수 메시지를 못 봤다.
    """
    tree = _leaf_tree()
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        log_keys: set[str] = set()
        write_keys: set[str] = set()
        for n in ast.walk(fn):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            if (isinstance(f, ast.Attribute) and f.attr in _LOGGER_PERSISTING
                    and isinstance(f.value, ast.Name) and f.value.id == "logger"):
                log_keys |= _msg_keys(n)
            elif _is_write_call(n):
                write_keys |= _msg_keys(n)
        both = sorted(log_keys & write_keys)
        if both:
            bad.append(f"{fn.name}: {both}")
    assert not bad, f"logger 줄과 같은 메시지를 영속 쓰기로 한 번 더 보낸다(사건당 system_logs 두 줄): {bad}"


def test_f8c_execute_sell_is_shielded():
    """Q3 — `execute_sell` 은 `asyncio.shield(...)` 안에서만 부른다(`stop()` 이 주문 제출을 자르지 않게)."""
    tree = _leaf_tree()
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) == "execute_sell"]
    assert calls, "양성 — 발사는 execute_sell"
    shielded = {id(a) for n in ast.walk(tree)
                if isinstance(n, ast.Call) and _call_name(n) == "shield" for a in n.args}
    naked = [c.lineno for c in calls if id(c) not in shielded]
    assert not naked, f"shield 밖 execute_sell 호출: line {naked}"


def test_f9_leaf_does_not_reuse_next_day_clear_queue():
    """자문 §6 — `_pending_next_day_clear` 재사용 금지(라벨·DB 영속·finally discard 가 맞지 않는다)."""
    tokens = _names_and_attrs(_leaf_tree())
    assert "_pending_next_day_clear" not in tokens
    assert "NEXT_DAY_CLEAR" not in tokens and "FORCE_CLEAR" not in tokens


# ===========================================================================
# J23 · J25 — 게이트 순수성 · 배치
# ===========================================================================
_PURE = ("buy_gate", "observe_fhkst", "record_read", "classify")


@pytest.mark.parametrize("fname", _PURE)
def test_j23_hot_path_functions_are_sync_and_io_free(fname):
    fn = _find_fn(_leaf_tree(), fname)
    assert isinstance(fn, ast.FunctionDef), f"{fname} 는 동기 함수여야 한다(check_buy_signal·훅은 동기)"
    bad = []
    for n in ast.walk(fn):
        if isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith, ast.AsyncFunctionDef)):
            bad.append(type(n).__name__)
        if isinstance(n, ast.Call):
            name = _call_name(n)
            if name in ("write_log", "safe_write_log") or name.startswith("kis_") \
                    or name.startswith("fetch_") or name in ("create_task", "ensure_future"):
                bad.append(f"call {name}")
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "pg":
            bad.append("pg")
    assert not bad, f"{fname}: hot path 에 I/O·await — {bad} (K22)"


def test_j23b_status_buy_blocked_is_sync_lazy_and_fail_open():
    tree = _tree(STRATEGY_BASE)
    fn = _find_fn(tree, "_status_buy_blocked", cls="StrategyBase")
    assert isinstance(fn, ast.FunctionDef)
    assert not any(isinstance(n, ast.Await) for n in ast.walk(fn))
    lazy = [n for n in ast.walk(fn) if isinstance(n, ast.ImportFrom)
            and any(a.name == "status_exit_watch" for a in n.names)]
    assert lazy, "leaf import 는 함수 안(lazy) — 순환 차단"
    handlers = [h for n in ast.walk(fn) if isinstance(n, ast.Try) for h in n.handlers]
    assert any(isinstance(h.type, ast.Name) and h.type.id == "Exception" for h in handlers), (
        "판정 예외 fail-open(`except Exception` → False) 부재"
    )
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = {a.name for a in node.names} | {getattr(node, "module", "") or ""}
            assert not any("status_exit_watch" in x for x in names), (
                "strategy_base 최상위에서 leaf 를 import 한다 — 순환(G-5 동형)"
            )


def test_j25_status_check_is_first_statement_of_account_gate():
    fn = _find_fn(_tree(STRATEGY_BASE), "_account_soft_gate_blocked", cls="StrategyBase")
    body = _body_wo_docstring(fn)
    assert body, "게이트 본문 부재"
    first = body[0]
    assert isinstance(first, ast.If), "첫 문장이 If 가 아니다"
    call = first.test
    assert (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and call.func.attr == "_status_buy_blocked"
            and isinstance(call.func.value, ast.Name) and call.func.value.id == "self"), (
        "첫 문장이 `if self._status_buy_blocked(...)` 가 아니다"
    )
    assert len(call.args) == 1 and isinstance(call.args[0], ast.Name) and call.args[0].id == "ticker"
    assert len(first.body) == 1 and isinstance(first.body[0], ast.Return)
    ret = first.body[0].value
    assert isinstance(ret, ast.Constant) and ret.value is True
    assert not first.orelse


def test_j25b_account_gate_rest_is_preserved():
    """상태 검사 뒤에는 cycle233 계좌 게이트가 그대로 남는다(기존 본문 byte 동일은 핀이 잰다)."""
    fn = _find_fn(_tree(STRATEGY_BASE), "_account_soft_gate_blocked", cls="StrategyBase")
    names = _names_and_attrs(fn)
    assert "is_soft_gated" in names and "account_risk_watcher" in names


def test_signal_status_exit_member_is_appended():
    from src.engine.strategy_base import Signal

    names = [m.name for m in Signal]
    assert names[:6] == ["NONE", "BUY", "STOP_LOSS", "NEXT_DAY_CLEAR", "TRAILING_STOP", "FORCE_CLEAR"], (
        "기존 멤버 순서가 바뀌었다 — append-only"
    )
    assert Signal.STATUS_EXIT.value == "STATUS_EXIT"
    assert Signal("STATUS_EXIT") is Signal.STATUS_EXIT


# ===========================================================================
# J16 — condition 관측 훅 배치
# ===========================================================================
def test_j16_hook_placement_after_output_before_cache_lock():
    tree = _tree(CONDITION)
    fn = _find_fn(tree, "_fetch_stock_detail_and_cache")
    hook_calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name) and n.func.id == "_notify_status_observer"]
    assert len(hook_calls) == 1, "훅 호출이 정확히 1곳이어야 한다"
    call = hook_calls[0]
    assert [a.id for a in call.args if isinstance(a, ast.Name)] == ["ticker", "output"]
    out_assign = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "output" for t in n.targets)]
    assert out_assign and call.lineno > out_assign[0].lineno, "훅이 output 대입 앞에 있다"
    locks = [n for n in ast.walk(fn) if isinstance(n, ast.AsyncWith)]
    assert locks and call.lineno < locks[0].lineno, "훅은 캐시 lock 앞(명세 §4.4)"

    other = _find_fn(tree, "fetch_stock_detail")
    assert not any(isinstance(n, ast.Name) and n.id == "_notify_status_observer" for n in ast.walk(other)), (
        "캐시 적중 경로에서 훅을 부르면 같은 응답을 중복 기록한다"
    )


def test_j16_notify_helper_is_lazy_and_double_guarded():
    tree = _tree(CONDITION)
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_notify_status_observer"),
              None)
    assert fn is not None, "`_notify_status_observer` 는 모듈 최상위 동기 함수"
    body = _body_wo_docstring(fn)
    assert len(body) == 1 and isinstance(body[0], ast.Try), "본문 전체가 try 한 겹(K19)"
    handlers = body[0].handlers
    assert any(isinstance(h.type, ast.Name) and h.type.id == "Exception" for h in handlers)
    lazy = [n for n in ast.walk(fn) if isinstance(n, ast.ImportFrom)
            and any(a.name == "status_exit_watch" for a in n.names)]
    assert lazy, "leaf import 는 함수 안(api→engine lazy 선례 = fetch_rising_stocks)"
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert not any("status_exit_watch" in (a.name or "") for a in node.names)


# ===========================================================================
# S — scheduler 배선
# ===========================================================================
def test_s1_scheduler_start_creates_status_exit_task():
    tree = _tree(SCHEDULER)
    start = _find_fn(tree, "start", cls="TradingScheduler")
    hits = []
    for n in ast.walk(start):
        if not (isinstance(n, ast.Assign) and len(n.targets) == 1):
            continue
        tgt = n.targets[0]
        if not (isinstance(tgt, ast.Attribute) and tgt.attr == "_status_exit_task"):
            continue
        v = n.value
        ok = (isinstance(v, ast.Call) and _call_name(v) == "create_task" and v.args
              and isinstance(v.args[0], ast.Call)
              and isinstance(v.args[0].func, ast.Attribute) and v.args[0].func.attr == "task_loop"
              and isinstance(v.args[0].func.value, ast.Name)
              and v.args[0].func.value.id == "status_exit_watch"
              and [a.id for a in v.args[0].args if isinstance(a, ast.Name)] == ["self"])
        hits.append(ok)
    assert hits == [True], "start() 에 `self._status_exit_task = asyncio.create_task(status_exit_watch.task_loop(self))` 1곳"
    top = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "src.engine"
           and any(a.name == "status_exit_watch" for a in n.names)]
    assert top, "scheduler 최상위 `from src.engine import ..., status_exit_watch`(leaf 최상위가 표준 라이브러리만이라 순환 없음)"


def test_s1b_status_exit_task_is_in_all_three_cancel_tuples():
    src = SCHEDULER.read_text(encoding="utf-8")
    assert src.count('"_status_exit_task"') >= 3, "task_attrs 세 튜플(start finally ×2 · stop) 전부에 등재"


# ===========================================================================
# R7 — 라우트에 시각 리터럴 0
# ===========================================================================
_HHMM = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b")


def test_r7_status_exit_routes_have_no_time_literals():
    src = ROUTES.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fns = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.decorator_list:
                if isinstance(d, ast.Call) and any(
                    isinstance(a, ast.Constant) and a.value == "/status-exit" for a in d.args
                ):
                    fns.append(n)
    assert len(fns) == 2, f"GET·PUT `/status-exit` 라우트 2개 기대, {len(fns)}개"
    for fn in fns:
        for n in ast.walk(fn):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                assert not _HHMM.search(n.value), f"{fn.name}: 시각 리터럴 {n.value!r} — leaf 상수에서 받아라"
            if isinstance(n, ast.Call) and _call_name(n) == "time" and any(
                isinstance(a, ast.Constant) and isinstance(a.value, int) for a in n.args
            ):
                pytest.fail(f"{fn.name}: time(...) 리터럴 — leaf 상수에서 받아라")


# ===========================================================================
# Y14 — conftest 중립화 메타 가드 (🔁 cycle369 R3 F6)
#
# `test_cycle369_status_isolation.py::test_6` 는 실제 루프가 도는 시각(평일 장중)으로 시계를 고정해
# 중립화를 **행위로** 잰다. 이 가드는 같은 사실을 **구조로** 잰다 — 픽스처가 autouse 인지, 마커
# 조건 아래에서 leaf 모듈의 세 이름을 실제로 바꾸는지, 바꾼 `task_loop` 가 아무것도 하지 않는지.
# (cycle295/317 교훈 — 게이트를 넣는 사이클은 중립화 + 옵트아웃 마커 + 메타 가드를 같이 만든다.)
# ===========================================================================
CONFTEST = ROOT / "tests" / "conftest.py"


def _is_autouse_fixture(fn: ast.FunctionDef) -> bool:
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and _call_name(d) == "fixture":
            if any(k.arg == "autouse" and isinstance(k.value, ast.Constant) and k.value.value is True
                   for k in d.keywords):
                return True
    return False


def test_y14_conftest_neutralises_leaf_under_marker_condition():
    tree = _tree(CONFTEST)
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_neutralize_status_watch"),
              None)
    assert fn is not None, "tests/conftest.py::_neutralize_status_watch 부재"
    assert _is_autouse_fixture(fn), "`@pytest.fixture(autouse=True)` 가 아니다 — 중립화가 걸리지 않는다"

    guard = None
    for n in ast.walk(fn):
        if isinstance(n, ast.If) and isinstance(n.test, ast.UnaryOp) and isinstance(n.test.op, ast.Not):
            inner = n.test.operand
            if (isinstance(inner, ast.Call) and _call_name(inner) == "get_closest_marker"
                    and any(isinstance(a, ast.Constant) and a.value == "real_status_watch" for a in inner.args)):
                guard = n
    assert guard is not None, "`if not request.node.get_closest_marker(\"real_status_watch\")` 조건 부재"

    leaf_names = {a.asname or a.name for n in ast.walk(guard) if isinstance(n, ast.ImportFrom)
                  and n.module == "src.engine" for a in n.names if a.name == "status_exit_watch"}
    assert leaf_names, "조건 안에서 `from src.engine import status_exit_watch` 가 없다"
    patched: dict[str, ast.AST] = {}
    for n in ast.walk(guard):
        if (isinstance(n, ast.Call) and _call_name(n) == "setattr" and len(n.args) >= 3
                and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "monkeypatch"
                and isinstance(n.args[0], ast.Name) and n.args[0].id in leaf_names
                and isinstance(n.args[1], ast.Constant)):
            patched[n.args[1].value] = n.args[2]
    missing = {"task_loop", "observe_fhkst", "buy_gate"} - set(patched)
    assert not missing, f"중립화가 leaf 의 {sorted(missing)} 를 바꾸지 않는다 — 실 루프·실 게이트가 무관한 테스트로 샌다"

    repl = patched["task_loop"]
    assert isinstance(repl, ast.Name), "task_loop 교체값은 픽스처 안의 이름 있는 코루틴이어야 한다"
    body = next((n for n in ast.walk(fn) if isinstance(n, ast.AsyncFunctionDef) and n.name == repl.id), None)
    assert body is not None, f"`{repl.id}` 정의 부재"
    busy = [type(n).__name__ for n in ast.walk(body)
            if isinstance(n, (ast.While, ast.For, ast.AsyncFor, ast.Await, ast.Call))]
    assert not busy, f"교체된 task_loop 가 무언가를 한다: {busy} — 즉시 반환이어야 한다"
    gate = patched["buy_gate"]
    assert isinstance(gate, ast.Lambda) and isinstance(gate.body, ast.Constant) and gate.body.value is False, (
        "중립화된 buy_gate 는 `lambda ...: False` — 무관한 테스트의 매수를 막지 않는다"
    )

