"""사이클 189 (2026-07-02) Red — kis_quote_accounts + system_config read retry AST 가드.

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179/187 false-positive 교훈).
`tests/unit/ast/_ast_helpers.py` (사이클 136~139) FunctionDef 노드 + 노드 서브트리
Call 카운트 헬퍼 재사용. 사이클 187 A1/A2 패턴 100% 답습.

가드 (설계 메모 영역 A):
- A-1: kis_quote_accounts read 4함수 = `execute_with_retry` 경유 + 직접 `to_thread` 0건.
  → 현재 FAIL (Red).
- A-2: system_config read 9함수 = 동일 (UNUSED 포함). → 현재 FAIL (Red).
- A-3: 양 모듈 쓰기 계열 = `to_thread` 직접 유지 + `execute_with_retry` 0건 (불변식).
  → 현재 PASS (187 A2 패턴 = 멱등 SELECT 전용 제외 영구 보장).
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

_KQA_READ_FUNCS = (
    "list_accounts",
    "get_account",
    "get_account_by_label",
    "get_credentials_for_token_manager",
)
_KQA_WRITE_FUNCS = ("insert_account", "update_account", "delete_account")

_SC_READ_FUNCS = (
    "get_cash_usage_ratio",
    "get_auto_regime_adjust",
    "_get_bool_or_none",
    "get_buy_block_mode",
    "_get_float_or_default",
    "_get_bool_or_default",
    "_get_int_or_default",
    "_get_str_or_default_UNUSED",
    "_get_string_or_none",
)
_SC_WRITE_FUNCS = (
    "set_cash_usage_ratio",
    "set_auto_regime_adjust",
    "_set_bool",
    "_set_float",
    "_set_int",
    "_set_string",
    "set_buy_block_mode",
)


def _kqa_source() -> str:
    import src.db.kis_quote_accounts as _kqa

    return read_module_source(_kqa.__file__)


def _sc_source() -> str:
    import src.db.system_config as _sc

    return read_module_source(_sc.__file__)


def _assert_read_funcs_routed(src: str, funcs: tuple[str, ...], label: str) -> None:
    """read 함수 전수 = execute_with_retry Call ≥ 1 + 직접 to_thread Call 0."""
    missing_retry: list[str] = []
    leftover_to_thread: list[str] = []

    for name in funcs:
        node = find_function_def(src, name)
        assert node is not None, f"{label} — read 함수 `{name}` 미발견 (구조 변경 재점검)."

        if count_function_calls_in_node(node, "execute_with_retry") < 1:
            missing_retry.append(name)
        if count_function_calls_in_node(node, "to_thread") != 0:
            leftover_to_thread.append(name)

    assert not missing_retry, (
        f"{label} (Red) — read 함수가 `execute_with_retry` 미경유. "
        "connection 계열 예외 1회 재시도 의무:\n  " + ", ".join(missing_retry)
    )
    assert not leftover_to_thread, (
        f"{label} (Red) — read 함수에 직접 `asyncio.to_thread` 잔존 "
        "(execute_with_retry 가 to_thread 위임 = 단일 경로 의무):\n  "
        + ", ".join(leftover_to_thread)
    )


# ---------------------------------------------------------------------------
# A-1 — kis_quote_accounts read 4함수 = execute_with_retry 경유 + to_thread 0
# ---------------------------------------------------------------------------
def test_A1_kqa_read_funcs_use_execute_with_retry():
    """kis_quote_accounts read 4함수 본체 execute_with_retry ≥ 1 + 직접 to_thread 0.

    현재 (retry 미존재) = read 함수가 `asyncio.to_thread(_query)` 직접 →
    execute_with_retry 0건 → FAIL (Red). Green 전환 후 PASS.
    """
    # 탐지기 self-test (false-negative 차단, 사이클 167/184/187 교훈)
    sample = ast.parse(
        "async def f():\n"
        "    return await execute_with_retry(_query, op='f')\n"
        "async def g():\n"
        "    return await asyncio.to_thread(_query)\n"
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

    _assert_read_funcs_routed(_kqa_source(), _KQA_READ_FUNCS, "G-189-A1")


# ---------------------------------------------------------------------------
# A-2 — system_config read 9함수 = execute_with_retry 경유 + to_thread 0
# ---------------------------------------------------------------------------
def test_A2_sc_read_funcs_use_execute_with_retry():
    """system_config read 9함수 (UNUSED 포함) 본체 execute_with_retry ≥ 1 + to_thread 0.

    현재 (retry 미존재) = read 함수 `asyncio.to_thread(_query)` 직접 → FAIL (Red).
    """
    _assert_read_funcs_routed(_sc_source(), _SC_READ_FUNCS, "G-189-A2")


# ---------------------------------------------------------------------------
# A-3 — 양 모듈 쓰기 계열 = to_thread 직접 유지 + execute_with_retry 0건 (불변식)
# ---------------------------------------------------------------------------
def test_A3_write_funcs_not_routed_through_retry():
    """쓰기 함수 = `execute_with_retry` 미경유 + `asyncio.to_thread` 직접 유지.

    187 A2 패턴 = 멱등 SELECT 전용 제외 영구 보장 (쓰기 retry 금지, 중복 위험).
    현재도 PASS (불변식) — Green 후에도 쓰기 경로 불변 유지 영구 가드.
    """
    routed: list[str] = []
    missing_to_thread: list[str] = []

    for src, funcs, label in (
        (_kqa_source(), _KQA_WRITE_FUNCS, "kis_quote_accounts"),
        (_sc_source(), _SC_WRITE_FUNCS, "system_config"),
    ):
        for name in funcs:
            node = find_function_def(src, name)
            assert node is not None, f"A3 — 쓰기 함수 `{label}.{name}` 미발견 (구조 변경 재점검)."

            if count_function_calls_in_node(node, "execute_with_retry") != 0:
                routed.append(f"{label}.{name}")
            if count_function_calls_in_node(node, "to_thread") < 1:
                missing_to_thread.append(f"{label}.{name}")

    assert not routed, (
        "G-189-A3 — 쓰기 함수가 `execute_with_retry` 경유 (멱등 우려, 쓰기 retry 금지):\n  "
        + ", ".join(routed)
    )
    assert not missing_to_thread, (
        "G-189-A3 — 쓰기 함수가 직접 `asyncio.to_thread` 미사용 (직접 위임 유지 의무):\n  "
        + ", ".join(missing_to_thread)
    )
