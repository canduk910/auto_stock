"""cycle461 검수 보완(tester 「보완 필요」) — D2 · D1 · M4~M7 · L1.

| # | 계약 |
|---|---|
| D2 | 15분 동기화가 방금 팔린 보유(sold_today) · 매도 중(`_selling`) 종목을 unknown 으로 다시 입양·매도하지 않는다. 판정은 주인 조회 await **뒤**, 입양과 사이 await 0 |
| D1 | 비중 PUT 의 매수금액 하한선 검증도 unknown 을 건너뛴다(예산이 있는 상태에서) |
| M4 | 재판정이 주인에게 옮길 때 `high_since_buy`·`buy_date` 를 보존한다(포지션 재생성 금지) |
| M5 | 백업 청산은 `_selling` 종목을 쏘지 않는다 |
| M6 | 재판정의 await 뒤 포지션이 바뀌었으면 옮기지 않는다 |
| M7 | 부팅이 KIS 잔고 보완 뒤·PENDING 정리 앞에서 재판정을 부른다 |
| L1 | 주인 입양의 `buy_date` = 열린 왕복 첫 BUY 날짜, 모르면 오늘 + `[unknown_holding_buy_date_unknown]` |
"""
from __future__ import annotations

import inspect
import logging
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import unknown_holding_policy as uhp
from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position
from tests.unit.engine.test_cycle461_unknown_holding import (
    _KST, _at, _boot_scheduler, _hold, _holding, _registry, _summary,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def env(monkeypatch):
    import src.db.positions as _pos
    import src.db.trade_history as _th
    import src.engine.corporate_action_reconcile as _car
    import src.engine.scheduler as _sched

    uhp._ADOPT_SKIP_EMITTED.clear()
    reg = _registry()
    eng = OrderEngine(reg)
    eng.execute_sell = AsyncMock()
    holdings: list = []
    monkeypatch.setattr(_sched, "get_balance", AsyncMock(return_value=(holdings, SimpleNamespace())))
    monkeypatch.setattr(_th, "mark_pending_buys_completed", AsyncMock(return_value=0))
    save = AsyncMock()
    monkeypatch.setattr(_pos, "save_position", save)
    lookup = AsyncMock(return_value=("none", None))
    monkeypatch.setattr(_th, "get_open_roundtrip_owner", lookup)
    monkeypatch.setattr(_th, "get_open_roundtrip_first_buy_date",
                        AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(_car, "observe_mid_session_sync", AsyncMock())
    return SimpleNamespace(sched=_sched, reg=reg, eng=eng, holdings=holdings, save=save, lookup=lookup,
                           self=SimpleNamespace(registry=reg, order_engine=eng))


# ---------------------------------------------------------------------------
# D2
# ---------------------------------------------------------------------------
async def test_d2_sync_does_not_readopt_ticker_sold_during_scan(env, monkeypatch, caplog) -> None:
    import src.db.trade_history as _th
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    kojiro = env.reg.get("kojiro")
    kojiro.state.positions["555555"] = Position(ticker="555555", buy_price=10_000, quantity=3,
                                                order_no="1", strategy_id="kojiro")
    env.holdings.append(_holding("555555"))

    async def _close_during_await(ticker):  # 매도 체결통보가 이 await 동안 착지
        kojiro.state.positions.pop(ticker, None)
        kojiro.state.sold_today.add(ticker)
        return 0
    monkeypatch.setattr(_th, "mark_pending_buys_completed", AsyncMock(side_effect=_close_during_await))
    with caplog.at_level(logging.WARNING):
        await env.sched.TradingScheduler._sync_positions_from_balance(env.self)
    assert "555555" not in env.reg.get("unknown").state.positions
    env.save.assert_not_awaited()
    env.eng.execute_sell.assert_not_awaited()
    assert "[unknown_holding_adopt_skipped] ticker=555555 reason=sold_today" in caplog.text


async def test_d2_adopt_skips_ticker_in_selling(env, caplog) -> None:
    env.eng._selling.add("666666")
    with caplog.at_level(logging.WARNING):
        await uhp.adopt_balance_only_holding(env.reg, _holding("666666"), order_engine=env.eng, path="sync")
    assert "666666" not in env.reg.get("unknown").state.positions
    env.save.assert_not_awaited()
    assert "[unknown_holding_adopt_skipped] ticker=666666 reason=selling" in caplog.text


async def test_d2_skip_marker_once_per_day(env, caplog) -> None:
    env.eng._selling.add("666666")
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            await uhp.adopt_balance_only_holding(env.reg, _holding("666666"), order_engine=env.eng)
    assert caplog.text.count("[unknown_holding_adopt_skipped] ticker=666666") == 1


async def test_d2_check_runs_after_owner_lookup_await(env) -> None:
    kojiro = env.reg.get("kojiro")

    async def _lookup(ticker):
        kojiro.state.sold_today.add(ticker)  # 조회 await 동안 매도 완료
        return ("none", None)
    env.lookup.side_effect = _lookup
    await uhp.adopt_balance_only_holding(env.reg, _holding("777777"), order_engine=env.eng)
    assert "777777" not in env.reg.get("unknown").state.positions
    env.save.assert_not_awaited()


async def test_d2_held_during_lookup_await_is_not_duplicated(env) -> None:
    kojiro = env.reg.get("kojiro")

    async def _lookup(ticker):  # 조회 await 동안 매수 체결통보가 포지션을 세웠다
        kojiro.state.positions[ticker] = Position(ticker=ticker, buy_price=1, quantity=3,
                                                  order_no="9", strategy_id="kojiro")
        return ("none", None)
    env.lookup.side_effect = _lookup
    await uhp.adopt_balance_only_holding(env.reg, _holding("787878"), order_engine=env.eng)
    assert "787878" not in env.reg.get("unknown").state.positions


# ---------------------------------------------------------------------------
# D1
# ---------------------------------------------------------------------------
async def test_d1_put_weights_unknown_zero_with_budget_and_holdings_passes(monkeypatch) -> None:
    from src.routes import strategies as rs
    from src.routes.strategies import WeightsRequest
    import src.db.positions as _pos
    import src.db.strategy_config as _sc
    reg = _registry()
    reg.allocate_funds(5_000_000)
    _hold(reg, "111111", "no_owner", qty=30)  # 매수금액 300,000 — 하한선 검증이 실제로 돈다
    assert sum(s.state.total_investment for s in reg.enabled()) > 0
    monkeypatch.setattr(rs.trading_scheduler, "registry", reg)
    monkeypatch.setattr(_pos, "load_all", AsyncMock(return_value=[
        {"ticker": "111111", "strategy_id": "unknown"}]))
    monkeypatch.setattr(_sc, "save_weights", AsyncMock())
    resp = await rs.update_weights(WeightsRequest(weights={"unknown": 0.0, "kojiro": 0.5}))
    assert resp.success is True, resp.message
    assert reg.get("unknown").config.enabled is True


# ---------------------------------------------------------------------------
# M4 · M5 · M6 · M7
# ---------------------------------------------------------------------------
async def test_m4_rejudge_transfer_keeps_position_fields(env) -> None:
    u = _hold(env.reg, "444444", None)
    pos = u.state.positions["444444"]
    pos.high_since_buy = 12_345
    pos.buy_date = date(2026, 10, 1)
    env.lookup.return_value = ("found", "kojiro")
    await uhp.rejudge_unknown_positions(env.reg, env.eng)
    moved = env.reg.get("kojiro").state.positions["444444"]
    assert moved.high_since_buy == 12_345
    assert moved.buy_date == date(2026, 10, 1)
    assert env.save.await_args.kwargs["high_since_buy"] == 12_345
    assert env.save.await_args.kwargs["buy_date"] == date(2026, 10, 1)


async def test_m5_backup_fire_skips_selling(env, monkeypatch) -> None:
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    _hold(env.reg, "444444", "no_owner")
    env.eng._selling.add("444444")
    await uhp.backup_fire(env.reg, env.eng)
    env.eng.execute_sell.assert_not_awaited()


async def test_m6_rejudge_does_not_move_position_changed_during_await(env) -> None:
    u = _hold(env.reg, "444444", None)

    async def _lookup(ticker):
        u.state.positions[ticker] = Position(ticker=ticker, buy_price=1, quantity=1,
                                             order_no="", strategy_id="unknown")  # 바뀐 포지션
        return ("found", "kojiro")
    env.lookup.side_effect = _lookup
    await uhp.rejudge_unknown_positions(env.reg, env.eng)
    assert "444444" not in env.reg.get("kojiro").state.positions
    assert "444444" in u.state.positions
    env.save.assert_not_awaited()


def test_m7_boot_calls_rejudge_after_kis_supplement_before_pending() -> None:
    from src.engine import boot_manager
    src = inspect.getsource(boot_manager.boot)
    i_supp = src.index("_uhp.resolve_owner(")
    i_rejudge = src.index("_uhp.rejudge_unknown_positions(")
    i_pending = src.index("from src.db.trade_history import mark_pending_buys_completed")
    assert i_supp < i_rejudge < i_pending


async def test_m7_boot_rejudges_restored_unknown_position() -> None:
    from src.engine import boot_manager
    reg = _registry()
    sched = _boot_scheduler(reg)
    row = {"ticker": "888888", "ticker_name": "x", "strategy_id": "unknown", "buy_price": 10_000,
           "quantity": 3, "order_no": "", "buy_date": None, "high_since_buy": 0}
    with (
        patch("src.engine.boot_manager.token_manager") as tm,
        patch("src.engine.boot_manager.get_balance", new=AsyncMock(return_value=([_holding("888888")], _summary()))),
        patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(return_value=[])),
        patch("src.engine.boot_manager.write_log", new=AsyncMock()),
        patch("src.db.stock_master.count_active", new=AsyncMock(return_value=2768)),
        patch("src.db.positions.load_all", new=AsyncMock(return_value=[row])),
        patch("src.db.positions.delete_position", new=AsyncMock()),
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch("src.db.trade_history.get_open_roundtrip_owner", new=AsyncMock(return_value=("found", "kojiro"))),
        patch("src.db.trade_history.mark_pending_buys_completed", new=AsyncMock()),
        patch("src.db.trade_history.get_today_buys_ticker_strategy", new=AsyncMock(return_value=[])),
    ):
        tm.get_token = AsyncMock()
        await boot_manager.boot(sched)
    assert "888888" in reg.get("kojiro").state.positions
    assert "888888" not in reg.get("unknown").state.positions


# ---------------------------------------------------------------------------
# L1
# ---------------------------------------------------------------------------
async def test_l1_owner_adoption_uses_open_roundtrip_first_buy_date(env, monkeypatch) -> None:
    import src.db.trade_history as _th
    env.lookup.return_value = ("found", "kojiro")
    monkeypatch.setattr(_th, "get_open_roundtrip_first_buy_date",
                        AsyncMock(return_value=date(2026, 10, 7)), raising=False)
    await uhp.adopt_balance_only_holding(env.reg, _holding("999999"), order_engine=env.eng)
    assert env.reg.get("kojiro").state.positions["999999"].buy_date == date(2026, 10, 7)
    assert env.save.await_args.kwargs["buy_date"] == date(2026, 10, 7)


async def test_l1_owner_adoption_buy_date_unknown_falls_back_to_today(env, monkeypatch, caplog) -> None:
    import src.db.trade_history as _th
    env.lookup.return_value = ("found", "kojiro")
    monkeypatch.setattr(_th, "get_open_roundtrip_first_buy_date",
                        AsyncMock(side_effect=RuntimeError("db")), raising=False)
    with caplog.at_level(logging.WARNING):
        await uhp.adopt_balance_only_holding(env.reg, _holding("999998"), order_engine=env.eng)
    assert env.reg.get("kojiro").state.positions["999998"].buy_date == datetime.now(_KST).date()
    assert "[unknown_holding_buy_date_unknown] ticker=999998" in caplog.text


async def test_l1_db_first_buy_date_after_last_sell(monkeypatch) -> None:
    from src.db import pg, trade_history as th
    monkeypatch.setattr(pg, "fetchval", AsyncMock(return_value=datetime(2026, 10, 7, 9, 5, tzinfo=_KST)))
    assert await th.get_open_roundtrip_first_buy_date("111111") == date(2026, 10, 7)
    monkeypatch.setattr(pg, "fetchval", AsyncMock(return_value=None))
    assert await th.get_open_roundtrip_first_buy_date("111111") is None
