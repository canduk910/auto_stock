"""사이클 73 G-6.S — AST 영구 가드: scheduler.py::_run_swing_rest_poll_once 함수 영역
logger.* + write_log 동시 호출 0건.

사이클 72 G-6 AST 가드 영역 확장 (`src/` 전체 → 함수 영역 한정 정밀 가드).

배경:
- 함수 영역 한정 가드 = 모듈 전역 가드가 다른 영역 정상 호출을 false-positive 검출 못하게
  하면서, 특정 hot path 함수 (`_run_swing_rest_poll_once`) 영역의 silent 결함만 정밀 감시.
- donchian_swing 60s 폴링 = 350회/일 emit hot path — sub-module 분해 후 재발 영구 차단.

Red 단계 = S-1 (`[swing_rest_poll]`) 1 사이트 잔존 → FAIL.
Green 단계 = 시정 후 0건 → PASS.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.unit.ast._ast_helpers import read_module_source


_SCHEDULER_PY = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
)

_WRITE_LOG_CALL_RE = re.compile(
    r"(?:await\s+_?write_log\s*\(|asyncio\.create_task\s*\(\s*_?write_log\s*\()"
)
_LOGGER_CALL_RE = re.compile(
    r"logger\.(?:info|warning|error|exception|critical)\s*\("
)
_PREFIX_RE = re.compile(r"\[([a-z_][a-z0-9_]*)\]")


def _extract_function_lines(source: str, func_name: str) -> tuple[int, int]:
    """AST 로 함수 정의 line 범위 (1-based start, end inclusive). 미발견 시 (-1, -1)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            start = node.lineno
            end = node.end_lineno or start
            return start, end
    return -1, -1


def test_g_6_s_no_logger_write_log_pair_in_swing_rest_poll_once() -> None:
    """G-6.S: `_run_swing_rest_poll_once` 함수 영역 write_log 호출 ±5 줄에 동일 prefix
    logger.* 호출 0건.

    사이클 73 옵션 A' 시정 후 영구 가드 — 함수 영역 한정 silent 결함 영구 차단.
    """
    source = read_module_source(_SCHEDULER_PY)
    start, end = _extract_function_lines(source, "_run_swing_rest_poll_once")
    assert start > 0, "_run_swing_rest_poll_once 함수 미발견"

    lines = source.splitlines()
    # 함수 영역 라인만 (1-based → 0-based 변환)
    func_lines_with_idx = list(enumerate(lines[start - 1:end], start=start))

    violations: list[tuple[int, str]] = []
    func_line_count = len(func_lines_with_idx)

    for local_i, (absolute_line_no, line) in enumerate(func_lines_with_idx):
        if not _WRITE_LOG_CALL_RE.search(line):
            continue
        # 함수 영역 한정 ±10 줄 윈도우 (multi-line logger.* 호출 흡수, 사이클 73 보강)
        ws = max(0, local_i - 10)
        we = min(func_line_count, local_i + 11)
        window_lines = [func_lines_with_idx[k][1] for k in range(ws, we)]
        window_text = "\n".join(window_lines)

        prefixes_in_window = set(_PREFIX_RE.findall(window_text))
        if not prefixes_in_window:
            continue

        for j in range(ws, we):
            if j == local_i:
                continue
            if not _LOGGER_CALL_RE.search(func_lines_with_idx[j][1]):
                continue
            # multi-line logger 메시지 흡수 (7줄)
            logger_text = "\n".join(
                func_lines_with_idx[k][1]
                for k in range(j, min(func_line_count, j + 7))
            )
            logger_prefixes = set(_PREFIX_RE.findall(logger_text))
            shared = prefixes_in_window & logger_prefixes
            if shared:
                violations.append((absolute_line_no, next(iter(shared))))
                break

    detail = "\n".join(
        f"  L{line_no}: prefix=[{prefix}]" for line_no, prefix in violations
    )
    assert len(violations) == 0, (
        f"\n사이클 73 G-6.S 위반 — `_run_swing_rest_poll_once` 함수 영역 write_log 호출 "
        f"±5 줄 내 동일 prefix logger.* 동시 호출 사이트 총 {len(violations)} 건 "
        f"(옵션 A' 시정 필요):\n{detail}\n"
        f"\nsystem_logs 이중 INSERT 결함 (사이클 73 영역 S-1, donchian 60s 폴링 350회/일 "
        f"hot path). 옵션 A' = logger.* 단독 유지 + write_log 호출 제거."
    )
