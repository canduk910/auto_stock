"""사이클 76 G-AST1/G-AST2/G-AST3 — AST 영구 가드: api retry helper 의무 사용.

G-AST1: `src/api/base.py::_request` 본문에 `_record_request_5xx_for_dedupe` 헬퍼
        경유 *없이* 직접 `logger.warning("HTTP %s")` 호출 0건 (Red FAIL → Green PASS).
G-AST2: `src/api/base.py::_request_via_quote_pool` 본문에 `_record_5xx_for_dedupe`
        헬퍼 호출 사이트 ≥ 1건 영속 (사이클 18 PASS 영속).
G-AST3: `_request` + `_request_via_quote_pool` 본문에 `[api_retry_recovered]` 직접
        write_log 호출 0건 — collector (`_record_api_recovered` /
        `_record_quote_recovered`) 경유 의무 (Red FAIL → Green PASS).

영구 가드 — 미래 신규 사이트 silent 결함 영구 차단.
사이클 74 G-7/G-8 AST 패턴 100% 답습 (AST 기반 multi-line 호환).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit


_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
_BASE_PY = _SRC_ROOT / "api" / "base.py"


def _find_logger_warning_with_msg_prefix(
    py_path: Path, func_name: str, msg_prefix: str
) -> list[tuple[int, str]]:
    """함수 본문에서 첫 인자가 ``msg_prefix`` 로 시작하는 ``logger.warning(...)``
    호출 사이트 추출 — (line_no, line_text)."""
    source = read_module_source(py_path)
    lines = source.splitlines()
    node = find_function_def(source, func_name)
    if node is None:
        return []
    violations: list[tuple[int, str]] = []
    for sub in ast.walk(node):
        if not (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "warning"
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "logger"
        ):
            continue
        if not sub.args:
            continue
        first = sub.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        if not first.value.startswith(msg_prefix):
            continue
        ln = sub.lineno
        violations.append((ln, lines[ln - 1].strip()))
    return violations


def _find_helper_call_sites(
    py_path: Path, func_name: str, helper_name: str
) -> list[int]:
    """함수 본문에서 ``helper_name(...)`` 또는 ``await helper_name(...)`` 호출
    사이트 line 추출."""
    source = read_module_source(py_path)
    node = find_function_def(source, func_name)
    if node is None:
        return []
    sites: list[int] = []
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == helper_name
        ):
            sites.append(sub.lineno)
    return sites


def _find_write_log_with_msg_prefix_in_function(
    py_path: Path, func_name: str, msg_prefix: str
) -> list[tuple[int, str]]:
    """함수 본문에서 ``write_log(...)`` 호출 중 메시지 f-string/문자열에
    ``msg_prefix`` 포함하는 사이트 추출.

    매칭 대상:
    - ``await _system_logs.write_log("INFO", "[prefix] ...")``
    - ``await _system_logs.write_log("INFO", f"[prefix] ...")``
    - 메시지를 변수에 저장 후 write_log 호출: ``_log_msg = f"[prefix] ..."``
    """
    source = read_module_source(py_path)
    lines = source.splitlines()
    node = find_function_def(source, func_name)
    if node is None:
        return []
    violations: list[tuple[int, str]] = []

    # 1) f-string / 문자열 리터럴이 직접 write_log 인자
    for sub in ast.walk(node):
        if not (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "write_log"
        ):
            continue
        for arg in sub.args:
            msg = _extract_string_literal_or_fstring(arg)
            if msg is not None and msg_prefix in msg:
                ln = sub.lineno
                violations.append((ln, lines[ln - 1].strip()))
                break

    # 2) 변수 할당 패턴: `_log_msg = f"[prefix] ..."` 후 `write_log(_, _log_msg)`
    #    AST 로 함수 본문 내 Assign 노드의 RHS f-string/문자열에 prefix 포함된 경우
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Assign):
            continue
        msg = _extract_string_literal_or_fstring(sub.value)
        if msg is None or msg_prefix not in msg:
            continue
        # 같은 함수 본문에 write_log 호출이 한 번이라도 있어야 의미 있음
        has_write_log = any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and c.func.attr == "write_log"
            for c in ast.walk(node)
        )
        if has_write_log:
            ln = sub.lineno
            violations.append((ln, lines[ln - 1].strip()))

    return violations


def _extract_string_literal_or_fstring(arg: ast.expr) -> str | None:
    """ast.expr 노드에서 문자열 리터럴 / f-string 의 값 부분 추출 (대략)."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr):
        parts: list[str] = []
        for v in arg.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("{}")  # FormattedValue placeholder
        return "".join(parts)
    return None


# ===========================================================================
# G-AST1: `_request` 본문 `logger.warning("HTTP %s")` 직접 호출 0건
#         (사이클 76 옵션 E — dedupe 헬퍼 경유 의무)
# ===========================================================================
def test_g_ast1_request_no_direct_logger_warning_http():
    """G-AST1: `_request` 본문 첫 인자가 `"HTTP "` 로 시작하는 `logger.warning(...)`
    호출 0건 — `_record_request_5xx_for_dedupe` 헬퍼 should_emit 분기 경유 의무.

    사이클 76 옵션 E — 사이클 18 dedupe 패턴 답습. 메인 5xx 폭주 시 WARNING 1행 +
    카운트 누적 → 사이클 18 풀 영역과 동일 효과.
    """
    violations = _find_logger_warning_with_msg_prefix(
        _BASE_PY, "_request", "HTTP "
    )
    assert len(violations) == 0, (
        f"\n사이클 76 G-AST1 위반 — `_request` 본문 "
        f"`logger.warning(\"HTTP ...\")` 직접 호출 {len(violations)} 건:\n"
        + "\n".join(f"  L{ln}: {txt}" for ln, txt in violations)
        + "\n\n시정: 사이클 76 옵션 E (사이클 18 답습) — `_record_request_5xx_for_dedupe(path, status)` "
        "헬퍼 호출 + should_emit True 시에만 logger.warning. 5xx 폭주 시 1행 + 카운트 누적."
    )


# ===========================================================================
# G-AST2: `_request_via_quote_pool` 본문 `_record_5xx_for_dedupe` 호출 영속
#         (사이클 18 영속 영역 — 사이클 76 변경 0)
# ===========================================================================
def test_g_ast2_request_via_quote_pool_dedupe_helper_call_preserved():
    """G-AST2: `_request_via_quote_pool` 본문에 `_record_5xx_for_dedupe(...)` 호출
    사이트 ≥ 1건 영속 — 사이클 18 dedupe 영역 침범 금지 (사이클 76 변경 0).

    사이클 76 의 메인 `_request` dedupe 도입이 풀 영역 헬퍼 호출 사이트를 제거하지
    못하도록 영구 차단.
    """
    sites = _find_helper_call_sites(
        _BASE_PY, "_request_via_quote_pool", "_record_5xx_for_dedupe"
    )
    assert len(sites) >= 1, (
        f"\n사이클 76 G-AST2 위반 — `_request_via_quote_pool` 본문에 "
        f"`_record_5xx_for_dedupe(...)` 호출 부재 (사이클 18 영속 영역 침범):\n"
        f"  - 사이클 18 PR (2026-05-19) dedupe 헬퍼 호출 의무\n"
        f"  - 사이클 76 메인 `_request` dedupe 도입과 별개 — 영속 보존\n"
        f"  - 시정: `should_emit_warning = await _record_5xx_for_dedupe(path, "
        f"actual_label, status)` 사이트 복구"
    )


# ===========================================================================
# G-AST3: `_request` + `_request_via_quote_pool` 본문 `[api_retry_recovered]`
#         직접 write_log 호출 0건 — collector 경유 의무
# ===========================================================================
def test_g_ast3_request_no_direct_api_retry_recovered_write_log():
    """G-AST3: `_request` + `_request_via_quote_pool` 본문에서 직접
    `[api_retry_recovered]` write_log 0건 — collector 경유 의무.

    사이클 76 의제 #2 옵션 E — 5분 윈도우 누적 + `[api_retry_recovered_summary]`
    1행. 메인은 `_record_api_recovered`, 풀은 `_record_quote_recovered` 헬퍼 경유.
    `[api_retry_recovered_summary]` prefix 는 collector flush 단독 — 허용.
    """
    main_violations = _find_write_log_with_msg_prefix_in_function(
        _BASE_PY, "_request", "[api_retry_recovered]"
    )
    quote_violations = _find_write_log_with_msg_prefix_in_function(
        _BASE_PY, "_request_via_quote_pool", "[api_retry_recovered]"
    )

    # Summary prefix 가 잘못 매칭되지 않도록 필터 (prefix 정확 매칭)
    def _strict(violations: list[tuple[int, str]]) -> list[tuple[int, str]]:
        # `[api_retry_recovered_summary]` 는 collector flush 단독 → 허용.
        # 본 검출 함수는 prefix 매칭이라 summary 도 매칭 가능 → 라인 텍스트로 제외.
        return [
            (ln, txt) for ln, txt in violations
            if "[api_retry_recovered_summary]" not in txt
        ]

    main_strict = _strict(main_violations)
    quote_strict = _strict(quote_violations)

    total = len(main_strict) + len(quote_strict)
    assert total == 0, (
        f"\n사이클 76 G-AST3 위반 — `_request` 본문 `{len(main_strict)}` 건 + "
        f"`_request_via_quote_pool` 본문 `{len(quote_strict)}` 건 = "
        f"`[api_retry_recovered]` 직접 write_log 사이트:\n"
        + "\n".join(
            f"  [_request] L{ln}: {txt}" for ln, txt in main_strict
        )
        + ("\n" if main_strict and quote_strict else "")
        + "\n".join(
            f"  [_request_via_quote_pool] L{ln}: {txt}"
            for ln, txt in quote_strict
        )
        + "\n\n시정: 사이클 76 옵션 E — collector 경유 의무.\n"
        "  - 메인 경유: `_record_api_recovered(path)` (5분 누적)\n"
        "  - 풀 경유: `_record_quote_recovered(path)` (5분 누적, Q4 분리)\n"
        "  - 5분 주기 task 가 `_flush_api_recovered_collector()` / "
        "`_flush_quote_recovered_collector()` 호출 → `[api_retry_recovered_summary]` 1행"
    )
