"""사이클 13-E Red — WebsocketPool.stop() 의 _started=False 재설정 회귀 가드.

진단 (`_workspace/cycle13e_shutdown_pool_cleanup_spec.md` §2 원인 3):
``WebsocketPool.stop()`` docstring 가 명시:
> "메인 세션은 호출자(scheduler) 책임으로 별도 disconnect — 본 메서드는 보조만 정리.
>  풀의 ``_started`` flag 재설정해 다음 ``start()`` 호출 시 재초기화."

호출자(scheduler) 가 ``stop()`` 을 부르지 않으면 ``_started=True`` 가 잔존 → 다음
``start()`` 호출이 멱등 가드(``websocket_pool.py:105-107``)로 noop → 보조 세션 silent death.

본 테스트 파일은 ``WebsocketPool.stop()`` *자체* 의 회귀 가드 — ``stop()`` 호출 후
``_started=False`` 가 정확히 재설정되고, 이어지는 ``start()`` 호출이 멱등 noop 이
아니라 *재초기화 발화* 임을 검증한다.

Red 단계: 본 테스트는 scheduler 가 ``stop()`` 을 부르지 않는 결함과는 *직접* 무관하다.
다만 회귀 가드로 ``stop()`` 자체 정합성을 못박는다. ``_started=False`` 재설정이 깨지면
scheduler Green Patch 가 호출해도 결함이 재발한다.

본 테스트가 Red 인 이유:
- 첫 ``start()`` → DB 조회 실패 / 보조 0개 → ``_started=True`` 유지
- ``stop()`` 후 두 번째 ``start()`` 가 list_accounts 를 *다시* 호출하는지를 verify
- 현재 코드는 ``stop()`` 이 정상 동작하면 통과해야 하지만, 본 테스트는 scheduler 가
  실제로 ``stop()`` 을 호출하는지가 아니라 ``stop()`` 의 *기능* 자체를 검증.
- Red 상태는 본 테스트보다 Test B (scheduler 가 stop 호출 안 함) 에서 발현.

안전 가드 (CLAUDE.md):
- 체결통보 분기 (H0STCNI0/H0STCNI9) 손대지 않음 — TICK_TR_ID 만 다룸
- ``_subscriptions`` set 직접 수정 금지 — mock 객체 위에서만 조작
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Test C — _started=False 재설정 + 다음 start() 재초기화 발화
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pool_stop_resets_started_flag_to_false(monkeypatch):
    """``stop()`` 호출 후 ``_started`` 가 False 로 재설정돼야 한다.

    시나리오:
    1. pool = WebsocketPool()
    2. await pool.start() — list_accounts 빈 리스트 모킹 → _started=True 유지
    3. await pool.stop()
    4. assert pool._started is False
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()

    # list_accounts → 빈 리스트로 모킹 (보조 0개)
    with patch("src.db.kis_quote_accounts.list_accounts", new=AsyncMock(return_value=[])):
        await pool.start()
        assert pool._started is True, "start() 직후 _started=True 여야 함"

        await pool.stop()
        assert pool._started is False, (
            f"stop() 호출 후 _started=False 여야 함. 실제: {pool._started}"
        )


@pytest.mark.asyncio
async def test_pool_stop_allows_subsequent_start_to_reinitialize(monkeypatch):
    """``stop()`` 후 다음 ``start()`` 호출이 멱등 noop 이 아니라 *재초기화 발화* 여야 한다.

    핵심: ``_started`` flag 가 ``stop()`` 에서 False 로 재설정됐다면, 이어지는
    ``start()`` 가 ``list_accounts`` 를 *다시* 호출해 보조 세션 재초기화를 시도한다.
    재설정 안 되면 멱등 가드(``[pool_start] already started — noop``)로 list_accounts
    가 호출되지 않음 — 24h 토큰 만료 후 silent death 의 근원.
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()

    call_counter = {"n": 0}

    async def _fake_list_accounts(active_only: bool = True):
        call_counter["n"] += 1
        return []

    with patch(
        "src.db.kis_quote_accounts.list_accounts", side_effect=_fake_list_accounts
    ):
        # 1차 start — list_accounts 호출 1회
        await pool.start()
        assert call_counter["n"] == 1, "1차 start() 에서 list_accounts 1회 호출"

        # 2차 start — _started 가드로 멱등 noop
        await pool.start()
        assert call_counter["n"] == 1, (
            "stop() 없이 두 번째 start() 는 멱등 noop — list_accounts 추가 호출 0"
        )

        # stop() 후 3차 start — list_accounts 가 *다시* 호출돼야 함
        await pool.stop()
        await pool.start()
        assert call_counter["n"] == 2, (
            f"stop() 후 start() 는 재초기화 발화 — list_accounts 다시 호출. 실제 누적: {call_counter['n']}"
        )


@pytest.mark.asyncio
async def test_pool_stop_clears_quotes_and_ticker_tracking():
    """``stop()`` 후 ``_quotes`` 리스트 + ``_ticker_to_session`` 분배 추적 둘 다 빈 상태.

    회귀 가드: ``stop()`` 이 ``_quotes.clear()`` + ``_ticker_to_session.clear()`` 를
    정확히 수행해야 다음 ``start()`` 호출이 stale 한 보조 세션 참조 없이 깨끗하게
    재초기화 가능.
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()

    # 가짜 보조 세션 + 분배 추적 미리 주입 (실제 start() 우회)
    fake_quote = MagicMock()
    fake_quote.disconnect = AsyncMock()
    fake_quote._subscriptions = {("H0UNCNT0", "AAA")}
    pool._quotes = [fake_quote]
    pool._ticker_to_session = {"AAA": fake_quote}
    pool._started = True
    pool._quote_connect_tasks = []

    await pool.stop()

    assert pool._quotes == [], f"보조 세션 리스트 미정리: {pool._quotes}"
    assert pool._ticker_to_session == {}, (
        f"_ticker_to_session 분배 추적 미정리: {pool._ticker_to_session}"
    )
    assert pool._started is False
    fake_quote.disconnect.assert_awaited_once()
