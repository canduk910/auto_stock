"""사이클 34 (2026-05-21) — strategy-funnel 라우트 contract."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


@pytest.fixture
def client(monkeypatch):
    from fastapi import FastAPI
    from src.routes.strategy_funnel import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ===========================================================================
# C-1: GET /api/strategy-funnel — 단일 영업일 조회
# ===========================================================================
def test_get_funnel_returns_snapshots(monkeypatch, client):
    """target_date + strategy_id 필터 + snapshots 응답."""
    from src.routes import strategy_funnel as sf_mod

    fake_snapshots = [
        {"id": "1", "step_no": 1, "step_name": "코스피200+코스닥150 합집합",
         "survived_count": 115, "excluded_count": 0,
         "survived_tickers": ["005930"], "excluded_sample": []},
        {"id": "2", "step_no": 4, "step_name": "20일 신고가 돌파",
         "survived_count": 0, "excluded_count": 111,
         "survived_tickers": [], "excluded_sample": []},
    ]
    monkeypatch.setattr(sf_mod, "list_snapshots", AsyncMock(return_value=fake_snapshots))

    resp = client.get("/api/strategy-funnel?target_date=2026-05-21&strategy_id=donchian_swing")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["target_date"] == "2026-05-21"
    assert data["strategy_id"] == "donchian_swing"
    assert len(data["snapshots"]) == 2
    assert data["snapshots"][0]["step_name"] == "코스피200+코스닥150 합집합"


def test_get_funnel_invalid_date_returns_422(client):
    """target_date 형식 오류 → 422."""
    resp = client.get("/api/strategy-funnel?target_date=invalid")
    assert resp.status_code == 422


def test_get_funnel_default_date_is_today(monkeypatch, client):
    """target_date 미지정 → 오늘 KST."""
    from src.routes import strategy_funnel as sf_mod
    from datetime import datetime, timezone, timedelta

    spy = AsyncMock(return_value=[])
    monkeypatch.setattr(sf_mod, "list_snapshots", spy)

    resp = client.get("/api/strategy-funnel")
    assert resp.status_code == 200
    today_kst = datetime.now(timezone(timedelta(hours=9))).date()
    assert resp.json()["data"]["target_date"] == today_kst.isoformat()


# ===========================================================================
# C-2: GET /api/strategy-funnel/recent — 최근 N일 추이
# ===========================================================================
def test_get_recent_funnel(monkeypatch, client):
    """recent?strategy_id=...&days=7 — 시계열 응답."""
    from src.routes import strategy_funnel as sf_mod

    fake_rows = [
        {"id": "1", "target_date": "2026-05-21", "step_no": 8,
         "survived_count": 5, "excluded_count": 0},
        {"id": "2", "target_date": "2026-05-20", "step_no": 8,
         "survived_count": 3, "excluded_count": 0},
    ]
    monkeypatch.setattr(sf_mod, "list_recent_by_strategy",
                        AsyncMock(return_value=fake_rows))

    resp = client.get("/api/strategy-funnel/recent?strategy_id=vcp_breakout&days=7")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["strategy_id"] == "vcp_breakout"
    assert data["days"] == 7
    assert len(data["snapshots"]) == 2


def test_get_recent_funnel_strategy_id_required(client):
    """strategy_id 미지정 → 422 (필수)."""
    resp = client.get("/api/strategy-funnel/recent?days=7")
    assert resp.status_code == 422


def test_get_recent_funnel_days_bounds(client):
    """days 1~30 범위 외 → 422."""
    resp = client.get("/api/strategy-funnel/recent?strategy_id=donchian_swing&days=0")
    assert resp.status_code == 422
    resp = client.get("/api/strategy-funnel/recent?strategy_id=donchian_swing&days=31")
    assert resp.status_code == 422


# ===========================================================================
# C-3: POST /api/strategy-funnel/snapshot — 수동 trigger
# ===========================================================================
def test_post_snapshot_triggers_all_strategies(monkeypatch, client):
    """수동 trigger — 활성 전략별 insert_snapshot 호출."""
    from src.routes import strategy_funnel as sf_mod
    from unittest.mock import MagicMock

    # registry mock — 2 전략
    s1 = MagicMock()
    s1.strategy_id = "donchian_swing"
    s1.get_scan_stats = MagicMock(return_value={"final_prepared": 0})
    s1.get_scanned_tickers = MagicMock(return_value=[])

    s2 = MagicMock()
    s2.strategy_id = "vcp_breakout"
    s2.get_scan_stats = MagicMock(return_value={"final_prepared": 5})
    s2.get_scanned_tickers = MagicMock(return_value=["005930", "000660"])

    fake_scheduler = MagicMock()
    fake_scheduler.registry.all = MagicMock(return_value=[s1, s2])
    monkeypatch.setattr("src.engine.scheduler.trading_scheduler", fake_scheduler)

    spy = AsyncMock(side_effect=lambda **kw: {"id": f"row-{kw['strategy_id']}"})
    monkeypatch.setattr(sf_mod, "insert_snapshot", spy)

    resp = client.post("/api/strategy-funnel/snapshot")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 2
    assert spy.await_count == 2
