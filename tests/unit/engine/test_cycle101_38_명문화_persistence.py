"""사이클 101 G-PERSIST1 — 사이클 38 명문화 영속 (LOW).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사이클 38 명문화 영속 (2026-05-22 영구 보장)**:
- `tradable_boards` 매수 진입 전용
- 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링 = PRE/MAIN/POST 무관 항상 작동
- 사이클 101 ~2,800 적재 = scanner 단계 영역 한정 = 매수 진입만 영향 (사이클 38 명문화 영속)

검증 매트릭스:
- G-PERSIST1-A: `_full_universe_load_once` source 영역 또는 docstring 영역에 사이클 38 인용 ≥1건
- G-PERSIST1-B: 매수 진입 전용 영역 영속 명문화

Red 상태: 신규 함수 docstring 영역 사이클 38 인용 부재.
Green (backend-dev): docstring 영역 영속 의무.

영속 의무:
- 사이클 38 명문화 영속 영구 보장 (`tradable_boards` 매수 진입 전용)
- 매매 안전성 영역 영향 0 (정적 가드)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _scanner_source() -> str:
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__).read_text(encoding="utf-8")


def test_g_persist1_a_cycle38_persistence_in_docstring() -> None:
    """G-PERSIST1-A: `_full_universe_load_once` 또는 `_fetch_market_cap_page`
    docstring 영역에 사이클 38 명문화 인용 ≥1건 영속 (LOW).

    검증 매트릭스 (사이클 38 명문화 영속 의무):
    - docstring 영역 `사이클 38` 또는 `tradable_boards` 또는 `매수 진입 전용` 인용 ≥1건

    Red 상태: 신규 함수 docstring 부재 또는 인용 부재.
    Green (backend-dev): docstring 영역 사이클 38 명문화 영속 인용 의무.
    """
    source = _scanner_source()
    tree = ast.parse(source)

    target_funcs = ["_full_universe_load_once", "_fetch_market_cap_page"]
    docstrings = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in target_funcs:
                ds = ast.get_docstring(node) or ""
                docstrings.append((node.name, ds))

    assert docstrings, (
        "\n사이클 101 G-PERSIST1-A Red — 신규 함수 부재 (G-CTPF1/G-MC1 영속).\n"
        "  Green: scanner.py 신규 함수 정의 의무"
    )

    has_cycle38 = any(
        ("사이클 38" in ds or "tradable_boards" in ds or "매수 진입 전용" in ds)
        for _, ds in docstrings
    )
    assert has_cycle38, (
        f"\n사이클 101 G-PERSIST1-A 위반 — 사이클 38 명문화 영속 인용 부재:\n"
        f"  기대: 신규 함수 docstring 영역에 `사이클 38` 또는 `tradable_boards`\n"
        f"        또는 `매수 진입 전용` 인용 ≥1건\n"
        f"  실제 docstring 검사:\n"
        + "\n".join(f"    {name}: {ds[:200]!r}" for name, ds in docstrings) +
        f"\n  Green (backend-dev): 사이클 38 명문화 영속 인용 의무 (CLAUDE.md 영속)"
    )
