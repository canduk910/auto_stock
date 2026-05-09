"""balance + performance 라우트 계약 — /api/balance/*, /api/performance/*"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def test_balance_returns_holdings_and_summary(contract_env):
    r = contract_env.client.get("/api/balance")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert "holdings" in data
    assert "summary" in data
    assert isinstance(data["holdings"], list)
    # AccountSummary pydantic dump 확인
    assert "deposit" in data["summary"]
    assert "net_asset" in data["summary"]
    assert "total_eval_amount" in data["summary"]


def test_balance_buyable_with_query_params(contract_env):
    r = contract_env.client.get("/api/balance/buyable?ticker=005930&price=70000")
    assert r.status_code == 200
    data = r.json()["data"]
    # BuyableInfo 필드 확인
    assert "max_buy_quantity" in data
    assert "cash_available" in data
    # fake fixture 가 호출 인자를 받았는지
    assert contract_env.calls.get_buyable[-1] == {"ticker": "005930", "price": 70000}


def test_performance_summary_when_no_records_returns_zero_envelope(contract_env):
    r = contract_env.client.get("/api/performance/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["total_days"] == 0
    assert data["latest_asset"] == 0


def test_performance_summary_with_records_aggregates(contract_env):
    contract_env.state.performance = [
        {"date": "2026-05-01", "daily_profit_rate": 0.5, "cumulative_return_rate": 1.0,
         "total_asset": 10_500_000},
        {"date": "2026-05-02", "daily_profit_rate": 1.0, "cumulative_return_rate": 2.0,
         "total_asset": 10_600_000},
    ]
    r = contract_env.client.get("/api/performance/summary")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_days"] == 2
    # avg = (0.5 + 1.0) / 2
    assert data["avg_daily_profit_rate"] == pytest.approx(0.75)
    # cumulative 는 latest 의 cumulative_return_rate
    assert data["total_profit_rate"] == 2.0
    assert data["latest_asset"] == 10_600_000


def test_performance_summary_strategy_filter_passes_through(contract_env):
    r = contract_env.client.get("/api/performance/summary?strategy=momentum")
    assert r.status_code == 200
    # fake_get_performance 호출 시 strategy='momentum' 으로 전달돼야 함
    assert contract_env.calls.get_performance[-1]["strategy"] == "momentum"


def test_performance_daily_returns_records_array(contract_env):
    contract_env.state.performance = [
        {"date": "2026-05-08", "daily_profit_rate": 0.5, "total_asset": 10_500_000}
    ]
    r = contract_env.client.get("/api/performance/daily?days=7")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    # query param 전달 확인
    assert contract_env.calls.get_performance[-1]["days"] == 7


def test_performance_recompute_returns_success(contract_env):
    r = contract_env.client.post("/api/performance/recompute")
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert len(contract_env.calls.recompute) == 1
