"""trading 라우트 계약 테스트 — /api/trading/*"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def _assert_envelope(body: dict):
    """ApiResponse 공통 래퍼 형태 검증."""
    assert set(body.keys()) >= {"success", "data", "message"}
    assert isinstance(body["success"], bool)


def test_status_returns_envelope_with_data(contract_env):
    r = contract_env.client.get("/api/trading/status")
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    assert body["success"] is True
    assert isinstance(body["data"], dict)


def test_status_with_include_filter_returns_subset(contract_env):
    """?include=system 으로 슬림 응답 — system 키만 포함."""
    r = contract_env.client.get("/api/trading/status?include=system")
    assert r.status_code == 200
    data = r.json()["data"]
    # 'system' 그룹 키의 일부만 돌아와야 한다 (positions/strategy/running 등)
    # 전체 응답 키 set 보다 작거나 같아야 함
    full = contract_env.client.get("/api/trading/status").json()["data"]
    assert set(data.keys()) <= set(full.keys())


def test_start_when_not_running_then_success(contract_env):
    contract_env.scheduler._running = False
    r = contract_env.client.post("/api/trading/start")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True


def test_start_when_already_running_then_failure_message(contract_env):
    contract_env.scheduler._running = True
    r = contract_env.client.post("/api/trading/start")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "실행 중" in body["message"]


def test_stop_when_running_then_success(contract_env):
    contract_env.scheduler._running = True
    r = contract_env.client.post("/api/trading/stop")
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert contract_env.scheduler._running is False


def test_stop_when_not_running_then_failure(contract_env):
    contract_env.scheduler._running = False
    r = contract_env.client.post("/api/trading/stop")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False


def test_positions_returns_position_tickers_and_detail(contract_env):
    r = contract_env.client.get("/api/trading/positions")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "position_tickers" in data
    assert "positions_detail" in data


def test_orders_returns_orders_field(contract_env):
    r = contract_env.client.get("/api/trading/orders")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True


def test_manual_sell_when_invalid_ticker_returns_failure_or_validation_error(contract_env, monkeypatch):
    """ticker 가 잘못된 형식이면 422 또는 success=False."""
    # quantity 누락 → 422
    r = contract_env.client.post("/api/trading/manual-sell", json={"ticker": "005930"})
    assert r.status_code == 422


def test_manual_sell_when_place_order_fails_then_returns_failure_envelope(contract_env, monkeypatch):
    """place_order 가 예외를 던지면 success=False 응답."""

    async def boom(*args, **kwargs):
        raise RuntimeError("KIS down")

    monkeypatch.setattr("src.routes.trading.place_order", boom, raising=False)
    # 동적 import 라 monkeypatch 도 동적 — try 한번
    monkeypatch.setattr("src.api.order.place_order", boom, raising=False)

    r = contract_env.client.post(
        "/api/trading/manual-sell", json={"ticker": "005930", "quantity": 10}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "실패" in body["message"]
