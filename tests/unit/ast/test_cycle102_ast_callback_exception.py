"""사이클 102 영역 2-C — 3 콜백 일관 패턴 AST 영구 가드 (Red).

G-CALLBACK2 — `_handle_tick` (`_on_tick`) + `_handle_execution` (`_on_execution`) +
`_handle_market_op` (`_on_board`) 3 콜백 모두 `try/except` + `logger.exception` +
**`raise` 영속** 일관 패턴 AST 정적 검증.

영역 2-C = 사이클 88 G-REJECT-1 영구 영속 패턴 영구 가드 (silent 결함 영역 통일).

Red: production 미시정 → 3 콜백 중 ≥1건 패턴 누락 → FAIL.
Green: backend-dev 3 콜백 모두 일관 패턴 시정 후 PASS.

영속 의무:
- **사이클 88 G-REJECT-1 영구 영속**: 3 콜백 모두 `raise` 영속 = 재연결 trigger 영속
- 사이클 88 G-REJECT-2/3 영속 (변경 0)
- 매매 안전성 영향 0 (lifecycle 영역 정적 검증만)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source


pytestmark = pytest.mark.unit


_HANDLER_PY = (
    Path(__file__).resolve().parents[3] / "src" / "realtime" / "handler.py"
)


# 3 콜백 함수 + 해당 콜백 호출 시 호출되는 함수 이름 매핑
_CALLBACK_HANDLER_MAP = {
    "_handle_tick": "_on_tick",
    "_handle_execution": "_on_execution",
    "_handle_market_op": "_on_board",
}


def _get_function_node(source: str, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef | None:
    """모듈 전체에서 `name` 함수 정의 첫 노드 반환."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _find_try_around_callback(
    func: ast.AsyncFunctionDef | ast.FunctionDef, callback_name: str,
) -> ast.Try | None:
    """함수 body 내 `await <callback_name>(...)` 호출을 감싸는 `try/except` 블록 탐색.

    매칭 규칙:
    - `ast.Try` 노드의 body 안에 `ast.Await(value=ast.Call(func=ast.Name(id=callback_name)))` 존재
    """
    for try_node in ast.walk(func):
        if not isinstance(try_node, ast.Try):
            continue
        # body 안에 await callback_name(...) 호출 확인
        for sub in ast.walk(try_node):
            if not isinstance(sub, ast.Await):
                continue
            call = sub.value
            if not isinstance(call, ast.Call):
                continue
            cf = call.func
            if isinstance(cf, ast.Name) and cf.id == callback_name:
                return try_node
        # if 분기 안에 try 있을 수 있으므로 그대로 진행
    return None


def _try_block_has_logger_exception(try_node: ast.Try, prefix: str) -> bool:
    """try.handlers 안 logger.exception("[callback_exception] ...") 호출 존재 검증."""
    for handler in try_node.handlers:
        for sub in ast.walk(handler):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            # logger.exception(...) 또는 임의 .exception(...) 매칭
            if isinstance(func, ast.Attribute) and func.attr == "exception":
                # 첫 인자가 문자열 리터럴 + prefix 포함 확인
                if sub.args and isinstance(sub.args[0], ast.Constant):
                    val = sub.args[0].value
                    if isinstance(val, str) and prefix in val:
                        return True
    return False


def _try_block_has_raise(try_node: ast.Try) -> bool:
    """try.handlers 안에 bare `raise` 또는 `raise <expr>` 존재 검증."""
    for handler in try_node.handlers:
        for sub in ast.walk(handler):
            if isinstance(sub, ast.Raise):
                return True
    return False


# ===========================================================================
# G-CALLBACK2 — 3 콜백 일관 패턴 AST 영구 가드
# ===========================================================================
def test_g_callback2_three_handlers_consistent_try_except_raise():
    """G-CALLBACK2 (HIGH): 3 콜백 (`_handle_tick` / `_handle_execution` /
    `_handle_market_op`) 모두 `try/except` + `logger.exception("[callback_exception] ...")` +
    `raise` 일관 패턴 AST 정적 검증.

    Red: production 미시정 → 1+ 콜백 패턴 누락 → FAIL.
    Green: backend-dev 3 콜백 모두 일관 패턴 시정 후 PASS.

    영속 의무:
    - **사이클 88 G-REJECT-1 영구 영속**: `raise` 영속 = 재연결 trigger 영속
    - 단일 restore 도입 차단 영구 영속 (외부 의견 R4 반려 영속)
    - silent 흡수 영역 영구 차단 (예외 흡수 시 _receive_loop 무한 잔류 위험)

    검증 매트릭스 (3 콜백 × 3 패턴 = 9 항목 영속):
    - `_handle_tick` + `_on_tick` 콜백 → try/except + [callback_exception] + raise 영속
    - `_handle_execution` + `_on_execution` 콜백 → try/except + [callback_exception] + raise 영속
    - `_handle_market_op` + `_on_board` 콜백 → try/except + [callback_exception] + raise 영속
    """
    source = read_module_source(_HANDLER_PY)

    missing: list[str] = []
    for handler_func_name, callback_name in _CALLBACK_HANDLER_MAP.items():
        func = _get_function_node(source, handler_func_name)
        if func is None:
            missing.append(
                f"  - 함수 `{handler_func_name}` 정의 부재 (사이클 88 영속 영역 침범)"
            )
            continue

        try_node = _find_try_around_callback(func, callback_name)
        if try_node is None:
            missing.append(
                f"  - `{handler_func_name}`: `await {callback_name}(...)` 호출 감싸는 "
                f"`try/except` 블록 부재"
            )
            continue

        if not _try_block_has_logger_exception(try_node, "[callback_exception]"):
            missing.append(
                f"  - `{handler_func_name}`: `try/except` 영역에 "
                f"`logger.exception(\"[callback_exception] ...\")` 호출 부재"
            )

        if not _try_block_has_raise(try_node):
            missing.append(
                f"  - `{handler_func_name}`: `try/except` 영역에 `raise` 영속 부재 "
                f"(**사이클 88 G-REJECT-1 영구 영속 위반 — 재연결 trigger 영역 침범**)"
            )

    assert not missing, (
        f"\n사이클 102 G-CALLBACK2 위반 — 3 콜백 일관 패턴 영역 침범:\n"
        + "\n".join(missing)
        + "\n\n  사이클 102 영역 2-C 시정 영역 (영속 의무 영역):\n"
        f"  - 3 콜백 (`_handle_tick` + `_handle_execution` + `_handle_market_op`) 모두:\n"
        f"    if _on_<X>:\n"
        f"        try:\n"
        f"            await _on_<X>(...)\n"
        f"        except Exception:\n"
        f"            logger.exception('[callback_exception] handler=_on_<X> ticker=%s', ticker)\n"
        f"            raise  # 사이클 88 G-REJECT-1 재연결 trigger 영속\n\n"
        f"  영역 2-C 영구 가드:\n"
        f"  - 사이클 88 G-REJECT-1 영구 영속 (단일 restore 도입 차단 + 4중 안전망)\n"
        f"  - silent 흡수 영역 영구 차단 (예외 흡수 시 `_receive_loop` 무한 잔류 위험)\n"
        f"  - 매매 안전성 영향 0 (lifecycle 영역 정적 검증, 가시화 영역 한정)\n"
    )
