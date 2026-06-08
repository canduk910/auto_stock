"""사이클 84 Red — M-5 (HIGH): 5 라우트 ApiResponse 래퍼 정합.

backend-dev Green 단계 `src/routes/stock_master.py` 신규 5 라우트 모두 ApiResponse 래퍼 의무
(`success`/`data`/`message`). 프론트 사이클 85 `data.data` 추출 정합성 보장.

위험 등급 HIGH (사이클 65 답습 영속 + 사이클 85 프론트 연동 정합성).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client(monkeypatch):
    """stock_master DB 헬퍼 mock — DB 의존성 격리."""
    from src.db import stock_master as sm
    from src.models.stock import StockBasics

    fake_basics = StockBasics(
        ticker="005930",
        name="삼성전자",
        excg_dvsn_cd="STK",
        nxt_tradable=True,
        krx_halted=False,
        admin_item=False,
        raw={"bfdy_clpr": "70000"},
    )

    monkeypatch.setattr(sm, "get", AsyncMock(return_value=fake_basics), raising=False)
    monkeypatch.setattr(sm, "list_all", AsyncMock(return_value=[]), raising=False)
    monkeypatch.setattr(
        sm, "get_stats",
        AsyncMock(return_value={
            "count_all": 14, "bfdy_clpr_present": 13,
            "nxt_tradable_count": 9, "top_10_recent": [],
        }),
        raising=False,
    )
    monkeypatch.setattr(sm, "list_history", AsyncMock(return_value=[]), raising=False)
    monkeypatch.setattr(
        sm, "count_eager_refresh_today", AsyncMock(return_value=0), raising=False
    )

    from src.main import app
    return TestClient(app)


@pytest.mark.parametrize("path", [
    "/api/stock-master/stats",
    "/api/stock-master/list",
    "/api/stock-master/005930",
    "/api/stock-master/005930/history",
    "/api/stock-master/scan-pool/summary",
])
def test_M5_all_routes_return_api_response_envelope(client, path):
    """M-5: 5 라우트 전수 ApiResponse 래퍼 `{success, data, message}` 응답.

    backend-dev Green 단계 라우트 작성 시 `response_model=ApiResponse` + `return ApiResponse(...)` 의무.
    """
    res = client.get(path)
    assert res.status_code == 200, (
        f"라우트 {path} 200 의무 (실제 {res.status_code}, body={res.text[:200]}) — "
        "backend-dev Green 단계 `src/routes/stock_master.py` 미작성/미등록"
    )
    body = res.json()
    assert "success" in body, f"{path}: ApiResponse `success` 필드 누락"
    assert "data" in body, f"{path}: ApiResponse `data` 필드 누락"
    assert body["success"] is True, f"{path}: success=True 의무 (실제 {body['success']})"
