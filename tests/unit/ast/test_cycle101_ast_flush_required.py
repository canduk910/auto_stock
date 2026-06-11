"""사이클 101 G-AST1 — `record_full_universe_load_summary` ↔ `flush_*` 영구 가드 (MEDIUM).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사이클 78 G-AST1 영속 (record_* ↔ flush_* 호출 사이트 영구 가드 패턴 답습)**:
- `record_full_universe_load_summary` 정의 모듈의 대응 `flush_full_universe_load_collector` 호출 사이트 ≥1건
- 미래 신규 collector 추가 시 flush 호출 누락 silent 결함 영구 차단

검증 매트릭스 (사이클 78 G-AST1 영속):
- G-AST1-A: `record_full_universe_load_summary` 함수 정의 영속 (Red = 부재)
- G-AST1-B: `flush_full_universe_load_collector` 함수 정의 영속
- G-AST1-C: production 코드 어딘가에 `flush_full_universe_load_collector` 호출 사이트 ≥1건

Red 상태: 신규 함수 부재 또는 호출 사이트 0건.
Green (backend-dev): `stock_master_metrics.py` 함수 정의 + scheduler.py 또는 scanner.py 호출.

영속 의무:
- 사이클 78 G-AST1 영구 가드 패턴 답습 (`tests/unit/ast/test_cycle78_ast_flush_required.py`)
- 매매 안전성 영역 영향 0 (collector 영역 한정)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _module_source(module_path: Path) -> str:
    return module_path.read_text(encoding="utf-8")


def _find_function_def(source: str, func_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                return node
    return None


def _find_function_calls(source: str, func_name: str) -> int:
    """source 영역에서 `func_name(...)` 호출 횟수 카운트."""
    tree = ast.parse(source)
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            callee = node.func
            # `flush_full_universe_load_collector()` 직접 호출
            if isinstance(callee, ast.Name) and callee.id == func_name:
                count += 1
            # `_metrics_mod.flush_full_universe_load_collector()` attribute 호출
            elif isinstance(callee, ast.Attribute) and callee.attr == func_name:
                count += 1
            # `await flush_full_universe_load_collector()` — Call wrap
        elif isinstance(node, ast.Await):
            inner = node.value
            if isinstance(inner, ast.Call):
                callee = inner.func
                if isinstance(callee, ast.Name) and callee.id == func_name:
                    count += 1
                elif isinstance(callee, ast.Attribute) and callee.attr == func_name:
                    count += 1
    return count


def test_g_ast1_a_record_full_universe_load_summary_exists() -> None:
    """G-AST1-A: `record_full_universe_load_summary` 함수 정의 영속 (MEDIUM)."""
    import src.engine.stock_master_metrics as metrics_mod

    assert hasattr(metrics_mod, "record_full_universe_load_summary"), (
        "\n사이클 101 G-AST1-A Red — `record_full_universe_load_summary` 부재.\n"
        "  Green: src/engine/stock_master_metrics.py 함수 정의 의무 (사이클 74/89 패턴 답습)"
    )


def test_g_ast1_b_flush_full_universe_load_collector_exists() -> None:
    """G-AST1-B: `flush_full_universe_load_collector` 함수 정의 영속 (MEDIUM)."""
    import src.engine.stock_master_metrics as metrics_mod

    assert hasattr(metrics_mod, "flush_full_universe_load_collector"), (
        "\n사이클 101 G-AST1-B Red — `flush_full_universe_load_collector` 부재.\n"
        "  Green: src/engine/stock_master_metrics.py 함수 정의 의무 (사이클 78 G-AST1 답습)"
    )


def test_g_ast1_c_flush_call_site_at_least_one() -> None:
    """G-AST1-C: `flush_full_universe_load_collector` 호출 사이트 ≥1건 영속 (MEDIUM).

    검증 매트릭스 (사이클 78 G-AST1 답습):
    - production source (scheduler.py + scanner.py) 영역에서 호출 사이트 ≥1건
    - 미래 silent 결함 영구 차단 (사이클 74 도입 누락 결함 패턴 답습)

    Red 상태: 호출 사이트 0건 → collector 무한 누적 (메모리 leak HIGH).
    Green (backend-dev): scheduler `_full_universe_load_task` 또는 `_api_recovered_collector_loop`
    영역에서 호출 사이트 영속.
    """
    import src.engine.scheduler as scheduler_mod
    import src.engine.scanner as scanner_mod

    scheduler_src = _module_source(Path(scheduler_mod.__file__))
    scanner_src = _module_source(Path(scanner_mod.__file__))

    scheduler_calls = _find_function_calls(scheduler_src, "flush_full_universe_load_collector")
    scanner_calls = _find_function_calls(scanner_src, "flush_full_universe_load_collector")
    total = scheduler_calls + scanner_calls

    assert total >= 1, (
        f"\n사이클 101 G-AST1-C 위반 — flush 호출 사이트 0건 (사이클 78 답습 silent 결함):\n"
        f"  기대: production 영역 호출 사이트 ≥1건\n"
        f"  실제 (scheduler.py + scanner.py 합산): {total}건\n"
        f"  Red 결함 가설: 사이클 74 패턴 — record 도입 / flush 호출 누락 = 메모리 leak HIGH\n"
        f"  Green (backend-dev): _full_universe_load_task 본체 또는\n"
        f"    _api_recovered_collector_loop 본체 영역에 flush 호출 영속 의무"
    )
