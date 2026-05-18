"""사이클 13-E Red — scanner.unsubscribe_all() 가 보조 세션까지 정리해야 한다.

진단 (`_workspace/cycle13e_shutdown_pool_cleanup_spec.md` §2 원인 1):
현재 `scanner.unsubscribe_all()` 은 메인 세션 `kis_ws._subscriptions` 만 순회한다.
보조 세션(`kis_ws_pool._quotes[i]._subscriptions`) 과 분배 추적 dict
(`kis_ws_pool._ticker_to_session`) 는 그대로 잔존 → 다음 _scan_loop 또는 다음
사이클 _boot 진입 시 stale 상태.

기대 동작 (Green Patch 1):
- `scanner.unsubscribe_all()` 호출 시 `kis_ws_pool.unsubscribe_all()` 위임
- 결과: 메인 _subscriptions == set() AND 보조 _subscriptions == set()
        AND _ticker_to_session == {}

본 테스트는 *Red* 상태 — Green Patch 1 적용 전엔 보조 세션 정리가 일어나지 않아
실패한다.

안전 가드 (CLAUDE.md):
- 체결통보 분기 (H0STCNI0/H0STCNI9) 는 본 테스트에서 다루지 않는다 — TICK_TR_ID
  (H0UNCNT0) 만 검증. 메인 단일 강제 분기 무변경 보장.
- `_subscriptions` set 은 mock 객체 위에서만 조작 — 운영 싱글톤 직접 수정 금지.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — 가짜 KisWebSocket 세션
# ---------------------------------------------------------------------------
def _fake_session(subs: set[tuple[str, str]]) -> MagicMock:
    """`KisWebSocket` 인터페이스 일부를 흉내내는 mock 세션.

    - `_subscriptions` set 보유 (실제 KisWebSocket 과 동일 컨테이너 타입)
    - `unsubscribe(tr_id, tr_key)` async 호출 시 _subscriptions 에서 discard
    """
    ws = MagicMock()
    ws._subscriptions = set(subs)
    ws._subscriptions_acked = set()

    async def _unsub(tr_id: str, tr_key: str) -> None:
        ws._subscriptions.discard((tr_id, tr_key))
        ws._subscriptions_acked.discard((tr_id, tr_key))

    ws.unsubscribe = AsyncMock(side_effect=_unsub)
    return ws


# ---------------------------------------------------------------------------
# Test A — 보조 세션 1개 + 메인 세션 잔존 구독 정리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsubscribe_all_clears_main_and_quote_sessions(monkeypatch):
    """scanner.unsubscribe_all() 호출 시 메인 + 보조 세션 _subscriptions 둘 다 비어야 한다.

    시나리오:
    1. 메인 세션 _subscriptions = {(TICK, "005930"), (TICK, "000660")}
    2. 보조 세션 quote-1 _subscriptions = {(TICK, "035420")}
       + _ticker_to_session = {"035420": quote-1}
    3. await scanner.unsubscribe_all()
    4. 메인 _subscriptions == set()
    5. 보조 _subscriptions == set()
    6. _ticker_to_session == {}
    """
    from src.engine import scanner
    from src.realtime import websocket_pool as wsp_module

    TICK = scanner.TICK_TR_ID

    main_ws = _fake_session({(TICK, "005930"), (TICK, "000660")})
    quote1 = _fake_session({(TICK, "035420")})

    # 풀 mock — 운영 싱글톤 직접 수정 금지 → 임시 인스턴스 주입
    fake_pool = MagicMock()
    fake_pool._main = main_ws
    fake_pool._quotes = [quote1]
    fake_pool._ticker_to_session = {"035420": quote1}

    async def _pool_unsub_all() -> None:
        # WebsocketPool.unsubscribe_all 의 실제 의미 모사 — 분배 추적 순회 + clear
        for tr_key, ws in list(fake_pool._ticker_to_session.items()):
            for tid, tk in list(ws._subscriptions):
                if tk == tr_key:
                    await ws.unsubscribe(tid, tk)
        fake_pool._ticker_to_session.clear()

    fake_pool.unsubscribe_all = AsyncMock(side_effect=_pool_unsub_all)

    monkeypatch.setattr(scanner, "kis_ws", main_ws, raising=True)
    monkeypatch.setattr(scanner, "kis_ws_pool", fake_pool, raising=True)
    # 동일 모듈 싱글톤 일관성 — 풀이 가진 메인 참조와 scanner 가 가진 메인 참조 일치
    monkeypatch.setattr(wsp_module, "kis_ws_pool", fake_pool, raising=True)

    await scanner.unsubscribe_all()

    # Green Patch 1 후 통과해야 하는 어서션
    assert main_ws._subscriptions == set(), (
        f"메인 세션 잔존 구독: {main_ws._subscriptions}"
    )
    assert quote1._subscriptions == set(), (
        f"보조 세션 잔존 구독: {quote1._subscriptions}"
    )
    assert fake_pool._ticker_to_session == {}, (
        f"_ticker_to_session 분배 추적 잔존: {fake_pool._ticker_to_session}"
    )


# ---------------------------------------------------------------------------
# Test A-2 — 보조 0개 회귀 (메인 only 정리)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsubscribe_all_main_only_no_quotes_regression(monkeypatch):
    """보조 0개 (DB 미등록) 상황에서도 메인 단독 해제 정상 동작.

    Green Patch 1 후에도 메인 only 동작이 유지돼야 한다 (회귀 가드).
    """
    from src.engine import scanner
    from src.realtime import websocket_pool as wsp_module

    TICK = scanner.TICK_TR_ID

    main_ws = _fake_session({(TICK, "005930")})

    fake_pool = MagicMock()
    fake_pool._main = main_ws
    fake_pool._quotes = []
    fake_pool._ticker_to_session = {}

    async def _pool_unsub_all_empty() -> None:
        # 보조 0개 + 추적 없음 — clear noop
        fake_pool._ticker_to_session.clear()

    fake_pool.unsubscribe_all = AsyncMock(side_effect=_pool_unsub_all_empty)

    monkeypatch.setattr(scanner, "kis_ws", main_ws, raising=True)
    monkeypatch.setattr(scanner, "kis_ws_pool", fake_pool, raising=True)
    monkeypatch.setattr(wsp_module, "kis_ws_pool", fake_pool, raising=True)

    await scanner.unsubscribe_all()

    assert main_ws._subscriptions == set(), (
        f"메인 only 케이스에서 메인 잔존: {main_ws._subscriptions}"
    )
    # 분배 추적 없으면 그대로 비어있어야 한다
    assert fake_pool._ticker_to_session == {}


# ---------------------------------------------------------------------------
# Test A-3 — 풀 위임 검증 (Patch 1 핵심)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsubscribe_all_delegates_to_pool(monkeypatch):
    """scanner.unsubscribe_all() 이 kis_ws_pool.unsubscribe_all() 을 호출해야 한다.

    Green Patch 1 의 핵심 — 메인 세션 직접 순회 대신 풀 위임으로 보조 세션 + 분배
    추적 dict 까지 일괄 정리. 이 호출이 일어나지 않으면 보조 세션 정합성 결함.
    """
    from src.engine import scanner
    from src.realtime import websocket_pool as wsp_module

    main_ws = _fake_session(set())

    fake_pool = MagicMock()
    fake_pool._main = main_ws
    fake_pool._quotes = []
    fake_pool._ticker_to_session = {}
    fake_pool.unsubscribe_all = AsyncMock(return_value=None)

    monkeypatch.setattr(scanner, "kis_ws", main_ws, raising=True)
    monkeypatch.setattr(scanner, "kis_ws_pool", fake_pool, raising=True)
    monkeypatch.setattr(wsp_module, "kis_ws_pool", fake_pool, raising=True)

    await scanner.unsubscribe_all()

    fake_pool.unsubscribe_all.assert_awaited_once()
