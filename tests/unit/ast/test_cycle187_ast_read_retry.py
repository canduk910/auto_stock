"""사이클 187 (2026-06-30) Red — execute_with_retry 경유 구조 AST 영구 가드.

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179 false-positive 교훈:
주석/별칭/공백 def 가 정규식 스캔을 오염). `tests/unit/ast/_ast_helpers.py`
(사이클 136~139) FunctionDef 노드 + 노드 서브트리 Call 카운트 헬퍼 재사용.

가드 (설계 메모 §회귀 가드 C):
- G-187-A1: read 4함수 (get_recent_daily / count_all / count_by_ticker / max_bas_dd)
  본체가 `execute_with_retry` 호출 + 직접 `asyncio.to_thread` 잔존 0건. → 현재 FAIL.
- G-187-A2: 쓰기 3함수 (upsert_daily / upsert_batch / purge_old_rows) 는
  `execute_with_retry` 미경유 (`asyncio.to_thread` 직접 유지) = Q2 멱등 제외 영구 보장.
  → 현재 PASS (불변식).
- G-187-A3: `execute_with_retry` 본체 `write_log` 호출 0건 (사이클 72 이중 INSERT 차단).
  → 현재 FAIL (헬퍼 미존재).
"""

from __future__ import annotations

import ast

import pytest

from tests.unit.ast._ast_helpers import (
    count_function_calls_in_node,
    find_function_def,
    read_module_source,
)

pytestmark = pytest.mark.unit

_READ_FUNCS = ("get_recent_daily", "count_all", "count_by_ticker", "max_bas_dd")
_WRITE_FUNCS = ("upsert_daily", "upsert_batch", "purge_old_rows")


def _smd_source() -> str:
    import src.db.stock_master_daily as _smd

    return read_module_source(_smd.__file__)


def _supabase_source() -> str:
    import src.db.supabase as _sb

    return read_module_source(_sb.__file__)


# ---------------------------------------------------------------------------
# G-187-A1 — read 4함수 = execute_with_retry 경유 + 직접 to_thread 잔존 0
# ---------------------------------------------------------------------------
def test_G187_A1_read_funcs_use_execute_with_retry():
    """read 4함수 본체에 `execute_with_retry` Call ≥ 1 + 직접 `asyncio.to_thread` Call 0.

    현재 (retry 미존재) = read 함수가 `asyncio.to_thread(lambda: ...execute())` 직접 →
    execute_with_retry 0건 → FAIL (Red). Green 전환 후 PASS.
    """
    # 탐지기 self-test (false-negative 차단, 사이클 167/184 교훈)
    sample = ast.parse(
        "async def f():\n"
        "    return await execute_with_retry(lambda: x.execute(), op='f')\n"
        "async def g():\n"
        "    return await asyncio.to_thread(lambda: y.execute())\n"
    )
    f_node = next(n for n in ast.walk(sample) if getattr(n, "name", None) == "f")
    g_node = next(n for n in ast.walk(sample) if getattr(n, "name", None) == "g")
    assert count_function_calls_in_node(f_node, "execute_with_retry") == 1, (
        "A1 self-test — execute_with_retry 탐지 실패 (탐지기 결함)."
    )
    assert count_function_calls_in_node(g_node, "to_thread") == 1, (
        "A1 self-test — asyncio.to_thread 탐지 실패 (탐지기 결함)."
    )
    assert count_function_calls_in_node(f_node, "to_thread") == 0

    src = _smd_source()
    missing_retry: list[str] = []
    leftover_to_thread: list[str] = []

    for name in _READ_FUNCS:
        node = find_function_def(src, name)
        assert node is not None, f"A1 — read 함수 `{name}` 미발견 (구조 변경 재점검)."

        if count_function_calls_in_node(node, "execute_with_retry") < 1:
            missing_retry.append(name)
        if count_function_calls_in_node(node, "to_thread") != 0:
            leftover_to_thread.append(name)

    assert not missing_retry, (
        "G-187-A1 (Red) — read 함수가 `execute_with_retry` 미경유. "
        "connection 계열 예외 1회 재시도 의무:\n  " + ", ".join(missing_retry)
    )
    assert not leftover_to_thread, (
        "G-187-A1 (Red) — read 함수에 직접 `asyncio.to_thread` 잔존 "
        "(execute_with_retry 가 to_thread 위임 = 단일 경로 의무):\n  "
        + ", ".join(leftover_to_thread)
    )


# ---------------------------------------------------------------------------
# G-187-A2 — 쓰기 3함수 = execute_with_retry 미경유 + to_thread 직접 유지 (불변식)
# ---------------------------------------------------------------------------
def test_G187_A2_write_funcs_not_routed_through_retry():
    """쓰기 3함수 (upsert_daily/upsert_batch/purge_old_rows) 는 `execute_with_retry`
    미경유 + `asyncio.to_thread` 직접 유지 = Q2 멱등 SELECT 전용 제외 영구 보장.

    현재도 PASS (불변식) — Green 후에도 쓰기 경로 불변 유지 영구 가드.
    """
    src = _smd_source()
    routed: list[str] = []
    missing_to_thread: list[str] = []

    for name in _WRITE_FUNCS:
        node = find_function_def(src, name)
        assert node is not None, f"A2 — 쓰기 함수 `{name}` 미발견 (구조 변경 재점검)."

        if count_function_calls_in_node(node, "execute_with_retry") != 0:
            routed.append(name)
        if count_function_calls_in_node(node, "to_thread") < 1:
            missing_to_thread.append(name)

    assert not routed, (
        "G-187-A2 — 쓰기 함수가 `execute_with_retry` 경유 (멱등 우려, 쓰기 retry 금지):\n  "
        + ", ".join(routed)
    )
    assert not missing_to_thread, (
        "G-187-A2 — 쓰기 함수가 직접 `asyncio.to_thread` 미사용 (직접 위임 유지 의무):\n  "
        + ", ".join(missing_to_thread)
    )


# ---------------------------------------------------------------------------
# G-187-A3 — execute_with_retry 본체 write_log 호출 0건 (사이클 72 이중 INSERT 차단)
# ---------------------------------------------------------------------------
def test_G187_A3_helper_no_write_log_call():
    """`execute_with_retry` 본체에 `write_log` Call 0건 (logger.warning 단독).

    사이클 72 — `_DbLogHandler` 위임 + write_log 동시 호출 = system_logs 이중 INSERT.
    헬퍼는 logger.warning 만 사용해야 함. 현재 헬퍼 미존재 → FunctionDef None → FAIL (Red).
    """
    src = _supabase_source()
    node = find_function_def(src, "execute_with_retry")
    assert node is not None, (
        "G-187-A3 (Red) — `src/db/supabase.py::execute_with_retry` 미존재 (헬퍼 신규 의무)."
    )

    write_log_calls = count_function_calls_in_node(node, "write_log")
    assert write_log_calls == 0, (
        f"G-187-A3 — execute_with_retry 본체 `write_log` 호출 {write_log_calls}건 "
        "(사이클 72 이중 INSERT 차단 — logger.warning 단독 의무)."
    )

    # 헬퍼가 connection 계열 재시도 래퍼임을 보강 검증 — to_thread 위임 존재.
    assert count_function_calls_in_node(node, "to_thread") >= 1, (
        "G-187-A3 — execute_with_retry 가 `asyncio.to_thread` 위임 미사용 "
        "(동기 Supabase 쿼리 thread pool 위임 의무)."
    )
