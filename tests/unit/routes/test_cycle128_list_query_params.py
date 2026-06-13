"""사이클 128 P1-2 — GET /api/stock-master/list 쿼리 파라미터 4 흡수 + 응답 schema 회귀 가드.

신규 query param (모두 optional):
- market: "KOSPI" | "KOSDAQ" | None
- min_market_cap: int (억원 단위 → 백엔드 변환 후 원 단위 list_paged_by_filter 호출)
- min_trade_amount: int (억원 단위 → 백엔드 변환)
- name_substr: str | None

응답 schema:
- 기존: list[dict]
- 사이클 128: {"items": list[dict], "total": int, "limit": int, "offset": int}

T-1 영속: 4 query param 모두 미지정 시 list_paged_by_filter 또는 동등 동작 + total 포함.
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


def test_g_route_list1_empty_filter_returns_envelope(client):
    """G-ROUTE-LIST1: 빈 필터 GET /list 응답 schema = {items, total, limit, offset}."""
    fake_result = {
        "items": [{"ticker": "005930", "name": "삼성전자"}],
        "total": 2697,
        "limit": 100,
        "offset": 0,
    }

    with patch(
        "src.db.stock_master.list_paged_by_filter",
        new=AsyncMock(return_value=fake_result),
    ):
        response = client.get("/api/stock-master/list")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    # 사이클 128 schema 의무
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert data["total"] == 2697
    assert data["limit"] == 100
    assert data["offset"] == 0
    assert data["items"][0]["ticker"] == "005930"


def test_g_route_list2_market_param_passes_through(client):
    """G-ROUTE-LIST2: ?market=KOSPI 가 list_paged_by_filter 에 전달."""
    captured: dict = {}

    async def fake_filter(**kwargs):
        captured.update(kwargs)
        return {"items": [], "total": 0, "limit": kwargs.get("limit", 100), "offset": kwargs.get("offset", 0)}

    with patch("src.db.stock_master.list_paged_by_filter", new=fake_filter):
        response = client.get("/api/stock-master/list?market=KOSPI")

    assert response.status_code == 200, response.text
    assert captured.get("market") == "KOSPI"


def test_g_route_list3_name_substr_param_passes_through(client):
    """G-ROUTE-LIST3: ?name_substr=삼성 이 list_paged_by_filter 에 전달."""
    captured: dict = {}

    async def fake_filter(**kwargs):
        captured.update(kwargs)
        return {"items": [], "total": 0, "limit": kwargs.get("limit", 100), "offset": kwargs.get("offset", 0)}

    with patch("src.db.stock_master.list_paged_by_filter", new=fake_filter):
        response = client.get("/api/stock-master/list?name_substr=삼성")

    assert response.status_code == 200, response.text
    assert captured.get("name_substr") == "삼성"


def test_g_route_list4_min_market_cap_billion_converts_to_won(client):
    """G-ROUTE-LIST4: ?min_market_cap=1000 (억원) → 백엔드 1_000 * 100_000_000 = 1천억 원 변환.

    T-2 단위 변환 헬퍼 캡슐화 의무 — 프론트 억원 입력 → 백엔드 원 단위.
    """
    captured: dict = {}

    async def fake_filter(**kwargs):
        captured.update(kwargs)
        return {"items": [], "total": 0, "limit": kwargs.get("limit", 100), "offset": kwargs.get("offset", 0)}

    with patch("src.db.stock_master.list_paged_by_filter", new=fake_filter):
        response = client.get("/api/stock-master/list?min_market_cap=1000")

    assert response.status_code == 200, response.text
    # 1000 억원 = 100_000_000_000 원
    assert captured.get("min_market_cap") == 100_000_000_000, (
        f"억원 → 원 변환 의무 (×100_000_000). 실제: {captured.get('min_market_cap')}"
    )


def test_g_route_list5_min_trade_amount_billion_converts_to_won(client):
    """G-ROUTE-LIST5: ?min_trade_amount=500 (억원) → 500 * 100_000_000 = 5백억 원."""
    captured: dict = {}

    async def fake_filter(**kwargs):
        captured.update(kwargs)
        return {"items": [], "total": 0, "limit": kwargs.get("limit", 100), "offset": kwargs.get("offset", 0)}

    with patch("src.db.stock_master.list_paged_by_filter", new=fake_filter):
        response = client.get("/api/stock-master/list?min_trade_amount=500")

    assert response.status_code == 200, response.text
    assert captured.get("min_trade_amount") == 50_000_000_000, (
        f"억원 → 원 변환 의무. 실제: {captured.get('min_trade_amount')}"
    )


def test_g_route_list6_combined_params(client):
    """G-ROUTE-LIST6: 4 파라미터 동시 지정 모두 전달."""
    captured: dict = {}

    async def fake_filter(**kwargs):
        captured.update(kwargs)
        return {"items": [], "total": 0, "limit": 100, "offset": 0}

    with patch("src.db.stock_master.list_paged_by_filter", new=fake_filter):
        response = client.get(
            "/api/stock-master/list"
            "?market=KOSDAQ&min_market_cap=500&min_trade_amount=100&name_substr=바이오"
        )

    assert response.status_code == 200, response.text
    assert captured.get("market") == "KOSDAQ"
    assert captured.get("min_market_cap") == 50_000_000_000
    assert captured.get("min_trade_amount") == 10_000_000_000
    assert captured.get("name_substr") == "바이오"
