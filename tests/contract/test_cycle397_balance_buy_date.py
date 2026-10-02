"""cycle397 — `/api/balance` 매입일(최초 매입일) 라우트 계약.

사용자 요청(2026-10-02) = "잔고내역에 매입일을 표기하자. 혹시 여러날짜에 걸쳐
매수했다면(피라미딩으로 인해) 최초매입일로 표시."

🔴 「새 화면 칸은 값이 찍히는지까지 실측」 규약 — 2026-09-21 손절가 칸이 검사
초록·배포 성공인데도 보유 9건 전부 빈 칸이었다. 그 재발을 막기 위해, 엔진
포지션이 실제로 있는 보유 11종목 모양으로 라우트를 통째로 호출해 **칸이 비지
않는다**를 직접 잰다(호출부는 실제 `/api/balance` 와 동일 — `trading_scheduler`
싱글톤 레지스트리를 그대로 쓴다).
"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.contract


def _tickers(n: int) -> list[str]:
    # 자리수 6 고정 — balance 응답의 종목코드 형식 계약(루트 CLAUDE.md).
    return [f"{100000 + i:06d}" for i in range(n)]


def test_eleven_held_tickers_all_have_buy_date(contract_env, monkeypatch):
    """엔진 포지션이 있는 보유 11종목 — 매입일 칸이 하나도 비지 않는다."""
    from src.models.balance import AccountSummary, StockHolding

    tickers = _tickers(11)
    today = date(2026, 10, 2)

    holdings = [
        StockHolding(
            ticker=t, name=f"종목{i}", quantity=1, sellable_quantity=1,
            avg_price=10_000.0, purchase_amount=10_000, current_price=10_500,
            eval_amount=10_500, eval_profit_loss=500, eval_profit_rate=5.0,
        )
        for i, t in enumerate(tickers)
    ]
    summary = AccountSummary(
        deposit=0, stock_eval_amount=0, total_eval_amount=0, net_asset=0,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )

    async def fake_get_balance():
        return holdings, summary

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)

    # 11 종목을 전략 registry 의 첫 전략 하나에 실제 Position 으로 심는다 —
    # 라우트가 실제로 도는 경로(resolve_engine_buy_dates → registry.all())를 그대로 탄다.
    from src.engine.scheduler import trading_scheduler
    from src.engine.strategy_base import Position

    strategy = trading_scheduler.registry.all()[0]
    for i, t in enumerate(tickers):
        strategy.state.positions[t] = Position(
            ticker=t, buy_price=10_000, quantity=1, order_no=f"ORD{i}",
            strategy_id=strategy.strategy_id, buy_date=today - timedelta(days=i),
        )

    try:
        r = contract_env.client.get("/api/balance")
        assert r.status_code == 200
        body = r.json()["data"]["holdings"]
        by_ticker = {h["ticker"]: h for h in body}
        assert len(by_ticker) == 11
        for i, t in enumerate(tickers):
            expected = (today - timedelta(days=i)).isoformat()
            assert by_ticker[t]["buy_date"] == expected, (
                f"{t} 매입일 칸이 비어 있다: {by_ticker[t]['buy_date']!r}"
            )
    finally:
        for t in tickers:
            strategy.state.positions.pop(t, None)


def test_db_fallback_used_when_engine_has_no_position(contract_env, monkeypatch):
    """재시작 직후(엔진 포지션 복구 전) — DB `positions.buy_date` 로 채운다."""
    from src.models.balance import AccountSummary, StockHolding

    holding = StockHolding(
        ticker="900110", name="수동보유", quantity=1, sellable_quantity=1,
        avg_price=1_000.0, purchase_amount=1_000, current_price=1_100,
        eval_amount=1_100, eval_profit_loss=100, eval_profit_rate=10.0,
    )
    summary = AccountSummary(
        deposit=0, stock_eval_amount=0, total_eval_amount=0, net_asset=0,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )

    async def fake_get_balance():
        return [holding], summary

    async def fake_get_buy_dates(tickers):
        assert tickers == ["900110"]
        return {"900110": date(2026, 8, 1)}

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)
    monkeypatch.setattr("src.db.positions.get_buy_dates", fake_get_buy_dates)

    r = contract_env.client.get("/api/balance")
    assert r.status_code == 200
    by_ticker = {h["ticker"]: h for h in r.json()["data"]["holdings"]}
    assert by_ticker["900110"]["buy_date"] == "2026-08-01"


def test_db_query_failure_is_graceful_and_leaves_blank(contract_env, monkeypatch):
    """DB 조회 예외(엔진에 포지션이 없을 때) — 잔고 자체는 나가고 그 칸만 None."""
    from src.models.balance import AccountSummary, StockHolding

    holding = StockHolding(
        ticker="999999", name="조회실패종목", quantity=1, sellable_quantity=1,
        avg_price=1_000.0, purchase_amount=1_000, current_price=1_100,
        eval_amount=1_100, eval_profit_loss=100, eval_profit_rate=10.0,
    )
    summary = AccountSummary(
        deposit=0, stock_eval_amount=0, total_eval_amount=0, net_asset=0,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )

    async def fake_get_balance():
        return [holding], summary

    async def fake_get_buy_dates(tickers):
        raise RuntimeError("DB down")

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)
    monkeypatch.setattr("src.db.positions.get_buy_dates", fake_get_buy_dates)

    r = contract_env.client.get("/api/balance")
    assert r.status_code == 200
    by_ticker = {h["ticker"]: h for h in r.json()["data"]["holdings"]}
    assert by_ticker["999999"]["buy_date"] is None


def test_engine_value_wins_and_is_earlier_than_stale_db_value(contract_env, monkeypatch):
    """엔진·DB 둘 다 값이 있고 엔진이 더 이르면 엔진 값 — 「최초 매입일」 규약."""
    from src.models.balance import AccountSummary, StockHolding
    from src.engine.scheduler import trading_scheduler
    from src.engine.strategy_base import Position

    holding = StockHolding(
        ticker="005930", name="삼성전자", quantity=1, sellable_quantity=1,
        avg_price=70_000.0, purchase_amount=70_000, current_price=71_000,
        eval_amount=71_000, eval_profit_loss=1_000, eval_profit_rate=1.4,
    )
    summary = AccountSummary(
        deposit=0, stock_eval_amount=0, total_eval_amount=0, net_asset=0,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )

    async def fake_get_balance():
        return [holding], summary

    async def fake_get_buy_dates(tickers):
        return {"005930": date(2026, 9, 25)}  # DB 가 더 늦은(오염된) 값

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)
    monkeypatch.setattr("src.db.positions.get_buy_dates", fake_get_buy_dates)

    strategy = trading_scheduler.registry.all()[0]
    strategy.state.positions["005930"] = Position(
        ticker="005930", buy_price=70_000, quantity=1, order_no="ORD1",
        strategy_id=strategy.strategy_id, buy_date=date(2026, 9, 10),
    )
    try:
        r = contract_env.client.get("/api/balance")
        assert r.status_code == 200
        by_ticker = {h["ticker"]: h for h in r.json()["data"]["holdings"]}
        assert by_ticker["005930"]["buy_date"] == "2026-09-10"
    finally:
        strategy.state.positions.pop("005930", None)
