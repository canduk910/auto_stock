"""사이클 100 G-DOC1 — 사이클 98 G-DOC1 영구 가드 영속 (LOW, 변경 0).

명세 (`_workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md`):

**사이클 100 = 영역 변경 0 영속 확인 가드**:
- 사이클 98 G-DOC1 영속 (`tests/unit/ast/test_cycle98_ast_chk_citation_required.py`) 영속
- `src/engine/scanner.py::_fetch_fluctuation` docstring 영역 `chk_fluctuation.py` 또는 `chk_*` 또는 `chk_` 인용 ≥1건 영속
- 사이클 100 = scanner.py 영역 변경 0 → 사이클 98 G-DOC1 영속 가드 PASS 의무

**Phase 1 진단 영속 영역 (사이클 100 Phase 1)**:
- 영역 1 (UI prefix 정정) + 영역 2 (주문 발주 시장 분기) = scanner.py 영역 영향 0
- 사이클 98 G-DOC1 = KIS 정본 영역 인용 의무 영구 가드 영속

검증 매트릭스:
- `_fetch_fluctuation` docstring 영역 `chk_` 인용 ≥1건 영속

**Red 상태**: 사이클 98 영속 = production 변경 0 → PASS (영속 확인 가드).

**Green**: 사이클 98 G-DOC1 영속 = PASS.

영속 의무:
- 사이클 98 G-DOC1 영속 (KIS chk_*.py main 호출 영역 정본 영속)
- 사이클 99 G-DOC1 영속 (KIS API 본질 한계 영구 명문화)
- 사이클 100 영역 변경 0 → 두 영역 모두 영속 가드 PASS 의무
- 매매 안전성 영역 영향 0 (영속 가드만)
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


def _get_fetch_fluctuation_docstring() -> str | None:
    """`_fetch_fluctuation` 함수 docstring 영역 추출."""
    source = _scanner_module_source()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_fetch_fluctuation":
                return ast.get_docstring(node)
    return None


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_fetch_fluctuation` 함수 자체 영구 폐기 "
        "(fluctuation API → market_cap FHPST01740000 전환). "
        "사이클 100 시점 G-DOC1 영속 가드 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_g_doc1_cycle98_chk_citation_persistence():
    """G-DOC1: 사이클 98 G-DOC1 영구 가드 영속 (LOW, 변경 0).

    검증 매트릭스 (사이클 100 영역 영구 영속):
    - `_fetch_fluctuation` docstring 영역 영속 (사이클 97 영역 신규 함수 영속)
    - docstring 영역 `chk_fluctuation.py` 또는 `chk_*` 또는 `chk_` 인용 ≥1건 영속 (사이클 98 G-DOC1 영속)
    - 사이클 100 = scanner.py 영역 변경 0 → 영속 가드 PASS 의무

    Red 상태 (사이클 100): 사이클 98 영속 = production 변경 0 → PASS (영속 확인 가드).

    Green: 사이클 98 G-DOC1 영속 = PASS.

    영속 의무:
    - 사이클 98 G-DOC1 (KIS chk_*.py main 호출 영역 정본 영속)
    - 사이클 99 G-DOC1 (KIS API 본질 한계 영구 명문화)
    - 사이클 100 영역 변경 0 → 두 영역 모두 영속 가드 PASS 의무
    """
    docstring = _get_fetch_fluctuation_docstring()
    assert docstring is not None, (
        "\n사이클 100 G-DOC1 Red 상태 — `_fetch_fluctuation` docstring 부재.\n"
        "  영속 의무: src/engine/scanner.py::_fetch_fluctuation docstring 영역 영속 (사이클 97 영역).\n"
        "  사이클 98 G-DOC1 영속: chk_fluctuation.py 영역 정본 인용 의무.\n"
        "  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )

    # 가드: `chk_` 인용 ≥1건 영속 (사이클 98 G-DOC1 영속)
    has_chk_citation = (
        "chk_fluctuation.py" in docstring
        or "chk_*" in docstring
        or "chk_" in docstring
    )
    assert has_chk_citation, (
        f"\n사이클 100 G-DOC1 위반 — 사이클 98 G-DOC1 영속 위반:\n"
        f"  기대: _fetch_fluctuation docstring 영역 `chk_fluctuation.py` 또는 `chk_*` 또는 `chk_` 인용 ≥1건 영속\n"
        f"  실제 docstring (excerpt):\n"
        f"  {docstring[:500]}\n"
        f"  결함 가설: 사이클 100 = scanner.py 영역 변경 0 영속 의무 — 사이클 98 G-DOC1 silent 삭제 영역 영구 차단\n"
        f"  영속 의무: 사이클 98 G-DOC1 (`tests/unit/ast/test_cycle98_ast_chk_citation_required.py`)\n"
        f"  KIS 정본 영역 위계: chk_*.py main 호출 영역 = 실측 영역 (운영 영역 정합 보장)\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )
