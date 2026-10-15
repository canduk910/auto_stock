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

# 사이클 137 (2026-06-15) — 카드 #25 AST DRY 헬퍼 모듈 마이그레이션.
from tests.unit.ast._ast_helpers import read_module_source as _read


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
        source = _read(py_file)
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


# ---------------------------------------------------------------------------
# cycle458 — 같은 식(변수 포함) 쌍 검출 (사용자 결정 2026-10-15 「1개 사건은 1번만 로그」)
#
# 위 G-6 은 `logger.*` 호출 *텍스트*에서 `[prefix]` 리터럴을 찾는다. 메시지를 변수(`msg`)로
# 만들어 `logger.warning(msg)` + `await write_log("WARNING", msg)` 로 넘기면 리터럴이
# 호출 줄에 없어 놓친다(10-14 `[tick_coverage]` 121회 발화 → system_logs 242행).
# G-458 은 AST 로 같은 함수 본문 안의 두 호출을 찾아, write_log 계열의 메시지 인자와
# logger.<level> 의 메시지 인자(첫 인자, 또는 `"%s"` 뒤 인자)가 **같은 식**이면 위반이다.
# ---------------------------------------------------------------------------
import ast as _ast

_G458_LOGGER_LEVELS = frozenset({"info", "warning", "error", "exception", "critical"})
_G458_WRITE_LOG_NAMES = frozenset({"write_log", "_write_log", "safe_write_log"})


def _g458_callee_name(func: _ast.expr) -> str | None:
    if isinstance(func, _ast.Name):
        return func.id
    if isinstance(func, _ast.Attribute):
        return func.attr
    return None


def _g458_is_logger_call(node: _ast.Call) -> bool:
    func = node.func
    if not (isinstance(func, _ast.Attribute) and func.attr in _G458_LOGGER_LEVELS):
        return False
    recv = func.value
    return isinstance(recv, _ast.Name) and (
        "logger" in recv.id.lower() or recv.id in {"log", "_log"}
    )


def _g458_write_log_message(node: _ast.Call) -> _ast.expr | None:
    if _g458_callee_name(node.func) not in _G458_WRITE_LOG_NAMES:
        return None
    if len(node.args) >= 2:
        return node.args[1]
    for kw in node.keywords:
        if kw.arg == "message":
            return kw.value
    return None


def _g458_logger_messages(node: _ast.Call) -> list[_ast.expr]:
    if not node.args:
        return []
    first = node.args[0]
    msgs = [first]
    if isinstance(first, _ast.Constant) and first.value == "%s" and len(node.args) >= 2:
        msgs.append(node.args[1])
    return msgs


def _find_same_expr_pairs(source: str) -> list[tuple[str, int, int, str]]:
    """[(함수 이름, logger 줄, write_log 줄, 메시지 식)] — 같은 식을 두 경로로 남기는 쌍."""
    tree = _ast.parse(source)
    found: set[tuple[str, int, int, str]] = set()
    for fn in _ast.walk(tree):
        if not isinstance(fn, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            continue
        logger_calls: list[_ast.Call] = []
        write_calls: list[tuple[_ast.Call, _ast.expr]] = []
        for node in _ast.walk(fn):
            if not isinstance(node, _ast.Call):
                continue
            if _g458_is_logger_call(node):
                logger_calls.append(node)
                continue
            msg = _g458_write_log_message(node)
            if msg is not None:
                write_calls.append((node, msg))
        for w_call, w_msg in write_calls:
            w_dump = _ast.dump(w_msg)
            for l_call in logger_calls:
                if any(_ast.dump(m) == w_dump for m in _g458_logger_messages(l_call)):
                    found.add((fn.name, l_call.lineno, w_call.lineno, _ast.unparse(w_msg)[:60]))
    return sorted(found, key=lambda x: (x[2], x[1]))


def test_g_458_detector_catches_variable_pair() -> None:
    """양성 대조군 — 검출기가 변수 메시지 쌍을 실제로 잡는다(공허한 초록 방지)."""
    src = (
        "async def f():\n"
        "    msg = '[x] a=1'\n"
        "    logger.warning(msg)\n"
        "    await write_log('WARNING', msg)\n"
        "async def g():\n"
        "    msg = '[y]'\n"
        "    logger.info(msg)\n"
        "    await system_logs.write_log('INFO', msg)\n"
        "async def h():\n"
        "    logger.info('%s', msg)\n"
        "    await safe_write_log('INFO', msg)\n"
        "async def ok():\n"
        "    logger.info(msg)\n"
        "    await write_log('INFO', other)\n"
    )
    names = {p[0] for p in _find_same_expr_pairs(src)}
    assert names == {"f", "g", "h"}


def test_g_458_no_same_expr_logger_write_log_pair() -> None:
    """G-458: src/ 전체 — 같은 함수 안 logger.<level>(X) 와 write_log(level, X) 쌍 0건.

    루트 `_DbLogHandler`(src/main.py)가 `src.*` 로거의 INFO 이상을 이미 system_logs 로
    옮긴다(접두 `[<logger name>] `). 같은 메시지를 write_log 로 또 쓰면 사건 하나가 두 줄이다.
    """
    all_violations: dict[str, list[tuple[str, int, int, str]]] = {}
    for py_file in _iter_py_files():
        violations = _find_same_expr_pairs(_read(py_file))
        if violations:
            all_violations[str(py_file.relative_to(_SRC_ROOT.parent))] = violations
    total = sum(len(v) for v in all_violations.values())
    detail = "\n".join(
        f"  {path}: {sites}" for path, sites in sorted(all_violations.items())
    )
    assert total == 0, (
        f"\ncycle458 G-458 위반 — 같은 메시지를 logger.* 와 write_log 로 두 번 남기는 쌍 "
        f"{total} 건 (함수, logger 줄, write_log 줄, 식):\n{detail}\n"
        f"\n한쪽만 남긴다 — 로거가 src.* 이고 INFO 이상이면 write_log 를 지운다."
    )
