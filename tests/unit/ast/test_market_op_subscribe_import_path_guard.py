"""AST/정적 가드 (결함 1 재발 차단) — `kis_ws_pool` import 경로.

`kis_ws_pool` 은 `src.realtime.websocket_pool` 에만 정의된다(websocket.py 에는 없음).
`from src.realtime.websocket import ... kis_ws_pool` 은 런타임 ImportError 를 유발한다.

이 가드는 두 가지를 정적으로 단언한다:
1. src/ 전체에서 `from src.realtime.websocket import (...)` 에 `kis_ws_pool` 이 포함된 구문 0건.
   (현재 scheduler.py 함수-로컬 import 1건 → Red.)
2. scheduler.py 의 `_subscribe_market_operation_tickers` 함수 본체가
   `kis_ws_pool` 을 반드시 `src.realtime.websocket_pool` 에서 import 하고,
   `src.realtime.websocket` 에서는 import 하지 않는다.
   (현재 websocket 에서 kis_ws_pool 을 import + websocket_pool import 없음 → Red.)

정적 분석이라 실제 호출 없이 소스 텍스트만으로 재발을 차단한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_SCHEDULER_PATH = _SRC / "engine" / "scheduler.py"


def _is_websocket_module(module: str | None) -> bool:
    """`src.realtime.websocket` (websocket_pool 은 제외) 모듈 여부."""
    if not module:
        return False
    return module.endswith("realtime.websocket") and not module.endswith(
        "realtime.websocket_pool"
    )


def _is_websocket_pool_module(module: str | None) -> bool:
    if not module:
        return False
    return module.endswith("realtime.websocket_pool")


def test_no_src_module_imports_kis_ws_pool_from_websocket() -> None:
    """src/ 전체에서 `from src.realtime.websocket import ... kis_ws_pool` 0건.

    현재 scheduler.py:~3544 함수-로컬 import 1건 → Red.
    """
    offenders: list[str] = []
    for py in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not _is_websocket_module(node.module):
                continue
            if any(alias.name == "kis_ws_pool" for alias in node.names):
                rel = py.relative_to(_ROOT)
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], (
        "kis_ws_pool 은 src.realtime.websocket 에 존재하지 않음 → ImportError. "
        "src.realtime.websocket_pool 에서 import 하도록 분리할 것. 위반: "
        + ", ".join(offenders)
    )


def _get_function_node(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"함수 {name} 미발견")


def test_market_op_function_imports_pool_from_websocket_pool() -> None:
    """`_subscribe_market_operation_tickers` 는 kis_ws_pool 을 websocket_pool 에서만 import.

    - websocket_pool 에서 kis_ws_pool import 존재해야 함.
    - websocket 에서 kis_ws_pool import 는 없어야 함.
    현재 코드는 websocket 에서 (kis_ws, kis_ws_pool) 를 함께 import + websocket_pool import 부재 → Red.
    """
    tree = ast.parse(_SCHEDULER_PATH.read_text(encoding="utf-8"))
    fn = _get_function_node(tree, "_subscribe_market_operation_tickers")

    pool_import_ok = False
    ws_imports_pool = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.ImportFrom):
            continue
        names = {alias.name for alias in node.names}
        if _is_websocket_pool_module(node.module) and "kis_ws_pool" in names:
            pool_import_ok = True
        if _is_websocket_module(node.module) and "kis_ws_pool" in names:
            ws_imports_pool = True

    assert not ws_imports_pool, (
        "kis_ws_pool 을 src.realtime.websocket 에서 import 하면 ImportError (결함 1)."
    )
    assert pool_import_ok, (
        "kis_ws_pool 은 src.realtime.websocket_pool 에서 import 해야 한다."
    )
