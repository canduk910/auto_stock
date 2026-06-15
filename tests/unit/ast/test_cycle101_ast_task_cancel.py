"""사이클 101 G-AST2 — `_full_universe_load_task` cancel 영구 가드 (MEDIUM).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사이클 79 G-AST2 영속 (`stop()` task_attrs 튜플 + `run_daily()` finally 양쪽 동행 영구 가드 답습)**:
- 사이클 101 신규 task `_full_universe_load_task` cancel 목록 양쪽 영속 의무
- 미래 신규 task 추가 시 cancel 목록 누락 silent 결함 영구 차단

검증 매트릭스 (사이클 79 G-AST2 영속):
- G-AST2-A: `scheduler.py` source 영역 `_full_universe_load_task` 문자열 ≥3건
  (`asyncio.create_task` 1 + `stop()` task_attrs 1 + `run_daily()` finally 1)
- G-AST2-B: `stop()` 함수 영역에 `"_full_universe_load_task"` 문자열 영속
- G-AST2-C: `run_daily()` finally 블록 영역에 `"_full_universe_load_task"` 문자열 영속

Red 상태: 신규 task 부재 또는 cancel 목록 누락.
Green (backend-dev): 양쪽 동행 추가 의무 (사이클 79 영속).

영속 의무:
- 사이클 79 G-AST2 영구 가드 패턴 답습 (`tests/unit/ast/test_cycle79_ast_task_cancel_required.py`)
- 매매 안전성 영역 영향 0 (lifecycle 영역 한정)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source

pytestmark = pytest.mark.unit


def _scheduler_source() -> str:
    import src.engine.scheduler as scheduler_mod
    return read_module_source(Path(scheduler_mod.__file__))


def test_g_ast2_a_full_universe_load_task_three_or_more_occurrences() -> None:
    """G-AST2-A: `_full_universe_load_task` 문자열 ≥3건 영속 (MEDIUM).

    검증 매트릭스 (사이클 79 G-AST2 답습):
    - 위치 1: `self._full_universe_load_task = asyncio.create_task(...)` (task 생성)
    - 위치 2: `stop()` task_attrs 튜플 (cancel 목록)
    - 위치 3: `run_daily()` finally task_attrs 튜플 (cancel 목록)

    Red 상태: 신규 task 부재 또는 cancel 목록 누락.
    Green (backend-dev): 양쪽 동행 영속.
    """
    source = _scheduler_source()
    count = source.count("_full_universe_load_task")

    assert count >= 3, (
        f"\n사이클 101 G-AST2-A 위반 — `_full_universe_load_task` 문자열 {count}건 (≥3 의무):\n"
        f"  기대: 3건 (create_task 1 + stop() task_attrs 1 + run_daily finally 1)\n"
        f"  실제: {count}건\n"
        f"  Red 결함 가설: cancel 목록 누락 = 사이클 79 답습 silent 결함\n"
        f"  Green (backend-dev): 사이클 79 패턴 양쪽 동행 추가 의무"
    )


def test_g_ast2_b_stop_function_contains_task_attr() -> None:
    """G-AST2-B: `stop()` 함수 영역에 `_full_universe_load_task` 영속 (MEDIUM).

    검증: AST 정적 분석 — `stop()` 함수 본체 영역에 task_attr 문자열 영속.

    Red 상태: stop() 영역 누락.
    Green (backend-dev): stop() task_attrs 튜플 추가 의무.
    """
    source = _scheduler_source()
    tree = ast.parse(source)

    stop_segment = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "stop":
                stop_segment = ast.get_source_segment(source, node)
                break

    assert stop_segment is not None, (
        "\n사이클 101 G-AST2-B Red — scheduler.py::stop() 함수 부재"
    )
    assert "_full_universe_load_task" in stop_segment, (
        f"\n사이클 101 G-AST2-B 위반 — stop() 영역에 task_attr 누락:\n"
        f"  기대: stop() task_attrs 튜플에 '_full_universe_load_task' 포함\n"
        f"  Red 결함 가설: 사이클 79 답습 silent 결함 (cancel 누락)\n"
        f"  Green (backend-dev): stop() task_attrs 튜플 추가 의무"
    )


def test_g_ast2_c_run_daily_finally_contains_task_attr() -> None:
    """G-AST2-C: `run_daily()` finally 블록 영역에 `_full_universe_load_task` 영속 (MEDIUM).

    검증: AST 정적 분석 — `run_daily()` 함수 본체 (finally 영역 포함) 에 task_attr 문자열.

    Red 상태: run_daily() finally 영역 누락.
    Green (backend-dev): finally 블록 task_attrs 튜플 추가 의무.
    """
    source = _scheduler_source()
    tree = ast.parse(source)

    run_daily_segment = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "run_daily":
                run_daily_segment = ast.get_source_segment(source, node)
                break

    assert run_daily_segment is not None, (
        "\n사이클 101 G-AST2-C Red — scheduler.py::run_daily() 함수 부재"
    )
    assert "_full_universe_load_task" in run_daily_segment, (
        f"\n사이클 101 G-AST2-C 위반 — run_daily() 영역에 task_attr 누락:\n"
        f"  기대: run_daily() finally 블록 task_attrs 튜플에 '_full_universe_load_task' 포함\n"
        f"  Red 결함 가설: 사이클 79 답습 silent 결함\n"
        f"  Green (backend-dev): run_daily() finally task_attrs 튜플 추가 의무"
    )
