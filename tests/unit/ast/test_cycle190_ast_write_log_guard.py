"""사이클 190 Red — write_log never-raise 불변식 + 재귀 차단 AST 영구 가드.

결함 (2026-07-03 07:59 운영 실증):
- write_log 가 INSERT 실패 시 raise → 관찰성 INSERT 가 매매 프로세스를 죽임.

Green 계약 (본 가드가 영구 강제):
- A-1: write_log 본체 = broad except Try 존재 + except 절 내 raise 0건 (never-raise 불변식)
- A-2: write_log except 절 내 logger.debug 호출 + logger.warning/error/critical/write_log
       재호출 0건 (_DbLogHandler 재귀/무한 INSERT 차단, safe_write_log 사이클 56-E 답습)
- A-3: scheduler.start() 크래시 핸들러 write_log 호출에 `type(exc).__name__` 계측 동반
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_ROOT = Path(__file__).resolve().parents[3]
_SYSTEM_LOGS_PY = _ROOT / "src" / "db" / "system_logs.py"
_SCHEDULER_PY = _ROOT / "src" / "engine" / "scheduler.py"


def _find_async_func(tree: ast.AST, name: str) -> ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def _write_log_node() -> ast.AsyncFunctionDef:
    tree = ast.parse(_SYSTEM_LOGS_PY.read_text(encoding="utf-8"))
    node = _find_async_func(tree, "write_log")
    assert node is not None, "write_log 비동기 함수 미존재"
    return node


def _except_handlers_in(node: ast.AST) -> list[ast.ExceptHandler]:
    """node 하위의 모든 except handler 수집."""
    handlers: list[ast.ExceptHandler] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Try):
            handlers.extend(sub.handlers)
    return handlers


def _attr_calls_in(nodes: list[ast.stmt], obj: str, attr: str) -> int:
    """nodes 하위에서 `obj.attr(...)` 호출 카운트 (예: logger.debug)."""
    count = 0
    for stmt in nodes:
        for sub in ast.walk(stmt):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == attr
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == obj
            ):
                count += 1
    return count


def _name_calls_in(nodes: list[ast.stmt], name: str) -> int:
    """nodes 하위에서 `name(...)` (또는 await name(...)) 호출 카운트."""
    count = 0
    for stmt in nodes:
        for sub in ast.walk(stmt):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == name
            ):
                count += 1
    return count


# ---------------------------------------------------------------------------
# A-1: write_log broad except Try 존재 + except 내 raise 0건
# ---------------------------------------------------------------------------


def test_a1_write_log_has_broad_except_no_reraise():
    """write_log 본체에 broad except Try 존재 + except 절 내 raise 0건 (never-raise)."""
    node = _write_log_node()

    tries = [n for n in ast.walk(node) if isinstance(n, ast.Try)]
    assert tries, (
        "A-1: write_log 본체에 try/except 부재 — never-raise 전환 미적용 "
        "(INSERT 실패가 그대로 전파 → 매매 프로세스 종료 위험)"
    )

    handlers = _except_handlers_in(node)
    assert handlers, "A-1: write_log 에 except handler 부재"

    # broad except 여부 — `except Exception` 또는 bare `except`
    broad = any(
        (h.type is None)
        or (isinstance(h.type, ast.Name) and h.type.id in ("Exception", "BaseException"))
        for h in handlers
    )
    assert broad, (
        "A-1: write_log except 가 broad(`except Exception`) 가 아님 — "
        "특정 예외만 잡으면 connection 계열 외 예외가 전파될 수 있음"
    )

    # except 본체에 raise 0건 (재전파 금지)
    reraises = 0
    for h in handlers:
        for sub in ast.walk(h):
            if isinstance(sub, ast.Raise):
                reraises += 1
    assert reraises == 0, (
        f"A-1: write_log except 절 내 raise {reraises}건 — never-raise 불변식 위반"
    )


# ---------------------------------------------------------------------------
# A-2: except 절 내 logger.debug 만 + warning/error/critical/write_log 0건
# ---------------------------------------------------------------------------


def test_a2_write_log_except_debug_only_no_recursion():
    """write_log except 절 = logger.debug 발화 + WARNING 이상/write_log 재호출 0건."""
    node = _write_log_node()
    handlers = _except_handlers_in(node)
    assert handlers, "A-2: write_log except handler 부재"

    handler_bodies: list[ast.stmt] = []
    for h in handlers:
        handler_bodies.extend(h.body)

    debug_calls = _attr_calls_in(handler_bodies, "logger", "debug")
    assert debug_calls >= 1, (
        "A-2: write_log except 절에 logger.debug 호출 부재 "
        "(실패 흔적 stdout 보존 의무)"
    )

    for forbidden in ("warning", "error", "critical", "exception", "info"):
        cnt = _attr_calls_in(handler_bodies, "logger", forbidden)
        assert cnt == 0, (
            f"A-2: write_log except 절에 logger.{forbidden} 호출 {cnt}건 — "
            f"_DbLogHandler 가 DB INSERT 재시도 → 재귀/무한 루프 위험 (사이클 56-E 답습)"
        )

    reentry = _name_calls_in(handler_bodies, "write_log")
    assert reentry == 0, (
        f"A-2: write_log except 절에 write_log 재호출 {reentry}건 — 재귀 위험"
    )


# ---------------------------------------------------------------------------
# A-3: 크래시 핸들러 write_log 호출에 type(exc).__name__ 계측 동반
# ---------------------------------------------------------------------------


def test_a3_crash_handler_write_log_has_exc_type_token():
    """scheduler.start() 크래시 핸들러 영역에 `type(exc).__name__` 계측 토큰 존재."""
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    start_node = _find_async_func(tree, "start")
    assert start_node is not None, "scheduler.start() 미존재"

    body_src = ast.unparse(start_node)
    assert "매매 프로세스 비정상 종료" in body_src, (
        "A-3: 크래시 핸들러 메시지 접두 보존 의무"
    )
    assert "type(exc).__name__" in body_src, (
        "A-3: 크래시 핸들러 write_log ERROR 에 `type(exc).__name__` 계측 부재 — "
        "사이클 190 진단성 확보 위반"
    )
