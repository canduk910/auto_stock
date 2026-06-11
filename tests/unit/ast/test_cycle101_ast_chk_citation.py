"""사이클 101 G-DOC1 — KIS MCP 정본 인용 AST 영구 가드 (HIGH).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사이클 98 G-DOC1 영속 (KIS chk_*.py main 호출 영역 정본 영속)**:
- 사이클 101 신규 함수 docstring 영역 = `chk_market_cap.py` + `chk_search_stock_info.py` 인용 의무
- 미래 KIS 정본 silent 누락 영역 영구 차단

검증 매트릭스 (사이클 98 G-DOC1 + 사이클 100 G-DOC1 영구 가드 답습):
- G-DOC1-A: `_fetch_market_cap_page` docstring 영역 `chk_market_cap.py` 또는 `chk_market_cap` 인용 ≥1건
- G-DOC1-B: `_full_universe_load_once` docstring 영역 `chk_search_stock_info.py` 또는 `chk_search_stock_info`
  또는 `CTPF1002R` 인용 ≥1건

Red 상태: 신규 함수 docstring 부재 또는 인용 부재.
Green (backend-dev): 정본 인용 의무 영속.

영속 의무:
- 사이클 98 G-DOC1 영구 가드 영속 (KIS 정본 인용 의무)
- 사이클 100 G-DOC1 영속 (3 prefix 패턴 답습)
- 매매 안전성 영역 영향 0 (정적 가드)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _scanner_source() -> str:
    """scanner.py source text."""
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__).read_text(encoding="utf-8")


def _get_docstring(func_name: str) -> str | None:
    """`scanner.py` 함수 docstring 추출."""
    source = _scanner_source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                return ast.get_docstring(node)
    return None


def test_g_doc1_a_fetch_market_cap_page_cites_chk_market_cap() -> None:
    """G-DOC1-A: `_fetch_market_cap_page` docstring `chk_market_cap` 인용 의무 (HIGH).

    검증 매트릭스 (사이클 98 G-DOC1 영속):
    - docstring 영역 `chk_market_cap.py` 또는 `chk_market_cap` 인용 ≥1건

    Red 상태: 신규 함수 부재 또는 인용 부재.
    Green (backend-dev): chk_market_cap.py main 호출 영역 정본 인용 의무.
    """
    docstring = _get_docstring("_fetch_market_cap_page")

    assert docstring is not None, (
        "\n사이클 101 G-DOC1-A Red 상태 — `_fetch_market_cap_page` docstring 부재.\n"
        "  Green (backend-dev): src/engine/scanner.py 함수 docstring 영역 영속.\n"
        "  사이클 98 G-DOC1 영속: KIS chk_*.py 정본 인용 의무.\n"
        "  명세 영속: _workspace/red/cycle101_market_cap_full_universe_load.md"
    )

    has_citation = (
        "chk_market_cap.py" in docstring
        or "chk_market_cap" in docstring
    )
    assert has_citation, (
        f"\n사이클 101 G-DOC1-A 위반 — 사이클 98 G-DOC1 영속 위반:\n"
        f"  기대: `chk_market_cap.py` 또는 `chk_market_cap` 인용 ≥1건\n"
        f"  실제 docstring (excerpt):\n{docstring[:500]}\n"
        f"  Red 결함 가설: 사이클 98 G-DOC1 silent 삭제 영역 영구 차단 영구 가드\n"
        f"  Green (backend-dev): chk_market_cap.py main 호출 영역 정본 인용 의무\n"
        f"  KIS 정본 영역 위계: chk_*.py main 호출 영역 = 실측 영역 (운영 영역 정합)"
    )


def test_g_doc1_b_full_universe_load_once_cites_ctpf1002r() -> None:
    """G-DOC1-B: `_full_universe_load_once` docstring CTPF1002R 인용 의무 (HIGH).

    검증 매트릭스 (사이클 98 G-DOC1 영속):
    - docstring 영역 `chk_search_stock_info.py` 또는 `chk_search_stock_info` 또는 `CTPF1002R` 인용 ≥1건

    Red 상태: 신규 함수 부재 또는 인용 부재.
    Green (backend-dev): chk_search_stock_info.py main 호출 영역 또는 TR_ID CTPF1002R 정본 인용.
    """
    docstring = _get_docstring("_full_universe_load_once")

    assert docstring is not None, (
        "\n사이클 101 G-DOC1-B Red 상태 — `_full_universe_load_once` docstring 부재.\n"
        "  Green (backend-dev): src/engine/scanner.py 함수 docstring 영역 영속."
    )

    has_citation = (
        "chk_search_stock_info.py" in docstring
        or "chk_search_stock_info" in docstring
        or "CTPF1002R" in docstring
    )
    assert has_citation, (
        f"\n사이클 101 G-DOC1-B 위반 — 사이클 98 G-DOC1 영속 위반:\n"
        f"  기대: `chk_search_stock_info` 또는 `CTPF1002R` 인용 ≥1건\n"
        f"  실제 docstring (excerpt):\n{docstring[:500]}\n"
        f"  Green (backend-dev): chk_search_stock_info.py main 영역 또는 TR_ID 정본 인용 의무"
    )
