"""cycle461 — ⑦-F1 안 U: 출처 모를 보유를 전용 전략 `unknown`(화면 「비식별 보유」)에 배정.

사용자 결정 2026-10-10(① 안 U · ② 계좌 자동매매 전용 · ③ 권리 입고도 즉시 매도 · ④ 주인 꺼짐 =
같은 청산 경로(`reason=owner_disabled`) · ⑤ `observe` 로 시작) + 2026-10-15 「구현 시작하자」.
자문 = `_workspace/domain_consult/2026-10-10_f1_unknown_holding_liquidation.md` 회귀 시나리오 R1~R21.

| # | 계약 |
|---|---|
| R1 | 열린 왕복 주인이 켜진 전략 → 그 전략이 맡는다 |
| R2 | 열린 왕복 없음 → `unknown`(no_owner) · `save_position(unknown)` · 부팅 발사 0 |
| R3·R11·R12 | 창(09:00:30~15:28) 밖 → NONE |
| R4 | 창 안 — `enforce` 는 `UNKNOWN_EXIT` 1회 · `observe` 는 기록만 |
| R5 | DB 조회 실패 → 판정 보류(`lookup_failed`) · momentum 폴백 0 · 팔지 않는다 |
| R6 | 마지막 BUY < 마지막 SELL(끝난 왕복) → `unknown` |
| R7 | 주인 꺼짐 → `unknown`(owner_disabled) — 같은 청산 경로 |
| R8' | 권리 입고(열린 왕복 없음) → `unknown`(no_owner), CTRGA 를 보지 않는다(사용자 결정 ③) |
| R13 | 종목당 하루 3회 · 5분 간격 · 다 쓰면 `[unknown_exit_giveup]` CRITICAL |
| R15·R16 | 비중 PUT: `unknown` > 0 은 422 · `unknown` 0 은 보유가 있어도 통과 · 켜짐 유지 |
| R17 | AI 자문이 `unknown` 을 다루지 않는다 |
| R20 | 재시작 — 사유 없는 `unknown` 보유는 팔지 않고 재판정한다 |
| R21 | 섀도·일반 전략의 비중 0 규칙은 그대로 |
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import unknown_holding_policy as uhp
from src.engine.order_engine import OrderEngine
from src.engine.strategies.unknown import UnknownHoldingStrategy, normalize_exit_mode
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


def _at(h: int, m: int, s: int = 0, *, day: int = 15) -> datetime:
    return datetime(2026, 10, day, h, m, s, tzinfo=_KST)


class _Strat(StrategyBase):
    def __init__(self, sid: str, *, enabled: bool = True, weight: float = 0.5, params=None) -> None:
        super().__init__(StrategyConfig(strategy_id=sid, name=sid, enabled=enabled, weight=weight,
                                        params=dict(params or {"exchange": "KRX"})))

    async def prepare(self, *, as_of=None) -> None:  # pragma: no cover
        return None

    def check_buy_signal(self, ticker, current_price, open_price):  # pragma: no cover
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):  # pragma: no cover
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:  # pragma: no cover
        return 0


def _unknown(mode: str | None = "enforce") -> UnknownHoldingStrategy:
    params = {} if mode is None else {"unknown_exit_mode": mode}
    return UnknownHoldingStrategy(StrategyConfig(
        strategy_id="unknown", name="비식별 보유", enabled=True, weight=0.0, params=params,
    ))


def _registry(*, unknown_mode: str | None = "enforce", ltv_enabled: bool = False) -> StrategyRegistry:
    reg = StrategyRegistry()
    reg.register(_Strat("momentum", enabled=False, weight=0.0))
    reg.register(_Strat("long_tail_volatility", enabled=ltv_enabled, weight=0.0))
    reg.register(_Strat("kojiro", enabled=True, weight=0.5))
    reg.register(_unknown(unknown_mode))
    return reg


def _hold(reg: StrategyRegistry, ticker: str, reason: str | None, qty: int = 3) -> UnknownHoldingStrategy:
    u = reg.get("unknown")
    u.state.positions[ticker] = Position(ticker=ticker, buy_price=10_000, quantity=qty,
                                         order_no="", strategy_id="unknown")
    if reason is not None:
        u._reasons[ticker] = reason
    return u


def _fetchrow(*, buy_strategy=None, buy_ts=None, sell_ts=None):
    return AsyncMock(return_value={"buy_strategy": buy_strategy, "buy_ts": buy_ts, "sell_ts": sell_ts})


# ---------------------------------------------------------------------------
# DB — 열린 왕복 주인 조회
# ---------------------------------------------------------------------------
async def test_db_open_roundtrip_found_when_last_buy_after_last_sell(monkeypatch) -> None:
    from src.db import pg, trade_history as th
    monkeypatch.setattr(pg, "fetchrow", _fetchrow(
        buy_strategy="kojiro", buy_ts=_at(10, 0), sell_ts=_at(9, 0)))
    assert await th.get_open_roundtrip_owner("111111") == ("found", "kojiro")


async def test_r6_db_closed_roundtrip_is_none(monkeypatch) -> None:
    from src.db import pg, trade_history as th
    monkeypatch.setattr(pg, "fetchrow", _fetchrow(
        buy_strategy="kojiro", buy_ts=_at(9, 0, day=1), sell_ts=_at(10, 0, day=2)))
    assert await th.get_open_roundtrip_owner("111111") == ("none", None)


async def test_db_no_buy_is_none(monkeypatch) -> None:
    from src.db import pg, trade_history as th
    monkeypatch.setattr(pg, "fetchrow", _fetchrow())
    assert await th.get_open_roundtrip_owner("111111") == ("none", None)


async def test_db_exception_propagates(monkeypatch) -> None:
    from src.db import pg, trade_history as th
    monkeypatch.setattr(pg, "fetchrow", AsyncMock(side_effect=RuntimeError("db down")))
    with pytest.raises(RuntimeError):
        await th.get_open_roundtrip_owner("111111")


# ---------------------------------------------------------------------------
# 판정 (순수)
# ---------------------------------------------------------------------------
def test_classify_owner_table() -> None:
    reg = _registry(ltv_enabled=False)
    assert uhp.classify_owner("found", "kojiro", reg) == ("kojiro", "owner")             # R1
    assert uhp.classify_owner("found", "long_tail_volatility", reg) == ("unknown", "owner_disabled")  # R7
    assert uhp.classify_owner("found", "momentum", reg) == ("unknown", "owner_disabled")
    assert uhp.classify_owner("found", "deleted_sid", reg) == ("unknown", "owner_unregistered")
    assert uhp.classify_owner("found", "unknown", reg) == ("unknown", "owner_unregistered")
    assert uhp.classify_owner("none", None, reg) == ("unknown", "no_owner")               # R2·R6
    assert uhp.classify_owner("error", None, reg) == ("unknown", "lookup_failed")         # R5


async def test_r5_resolve_owner_lookup_failure_is_held_not_momentum(monkeypatch, caplog) -> None:
    from src.db import trade_history as th
    monkeypatch.setattr(th, "get_open_roundtrip_owner", AsyncMock(side_effect=RuntimeError("x")))
    reg = _registry()
    with caplog.at_level(logging.ERROR):
        sid, reason, owner = await uhp.resolve_owner(reg, "111111")
    assert (sid, reason, owner) == ("unknown", "lookup_failed", None)
    assert "[unknown_holding_lookup_failed]" in caplog.text


# ---------------------------------------------------------------------------
# 전략 — 매수 없음 · 항상 켜짐 · 청산 창·모드·상한
# ---------------------------------------------------------------------------
def test_buy_signal_is_always_none() -> None:
    u = _unknown()
    for t in ("005930", "000660", "111111"):
        assert u.check_buy_signal(t, 70_000, 69_000) == Signal.NONE
    assert u.calc_buy_quantity(10_000, "005930") == 0


def test_always_enabled_even_when_assigned_false() -> None:
    u = _unknown()
    u.config.enabled = False
    assert u.config.enabled is True


@pytest.mark.parametrize("raw,expected", [
    (None, "observe"), ("", "observe"), ("enforc", "observe"), (1, "observe"),
    ("observe", "observe"), ("ENFORCE", "enforce"), (" off ", "off"),
])
def test_mode_missing_or_typo_is_observe(raw, expected) -> None:
    assert normalize_exit_mode(raw) == expected


def test_default_mode_is_observe() -> None:
    assert UnknownHoldingStrategy.DEFAULT_PARAMS["unknown_exit_mode"] == "observe"


@pytest.mark.parametrize("now", [_at(9, 0, 10), _at(8, 10), _at(15, 28), _at(16, 30), _at(19, 50)])
def test_r3_r11_out_of_window_is_none(monkeypatch, now) -> None:
    reg = _registry()
    u = _hold(reg, "111111", "no_owner")
    monkeypatch.setattr(uhp, "now_kst", lambda: now)
    assert u.check_exit_signal("111111", 10_000, 10_000) == Signal.NONE


def test_r4_enforce_fires_once_in_window(monkeypatch, caplog) -> None:
    reg = _registry()
    u = _hold(reg, "111111", "no_owner")
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(9, 0, 31))
    with caplog.at_level(logging.WARNING):
        assert u.check_exit_signal("111111", 10_000, 10_000) == Signal.UNKNOWN_EXIT
        # 같은 순간 다시 — 간격(300초) 안이라 NONE
        assert u.check_exit_signal("111111", 10_000, 10_000) == Signal.NONE
    assert "[unknown_exit_fire] ticker=111111 reason=no_owner" in caplog.text


def test_r4_observe_records_only(monkeypatch, caplog) -> None:
    reg = _registry(unknown_mode="observe")
    u = _hold(reg, "111111", "no_owner")
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    with caplog.at_level(logging.WARNING):
        assert u.check_exit_signal("111111", 10_000, 10_000) == Signal.NONE
        assert u.check_exit_signal("111111", 10_000, 10_000) == Signal.NONE
    assert caplog.text.count("[unknown_exit_would_fire]") == 1


def test_mode_off_neither_fires_nor_records(monkeypatch, caplog) -> None:
    reg = _registry(unknown_mode="off")
    u = _hold(reg, "111111", "no_owner")
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    with caplog.at_level(logging.DEBUG):
        assert u.check_exit_signal("111111", 10_000, 10_000) == Signal.NONE
    assert "[unknown_exit" not in caplog.text


@pytest.mark.parametrize("reason", ["lookup_failed", None])
def test_r5_r20_held_or_unjudged_never_fires(monkeypatch, reason) -> None:
    reg = _registry()
    u = _hold(reg, "111111", reason)
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    assert u.check_exit_signal("111111", 10_000, 10_000) == Signal.NONE


def test_r7_owner_disabled_uses_same_exit_path(monkeypatch) -> None:
    reg = _registry()
    u = _hold(reg, "111111", "owner_disabled")
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    assert u.check_exit_signal("111111", 10_000, 10_000) == Signal.UNKNOWN_EXIT


def test_r13_three_fires_per_day_then_giveup(monkeypatch, caplog) -> None:
    reg = _registry()
    u = _hold(reg, "111111", "no_owner")
    t = [_at(9, 1)]
    monkeypatch.setattr(uhp, "now_kst", lambda: t[0])
    fired = 0
    with caplog.at_level(logging.WARNING):
        for _ in range(6):
            if u.check_exit_signal("111111", 10_000, 10_000) == Signal.UNKNOWN_EXIT:
                fired += 1
            t[0] = t[0] + timedelta(seconds=301)
    assert fired == 3
    giveups = [r for r in caplog.records if "[unknown_exit_giveup]" in r.getMessage()]
    assert len(giveups) == 1 and giveups[0].levelno == logging.CRITICAL
    # 다음 날 다시
    t[0] = _at(9, 1, day=16)
    assert u.check_exit_signal("111111", 10_000, 10_000) == Signal.UNKNOWN_EXIT


# ---------------------------------------------------------------------------
# 부팅 KIS 잔고 보완 복구
# ---------------------------------------------------------------------------
def _holding(ticker: str, qty: int = 3):
    from src.models.balance import StockHolding
    return StockHolding(ticker=ticker, name=f"종목{ticker}", quantity=qty, sellable_quantity=qty,
                        avg_price=10_000.0, purchase_amount=10_000 * qty, current_price=10_000,
                        eval_amount=10_000 * qty, eval_profit_loss=0, eval_profit_rate=0.0)


def _summary():
    from src.models.balance import AccountSummary
    return AccountSummary(deposit=0, stock_eval_amount=0, total_eval_amount=1_000_000,
                          net_asset=1_000_000, purchase_total=0, eval_total=0, profit_loss_total=0)


def _boot_scheduler(reg: StrategyRegistry) -> MagicMock:
    s = MagicMock()
    s.registry = reg
    s._preissue_all_tokens = AsyncMock()
    s._load_strategy_config = AsyncMock()
    s._refresh_market_regime_and_persist = AsyncMock()
    s._resolve_cash_usage_ratio = AsyncMock(return_value=1.0)
    s._sync_orders_to_db = AsyncMock()
    s._eager_refresh_stock_master_for_held_positions = AsyncMock()
    s.order_engine = OrderEngine(reg)
    s.order_engine.execute_sell = AsyncMock()
    s._pending_next_day_clear = set()
    return s


async def _run_boot(reg, holdings, owner_lookup, *, save=None, ctrga=None):
    from src.engine import boot_manager
    save = save or AsyncMock()
    ctrga = ctrga or AsyncMock(side_effect=AssertionError("CTRGA 를 조회하면 안 된다(사용자 결정 ③)"))
    sched = _boot_scheduler(reg)
    with (
        patch("src.engine.boot_manager.token_manager") as tm,
        patch("src.engine.boot_manager.get_balance", new=AsyncMock(return_value=(holdings, _summary()))),
        patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(return_value=[])),
        patch("src.engine.boot_manager.write_log", new=AsyncMock()),
        patch("src.db.stock_master.count_active", new=AsyncMock(return_value=2768)),
        patch("src.db.positions.load_all", new=AsyncMock(return_value=[])),
        patch("src.db.positions.delete_position", new=AsyncMock()),
        patch("src.db.positions.save_position", new=save),
        patch("src.db.trade_history.get_open_roundtrip_owner", new=owner_lookup),
        patch("src.db.trade_history.mark_pending_buys_completed", new=AsyncMock()),
        patch("src.db.trade_history.get_today_buys_ticker_strategy", new=AsyncMock(return_value=[])),
        patch("src.api.corporate_actions.fetch_period_rights", new=ctrga, create=True),
    ):
        tm.get_token = AsyncMock()
        await boot_manager.boot(sched)
    return sched, save


async def test_r2_boot_no_owner_goes_to_unknown_and_persists() -> None:
    reg = _registry()
    sched, save = await _run_boot(reg, [_holding("111111")], AsyncMock(return_value=("none", None)))
    u = reg.get("unknown")
    assert "111111" in u.state.positions
    assert u._reasons["111111"] == "no_owner"
    assert not reg.get("momentum").state.positions
    saved = [c.kwargs for c in save.await_args_list if c.kwargs.get("ticker") == "111111"]
    assert saved and saved[-1]["strategy_id"] == "unknown"
    sched.order_engine.execute_sell.assert_not_awaited()


async def test_r8_rights_receipt_goes_to_unknown_without_ctrga() -> None:
    """권리 입고(회사분할 신주 등)는 열린 왕복이 없다 → no_owner, 즉시 매도 대상(사용자 결정 ③)."""
    reg = _registry()
    await _run_boot(reg, [_holding("222222")], AsyncMock(return_value=("none", None)))
    assert reg.get("unknown")._reasons["222222"] == "no_owner"


async def test_r1_boot_open_roundtrip_owner_enabled() -> None:
    reg = _registry()
    await _run_boot(reg, [_holding("111111")], AsyncMock(return_value=("found", "kojiro")))
    assert "111111" in reg.get("kojiro").state.positions
    assert "111111" not in reg.get("unknown").state.positions


async def test_r7_boot_owner_disabled_goes_to_unknown() -> None:
    reg = _registry(ltv_enabled=False)
    await _run_boot(reg, [_holding("111111")], AsyncMock(return_value=("found", "long_tail_volatility")))
    assert reg.get("unknown")._reasons["111111"] == "owner_disabled"
    assert not reg.get("long_tail_volatility").state.positions


async def test_r5_boot_lookup_failure_held_no_momentum() -> None:
    reg = _registry()
    await _run_boot(reg, [_holding("111111")], AsyncMock(side_effect=RuntimeError("db")))
    assert reg.get("unknown")._reasons["111111"] == "lookup_failed"
    assert not reg.get("momentum").state.positions


# ---------------------------------------------------------------------------
# 15분 잔고 동기화
# ---------------------------------------------------------------------------
@pytest.fixture
def sync_env(monkeypatch):
    import src.db.positions as _pos
    import src.db.trade_history as _th
    import src.engine.scheduler as _sched

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
    import src.engine.corporate_action_reconcile as _car
    monkeypatch.setattr(_car, "observe_mid_session_sync", AsyncMock())
    return SimpleNamespace(sched=_sched, reg=reg, eng=eng, holdings=holdings, save=save, lookup=lookup,
                           self=SimpleNamespace(registry=reg, order_engine=eng))


async def _sync(env) -> None:
    await env.sched.TradingScheduler._sync_positions_from_balance(env.self)


async def test_sync_adopts_to_unknown_and_saves(sync_env, monkeypatch) -> None:
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(8, 30))  # 창 밖 — 발사 0
    sync_env.holdings.append(_holding("333333"))
    await _sync(sync_env)
    u = sync_env.reg.get("unknown")
    assert u._reasons["333333"] == "no_owner"
    assert sync_env.save.await_args.kwargs["strategy_id"] == "unknown"
    assert not sync_env.reg.get("momentum").state.positions
    sync_env.eng.execute_sell.assert_not_awaited()


async def test_sync_backup_fire_in_window_enforce(sync_env, monkeypatch) -> None:
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    sync_env.holdings.append(_holding("333333"))
    await _sync(sync_env)
    sync_env.eng.execute_sell.assert_awaited_once_with("333333", Signal.UNKNOWN_EXIT, "unknown")


async def test_sync_backup_fire_observe_sends_nothing(sync_env, monkeypatch) -> None:
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    sync_env.reg.get("unknown").config.params["unknown_exit_mode"] = "observe"
    sync_env.holdings.append(_holding("333333"))
    await _sync(sync_env)
    sync_env.eng.execute_sell.assert_not_awaited()


async def test_sync_does_not_readopt_held_ticker(sync_env, monkeypatch) -> None:
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(8, 30))
    _hold(sync_env.reg, "333333", "no_owner")
    sync_env.holdings.append(_holding("333333"))
    await _sync(sync_env)
    sync_env.save.assert_not_awaited()


async def test_r20_rejudge_restored_unknown_to_enabled_owner(sync_env, monkeypatch) -> None:
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    _hold(sync_env.reg, "444444", None)  # 재시작으로 사유를 잃은 보유
    sync_env.lookup.return_value = ("found", "kojiro")
    await uhp.sync_pass(sync_env.reg, sync_env.eng)
    assert "444444" in sync_env.reg.get("kojiro").state.positions
    assert sync_env.reg.get("kojiro").state.positions["444444"].strategy_id == "kojiro"
    assert "444444" not in sync_env.reg.get("unknown").state.positions
    assert sync_env.save.await_args.kwargs["strategy_id"] == "kojiro"
    sync_env.eng.execute_sell.assert_not_awaited()


async def test_r20_rejudge_restored_unknown_no_owner_becomes_sellable(sync_env, monkeypatch) -> None:
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    _hold(sync_env.reg, "444444", None)
    await uhp.sync_pass(sync_env.reg, sync_env.eng)
    assert sync_env.reg.get("unknown")._reasons["444444"] == "no_owner"
    sync_env.eng.execute_sell.assert_awaited_once_with("444444", Signal.UNKNOWN_EXIT, "unknown")


async def test_rejudge_lookup_failure_stays_held(sync_env, monkeypatch) -> None:
    monkeypatch.setattr(uhp, "now_kst", lambda: _at(11, 0))
    _hold(sync_env.reg, "444444", "lookup_failed")
    sync_env.lookup.side_effect = RuntimeError("db")
    await uhp.sync_pass(sync_env.reg, sync_env.eng)
    assert sync_env.reg.get("unknown")._reasons["444444"] == "lookup_failed"
    sync_env.eng.execute_sell.assert_not_awaited()


# ---------------------------------------------------------------------------
# 비중 — 항상 켜짐 · 비중 > 0 거부
# ---------------------------------------------------------------------------
def test_r16_r21_update_weights_keeps_unknown_enabled() -> None:
    reg = _registry()
    reg.register(_Strat("vcp_breakout", enabled=True, weight=0.3))
    reg.update_weights({"unknown": 0.0, "vcp_breakout": 0.0})
    assert reg.get("unknown").config.enabled is True
    assert reg.get("vcp_breakout").config.enabled is False   # 일반 전략 비중 0 = 꺼짐(그대로)


async def test_r15_put_weights_unknown_positive_rejected(monkeypatch) -> None:
    from fastapi import HTTPException
    from src.routes import strategies as rs
    from src.routes.strategies import WeightsRequest
    reg = _registry()
    monkeypatch.setattr(rs.trading_scheduler, "registry", reg)
    with pytest.raises(HTTPException) as ei:
        await rs.update_weights(WeightsRequest(weights={"unknown": 0.1, "kojiro": 0.5}))
    assert ei.value.status_code == 422


async def test_r16_put_weights_unknown_zero_with_holdings_passes(monkeypatch) -> None:
    from src.routes import strategies as rs
    from src.routes.strategies import WeightsRequest
    import src.db.positions as _pos
    import src.db.strategy_config as _sc
    reg = _registry()
    _hold(reg, "111111", "no_owner")
    monkeypatch.setattr(rs.trading_scheduler, "registry", reg)
    monkeypatch.setattr(_pos, "load_all", AsyncMock(return_value=[
        {"ticker": "111111", "strategy_id": "unknown"}]))
    save_weights = AsyncMock()
    monkeypatch.setattr(_sc, "save_weights", save_weights)
    resp = await rs.update_weights(WeightsRequest(weights={"unknown": 0.0, "kojiro": 0.5}))
    assert resp.success is True, resp.message
    assert reg.get("unknown").config.enabled is True
    assert "unknown" in save_weights.await_args.kwargs.get("keep_enabled", set())


# ---------------------------------------------------------------------------
# 편입 금지 · AI 자문 제외 · 명부
# ---------------------------------------------------------------------------
def test_mode_key_not_auto_tunable() -> None:
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES
    assert "unknown_exit_mode" not in PARAM_RANGES
    assert "unknown_exit_mode" not in INT_PARAMS


def test_r17_recommendation_engine_skips_unknown() -> None:
    import inspect
    from src.engine import recommendation_engine as re_
    src = inspect.getsource(re_.generate_recommendations)
    assert "is_unknown_strategy_id" in src


def test_manifest_registers_unknown_last_weight_zero_enabled() -> None:
    from src.engine.strategy_manifest import STRATEGY_MANIFEST
    last = STRATEGY_MANIFEST[-1]
    assert (last.strategy_id, last.name, last.enabled, last.weight) == ("unknown", "비식별 보유", True, 0.0)
    assert last.breakout_rank is None and not last.close_at_1520 and not last.open_price_target


def test_fire_window_shared_with_status_exit() -> None:
    import src.engine.strategies.unknown as mod
    from src.engine import status_exit_watch as sew
    assert mod.FIRE_WINDOW_START is sew.FIRE_WINDOW_START
    assert mod.FIRE_WINDOW_END is sew.FIRE_WINDOW_END
    assert mod.MAX_FIRES_PER_DAY == sew.MAX_FIRES_PER_DAY == 3


def test_unknown_source_has_no_buy_signal() -> None:
    """섀도·예산 BUY 가드가 이 파일을 건너뛰는 대신(`_strategy_census.NON_BUYING_STRATEGY_FILES`)
    `Signal.BUY` 토큰 자체가 소스에 없음을 잰다."""
    import ast
    from pathlib import Path
    src = Path(__file__).resolve().parents[3] / "src" / "engine" / "strategies" / "unknown.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    hits = [n for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr == "BUY"
            and isinstance(n.value, ast.Name) and n.value.id == "Signal"]
    assert hits == []
