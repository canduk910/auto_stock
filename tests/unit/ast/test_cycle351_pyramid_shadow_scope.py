"""cycle351 Red — 피라미딩 셰도 leaf 의 범위 가드 (AST, 명세 §4-4).

명세(정본) = `_workspace/red/cycle351_pyramid_shadow_spec.md` §4-4 · §2-6.

셰도는 **매매 행위 0** 이 전제다(8영역 · `scheduler.py` · 전략 7파일 · `strategy_base.py` 무접촉,
DB 는 SELECT 만, KIS 호출 0). 이 파일은 그 전제를 코드 구조로 잰다.

- S1 — `pyramid_shadow` 를 import 하는 프로덕션 모듈 = `log_metrics_collector.py` **하나뿐**.
       (`log_analysis_engine.py` · `daily_metrics_snapshot.py` · `routes/log_reports.py` 는 콜렉터를 통해
       자동으로 실리므로 셰도를 직접 알면 안 된다 — §2-6.)
- S2 — leaf 는 매매·주문·세션·실시간·인증 모듈을 import 하지 않는다(함수 안 지연 import 포함).
- S3 — leaf 에 DB 쓰기 0: `pg.execute`/`executemany` 호출 0 + INSERT/UPDATE/DELETE SQL 문자열 0.
- S4 — leaf 최상단 import = 표준 라이브러리 + `src.engine.daily_emit_cap` 까지. pandas·DB·
       `kojiro_indicators`·`strategy_base` 는 함수 안 지연 import(S0 스크립트가 운영 컨테이너 `/tmp` 사본을
       import 해야 한다 — §3).
- S5 — 그 사본 import 가 실제로 된다(다른 이름·다른 경로로 로드해도 공개 API 가 살아 있다).

가드 설계 금기(에이전트 정의) 준수: `git grep`/`git ls-files` 대신 `Path.rglob` + AST, 주석·docstring 은
세지 않는다, `ast.dump` sha 핀 없음. 기존 digest·파일 수 핀(`test_cycle287_ast_scope.py` ·
`test_cycle290_ast_scope.py`)은 이 사이클이 정당하게 움직이는 두 파일 때문에 Green 이 갱신한다.
"""
from __future__ import annotations

import ast
import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
LEAF_REL = "src/engine/pyramid_shadow.py"
LEAF = ROOT / LEAF_REL
LEAF_MOD = "src.engine.pyramid_shadow"
COLLECTOR_REL = "src/engine/log_metrics_collector.py"

#: §2-6 — 콜렉터를 통해 자동으로 실리는 쪽. 셰도를 직접 알면 안 된다.
MUST_NOT_KNOW_SHADOW = (
    "src/engine/log_analysis_engine.py",
    "src/engine/daily_metrics_snapshot.py",
    "src/routes/log_reports.py",
)

#: §4-4 — leaf 가 import 하면 안 되는 모듈(정확히 그 모듈이거나 그 하위).
FORBIDDEN_FOR_LEAF = (
    "src.engine.order_engine",
    "src.engine.risk",
    "src.engine.scheduler",
    "src.engine.strategy_registry",
    "src.engine.session",
    "src.engine.scanner",
    "src.engine.strategies",
    "src.api.order",
    "src.api.base",
    "src.realtime",
    "src.auth",
)

#: 독립 검증 지적 #5·#24 — S3 를 허용 목록 방식으로 강화한다. leaf 가 import 할 수 있는
#: `src.db.*` 서브모듈과, 그 모듈 별칭에 대해 leaf 가 호출할 수 있는 속성(함수) 이름.
DB_ALLOWED_ATTRS = {
    "stock_master_daily": frozenset({"get_recent_daily"}),
    "trade_history": frozenset({"get_trade_pairs"}),
}

#: §4-4 — leaf 최상단에서 허용되는 비-표준 import.
TOP_LEVEL_ALLOWED_SRC = ("src.engine.daily_emit_cap",)

_SQL_WRITE_RE = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b", re.IGNORECASE)


def _require_leaf() -> str:
    if not LEAF.exists():  # pragma: no cover - Red 경로
        pytest.fail(f"Red — `{LEAF_REL}` 미생성 (cycle351 §1·§2 신규 leaf)")
    return LEAF.read_text(encoding="utf-8")


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _imported_names(path: Path, tree: ast.AST) -> list[str]:
    """파일 안(함수 안 포함) 모든 import 가 가리킬 수 있는 절대 모듈 이름 후보.

    `from a.b import c` → `a.b` 와 `a.b.c` 둘 다(서브모듈일 수 있다). 상대 import 는 파일 위치로 푼다.
    """
    pkg_parts = _module_name(path).split(".")[:-1]   # `__init__` 도 [:-1] 이면 그 패키지다
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            if mod:
                out.append(mod)
            out.extend(f"{mod}.{a.name}" if mod else a.name for a in node.names)
    return out


def _hits(name: str, target: str) -> bool:
    return name == target or name.startswith(target + ".")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _top_level_imports(tree: ast.Module) -> list[ast.stmt]:
    """모듈 본문 직속 + 최상단 if/try 블록 안의 import(실행 시점 = 모듈 로드)."""
    out: list[ast.stmt] = []

    def _scan(stmts):
        for st in stmts:
            if isinstance(st, (ast.Import, ast.ImportFrom)):
                out.append(st)
            elif isinstance(st, ast.If):
                _scan(st.body)
                _scan(st.orelse)
            elif isinstance(st, ast.Try):
                _scan(st.body)
                for h in st.handlers:
                    _scan(h.body)
                _scan(st.orelse)
                _scan(st.finalbody)

    _scan(tree.body)
    return out


# ===========================================================================
# S1 — leaf 를 import 하는 프로덕션 모듈은 콜렉터 하나
# ===========================================================================
def test_s1_only_log_metrics_collector_imports_the_leaf():
    importers: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts or path == LEAF:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(_hits(n, LEAF_MOD) for n in _imported_names(path, tree)):
            importers.add(str(path.relative_to(ROOT)).replace("\\", "/"))
    assert importers == {COLLECTOR_REL}, (
        f"`{LEAF_MOD}` 를 import 하는 프로덕션 모듈 = {sorted(importers)} (기대: 콜렉터 하나, §4-4)"
    )


@pytest.mark.parametrize("rel", MUST_NOT_KNOW_SHADOW)
def test_s1b_downstream_consumers_do_not_reference_the_shadow(rel):
    """§2-6 — 이 셋은 콜렉터를 통해 자동으로 싣는다. 셰도 식별자가 나타나면 배선이 새로 생긴 것이다."""
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    doc = _docstring_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and "pyramid" in node.id:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and "pyramid" in node.attr:
            found.append(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc \
                and "pyramid" in node.value:
            found.append(node.value[:60])
    assert not found, f"{rel} 이 셰도를 직접 참조한다: {found}"


# ===========================================================================
# S2 — 금지 import
# ===========================================================================
def test_s2_leaf_does_not_import_trading_order_session_realtime_auth():
    src = _require_leaf()
    names = _imported_names(LEAF, ast.parse(src))
    bad = sorted({n for n in names for f in FORBIDDEN_FOR_LEAF if _hits(n, f)})
    assert not bad, f"leaf 가 금지 모듈을 import 한다(함수 안 포함): {bad}"


# ===========================================================================
# S3 — DB 쓰기 0
# ===========================================================================
def test_s3_leaf_has_no_db_write_calls_or_sql_write_strings():
    src = _require_leaf()
    tree = ast.parse(src)
    doc = _docstring_nodes(tree)
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in {"execute", "executemany", "copy_records_to_table"}:
            calls.append(ast.unparse(node.func))
    assert not calls, f"leaf 에 DB 쓰기 호출: {calls} (§4-4 — SELECT 만)"
    sql = [n.value[:80] for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc
           and _SQL_WRITE_RE.search(n.value)]
    assert not sql, f"leaf 에 SQL 쓰기 문자열: {sql}"


def _leaf_db_module_aliases(tree: ast.AST) -> dict[str, str]:
    """이름(alias) → `src.db.<서브모듈>`. `import src.db.X as alias`/`import src.db.X`
    (이 경우 alias=X) 형태만 잡는다 — leaf 가 실제로 쓰는 형태(§2 어댑터 지연 import)."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("src.db."):
                    sub = a.name[len("src.db."):].split(".")[0]
                    bound = a.asname or a.name.split(".")[-1]
                    aliases[bound] = sub
    return aliases


def test_s3b_leaf_db_module_imports_are_allowlisted():
    """독립 검증 지적 #5·#24 — leaf 가 import 할 수 있는 `src.db.*` 서브모듈은
    `stock_master_daily`·`trade_history` 둘뿐이다. `import src.db.positions` 같은 쓰기 모듈
    import 는 호출 여부와 무관하게 이 시점에 이미 위반이다(M5 돌연변이가 여기서 잡힌다)."""
    src = _require_leaf()
    tree = ast.parse(src)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("src.db."):
                    sub = a.name[len("src.db."):].split(".")[0]
                    if sub not in DB_ALLOWED_ATTRS:
                        bad.append(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src.db."):
            sub = node.module[len("src.db."):].split(".")[0]
            if sub not in DB_ALLOWED_ATTRS:
                bad.append(node.module)
    assert not bad, f"leaf 가 허용 목록 밖 src.db 모듈을 import 한다: {bad} (허용: {sorted(DB_ALLOWED_ATTRS)})"


def test_s3c_leaf_db_attribute_calls_are_allowlisted():
    """독립 검증 지적 #5·#24 — leaf 가 `src.db.*` 별칭에 대해 호출할 수 있는 속성은
    `get_recent_daily`·`get_trade_pairs` 뿐이다. `trade_history_db.update_trade_status(...)`
    같은 쓰기 헬퍼 호출은 raw `execute`/SQL 문자열이 없어도 여기서 잡힌다(M6 돌연변이)."""
    src = _require_leaf()
    tree = ast.parse(src)
    aliases = _leaf_db_module_aliases(tree)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) and node.func.value.id in aliases:
            sub = aliases[node.func.value.id]
            if node.func.attr not in DB_ALLOWED_ATTRS.get(sub, frozenset()):
                bad.append(f"{node.func.value.id}.{node.func.attr}")
    assert not bad, f"leaf 의 src.db 호출이 허용 목록 밖이다: {bad}"


# ===========================================================================
# S4 — 최상단 import = 표준 라이브러리 + daily_emit_cap
# ===========================================================================
def test_s4_leaf_top_level_imports_are_stdlib_or_daily_emit_cap():
    src = _require_leaf()
    tree = ast.parse(src)
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    offenders = []
    for st in _top_level_imports(tree):
        if isinstance(st, ast.Import):
            mods = [a.name for a in st.names]
        else:
            if st.level:
                offenders.append(ast.unparse(st))
                continue
            base = st.module or ""
            mods = [base] if base != "src.engine" else [f"src.engine.{a.name}" for a in st.names]
        for m in mods:
            if m.split(".")[0] in stdlib or m in TOP_LEVEL_ALLOWED_SRC:
                continue
            offenders.append(ast.unparse(st))
    assert not offenders, (
        "leaf 최상단 import 는 표준 라이브러리 + `src.engine.daily_emit_cap` 까지다 — "
        f"pandas·DB·kojiro_indicators·strategy_base 는 함수 안 지연 import(§4-4): {offenders}"
    )


def test_s4b_leaf_defines_the_public_api_at_module_level():
    """§1·§2 이름 계약 — S0 스크립트와 콜렉터가 이 이름으로 부른다."""
    tree = ast.parse(_require_leaf())
    defs = {n.name: type(n).__name__ for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    assigns = {t.id for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
               for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
               if isinstance(t, ast.Name)}
    assert defs.get("overlay_ladder") == "FunctionDef", "순수 코어 `overlay_ladder` 는 동기 def"
    assert defs.get("no_add_flags") == "FunctionDef"
    assert defs.get("LadderConfig") == "ClassDef"
    assert defs.get("build_pyramid_shadow") == "AsyncFunctionDef", "어댑터는 async def"
    assert "LADDER_C" in assigns


# ===========================================================================
# S5 — /tmp 사본 import (S0 스크립트 경로)
# ===========================================================================
def test_s5_leaf_copy_is_importable_under_another_name(tmp_path):
    """§3 — 운영 이미지에는 새 leaf 가 없어 S0 스크립트가 컨테이너 `/tmp` 사본을 import 한다.
    다른 경로·다른 모듈 이름으로 로드해도 공개 API 가 살아 있어야 한다(상대 import·패키지 가정 금지)."""
    _require_leaf()
    copy = tmp_path / "pyramid_shadow_s0_copy.py"
    shutil.copyfile(LEAF, copy)
    spec = importlib.util.spec_from_file_location("pyramid_shadow_s0_copy", copy)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pyramid_shadow_s0_copy"] = mod
    try:
        spec.loader.exec_module(mod)
        for name in ("overlay_ladder", "no_add_flags", "LadderConfig", "LADDER_C"):
            assert hasattr(mod, name), name
        assert mod.LADDER_C.step_n == 1.0
    finally:
        sys.modules.pop("pyramid_shadow_s0_copy", None)
