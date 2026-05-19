"""GET /api/realtime/stream-status contract 테스트 (사이클 15-C-1, 2026-05-19).

stream_pool_manager 상태를 응답으로 노출. 사용자 설계서 제6장.

5 케이스:
- A: 빈 상태 → 3 카테고리 모두 빈 리스트
- B: ws_active 1 종목 → ws 리스트 + min_hold_remaining_secs 필드
- C: rest_watch 1 종목 → rest 리스트
- D: cooldown 1 종목 → dropped 리스트 + cooldown_remaining_secs
- E: cooldown 만료 종목 호출 시 rest_watch 로 자동 전이
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


@pytest.fixture
def client(monkeypatch):
    from src.engine.stream_pool_manager import StreamPoolManager
    from src.main import app

    # 모듈 싱글톤 reset (테스트 격리)
    fresh = StreamPoolManager()
    monkeypatch.setattr("src.engine.stream_pool_manager.stream_pool_manager", fresh, raising=False)
    monkeypatch.setattr("src.routes.realtime.stream_pool_manager", fresh, raising=False)
    return TestClient(app), fresh


# ===========================================================================
# Case A: 빈 상태
# ===========================================================================
def test_stream_status_empty(client):
    c, _pool = client
    resp = c.get("/api/realtime/stream-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["rest"] == []
    assert body["data"]["ws"] == []
    assert body["data"]["dropped"] == []


# ===========================================================================
# Case B: ws_active 1 종목
# ===========================================================================
def test_stream_status_ws_active(client):
    c, pool = client
    pool.mark_promoted("005930", "volatility_breakout", "distance_pct=0.2%", now=1000.0)
    resp = c.get("/api/realtime/stream-status")
    data = resp.json()["data"]
    assert len(data["ws"]) == 1
    entry = data["ws"][0]
    assert entry["ticker"] == "005930"
    assert entry["strategy"] == "volatility_breakout"
    assert "min_hold_remaining_secs" in entry
    assert data["rest"] == []
    assert data["dropped"] == []


# ===========================================================================
# Case C: rest_watch 1 종목
# ===========================================================================
def test_stream_status_rest_watch(client):
    c, pool = client
    pool.mark_rest_watch("000660", "long_tail_volatility")
    resp = c.get("/api/realtime/stream-status")
    data = resp.json()["data"]
    assert len(data["rest"]) == 1
    assert data["rest"][0]["ticker"] == "000660"
    assert data["rest"][0]["strategy"] == "long_tail_volatility"


# ===========================================================================
# Case D: cooldown 1 종목 → dropped
# ===========================================================================
def test_stream_status_cooldown_dropped(client, monkeypatch):
    c, pool = client
    from src.engine.stream_pool_manager import MIN_WS_HOLD_SECS

    pool.mark_promoted("005380", "bull_flag_breakout", "near", now=1000.0)
    pool.reset_cycle()
    demote_time = 1000.0 + MIN_WS_HOLD_SECS + 10
    pool.mark_demoted("005380", "signal_faded", now=demote_time)

    # route 의 expire_cooldowns() 가 cooldown_until(=1610) 보다 작은 시점으로 mock
    import time as _time
    monkeypatch.setattr(_time, "monotonic", lambda: demote_time + 60)

    resp = c.get("/api/realtime/stream-status")
    data = resp.json()["data"]
    assert len(data["dropped"]) == 1
    entry = data["dropped"][0]
    assert entry["ticker"] == "005380"
    assert "cooldown_remaining_secs" in entry


# ===========================================================================
# Case E: cooldown 만료 → rest_watch 자동 전이
# ===========================================================================
def test_stream_status_expires_cooldown_on_query(client, monkeypatch):
    c, pool = client
    from src.engine.stream_pool_manager import MIN_WS_HOLD_SECS, WS_REJOIN_COOLDOWN_SECS

    pool.mark_promoted("005490", "vcp_breakout", "near", now=1000.0)
    pool.reset_cycle()
    demote_time = 1000.0 + MIN_WS_HOLD_SECS + 10
    pool.mark_demoted("005490", "signal_faded", now=demote_time)

    # cooldown 만료된 시점으로 monotonic mock
    import time as _time
    expire_time = demote_time + WS_REJOIN_COOLDOWN_SECS + 5
    monkeypatch.setattr(_time, "monotonic", lambda: expire_time)

    resp = c.get("/api/realtime/stream-status")
    data = resp.json()["data"]

    # cooldown 자동 전이 → rest_watch
    assert len(data["dropped"]) == 0
    assert len(data["rest"]) == 1
    assert data["rest"][0]["ticker"] == "005490"
