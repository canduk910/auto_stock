"""사이클 99 G-DEFAULT1 — `_fetch_fluctuation` 시그너처 AST 영구 가드 (HIGH).

명세 (`_workspace/red/cycle99_pagination_removal_60_ticker_persistence.md`):

- KIS API 본질 한계 영구 확정 = 단일 페이지 30 ticker 한도 + tr_cont "M" 영구 비반환
- 사이클 99 = 페이징 영역 영구 폐기 + 60 ticker 영구 영속 명문화

AST 영구 가드 매트릭스 (`FunctionDef.args.defaults`):
- 영속 영역 (영구 영속):
  - `top_n: int = 30` (KIS API 본질 한계 영구 영속)
- 영구 차단 영역 (silent 결함 영구 차단):
  - `top_n: int = 250` (사이클 91/94/96/97 영역)
  - `top_n: int = 500` (사이클 91 영역)
  - `max_pages: int = *` (페이징 안전 마진 영역)
  - `tr_cont: str = *` (KIS 페이징 인자 영역)

Red 상태 (사이클 99): 사이클 97 영역 `top_n=250, max_pages=17` 영속 → FAIL.

Green (backend-dev): 사이클 99 시그너처 영역 시정 → PASS.

영속 의무:
- 미래 페이징 영역 재도입 silent 결함 영구 차단 (AST 정적 가드)
- KIS API 본질 한계 영구 영속 명문화 패턴 신설
- 사이클 81 / 97 / 98 AST 가드 패턴 답습 (silent 결함 영구 차단 패턴)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit


def _scanner_module_path() -> Path:
    """scanner.py 모듈 절대 경로."""
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__)


def _fetch_fluctuation_function_node() -> ast.AsyncFunctionDef:
    """`_fetch_fluctuation` AST 함수 노드 추출."""
    source = read_module_source(_scanner_module_path())
    node = find_function_def(source, "_fetch_fluctuation")
    if isinstance(node, ast.AsyncFunctionDef):
        return node
    pytest.fail(
        "\n사이클 99 G-DEFAULT1 Red 상태 — `_fetch_fluctuation` AST 노드 추출 실패.\n"
        "  사이클 97 영역 = `_fetch_fluctuation` 신규 함수 영속 의무"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_fetch_fluctuation` 함수 자체 영구 폐기 "
        "(fluctuation API → market_cap FHPST01740000 전환). "
        "사이클 99 시점 시그너처 AST 가드 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_g_default1_top_n_default_30_persistence_and_pagination_args_forbidden():
    """G-DEFAULT1: `_fetch_fluctuation` 시그너처 영역 AST 영구 가드.

    검증 매트릭스 (사이클 99 영역 영구 영속):

    1. 영속 영역 (영구 영속):
       - `top_n` 인자 기본값 = 30 (KIS API 본질 한계 영구 영속)

    2. 영구 차단 영역 (silent 결함 영구 차단):
       - `top_n` 인자 기본값 ∈ {250, 500} 영구 차단 (사이클 91/94/96/97 영역)
       - `max_pages` 인자 영구 부재 (페이징 안전 마진 영역 영구 폐기)
       - `tr_cont` 인자 영구 부재 (KIS 페이징 인자 영역 영구 폐기)

    Red 상태 (사이클 99): 사이클 97 영역 시그너처 `top_n=250, max_pages=17` 영속 → FAIL.

    Green (backend-dev): 사이클 99 시그너처 영역 시정 의무 → PASS.
        - `top_n: int = 250` → `top_n: int = 30` (KIS API 본질 한계 영구 영속)
        - `max_pages: int = 17` 인자 영구 폐기
        - `tr_cont` 인자 영구 부재 (KIS 페이징 인자 영역 영구 폐기)

    영속 의무:
    - 미래 페이징 영역 재도입 silent 결함 영구 차단 (AST 정적 가드)
    - KIS API 본질 한계 영구 영속 명문화 패턴 신설 (사이클 99 패턴)
    - 사이클 81 `bfdy_clpr` AST + 사이클 98 G-AST1 답습 (silent 결함 영구 차단)
    """
    node = _fetch_fluctuation_function_node()

    # AST 인자 영역 전체 (positional + kwonly)
    positional_args = list(node.args.args)
    kwonly_args = list(node.args.kwonlyargs)
    all_args = positional_args + kwonly_args
    arg_names = [a.arg for a in all_args]

    violations: list[str] = []

    # 가드 1: 영구 폐기 영역 — `max_pages` 인자 영구 부재
    if "max_pages" in arg_names:
        violations.append(
            f"  - `max_pages` 인자 영속 위반 (페이징 안전 마진 영역 영구 폐기 의무)\n"
            f"    현재 인자: {arg_names}\n"
            f"    KIS API 본질 한계: 페이징 미지원 영구 확정 → max_pages 영역 영구 무용\n"
            f"    Green: `max_pages: int = 17` 인자 영구 폐기 의무"
        )

    # 가드 2: 영구 폐기 영역 — `tr_cont` 인자 영구 부재
    if "tr_cont" in arg_names:
        violations.append(
            f"  - `tr_cont` 인자 영속 위반 (KIS 페이징 인자 영역 영구 폐기 의무)\n"
            f"    현재 인자: {arg_names}\n"
            f"    KIS API 본질 한계: 페이징 미지원 영구 확정 → tr_cont 영역 영구 무용\n"
            f"    Green: `tr_cont` 인자 영구 폐기 의무"
        )

    # 가드 3: 영속 영역 — `top_n` 인자 영속 + 기본값 = 30 (KIS API 본질 한계 영구 영속)
    # AST `args.defaults` = positional 인자 끝부터 매핑 (kwonly_defaults 분리)
    # `top_n` 위치 식별 + defaults 매핑 추출
    top_n_default_value = None
    if "top_n" in arg_names:
        # positional 인자 영역
        if "top_n" in [a.arg for a in positional_args]:
            top_n_idx = [a.arg for a in positional_args].index("top_n")
            defaults_offset = len(positional_args) - len(node.args.defaults)
            if top_n_idx >= defaults_offset:
                default_node = node.args.defaults[top_n_idx - defaults_offset]
                top_n_default_value = ast.literal_eval(default_node) \
                    if isinstance(default_node, ast.Constant) else None
        # kwonly 인자 영역
        elif "top_n" in [a.arg for a in kwonly_args]:
            kwonly_idx = [a.arg for a in kwonly_args].index("top_n")
            default_node = node.args.kw_defaults[kwonly_idx] \
                if kwonly_idx < len(node.args.kw_defaults) else None
            if default_node is not None and isinstance(default_node, ast.Constant):
                top_n_default_value = ast.literal_eval(default_node)
    else:
        violations.append(
            f"  - `top_n` 인자 부재 위반 (KIS API 본질 한계 영속 영역 의무)\n"
            f"    현재 인자: {arg_names}\n"
            f"    Green: `top_n: int = 30` 영구 영속 의무"
        )

    # 가드 4: `top_n` 기본값 = 30 (KIS API 본질 한계 영구 영속)
    if top_n_default_value is not None and top_n_default_value != 30:
        violations.append(
            f"  - `top_n` 기본값 = {top_n_default_value!r} 위반 (KIS API 본질 한계 영구 영속 위반)\n"
            f"    현재 기본값: {top_n_default_value}\n"
            f"    영속 영역: 30 (KIS API 단일 페이지 한도 영구 영속)\n"
            f"    영구 차단 영역: 250 (사이클 91/94/96/97) / 500 (사이클 91 초기)\n"
            f"    Green: `top_n: int = 30` 영구 영속 의무"
        )

    assert not violations, (
        f"\n사이클 99 G-DEFAULT1 위반 — `_fetch_fluctuation` 시그너처 영역 AST 영구 가드 위반:\n"
        + "\n".join(violations)
        + "\n\n"
        f"  KIS API 본질 한계 영구 확정 매트릭스:\n"
        f"    - volume_rank (FHPST01710000) = 단일 페이지 30 한도 + tr_cont 'M' 영구 비반환\n"
        f"    - fluctuation (FHPST01700000) = 단일 페이지 30 한도 + tr_cont 'M' 영구 비반환\n"
        f"    - KIS API 전체 영역 = 페이징 미지원 영구 확정\n"
        f"  사이클 99 영역 영구 영속:\n"
        f"    - 60 ticker 영구 영속 수용 (KOSPI 30 + KOSDAQ 30)\n"
        f"    - 페이징 영역 영구 폐기 (사이클 91~98 모든 시정 영구 무용)\n"
        f"    - AST 정적 가드 = 미래 페이징 영역 재도입 silent 결함 영구 차단\n"
        f"  명세 영속: `_workspace/red/cycle99_pagination_removal_60_ticker_persistence.md`\n"
        f"  silent 결함 영구 차단 21 회 누적 (사이클 60~98 + 99)"
    )
