"""사이클 73 G-SCH1 — `_run_swing_rest_poll_once` 사이트 write_log 호출 0건 (Red 단계).

옵션 A' 시정 (사이클 72 답습 + 영역 확장):
- `src/engine/scheduler.py::_run_swing_rest_poll_once` 에서 `logger.info` +
  `await write_log("INFO", "[swing_rest_poll] ...")` 동시 호출 = system_logs 이중 INSERT root cause.
- 시정 = `write_log` 직접 호출 제거 (`logger.info` 단독 유지 — `_DbLogHandler` 위임 단일 INSERT).

Red 단계 = `await write_log("INFO", "[swing_rest_poll] ...")` 1건 잔존 → FAIL.
Green 단계 = 시정 후 0건 → PASS.

donchian_swing 60s 주기 폴링 = 09:30~15:20 KRX 메인 5.83 시간 = 350 회/일 emit.
사이클 72 영역 누락 — system_logs 일일 350 dup 잠재 영역 차단.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


_SCHEDULER_PY = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
)


def _extract_function_lines(source: str, func_name: str) -> tuple[int, int]:
    """AST 로 함수 정의 line 범위 (start, end) 추출. 함수 미발견 시 (-1, -1)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            start = node.lineno
            end = node.end_lineno or start
            return start, end
    return -1, -1


def test_g_sch1_swing_rest_poll_once_no_write_log_call() -> None:
    """G-SCH1: `_run_swing_rest_poll_once` 함수 본체 write_log 호출 0건.

    사이클 72 옵션 A' 영역 확장 (S-1) — donchian_swing 60s 폴링 = 350회/일 emit
    영역의 system_logs 이중 INSERT 영구 차단.
    `logger.info("[swing_rest_poll] ...")` 단독 유지 (운영 가시화 보존).
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    start, end = _extract_function_lines(source, "_run_swing_rest_poll_once")
    assert start > 0, "_run_swing_rest_poll_once 함수 미발견"

    lines = source.splitlines()
    func_lines = lines[start - 1:end]

    violations: list[tuple[int, str]] = []
    for offset, line in enumerate(func_lines):
        absolute_line_no = start + offset
        # await write_log / await _write_log / asyncio.create_task(_write_log(
        if not re.search(
            r"(?:await\s+_?write_log\s*\(|asyncio\.create_task\s*\(\s*_?write_log\s*\()",
            line,
        ):
            continue
        stripped = line.strip()
        # 주석/docstring 라인 제외
        if stripped.startswith("#") or stripped.startswith('"'):
            continue
        violations.append((absolute_line_no, stripped))

    assert len(violations) == 0, (
        f"\n사이클 73 G-SCH1 위반 — `_run_swing_rest_poll_once` 본체 write_log 호출 잔존:\n"
        + "\n".join(f"  L{line_no}: {snippet}" for line_no, snippet in violations)
        + "\n\n시정: src/engine/scheduler.py L2324-2333 영역의 try/except + "
        f"await write_log 블록 제거. logger.info 단독 유지 = _DbLogHandler 위임 "
        f"단일 INSERT (사이클 72 옵션 A' 영역 확장)."
    )
