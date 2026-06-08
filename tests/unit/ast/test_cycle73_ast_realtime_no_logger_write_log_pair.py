"""사이클 73 G-6.R — AST 영구 가드: src/realtime/ logger.* + write_log 동시 호출 0건.

사이클 72 G-6 AST 가드 영역 확장 (`src/` 전체 → `src/realtime/` 한정 정밀 가드).

배경:
- 사이클 72 G-6 AST 가드 (`src/` 전체) 는 시정 완료 후 사이클 73 신규 영역 (R-1/R-2/S-1)
  발견 시 즉시 FAIL → 결함 가시화 (사이클 72 영역 영속 + 사이클 73 영역 신규 검출).
- 본 G-6.R = `src/realtime/` 디렉토리 한정 영역 가드 — 시정 후 0건 보장 +
  미래 신규 사이트 silent 결함 영구 차단.

Red 단계 = R-1 (`[ws_reverify]`) + R-2 (`[ws_subscribe_reject]`) 2 사이트 잔존 → FAIL.
Green 단계 = 시정 후 0건 → PASS.

화이트리스트:
- `safe_write_log` (사이클 56-E 통합 graceful 패턴) 는 단일 진입점 — try/except 내부 fallback
  logger.debug 는 별개 의미. 동일 사이트 logger.* (info/warning/error/exception) 와
  write_log 동시 호출 검출만.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_REALTIME_ROOT = Path(__file__).resolve().parents[3] / "src" / "realtime"

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
    """src/realtime/ 전체 .py 파일 (테스트 제외)."""
    return sorted(_REALTIME_ROOT.rglob("*.py"))


def _find_violation_sites(source: str) -> list[tuple[int, str]]:
    """write_log 호출 사이트 + ±10 줄 내 동일 prefix logger.* 호출 동시 존재 사이트.

    사이클 73 영역 보강 — multi-line `logger.warning(...)` 호출이 ±5 줄 윈도우 밖으로
    벗어나는 케이스 (L380~L384 5줄 logger.warning + L386 write_log) 검출 위해 ±10 줄 확장.
    사이클 72 G-6 단방향 ±5 줄 가드 한계 보강.
    """
    lines = source.splitlines()
    violations: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        if not _WRITE_LOG_CALL_RE.search(line):
            continue
        start = max(0, i - 10)
        end = min(len(lines), i + 11)
        window = lines[start:end]
        window_text = "\n".join(window)

        prefixes_in_window = set(_PREFIX_RE.findall(window_text))
        if not prefixes_in_window:
            continue

        for j in range(start, end):
            if j == i:
                continue
            if not _LOGGER_CALL_RE.search(lines[j]):
                continue
            # logger.* multi-line 메시지 흡수 — 다음 6줄까지 (multi-line 인자 포괄)
            logger_text = "\n".join(lines[j:min(len(lines), j + 7)])
            logger_prefixes = set(_PREFIX_RE.findall(logger_text))
            shared = prefixes_in_window & logger_prefixes
            if shared:
                violations.append((i + 1, next(iter(shared))))
                break

    return violations


def test_g_6_r_no_logger_write_log_pair_in_realtime() -> None:
    """G-6.R: src/realtime/ 전체 write_log 호출 ±5 줄에 동일 prefix logger.* 호출 0건.

    사이클 73 옵션 A' 시정 후 영구 가드 — 미래 신규 사이트 silent 결함 영구 차단.
    """
    all_violations: dict[str, list[tuple[int, str]]] = {}
    for py_file in _iter_py_files():
        if py_file.name.startswith("test_"):
            continue
        source = py_file.read_text(encoding="utf-8")
        violations = _find_violation_sites(source)
        if violations:
            rel = py_file.relative_to(_REALTIME_ROOT.parent.parent)
            all_violations[str(rel)] = violations

    total = sum(len(v) for v in all_violations.values())
    detail = "\n".join(
        f"  {path}: {len(sites)} site(s) — "
        f"lines {[(line, prefix) for line, prefix in sites]}"
        for path, sites in sorted(all_violations.items())
    )
    assert total == 0, (
        f"\n사이클 73 G-6.R 위반 — src/realtime/ write_log 호출 ±5 줄 내 동일 prefix "
        f"logger.* 동시 호출 사이트 총 {total} 건 (옵션 A' 시정 필요):\n{detail}\n"
        f"\nsystem_logs 이중 INSERT 결함 (사이클 73 영역 R-1/R-2). 옵션 A' = logger.* "
        f"단독 유지 + write_log 호출 제거 (logger 가 _DbLogHandler 위임으로 INSERT)."
    )
