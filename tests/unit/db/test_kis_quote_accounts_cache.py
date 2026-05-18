"""사이클 14-D (2026-05-18) — `list_accounts()` 60s TTL 메모리 캐시.

배경 (운영 사고 2026-05-18):
- system_logs `[kis_quote_accounts] list 실패` ERROR 28회 (14:11, 14:44, 13:13 KST).
- 호출처 2곳: (1) `routes/kis_quote_accounts.py:42` Settings UI GET (KisQuoteAccountsCard +
  KisAccountPoolCard 30s 폴링) (2) `realtime/websocket_pool.py:112` _pool_start boot 1회.
- 폴링 시점에 supabase HTTP/2 stale connection 결함 + 컨테이너 재시작 race 로 다발 실패.
- graceful 폴백 ([]) 동작이라 매매 안전성 영향 0 이지만 ERROR 로그 누적 + DB 부하.

본 사이클은 모듈 전역 60s TTL 캐시를 추가:
- 매 호출 시 `time.monotonic()` 비교 → 만료 전 캐시 hit 으로 DB 호출 0
- INSERT/UPDATE/DELETE 직후 `invalidate_list_cache()` 즉시 무효화 — 운영 토글 즉시 반영
- DB 예외 시 stale 캐시 반환 (graceful), 캐시 없으면 빈 리스트 (회귀 보존)
- `active_only=True` vs `False` 키 분리

7 케이스:
1. TTL fresh — 60s 이내 재호출 캐시 hit (DB 호출 0)
2. TTL 만료 — 60s 경과 후 DB fetch 1 회
3. invalidate_list_cache — 명시 무효화 후 다음 호출 시 fresh fetch
4. 첫 호출 — 캐시 없을 때 정상 DB fetch
5. DB 예외 + 캐시 있음 — stale 캐시 반환 (graceful)
6. DB 예외 + 캐시 없음 — 빈 리스트 (회귀 보존)
7. active_only=True vs False 키 분리
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def fake_clock(monkeypatch):
    """`kis_quote_accounts.time.monotonic` 을 가짜 시계로 교체."""
    from src.db import kis_quote_accounts as kqa

    state = {"now": 1000.0}

    def _fake_monotonic():
        return state["now"]

    monkeypatch.setattr(kqa.time, "monotonic", _fake_monotonic, raising=False)
    return state


@pytest.fixture(autouse=True)
def _reset_cache():
    """매 테스트 시작 시 모듈 캐시 비우기."""
    from src.db import kis_quote_accounts as kqa

    kqa.invalidate_list_cache()
    yield
    kqa.invalidate_list_cache()


@pytest.fixture
def patched_supabase(monkeypatch):
    """`supabase.table(...).select(...).execute()` 호출 카운트 mock."""
    from src.db import kis_quote_accounts as kqa

    call_count = {"count": 0}
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "label": "ISA",
        "app_key": "appkey1234567890",
        "app_secret": "secret1234567890",
        "kis_env": "real",
        "active": True,
        "created_at": "2026-05-17T21:26:38+00:00",
        "updated_at": "2026-05-17T21:26:38+00:00",
    }

    def _build_table_chain():
        result_mock = MagicMock()
        result_mock.data = [row]

        q_mock = MagicMock()
        q_mock.select.return_value = q_mock
        q_mock.eq.return_value = q_mock
        q_mock.order.return_value = q_mock

        def _execute(*args, **kwargs):
            call_count["count"] += 1
            return result_mock

        q_mock.execute = _execute
        return q_mock

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = _build_table_chain()
    monkeypatch.setattr(kqa, "supabase", mock_supabase, raising=False)
    return call_count


# ===========================================================================
# Case 1: TTL fresh — 60s 이내 재호출 캐시 hit
# ===========================================================================
@pytest.mark.asyncio
async def test_list_accounts_cache_fresh_hits_skip_db_fetch(fake_clock, patched_supabase):
    """첫 호출 후 30s 뒤 재호출 → DB fetch 1 회만 (캐시 hit)."""
    from src.db.kis_quote_accounts import list_accounts

    fake_clock["now"] = 1000.0
    r1 = await list_accounts(active_only=False)
    assert patched_supabase["count"] == 1, "첫 호출 시 DB fetch 1 회"

    fake_clock["now"] = 1030.0  # 30s 경과 (TTL=60s 내)
    r2 = await list_accounts(active_only=False)
    assert patched_supabase["count"] == 1, (
        f"TTL 내 재호출은 캐시 hit (DB fetch 0). 실제 누적={patched_supabase['count']}"
    )
    # 캐시된 동일 결과
    assert [a.id for a in r2] == [a.id for a in r1]


# ===========================================================================
# Case 2: TTL 만료 — 60s 경과 후 DB fetch 1 회
# ===========================================================================
@pytest.mark.asyncio
async def test_list_accounts_cache_expires_after_ttl(fake_clock, patched_supabase):
    """첫 호출 후 60s 초과하면 다음 호출에서 DB fetch."""
    from src.db.kis_quote_accounts import list_accounts

    fake_clock["now"] = 1000.0
    await list_accounts(active_only=False)
    assert patched_supabase["count"] == 1

    fake_clock["now"] = 1061.0  # 61s 경과
    await list_accounts(active_only=False)
    assert patched_supabase["count"] == 2, (
        f"TTL 만료 후 fresh fetch 필요. 실제 누적={patched_supabase['count']}"
    )


# ===========================================================================
# Case 3: invalidate_list_cache — 명시 무효화
# ===========================================================================
@pytest.mark.asyncio
async def test_invalidate_list_cache_forces_next_fetch(fake_clock, patched_supabase):
    """`invalidate_list_cache()` 호출 → 다음 호출 시 즉시 DB fetch."""
    from src.db.kis_quote_accounts import invalidate_list_cache, list_accounts

    fake_clock["now"] = 1000.0
    await list_accounts(active_only=False)
    assert patched_supabase["count"] == 1

    invalidate_list_cache()  # 명시 무효화

    fake_clock["now"] = 1010.0  # TTL 내인데도 무효화로 인해 fresh fetch
    await list_accounts(active_only=False)
    assert patched_supabase["count"] == 2, (
        "invalidate 후 다음 호출은 무조건 DB fetch"
    )


# ===========================================================================
# Case 4: 첫 호출 — 캐시 없을 때 정상 DB fetch
# ===========================================================================
@pytest.mark.asyncio
async def test_list_accounts_first_call_fetches_db(fake_clock, patched_supabase):
    """캐시 미존재 시 첫 호출은 DB fetch."""
    from src.db.kis_quote_accounts import list_accounts

    fake_clock["now"] = 1000.0
    result = await list_accounts(active_only=False)
    assert patched_supabase["count"] == 1
    assert len(result) == 1
    assert result[0].label == "ISA"


# ===========================================================================
# Case 5: DB 예외 + 캐시 있음 — stale 반환 (graceful)
# ===========================================================================
@pytest.mark.asyncio
async def test_list_accounts_db_exception_returns_stale_cache(fake_clock, patched_supabase, monkeypatch):
    """첫 호출 성공으로 캐시 채운 후, 두 번째 호출에서 DB 예외 → stale 캐시 반환."""
    from src.db import kis_quote_accounts as kqa
    from src.db.kis_quote_accounts import list_accounts

    fake_clock["now"] = 1000.0
    r1 = await list_accounts(active_only=False)
    assert len(r1) == 1

    # TTL 만료 + DB 예외 시뮬레이션
    fake_clock["now"] = 1100.0  # 100s 경과 (TTL=60s 초과)

    def _broken_query():
        raise RuntimeError("supabase HTTP/2 stale connection")

    broken_q = MagicMock()
    broken_q.select.return_value = broken_q
    broken_q.eq.return_value = broken_q
    broken_q.order.return_value = broken_q
    broken_q.execute = MagicMock(side_effect=_broken_query)

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = broken_q
    monkeypatch.setattr(kqa, "supabase", mock_supabase, raising=False)

    r2 = await list_accounts(active_only=False)
    # 사이클 14-D: DB 실패해도 캐시된 stale 반환 (graceful, 운영 안정성)
    assert len(r2) == 1, (
        f"DB 예외 + 캐시 있음 → stale 캐시 반환. 실제 len={len(r2)}"
    )
    assert r2[0].label == "ISA"


# ===========================================================================
# Case 6: DB 예외 + 캐시 없음 — 빈 리스트 (회귀 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_list_accounts_db_exception_no_cache_returns_empty(fake_clock, monkeypatch):
    """캐시 없는 상태에서 DB 예외 → 빈 리스트 (사이클 7-A 회귀 보존)."""
    from src.db import kis_quote_accounts as kqa
    from src.db.kis_quote_accounts import list_accounts

    fake_clock["now"] = 1000.0

    broken_q = MagicMock()
    broken_q.select.return_value = broken_q
    broken_q.eq.return_value = broken_q
    broken_q.order.return_value = broken_q
    broken_q.execute = MagicMock(side_effect=RuntimeError("supabase down"))

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = broken_q
    monkeypatch.setattr(kqa, "supabase", mock_supabase, raising=False)

    result = await list_accounts(active_only=False)
    assert result == [], (
        f"DB 예외 + 캐시 없음 → 빈 리스트. 실제={result}"
    )


# ===========================================================================
# Case 7: active_only=True vs False 키 분리
# ===========================================================================
@pytest.mark.asyncio
async def test_list_accounts_cache_separates_active_only_key(fake_clock, patched_supabase):
    """`active_only=True` 와 `False` 는 별개 캐시 키 — 한쪽이 fresh 여도 다른 쪽은 fetch."""
    from src.db.kis_quote_accounts import list_accounts

    fake_clock["now"] = 1000.0
    await list_accounts(active_only=False)
    assert patched_supabase["count"] == 1

    # 동일 시점에 active_only=True 호출 — 별개 키라 fetch 필요
    await list_accounts(active_only=True)
    assert patched_supabase["count"] == 2, (
        f"active_only 분리 캐시 키 — 별개 fetch. 실제 누적={patched_supabase['count']}"
    )

    # 다시 active_only=False — 캐시 hit
    fake_clock["now"] = 1010.0
    await list_accounts(active_only=False)
    assert patched_supabase["count"] == 2, "False 캐시 보존 hit"
