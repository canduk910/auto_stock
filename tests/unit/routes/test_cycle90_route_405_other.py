"""사이클 90 M-1 (MEDIUM) — PUT/DELETE/PATCH /refresh-universe 405 영속.

Red 명세 (`_workspace/red/cycle90_manual_refresh_universe_api.md`):

POST 1개 예외 허용 (사이클 84 L-2 영속) — PUT/DELETE/PATCH 는 405 의무.

기대 동작 (Green, 사이클 90):
- GET /refresh-universe = 405 (POST only)
- PUT /refresh-universe = 405
- DELETE /refresh-universe = 405
- PATCH /refresh-universe = 405

Red 상태: production 코드 0 → 모두 404.

위험 등급 MEDIUM (사이클 84 Q9=B 원칙 영속 보강).

영속 의무:
- 사이클 84 L-2 영속 (POST 1개 예외 허용 + 기타 0건 변경 0)
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client(monkeypatch):
    from src.engine import scanner
    monkeypatch.setattr(
        scanner, "fetch_top_500_universe", AsyncMock(return_value=[]), raising=False
    )
    from src.main import app
    return TestClient(app)


@pytest.mark.parametrize("method", ["put", "delete", "patch"])
def test_m1_other_methods_return_405(client, method):
    """M-1: PUT/DELETE/PATCH /refresh-universe 405 Method Not Allowed.

    POST 1개 예외 허용 (사이클 84 L-2 영속) + 기타 변경 메서드 0건 의무.
    """
    res = getattr(client, method)("/api/stock-master/refresh-universe")
    assert res.status_code == 405, (
        f"{method.upper()} /refresh-universe 405 의무 (실제 {res.status_code}) — "
        f"사이클 84 L-2 영속 위반 (POST 1개 예외 허용 + 기타 0건)"
    )


def test_m1_get_returns_405(client):
    """M-1-bis: GET /refresh-universe 405 (POST only).

    동일 path GET 요청은 POST only 라우트 의무.
    """
    res = client.get("/api/stock-master/refresh-universe")
    assert res.status_code == 405, (
        f"GET /refresh-universe 405 의무 (실제 {res.status_code}) — "
        "POST only 라우트 의무 위반"
    )
