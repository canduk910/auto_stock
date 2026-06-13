"""사이클 126 영역 3-C + 4-B — POST /basics/refresh + /daily/refresh 회귀 가드.

사이클 90 _refresh_universe_lock 패턴 100% 답습:
- asyncio.Lock 단일 in-flight 가드
- 409 Conflict (동시 호출 차단)
- ApiResponse 정합
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client():
    from src.main import app
    return TestClient(app)


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget BackgroundTasks 전환 — 동기 응답 schema (total/updated/elapsed_ms) 폐기 → {status, task_key} 의미 전환 (사이클 66 K-2 패턴)",
)
def test_g_route1_basics_refresh_200(client):
    """G-ROUTE1: POST /api/stock-master/basics/refresh 200 + ApiResponse 정합."""
    async def fake_once(force: bool = True):
        return {"total": 100, "updated": 100, "skipped": 0, "failed": 0, "elapsed_ms": 1000}

    with patch("src.engine.scanner._stock_master_basics_refresh_once", fake_once):
        response = client.post("/api/stock-master/basics/refresh")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 100
    assert body["data"]["updated"] == 100
    assert "elapsed_ms" in body["data"]


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget BackgroundTasks 전환 — 동기 응답 schema (fetched/upserted_rows/elapsed_ms) 폐기 → {status, task_key} 의미 전환 (사이클 66 K-2 패턴)",
)
def test_g_route2_daily_refresh_200(client):
    """G-ROUTE2: POST /api/stock-master/daily/refresh 200 + ApiResponse 정합."""
    async def fake_once(force: bool = True):
        return {
            "total": 100,
            "fetched": 100,
            "upserted_rows": 10000,
            "skipped_fresh": 0,
            "failed": 0,
            "db_write_failures": 0,
            "elapsed_ms": 1000,
            "mode": "incremental",
        }

    with patch("src.engine.scanner._stock_master_daily_load_once", fake_once):
        response = client.post("/api/stock-master/daily/refresh")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 100
    assert body["data"]["upserted_rows"] == 10000
    assert body["data"]["mode"] == "incremental"
    assert body["data"]["db_write_failures"] == 0


def test_g_route1_basics_refresh_405_on_get(client):
    """GET /basics 요청 시 405 (POST only 가드, 사이클 90 패턴 답습)."""
    response = client.get("/api/stock-master/basics")
    assert response.status_code == 405


def test_g_route2_daily_refresh_405_on_get(client):
    """GET /daily 요청 시 405 (POST only 가드, 사이클 90 패턴 답습)."""
    response = client.get("/api/stock-master/daily")
    assert response.status_code == 405
