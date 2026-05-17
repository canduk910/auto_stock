"""`/api/realtime/subscriptions` 풀 응답 확장 contract — 사이클 7-B (2026-05-17).

기존 응답에 `sessions` 배열 추가:
{
  "total": ..., "acked": ..., "fresh_60s": ..., "stale_60s": ..., "limit": ...,
  "sessions": [
    {"label": "main", "subscribed": ..., "acked": ..., "fresh": ..., "stale": ..., "limit": 41, "ws_connected": true, "reconnect_count": 0},
    {"label": "quote-1", ...},
    ...
  ],
  ...
}

회귀 보호:
- 보조 세션 0개 시 sessions 길이 1 (main only) — 기존 응답 키와 호환
- 메인 단독 카운트가 total 과 일치 (집계 정합성)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


def _build_session_mock(label: str, subscribed_tickers: list[str], acked_tickers: list[str], connected: bool = True, reconnect: int = 0):
    """Mock KisWebSocket session — `_subscriptions` set + `_ws` 객체."""
    ws = MagicMock(name=label)
    ws._subscriptions = {("H0UNCNT0", t) for t in subscribed_tickers}
    ws._subscriptions_acked = {("H0UNCNT0", t) for t in acked_tickers}
    ws._ws = object() if connected else None
    ws._reconnect_count = reconnect
    return ws


def _build_app_with_pool(pool):
    """라우터 + 풀 패치 — 라우트 테스트 격리."""
    from fastapi import FastAPI

    from src.routes.realtime import router

    app = FastAPI()
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# 사양 1: 응답에 sessions 배열 포함
# ---------------------------------------------------------------------------
def test_subscriptions_response_includes_sessions_array(monkeypatch):
    """`/api/realtime/subscriptions` 응답 data 에 `sessions` 키 존재."""
    from src.realtime import websocket_pool
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["005930", "000660"], ["005930"])
    pool._quotes = [_build_session_mock("quote-1", ["AAA"], ["AAA"])]

    monkeypatch.setattr(websocket_pool, "kis_ws_pool", pool)
    # 호환: kis_ws 도 풀 메인으로 교체 (라우트는 kis_ws_pool 도 인식)
    import src.realtime.websocket as ws_mod
    monkeypatch.setattr(ws_mod, "kis_ws", pool._main)

    app = _build_app_with_pool(pool)
    with TestClient(app) as client:
        resp = client.get("/api/realtime/subscriptions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "sessions" in data, f"sessions 키 부재 — {list(data.keys())}"
    assert isinstance(data["sessions"], list)


def test_subscriptions_main_only_response_has_one_session(monkeypatch):
    """보조 0개 → sessions 길이 1 (main only)."""
    from src.realtime import websocket_pool
    from src.realtime.websocket_pool import WebsocketPool
    import src.realtime.websocket as ws_mod

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["005930"], ["005930"])
    pool._quotes = []

    monkeypatch.setattr(websocket_pool, "kis_ws_pool", pool)
    monkeypatch.setattr(ws_mod, "kis_ws", pool._main)

    app = _build_app_with_pool(pool)
    with TestClient(app) as client:
        resp = client.get("/api/realtime/subscriptions")
    data = resp.json()["data"]
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["label"] == "main"


def test_subscriptions_with_3_quote_sessions_has_4_sessions(monkeypatch):
    """보조 3개 → sessions 길이 4 (main + quote-1/2/3)."""
    from src.realtime import websocket_pool
    from src.realtime.websocket_pool import WebsocketPool
    import src.realtime.websocket as ws_mod

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["005930"], ["005930"])
    pool._quotes = [
        _build_session_mock("quote-1", ["A1", "A2"], ["A1", "A2"]),
        _build_session_mock("quote-2", ["B1"], ["B1"]),
        _build_session_mock("quote-3", [], []),
    ]

    monkeypatch.setattr(websocket_pool, "kis_ws_pool", pool)
    monkeypatch.setattr(ws_mod, "kis_ws", pool._main)

    app = _build_app_with_pool(pool)
    with TestClient(app) as client:
        resp = client.get("/api/realtime/subscriptions")
    data = resp.json()["data"]
    assert len(data["sessions"]) == 4
    labels = [s["label"] for s in data["sessions"]]
    assert labels == ["main", "quote-1", "quote-2", "quote-3"]


# ---------------------------------------------------------------------------
# 사양 2: 세션별 슬롯 카운트 노출
# ---------------------------------------------------------------------------
def test_subscriptions_session_has_required_fields(monkeypatch):
    """각 세션 dict 가 label/subscribed/acked/limit/ws_connected/reconnect_count 필수."""
    from src.realtime import websocket_pool
    from src.realtime.websocket_pool import WebsocketPool
    import src.realtime.websocket as ws_mod

    pool = WebsocketPool()
    pool._main = _build_session_mock(
        "main", ["005930", "000660"], ["005930"], connected=True, reconnect=0
    )
    pool._quotes = [
        _build_session_mock("quote-1", ["A1"], ["A1"], connected=False, reconnect=2),
    ]

    monkeypatch.setattr(websocket_pool, "kis_ws_pool", pool)
    monkeypatch.setattr(ws_mod, "kis_ws", pool._main)

    app = _build_app_with_pool(pool)
    with TestClient(app) as client:
        resp = client.get("/api/realtime/subscriptions")
    data = resp.json()["data"]
    main_section = data["sessions"][0]
    required = {"label", "subscribed", "acked", "limit", "ws_connected", "reconnect_count"}
    assert required.issubset(main_section.keys()), f"필수 키 누락 — {main_section.keys()}"
    assert main_section["subscribed"] == 2
    assert main_section["acked"] == 1
    assert main_section["limit"] == 41
    assert main_section["ws_connected"] is True
    assert main_section["reconnect_count"] == 0

    q1 = data["sessions"][1]
    assert q1["label"] == "quote-1"
    assert q1["ws_connected"] is False
    assert q1["reconnect_count"] == 2


# ---------------------------------------------------------------------------
# 사양 3: 집계 정합성 — main only 카운트 == total
# ---------------------------------------------------------------------------
def test_subscriptions_total_equals_sum_of_sessions_subscribed(monkeypatch):
    """data.total == sum(sessions[*].subscribed) — 집계 정합성."""
    from src.realtime import websocket_pool
    from src.realtime.websocket_pool import WebsocketPool
    import src.realtime.websocket as ws_mod

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["M1", "M2", "M3"], ["M1", "M2", "M3"])
    pool._quotes = [
        _build_session_mock("quote-1", ["Q1A", "Q1B"], ["Q1A"]),
        _build_session_mock("quote-2", ["Q2A"], ["Q2A"]),
    ]

    monkeypatch.setattr(websocket_pool, "kis_ws_pool", pool)
    monkeypatch.setattr(ws_mod, "kis_ws", pool._main)

    app = _build_app_with_pool(pool)
    with TestClient(app) as client:
        resp = client.get("/api/realtime/subscriptions")
    data = resp.json()["data"]
    sum_subscribed = sum(s["subscribed"] for s in data["sessions"])
    assert data["total"] == sum_subscribed == 6


def test_subscriptions_total_acked_equals_sum(monkeypatch):
    """data.acked == sum(sessions[*].acked)."""
    from src.realtime import websocket_pool
    from src.realtime.websocket_pool import WebsocketPool
    import src.realtime.websocket as ws_mod

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", ["M1", "M2"], ["M1"])
    pool._quotes = [
        _build_session_mock("quote-1", ["Q1A", "Q1B"], ["Q1A"]),
    ]

    monkeypatch.setattr(websocket_pool, "kis_ws_pool", pool)
    monkeypatch.setattr(ws_mod, "kis_ws", pool._main)

    app = _build_app_with_pool(pool)
    with TestClient(app) as client:
        resp = client.get("/api/realtime/subscriptions")
    data = resp.json()["data"]
    sum_acked = sum(s["acked"] for s in data["sessions"])
    assert data["acked"] == sum_acked == 2


# ---------------------------------------------------------------------------
# 사양 4: limit 합계 = 41 × (1 + N)
# ---------------------------------------------------------------------------
def test_subscriptions_total_limit_scales_with_session_count(monkeypatch):
    """`data.limit` == 41 × (1 + 보조 세션 수) — 총 슬롯 용량."""
    from src.realtime import websocket_pool
    from src.realtime.websocket_pool import WebsocketPool
    import src.realtime.websocket as ws_mod

    pool = WebsocketPool()
    pool._main = _build_session_mock("main", [], [])
    pool._quotes = [_build_session_mock(f"quote-{i}", [], []) for i in range(1, 4)]

    monkeypatch.setattr(websocket_pool, "kis_ws_pool", pool)
    monkeypatch.setattr(ws_mod, "kis_ws", pool._main)

    app = _build_app_with_pool(pool)
    with TestClient(app) as client:
        resp = client.get("/api/realtime/subscriptions")
    data = resp.json()["data"]
    # 메인 + 3 보조 = 4 세션 × 41 = 164
    assert data["limit"] == 41 * 4 == 164
