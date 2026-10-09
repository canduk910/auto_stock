"""cycle416 Red — 시장 등락 통계 구조 가드 (G-416-1 ~ G-416-6).

명세: `_workspace/red/cycle416/breadth_spec.md` §5.1 · §5.2 · §7.4 · §8
계약: `_workspace/red/cycle416/breadth_contract.md` 「3. 구조 가드」

  G-416-1  leaf `src/engine/market_breadth.py` 는 순수하다 — `await`·`async def` 0 · 표준 라이브러리만 ·
           입출력/비동기/로깅/시계 모듈 import 0 · 벽시계 호출(`now()`/`today()`) 0.
  G-416-2  라우트는 KIS·스케줄러·8영역을 import 하지 않는다 · `krx` 는 모듈 참조로만 import 한다.
  G-416-3  라우트의 KRX 호출 = `krx.fetch_stk_bydd_trd` · `krx.fetch_ksq_bydd_trd` 두 이름뿐.
  G-416-4  라우트의 로그·응답 인자에 설정의 `.key` 가 들어가지 않는다.
  G-416-5  두 새 모듈을 import 하는 곳 = 라우트(leaf) · `src/main.py`(라우트) 뿐 — 매매 엔진·전략은 읽지 않는다.
  G-416-6  `src/api/krx.py` 무변경 — 최상위 정의 이름 집합 고정 + 각 정의 본문 sha256 핀
           (`ast.get_source_segment` — `ast.dump` 는 파이썬 버전마다 달라 쓰지 않는다).

소스 스캔은 `Path.rglob` + AST 로 한다(`git grep` 은 미추적 파일을 못 본다).
8영역·`scheduler.py` 의 **파일 무접촉**은 기존 가드
`tests/unit/ast/test_cycle222a3_ast_followup_fixes.py`(8영역 diff) 가 맡는다 — 여기서는 import 결합만 본다.

RED: 두 모듈 부재 → 파일 읽기 실패로 G-416-1~5 FAIL (G-416-6 은 지금도 초록 — 무변경 핀).
"""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
LEAF = SRC / "engine" / "market_breadth.py"
ROUTE = SRC / "routes" / "market_breadth.py"
KRX = SRC / "api" / "krx.py"

_FORBIDDEN_LEAF_MODULES = {
    "asyncio", "logging", "socket", "http", "urllib", "ssl", "sqlite3", "subprocess",
    "threading", "concurrent", "multiprocessing", "time", "httpx", "asyncpg", "src",
}
_EIGHT_AREA_MODULES = (
    "src.engine.risk", "src.engine.order_engine", "src.engine.session", "src.engine.scanner",
    "src.engine.strategy_registry", "src.api.order", "src.realtime", "src.auth",
)
_KIS_MODULES = ("src.api.base", "src.api.order", "src.auth")
_KRX_ALLOWED_CALLS = {"fetch_stk_bydd_trd", "fetch_ksq_bydd_trd"}

# krx.py 본문 핀 — main 3d6f7b52 (krx.py 최종 커밋 b615e03c) 의 `ast.get_source_segment` sha256.
# 이 핀이 깨졌다면 krx.py 를 고친 것이다: cycle416 은 krx.py 를 고치지 않는다(새 함수는 새 모듈에).
# 다른 사이클이 krx.py 를 정당하게 고쳤다면 그 사이클이 아래 값을 새 sha 로 갈아 쓴다.
_KRX_PINS = {
    "KrxApiError": "65131664409d0bdfaf75079d0333e04173313ec0b5a082dc955de0f6bd60d3c5",
    "fetch_krx_open_api": "d0e3d4b312c254b7ef0304ed8cb777db470ad0991b787372e90bb466ce5385ce",
    "fetch_stk_bydd_trd": "7f72811d8722c91ab6f1d2a0339b1bac78913cf1a7c89d9bfb4469e2cc154c9b",
    "fetch_ksq_bydd_trd": "7700f154341a7b8ccd008c2ca345cfcde24e0dadf0f5ec1cb9a05b1f385822ce",
    "fetch_stk_isu_base_info": "f4bdd33204a42b7b4f3cb525625204fbf73da151026a0673c989cabf2abfe8b4",
    "fetch_ksq_isu_base_info": "3fa76671348a64efb547798a813a357fdfa4f4b11bac1eed9b3adbb1fd82afab",
}


def _parse(path: Path) -> tuple[str, ast.Module]:
    text = path.read_text(encoding="utf-8")
    return text, ast.parse(text)


def _imported_modules(tree: ast.Module) -> list[tuple[str, list[str]]]:
    """(모듈 경로, import 된 이름들). `import a.b` → ("a.b", []) · `from a import b, c` → ("a", ["b","c"])."""
    out: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(a.name, []) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append(((node.module or ""), [a.name for a in node.names]))
    return out


def _under(mod: str, prefix: str) -> bool:
    return mod == prefix or mod.startswith(prefix + ".")


# ═════════════════════════════════════════════════════════════════════════════
# G-416-1 — leaf 순수성
# ═════════════════════════════════════════════════════════════════════════════

def test_g416_1_leaf_is_pure():
    text, tree = _parse(LEAF)
    asyncish = [
        type(n).__name__ for n in ast.walk(tree)
        if isinstance(n, (ast.Await, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith))
    ]
    assert asyncish == [], f"leaf 에 비동기 구문 {asyncish}"

    bad: list[str] = []
    for mod, _names in _imported_modules(tree):
        top = mod.split(".")[0]
        if mod == "__future__":
            continue
        if top in _FORBIDDEN_LEAF_MODULES or top not in sys.stdlib_module_names:
            bad.append(mod)
    assert bad == [], f"leaf import 는 표준 라이브러리(dataclasses·datetime·decimal·typing·enum 등)만 — {bad}"

    clock = [
        ast.get_source_segment(text, n) for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"now", "today", "utcnow", "monotonic"}
    ]
    assert clock == [], f"leaf 는 시계를 읽지 않는다(today·now 는 인자로 받는다) — {clock}"


# ═════════════════════════════════════════════════════════════════════════════
# G-416-2 — 라우트 import 결합
# ═════════════════════════════════════════════════════════════════════════════

def test_g416_2_route_imports_no_kis_scheduler_or_eight_areas():
    _, tree = _parse(ROUTE)
    mods = _imported_modules(tree)
    bad: list[str] = []
    for mod, names in mods:
        full = [mod] + [f"{mod}.{n}" for n in names]
        for m in full:
            if any(_under(m, p) for p in _KIS_MODULES + _EIGHT_AREA_MODULES):
                bad.append(m)
            if _under(m, "src.engine.scheduler"):
                bad.append(m)
        if any("kis" in n.lower() for n in names) or "kis" in mod.lower().split(".")[-1]:
            bad.append(f"{mod}:{names}")
    assert bad == [], f"라우트가 KIS·스케줄러·8영역에 묶였다 — {sorted(set(bad))}"

    krx_imports = [(m, n) for m, n in mods if m == "src.api.krx" or (m == "src.api" and "krx" in n)]
    assert any(m == "src.api" and "krx" in n for m, n in krx_imports), "`from src.api import krx` 모듈 참조가 없다"
    direct = [n for m, ns in krx_imports if m == "src.api.krx" for n in ns if n.startswith("fetch")]
    assert direct == [], (
        f"`from src.api.krx import {direct}` 금지 — 테스트가 `src.api.krx.fetch_*` 를 갈아끼우는 seam 이 사라진다"
    )
    leaf_ref = [(m, n) for m, n in mods if m == "src.engine" and "market_breadth" in n]
    assert leaf_ref, "leaf 는 `from src.engine import market_breadth` 모듈 참조로 쓴다(계약 2.4)"


# ═════════════════════════════════════════════════════════════════════════════
# G-416-3 — KRX 호출 이름
# ═════════════════════════════════════════════════════════════════════════════

def test_g416_3_route_calls_only_two_krx_functions():
    text, tree = _parse(ROUTE)
    krx_attrs = [
        n.attr for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "krx"
    ]
    calls = {a for a in krx_attrs if a.startswith("fetch")}
    assert calls == _KRX_ALLOWED_CALLS, f"KRX 호출 = {calls} (기대 {_KRX_ALLOWED_CALLS})"
    for banned in ("fetch_krx_open_api", "isu_base_info"):
        assert banned not in text, f"라우트에 `{banned}` — KRX 는 두 함수로만 부른다"


# ═════════════════════════════════════════════════════════════════════════════
# G-416-4 — 키 평문 미노출 (정적)
# ═════════════════════════════════════════════════════════════════════════════

_LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}


def _key_attrs(node: ast.AST) -> list[ast.Attribute]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Attribute) and n.attr == "key"]


def test_g416_4_key_never_passed_to_logger_or_response():
    text, tree = _parse(ROUTE)
    leaks: list[str] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        is_log = isinstance(f, ast.Attribute) and f.attr in _LOG_METHODS and (
            (isinstance(f.value, ast.Name) and f.value.id in {"logger", "logging", "log"})
        )
        is_resp = isinstance(f, ast.Name) and f.id in {"ApiResponse", "HTTPException"}
        is_exc = isinstance(f, ast.Name) and f.id.endswith(("Error", "Exception"))
        if is_log or is_resp or is_exc:
            for a in list(n.args) + [k.value for k in n.keywords]:
                if _key_attrs(a):
                    leaks.append(ast.get_source_segment(text, n) or "?")
    assert leaks == [], f"설정의 `.key` 가 로그·응답·예외 인자에 들어갔다 — {leaks}"


# ═════════════════════════════════════════════════════════════════════════════
# G-416-5 — 소비처 = 라우트·main 뿐 (매매 행위 무변경)
# ═════════════════════════════════════════════════════════════════════════════

def test_g416_5_only_route_and_main_import_new_modules():
    importers: dict[str, set[str]] = {"leaf": set(), "route": set()}
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for mod, names in _imported_modules(tree):
            if mod == "src.engine.market_breadth" or (mod == "src.engine" and "market_breadth" in names):
                importers["leaf"].add(rel)
            if mod == "src.routes.market_breadth" or (mod == "src.routes" and "market_breadth" in names):
                importers["route"].add(rel)
    assert importers["leaf"] == {"src/routes/market_breadth.py"}, (
        f"leaf 소비처 = 라우트 하나 — {sorted(importers['leaf'])} (엔진·전략이 읽으면 관찰 전용이 깨진다)"
    )
    assert importers["route"] == {"src/main.py"}, f"라우트 소비처 = main 하나 — {sorted(importers['route'])}"


# ═════════════════════════════════════════════════════════════════════════════
# G-416-6 — krx.py 무변경 (지금도 초록이어야 한다)
# ═════════════════════════════════════════════════════════════════════════════

def test_g416_6_krx_client_unchanged():
    text, tree = _parse(KRX)
    defs = {
        n.name: hashlib.sha256((ast.get_source_segment(text, n) or "").encode("utf-8")).hexdigest()
        for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert set(defs) == set(_KRX_PINS), (
        f"krx.py 최상위 정의가 바뀌었다 — 추가 {sorted(set(defs) - set(_KRX_PINS))} · "
        f"삭제 {sorted(set(_KRX_PINS) - set(defs))}. 새 함수는 새 모듈에 둔다"
    )
    changed = sorted(name for name, sha in defs.items() if sha != _KRX_PINS[name])
    assert changed == [], f"krx.py 본문 변경 — {changed}"
