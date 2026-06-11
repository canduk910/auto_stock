"""사이클 101 G-PURGE2 — `_universe_eager_refresh_*` 영구 폐기 AST 영구 가드 (MEDIUM).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사용자 결정 Q69=B 영속 (영구 폐기)**:
- `scanner.py::_universe_eager_refresh_loop` 함수 정의 영구 폐기 (사이클 89 영속)
- `scheduler.py::_universe_eager_refresh_loop` 메서드 정의 영구 폐기 (사이클 89 영속)
- `_universe_eager_refresh_task` 속성 영구 폐기 (사이클 89 영속)

검증 매트릭스:
- G-PURGE2-A: scanner.py `_universe_eager_refresh_loop` 함수 0건 영속
- G-PURGE2-B: scheduler.py `_universe_eager_refresh_loop` 메서드 0건 영속
- G-PURGE2-C: scheduler.py `_universe_eager_refresh_task` 문자열 0건 영속

Red 상태 (현재): 사이클 89 영속 → 3 영역 모두 존재 → FAIL.
Green (backend-dev): Q69=B 영구 폐기 후 모두 0건 영속.

영속 의무:
- 사이클 89 5분 주기 영구 폐기 (Q69=B 영속)
- 매일 20:00:05 일괄 단독 영역 영속
- 매매 hot path 영향 0 (lifecycle 영역)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _module_source(module_path: Path) -> str:
    return module_path.read_text(encoding="utf-8")


def test_g_purge2_a_scanner_universe_eager_refresh_loop_purged() -> None:
    """G-PURGE2-A: scanner.py `_universe_eager_refresh_loop` 함수 0건 영속 (MEDIUM)."""
    import src.engine.scanner as scanner_mod
    source = _module_source(Path(scanner_mod.__file__))
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_universe_eager_refresh_loop":
                pytest.fail(
                    f"\n사이클 101 G-PURGE2-A 위반 — scanner.py `_universe_eager_refresh_loop` 영속:\n"
                    f"  위치: scanner.py:{node.lineno}\n"
                    f"  Red 결함: 사이클 89 영역 영속 (Q69=B 영구 폐기 위반)\n"
                    f"  Green (backend-dev): Q69=B 영구 폐기 후 0건 영속 의무"
                )


def test_g_purge2_b_scheduler_universe_eager_refresh_loop_purged() -> None:
    """G-PURGE2-B: scheduler.py `_universe_eager_refresh_loop` 메서드 0건 영속 (MEDIUM)."""
    import src.engine.scheduler as scheduler_mod
    source = _module_source(Path(scheduler_mod.__file__))
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_universe_eager_refresh_loop":
                pytest.fail(
                    f"\n사이클 101 G-PURGE2-B 위반 — scheduler.py `_universe_eager_refresh_loop` 영속:\n"
                    f"  위치: scheduler.py:{node.lineno}\n"
                    f"  Red 결함: 사이클 89 영역 영속 (Q69=B 영구 폐기 위반)\n"
                    f"  Green (backend-dev): Q69=B 영구 폐기 후 0건 영속 의무"
                )


def test_g_purge2_c_universe_eager_refresh_task_purged() -> None:
    """G-PURGE2-C: scheduler.py `_universe_eager_refresh_task` 문자열 0건 영속 (MEDIUM)."""
    import src.engine.scheduler as scheduler_mod
    source = _module_source(Path(scheduler_mod.__file__))

    count = source.count("_universe_eager_refresh_task")
    assert count == 0, (
        f"\n사이클 101 G-PURGE2-C 위반 — `_universe_eager_refresh_task` 문자열 {count}건 (0건 의무):\n"
        f"  Red 결함: 사이클 89 영역 영속 (Q69=B 영구 폐기 위반)\n"
        f"  Green (backend-dev):\n"
        f"    1. asyncio.create_task(...) 영역 영구 삭제\n"
        f"    2. stop() task_attrs 튜플에서 영구 삭제\n"
        f"    3. run_daily() finally task_attrs 튜플에서 영구 삭제\n"
        f"  Q69=B 영속 의무: 매일 20:00:05 일괄 단독 영역 영속"
    )
