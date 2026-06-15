"""사이클 101 G-PURGE1 — fluctuation 영구 폐기 AST 영구 가드 (MEDIUM).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사용자 결정 Q68=A 영속 (영구 폐기)**:
- `_fetch_fluctuation` 함수 정의 영구 폐기 (사이클 97 영속 → 사이클 101 폐기)
- `_FLUCTUATION_URL` 모듈 전역 영구 폐기
- `_FLUCTUATION_TR_ID` 모듈 전역 영구 폐기

검증 매트릭스 (사이클 66 K-2 의미 전환 패턴 답습):
- G-PURGE1-A: `_fetch_fluctuation` 함수 정의 0건 AST 정적
- G-PURGE1-B: `_FLUCTUATION_URL` 모듈 전역 0건 AST 정적
- G-PURGE1-C: `_FLUCTUATION_TR_ID` 모듈 전역 0건 AST 정적

Red 상태 (현재): 사이클 97 영속 → 3 영역 모두 존재 → FAIL.
Green (backend-dev): Q68=A 영구 폐기 후 모두 0건 영속.

영속 의무:
- 사이클 97 fluctuation 영역 폐기 (Q68=A 영속)
- 사이클 99 60 ticker 영역 자연 폐기 (market_cap 페이징 ~2,800 흡수)
- 미래 silent 복원 영역 영구 차단
- 매매 hot path 영향 0 (scanner 단계 영역)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source

pytestmark = pytest.mark.unit


def _scanner_source() -> str:
    import src.engine.scanner as scanner_mod
    return read_module_source(Path(scanner_mod.__file__))


def test_g_purge1_a_fetch_fluctuation_function_purged() -> None:
    """G-PURGE1-A: `_fetch_fluctuation` 함수 정의 0건 영속 (MEDIUM).

    Red 상태 (현재): 사이클 97 영속 → 함수 정의 존재 → FAIL.
    Green (backend-dev): Q68=A 영구 폐기 후 0건 영속.
    """
    source = _scanner_source()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_fetch_fluctuation":
                pytest.fail(
                    f"\n사이클 101 G-PURGE1-A 위반 — `_fetch_fluctuation` 함수 정의 영속 (Q68=A 영구 폐기 위반):\n"
                    f"  위치: scanner.py:{node.lineno}\n"
                    f"  Red 결함 가설: 사이클 97 영역 영속 (Q68=A 영구 폐기 위반)\n"
                    f"  Green (backend-dev): 함수 정의 + 모든 호출 사이트 영구 삭제 의무\n"
                    f"  사이클 99 영역 자연 폐기 (market_cap ~2,800 흡수)"
                )


def test_g_purge1_b_fluctuation_url_purged() -> None:
    """G-PURGE1-B: `_FLUCTUATION_URL` 모듈 전역 0건 영속 (MEDIUM)."""
    source = _scanner_source()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_FLUCTUATION_URL":
                    pytest.fail(
                        f"\n사이클 101 G-PURGE1-B 위반 — `_FLUCTUATION_URL` 영속:\n"
                        f"  위치: scanner.py:{node.lineno}\n"
                        f"  Green (backend-dev): Q68=A 영구 폐기 후 0건 영속 의무"
                    )


def test_g_purge1_c_fluctuation_tr_id_purged() -> None:
    """G-PURGE1-C: `_FLUCTUATION_TR_ID` 모듈 전역 0건 영속 (MEDIUM)."""
    source = _scanner_source()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_FLUCTUATION_TR_ID":
                    pytest.fail(
                        f"\n사이클 101 G-PURGE1-C 위반 — `_FLUCTUATION_TR_ID` 영속:\n"
                        f"  위치: scanner.py:{node.lineno}\n"
                        f"  Green (backend-dev): Q68=A 영구 폐기 후 0건 영속 의무"
                    )
