"""사이클 89 L-2 (G-AST2) — AST 영구 가드: `_universe_eager_refresh_task` 도입 시 stop() task_attrs 튜플 포함 의무.

사이클 79 G-AST1 패턴 직답습. 미래 신규 background task 추가 시 cancel 누락 silent 결함
영구 차단.

Red 단계: `_universe_eager_refresh_task = asyncio.create_task(...)` 패턴 도입 후
`TradingScheduler.stop()` 의 `for task_attr in (...)` 튜플 안에 `_universe_eager_refresh_task`
미포함 → FAIL.

Green 단계: backend-dev 가 `task_attrs` 튜플에 `_universe_eager_refresh_task` 추가 후 PASS.

검증 규칙:
- `src/engine/scheduler.py` 내 `self._*_task = asyncio.create_task(...)` 패턴으로
  대입되는 모든 attribute 이름을 AST 로 수집
- `TradingScheduler.stop()` 의 task_attrs 튜플 안의 문자열 리터럴 집합과 비교
- 수집된 attribute - 튜플 = 누락 task → ≥ 1건이면 FAIL

영속 의무:
- 사이클 79 G-AST1 패턴 답습 (AST 기반 정적 검증)
- 사이클 42 `_heartbeat_metrics_loop` 좀비 task 영구 차단 패턴 답습
- 매매 안전성 영향 0 (lifecycle 영역 정적 검증만)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

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
# L-2 (G-AST2): 모든 `self._*_task = asyncio.create_task(...)` 가 stop() 튜플에 포함
# (사이클 79 G-AST1 패턴 답습 — 미래 신규 task 누락 silent 결함 영구 차단)
# ===========================================================================
def test_l2_universe_eager_refresh_task_included_in_stop_cancel_tuple():
    """L-2 (G-AST2): `_universe_eager_refresh_task` (사이클 89 도입 예정) 가
    `TradingScheduler.stop()` 의 `task_attrs` 튜플에 포함되어야 함 (영구 가드, 미래
    신규 task 누락 silent 결함 차단).

    검증 매트릭스 (사이클 79 G-AST1 직답습):
    - scheduler.py 내 `self._*_task = asyncio.create_task(...)` AST 수집
    - `TradingScheduler.stop()` 의 `for task_attr in (...)` 튜플 안 문자열 리터럴 수집
    - 수집된 attribute - 튜플 = ∅ (모든 task 가 cancel 목록에 포함)

    Red 상태 (사이클 89 시점):
    - 신규 `self._universe_eager_refresh_task = asyncio.create_task(...)` 도입
    - stop() 튜플 미포함 → 누락 → FAIL

    Green (사이클 90): backend-dev 가 `task_attrs` 튜플에
    `_universe_eager_refresh_task` 추가 → 누락 0건 → PASS.

    영속 의무:
    - 사이클 79 G-AST1 패턴 답습 (AST 기반 정적 검증)
    - 사이클 42 `_heartbeat_metrics_loop` 좀비 task 영구 차단 패턴 답습
    - 미래 신규 `self._foo_task = asyncio.create_task(...)` 추가 시 자동 검출
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")

    created_tasks = _collect_create_task_attrs(source)
    stop_tuple = _collect_stop_task_attrs_tuple(source)

    # 사전 조건: 수집이 정상 작동
    assert created_tasks, (
        "L-2 (G-AST2) 사전조건: `self._*_task = asyncio.create_task(...)` 패턴 "
        "수집 0건 — AST 수집 로직 결함 또는 scheduler.py 패턴 변경."
    )
    assert stop_tuple, (
        "L-2 (G-AST2) 사전조건: `TradingScheduler.stop()` 의 `for task_attr in (...)` "
        "튜플 수집 0건 — 사이클 13-E-1 통합 루프 패턴 누락."
    )

    missing = sorted(created_tasks - stop_tuple)

    assert not missing, (
        f"\n사이클 89 L-2 (G-AST2) 위반 — `asyncio.create_task(...)` 으로 도입된 task "
        f"중 `stop()` cancel 목록에 미포함된 attribute 발견:\n\n"
        f"  도입 task (asyncio.create_task): {sorted(created_tasks)}\n"
        f"  stop() task_attrs 튜플:          {sorted(stop_tuple)}\n"
        f"  누락 (좀비 task 위험):           {missing}\n\n"
        f"  사이클 89 = `_universe_eager_refresh_task` 도입 예정\n"
        f"  사이클 79 G-AST1 패턴 답습 의무\n\n"
        f"  시정 (Green): `stop()` 의 `for task_attr in (...)` 튜플 + `run_daily.finally`\n"
        f"  양쪽에 누락 항목 추가.\n"
        f"  영구 가드 — 미래 신규 background task 추가 시 cancel 누락 silent 결함\n"
        f"  즉시 FAIL (사이클 42 `_heartbeat_metrics_loop` 좀비 task 패턴 답습)."
    )
