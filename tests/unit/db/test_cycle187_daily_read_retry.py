"""사이클 187 (2026-06-30) Red — stock_master_daily read 4함수 retry 경유 통합 가드.

read 4함수 (get_recent_daily / count_all / count_by_ticker / max_bas_dd) 가
`execute_with_retry` 경유 → connection 계열 예외 1회 재시도 후 성공 시 정상값,
2회 실패 시 기존 graceful 폴백 (`[]` / `0` / `None`) 보존.

운영 배경: httpx.RemoteProtocolError "Server disconnected" 90건/24h (전부 read 경로).
16:00 일봉 task 수백 종목 순회 시 httpx pool stale keep-alive 첫 요청 끊김.
현행 단발 to_thread → 1회 실패 = graceful 빈값 → KIS 폴백 (사이클 173 목적 부분 무력화).

Red 유효성 (현재 코드 = retry 미존재):
- I1 (get_recent_daily retry-success → rows): FAIL — 1회 실패 시 graceful [] 반환.
- I2 (get_recent_daily 2회 실패 → graceful []): PASS (불변식, 현재도 동일).
- I3 (count_all retry-success → count): FAIL — 1회 실패 시 0 반환.
- I4 (max_bas_dd retry-success → date): FAIL — 1회 실패 시 None 반환.

설계 메모: `_workspace/red/cycle187_supabase_execute_retry.md` §회귀 가드 B.

테스트 격리 (사이클 163/172/173 stock_master_daily mock 패턴 답습):
- `patch.object(smd, "supabase", mock)` — 체인 mock `.execute()` side_effect 로 구동.
- asyncio.sleep 전역 patch (autouse) — 재시도 backoff 실지연 0.
- 날짜 = 고정 2024 (today 의존 0, max_bas_dd 는 today 비교 없음).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import src.db.stock_master_daily as smd

# 사이클 M2b (Supabase→RDS asyncpg 전환) — 이 파일 전체 xfail.
# 본 가드는 supabase `execute_with_retry` 경유(체인 mock `.execute()` side_effect +
# chain.execute.call_count==2 로 재시도 검증)를 단언한다. asyncpg 전환으로 재시도는
# `src.db.pg._with_retry` 내부로 이동했고 재시도 대상 예외군도 httpx →
# asyncpg(PostgresConnectionError/InterfaceError 등)로 바뀌었다. supabase 심볼 부재로
# `patch.object(smd, "supabase")` 가 AttributeError → 라우팅 불가.
# read 4함수(get_recent_daily/count_all/max_bas_dd)의 fetch/fetchval 경유 + graceful
# 폴백 계약은 M2b 신규 가드 test_cycleM2b_stock_master_daily_pg.py 가 pg 레벨에서 커버
# (test_get_recent_daily_desc_limit_via_fetch / _exception_graceful_empty /
#  test_count_all_via_fetchval / test_max_bas_dd_ticker_none_and_specified), _with_retry
# 재시도 로직 자체는 pg 인프라 테스트가 담당.
pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b — supabase execute_with_retry 경유 계약이 pg._with_retry 로 대체됨 "
            "(supabase 심볼 부재, 재시도 예외군 httpx→asyncpg). read 함수 fetch/graceful 계약은 "
            "test_cycleM2b_stock_master_daily_pg.py 가 커버."
        ),
    ),
]


@pytest.fixture(autouse=True)
def no_sleep():
    """asyncio.sleep 무력화 — 재시도 backoff 실지연 0 (전역 패치, Red 안전)."""
    with patch("asyncio.sleep", new_callable=AsyncMock):
        yield


def _make_supabase(execute_side_effect):
    """모든 체인 링크가 자기 자신 반환 + `.execute()` side_effect 부착한 supabase mock.

    Returns:
        (mock_supabase, chain) — chain.execute.call_count 로 재시도 횟수 검증.
    """
    chain = MagicMock(name="chain")
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute.side_effect = execute_side_effect

    mock_sb = MagicMock(name="supabase")
    mock_sb.table.return_value = chain
    return mock_sb, chain


def _ok(*, data=None, count=None):
    """Supabase 응답 mock — data / count 명시 (MagicMock 자동 child 회피)."""
    r = MagicMock(name="result")
    r.data = data
    r.count = count
    return r


# ---------------------------------------------------------------------------
# G-187-I1 — get_recent_daily: 1차 RemoteProtocolError → 2차 성공 → rows. Red 핵심.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G187_I1_get_recent_daily_retry_then_rows():
    """1차 Server disconnected → 재시도 → 2차 성공 → rows 반환 (graceful [] 안 빠짐)."""
    rows_data = [
        {"ticker": "005930", "bas_dd": "2024-06-20", "close_price": 71000},
        {"ticker": "005930", "bas_dd": "2024-06-19", "close_price": 70500},
    ]
    mock_sb, chain = _make_supabase(
        [httpx.RemoteProtocolError("Server disconnected"), _ok(data=rows_data)]
    )

    with patch.object(smd, "supabase", mock_sb):
        rows = await smd.get_recent_daily("005930", 22)

    assert rows == rows_data, "재시도 후 rows 반환 (현행 retry 미존재 시 graceful [] = Red FAIL)"
    assert chain.execute.call_count == 2, "1차 실패 + 2차 성공 = execute 2회 (retry 경유)"


# ---------------------------------------------------------------------------
# G-187-I2 — get_recent_daily: 2회 실패 → graceful [] (기존 except 보존). Red PASS.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G187_I2_get_recent_daily_two_failures_graceful():
    """재시도 소진 (2회 실패) → 기존 except 보존 → 빈 list 폴백.

    현행 (retry 미존재) 도 1회 실패 → 즉시 graceful [] → 동일 결과 (불변식, PASS).
    """
    mock_sb, _chain = _make_supabase(
        [
            httpx.RemoteProtocolError("disconnect 1"),
            httpx.RemoteProtocolError("disconnect 2"),
        ]
    )

    with patch.object(smd, "supabase", mock_sb):
        rows = await smd.get_recent_daily("005930", 22)

    assert rows == [], "재시도 소진 → 기존 graceful 폴백 [] 보존"


# ---------------------------------------------------------------------------
# G-187-I3 — count_all: retry 후 성공 → count / 2회 실패 → graceful 0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G187_I3_count_all_retry_and_graceful():
    """count_all — 1차 실패 → 재시도 → count 반환 / 2회 실패 → graceful 0."""
    # (1) retry 후 성공 → count (현행 retry 미존재 시 0 반환 = Red FAIL)
    mock_sb, chain = _make_supabase(
        [httpx.RemoteProtocolError("Server disconnected"), _ok(count=2768)]
    )
    with patch.object(smd, "supabase", mock_sb):
        cnt = await smd.count_all()
    assert cnt == 2768, "재시도 후 count 반환"
    assert chain.execute.call_count == 2, "retry 경유 = execute 2회"

    # (2) 2회 실패 → graceful 0 (기존 except 보존)
    mock_sb2, _chain2 = _make_supabase(
        [
            httpx.RemoteProtocolError("d1"),
            httpx.RemoteProtocolError("d2"),
        ]
    )
    with patch.object(smd, "supabase", mock_sb2):
        cnt2 = await smd.count_all()
    assert cnt2 == 0, "재시도 소진 → graceful 0 보존"


# ---------------------------------------------------------------------------
# G-187-I4 — max_bas_dd(ticker) + max_bas_dd(None): retry 후 성공 / 2회 실패 → None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G187_I4_max_bas_dd_retry_and_graceful():
    """max_bas_dd — ticker 지정/None 두 분기 retry-success + 2회 실패 graceful None."""
    # (1) ticker 지정 — retry 후 성공 → date
    mock_sb, chain = _make_supabase(
        [httpx.RemoteProtocolError("disconnect"), _ok(data=[{"bas_dd": "2024-06-20"}])]
    )
    with patch.object(smd, "supabase", mock_sb):
        d = await smd.max_bas_dd("005930")
    assert d == date(2024, 6, 20), "재시도 후 최신 bas_dd 반환 (ticker 분기)"
    assert chain.execute.call_count == 2, "retry 경유 = execute 2회"

    # (2) ticker None (전체 MAX) — retry 후 성공 → date
    mock_sb2, chain2 = _make_supabase(
        [httpx.RemoteProtocolError("disconnect"), _ok(data=[{"bas_dd": "2024-06-19"}])]
    )
    with patch.object(smd, "supabase", mock_sb2):
        d2 = await smd.max_bas_dd(None)
    assert d2 == date(2024, 6, 19), "재시도 후 최신 bas_dd 반환 (None 분기)"
    assert chain2.execute.call_count == 2, "None 분기도 retry 경유 = execute 2회"

    # (3) 2회 실패 → graceful None
    mock_sb3, _chain3 = _make_supabase(
        [
            httpx.RemoteProtocolError("d1"),
            httpx.RemoteProtocolError("d2"),
        ]
    )
    with patch.object(smd, "supabase", mock_sb3):
        d3 = await smd.max_bas_dd("005930")
    assert d3 is None, "재시도 소진 → graceful None 보존"
