"""사이클 102 영역 1 — 사이클 78 silent 결함 영역 영구 가드 (AST 정적).

G-78-VERIFY-2 + G-78-VERIFY-3 + G-78-VERIFY-4 — `_api_recovered_collector_loop` body +
`stop()` lifecycle hook 양쪽 flush 호출 사이트 영속 + `if not self._running: break`
위치 영속 AST 검증.

영역 1 = 코드 변경 0 의무 영역 (사이클 78 영속 영역 영구 확인 + 회귀 영구 차단).

영속 의무:
- 사이클 78 G-AST1 답습 (AST 기반 정적 검증)
- 사이클 74 5분 윈도우 emit 영속 (collector 패턴)
- 사이클 17 KIS LMS chain / 사이클 38 명문화 / 매매 안전성 영향 0
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


_SCHEDULER_PY = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
)


def _get_function_node(source: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """모듈 전체 (클래스 내부 포함) 에서 `name` 함수/메서드 정의 첫 노드 반환."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _count_calls_in(node: ast.AST, name: str) -> int:
    """`node` 서브트리 안에서 `name(...)` 호출 사이트 개수.

    매칭: `name(...)` 단순 호출 + `module.name(...)` 속성 호출
    """
    count = 0
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == name:
            count += 1
        elif isinstance(func, ast.Attribute) and func.attr == name:
            count += 1
    return count


# ===========================================================================
# G-78-VERIFY-2 — `_api_recovered_collector_loop` body flush 호출 사이트 영속
# ===========================================================================
def test_g_78_verify_2_api_recovered_collector_loop_flush_call_sites():
    """G-78-VERIFY-2 (HIGH): `_api_recovered_collector_loop` 본체 영속 영역에
    `flush_swing_rest_poll_collector` + `flush_stale_watcher_collector` 양쪽 호출 사이트
    ≥1건 영속 (사이클 78 영구 가드 영역 확인).

    Red: 사이클 78 영속 영역 침범 시 FAIL.
    Green: 호출 사이트 ≥1건 → PASS.

    회귀 차단: `_api_recovered_collector_loop` 본체 flush 4 줄 제거 시 메모리 leak HIGH
    재현 영구 차단 (사이클 78 silent 결함 재발 영역 영구 차단).
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    func = _get_function_node(source, "_api_recovered_collector_loop")

    assert func is not None, (
        "G-78-VERIFY-2 사전조건: `_api_recovered_collector_loop` 함수 정의 미존재 — "
        "사이클 76/78 영속 영역 침범"
    )

    swing_calls = _count_calls_in(func, "flush_swing_rest_poll_collector")
    stale_calls = _count_calls_in(func, "flush_stale_watcher_collector")

    missing: list[str] = []
    if swing_calls < 1:
        missing.append(
            f"  - `flush_swing_rest_poll_collector` 호출 사이트: {swing_calls} 건 (≥ 1 필요)"
        )
    if stale_calls < 1:
        missing.append(
            f"  - `flush_stale_watcher_collector` 호출 사이트: {stale_calls} 건 (≥ 1 필요)"
        )

    assert not missing, (
        f"\n사이클 102 G-78-VERIFY-2 위반 — `_api_recovered_collector_loop` 본체 영속 영역 침범 "
        f"(사이클 78 silent 결함 재발 영역):\n"
        + "\n".join(missing)
        + "\n\n  사이클 78 영속 영역 (영역 1 코드 변경 0 의무):\n"
        f"  - `scheduler.py::_api_recovered_collector_loop` (L2543~L2565) 영역 영속\n"
        f"  - `if not self._running: break` 위치 = flush 4 줄 *이후* 영속\n"
        f"  - 사이클 78 의도 = sleep 후 무조건 1회 flush 보장 (마지막 flush 보장)\n\n"
        f"  운영 효과 보장 (push 후): [stale_watcher_summary] 0건/7일 → 144건/day (5분 주기)\n"
    )


# ===========================================================================
# G-78-VERIFY-3 — `stop()` lifecycle hook flush 호출 사이트 영속
# ===========================================================================
def test_g_78_verify_3_stop_lifecycle_hook_flush_call_sites():
    """G-78-VERIFY-3 (HIGH): `stop()` lifecycle hook 영속 영역에 양쪽 flush 호출 사이트
    ≥1건 영속 (사이클 78 G-AST1 영속 영구 확인).

    Red: 사이클 78 영속 영역 침범 시 FAIL.
    Green: `stop()` 메서드 본체 호출 사이트 ≥1건 → PASS.

    회귀 차단: `stop()` shutdown 시 잔여 collector 카운터 손실 (Q5 사이클 74 G-SP4 영속 영역
    침범 영구 차단). `unsubscribe_all()` *전* flush 위치 영속.
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    func = _get_function_node(source, "stop")

    assert func is not None, (
        "G-78-VERIFY-3 사전조건: `stop()` 메서드 정의 미존재 — 사이클 78 영속 영역 침범"
    )

    swing_calls = _count_calls_in(func, "flush_swing_rest_poll_collector")
    stale_calls = _count_calls_in(func, "flush_stale_watcher_collector")

    missing: list[str] = []
    if swing_calls < 1:
        missing.append(
            f"  - `flush_swing_rest_poll_collector` 호출 사이트 (stop): "
            f"{swing_calls} 건 (≥ 1 필요)"
        )
    if stale_calls < 1:
        missing.append(
            f"  - `flush_stale_watcher_collector` 호출 사이트 (stop): "
            f"{stale_calls} 건 (≥ 1 필요)"
        )

    assert not missing, (
        f"\n사이클 102 G-78-VERIFY-3 위반 — `stop()` lifecycle hook 영속 영역 침범 "
        f"(사이클 78 G-AST1 영역 영구 영속 침범):\n"
        + "\n".join(missing)
        + "\n\n  사이클 78 영속 영역 (영역 1 코드 변경 0 의무):\n"
        f"  - `scheduler.py::stop()` (L920~L930) shutdown 직전 양쪽 flush\n"
        f"  - `unsubscribe_all()` *전* flush 영속 (Q5 사이클 74 G-SP4 패턴 답습)\n"
        f"  - 잔여 카운터 손실 방지 영구 가드.\n"
    )


# ===========================================================================
# G-78-VERIFY-4 — `if not self._running: break` 위치 영속 AST 검증
# ===========================================================================
def test_g_78_verify_4_break_position_after_flush_in_loop():
    """G-78-VERIFY-4 (MEDIUM): `_api_recovered_collector_loop` body 내
    `if not self._running: break` 가 flush 4 줄 *이후* 위치 영속 AST 검증.

    Red: break 가 flush 4 줄 *전* 위치 → FAIL.
    Green: break 가 flush 4 줄 *이후* 위치 → PASS.

    회귀 차단: 사이클 78 의도 영역 (sleep 후 무조건 1회 flush 보장) 침범 영구 차단.
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    func = _get_function_node(source, "_api_recovered_collector_loop")

    assert func is not None, (
        "G-78-VERIFY-4 사전조건: `_api_recovered_collector_loop` 함수 정의 미존재"
    )

    # while body 내 statement 순서 분석
    while_node = None
    for sub in ast.walk(func):
        if isinstance(sub, ast.While):
            while_node = sub
            break
    assert while_node is not None, (
        "G-78-VERIFY-4 사전조건: while loop 미존재 — 사이클 76 영속 영역 침범"
    )

    # body 안 statement 순서 = sleep → flush 4 영역 → break 영속
    body = while_node.body
    flush_indexes: list[int] = []
    break_indexes: list[int] = []

    for idx, stmt in enumerate(body):
        # flush_*_collector 호출 사이트 탐지 (Try 블록 안에 있을 수 있음)
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Call):
                func_node = sub.func
                if isinstance(func_node, ast.Name) and func_node.id in (
                    "flush_swing_rest_poll_collector",
                    "flush_stale_watcher_collector",
                ):
                    flush_indexes.append(idx)
                    break
                if isinstance(func_node, ast.Attribute) and func_node.attr in (
                    "flush_swing_rest_poll_collector",
                    "flush_stale_watcher_collector",
                ):
                    flush_indexes.append(idx)
                    break
        # break statement 안에 if not self._running 가드 탐지
        if isinstance(stmt, ast.If):
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Break):
                    break_indexes.append(idx)
                    break

    assert flush_indexes, (
        "G-78-VERIFY-4 사전조건: flush 호출 사이트 미존재 (G-78-VERIFY-2 영속 의존)"
    )
    assert break_indexes, (
        "G-78-VERIFY-4 사전조건: `if not self._running: break` 패턴 미존재 — "
        "사이클 76 영속 영역 침범"
    )

    last_flush_idx = max(flush_indexes)
    first_break_idx = min(break_indexes)

    assert first_break_idx > last_flush_idx, (
        f"\n사이클 102 G-78-VERIFY-4 위반 — `if not self._running: break` 위치 영역 침범:\n"
        f"  마지막 flush 위치: index {last_flush_idx}\n"
        f"  첫 break 위치: index {first_break_idx}\n\n"
        f"  사이클 78 영속 의도 (영역 1 코드 변경 0):\n"
        f"  - sleep → flush 4 줄 → `if not self._running: break` 순서 영속\n"
        f"  - sleep 후 무조건 1회 flush 보장 = 마지막 flush 보장 영구 가드\n"
        f"  - 사이클 78 hotfix 의도 = `_running=False` 직전에도 flush 영속 보장\n"
    )
