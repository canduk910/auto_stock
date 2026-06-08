"""사이클 84 Red — H-6 (MEDIUM): limit 검증 422.

`GET /api/stock-master/list?limit=N` 에서 N < 1 또는 N > 1000 → 422 (Pydantic Query validator).

위험 등급 MEDIUM (라우트 입력 검증).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client(monkeypatch):
    from src.db import stock_master as sm

    monkeypatch.setattr(sm, "list_all", AsyncMock(return_value=[]), raising=False)

    from src.main import app
    return TestClient(app)


@pytest.mark.parametrize("limit", [0, -1, 1001, 5000])
def test_H6_invalid_limit_returns_422(client, limit):
    """H-6: limit 범위 외 (< 1 or > 1000) → 422."""
    res = client.get(f"/api/stock-master/list?limit={limit}")
    assert res.status_code == 422, (
        f"limit={limit} 범위 외 시 422 의무 (실제 {res.status_code}, body={res.text[:200]}) — "
        "backend-dev Green 단계 `limit: int = Query(100, ge=1, le=1000)` 의무"
    )
