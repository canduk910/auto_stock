"""사이클 13-E Red — WebsocketPool.stop() 보조 0개 회귀 가드.

진단 (`_workspace/cycle13e_shutdown_pool_cleanup_spec.md` §4 Red Test D):
보조 세션 0개 (``kis_quote_accounts`` 미등록) 상황은 점진 활성화 1단계 (코드 배포
직후, DB 미등록) 의 기본 동작이다. 본 환경에서도 ``pool.stop()`` 이 예외 없이 통과
해야 한다.

회귀 가드 목적:
- Green Patch 2/3 가 scheduler 종료 시퀀스에 ``pool.stop()`` 을 추가할 때, 보조 0개
  환경에서도 안전하게 통과해야 한다.
- ``_quotes`` 빈 리스트 → ``for ws in self._quotes`` 가 0회 순회 → 예외 없이
  ``_quotes.clear() / _ticker_to_session.clear() / _started = False`` 도달.

Red 단계 의미:
- 본 테스트는 현재 ``WebsocketPool.stop()`` 구현 (보조 0개에서 정상 동작) 자체는
  통과한다. 다만 ``_started=False`` 재설정 회귀 가드를 같이 검증하면, 향후 Green
  Patch 2/3 에서 stop 호출 누락 / 잘못된 분기가 도입되더라도 즉시 발견된다.
- "Red 상태" 의 본질은 Test A/B 에서 발현 — 본 D 는 동행 회귀 가드.

안전 가드 (CLAUDE.md):
- 체결통보 분기 (H0STCNI0/H0STCNI9) 무관 — TICK 만 다룸
- ``_subscriptions`` set 직접 수정 금지 — 운영 싱글톤 안 건드림 (새 인스턴스만)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Test D — 보조 0개 (kis_quote_accounts 미등록) 환경의 stop() 정상 종료
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pool_stop_with_empty_quotes_is_noop_safe():
    """보조 0개 환경에서 ``pool.start() → stop()`` 이 예외 없이 통과.

    시나리오:
    1. WebsocketPool 생성 (운영 싱글톤 사용 안 함 — 새 인스턴스)
    2. list_accounts → 빈 리스트 모킹 → 보조 0개 동작
    3. await pool.start() — ``[pool_start] 보조 시세 계좌 0개`` 분기 도달
    4. await pool.stop() — 예외 없이 통과
    5. _quotes == [] / _ticker_to_session == {} / _started is False
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()

    with patch("src.db.kis_quote_accounts.list_accounts", new=AsyncMock(return_value=[])):
        await pool.start()

    assert pool._quotes == [], (
        f"보조 0개 start() 직후 _quotes 비어있어야 함: {pool._quotes}"
    )
    assert pool._started is True, "start() 직후 _started=True"

    # stop() — 예외 없이 통과해야 한다
    await pool.stop()

    assert pool._quotes == [], (
        f"stop() 후에도 빈 보조 리스트 유지: {pool._quotes}"
    )
    assert pool._ticker_to_session == {}, (
        f"_ticker_to_session 분배 추적 비어있어야 함: {pool._ticker_to_session}"
    )
    assert pool._started is False, (
        f"_started 재설정 실패: {pool._started}"
    )


@pytest.mark.asyncio
async def test_pool_stop_without_prior_start_is_safe():
    """``start()`` 호출 없이 ``stop()`` 만 불러도 예외 없이 통과 (방어적 호출 가드).

    실제 scheduler 종료 흐름에서 풀 start 가 실패한 상태(보조 토큰 발급 실패 등)
    에서도 finally 에서 ``stop()`` 이 호출될 수 있다. 안전한 idempotent 동작 검증.
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()

    # start() 호출 없이 stop() — 예외 없이 통과
    await pool.stop()

    assert pool._quotes == []
    assert pool._ticker_to_session == {}
    assert pool._started is False
