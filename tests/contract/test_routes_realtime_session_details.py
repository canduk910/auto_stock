"""사이클 35 (2026-05-21) — 세션별 종목 상세 정보 확장.

배경:
- 사이클 28 `[tick_coverage_session]` 로그 데이터를 UI 에서 실시간 노출 요구.
- 기존 `/api/realtime/subscriptions` 응답이 sessions 배열은 제공하지만,
  세션별 종목 단위 stale/retries/last_resub 정보 미노출.

본 사이클 (35) 변경:
- `sessions[*].tickers_detail` 신규 — 종목별 (ticker, ticker_name, stale, last_tick, retries, last_resub) 배열
- 기존 `sessions[*].tickers.{subscribed, acked}` 보존 (UI 회귀 보호)
- 종목 cap 200 (세션별, 메모리/응답 크기 보호)

사양 (S-1 ~ S-5):
- S-1: sessions[*] 에 tickers_detail 키 존재 + 배열 타입
- S-2: tickers_detail row 가 필수 필드 보유 (ticker, ticker_name, stale, last_tick, retries, last_resub)
- S-3: stale 플래그가 60s freshness 와 일관 (라우트의 stale_set 과 동일 로직)
- S-4: 종목 cap 200 적용 (세션당)
- S-5: 기존 sessions[*].tickers 키 보존 (UI 회귀)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


def _build_session_mock(label: str, subscribed_tickers: list[str], acked_tickers: list[str],
                        connected: bool = True, reconnect: int = 0):
    """Mock KisWebSocket session."""
    ws = MagicMock(name=label)
    ws._subscriptions = {("H0UNCNT0", t) for t in subscribed_tickers}
    ws._subscriptions_acked = {("H0UNCNT0", t) for t in acked_tickers}
    ws._ws = object() if connected else None
    ws._reconnect_count = reconnect
    return ws


def _build_app_and_client(pool, monkeypatch):
    """라우터 + 풀 패치 + scheduler stale 추적 mock."""
    from fastapi import FastAPI
    from src.routes.realtime import router
    from src.realtime import websocket_pool as wp_mod
    from src.realtime import websocket as ws_mod
    from src.engine import scanner as scanner_mod

    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool, raising=True)
    monkeypatch.setattr(ws_mod, "MAX_SUBSCRIPTIONS", 41, raising=False)

    # ticker_last_tick: 일부 ticker 는 fresh (5초 전), 일부 stale (300초 전)
    from datetime import datetime, timedelta, timezone
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    scanner_mod.ticker_last_tick.clear()
    scanner_mod.ticker_last_tick["005930"] = now - timedelta(seconds=5)
    scanner_mod.ticker_last_tick["000660"] = now - timedelta(seconds=300)  # stale
    scanner_mod.ticker_last_tick["AAA"] = now - timedelta(seconds=10)
    scanner_mod.ticker_last_tick["BBB"] = now - timedelta(seconds=300)  # stale

    # ticker_names mock
    scanner_mod.ticker_names.clear()
    scanner_mod.ticker_names["005930"] = "삼성전자"
    scanner_mod.ticker_names["000660"] = "SK하이닉스"

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ===========================================================================
# S-1: sessions[*] 에 tickers_detail 키 존재 + 배열 타입
# ===========================================================================
def test_sessions_include_tickers_detail_key(monkeypatch):
    """`sessions[*].tickers_detail` 키 존재 + list 타입."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["005930", "000660"], ["005930", "000660"])
    pool._quotes = [_build_session_mock("quote-1", ["AAA", "BBB"], ["AAA", "BBB"])]

    client = _build_app_and_client(pool, monkeypatch)
    resp = client.get("/api/realtime/subscriptions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    sessions = data["sessions"]
    assert len(sessions) == 2
    for session in sessions:
        assert "tickers_detail" in session, (
            f"session {session['label']} 에 tickers_detail 키 누락"
        )
        assert isinstance(session["tickers_detail"], list)


# ===========================================================================
# S-2: tickers_detail row 의 필수 필드
# ===========================================================================
def test_tickers_detail_row_has_required_fields(monkeypatch):
    """tickers_detail row = {ticker, ticker_name, stale, last_tick, retries, last_resub}."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["005930", "000660"], ["005930", "000660"])
    pool._quotes = []

    client = _build_app_and_client(pool, monkeypatch)
    resp = client.get("/api/realtime/subscriptions")
    detail = resp.json()["data"]["sessions"][0]["tickers_detail"]
    assert len(detail) == 2
    required_keys = {"ticker", "ticker_name", "stale", "last_tick", "retries", "last_resub"}
    for row in detail:
        missing = required_keys - set(row.keys())
        assert not missing, f"필수 필드 누락: {missing} in row={row}"
    # ticker_name 매핑
    by_ticker = {r["ticker"]: r for r in detail}
    assert by_ticker["005930"]["ticker_name"] == "삼성전자"
    assert by_ticker["000660"]["ticker_name"] == "SK하이닉스"


# ===========================================================================
# S-3: stale 플래그 60s freshness 와 일관
# ===========================================================================
def test_tickers_detail_stale_flag_matches_60s_freshness(monkeypatch):
    """tickers_detail[*].stale 가 60s 임계 기반 stale 판정 일관."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    # 005930: fresh, 000660: stale
    pool._main = _build_session_mock("main", ["005930", "000660"], ["005930", "000660"])
    pool._quotes = []

    client = _build_app_and_client(pool, monkeypatch)
    detail = resp_detail = resp = client.get("/api/realtime/subscriptions").json()["data"]["sessions"][0]["tickers_detail"]
    by_ticker = {r["ticker"]: r for r in detail}
    assert by_ticker["005930"]["stale"] is False, "5초 전 tick → fresh"
    assert by_ticker["000660"]["stale"] is True, "300초 전 tick → stale (60s 초과)"


# ===========================================================================
# S-4: 종목 cap 200 적용 (세션당)
# ===========================================================================
def test_tickers_detail_capped_at_200_per_session(monkeypatch):
    """세션당 tickers_detail row 수 ≤ 200 (응답 크기 보호)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    # 300개 종목 시뮬 (실제 41 한도 무시 — _subscriptions 직접 주입)
    many_tickers = [f"{i:06d}" for i in range(300)]
    pool._main = _build_session_mock("main", many_tickers, many_tickers)
    pool._quotes = []

    client = _build_app_and_client(pool, monkeypatch)
    detail = client.get("/api/realtime/subscriptions").json()["data"]["sessions"][0]["tickers_detail"]
    assert len(detail) <= 200, f"세션당 cap 200 초과 — {len(detail)}건"


# ===========================================================================
# S-5: 기존 sessions[*].tickers 키 보존 (UI 회귀)
# ===========================================================================
def test_existing_tickers_key_preserved(monkeypatch):
    """기존 `sessions[*].tickers.{subscribed, acked}` 키 보존 (사이클 7-B 회귀)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["005930"], ["005930"])
    pool._quotes = []

    client = _build_app_and_client(pool, monkeypatch)
    session = client.get("/api/realtime/subscriptions").json()["data"]["sessions"][0]
    assert "tickers" in session
    assert "subscribed" in session["tickers"]
    assert "acked" in session["tickers"]
    assert "005930" in session["tickers"]["subscribed"]
