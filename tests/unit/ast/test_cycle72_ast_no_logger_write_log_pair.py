"""사이클 72 G-6 — AST 영구 가드: logger.* + write_log 동시 호출 0건 (Red 단계).

옵션 A' + AST G-6 (사용자 결정):
- 11 사이트의 logger.info/warning + await write_log 동시 호출 패턴을 영구 차단.
- 시정 후 신규 사이트 도입 시 silent 결함 (재발) 영구 차단.

검증 방법:
- `src/` 전체 rglob *.py
- 각 `await write_log(` / `await _write_log(` / `asyncio.create_task(_write_log(` 사이트의
  ±5 줄 윈도우 내에 동일 prefix `[X]` 의 `logger.info(...)` / `logger.warning(...)` /
  `logger.error(...)` / `logger.exception(...)` 호출이 동시에 존재하는 위반 사이트 검출.

Red 단계 = 11 사이트 잔존 → FAIL.
Green 단계 = 옵션 A' 시정 후 0 건 → PASS.

화이트리스트:
- `safe_write_log` (사이클 56-E 통합 graceful 패턴) 는 단일 진입점 — try/except 내부의
  logger.debug fallback 은 별개 의미. `safe_write_log` 호출 자체를 검증하는 게 아니라
  *동일 사이트* 의 logger.* (info/warning/error/exception) 와 write_log 동시 호출 검출.
- `src/main.py::_DbLogHandler.emit` 내부 `_insert_log_to_db` 호출은 logger 위임 경로 —
  write_log 직접 호출 아니므로 무관.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"

# write_log fire-and-forget 패턴 포괄
_WRITE_LOG_CALL_RE = re.compile(
    r"(?:await\s+_?write_log\s*\(|asyncio\.create_task\s*\(\s*_?write_log\s*\()"
)

# logger.info/warning/error/exception/critical 호출 (debug 제외 — fallback 표준)
_LOGGER_CALL_RE = re.compile(
    r"logger\.(?:info|warning|error|exception|critical)\s*\("
)

# prefix `[X]` 추출 — write_log 호출 메시지 라인 또는 ±5 줄 내 등장
_PREFIX_RE = re.compile(r"\[([a-z_][a-z0-9_]*)\]")


def _iter_py_files() -> list[Path]:
    """src/ 전체 .py 파일 (테스트 제외)."""
    return sorted(_SRC_ROOT.rglob("*.py"))


def _find_violation_sites(source: str) -> list[tuple[int, str]]:
    """write_log 호출 사이트 + ±5 줄 내 동일 prefix logger.* 호출 동시 존재 사이트.

    Returns:
        [(write_log_line_no, prefix), ...] — 위반 (line_no 1-based)
    """
    lines = source.splitlines()
    violations: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        if not _WRITE_LOG_CALL_RE.search(line):
            continue
        # write_log 호출 라인 + ±5 줄 윈도우 텍스트
        start = max(0, i - 5)
        end = min(len(lines), i + 6)
        window = lines[start:end]
        window_text = "\n".join(window)

        # write_log 메시지에 등장하는 prefix `[X]` 들 추출
        prefixes_in_window = set(_PREFIX_RE.findall(window_text))
        if not prefixes_in_window:
            continue

        # 같은 윈도우 내 logger.* 호출 라인이 동일 prefix 메시지를 포함하는지
        for j in range(start, end):
            if j == i:
                continue
            if not _LOGGER_CALL_RE.search(lines[j]):
                continue
            # logger.* 호출의 메시지 (해당 줄 + 다음 3줄까지 multiline 인자 흡수)
            logger_text = "\n".join(lines[j:min(len(lines), j + 4)])
            logger_prefixes = set(_PREFIX_RE.findall(logger_text))
            shared = prefixes_in_window & logger_prefixes
            if shared:
                violations.append((i + 1, next(iter(shared))))
                break

    return violations


def test_g_6_no_logger_write_log_pair_within_5_lines() -> None:
    """G-6: src/ 전체 write_log 호출 ±5 줄에 동일 prefix logger.* 호출 0건.

    옵션 A' 시정 후 11 사이트의 이중 호출 패턴 영구 차단.
    """
    all_violations: dict[str, list[tuple[int, str]]] = {}
    for py_file in _iter_py_files():
        # 본 가드 파일 자체는 검사 제외
        if py_file.name.startswith("test_"):
            continue
        source = py_file.read_text(encoding="utf-8")
        violations = _find_violation_sites(source)
        if violations:
            rel = py_file.relative_to(_SRC_ROOT.parent)
            all_violations[str(rel)] = violations

    total = sum(len(v) for v in all_violations.values())
    detail = "\n".join(
        f"  {path}: {len(sites)} site(s) — "
        f"lines {[(line, prefix) for line, prefix in sites]}"
        for path, sites in sorted(all_violations.items())
    )
    assert total == 0, (
        f"\n사이클 72 G-6 위반 — write_log 호출 ±5 줄 내 동일 prefix logger.* 동시 "
        f"호출 사이트 총 {total} 건 (옵션 A' 시정 필요):\n{detail}\n"
        f"\nsystem_logs 이중 INSERT 결함 (사이클 71 root cause). 옵션 A' = logger.* "
        f"단독 유지 + write_log 호출 제거 (logger 가 _DbLogHandler 위임으로 INSERT)."
    )
