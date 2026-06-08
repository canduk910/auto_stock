"""사이클 83 G-AST1 — AST 영구 가드: 신규 `_scan_pool_eager_refresh_task` 가
`stop()` + `run_daily.finally` 양쪽 task_attrs 튜플에 동행 추가되어야 함.

미래 신규 background task 추가 시 cancel 목록 누락 silent 결함 영구 차단.

Red 단계: 현재 `_scan_pool_eager_refresh_task` (사이클 83 도입 예정) 가
`stop()` (L861~868) + `run_daily.finally` (L737~744) 양쪽 task_attrs 튜플에
미존재 → AST 분석 결과 missing ≥ 1건 → FAIL.

Green 단계: backend-dev 가 양쪽 task_attrs 튜플에 `_scan_pool_eager_refresh_task`
추가 → missing 0건 → PASS.

검증 규칙:
- `src/engine/scheduler.py` 내 `self._*_task = asyncio.create_task(...)` 패턴으로
  대입되는 모든 attribute 이름을 AST 로 수집
- `TradingScheduler.stop()` 의 task_attrs 튜플 + `run_daily()` `finally` 블록의
  task_attrs 튜플 양쪽 안의 문자열 리터럴 집합과 비교
- 수집된 attribute - 양쪽 튜플 교집합 = 누락 task → ≥ 1건이면 FAIL

영속 의무:
- 사이클 79 G-AST1 패턴 답습 (AST 기반 정적 검증)
- 사이클 42 `_heartbeat_metrics_loop` 좀비 task 영구 차단 패턴 답습
- 사이클 13-E-2 명세 (양쪽 동일 목록 통일) 영속
- 매매 안전성 영향 0 (lifecycle 영역 정적 검증만)

Red 의도:
- backend-dev 가 `_scan_pool_eager_refresh_task` (또는 결정 명명) 도입 시
  `asyncio.create_task(...)` 만 추가하고 `stop()` + `finally` task_attrs 튜플
  추가 누락하면 즉시 FAIL → 좀비 task 영구 차단
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_SCHEDULER_PY = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
)

_NEW_TASK_ATTR = "_scan_pool_eager_refresh_task"


def _collect_create_task_attrs(source: str) -> set[str]:
    """`self._*_task = asyncio.create_task(...)` 패턴의 attribute 이름 수집.

    사이클 79 G-AST1 패턴 답습.
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
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "create_task"
            and isinstance(func.value, ast.Name)
            and func.value.id == "asyncio"
        ):
            continue
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


def _collect_for_loop_tuple_strings_in_func(
    source: str, class_name: str, func_name: str,
) -> list[set[str]]:
    """클래스 내 특정 함수의 `for ... in (...)` 튜플 안 문자열 리터럴 집합 리스트 반환.

    각 for-loop 별로 set 1개 반환 (여러 for-loop 있을 경우 모두 수집).
    """
    tree = ast.parse(source)
    result: list[set[str]] = []
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.name != class_name:
            continue
        for fn in cls.body:
            if (
                not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                or fn.name != func_name
            ):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.For):
                    continue
                iter_node = node.iter
                if not isinstance(iter_node, ast.Tuple):
                    continue
                strings: set[str] = set()
                for elt in iter_node.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        strings.add(elt.value)
                if strings:
                    result.append(strings)
    return result


# ===========================================================================
# G-AST1: 신규 `_scan_pool_eager_refresh_task` 가 stop() + finally 양쪽 포함
# ===========================================================================
def test_g_ast1_scan_pool_eager_refresh_task_in_both_cancel_tuples():
    """G-AST1: `_scan_pool_eager_refresh_task` (사이클 83 도입 예정) 가
    `TradingScheduler.stop()` + `TradingScheduler.run_daily()` `finally` 블록
    양쪽 task_attrs 튜플에 포함되어야 함 (영구 가드).

    검증 매트릭스:
    - scheduler.py 내 `self._*_task = asyncio.create_task(...)` AST 수집
    - 그 중 `_scan_pool_eager_refresh_task` 존재 (Green 사전조건)
    - `stop()` 의 모든 for-loop 튜플 union 안에 `"_scan_pool_eager_refresh_task"` 포함
    - `run_daily()` 의 모든 for-loop 튜플 union 안에 `"_scan_pool_eager_refresh_task"` 포함

    Red 상태 (사이클 83 Red 시점):
    - 신규 task `_scan_pool_eager_refresh_task` 미도입 → asyncio.create_task 수집 누락
    - stop() 튜플 / finally 튜플 양쪽 미포함
    - → 사전조건 단계에서 FAIL (Red 단계 의무 — 시정 코드 부재 시 fail)

    Green (사이클 84 backend-dev):
    - `self._scan_pool_eager_refresh_task = asyncio.create_task(self._scan_pool_eager_refresh_loop())` 도입
    - `stop()` + `run_daily.finally` 양쪽 task_attrs 튜플에 `"_scan_pool_eager_refresh_task"` 추가
    - 모두 만족 → PASS

    영속 의무:
    - 사이클 79 G-AST1 패턴 답습 (사이클 13-E-2 양쪽 동일 목록 통일)
    - 사이클 42 좀비 task 영구 차단
    - 미래 신규 `self._foo_task = asyncio.create_task(...)` 추가 시 자동 검출
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")

    created_tasks = _collect_create_task_attrs(source)
    stop_tuples = _collect_for_loop_tuple_strings_in_func(
        source, "TradingScheduler", "stop"
    )
    finally_tuples = _collect_for_loop_tuple_strings_in_func(
        source, "TradingScheduler", "run_daily"
    )

    stop_union: set[str] = set().union(*stop_tuples) if stop_tuples else set()
    finally_union: set[str] = set().union(*finally_tuples) if finally_tuples else set()

    errors: list[str] = []

    # 사전조건: asyncio.create_task 수집 정상
    if not created_tasks:
        errors.append(
            "  - `self._*_task = asyncio.create_task(...)` 수집 0건 — "
            "AST 수집 로직 또는 scheduler.py 패턴 변경"
        )

    # 사전조건 + Green 의무: `_scan_pool_eager_refresh_task` asyncio.create_task 등록
    if _NEW_TASK_ATTR not in created_tasks:
        errors.append(
            f"  - `self.{_NEW_TASK_ATTR} = asyncio.create_task(...)` 도입 누락 "
            f"(Green 사전조건 — backend-dev 가 task 도입 의무)"
        )

    # 본 가드: stop() 튜플 포함
    if _NEW_TASK_ATTR not in stop_union:
        errors.append(
            f"  - `stop()` 의 task_attrs 튜플에 `\"{_NEW_TASK_ATTR}\"` 미포함 "
            f"(좀비 task 위험, 사이클 79 G-AST1 패턴 답습 의무)"
        )

    # 본 가드: run_daily.finally 튜플 포함 (사이클 13-E-2 양쪽 통일)
    if _NEW_TASK_ATTR not in finally_union:
        errors.append(
            f"  - `run_daily()` `finally` 블록 task_attrs 튜플에 `\"{_NEW_TASK_ATTR}\"` "
            f"미포함 (비정상 종료 경로 좀비 task 위험, 사이클 13-E-2 통일 의무)"
        )

    assert not errors, (
        f"\n사이클 83 G-AST1 위반 — 신규 `_scan_pool_eager_refresh_task` "
        f"lifecycle 가드 결함:\n\n"
        + "\n".join(errors)
        + f"\n\n  도입 task (asyncio.create_task): {sorted(created_tasks)}\n"
        f"  stop() task_attrs 튜플 union:    {sorted(stop_union)}\n"
        f"  run_daily.finally tuple union:   {sorted(finally_union)}\n\n"
        f"  사이클 83 (#82-A 옵션 1) = `_scan_loop` 후보 풀 ticker stock_master\n"
        f"  eager refresh 영역 확장. Q1=B `subscribe_filtered_stocks` 진입점 hook\n"
        f"  + Q2=C 백그라운드 task → 신규 `_scan_pool_eager_refresh_task` 도입\n"
        f"  + 사이클 79 패턴 답습 (`stop()` + `finally` 양쪽 cancel 목록 동행).\n\n"
        f"  Green 시정 예시:\n"
        f"    self._scan_pool_eager_refresh_task = asyncio.create_task(\n"
        f"        self._scan_pool_eager_refresh_loop()\n"
        f"    )\n"
        f"    # stop() + run_daily.finally 양쪽 task_attrs 튜플에 추가:\n"
        f"    for task_attr in (\n"
        f"        ..., \"_scan_pool_eager_refresh_task\",  # 사이클 83 신규\n"
        f"    ):\n"
        f"        ...\n"
    )
