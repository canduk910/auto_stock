"""cycle404 Red — 계좌 묶음 배정 기록 AST 가드 (G1~G7).

명세 = `_workspace/red/cycle404_account_cluster_assign_spec.md` §6 · §7 · §9-7 · §9-8.

스캔 = 파일 읽기 + AST(import·호출·이름·문자열 상수만 — 주석·docstring 제외).
`git grep`/`git ls-files` 금지(미추적 새 파일을 못 본다), `ast.dump` sha 핀 금지(3.12/3.13 차이).

영구 가드다. 단 G2(소비처 0 = 행위 변경 0 봉인)는 **단계 1(섀도 게이트) 착수 사이클이 의도적으로
고친다** — 그때 `strategy_base.py` 가 이 leaf 를 부르게 된다.

Red 유효성: leaf 가 없어 G1·G4·G5·G6 이 실패한다. G2·G3 의 음성 단언(소비처 0 · 파라미터 편입 0)은
지금도 초록이다 — 구현이 깨면 붉어지는 몫.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_ENGINE = _ROOT / "src" / "engine"
_LEAF = _ENGINE / "account_cluster.py"
_BOOT = _ENGINE / "boot_manager.py"
_KEY = "account_cluster_mode"

#: leaf 가 import 해도 되는 우리 모듈 — 이 밖의 `src.*` 는 전부 금지(§7)
_ALLOWED_SRC = {"src.db.stock_master_daily", "src.db.system_config"}
_FORBIDDEN_THIRD = ("httpx", "requests", "aiohttp", "websockets")
#: KIS 폴백 경로가 있는 일봉 함수 · KIS 호출 표지
_FORBIDDEN_NAMES = (
    "get_recent_daily_with_fallback", "get_recent_daily_normalized",
    "kis_request", "kis_get_quote", "inquire_daily_price", "get_daily_chart",
)
_PURE = ("assign_one", "assign_all", "summarize")


def _leaf_tree() -> ast.Module:
    if not _LEAF.exists():
        pytest.fail("[Red] src/engine/account_cluster.py 미존재 — cycle404 미구현")
    return ast.parse(_LEAF.read_text(encoding="utf-8"))


def _imported_modules(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module:
            if n.level:
                out.append("." * n.level + n.module)
                continue
            out.append(n.module)
            # `from src.db import system_config` → src.db.system_config 로도 센다(패키지에서 모듈을 꺼낼 때만)
            if n.module in ("src", "src.db", "src.engine", "src.api", "src.realtime", "src.auth"):
                out += [f"{n.module}.{a.name}" for a in n.names]
        elif isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute)):
            fname = n.func.id if isinstance(n.func, ast.Name) else n.func.attr
            if fname in ("import_module", "__import__") and n.args and isinstance(n.args[0], ast.Constant):
                out.append(str(n.args[0].value))
    return out


def _names(tree: ast.AST) -> set[str]:
    s: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            s.add(n.id)
        elif isinstance(n, ast.Attribute):
            s.add(n.attr)
        elif isinstance(n, ast.alias):
            s.add(n.name.split(".")[-1])
            if n.asname:
                s.add(n.asname)
    return s


def _func(tree: ast.Module, name: str):
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


# ══════════════════════════════════════════════════════════════════════
# G1 — leaf import 허용 목록(§7)
# ══════════════════════════════════════════════════════════════════════
def test_g1_leaf_imports_only_stdlib_and_two_db_modules():
    mods = _imported_modules(_leaf_tree())
    assert not any(m.startswith(".") for m in mods), f"상대 import 금지: {mods}"
    src_mods = {m for m in mods if m == "src" or m.startswith("src.")}
    # `from src.db import system_config` 는 "src.db" 와 "src.db.system_config" 두 개로 잡힌다
    bad = {m for m in src_mods if m not in _ALLOWED_SRC and m not in ("src", "src.db")}
    assert not bad, (
        f"leaf 는 표준 라이브러리 · {sorted(_ALLOWED_SRC)} 만 import 한다(§7) — 금지 import: {sorted(bad)}"
    )
    third = [m for m in mods if m.split(".")[0] in _FORBIDDEN_THIRD]
    assert not third, f"HTTP 클라이언트 import 금지: {third}"


def test_g1b_leaf_no_kis_fallback_or_kis_call_names():
    hits = sorted(_names(_leaf_tree()) & set(_FORBIDDEN_NAMES))
    assert not hits, f"KIS 폴백·KIS 호출 경로 사용 금지(§7 · §9-8): {hits}"


def test_g1c_leaf_reads_daily_via_get_recent_daily():
    assert "get_recent_daily" in _names(_leaf_tree()), "일봉은 DB 전용 `get_recent_daily` 로 읽는다(§7)"


# ══════════════════════════════════════════════════════════════════════
# G2 — 소비처 0 (이번 사이클 행위 변경 0 봉인 · 단계 1 에서 의도적으로 고친다)
# ══════════════════════════════════════════════════════════════════════
def _consumer_files() -> list[Path]:
    files = sorted((_ENGINE / "strategies").glob("*.py"))
    files += [_ENGINE / n for n in (
        "strategy_base.py", "risk.py", "order_engine.py", "scheduler.py", "strategy_registry.py",
    )]
    return [f for f in files if f.exists()]


@pytest.mark.parametrize("path", _consumer_files(), ids=lambda p: p.name)
def test_g2_trading_modules_do_not_reference_account_cluster(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = [m for m in _imported_modules(tree) if "account_cluster" in m]
    names = [n for n in _names(tree) if "account_cluster" in n]
    assert not mods and not names, (
        f"{path.name} 가 account_cluster 를 참조한다 — 단계 0 은 기록만(소비처 0). "
        f"섀도 게이트는 단계 1 사이클에서 이 가드를 고치며 들인다: {mods + names}"
    )


# ══════════════════════════════════════════════════════════════════════
# G3 — 킬스위치는 계좌 키(system_config) — 전략 파라미터·AI 자문 경로 편입 금지(§6)
# ══════════════════════════════════════════════════════════════════════
def test_g3a_key_not_in_param_ranges_or_int_params():
    from src.engine import recommendation_engine as rec

    assert _KEY not in rec.PARAM_RANGES
    assert _KEY not in rec.INT_PARAMS


def _str_consts(tree: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def test_g3b_key_absent_from_strategy_sources_and_recommendation_engine():
    files = sorted((_ENGINE / "strategies").glob("*.py")) + [
        _ENGINE / "strategy_base.py", _ENGINE / "recommendation_engine.py",
    ]
    hits = [f.name for f in files if f.exists() and _KEY in _str_consts(ast.parse(f.read_text(encoding="utf-8")))]
    assert not hits, f"`{_KEY}` 는 계좌 키다 — 전략 DEFAULT_PARAMS·AI 자문 경로에 두지 않는다: {hits}"


def test_g3c_leaf_reads_key_by_exact_name():
    assert _KEY in _str_consts(_leaf_tree()), f"leaf 가 system_config 키 `{_KEY}` 를 읽어야 한다(§6)"


# ══════════════════════════════════════════════════════════════════════
# G4 — 순수/I-O 분리 · spawn 은 일반 def
# ══════════════════════════════════════════════════════════════════════
def test_g4a_pure_functions_are_sync_without_await():
    tree = _leaf_tree()
    for name in _PURE:
        fn = _func(tree, name)
        assert isinstance(fn, ast.FunctionDef), f"`{name}` 는 모듈 최상위 일반 def(순수, §7)"
        awaits = [n.lineno for n in ast.walk(fn) if isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith))]
        assert not awaits, f"`{name}` 안 await (줄 {awaits}) — 순수 함수는 I/O 0"


def test_g4b_run_is_async_and_spawn_is_plain_def():
    tree = _leaf_tree()
    assert isinstance(_func(tree, "run_boot_assign"), ast.AsyncFunctionDef)
    assert isinstance(_func(tree, "spawn_boot_assign"), ast.FunctionDef), "spawn 은 일반 def — task 만 만든다"
    assert isinstance(_func(tree, "get_assignment_map"), ast.FunctionDef)


def test_g4c_bg_tasks_module_level_set():
    tree = _leaf_tree()
    hit = False
    for n in tree.body:
        targets = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "_BG_TASKS" for t in targets):
            hit = True
    assert hit, "spawn 한 task 를 붙드는 모듈 전역 `_BG_TASKS` (funnel_capture 선례)"


# ══════════════════════════════════════════════════════════════════════
# G5 — 부팅 배선(§7 · §9-7): boot_manager.boot 한 곳 · await 없음 · funnel spawn 뒤 · try 안
# ══════════════════════════════════════════════════════════════════════
def _boot_fn() -> ast.AsyncFunctionDef:
    tree = ast.parse(_BOOT.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "boot")


def _calls(fn: ast.AST, name: str) -> list[ast.Call]:
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if (isinstance(f, ast.Name) and f.id == name) or (isinstance(f, ast.Attribute) and f.attr == name):
                out.append(n)
    return out


def test_g5a_boot_spawns_once_not_awaited_after_funnel_spawn():
    boot = _boot_fn()
    awaited = {id(n.value) for n in ast.walk(boot) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)}
    spawns = _calls(boot, "spawn_boot_assign")
    assert len(spawns) == 1, f"boot 안 `spawn_boot_assign` 호출은 정확히 1곳 (실측 {[c.lineno for c in spawns]})"
    assert id(spawns[0]) not in awaited, "spawn 은 await 하지 않는다(부팅을 막지 않는다)"
    funnel = _calls(boot, "spawn_funnel_boot_vs_evening")
    assert funnel and spawns[0].lineno > max(c.lineno for c in funnel), (
        "배정 spawn 은 `spawn_funnel_boot_vs_evening` 뒤(포지션·미체결·익일청산 복구가 끝난 뒤, §7)"
    )
    run_awaited = [c.lineno for c in _calls(boot, "run_boot_assign") if id(c) in awaited]
    assert not run_awaited, f"boot 이 run_boot_assign 을 동기로 await 한다 (줄 {run_awaited})"


def test_g5b_spawn_passes_summary_net_asset():
    call = _calls(_boot_fn(), "spawn_boot_assign")
    assert call, "[Red] boot 에 spawn_boot_assign 배선 없음"
    args = list(call[0].args) + [k.value for k in call[0].keywords]
    ok = any(
        isinstance(a, ast.Attribute) and a.attr == "net_asset"
        and isinstance(a.value, ast.Name) and a.value.id == "summary"
        for a in args
    )
    assert ok, "순자산은 부팅 `summary.net_asset` 을 넘긴다(§7)"


def test_g5c_spawn_is_inside_try_except_exception():
    boot = _boot_fn()
    spawns = _calls(boot, "spawn_boot_assign")
    assert spawns, "[Red] boot 에 spawn_boot_assign 배선 없음"
    target = spawns[0]

    def handlers_catch_exception(t: ast.Try) -> bool:
        for h in t.handlers:
            ty = h.type
            if ty is None:
                return True
            names = [e for e in (ty.elts if isinstance(ty, ast.Tuple) else [ty])]
            if any(isinstance(e, ast.Name) and e.id in ("Exception", "BaseException") for e in names):
                return True
        return False

    covered = any(
        isinstance(t, ast.Try) and handlers_catch_exception(t)
        and any(target is n for stmt in t.body for n in ast.walk(stmt))
        for t in ast.walk(boot)
    )
    assert covered, "spawn 호출은 `try/except Exception` 안 — 예외가 부팅을 막지 않는다(§7)"


# ══════════════════════════════════════════════════════════════════════
# G6 — 런타임 확인: 공개 함수 모양
# ══════════════════════════════════════════════════════════════════════
def test_g6_runtime_signatures():
    if not _LEAF.exists():
        pytest.fail("[Red] src/engine/account_cluster.py 미존재")
    import importlib

    ac = importlib.import_module("src.engine.account_cluster")
    assert inspect.iscoroutinefunction(ac.run_boot_assign)
    assert not inspect.iscoroutinefunction(ac.spawn_boot_assign)
    assert list(inspect.signature(ac.run_boot_assign).parameters)[:2] == ["registry", "net_asset"]
    assert len(inspect.signature(ac.spawn_boot_assign).parameters) >= 2
    assert isinstance(ac._BG_TASKS, set)
