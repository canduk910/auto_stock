"""사이클 110 HIGH-2 (G-AST1) — 사이클 101 영구 폐기 영역 import 영구 부재 AST 가드.

Red 명세 (`_workspace/red/cycle110_silent_defect_fix.md`):

사이클 101 (Q68=A+Q69=B) 영구 폐기 영역:
- `fetch_top_500_universe`
- `_universe_eager_refresh_loop`
- `_scanner_upsert_loop` (alias)

`src/routes/stock_master.py` 영역 영구 영속이 에서 위 3 식별자 import 0건 영구 영속이.
미래 silent 결함 영역 영구 차단 = 회귀 시 즉시 검출 (AST 정적 검증).

위험 등급 HIGH (silent 결함 영구 차단 영역 영구 영속이 + 미래 영구 차단 패턴 신설).

영속 의무 매트릭스 영구 영속:
- 사이클 101 영속 (`fetch_top_500_universe` + `_universe_eager_refresh_loop` 영구 폐기)
- 사이클 110 영속 (silent 결함 영역 영구 영속이 영구 시정 + 미래 회귀 영구 차단)
- 사이클 78 G-AST1 패턴 답습 (AST 영구 가드 신설 영역)
- 사이클 79 G-AST2 패턴 답습 (정적 검증 영역)
- 사이클 98 G-DOC1 영속 (영역 영구 영속이 docstring 영역 영속)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# 사이클 101 영구 폐기 영역 영구 영속이 (영구 부재 의무)
FORBIDDEN_IDENTIFIERS = {
    "fetch_top_500_universe",
    "_universe_eager_refresh_loop",
    "_scanner_upsert_loop",  # alias 영역 영구 영속이
}


# 사이클 136 (2026-06-15) — 카드 #25 AST DRY 헬퍼 모듈 영역 영구 영속 마이그레이션.
from tests.unit.ast._ast_helpers import read_module_source as _read_module


def _read_routes_stock_master() -> str:
    """`src/routes/stock_master.py` 영역 영구 영속이 소스 영역 읽기 (헬퍼 위임 영속)."""
    project_root = Path(__file__).resolve().parents[3]
    path = project_root / "src" / "routes" / "stock_master.py"
    assert path.exists(), f"routes/stock_master.py 영역 영구 영속이 부재: {path}"
    return _read_module(path)


def test_g_ast1_no_deprecated_universe_imports():
    """G-AST1: `src/routes/stock_master.py` 영역 영구 영속이 에 사이클 101 영구 폐기 영역 import 0건.

    AST 정적 검증 의무:
    - `from src.engine.scanner import (fetch_top_500_universe, ...)` 영구 부재
    - `from src.engine.scanner import (_universe_eager_refresh_loop, ...)` 영구 부재
    - `as _scanner_upsert_loop` alias 영구 부재

    미래 회귀 영역 영구 차단 = 사이클 101 영구 폐기 영역 재도입 시 즉시 검출.
    """
    src = _read_routes_stock_master()
    tree = ast.parse(src)

    found_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                # import 이름 영역 영구 영속이 검증
                if alias.name in FORBIDDEN_IDENTIFIERS:
                    found_imports.append(
                        f"L{node.lineno}: from {node.module} import {alias.name}"
                    )
                # alias 영역 영구 영속이 검증 (as _scanner_upsert_loop 영역)
                if alias.asname and alias.asname in FORBIDDEN_IDENTIFIERS:
                    found_imports.append(
                        f"L{node.lineno}: from {node.module} import {alias.name} as {alias.asname}"
                    )

    assert not found_imports, (
        f"사이클 101 영구 폐기 영역 import 영역 영구 영속이 영구 잔존 ({len(found_imports)}건): "
        f"{found_imports}. 사이클 110 시정 영역 영구 영속이 의무 위반 "
        "(미래 silent 결함 영역 영구 차단 가드)"
    )


def test_g_ast1_full_universe_load_once_called():
    """G-AST1-bis: `_full_universe_load_once` 호출 영역 영구 영속이 ≥1건 (사이클 110 시정 영역).

    AST 정적 검증 의무:
    - `from src.engine.scanner import _full_universe_load_once` ≥1건
    - 또는 `_full_universe_load_once(` 호출 ≥1건

    사이클 110 시정 영역 영구 영속이 정합성 영구 검증.

    사이클 131 의미 전환 (카드 #22 — refactor-review 권고 채택) — 사이클 66 K-2 패턴 답습:
    - Red 시점 (사이클 110/127) = `from src.engine.scanner import _full_universe_load_once` (모듈 상단 import)
    - Green 시점 (사이클 131) = `_resolve_once_callable("universe")` 헬퍼 영역 내부에서
      `from src.engine import scanner as _scanner` lazy import + `_scanner._full_universe_load_once` 호출.
      모듈 상단 import 폐기 + lazy import + 헬퍼 dispatch chain.
    - 핵심 의도 보존: `_full_universe_load_once` 영역 영속 + 호출 영역 영속.
      라우트 → (헬퍼 dispatch) → `_full_universe_load_once` chain 영속.

    의미 보존 영역:
    - 사이클 110 silent 결함 (사이클 101 시정 동행 누락) 영구 차단 의무 영속
    - 호출 영역 ≥ 1건 영속 (라우트 본체 OR 헬퍼 dispatch 영역 흡수 OR)
    """
    src = _read_routes_stock_master()
    tree = ast.parse(src)

    has_import = False
    has_call = False
    # 사이클 131 — Attribute access `_scanner._full_universe_load_once` 또는 동등 영속 검증
    has_attr_access = False

    for node in ast.walk(tree):
        # import 영역 영구 영속이 검증 (모듈 상단 또는 헬퍼 내부 lazy import 모두 흡수)
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "_full_universe_load_once":
                    has_import = True
        # 호출 영역 영구 영속이 검증
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "_full_universe_load_once":
                has_call = True
            elif isinstance(func, ast.Attribute) and func.attr == "_full_universe_load_once":
                has_call = True
        # 사이클 131 — Attribute access (호출 아닌 함수 객체 반환 영역) 검증
        # `return _scanner._full_universe_load_once` 패턴 영속 의무
        if isinstance(node, ast.Attribute) and node.attr == "_full_universe_load_once":
            has_attr_access = True

    # 사이클 131 의미 전환 — import OR attr_access (lazy import + 함수 객체 반환 패턴 영속)
    assert has_import or has_attr_access, (
        "`_full_universe_load_once` 영역 영구 영속이 부재 — "
        "사이클 110 시정 영역 영구 영속이 미적용 + 사이클 131 헬퍼 dispatch lazy import 영역 영속 의무 위반"
    )
    # 호출 영역 또는 함수 객체 반환 영역 OR (사이클 131 헬퍼 dispatch chain 영속)
    assert has_call or has_attr_access, (
        "`_full_universe_load_once()` 호출 영역 영구 영속이 부재 — "
        "사이클 110 시정 영역 영구 영속이 미적용 + 사이클 131 헬퍼 dispatch chain 영역 영속 의무 위반"
    )
