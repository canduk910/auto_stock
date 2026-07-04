"""사이클 192 (2026-07-04) — stock_master_daily purge 루프 배치 AST 영구 가드.

P-2: `purge_old_rows` 본체에서 단일 bulk DELETE 패턴 영구 폐기 검증.
  - 무인자 `delete()` 직후 `.lt(` 직결 (bulk 삭제) 잔존 0건.
  - `returning="minimal"` 키워드 존재 (응답 비대 근본 차단).
  - `.eq("bas_dd"` 날짜 슬라이스 DELETE 필터 존재.
  - `PURGE_MAX_DATE_ITERATIONS` 모듈 상수 존재.

P-7: `purge_old_rows` 가 `execute_with_retry` 미경유 영속 (G-187-A2 = 쓰기 함수).

AST 헬퍼 `tests/unit/ast/_ast_helpers.py` 재사용.
Red 상태 (현재 bulk DELETE 코드): P-2 전부 FAIL / P-7 = 불변식 PASS.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import (
    count_function_calls_in_node,
    find_constant_value,
    find_function_def,
    read_module_source,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DAILY_PY = _REPO_ROOT / "src" / "db" / "stock_master_daily.py"


def _purge_source() -> str:
    """purge_old_rows 함수 정의(중첩 헬퍼 포함) 를 unparse 한 정규화 문자열."""
    source = read_module_source(_DAILY_PY)
    node = find_function_def(source, "purge_old_rows")
    assert node is not None, "purge_old_rows 함수 정의 영구 영속 의무"
    return ast.unparse(node)


def _normalize(text: str) -> str:
    return text.replace(" ", "").replace("\n", "")


# =============================================================================
# P-2 (HIGH) — bulk DELETE 패턴 폐기 + returning minimal + eq(bas_dd) + 상수
# =============================================================================


class TestP2NoBulkDeleteLt:
    def test_p2a_no_bulk_delete_lt_pattern(self) -> None:
        """무인자 `delete().lt(` 직결 bulk 삭제 패턴 잔존 0건."""
        normalized = _normalize(_purge_source())
        assert ".delete().lt(" not in normalized, \
            "bulk `delete().lt(` 패턴 영구 폐기 의무 (응답 비대 근본 원인)"

    def test_p2b_returning_minimal_present(self) -> None:
        """DELETE 가 returning='minimal' 로 생성 (응답 비대 차단)."""
        unparsed = _purge_source()
        assert re.search(r"returning\s*=\s*['\"]minimal['\"]", unparsed) is not None, \
            "returning='minimal' 키워드 영구 영속 의무"

    def test_p2c_eq_bas_dd_present(self) -> None:
        """날짜 슬라이스 DELETE = `.eq('bas_dd', ...)` 필터 존재."""
        unparsed = _purge_source()
        assert re.search(r"\.eq\(\s*['\"]bas_dd['\"]", unparsed) is not None, \
            ".eq('bas_dd', oldest) 날짜 슬라이스 DELETE 영구 영속 의무"

    def test_p2d_max_date_iterations_constant(self) -> None:
        """PURGE_MAX_DATE_ITERATIONS 모듈 상수 존재 + 양수 int."""
        source = read_module_source(_DAILY_PY)
        value = find_constant_value(source, "PURGE_MAX_DATE_ITERATIONS")
        assert value is not None, "PURGE_MAX_DATE_ITERATIONS 상수 영구 영속 의무"
        assert isinstance(value, int) and value > 0, \
            "PURGE_MAX_DATE_ITERATIONS 양수 int 의무 (런어웨이 가드)"

    def test_p2e_loop_over_max_iterations(self) -> None:
        """purge 본체가 PURGE_MAX_DATE_ITERATIONS 로 루프 (range 참조)."""
        normalized = _normalize(_purge_source())
        assert "range(PURGE_MAX_DATE_ITERATIONS)" in normalized, \
            "for _ in range(PURGE_MAX_DATE_ITERATIONS) 루프 영구 영속 의무"


# =============================================================================
# P-7 — execute_with_retry 미경유 영속 (쓰기 함수, G-187-A2 불변식)
# =============================================================================


class TestP7NoRetryWrapper:
    def test_p7_purge_not_via_execute_with_retry(self) -> None:
        """purge_old_rows 는 execute_with_retry 미경유 (쓰기 = 멱등 우려 제외)."""
        source = read_module_source(_DAILY_PY)
        node = find_function_def(source, "purge_old_rows")
        assert node is not None, "purge_old_rows 함수 정의 영구 영속 의무"
        calls = count_function_calls_in_node(node, "execute_with_retry")
        assert calls == 0, \
            "purge_old_rows execute_with_retry 미경유 영속 의무 (G-187-A2 쓰기 불변식)"

    def test_p7b_uses_to_thread(self) -> None:
        """purge_old_rows 는 asyncio.to_thread 위임 유지 (동기 SDK 정책)."""
        source = read_module_source(_DAILY_PY)
        node = find_function_def(source, "purge_old_rows")
        assert node is not None, "purge_old_rows 함수 정의 영구 영속 의무"
        calls = count_function_calls_in_node(node, "to_thread")
        assert calls >= 1, "asyncio.to_thread 위임 영속 의무 (동기 SDK)"
