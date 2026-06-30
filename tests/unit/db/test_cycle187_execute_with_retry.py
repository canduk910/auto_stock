"""사이클 187 (2026-06-30) Red — execute_with_retry 헬퍼 단위 회귀 가드.

`src/db/supabase.py::execute_with_retry(build, *, retries=1, op="")` 신규 헬퍼:
- connection 계열 예외 (httpx.RemoteProtocolError / ConnectError / ConnectTimeout
  / ReadError) 만 `retries` 회 재시도 (각 시도 사이 asyncio.sleep(0.2)).
- 재시도 소진 시 마지막 예외 raise → 호출자 graceful except 보존.
- 비-retry 예외 (ValueError / postgrest.APIError 등) 는 즉시 전파 (재시도 0).
- `build` 는 `.execute()` 포함 무인자 callable. `asyncio.to_thread(build)` 위임.

Red 유효성: 현재 코드에 헬퍼 미존재 → H1~H6 전부 import 단계 FAIL.
Green 후 PASS.

설계 메모: `_workspace/red/cycle187_supabase_execute_retry.md` §회귀 가드 A.

테스트 격리:
- build = MagicMock(side_effect=[...]) — 1차 RemoteProtocolError → 2차 정상값.
- asyncio.sleep 은 전역 patch (AsyncMock) 로 무력화 (테스트 지연 0).
  → src.db.supabase 모듈이 Red 시점 asyncio 미import 라도 전역 asyncio.sleep 패치는 안전.
- execute_with_retry import 는 각 테스트 본체 lazy import (Red ImportError = 깔끔한 FAIL).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def no_sleep():
    """asyncio.sleep 무력화 — 재시도 backoff 실지연 0 (전역 패치, Red 안전)."""
    with patch("asyncio.sleep", new_callable=AsyncMock) as m:
        yield m


# ---------------------------------------------------------------------------
# G-187-H1 — RemoteProtocolError 1회 후 2차 정상 → 결과 반환 (build 2회). Red 핵심.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G187_H1_retry_once_then_success(no_sleep):
    """1차 RemoteProtocolError (Server disconnected) → 재시도 → 2차 정상값 반환."""
    from src.db.supabase import execute_with_retry

    sentinel = {"data": [1, 2, 3]}
    build = MagicMock(
        side_effect=[httpx.RemoteProtocolError("Server disconnected"), sentinel]
    )

    result = await execute_with_retry(build, retries=1, op="get_recent_daily")

    assert result == sentinel, "재시도 후 2차 정상값 반환 (graceful 폴백 아님)"
    assert build.call_count == 2, "1차 실패 + 2차 성공 = build 2회 호출"
    assert no_sleep.await_count == 1, "재시도 1회 사이 asyncio.sleep 1회"


# ---------------------------------------------------------------------------
# G-187-H2 — retries=1 → 2회 연속 RemoteProtocolError → 마지막 예외 raise
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G187_H2_exhausted_raises_last(no_sleep):
    """retries=1 소진 (2회 연속 실패) → 마지막 예외 raise (호출자 graceful 보존용)."""
    from src.db.supabase import execute_with_retry

    exc1 = httpx.RemoteProtocolError("disconnect 1")
    exc2 = httpx.RemoteProtocolError("disconnect 2")
    build = MagicMock(side_effect=[exc1, exc2])

    with pytest.raises(httpx.RemoteProtocolError) as ei:
        await execute_with_retry(build, retries=1, op="count_all")

    assert ei.value is exc2, "재시도 소진 시 마지막 시도의 예외를 raise"
    assert build.call_count == 2, "retries=1 → 총 2회 시도"
    assert no_sleep.await_count == 1, "재시도 사이 sleep 1회 (마지막 실패 후엔 sleep 없음)"


# ---------------------------------------------------------------------------
# G-187-H3 — ConnectError / ConnectTimeout / ReadError 도 재시도 대상
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G187_H3_other_connection_excs_retried(no_sleep):
    """RemoteProtocolError 외 connection 계열 예외 3종도 재시도."""
    from src.db.supabase import execute_with_retry

    for exc_cls in (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError):
        build = MagicMock(side_effect=[exc_cls("conn fail"), "OK"])

        result = await execute_with_retry(build, retries=1, op="x")

        assert result == "OK", f"{exc_cls.__name__} 재시도 후 성공"
        assert build.call_count == 2, f"{exc_cls.__name__} → 재시도 발생 (build 2회)"


# ---------------------------------------------------------------------------
# G-187-H4 — 비-retry 예외 (ValueError) → 즉시 raise, build 1회 (재시도 0)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G187_H4_non_retry_exc_immediate(no_sleep):
    """ValueError (비-connection 예외) → 재시도 없이 즉시 전파."""
    from src.db.supabase import execute_with_retry

    build = MagicMock(side_effect=[ValueError("bad query"), "OK"])

    with pytest.raises(ValueError):
        await execute_with_retry(build, retries=1, op="x")

    assert build.call_count == 1, "비-retry 예외 = 재시도 0 (build 1회)"
    assert no_sleep.await_count == 0, "재시도 없음 = sleep 0"


# ---------------------------------------------------------------------------
# G-187-H5 — 정상 1회 → 결과 반환, build 1회 (재시도 0, sleep 0)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G187_H5_success_no_retry(no_sleep):
    """1차 정상 → 즉시 반환 (재시도/sleep 0)."""
    from src.db.supabase import execute_with_retry

    sentinel = {"ok": True}
    build = MagicMock(return_value=sentinel)

    result = await execute_with_retry(build, retries=1, op="x")

    assert result == sentinel
    assert build.call_count == 1, "정상 = build 1회 (재시도 0)"
    assert no_sleep.await_count == 0, "정상 = sleep 0"


# ---------------------------------------------------------------------------
# G-187-H6 — retries=0 → 재시도 없이 1회 시도 후 raise
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G187_H6_retries_zero_no_retry(no_sleep):
    """retries=0 → 1회 시도 (재시도 0). connection 예외도 즉시 raise."""
    from src.db.supabase import execute_with_retry

    build = MagicMock(side_effect=[httpx.RemoteProtocolError("disconnect")])

    with pytest.raises(httpx.RemoteProtocolError):
        await execute_with_retry(build, retries=0, op="x")

    assert build.call_count == 1, "retries=0 → 총 1회 시도"
    assert no_sleep.await_count == 0, "retries=0 → sleep 0"
