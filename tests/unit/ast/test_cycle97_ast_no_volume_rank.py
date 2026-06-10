"""사이클 97 H-5 — AST 영구 가드: `volume-rank` URL + `FHPST01710000` TR_ID 영구 차단 (HIGH).

명세 (`_workspace/red/cycle97_fluctuation_api_replacement.md`):

- 사이클 89/91/94/96 회귀 영역 영구 차단 (silent 결함 미래 재발 영구 차단)
- KIS volume_rank API 자체 폐기 영역 영속:
  - URL: `/uapi/domestic-stock/v1/quotations/volume-rank`
  - TR_ID: `FHPST01710000`
- AST 정적 가드 = scanner.py source 전수 grep

검증 패턴 (AST + raw text grep):
- scanner.py source 에 `volume-rank` 문자열 부재 (URL 영역)
- scanner.py source 에 `FHPST01710000` 문자열 부재 (TR_ID 영역)
- scanner.py source 에 `_fetch_volume_rank` 함수 정의 부재 (AST FunctionDef)
- scanner.py source 에 `_VOLUME_RANK_URL` / `_VOLUME_RANK_TR_ID` 상수 정의 부재 (AST Assign)

Red 상태 (사이클 97): production 코드 영속 → FAIL.

영속 의무:
- 사이클 81 `bfdy_clpr` AST 답습 (silent 결함 영구 차단 패턴)
- 사이클 88 G-REJECT 답습 (외부 LLM 영구 차단 정적 검증)
- 사이클 96 H-5 답습 (`"0000"` 시장코드 영역 영구 차단 패턴 확장)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _scanner_module_path() -> Path:
    """scanner.py 모듈 절대 경로."""
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__)


def _scanner_module_source() -> str:
    """scanner.py source text."""
    return _scanner_module_path().read_text(encoding="utf-8")


def test_h5_no_volume_rank_url_literal():
    """H-5.a: scanner.py source 에 `volume-rank` URL 문자열 영구 부재.

    검증 영역:
    - `/uapi/domestic-stock/v1/quotations/volume-rank` URL 영역 영구 차단
    - 사이클 89/91/94/96 영역 silent 결함 회귀 영구 차단

    Red 상태 (사이클 97): production 코드 `_VOLUME_RANK_URL = "/uapi/.../volume-rank"` 영속 → FAIL.

    Green (backend-dev): scanner.py 에서 URL 영역 전수 제거 → PASS.
    """
    source = _scanner_module_source()

    forbidden = "volume-rank"
    assert forbidden not in source, (
        f"\n사이클 97 H-5.a 위반 — `volume-rank` URL 문자열 영속:\n"
        f"  금지 영역: {forbidden!r}\n"
        f"  사이클 89/91/94/96 영역 silent 결함 영구 차단 의무\n"
        f"  사이클 97 시정 = `/uapi/domestic-stock/v1/ranking/fluctuation` 영역 영속"
    )


def test_h5_no_fhpst01710000_tr_id():
    """H-5.b: scanner.py source 에 `FHPST01710000` TR_ID 문자열 영구 부재.

    KIS volume_rank TR_ID = FHPST01710000 (사이클 89/91/94/96 영역)
    KIS fluctuation TR_ID = FHPST01700000 (사이클 97 신규 영역)

    Red 상태 (사이클 97): production 코드 영속 → FAIL.
    Green (backend-dev): scanner.py 에서 TR_ID 영역 전수 제거 → PASS.
    """
    source = _scanner_module_source()

    forbidden = "FHPST01710000"
    assert forbidden not in source, (
        f"\n사이클 97 H-5.b 위반 — `FHPST01710000` TR_ID 문자열 영속:\n"
        f"  금지 영역: {forbidden!r}\n"
        f"  사이클 97 시정 = `FHPST01700000` (fluctuation) 영역 영속\n"
        f"  KIS 정본: fluctuation.py `tr_id = \"FHPST01700000\"`"
    )


def test_h5_no_fetch_volume_rank_function_def():
    """H-5.c: scanner.py AST 에 `_fetch_volume_rank` 함수 정의 영구 부재.

    검증 영역: AST FunctionDef / AsyncFunctionDef 전수 검사.

    Red 상태 (사이클 97): production 코드 영속 → FAIL.
    Green (backend-dev): 함수 삭제 → PASS.
    """
    source = _scanner_module_source()
    tree = ast.parse(source)

    found_function_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_fetch_volume_rank":
                found_function_names.append(node.name)

    assert not found_function_names, (
        f"\n사이클 97 H-5.c 위반 — `_fetch_volume_rank` 함수 정의 영속:\n"
        f"  발견: {found_function_names}\n"
        f"  사이클 89/91/96 영역 silent 결함 영구 차단 의무\n"
        f"  사이클 97 시정 = `_fetch_fluctuation` 영역 영속"
    )


def test_h5_no_volume_rank_constant_assigns():
    """H-5.d: scanner.py AST 에 `_VOLUME_RANK_URL` / `_VOLUME_RANK_TR_ID` /
    `_MARKET_INPUT_ISCD` 상수 정의 영구 부재.

    검증 영역: AST Assign / AnnAssign 전수 검사.

    Red 상태 (사이클 97): production 코드 영속 → FAIL.
    Green (backend-dev): 상수 삭제 → PASS.
    """
    source = _scanner_module_source()
    tree = ast.parse(source)

    forbidden_names = {"_VOLUME_RANK_URL", "_VOLUME_RANK_TR_ID", "_MARKET_INPUT_ISCD"}
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id in forbidden_names:
                found.append(node.target.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in forbidden_names:
                    found.append(target.id)

    assert not found, (
        f"\n사이클 97 H-5.d 위반 — 폐기 상수 영속:\n"
        f"  발견: {found}\n"
        f"  사이클 89/91/94/96 영역 silent 결함 영구 차단 의무\n"
        f"  사이클 97 시정 영역:\n"
        f"    - _VOLUME_RANK_URL → _FLUCTUATION_URL\n"
        f"    - _VOLUME_RANK_TR_ID → _FLUCTUATION_TR_ID\n"
        f"    - _MARKET_INPUT_ISCD → _FLUCTUATION_MARKET_INPUT_ISCD"
    )
