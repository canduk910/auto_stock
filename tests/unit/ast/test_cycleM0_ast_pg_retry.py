"""사이클 M0 (Red) — src/db/pg.py `_with_retry` 경유 구조 AST 영구 가드.

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179/187 교훈). `_ast_helpers.py` 재사용.

`_with_retry` = execute_with_retry(사이클187) asyncpg 대체. 계획: read 헬퍼(fetch/fetchrow/
fetchval)만 경유, 쓰기(execute/executemany) 미경유 (멱등 우려 영속, G-187-A2 답습).

가드:
- G-M0-A1: read 3헬퍼(fetch/fetchrow/fetchval) 본체가 `_with_retry` 호출 ≥ 1. → Red FAIL.
- G-M0-A2: 쓰기 2헬퍼(execute/executemany) 는 `_with_retry` 미경유 (멱등 제외). → Red 시엔
  함수 미존재라 판정 불가(FAIL). Green 후 불변식 PASS.
- G-M0-A3: `_with_retry` 본체 `write_log` 호출 0건 (사이클72 이중 INSERT 차단, logger.warning
  단독). → Red FAIL (함수 미존재).

Red 유효성: 현재 `src/db/pg.py` 미존재 → read_module_source 단계 FileNotFoundError/import FAIL.
Green 후 PASS.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit.ast._ast_helpers import (
    count_function_calls_in_node,
    find_function_def,
)

pytestmark = pytest.mark.unit

_READ_HELPERS = ("fetch", "fetchrow", "fetchval")
_WRITE_HELPERS = ("execute", "executemany")


def _pg_source() -> str:
    import src.db.pg as _pg
    from tests.unit.ast._ast_helpers import read_module_source

    return read_module_source(_pg.__file__)


# ---------------------------------------------------------------------------
# G-M0-A1 — read 3헬퍼 = _with_retry 경유
# ---------------------------------------------------------------------------
def test_GM0_A1_read_helpers_use_with_retry():
    """read 3헬퍼(fetch/fetchrow/fetchval) 본체에 `_with_retry` Call ≥ 1.

    현재 pg.py 미존재 → _pg_source() FAIL (Red).
    """
    # 탐지기 self-test (false-negative 차단)
    sample = ast.parse(
        "async def fetch(sql, *a):\n"
        "    return await _with_retry(lambda: conn.fetch(sql, *a), op='fetch')\n"
    )
    f_node = next(n for n in ast.walk(sample) if getattr(n, "name", None) == "fetch")
    assert count_function_calls_in_node(f_node, "_with_retry") == 1, (
        "A1 self-test — _with_retry 탐지 실패 (탐지기 결함)."
    )

    src = _pg_source()
    missing: list[str] = []
    for name in _READ_HELPERS:
        node = find_function_def(src, name)
        assert node is not None, f"A1 — read 헬퍼 `{name}` 미발견 (구조 변경 재점검)."
        if count_function_calls_in_node(node, "_with_retry") < 1:
            missing.append(name)

    assert not missing, (
        "G-M0-A1 (Red) — read 헬퍼가 `_with_retry` 미경유 "
        "(connection 계열 예외 재시도 의무):\n  " + ", ".join(missing)
    )


# ---------------------------------------------------------------------------
# G-M0-A2 — 쓰기 2헬퍼 = _with_retry 미경유 (멱등 제외, 불변식)
# ---------------------------------------------------------------------------
def test_GM0_A2_write_helpers_not_routed_through_retry():
    """쓰기 2헬퍼(execute/executemany) 는 `_with_retry` 미경유 = 멱등 우려 제외 영구 보장.

    사이클187 G-187-A2 답습 — 쓰기 retry 는 'RemoteProtocolError 요청 도달 후 응답만 유실'
    시 중복 위험이라 금지. Green 후 불변식 PASS.
    """
    src = _pg_source()
    routed: list[str] = []
    for name in _WRITE_HELPERS:
        node = find_function_def(src, name)
        assert node is not None, f"A2 — 쓰기 헬퍼 `{name}` 미발견 (구조 변경 재점검)."
        if count_function_calls_in_node(node, "_with_retry") != 0:
            routed.append(name)

    assert not routed, (
        "G-M0-A2 — 쓰기 헬퍼가 `_with_retry` 경유 (멱등 우려, 쓰기 retry 금지):\n  "
        + ", ".join(routed)
    )


# ---------------------------------------------------------------------------
# G-M0-A3 — _with_retry 본체 write_log 호출 0건 (사이클72 이중 INSERT 차단)
# ---------------------------------------------------------------------------
def test_GM0_A3_with_retry_no_write_log_call():
    """`_with_retry` 본체에 `write_log` Call 0건 (logger.warning 단독).

    사이클72 — `_DbLogHandler` 위임 + write_log 동시 호출 = system_logs 이중 INSERT.
    _with_retry 는 재귀 차단 위해 logger.warning 만. 현재 함수 미존재 → FAIL (Red).
    """
    src = _pg_source()
    node = find_function_def(src, "_with_retry")
    assert node is not None, (
        "G-M0-A3 (Red) — `src/db/pg.py::_with_retry` 미존재 (헬퍼 신규 의무)."
    )

    write_log_calls = count_function_calls_in_node(node, "write_log")
    assert write_log_calls == 0, (
        f"G-M0-A3 — _with_retry 본체 `write_log` 호출 {write_log_calls}건 "
        "(사이클72 이중 INSERT 차단 — logger.warning 단독 의무)."
    )
