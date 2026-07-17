"""contract 테스트용 fixture — FastAPI TestClient + 싱글톤 격리.

`TestClient(app)` 를 `with` 없이 사용하면 lifespan(token 발급/scheduler 등록/auto_start)
이 실행되지 않는다. 그 위에 `trading_scheduler` 싱글톤 상태와 DB CRUD 를
테스트마다 모킹/리셋한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient


@dataclass
class ContractCalls:
    insert_trade: list = field(default_factory=list)
    get_trades: list = field(default_factory=list)
    get_trade_pairs: list = field(default_factory=list)
    get_performance: list = field(default_factory=list)
    recompute: list = field(default_factory=list)
    save_params: list = field(default_factory=list)
    save_weights: list = field(default_factory=list)
    list_recommendations: list = field(default_factory=list)
    get_recommendation: list = field(default_factory=list)
    update_rec_status: list = field(default_factory=list)
    list_log_reports: list = field(default_factory=list)
    get_log_report: list = field(default_factory=list)
    generate_log_report: list = field(default_factory=list)
    place_order: list = field(default_factory=list)
    get_balance: list = field(default_factory=list)
    get_buyable: list = field(default_factory=list)
    get_logs: list = field(default_factory=list)


@dataclass
class ContractState:
    trades: list[dict] = field(default_factory=list)
    trade_pairs: list[dict] = field(default_factory=list)
    performance: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    log_reports: list[dict] = field(default_factory=list)
    logs: list[dict] = field(default_factory=list)
    auto_start_value: bool = False


@pytest.fixture
def contract_env(monkeypatch):
    """FastAPI 앱 + scheduler 싱글톤 격리 + DB CRUD 모킹."""
    # scheduler 싱글톤 상태 초기화 — 직전 테스트의 잔재 제거
    from src.engine.scheduler import trading_scheduler
    from src.engine.session import MarketBoard, session_tracker
    from src.engine import scanner

    trading_scheduler._running = False
    # 신규 추가된 전략은 마이그레이션상 enabled=false / weight=0 / 자금 0 으로 시작.
    # 컨트랙트 테스트의 4-전략 시나리오(`total_asset = 100M × 4 = 400M` 가정)를 유지하기 위해
    # 본 픽스처는 등록은 보존하되 자금 0 으로 격리한다 (운영 마이그레이션 011/018 컨벤션).
    _INACTIVE_STRATEGY_IDS = {"bull_flag_breakout", "vcp_breakout"}
    for s in trading_scheduler.registry.all():
        s.state.positions.clear()
        s.state.pending_buys.clear()
        s.state.sold_today.clear()
        s.state.daily_realized_pnl = 0
        s.state.total_investment = 0 if s.strategy_id in _INACTIVE_STRATEGY_IDS else 100_000_000
        s.state.buy_disabled = False
        s.state.buy_signals.clear()
        s.state.low_funds_tickers.clear()
        s.state.signal_count_today = 0
        s.state.order_attempt_today = 0
        s.state.fill_count_today = 0
    trading_scheduler.order_engine._selling.clear()
    trading_scheduler.order_engine._filled_qty.clear()
    trading_scheduler.order_engine._order_qty.clear()
    trading_scheduler.order_engine._order_strategy.clear()
    trading_scheduler.order_engine._order_ticker.clear()
    trading_scheduler.order_engine._pending_buy_orders.clear()

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prices", {})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(scanner, "ticker_market_info", {})
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))

    calls = ContractCalls()
    state = ContractState()

    # ---- scheduler.start / stop 모킹 (asyncio.create_task 가 실제 start 를 큐잉하므로) ----
    async def fake_start():
        trading_scheduler._running = True

    async def fake_stop():
        trading_scheduler._running = False

    monkeypatch.setattr(trading_scheduler, "start", fake_start)
    monkeypatch.setattr(trading_scheduler, "stop", fake_stop)

    # ---- DB CRUD 모킹 ----
    async def fake_get_trades(limit=20, offset=0, ticker=None, strategy=None):
        calls.get_trades.append({"limit": limit, "offset": offset, "ticker": ticker, "strategy": strategy})
        sliced = state.trades[offset:offset + limit]
        return sliced, len(state.trades)

    async def fake_get_trade_pairs(strategy=None, ticker=None):
        calls.get_trade_pairs.append({"strategy": strategy, "ticker": ticker})
        return list(state.trade_pairs)

    async def fake_insert_trade(record):
        calls.insert_trade.append(record)

    monkeypatch.setattr("src.routes.history.get_trades", fake_get_trades)
    monkeypatch.setattr("src.routes.history.get_trade_pairs", fake_get_trade_pairs)
    monkeypatch.setattr("src.routes.trading.insert_trade", fake_insert_trade, raising=False)

    async def fake_get_performance(days=30, strategy="total"):
        calls.get_performance.append({"days": days, "strategy": strategy})
        return list(state.performance)

    async def fake_get_latest_performance(strategy="total"):
        return state.performance[-1] if state.performance else None

    async def fake_recompute():
        calls.recompute.append({})
        return True

    monkeypatch.setattr("src.routes.performance.get_performance", fake_get_performance)
    monkeypatch.setattr(
        "src.routes.performance.get_latest_performance", fake_get_latest_performance
    )
    monkeypatch.setattr("src.routes.performance.recompute_from_trades", fake_recompute)

    # ---- balance 모킹 ----
    async def fake_get_balance():
        calls.get_balance.append({})
        from src.models.balance import AccountSummary

        summary = AccountSummary(
            deposit=10_000_000,
            stock_eval_amount=720_000,
            total_eval_amount=10_720_000,
            net_asset=10_720_000,
            purchase_total=700_000,
            eval_total=720_000,
            profit_loss_total=20_000,
        )
        return [], summary

    async def fake_get_buyable(ticker, price):
        calls.get_buyable.append({"ticker": ticker, "price": price})
        from src.models.balance import BuyableInfo

        return BuyableInfo(
            cash_available=10_000_000,
            max_buy_amount=10_000_000,
            max_buy_quantity=100,
        )

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)
    monkeypatch.setattr("src.routes.balance.get_buyable", fake_get_buyable)

    # ---- strategy_config (DB 영속화) — strategies.py 는 함수 내부에서 lazy import,
    # recommendations.py 는 모듈 상단 import. 두 곳 모두 모킹한다.
    async def fake_save_params(strategy_id, params):
        calls.save_params.append({"strategy_id": strategy_id, "params": params})

    async def fake_save_weights(weights):
        calls.save_weights.append({"weights": weights})

    import src.db.strategy_config as strategy_config_mod
    monkeypatch.setattr(strategy_config_mod, "save_params", fake_save_params, raising=False)
    monkeypatch.setattr(strategy_config_mod, "save_weights", fake_save_weights, raising=False)
    monkeypatch.setattr(
        "src.routes.recommendations.save_params", fake_save_params, raising=False,
    )
    monkeypatch.setattr(
        "src.routes.recommendations.save_weights", fake_save_weights, raising=False,
    )

    # ---- auto-start (사이클 M5 — system_config.get_auto_start/set_auto_start RDS 헬퍼) ----
    async def fake_get_auto_start():
        return bool(state.auto_start_value)

    async def fake_set_auto_start(enabled):
        state.auto_start_value = bool(enabled)

    import src.db.system_config as system_config_mod
    monkeypatch.setattr(system_config_mod, "get_auto_start", fake_get_auto_start)
    monkeypatch.setattr(system_config_mod, "set_auto_start", fake_set_auto_start)
    monkeypatch.setattr(
        "src.routes.strategies._system_config.get_auto_start", fake_get_auto_start,
    )
    monkeypatch.setattr(
        "src.routes.strategies._system_config.set_auto_start", fake_set_auto_start,
    )

    # ---- recommendations 모킹 ----
    async def fake_list_recommendations(days=30):
        calls.list_recommendations.append({"days": days})
        return list(state.recommendations)

    async def fake_get_recommendation(rec_id):
        calls.get_recommendation.append({"rec_id": rec_id})
        return next(
            (r for r in state.recommendations if r.get("id") == rec_id), None
        )

    async def fake_update_status(rec_id, status, applied_params=None, applied_weight=None):
        calls.update_rec_status.append({
            "rec_id": rec_id,
            "status": status,
            "applied_params": applied_params,
            "applied_weight": applied_weight,
        })
        for r in state.recommendations:
            if r.get("id") == rec_id:
                r["status"] = status
                if applied_params is not None:
                    r["applied_params"] = applied_params
                if applied_weight is not None:
                    r["applied_weight"] = applied_weight
                return r
        return None

    monkeypatch.setattr(
        "src.routes.recommendations.list_recommendations", fake_list_recommendations,
        raising=False,
    )
    monkeypatch.setattr(
        "src.routes.recommendations.get_recommendation", fake_get_recommendation,
        raising=False,
    )
    monkeypatch.setattr(
        "src.routes.recommendations.update_recommendation_status", fake_update_status,
        raising=False,
    )

    # ---- log_reports 모킹 ----
    async def fake_list_log_reports(days=30):
        calls.list_log_reports.append({"days": days})
        return list(state.log_reports)

    async def fake_get_log_report(target_date):
        calls.get_log_report.append({"target_date": target_date})
        return next(
            (r for r in state.log_reports if r.get("target_date") == target_date), None
        )

    async def fake_generate(*_args, **_kwargs):
        calls.generate_log_report.append({})
        return {"id": 999, "target_date": "2026-05-08", "summary": "ok"}

    monkeypatch.setattr(
        "src.routes.log_reports.list_log_reports", fake_list_log_reports, raising=False,
    )
    monkeypatch.setattr(
        "src.routes.log_reports.get_log_report", fake_get_log_report, raising=False,
    )
    monkeypatch.setattr(
        "src.routes.log_reports.generate_daily_log_report", fake_generate, raising=False,
    )

    # ---- logs ----
    # 사이클 6 (2026-05-17) — 신규 keyword(`from_date`/`to_date`/`page`/`size`) 흡수 + dict 응답.
    # 테스트는 `state.logs` 에 list 또는 dict 둘 다 넣을 수 있다.
    # - list 면 default total=len(items), total_pages=1(있으면)/0(없으면)
    # - dict 면 그대로 반환
    async def fake_get_logs(
        limit=50,
        log_level=None,
        *,
        from_date=None,
        to_date=None,
        page=1,
        size=None,
    ):
        eff_size = size if size is not None else limit
        calls.get_logs.append({
            "limit": limit,
            "log_level": log_level,
            "from_date": from_date,
            "to_date": to_date,
            "page": page,
            "size": eff_size,
        })
        raw = state.logs
        if isinstance(raw, dict):
            return {
                "items": list(raw.get("items", [])),
                "total": int(raw.get("total", 0)),
                "total_pages": int(raw.get("total_pages", 0)),
            }
        items = list(raw)
        total = len(items)
        total_pages = 1 if total else 0
        return {"items": items, "total": total, "total_pages": total_pages}

    monkeypatch.setattr("src.routes.logs.get_logs", fake_get_logs, raising=False)

    # ---- TestClient — lifespan 미실행 ----
    from src.main import app

    client = TestClient(app)

    yield SimpleNamespace(client=client, calls=calls, state=state, scheduler=trading_scheduler)
