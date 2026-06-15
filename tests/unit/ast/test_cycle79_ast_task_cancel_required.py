"""사이클 79 G-AST1 — AST 영구 가드: `asyncio.create_task(self._*_loop())` 패턴으로
도입되는 모든 background task 가 `stop()` task_attrs 튜플에 포함되어야 함.

미래 신규 background task 추가 시 `stop()` cancel 목록 누락 silent 결함 영구 차단.

Red 단계: 현재 `_api_recovered_collector_task` (사이클 76 도입) 가 `stop()`
task_attrs 튜플 (L860~865) 에 미포함 → AST 분석 결과 missing 1건 → FAIL.

Green 단계: backend-dev 가 `task_attrs` 튜플에 `_api_recovered_collector_task`
추가 → missing 0건 → PASS.

검증 규칙:
- `src/engine/scheduler.py` 내 `self._*_task = asyncio.create_task(...)` 패턴으로
  대입되는 모든 attribute 이름을 AST 로 수집
- `TradingScheduler.stop()` 의 task_attrs 튜플 (사이클 13-E-1 통합 루프) 안의
  문자열 리터럴 집합과 비교
- 수집된 attribute - 튜플 = 누락 task → ≥ 1건이면 FAIL

영속 의무:
- 사이클 78 G-AST1 패턴 답습 (AST 기반 정적 검증)
- 사이클 42 `_heartbeat_metrics_loop` 좀비 task 영구 차단 패턴 답습
- 매매 안전성 영향 0 (lifecycle 영역 정적 검증만)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

# 사이클 137 (2026-06-15) — 카드 #25 AST DRY 헬퍼 모듈 마이그레이션.
from tests.unit.ast._ast_helpers import read_module_source as _read

pytestmark = pytest.mark.unit


_SCHEDULER_PY = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
)


def _collect_create_task_attrs(source: str) -> set[str]:
    """`self._*_task = asyncio.create_task(...)` 패턴의 attribute 이름 수집.

    AST 분석:
    - `ast.Assign` 노드 + targets 가 `ast.Attribute(value=ast.Name(id="self"))`
    - value 가 `ast.Call(func=ast.Attribute(attr="create_task", value=ast.Name(id="asyncio")))`
    """
    tree = ast.parse(source)
    result: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        func = value.func
        # `asyncio.create_task(...)` 매칭
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "create_task"
            and isinstance(func.value, ast.Name)
            and func.value.id == "asyncio"
        ):
            continue
        # targets 가 `self._foo_task` 패턴인지
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr.startswith("_")
                and target.attr.endswith("_task")
            ):
                result.add(target.attr)
    return result


def _collect_stop_task_attrs_tuple(source: str) -> set[str]:
    """`TradingScheduler.stop()` 의 `for task_attr in (...)` 튜플 안의 문자열 수집."""
    tree = ast.parse(source)
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.name != "TradingScheduler":
            continue
        for fn in cls.body:
            if (
                not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                or fn.name != "stop"
            ):
                continue
            # 첫 번째 `for task_attr in (...)` 의 튜플 elts 수집
            for node in ast.walk(fn):
                if not isinstance(node, ast.For):
                    continue
                iter_node = node.iter
                if not isinstance(iter_node, ast.Tuple):
                    continue
                strings: set[str] = set()
                for elt in iter_node.elts:
                    if isinstance(elt, ast.Constant) and isinstance(
                        elt.value, str
                    ):
                        strings.add(elt.value)
                if strings:
                    return strings
    return set()


# ===========================================================================
# G-AST1: 모든 `self._*_task = asyncio.create_task(...)` 가 stop() 튜플에 포함
# ===========================================================================
def test_g_ast1_all_create_task_attrs_included_in_stop_cancel_tuple():
    """G-AST1: `self._*_task = asyncio.create_task(...)` 패턴으로 도입되는 모든
    attribute 가 `TradingScheduler.stop()` 의 `task_attrs` 튜플에 포함되어야 함
    (영구 가드, 미래 신규 task 누락 silent 결함 차단).

    검증 매트릭스:
    - scheduler.py 내 `self._*_task = asyncio.create_task(...)` AST 수집
    - `TradingScheduler.stop()` 의 `for task_attr in (...)` 튜플 안 문자열 리터럴 수집
    - 수집된 attribute - 튜플 = ∅

    Red 상태 (사이클 79 시점):
    - 도입 attribute 8종 + 신규 1종 (`_api_recovered_collector_task`, 사이클 76)
    - stop() 튜플: 8종 (`_next_day_task` / `_session_task` / `_stale_watcher_task` /
      `_session_health_task` / `_swing_poll_task` / `_swing_rest_poll_task` /
      `_5xx_dedupe_summary_task` / `_ws_task` / `_scan_task`)
    - 누락: `_api_recovered_collector_task` 1건 → FAIL

    Green: backend-dev 가 `task_attrs` 튜플에 `_api_recovered_collector_task`
    추가 → 누락 0건 → PASS.

    영속 의무:
    - 미래 신규 `self._foo_task = asyncio.create_task(...)` 추가 시 `stop()`
      에 자동으로 cancel 누락 감지 (영구 좀비 task 차단)
    """
    source = _read(_SCHEDULER_PY)

    created_tasks = _collect_create_task_attrs(source)
    stop_tuple = _collect_stop_task_attrs_tuple(source)

    # 사전 조건: 수집이 정상 작동
    assert created_tasks, (
        "G-AST1 사전조건: `self._*_task = asyncio.create_task(...)` 패턴 "
        "수집 0건 — AST 수집 로직 결함 또는 scheduler.py 패턴 변경."
    )
    assert stop_tuple, (
        "G-AST1 사전조건: `TradingScheduler.stop()` 의 `for task_attr in (...)` "
        "튜플 수집 0건 — 사이클 13-E-1 통합 루프 패턴 누락."
    )

    missing = sorted(created_tasks - stop_tuple)

    assert not missing, (
        f"\n사이클 79 G-AST1 위반 — `asyncio.create_task(...)` 으로 도입된 task "
        f"중 `stop()` cancel 목록에 미포함된 attribute 발견:\n\n"
        f"  도입 task (asyncio.create_task): {sorted(created_tasks)}\n"
        f"  stop() task_attrs 튜플:          {sorted(stop_tuple)}\n"
        f"  누락 (좀비 task 위험):           {missing}\n\n"
        f"  사이클 76 commit (0d633a8) = `_api_recovered_collector_task` 도입\n"
        f"  사이클 78 부차 발견 = `stop()` cancel 목록 추가 누락\n\n"
        f"  시정 (Green): `stop()` 의 `for task_attr in (...)` 튜플에 누락 항목 추가.\n"
        f"  영구 가드 — 미래 신규 background task 추가 시 cancel 누락 silent 결함\n"
        f"  즉시 FAIL (사이클 42 `_heartbeat_metrics_loop` 좀비 task 패턴 답습)."
    )
