"""사이클 81 (2026-06-08) Red — AST 정적 가드 (A-3 + F-2, HIGH).

> **선행 명세**: `_workspace/red/cycle81_price_filter_key_fix.md` (§A-3, §F-2)
> **자문 응답**: domain-expert (CTPF1002R 정본 키 확정 — `bfdy_clpr` only, `prdy_clpr`/`acml_tr_pbmn` 잔존 영구 차단)
> **선례**: 사이클 65 G-AST + 사이클 64 G-3 패턴 답습

가드:
- A-3 (HIGH): `_apply_price_filter` 영역 `"prdy_clpr"` 문자열 잔존 0건 (사이클 64 잔존 영구 차단)
- F-2 (HIGH): `_get_acml_tr_pbmn` 영역 `"acml_tr_pbmn"` 문자열 잔존 0건 + 2순위 폴백 분기 제거 검증

CLAUDE.md 절대 규칙 보호:
- "**WebSocket 시세 보유·익일청산 우선 보장**" — 미존재 키 영구 무력화 결함 영구 차단
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

# 사이클 137 (2026-06-15) — 카드 #25 AST DRY 헬퍼 모듈 마이그레이션.
from tests.unit.ast._ast_helpers import read_module_source as _read

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼: scanner.py 모듈 AST 파싱
# ---------------------------------------------------------------------------
def _load_scanner_tree() -> tuple[ast.Module, str]:
    scanner_path = Path("src/engine/scanner.py")
    assert scanner_path.exists(), f"scanner.py 경로 결함: {scanner_path.resolve()}"
    source = _read(scanner_path)
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        pytest.fail(f"scanner.py SyntaxError: {e}")
    return tree, source


def _find_func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef | None:
    """모듈 트리에서 (Async)FunctionDef 한 개 찾기."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    return None


def _collect_str_constants(func: ast.AST) -> list[tuple[int, str]]:
    """함수 본체에서 문자열 상수 (라인번호, 값) 수집."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append((node.lineno, node.value))
    return found


# ===========================================================================
# A-3 [HIGH]: `_apply_price_filter` 영역 "prdy_clpr" 잔존 0건
# ===========================================================================
def test_A3_apply_price_filter_no_prdy_clpr_literal():
    """A-3 (HIGH): `_apply_price_filter` 본체에 `"prdy_clpr"` 문자열 0건.

    CTPF1002R 정본 키 = `bfdy_clpr` 전용. `prdy_clpr` 잔존 = 사이클 64 결함 영속.

    AST 정적 검증 — 함수 본체 한정 (모듈 다른 함수의 prdy_clpr 호환 허용).
    """
    tree, _ = _load_scanner_tree()
    func = _find_func(tree, "_apply_price_filter")
    assert func is not None, "`_apply_price_filter` 함수 미발견 — scanner.py 영역 위반"

    constants = _collect_str_constants(func)
    violations = [
        (lineno, val) for (lineno, val) in constants
        if val == "prdy_clpr"
    ]

    assert not violations, (
        f"A-3 (HIGH) `_apply_price_filter` 본체에 `\"prdy_clpr\"` 잔존 {len(violations)}건. "
        f"CTPF1002R 정본 키 = `bfdy_clpr` 전용. 사이클 64 결함 영속 차단:\n"
        + "\n".join(f"  L{ln}: {repr(v)}" for (ln, v) in violations)
    )


# ===========================================================================
# A-3-BIS: `_apply_price_filter` 영역 "bfdy_clpr" 정본 키 존재 검증
# ===========================================================================
def test_A3_BIS_apply_price_filter_has_bfdy_clpr_literal():
    """A-3-BIS: `_apply_price_filter` 본체에 `"bfdy_clpr"` 문자열 ≥1건.

    Green 시정 후 정본 키 사용 검증 (Red 단계 FAIL → Green PASS).
    """
    tree, _ = _load_scanner_tree()
    func = _find_func(tree, "_apply_price_filter")
    assert func is not None

    constants = _collect_str_constants(func)
    bfdy_count = sum(1 for (_, val) in constants if val == "bfdy_clpr")

    assert bfdy_count >= 1, (
        f"A-3-BIS: `_apply_price_filter` 본체에 `\"bfdy_clpr\"` 정본 키 ≥1건 의무. "
        f"실제 {bfdy_count}건 — Green 시정 미적용."
    )


# ===========================================================================
# F-2 [HIGH]: `_get_acml_tr_pbmn` 영역 "acml_tr_pbmn" 잔존 0건
# ===========================================================================
def test_F2_get_acml_tr_pbmn_no_acml_tr_pbmn_literal_in_fallback():
    """F-2 (HIGH): `_get_acml_tr_pbmn` 본체에 `"acml_tr_pbmn"` 문자열 0건.

    CTPF1002R 미존재 키. 2순위 폴백 폐기 = `acml_tr_pbmn` 키 조회 코드 제거.

    AST 정적 검증 — 함수 본체 한정.
    """
    tree, _ = _load_scanner_tree()
    func = _find_func(tree, "_get_acml_tr_pbmn")
    assert func is not None, "`_get_acml_tr_pbmn` 함수 미발견 — scanner.py 영역 위반"

    constants = _collect_str_constants(func)
    violations = [
        (lineno, val) for (lineno, val) in constants
        if val == "acml_tr_pbmn"
    ]

    assert not violations, (
        f"F-2 (HIGH) `_get_acml_tr_pbmn` 본체에 `\"acml_tr_pbmn\"` 잔존 {len(violations)}건. "
        f"CTPF1002R 미존재 키 2순위 폴백 폐기 의무:\n"
        + "\n".join(f"  L{ln}: {repr(v)}" for (ln, v) in violations)
    )


# ===========================================================================
# F-2-BIS: `_get_acml_tr_pbmn` 영역 stock_master 호출 0건 (정적)
# ===========================================================================
def test_F2_BIS_get_acml_tr_pbmn_no_stock_master_call():
    """F-2-BIS (HIGH): `_get_acml_tr_pbmn` 본체에 stock_master 모듈 호출 0건.

    2순위 폴백 폐기 = `from src.db.stock_master import get` / `stock_master.get(...)` 호출 코드 제거.

    AST 정적 가드 — Import + Attribute 호출 모두 검사.
    """
    tree, _ = _load_scanner_tree()
    func = _find_func(tree, "_get_acml_tr_pbmn")
    assert func is not None

    violations: list[str] = []
    for node in ast.walk(func):
        # ImportFrom: `from src.db.stock_master import ...`
        if isinstance(node, ast.ImportFrom):
            if node.module and "stock_master" in node.module:
                violations.append(
                    f"L{node.lineno}: ImportFrom `{node.module}` 잔존 (2순위 폴백 코드)"
                )
        # Attribute 호출: `stock_master.get(...)` / `_sm_get(...)`
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                # xxx.stock_master.* 또는 stock_master.get 형태
                if isinstance(fn.value, ast.Name) and "stock_master" in (fn.value.id or ""):
                    violations.append(
                        f"L{node.lineno}: Attribute 호출 `{fn.value.id}.{fn.attr}` 잔존"
                    )

    assert not violations, (
        f"F-2-BIS (HIGH) `_get_acml_tr_pbmn` 본체에 stock_master 호출 잔존 {len(violations)}건. "
        f"2순위 폴백 폐기 의무:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
