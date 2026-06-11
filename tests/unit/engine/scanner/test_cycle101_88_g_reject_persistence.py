"""사이클 101 G-PERSIST4 — 사이클 88 G-REJECT graceful 영속 (LOW).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사이클 88 G-REJECT 영속 (graceful 매트릭스 영구 보장)**:
- KIS rt_cd != "0" 시 graceful (continue, 영역 영속)
- KIS 예외 시 graceful (`try: ... except Exception: continue`)
- 사이클 101 ~2,800 호출 영역 = graceful 영속 의무 (사이클 88 답습)

검증 매트릭스:
- G-PERSIST4-A: `_fetch_market_cap_page` 영역 try/except 영속 (사이클 88 답습)
- G-PERSIST4-B: `_full_universe_load_once` 영역 try/except 영속 (CTPF1002R 호출 graceful)

Red 상태: 신규 함수 부재 또는 try/except 없음 → KIS 한 건 실패 시 전체 chain 차단.
Green (backend-dev): graceful 영속 의무.

영속 의무:
- 사이클 88 G-REJECT 영속 영구 보장
- 매매 안전성 영역 영향 0 (graceful 영역)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _scanner_source() -> str:
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__).read_text(encoding="utf-8")


def _function_has_try_except(func_name: str) -> bool:
    source = _scanner_source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                # 함수 본체 내부 어딘가에 Try 노드 영속
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Try):
                        return True
                return False
    return False


def test_g_persist4_a_fetch_market_cap_page_graceful() -> None:
    """G-PERSIST4-A: `_fetch_market_cap_page` 영역 try/except 영속 (LOW).

    검증 매트릭스 (사이클 88 G-REJECT 영속):
    - 함수 본체 내부 Try 노드 ≥1건

    Red 상태: 함수 부재 또는 try/except 없음.
    Green (backend-dev): graceful 영속 의무 (KIS 한 페이지 실패 시 다음 페이지 진행 또는 [] 반환).
    """
    from src.engine import scanner

    if not hasattr(scanner, "_fetch_market_cap_page"):
        pytest.fail("G-PERSIST4-A Red — `_fetch_market_cap_page` 부재 (G-MC1 영속)")

    has_try = _function_has_try_except("_fetch_market_cap_page")
    assert has_try, (
        "\n사이클 101 G-PERSIST4-A 위반 — graceful try/except 부재:\n"
        "  Red 결함: KIS 한 건 실패 시 전체 chain 차단 위험\n"
        "  Green (backend-dev): try/except 영속 의무 (사이클 88 G-REJECT 답습)"
    )


def test_g_persist4_b_full_universe_load_once_graceful() -> None:
    """G-PERSIST4-B: `_full_universe_load_once` 영역 try/except 영속 (LOW).

    검증 매트릭스 (사이클 88 G-REJECT 영속):
    - CTPF1002R 호출 (~2,800 ticker) 중 일부 실패 시 graceful 영속
    """
    from src.engine import scanner

    if not hasattr(scanner, "_full_universe_load_once"):
        pytest.fail("G-PERSIST4-B Red — `_full_universe_load_once` 부재 (G-CTPF1 영속)")

    has_try = _function_has_try_except("_full_universe_load_once")
    assert has_try, (
        "\n사이클 101 G-PERSIST4-B 위반 — graceful try/except 부재:\n"
        "  Red 결함: CTPF1002R 한 건 실패 시 ~2,800 chain 차단 위험\n"
        "  Green (backend-dev): try/except 영속 의무 (사이클 88 G-REJECT 답습)\n"
        "  운영 효과: 1건 실패 → continue + failed counter 증가 → summary emit"
    )
