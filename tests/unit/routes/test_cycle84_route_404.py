"""사이클 84 Red — H-5 (MEDIUM): 미존재 ticker GET 시 404.

`GET /api/stock-master/{ticker}` 미존재 시 `HTTPException(status_code=404)` 의무.

위험 등급 MEDIUM (라우트 에러 처리 정합).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client(monkeypatch):
    """stock_master.get → None 시뮬 (미존재) + get_stats mock (라우트 등록 가드용)."""
    from src.db import stock_master as sm

    monkeypatch.setattr(sm, "get", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(
        sm, "get_stats",
        AsyncMock(return_value={
            "count_all": 0, "bfdy_clpr_present": 0,
            "nxt_tradable_count": 0, "top_10_recent": [],
        }),
        raising=False,
    )

    from src.main import app
    return TestClient(app)


def test_H5_get_unknown_ticker_returns_404(client):
    """H-5: GET /api/stock-master/999999 (미존재) → 404.

    Red 단계 vacuous PASS 방지: 먼저 stats 라우트 정상 응답 (200) 으로 라우트 등록 확인
    → 그 후 미존재 ticker 404 분기 의미있는 검증.
    """
    # 가드: 라우트 등록 확인 (Red 단계 라우트 부재 시 fail)
    stats_res = client.get("/api/stock-master/stats")
    assert stats_res.status_code == 200, (
        f"라우트 미등록 — GET /api/stock-master/stats {stats_res.status_code}. "
        "backend-dev Green 단계 라우트 등록 후 본 가드 정상화"
    )

    res = client.get("/api/stock-master/999999")
    assert res.status_code == 404, (
        f"미존재 ticker 404 의무 (실제 {res.status_code}, body={res.text[:200]}) — "
        "라우트는 등록되었으나 404 분기 누락"
    )
