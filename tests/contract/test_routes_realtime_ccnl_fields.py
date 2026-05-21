"""사이클 37 (2026-05-21) — `/api/realtime/subscriptions` 응답에 KIS 체결시각 노출.

`tickers_detail` 에 `last_cntg_hour` / `today_volume` 필드 추가.
scheduler `_last_ccnl_cache` 매핑 (캐시 미스는 null).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


def _build_session_mock(label: str, subscribed_tickers: list[str],
                        acked_tickers: list[str], connected: bool = True):
    ws = MagicMock(name=label)
    ws._subscriptions = {("H0UNCNT0", t) for t in subscribed_tickers}
    ws._subscriptions_acked = {("H0UNCNT0", t) for t in acked_tickers}
    ws._ws = object() if connected else None
    ws._reconnect_count = 0
    return ws


def _build_client(pool, monkeypatch, *, ccnl_cache: dict | None = None,
                   stale_retry: dict | None = None):
    from fastapi import FastAPI
    from src.routes.realtime import router
    from src.realtime import websocket_pool as wp_mod
    from src.realtime import websocket as ws_mod
    from src.engine import scanner as scanner_mod

    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool, raising=True)
    monkeypatch.setattr(ws_mod, "MAX_SUBSCRIPTIONS", 41, raising=False)

    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    scanner_mod.ticker_last_tick.clear()
    scanner_mod.ticker_last_tick["005930"] = now - timedelta(seconds=5)
    scanner_mod.ticker_last_tick["036930"] = now - timedelta(seconds=300)  # stale
    scanner_mod.ticker_names.clear()
    scanner_mod.ticker_names["005930"] = "삼성전자"
    scanner_mod.ticker_names["036930"] = "주성엔지니어링"

    # scheduler mock — _last_ccnl_cache + _stale_retry_count
    from src.engine import scheduler as sch_mod
    fake_scheduler = MagicMock()
    fake_scheduler._stale_retry_count = stale_retry or {}
    fake_scheduler._stale_last_resubscribe_at = {}
    fake_scheduler._last_ccnl_cache = ccnl_cache or {}
    monkeypatch.setattr(sch_mod, "trading_scheduler", fake_scheduler, raising=False)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ===========================================================================
# R-1: tickers_detail 에 last_cntg_hour / today_volume 키 존재
# ===========================================================================
def test_tickers_detail_has_last_cntg_hour_and_today_volume(monkeypatch):
    """`sessions[*].tickers_detail` row 에 `last_cntg_hour` / `today_volume` 키 추가."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["005930", "036930"], ["005930", "036930"])
    pool._quotes = []

    ccnl_cache = {
        "036930": {
            "fetched_at": datetime.now(timezone(timedelta(hours=9))),
            "last_cntg_hour": "142045",
            "today_volume": 8500,
        }
    }

    client = _build_client(pool, monkeypatch, ccnl_cache=ccnl_cache)
    resp = client.get("/api/realtime/subscriptions")
    assert resp.status_code == 200
    detail = resp.json()["data"]["sessions"][0]["tickers_detail"]

    required_keys = {"ticker", "ticker_name", "stale", "last_tick",
                     "retries", "last_resub", "last_cntg_hour", "today_volume"}
    for row in detail:
        missing = required_keys - set(row.keys())
        assert not missing, f"필수 키 누락: {missing} in row={row}"

    by_ticker = {r["ticker"]: r for r in detail}
    # 036930 캐시 hit
    assert by_ticker["036930"]["last_cntg_hour"] == "142045"
    assert by_ticker["036930"]["today_volume"] == 8500
    # 005930 캐시 미스 → null
    assert by_ticker["005930"]["last_cntg_hour"] is None
    assert by_ticker["005930"]["today_volume"] is None


# ===========================================================================
# R-2: 캐시 미스 종목은 null 값으로 정상 노출
# ===========================================================================
def test_tickers_detail_null_for_cache_miss(monkeypatch):
    """`_last_ccnl_cache` 부재 종목 → last_cntg_hour / today_volume null (정상)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["005930"], ["005930"])
    pool._quotes = []

    # 캐시 비어있음
    client = _build_client(pool, monkeypatch, ccnl_cache={})
    detail = client.get("/api/realtime/subscriptions").json()["data"]["sessions"][0]["tickers_detail"]
    assert len(detail) == 1
    row = detail[0]
    assert row["last_cntg_hour"] is None
    assert row["today_volume"] is None


# ===========================================================================
# R-3: 기존 tickers_detail 필드 보존 (사이클 35 회귀)
# ===========================================================================
def test_existing_tickers_detail_fields_preserved(monkeypatch):
    """사이클 35 도입 필드 (ticker, ticker_name, stale, last_tick, retries, last_resub) 보존."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["005930"], ["005930"])
    pool._quotes = []

    client = _build_client(pool, monkeypatch)
    row = client.get("/api/realtime/subscriptions").json()["data"]["sessions"][0]["tickers_detail"][0]
    # 사이클 35 필드 보존
    assert row["ticker"] == "005930"
    assert row["ticker_name"] == "삼성전자"
    assert row["stale"] is False
    assert "last_tick" in row
    assert "retries" in row
    assert "last_resub" in row
