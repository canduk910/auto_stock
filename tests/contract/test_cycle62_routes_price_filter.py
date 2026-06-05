"""사이클 62 (2026-06-05) Red — C-Route 카테고리: `/api/system/price-filter` 컨트랙트 (3 케이스).

> **선행 명세**: `_workspace/red/cycle62_price_filter.md` (§C-Route)
> **설계 카드**: §3 API 라우트
> **선례**: `tests/contract/test_routes_buy_block.py` (사이클 8) 답습

요구 행위 (Red 단계 모두 404 정답 — 라우트 미존재):

CR-1: GET /api/system/price-filter → 200 + 기본 {min:0, max:0, mode:OFF}
CR-2: PUT /api/system/price-filter → 200 + 부분 갱신
CR-3: PUT 400/422 검증 (음수 / max<min / 잘못된 mode)

라우트 경로는 design card §3 권고: 신규 라우트 (또는 strategies.py 옆 통합). 본 테스트는
설계 카드 §3.1 권고대로 `/api/system/price-filter` 로 가정.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


@pytest.fixture
def client(monkeypatch):
    """가격 필터 DB 헬퍼 mock."""
    from src.db import system_config as sc

    state = {"min_price": 0, "max_price": 0, "mode": "OFF"}

    async def fake_get():
        # Red: PriceFilter import 자체가 실패할 수 있음 — 라우트 호출 시점에 해결됨
        from src.db.system_config import PriceFilter
        return PriceFilter(
            min_price=state["min_price"],
            max_price=state["max_price"],
            mode=state["mode"],
        )

    async def fake_set(
        min_price=None, max_price=None, mode=None,
    ):
        # 검증 (실제 헬퍼와 동형)
        if min_price is not None:
            if min_price < 0:
                raise ValueError(f"min_price out of range: {min_price}")
            state["min_price"] = min_price
        if max_price is not None:
            if max_price < 0:
                raise ValueError(f"max_price out of range: {max_price}")
            state["max_price"] = max_price
        # max < min 검증 (둘 다 명시되면 결과 기준)
        if state["max_price"] > 0 and state["min_price"] > state["max_price"]:
            raise ValueError("max_price < min_price")
        if mode is not None:
            if mode not in ("HARD", "WARN", "OFF"):
                raise ValueError(f"invalid mode: {mode}")
            state["mode"] = mode

    monkeypatch.setattr(sc, "get_price_filter", fake_get, raising=False)
    monkeypatch.setattr(sc, "set_price_filter", fake_set, raising=False)

    from src.main import app
    return SimpleNamespace(client=TestClient(app), state=state)


# ---------------------------------------------------------------------------
# CR-1: GET 기본값
# ---------------------------------------------------------------------------
def test_CR1_get_price_filter_returns_default(client):
    """CR-1: GET /api/system/price-filter → 200 + 기본 {min:0, max:0, mode:OFF}."""
    resp = client.client.get("/api/system/price-filter")
    assert resp.status_code == 200, (
        f"라우트 미등록 또는 응답 결함 (status={resp.status_code})"
    )
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["min_price"] == 0
    assert data["max_price"] == 0
    assert data["mode"] == "OFF"


# ---------------------------------------------------------------------------
# CR-2: PUT 부분 갱신
# ---------------------------------------------------------------------------
def test_CR2_put_partial_update(client):
    """CR-2: PUT /api/system/price-filter — 부분 갱신 + 200 + 갱신된 상태 응답."""
    # 1) mode 만 갱신 → 임계 보존
    resp = client.client.put(
        "/api/system/price-filter",
        json={"mode": "HARD"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "HARD"
    assert data["min_price"] == 0  # 보존
    assert data["max_price"] == 0  # 보존

    # 2) min/max 만 갱신 → mode 보존
    resp = client.client.put(
        "/api/system/price-filter",
        json={"min_price": 5000, "max_price": 1_000_000},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["min_price"] == 5000
    assert data["max_price"] == 1_000_000
    assert data["mode"] == "HARD"  # 보존


# ---------------------------------------------------------------------------
# CR-3: PUT 400/422 검증 (음수 / max<min / 잘못된 mode)
# ---------------------------------------------------------------------------
def test_CR3_put_invalid_returns_error(client):
    """CR-3: 음수 / max<min / 잘못된 mode → 400 또는 422."""
    # 음수 min
    resp = client.client.put(
        "/api/system/price-filter", json={"min_price": -100},
    )
    assert resp.status_code in (400, 422), (
        f"음수 min_price 검증 누락 (status={resp.status_code})"
    )

    # max < min (둘 다 명시)
    resp = client.client.put(
        "/api/system/price-filter",
        json={"min_price": 10_000, "max_price": 5000},
    )
    assert resp.status_code in (400, 422), (
        f"max<min 검증 누락 (status={resp.status_code})"
    )

    # 잘못된 mode
    resp = client.client.put(
        "/api/system/price-filter", json={"mode": "INVALID"},
    )
    assert resp.status_code in (400, 422), (
        f"잘못된 mode 검증 누락 (status={resp.status_code})"
    )

    # 소문자 mode (정합성 일관)
    resp = client.client.put(
        "/api/system/price-filter", json={"mode": "hard"},
    )
    assert resp.status_code in (400, 422)
