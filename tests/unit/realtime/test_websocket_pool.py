"""WebsocketPool 시세 분배 — 사이클 7-B (2026-05-17).

배경:
- 사이클 7-A 에서 `kis_quote_accounts` 테이블 + multi-account 토큰 매니저 인프라 완성.
- 본 사이클은 시세 수신 핵심 변경 — 단일 WebSocket → 메인 + 보조 N 세션 풀.
- 외부 호출자(scanner/risk/scheduler) 인터페이스 100% 보존, 내부 분배 로직 캡슐화.

자금 안전 절대 원칙:
- 체결통보(H0STCNI0/H0STCNI9) → 메인 세션 단일 강제(보조 세션 시도 시 RuntimeError)
- 매매/잔고/체결조회 → 본 사이클 변경 0 (사이클 7-A 가드 명시됨)
- 보조 세션 0개 시 기존 동작 회귀 보존 (5/18 자문 영향 0)

본 파일은 다음 사양을 검증한다:
1. 메인 세션 우선 점유 (보유/익일청산 — bypass_limit=True 절대 보장)
2. 보조 세션 라운드로빈 (스캐닝 종목)
3. 체결통보 메인 강제 (보조 세션 시도 → RuntimeError)
4. 중복 ticker 차단 (메인 우선)
5. 슬롯 가득 시 drop + `[priority_drop_pool]` 로그
6. 보조 세션 0개 시 메인 only 회귀 동작
7. tr_key (ticker) → session label 분배 추적
8. get_subscribed_tickers / get_session_status
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 사양 1: WebsocketPool import + 기본 구조
# ---------------------------------------------------------------------------
def test_websocket_pool_module_importable():
    """`src.realtime.websocket_pool` 모듈이 import 가능."""
    from src.realtime import websocket_pool  # noqa: F401


def test_websocket_pool_class_exists():
    """`WebsocketPool` 클래스 + 기본 속성."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    assert hasattr(pool, "_main"), "메인 세션 보유"
    assert hasattr(pool, "_quotes"), "보조 세션 리스트"
    assert isinstance(pool._quotes, list)
    assert pool._main is not None, "메인 세션 None 금지 (생성자가 자동 초기화)"


def test_websocket_pool_main_session_is_kis_websocket():
    """메인 세션은 기존 `KisWebSocket` 인스턴스 (호환성)."""
    from src.realtime.websocket import KisWebSocket
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    assert isinstance(pool._main, KisWebSocket)


def test_websocket_pool_quotes_empty_by_default():
    """보조 세션 0개가 기본 (DB 미등록 시 메인 only 동작 회귀 보존)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    assert pool._quotes == [], "DB 미등록 시 보조 세션 0개"


# ---------------------------------------------------------------------------
# 사양 2: 분배 알고리즘 — _select_session
# ---------------------------------------------------------------------------
def test_select_session_high_priority_routes_to_main():
    """HIGH 우선순위(보유/익일청산) → 메인 세션 절대 보장."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    # 보조 2개 등록 (mock)
    pool._quotes = [MagicMock(), MagicMock()]

    chosen = pool._select_session("005930", priority="HIGH")
    assert chosen is pool._main


def test_select_session_low_priority_round_robin_among_quotes():
    """LOW 우선순위(스캐닝) → 보조 세션 라운드로빈."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    quote1 = MagicMock(name="quote-1")
    quote2 = MagicMock(name="quote-2")
    # 라운드로빈을 위해 슬롯 카운트 mock 필요
    quote1._subscriptions = set()
    quote2._subscriptions = set()
    pool._quotes = [quote1, quote2]

    # 첫 호출 → quote-1, 두 번째 → quote-2, 세 번째 → quote-1
    chosen1 = pool._select_session("AAA", priority="LOW")
    chosen2 = pool._select_session("BBB", priority="LOW")
    chosen3 = pool._select_session("CCC", priority="LOW")

    # 세 종목이 두 세션에 분산되어야 함
    chosen_ids = [id(chosen1), id(chosen2), id(chosen3)]
    assert id(quote1) in chosen_ids
    assert id(quote2) in chosen_ids
    # 같은 세션이 모두 차지하지는 않음
    assert not (chosen1 is chosen2 is chosen3)


def test_select_session_low_priority_fallback_to_main_if_no_quotes():
    """보조 세션 0개 → LOW 도 메인 fallback (회귀 보존)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    assert pool._quotes == []

    chosen = pool._select_session("AAA", priority="LOW")
    assert chosen is pool._main


def test_select_session_skips_full_quote_session():
    """슬롯 가득 찬 보조 세션은 라운드로빈에서 건너뛴다."""
    from src.realtime.websocket import MAX_SUBSCRIPTIONS
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    full_q = MagicMock(name="quote-1-full")
    full_q._subscriptions = {(f"TR{i}", f"K{i}") for i in range(MAX_SUBSCRIPTIONS)}
    empty_q = MagicMock(name="quote-2-empty")
    empty_q._subscriptions = set()
    pool._quotes = [full_q, empty_q]

    chosen = pool._select_session("NEW", priority="LOW")
    assert chosen is empty_q, "가득 찬 세션 건너뛰고 빈 세션 선택"


# ---------------------------------------------------------------------------
# 사양 3: subscribe — tr_key 분배 + 추적
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_subscribe_high_priority_calls_main_with_bypass():
    """priority=HIGH → 메인 세션의 subscribe(bypass_limit=True) 호출."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    # _subscriptions은 set 으로 유지 (라운드로빈 슬롯 카운트)
    pool._main._subscriptions = set()
    pool._quotes = []

    label = await pool.subscribe("H0UNCNT0", "005930", priority="HIGH")

    assert label == "main"
    pool._main.subscribe.assert_awaited_once()
    call = pool._main.subscribe.await_args
    assert call.args == ("H0UNCNT0", "005930")
    assert call.kwargs == {"bypass_limit": True}


@pytest.mark.asyncio
async def test_subscribe_low_priority_calls_quote_session():
    """priority=LOW → 보조 세션 라운드로빈 호출."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    quote1 = MagicMock()
    quote1._subscriptions = set()
    quote1.subscribe = AsyncMock()
    # 사이클 43 (2026-05-22) — label 매칭으로 변경
    quote1._label = "quote-1"
    pool._quotes = [quote1]

    label = await pool.subscribe("H0UNCNT0", "AAA", priority="LOW")

    assert label == "quote-1"
    quote1.subscribe.assert_awaited_once_with("H0UNCNT0", "AAA", bypass_limit=False)


@pytest.mark.asyncio
async def test_subscribe_tracks_ticker_to_session_mapping():
    """`_ticker_to_session` 분배 추적 dict 갱신."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    pool._main._subscriptions = set()

    await pool.subscribe("H0UNCNT0", "005930", priority="HIGH")

    assert "005930" in pool._ticker_to_session
    assert pool._ticker_to_session["005930"] is pool._main


@pytest.mark.asyncio
async def test_subscribe_default_priority_is_low():
    """priority 미지정 시 LOW (기존 호출자 호환)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    pool._main._subscriptions = set()
    # 보조 0 → LOW 도 메인 fallback
    pool._quotes = []

    label = await pool.subscribe("H0UNCNT0", "AAA")
    assert label == "main"
    # bypass_limit=False 가 LOW 의 기본
    pool._main.subscribe.assert_awaited_once_with("H0UNCNT0", "AAA", bypass_limit=False)


# ---------------------------------------------------------------------------
# 사양 4: 체결통보 메인 강제
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_subscribe_execution_notice_h0stcni0_forces_main():
    """tr_id == 'H0STCNI0' → 무조건 메인 세션."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    pool._main._subscriptions = set()
    quote1 = MagicMock()
    quote1._subscriptions = set()
    quote1.subscribe = AsyncMock()
    pool._quotes = [quote1]

    # priority 와 무관하게 메인으로 강제
    label = await pool.subscribe("H0STCNI0", "MYHTSID", priority="LOW")

    assert label == "main"
    pool._main.subscribe.assert_awaited_once()
    quote1.subscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscribe_execution_notice_h0stcni9_forces_main():
    """모의 환경 체결통보(H0STCNI9) 도 메인 강제."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    pool._main._subscriptions = set()
    quote1 = MagicMock()
    quote1._subscriptions = set()
    quote1.subscribe = AsyncMock()
    pool._quotes = [quote1]

    label = await pool.subscribe("H0STCNI9", "12345678", priority="LOW")

    assert label == "main"
    pool._main.subscribe.assert_awaited_once()
    quote1.subscribe.assert_not_awaited()


# ---------------------------------------------------------------------------
# 사양 5: 중복 ticker 차단 (메인 우선)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_ticker_main_first_blocks_quote_subscribe():
    """동일 ticker 가 HIGH(메인)로 먼저 등록 → LOW 시도 시 메인 그대로 사용."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    pool._main._subscriptions = set()
    quote1 = MagicMock()
    quote1._subscriptions = set()
    quote1.subscribe = AsyncMock()
    pool._quotes = [quote1]

    # 1차: 보유 종목으로 메인에 HIGH 등록
    await pool.subscribe("H0UNCNT0", "005930", priority="HIGH")
    # 2차: 같은 ticker 가 스캐닝 후보로 들어옴 → 메인에 이미 있으므로 보조에 추가 금지
    label2 = await pool.subscribe("H0UNCNT0", "005930", priority="LOW")

    assert label2 == "main", "중복 ticker 는 메인 세션 유지"
    quote1.subscribe.assert_not_awaited()
    # 메인 subscribe 도 한 번만 호출
    assert pool._main.subscribe.await_count == 1


@pytest.mark.asyncio
async def test_duplicate_ticker_quote_then_high_promotes_to_main(caplog):
    """이미 보조에 있는 ticker 가 HIGH 로 들어오면 메인으로 승격 (보조에서 unsubscribe)."""
    from src.realtime.websocket_pool import WebsocketPool

    caplog.set_level(logging.INFO, logger="src.realtime.websocket_pool")

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    pool._main._subscriptions = set()
    quote1 = MagicMock()
    quote1._subscriptions = set()
    quote1.subscribe = AsyncMock()
    quote1.unsubscribe = AsyncMock()
    pool._quotes = [quote1]

    # 1차: 보조에 LOW 로 등록
    await pool.subscribe("H0UNCNT0", "AAA", priority="LOW")
    assert pool._ticker_to_session["AAA"] is quote1
    # 2차: 같은 ticker 가 HIGH 로 들어옴 → 메인 승격
    label2 = await pool.subscribe("H0UNCNT0", "AAA", priority="HIGH")

    assert label2 == "main"
    quote1.unsubscribe.assert_awaited_once_with("H0UNCNT0", "AAA")
    pool._main.subscribe.assert_awaited_once()
    assert pool._ticker_to_session["AAA"] is pool._main


# ---------------------------------------------------------------------------
# 사양 6: 슬롯 가득 시 drop + 로그
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_sessions_full_drops_and_logs(caplog):
    """메인 + 모든 보조 가득 → drop + `[priority_drop_pool]` 로그."""
    from src.realtime.websocket import MAX_SUBSCRIPTIONS
    from src.realtime.websocket_pool import WebsocketPool

    caplog.set_level(logging.INFO, logger="src.realtime.websocket_pool")

    pool = WebsocketPool()
    # 메인 가득
    pool._main._subscriptions = {(f"TR{i}", f"K{i}") for i in range(MAX_SUBSCRIPTIONS)}
    pool._main.subscribe = AsyncMock()
    # 보조 1개 가득
    quote1 = MagicMock()
    quote1._subscriptions = {(f"TR{i}", f"Q{i}") for i in range(MAX_SUBSCRIPTIONS)}
    quote1.subscribe = AsyncMock()
    pool._quotes = [quote1]

    # LOW 시도 → drop
    label = await pool.subscribe("H0UNCNT0", "NEW", priority="LOW")

    assert label is None, "drop 시 None 반환"
    pool._main.subscribe.assert_not_awaited()
    quote1.subscribe.assert_not_awaited()

    # 로그 검증
    drop_logs = [r for r in caplog.records if "[priority_drop_pool]" in r.getMessage()]
    assert len(drop_logs) >= 1, f"[priority_drop_pool] 로그 1행 이상 — found={[r.getMessage() for r in caplog.records]}"


@pytest.mark.asyncio
async def test_high_priority_bypass_works_even_when_main_full():
    """메인이 가득 차도 HIGH 는 bypass_limit=True 로 절대 보장."""
    from src.realtime.websocket import MAX_SUBSCRIPTIONS
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main._subscriptions = {(f"TR{i}", f"K{i}") for i in range(MAX_SUBSCRIPTIONS)}
    pool._main.subscribe = AsyncMock()

    label = await pool.subscribe("H0UNCNT0", "HELD", priority="HIGH")

    assert label == "main"
    pool._main.subscribe.assert_awaited_once_with("H0UNCNT0", "HELD", bypass_limit=True)


# ---------------------------------------------------------------------------
# 사양 7: get_subscribed_tickers 통합 (모든 세션 합집합)
# ---------------------------------------------------------------------------
def test_get_subscribed_tickers_aggregates_all_sessions():
    """`get_subscribed_tickers()` 가 메인 + 보조 모든 세션의 TICK 구독 합집합 반환."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    # 메인에 3개 TICK 구독
    pool._main._subscriptions = {
        ("H0UNCNT0", "M001"),
        ("H0UNCNT0", "M002"),
        ("H0UNCNT0", "M003"),
        ("H0STCNI0", "HTSID"),  # 체결통보 — TICK 아님 → 제외
    }
    quote1 = MagicMock()
    quote1._subscriptions = {
        ("H0UNCNT0", "Q001"),
        ("H0UNCNT0", "Q002"),
    }
    pool._quotes = [quote1]

    tickers = pool.get_subscribed_tickers()

    assert isinstance(tickers, set)
    assert tickers == {"M001", "M002", "M003", "Q001", "Q002"}


def test_get_subscribed_tickers_main_only_when_no_quotes():
    """보조 세션 0개 시 메인 only (회귀)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main._subscriptions = {("H0UNCNT0", "M001"), ("H0UNCNT0", "M002")}
    pool._quotes = []

    tickers = pool.get_subscribed_tickers()
    assert tickers == {"M001", "M002"}


# ---------------------------------------------------------------------------
# 사양 8: get_session_status — 세션별 슬롯 진단
# ---------------------------------------------------------------------------
def test_get_session_status_returns_main_and_quotes_breakdown():
    """`get_session_status()` 가 메인 + 보조 세션별 slot 상태 dict 리스트 반환."""
    from src.realtime.websocket import MAX_SUBSCRIPTIONS
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main._subscriptions = {("H0UNCNT0", f"M{i:03d}") for i in range(5)}
    pool._main._subscriptions_acked = {("H0UNCNT0", f"M{i:03d}") for i in range(4)}
    pool._main._reconnect_count = 0
    pool._main._ws = object()  # truthy

    quote1 = MagicMock()
    quote1._subscriptions = {("H0UNCNT0", f"Q{i:03d}") for i in range(3)}
    quote1._subscriptions_acked = {("H0UNCNT0", f"Q{i:03d}") for i in range(3)}
    quote1._reconnect_count = 1
    quote1._ws = object()
    quote1._label = "quote-1"  # 사이클 43 (2026-05-22) — label 매칭
    pool._quotes = [quote1]

    status = pool.get_session_status()

    assert isinstance(status, list)
    assert len(status) == 2  # main + 1 quote

    main = status[0]
    assert main["label"] == "main"
    assert main["subscribed"] == 5
    assert main["acked"] == 4
    assert main["limit"] == MAX_SUBSCRIPTIONS
    assert main["ws_connected"] is True
    assert main["reconnect_count"] == 0

    q1 = status[1]
    assert q1["label"] == "quote-1"
    assert q1["subscribed"] == 3
    assert q1["acked"] == 3
    assert q1["limit"] == MAX_SUBSCRIPTIONS


def test_get_session_status_main_only_no_quotes():
    """보조 0개 시 status 길이 1."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main._subscriptions = set()
    pool._main._subscriptions_acked = set()
    pool._main._reconnect_count = 0
    pool._main._ws = None

    status = pool.get_session_status()
    assert len(status) == 1
    assert status[0]["label"] == "main"
    assert status[0]["ws_connected"] is False


# ---------------------------------------------------------------------------
# 사양 9: unsubscribe — 분배 추적 활용
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsubscribe_routes_to_recorded_session():
    """`_ticker_to_session` 기록된 세션에서 unsubscribe 호출."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.subscribe = AsyncMock()
    pool._main.unsubscribe = AsyncMock()
    pool._main._subscriptions = set()
    quote1 = MagicMock()
    quote1._subscriptions = set()
    quote1.subscribe = AsyncMock()
    quote1.unsubscribe = AsyncMock()
    pool._quotes = [quote1]

    # LOW 로 보조에 등록 후
    await pool.subscribe("H0UNCNT0", "AAA", priority="LOW")
    # unsubscribe 호출
    await pool.unsubscribe("H0UNCNT0", "AAA")

    quote1.unsubscribe.assert_awaited_once_with("H0UNCNT0", "AAA")
    pool._main.unsubscribe.assert_not_awaited()
    # 추적 dict 에서 제거
    assert "AAA" not in pool._ticker_to_session


@pytest.mark.asyncio
async def test_unsubscribe_unknown_ticker_is_noop():
    """추적 없는 ticker unsubscribe 는 noop (예외 X)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main.unsubscribe = AsyncMock()

    # 예외 안 나야 함
    await pool.unsubscribe("H0UNCNT0", "UNKNOWN")
    # 메인에 fallback 호출은 안 함 (분배 추적 없음 → 어디서 unsubscribe 할지 모름)
    # 정책: noop 이 안전 — 다음 _scan_loop 가 자연 정리
    pool._main.unsubscribe.assert_not_awaited()


# ---------------------------------------------------------------------------
# 사양 10: unsubscribe_all — 모든 세션 전체 해제
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsubscribe_all_clears_all_sessions():
    """`unsubscribe_all()` 이 메인 + 모든 보조 세션의 모든 구독 해제."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main._subscriptions = {
        ("H0UNCNT0", "M001"),
        ("H0UNCNT0", "M002"),
    }
    pool._main.unsubscribe = AsyncMock()
    quote1 = MagicMock()
    quote1._subscriptions = {("H0UNCNT0", "Q001")}
    quote1.unsubscribe = AsyncMock()
    pool._quotes = [quote1]
    pool._ticker_to_session = {
        "M001": pool._main, "M002": pool._main, "Q001": quote1,
    }

    await pool.unsubscribe_all()

    # 모든 ticker 가 각각 unsubscribe 됨
    assert pool._main.unsubscribe.await_count == 2
    assert quote1.unsubscribe.await_count == 1
    # 추적 dict clear
    assert pool._ticker_to_session == {}
