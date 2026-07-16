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
@pytest.mark.xfail(
    reason=(
        "사이클 M3a (2026-07-16) 의미 전환 — kis_quote_accounts 가 supabase-py에서 "
        "src.db.pg(asyncpg) 로 전환. 사이클 189 정책(read retry)은 pg.fetch/"
        "pg.fetchrow 자체가 내부적으로 pg._with_retry 를 경유하는 형태로 계승되어 "
        "supabase execute_with_retry AST 패턴이 소멸(대체 = "
        "tests/unit/db/test_cycleM3a_kis_quote_accounts_pg.py). "
        "M1/M2a 선례(사이클 189→xfail 은퇴 패턴) 답습."
    ),
    strict=False,
)
def test_A1_kqa_read_funcs_use_execute_with_retry():
    """kis_quote_accounts read 4함수 본체 execute_with_retry ≥ 1 + 직접 to_thread 0.

    사이클 M3a 전환 후 — pg.fetch/pg.fetchrow 직접 호출(내부 _with_retry 자동
    경유)로 바뀌어 supabase execute_with_retry Call 이 0건 → xfail (의미 전환).
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
@pytest.mark.xfail(
    reason=(
        "사이클 M2a (2026-07-16) 의미 전환 — system_config 가 supabase-py에서 "
        "src.db.pg(asyncpg) 로 전환. 사이클 189 정책(read retry)은 pg.fetch 자체가 "
        "내부적으로 pg._with_retry 를 경유하는 형태로 계승되어 supabase "
        "execute_with_retry AST 패턴이 소멸(대체 = "
        "tests/unit/db/test_cycleM2a_system_config_pg.py "
        "test_get_cash_usage_ratio_uses_with_retry 등). M1 선례(사이클 189→M1 "
        "xfail 은퇴 패턴) 답습."
    ),
    strict=False,
)
def test_A2_sc_read_funcs_use_execute_with_retry():
    """system_config read 9함수 (UNUSED 포함) 본체 execute_with_retry ≥ 1 + to_thread 0.

    사이클 M2a 전환 후 — pg.fetch 직접 호출(내부 _with_retry 자동 경유)로
    바뀌어 supabase execute_with_retry Call 이 0건 → xfail (의미 전환).
    """
    _assert_read_funcs_routed(_sc_source(), _SC_READ_FUNCS, "G-189-A2")


# ---------------------------------------------------------------------------
# A-3 — 양 모듈 쓰기 계열 = to_thread 직접 유지 + execute_with_retry 0건 (불변식)
# ---------------------------------------------------------------------------
def test_A3_write_funcs_not_routed_through_retry():
    """쓰기 함수 = `execute_with_retry` 미경유 (불변식, kis_quote_accounts 한정).

    187 A2 패턴 = 멱등 SELECT 전용 제외 영구 보장 (쓰기 retry 금지, 중복 위험).
    사이클 M2a (2026-07-16) 의미 전환 — system_config 는 supabase-py → src.db.pg
    전환으로 쓰기가 `asyncio.to_thread` 대신 `pg.execute` 직접 호출로 바뀌어
    "직접 to_thread 유지" 불변식이 무의미해짐(대체 계약 =
    test_cycleM2a_system_config_pg.py::test_set_does_not_use_with_retry).
    사이클 M3a (2026-07-16) — kis_quote_accounts 도 동일 전환(대체 계약 =
    test_cycleM3a_kis_quote_accounts_pg.py::test_insert_does_not_use_with_retry).
    "직접 to_thread 유지" 불변식은 두 모듈 모두 무의미 — 본 테스트는 은퇴 대상.
    execute_with_retry 미경유(routed 검사)는 test_A3b 계열이 계승.
    """
    routed: list[str] = []

    for src, funcs, label in (
        (_kqa_source(), _KQA_WRITE_FUNCS, "kis_quote_accounts"),
    ):
        for name in funcs:
            node = find_function_def(src, name)
            assert node is not None, f"A3 — 쓰기 함수 `{label}.{name}` 미발견 (구조 변경 재점검)."

            if count_function_calls_in_node(node, "execute_with_retry") != 0:
                routed.append(f"{label}.{name}")

    assert not routed, (
        "G-189-A3 — 쓰기 함수가 `execute_with_retry` 경유 (멱등 우려, 쓰기 retry 금지):\n  "
        + ", ".join(routed)
    )


def test_A3c_kqa_write_funcs_use_pg_execute_not_retry():
    """kis_quote_accounts 쓰기 함수 (M3a 전환 후) — pg 직접 호출 + execute_with_retry 미경유.

    사이클 189 정책(쓰기 retry 금지)의 M3a 계승판. supabase to_thread 대신
    pg.execute/pg.fetchrow 직접 호출로 동일 정책(멱등 우려로 재시도 없음) 유지.
    """
    routed: list[str] = []

    for name in _KQA_WRITE_FUNCS:
        node = find_function_def(_kqa_source(), name)
        assert node is not None, f"A3c — 쓰기 함수 `kis_quote_accounts.{name}` 미발견."

        if count_function_calls_in_node(node, "execute_with_retry") != 0:
            routed.append(name)

    assert not routed, (
        "G-189-A3c — kis_quote_accounts 쓰기 함수가 execute_with_retry 경유 (정책 위반):\n  "
        + ", ".join(routed)
    )


def test_A3b_sc_write_funcs_use_pg_execute_not_retry():
    """system_config 쓰기 함수 (M2a 전환 후) — pg.execute 직접 + execute_with_retry 미경유.

    사이클 189 정책(쓰기 retry 금지)의 M2a 계승판. supabase to_thread 대신
    pg.execute 직접 호출로 동일 정책(멱등 우려로 재시도 없음) 유지.
    """
    routed: list[str] = []
    missing_pg_execute: list[str] = []

    for name in _SC_WRITE_FUNCS:
        node = find_function_def(_sc_source(), name)
        assert node is not None, f"A3b — 쓰기 함수 `system_config.{name}` 미발견."

        if count_function_calls_in_node(node, "execute_with_retry") != 0:
            routed.append(name)
        # 직접 또는 _upsert_value 경유 pg.execute 호출(간접 위임도 정책 계승 인정)
        # → 단순화: 본 함수가 execute_with_retry 를 쓰지 않는 것만 확인(양성 검증은
        # test_cycleM2a_system_config_pg.py::test_set_does_not_use_with_retry 담당).

    assert not routed, (
        "G-189-A3b — system_config 쓰기 함수가 execute_with_retry 경유 (정책 위반):\n  "
        + ", ".join(routed)
    )
