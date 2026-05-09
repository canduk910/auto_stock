"""history 라우트 계약 — /api/history, /api/history/pnl"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def _make_trade(i, *, ticker="005930", strategy="momentum"):
    return {
        "id": i, "ticker": ticker, "ticker_name": "삼성전자",
        "trade_type": "BUY", "price": 70000 + i, "quantity": 1,
        "profit_loss": 0, "status": "COMPLETED", "strategy": strategy,
        "order_no": f"O-{i}", "timestamp": "2026-05-08T15:00:00+09:00",
    }


def test_history_default_pagination(contract_env):
    contract_env.state.trades = [_make_trade(i) for i in range(5)]
    r = contract_env.client.get("/api/history")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["page"] == 1
    assert data["size"] == 20
    assert data["total"] == 5
    assert data["total_pages"] == 1
    assert len(data["trades"]) == 5


def test_history_with_pagination_params(contract_env):
    contract_env.state.trades = [_make_trade(i) for i in range(50)]
    r = contract_env.client.get("/api/history?page=2&size=10")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["page"] == 2
    assert data["size"] == 10
    assert data["total"] == 50
    assert data["total_pages"] == 5
    assert len(data["trades"]) == 10
    # offset = 10 → trades[10:20]
    assert contract_env.calls.get_trades[-1]["offset"] == 10


def test_history_invalid_page_returns_422(contract_env):
    r = contract_env.client.get("/api/history?page=0")
    assert r.status_code == 422  # ge=1 위반


def test_history_size_max_100_validated(contract_env):
    r = contract_env.client.get("/api/history?size=500")
    assert r.status_code == 422  # le=100 위반


def test_history_strategy_filter_passes_through(contract_env):
    r = contract_env.client.get("/api/history?strategy=momentum&ticker=005930")
    assert r.status_code == 200
    last = contract_env.calls.get_trades[-1]
    assert last["strategy"] == "momentum"
    assert last["ticker"] == "005930"


def test_history_pnl_default_pagination(contract_env):
    contract_env.state.trade_pairs = [
        {"ticker": "005930", "ticker_name": "", "buy_price": 70000, "sell_price": 75000,
         "quantity": 10, "profit_loss": 50000, "profit_rate": 7.14, "strategy": "momentum"},
    ]
    r = contract_env.client.get("/api/history/pnl")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["page"] == 1
    assert data["size"] == 50
    assert data["total"] == 1
    assert len(data["pairs"]) == 1
    # ticker_name fallback (DB 빈값 + scanner 매핑)
    assert data["pairs"][0]["ticker_name"] == "삼성전자"


def test_history_pnl_pagination_slices_results(contract_env):
    contract_env.state.trade_pairs = [
        {"ticker": f"00{i:04d}", "buy_price": 1, "sell_price": 1, "quantity": 1,
         "profit_loss": 0, "strategy": "momentum"}
        for i in range(150)
    ]
    r = contract_env.client.get("/api/history/pnl?page=2&size=50")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 150
    assert data["total_pages"] == 3
    assert len(data["pairs"]) == 50
