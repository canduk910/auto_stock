"""AST/정적 가드 (결함 1 재발 차단) — `kis_ws_pool` import 경로.

`kis_ws_pool` 은 `src.realtime.websocket_pool` 에만 정의된다(websocket.py 에는 없음).
`from src.realtime.websocket import ... kis_ws_pool` 은 런타임 ImportError 를 유발한다.

이 가드는 두 가지를 정적으로 단언한다:
1. src/ 전체에서 `from src.realtime.websocket import (...)` 에 `kis_ws_pool` 이 포함된 구문 0건.
   (현재 scheduler.py 함수-로컬 import 1건 → Red.)
2. VI 구독 **본체** 함수가 `kis_ws_pool` 을 반드시 `src.realtime.websocket_pool` 에서
   import 하고, `src.realtime.websocket` 에서는 import 하지 않는다.
   (원 Red 시점: websocket 에서 kis_ws_pool 을 import + websocket_pool import 없음.)

정적 분석이라 실제 호출 없이 소스 텍스트만으로 재발을 차단한다.

cycle292 (2026-09-14) — 본체가 `scheduler.py` 에서
`src/engine/market_op_subscribe.py::subscribe_market_operation_tickers` 로 이동했다.
(2) 를 그 leaf 로 재조준한다. (1) 은 `_SRC.rglob("*.py")` 전수라 신규 leaf 를 **자동 커버**
하므로 무수정이다. ⚠️ (1) 은 import **경로**만 보므로 함수-로컬 import 를 모듈 최상단으로
승격하는 변경은 못 막는다 — 그건 monkeypatch 무력화 + 조기 반환으로 부정 단언 6케이스를
조용히 초록으로 만든다. 그 함정은
`tests/unit/ast/test_cycle292_ast_market_op_leaf.py::G-292-1` 이 맡는다.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_SCHEDULER_PATH = _SRC / "engine" / "scheduler.py"
# cycle292 — VI 구독 본체가 사는 leaf.
_BODY_PATH = _SRC / "engine" / "market_op_subscribe.py"
_BODY_FN = "subscribe_market_operation_tickers"


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

    원 Red 시점: scheduler.py 함수-로컬 import 1건.
    cycle292 이후 검사 면적에 `src/engine/market_op_subscribe.py` 가 자동 포함된다.
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
    """VI 구독 본체는 kis_ws_pool 을 websocket_pool 에서만 import.

    - websocket_pool 에서 kis_ws_pool import 존재해야 함.
    - websocket 에서 kis_ws_pool import 는 없어야 함.
    원 Red 시점: websocket 에서 (kis_ws, kis_ws_pool) 를 함께 import + websocket_pool 부재.
    cycle292 — 검사 대상이 `market_op_subscribe.subscribe_market_operation_tickers` 다.
    존재 단언 + 부재 단언 **쌍**이라 공허 통과가 구조적으로 불가능하다(강도 불변).
    """
    assert _BODY_PATH.exists(), (
        f"본체 leaf 부재: {_BODY_PATH} — 기준선 소실은 명시 FAIL(공허 초록 차단)"
    )
    tree = ast.parse(_BODY_PATH.read_text(encoding="utf-8"))
    fn = _get_function_node(tree, _BODY_FN)

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
