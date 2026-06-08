"""사이클 74 G-7/G-8 — AST 영구 가드: aggregator helper 의무 사용.

G-7: `_send_subscribe` 본문 `logger.info("WebSocket 구독/해제 ...")` 직접 호출 0건.
G-8: `_run_swing_rest_poll_once` 본문 + stale_watcher_core `check_and_resubscribe_stale`
     본문 `logger.info("[swing_rest_poll] ...")` / `logger.info("[stale_watcher] ...")`
     직접 호출 0건.

Red 단계 = 직접 logger.info 잔존 → FAIL.
Green 단계 = aggregator helper (`_record_action` / `record_swing_rest_poll` /
            `record_stale_watcher_check`) 흡수 후 PASS.

영구 가드 — 미래 신규 사이트 silent 결함 영구 차단.
사이클 67 G-16 / 사이클 73 G-6.R AST 패턴 100% 답습.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"


def _extract_function_lines(source: str, func_name: str) -> tuple[int, int]:
    """AST 로 함수 정의 line 범위 (start, end) 추출. 미발견 시 (-1, -1)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            start = node.lineno
            end = node.end_lineno or start
            return start, end
    return -1, -1


def _find_logger_info_calls_in_function(
    py_path: Path, func_name: str
) -> list[tuple[int, str]]:
    """함수 본체에서 `logger.info(...)` 호출 사이트 추출 — (line_no, line_text)."""
    source = py_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "info"
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "logger"
                ):
                    line_no = sub.lineno
                    line_text = source.splitlines()[line_no - 1].strip()
                    violations.append((line_no, line_text))
    return violations


# ===========================================================================
# G-7: `_send_subscribe` 본문 logger.info(...) 직접 호출 0건
# ===========================================================================
def test_g_7_send_subscribe_no_direct_logger_info():
    """G-7: `KisWebSocket._send_subscribe` 본문에 logger.info(...) 직접 호출 0건.

    옵션 E-1 aggregator (`_record_action`) 흡수 의무. dup 6.68x → ≤2.0x 영속.
    """
    py = _SRC_ROOT / "realtime" / "websocket.py"
    violations = _find_logger_info_calls_in_function(py, "_send_subscribe")
    assert len(violations) == 0, (
        f"\n사이클 74 G-7 위반 — `_send_subscribe` 본문 logger.info 직접 호출 {len(violations)} 건:\n"
        + "\n".join(f"  L{ln}: {txt}" for ln, txt in violations)
        + "\n\n시정: 사이클 74 옵션 E-1 aggregator (`_record_action`) 흡수 의무. "
        "직접 logger.info 호출 제거 → collector 5분 주기 `[ws_action_summary]` 단일 행 emit."
    )


# ===========================================================================
# G-8: `_run_swing_rest_poll_once` + `check_and_resubscribe_stale` 본문
#      직접 logger.info(...) 0건
# ===========================================================================
def _find_logger_info_with_prefix_in_function(
    py_path: Path, func_name: str, allowed_prefixes: set[str], target_prefix: str
) -> list[tuple[int, str]]:
    """AST 로 함수 본문 `logger.info(prefix, ...)` 호출 추출 — multi-line 호환.

    `target_prefix` (예: `[swing_rest_poll]`) 로 시작하지만 `allowed_prefixes`
    (예: `[swing_rest_poll_summary]`) 로 시작하지 *않는* 호출만 위반.
    `logger.exception` / `logger.debug` / `logger.warning` / `logger.error` 는 제외.
    """
    source = py_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations: list[tuple[int, str]] = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if not (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            continue
        for sub in ast.walk(node):
            if not (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "info"
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "logger"
            ):
                continue
            # 첫 인자가 문자열 리터럴인지 검증
            if not sub.args:
                continue
            first = sub.args[0]
            msg = None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                msg = first.value
            if msg is None:
                continue
            # target prefix 매칭 + allowed prefix 제외
            if not msg.startswith(target_prefix):
                continue
            if any(msg.startswith(p) for p in allowed_prefixes):
                continue
            line_no = sub.lineno
            line_text = lines[line_no - 1].strip()
            violations.append((line_no, line_text))
    return violations


def test_g_8_run_swing_rest_poll_once_no_direct_logger_info_summary_prefix():
    """G-8-A: `_run_swing_rest_poll_once` 본문에 `[swing_rest_poll]` prefix
    `logger.info(...)` 직접 호출 0건 — aggregator (`record_swing_rest_poll`) 흡수 의무.

    debug / exception / error / warning 은 영속 (graceful 분기 보존).
    `[swing_rest_poll_summary]` prefix (aggregator flush 단독) 는 허용.
    multi-line 호환 — AST 기반 검출.
    """
    py = _SRC_ROOT / "engine" / "scheduler.py"
    violations = _find_logger_info_with_prefix_in_function(
        py, "_run_swing_rest_poll_once",
        allowed_prefixes={"[swing_rest_poll_summary]"},
        target_prefix="[swing_rest_poll]",
    )

    assert len(violations) == 0, (
        f"\n사이클 74 G-8-A 위반 — `_run_swing_rest_poll_once` 본문 "
        f"`logger.info('[swing_rest_poll] ...')` 직접 호출 {len(violations)} 건:\n"
        + "\n".join(f"  L{ln}: {txt}" for ln, txt in violations)
        + "\n\n시정: 사이클 74 옵션 C aggregator (`record_swing_rest_poll`) 흡수 의무. "
        "`[swing_rest_poll_summary]` prefix 단일 행 5분 주기 emit (80% 감소)."
    )


def test_g_8_check_and_resubscribe_stale_no_direct_logger_info_summary_prefix():
    """G-8-B: `check_and_resubscribe_stale` 본문에 `[stale_watcher]` prefix
    `logger.info(...)` 직접 호출 0건 — aggregator (`record_stale_watcher_check`) 흡수 의무.

    `[stale_watcher_summary]` 는 aggregator flush, `[stale_watcher_detail]` 는
    사이클 73 individual 영속 영역 — 모두 허용.
    `[stale_priority_resubscribe]` / `[stale_priority_resubscribe_cap_exceeded]` /
    `[stale_force_retry_cap]` / `[stale_force_retry]` 는 사이클 17/29/66 영속 — 허용.
    multi-line 호환 — AST 기반 검출.
    """
    py = _SRC_ROOT / "engine" / "stale_watcher_core.py"
    violations = _find_logger_info_with_prefix_in_function(
        py, "check_and_resubscribe_stale",
        allowed_prefixes={
            "[stale_watcher_summary]",
            "[stale_watcher_detail]",
            "[stale_priority_resubscribe]",
            "[stale_priority_resubscribe_cap_exceeded]",
            "[stale_force_retry]",
            "[stale_force_retry_cap]",
        },
        target_prefix="[stale_watcher]",
    )

    assert len(violations) == 0, (
        f"\n사이클 74 G-8-B 위반 — `check_and_resubscribe_stale` 본문 "
        f"`logger.info('[stale_watcher] ...')` 정상 흐름 직접 호출 {len(violations)} 건:\n"
        + "\n".join(f"  L{ln}: {txt}" for ln, txt in violations)
        + "\n\n시정: 사이클 74 옵션 C 조건부 aggregator (`record_stale_watcher_check`) 흡수. "
        "`[stale_watcher_summary]` 단일 행 5분 주기 emit (97% 감소). "
        "단 `[stale_watcher_detail]` (사이클 73) / `[stale_force_retry_cap]` (사이클 66 K-10) / "
        "`[stale_priority_resubscribe_cap_exceeded]` (사이클 66 K-10) 는 individual 영속 영역."
    )
