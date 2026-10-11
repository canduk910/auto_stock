"""cycle446 D-6 — `/api/balance` 「현재 AI 판단」 칸(`ai_verdict`) 계약.

🔴 「새 화면 칸은 값이 찍히는지까지 실측」 규약 — 「없음」(대상 전략 아님)과 「모름」(대상인데
아직 평가 없음)을 가른다. 실제 엔진 포지션으로 라우트를 통째로 호출한다.
"""
from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.contract


def _balance_fixture():
    from src.models.balance import AccountSummary, StockHolding

    holding = StockHolding(
        ticker="005930", name="삼성전자", quantity=1, sellable_quantity=1,
        avg_price=70_000.0, purchase_amount=70_000, current_price=71_000,
        eval_amount=71_000, eval_profit_loss=1_000, eval_profit_rate=1.4,
    )
    summary = AccountSummary(
        deposit=0, stock_eval_amount=0, total_eval_amount=0, net_asset=0,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )
    return holding, summary


def test_target_strategy_without_evaluation_is_no_evaluation(contract_env, monkeypatch):
    from src.engine.scheduler import trading_scheduler
    from src.engine.strategy_base import Position

    holding, summary = _balance_fixture()

    async def fake_get_balance():
        return [holding], summary

    async def fake_get_latest_verdicts(pairs):
        assert pairs == [("donchian_swing", "005930")]
        return {}

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)
    monkeypatch.setattr("src.routes.balance.get_latest_verdicts", fake_get_latest_verdicts)

    strategy = trading_scheduler.registry.get("donchian_swing")
    strategy.state.positions["005930"] = Position(
        ticker="005930", buy_price=70_000, quantity=1, order_no="ORD1",
        strategy_id="donchian_swing", buy_date=date(2026, 10, 1),
    )
    try:
        r = contract_env.client.get("/api/balance")
        assert r.status_code == 200
        by_ticker = {h["ticker"]: h for h in r.json()["data"]["holdings"]}
        assert by_ticker["005930"]["ai_verdict"] == {"status": "no_evaluation"}
    finally:
        strategy.state.positions.pop("005930", None)


def test_target_strategy_with_evaluation_is_available(contract_env, monkeypatch):
    from src.engine.scheduler import trading_scheduler
    from src.engine.strategy_base import Position

    holding, summary = _balance_fixture()

    async def fake_get_balance():
        return [holding], summary

    async def fake_get_latest_verdicts(pairs):
        return {
            ("kojiro", "005930"): {
                "action": "hold", "exit_score": 35, "bar_date": date(2026, 10, 13),
                "evaluated_at_iso": "2026-10-14T08:16:00.000000+09:00",
            },
        }

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)
    monkeypatch.setattr("src.routes.balance.get_latest_verdicts", fake_get_latest_verdicts)

    strategy = trading_scheduler.registry.get("kojiro")
    strategy.state.positions["005930"] = Position(
        ticker="005930", buy_price=70_000, quantity=1, order_no="ORD1",
        strategy_id="kojiro", buy_date=date(2026, 10, 1),
    )
    try:
        r = contract_env.client.get("/api/balance")
        assert r.status_code == 200
        by_ticker = {h["ticker"]: h for h in r.json()["data"]["holdings"]}
        verdict = by_ticker["005930"]["ai_verdict"]
        assert verdict["status"] == "available"
        assert verdict["action"] == "hold"
        assert verdict["exit_score"] == 35
        assert verdict["bar_date"] == "2026-10-13"
    finally:
        strategy.state.positions.pop("005930", None)


def test_non_target_strategy_is_not_applicable(contract_env, monkeypatch):
    from src.engine.scheduler import trading_scheduler
    from src.engine.strategy_base import Position

    holding, summary = _balance_fixture()

    async def fake_get_balance():
        return [holding], summary

    async def fake_get_latest_verdicts(pairs):
        assert pairs == [], "대상 전략이 아니면 조회 자체를 하지 않는다"
        return {}

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)
    monkeypatch.setattr("src.routes.balance.get_latest_verdicts", fake_get_latest_verdicts)

    strategy = trading_scheduler.registry.get("momentum")
    strategy.state.positions["005930"] = Position(
        ticker="005930", buy_price=70_000, quantity=1, order_no="ORD1",
        strategy_id="momentum", buy_date=date(2026, 10, 1),
    )
    try:
        r = contract_env.client.get("/api/balance")
        assert r.status_code == 200
        by_ticker = {h["ticker"]: h for h in r.json()["data"]["holdings"]}
        assert by_ticker["005930"]["ai_verdict"] == {"status": "not_applicable"}
    finally:
        strategy.state.positions.pop("005930", None)


def test_exit_ai_lookup_failure_is_graceful(contract_env, monkeypatch):
    """조회 자체가 예외를 내도 잔고는 그대로 나간다."""
    from src.engine.scheduler import trading_scheduler
    from src.engine.strategy_base import Position

    holding, summary = _balance_fixture()

    async def fake_get_balance():
        return [holding], summary

    async def fake_get_latest_verdicts(pairs):
        raise RuntimeError("db down")

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)
    monkeypatch.setattr("src.routes.balance.get_latest_verdicts", fake_get_latest_verdicts)

    strategy = trading_scheduler.registry.get("donchian_swing")
    strategy.state.positions["005930"] = Position(
        ticker="005930", buy_price=70_000, quantity=1, order_no="ORD1",
        strategy_id="donchian_swing", buy_date=date(2026, 10, 1),
    )
    try:
        r = contract_env.client.get("/api/balance")
        assert r.status_code == 200
        by_ticker = {h["ticker"]: h for h in r.json()["data"]["holdings"]}
        assert by_ticker["005930"]["ai_verdict"] == {"status": "no_evaluation"}
    finally:
        strategy.state.positions.pop("005930", None)
