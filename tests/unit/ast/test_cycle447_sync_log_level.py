"""cycle447 제안 5 — `_scan_loop` 의 15분 포지션 동기화 실패 로그 DEBUG → WARNING.

정본 = `_workspace/analysis/balance_5xx_20261011/result.md` 제안 5. 로그 레벨만
바꾼다 — `scheduler.py` 는 승인 대상(8영역 동급, <3,900L 영구 상한)이라 로직은
그대로 두고 메시지만 확인한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCHEDULER = Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"


def _find_sync_except_handler() -> ast.ExceptHandler:
    tree = ast.parse(_SCHEDULER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        body_src = ast.dump(node)
        if "_sync_positions_from_balance" not in body_src:
            continue
        if not node.handlers:
            continue
        return node.handlers[0]
    raise AssertionError("`_sync_positions_from_balance` 를 감싼 try/except 를 못 찾았다")


def test_sync_failure_log_is_warning_not_debug():
    handler = _find_sync_except_handler()
    calls = [
        n for n in ast.walk(handler)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.value.id == "logger"  # type: ignore[union-attr]
    ]
    assert len(calls) == 1, f"except 블록의 logger 호출이 1개여야 한다 (실측 {len(calls)})"
    call = calls[0]
    assert call.func.attr == "warning", (  # type: ignore[union-attr]
        f"포지션 동기화 실패 로그가 여전히 `{call.func.attr}` 레벨이다 — WARNING 으로 "  # type: ignore[union-attr]
        "올려야 system_logs(21:30 분석)에 보인다"
    )
