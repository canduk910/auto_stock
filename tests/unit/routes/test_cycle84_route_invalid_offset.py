"""사이클 84 Red — H-7 (MEDIUM): offset 검증 422.

`GET /api/stock-master/list?offset=N` 에서 N < 0 → 422.

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


@pytest.mark.parametrize("offset", [-1, -100])
def test_H7_negative_offset_returns_422(client, offset):
    """H-7: offset < 0 시 422."""
    res = client.get(f"/api/stock-master/list?offset={offset}")
    assert res.status_code == 422, (
        f"offset={offset} 음수 시 422 의무 (실제 {res.status_code}, body={res.text[:200]}) — "
        "backend-dev Green 단계 `offset: int = Query(0, ge=0)` 의무"
    )
