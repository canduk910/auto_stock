"""사이클 128 P0-5 — AST 영구 가드.

`src/db/` 전체에서 `.range(0, 9999)` 패턴 잔존 0건 영구 검증.

Supabase PostgREST max-rows 한도 (기본 1000행) 가 `.range(0, 9999)` 를 silent cap →
부분 집계 결함. 사이클 126 시작 + 사이클 128 완료 영역 영구 폐기 의무.

예외 화이트리스트:
- 본 가드 테스트 파일 자체 (false-positive 방지)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

# 사이클 137 (2026-06-15) — 카드 #25 AST DRY 헬퍼 모듈 마이그레이션.
from tests.unit.ast._ast_helpers import read_module_source as _read

pytestmark = pytest.mark.unit


def _find_range_9999_calls(file_path: Path) -> list[int]:
    """파일 내 `.range(0, 9999)` 호출 라인 번호 리스트."""
    try:
        src = _read(file_path)
    except (UnicodeDecodeError, FileNotFoundError):
        return []

    try:
        tree = ast.parse(src, filename=str(file_path))
    except SyntaxError:
        return []

    matches: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            is_range_method = isinstance(func, ast.Attribute) and func.attr == "range"
            if is_range_method and len(node.args) >= 2:
                a, b = node.args[0], node.args[1]
                if (
                    isinstance(a, ast.Constant) and a.value == 0
                    and isinstance(b, ast.Constant) and b.value == 9999
                ):
                    matches.append(node.lineno)
    return matches


def test_g_ast_range1_src_db_no_range_9999_silent_cap():
    """G-AST-RANGE1: `src/db/` 전체 `.range(0, 9999)` 패턴 잔존 0건.

    사이클 128 영구 가드 — PostgREST max-rows silent cap 영역 영구 폐기.
    """
    src_db = Path("src/db")
    assert src_db.is_dir(), f"{src_db} 디렉토리 없음"

    violations: dict[str, list[int]] = {}
    for py_file in src_db.rglob("*.py"):
        # 본 가드 테스트 파일 자체 제외
        if "test_cycle128_ast_no_range_9999" in py_file.name:
            continue
        lines = _find_range_9999_calls(py_file)
        if lines:
            violations[str(py_file)] = lines

    assert not violations, (
        f"사이클 128 영구 가드 — `src/db/` 내 .range(0, 9999) 잔존 차단.\n"
        f"silent cap 영역 영구 폐기 의무 (PostgREST 1000행 한도).\n"
        f"위반: {violations}"
    )


def test_g_ast_range2_stock_master_get_stats_no_range_9999():
    """G-AST-RANGE2: `src/db/stock_master.py::get_stats()` 본체 `.range(0, 9999)` 잔존 0건.

    사이클 126 부분 시정 + 사이클 128 완전 폐기 영구 가드.
    """
    src_file = Path("src/db/stock_master.py")
    assert src_file.exists(), "stock_master.py 미존재"

    tree = ast.parse(_read(src_file))
    violations: list[int] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_stats":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    if isinstance(func, ast.Attribute) and func.attr == "range":
                        if len(sub.args) >= 2:
                            a, b = sub.args[0], sub.args[1]
                            if (
                                isinstance(a, ast.Constant) and a.value == 0
                                and isinstance(b, ast.Constant) and b.value == 9999
                            ):
                                violations.append(sub.lineno)

    assert not violations, (
        f"사이클 128 — get_stats() 본체 .range(0, 9999) 영구 폐기. 잔존: {violations}"
    )
