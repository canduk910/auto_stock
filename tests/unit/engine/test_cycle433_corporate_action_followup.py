"""cycle433 — cycle431 액면병합 대사 후속 3건.

사용자 지시 2026-10-10 「후속작업도 정리하자」. 정본 = `_workspace/domain_consult/
2026-10-10_corporate_action_qty_reconcile.md` (특히 Q4 15분 관측 5분류, Q1 B
「3영업일 연속 → CRITICAL」) + `src/engine/CLAUDE.md` 의 cycle431 서술.

구성:
- A. `observe_mid_session_sync` 15분 관측 5분류 복원(통보 대기 · 운영자 몫 분리)
- B. `boot_manager._reconcile_corporate_actions` 의 3영업일 연속 CRITICAL 승격
- C. 빠진 통합 테스트(회귀표 C4·C19·C20)
"""
from __future__ import annotations

import inspect
import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.engine import boot_manager, corporate_action_reconcile as car
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.balance import AccountSummary, StockHolding

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_SCHED_LOGGER = "src.engine.scheduler"
_BOOT_LOGGER = "src.engine.boot_manager"


@pytest.fixture(autouse=True)
def _reset_state():
    car.reset_state_for_test()
    yield
    car.reset_state_for_test()


class _Pos:
    def __init__(self, qty):
        self.quantity = qty


class _Strategy:
    def __init__(self, positions):
        self.state = type("S", (), {"positions": positions})()


class _Registry:
    def __init__(self, strategies):
        self._strategies = strategies

    def all(self):
        return self._strategies


class _Holding:
    def __init__(self, ticker, quantity):
        self.ticker = ticker
        self.quantity = quantity


# ═══════════════════════════════════════════════════════════════════════════
# A. observe_mid_session_sync — 5분류 복원 (통보 대기 · 운영자 몫)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a1_operator_buy_fill_is_operator_share_not_merged(monkeypatch, caplog):
    """운영자 몫 — Δ>0 이고 우리 매핑에 없는 주문의 매수 체결. 추적 수량 그대로."""
    registry = _Registry([_Strategy({"005930": _Pos(10)})])
    holdings = [_Holding("005930", 15)]
    rows = [{"pdno": "005930", "odno": "0000777", "rmn_qty": "0",
             "sll_buy_dvsn_cd": "02", "tot_ccld_qty": "5"}]
    monkeypatch.setattr("src.api.balance.get_daily_orders", AsyncMock(return_value=rows))
    # 우리 쪽 오늘 매수·매도 주문 없음 → 이 주문은 "우리 것" 이 아니다.
    monkeypatch.setattr(
        "src.db.trade_history.get_today_buy_trades_for_sync", AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.db.trade_history.get_today_sell_trades_for_sync", AsyncMock(return_value=[]),
    )
    with caplog.at_level("INFO", logger=_SCHED_LOGGER):
        await car.observe_mid_session_sync(registry, holdings)

    assert any("result=operator_share" in r.message for r in caplog.records)
    assert not any("explained_by_orders" in r.message for r in caplog.records)
    assert not any("holding_qty_unexplained" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_a2_our_sell_fill_is_pending_notice_not_merged(monkeypatch, caplog):
    """통보 대기 — Δ<0 이고 -Δ 가 우리 매도 주문의 미반영 체결. 장부 무변경."""
    registry = _Registry([_Strategy({"005930": _Pos(10)})])
    holdings = [_Holding("005930", 7)]
    rows = [{"pdno": "005930", "odno": "0000321", "rmn_qty": "0",
             "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "3"}]
    monkeypatch.setattr("src.api.balance.get_daily_orders", AsyncMock(return_value=rows))
    # 우리 주문 — trade_history sync 조회가 같은 주문번호(선행 0 제거 후 "321")를 돌려준다.
    monkeypatch.setattr(
        "src.db.trade_history.get_today_buy_trades_for_sync", AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.db.trade_history.get_today_sell_trades_for_sync",
        AsyncMock(return_value=[{"order_no": "321"}]),
    )
    with caplog.at_level("INFO", logger=_SCHED_LOGGER):
        await car.observe_mid_session_sync(registry, holdings)

    assert any("result=pending_notice" in r.message for r in caplog.records)
    assert not any("explained_by_orders" in r.message for r in caplog.records)
    assert not any("operator_share" in r.message for r in caplog.records)
    assert not any(
        r.levelname == "ERROR" and "holding_qty_unexplained" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_a3_ownership_lookup_failure_falls_back_to_merged_not_operator(monkeypatch, caplog):
    """정보가 없으면 operator 로 단정하지 않고 묶은 explained_by_orders 로 남긴다."""
    registry = _Registry([_Strategy({"005930": _Pos(10)})])
    holdings = [_Holding("005930", 15)]
    rows = [{"pdno": "005930", "odno": "0000777", "rmn_qty": "0",
             "sll_buy_dvsn_cd": "02", "tot_ccld_qty": "5"}]
    monkeypatch.setattr("src.api.balance.get_daily_orders", AsyncMock(return_value=rows))
    monkeypatch.setattr(
        "src.db.trade_history.get_today_buy_trades_for_sync",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    with caplog.at_level("INFO", logger=_SCHED_LOGGER):
        await car.observe_mid_session_sync(registry, holdings)

    assert any("result=explained_by_orders" in r.message for r in caplog.records)
    assert not any("operator_share" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_a4_pending_notice_escalates_to_fill_notice_missing_after_30min(
    monkeypatch, caplog,
):
    """2회차(30분) 넘게 통보 대기면 [fill_notice_missing] ERROR(통보 유실 확정)."""
    registry = _Registry([_Strategy({"005930": _Pos(10)})])
    holdings = [_Holding("005930", 7)]
    rows = [{"pdno": "005930", "odno": "0000321", "rmn_qty": "0",
             "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "3"}]
    monkeypatch.setattr("src.api.balance.get_daily_orders", AsyncMock(return_value=rows))
    monkeypatch.setattr(
        "src.db.trade_history.get_today_buy_trades_for_sync", AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.db.trade_history.get_today_sell_trades_for_sync",
        AsyncMock(return_value=[{"order_no": "321"}]),
    )

    with caplog.at_level("INFO", logger=_SCHED_LOGGER):
        with freeze_time("2026-10-10 10:00:00+09:00"):
            await car.observe_mid_session_sync(registry, holdings)
        with freeze_time("2026-10-10 10:15:00+09:00"):
            await car.observe_mid_session_sync(registry, holdings)
        with freeze_time("2026-10-10 10:30:00+09:00"):
            await car.observe_mid_session_sync(registry, holdings)

    pending_infos = [r for r in caplog.records if "result=pending_notice" in r.message]
    assert len(pending_infos) == 2, "1·2회차(0분·15분)는 아직 INFO 통보 대기여야 한다"
    assert any(
        r.levelname == "ERROR" and "fill_notice_missing" in r.message for r in caplog.records
    ), "3회차(30분)는 통보 유실 확정 ERROR 여야 한다"


@pytest.mark.asyncio
async def test_a5_resolved_ticker_clears_pending_notice_timer(monkeypatch, caplog):
    """일치로 돌아오면 통보 대기 타이머가 지워져 다음 사건이 처음부터 잰다."""
    registry = _Registry([_Strategy({"005930": _Pos(10)})])
    rows = [{"pdno": "005930", "odno": "0000321", "rmn_qty": "0",
             "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "3"}]
    monkeypatch.setattr("src.api.balance.get_daily_orders", AsyncMock(return_value=rows))
    monkeypatch.setattr(
        "src.db.trade_history.get_today_buy_trades_for_sync", AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.db.trade_history.get_today_sell_trades_for_sync",
        AsyncMock(return_value=[{"order_no": "321"}]),
    )

    with freeze_time("2026-10-10 10:00:00+09:00"):
        await car.observe_mid_session_sync(registry, [_Holding("005930", 7)])
    # 통보가 반영돼 일치로 돌아왔다 — 다음 회차는 조회를 건너뛴다(mismatched 가 비므로).
    with freeze_time("2026-10-10 10:10:00+09:00"):
        await car.observe_mid_session_sync(registry, [_Holding("005930", 10)])

    assert car._PENDING_NOTICE_FIRST_SEEN.get("2026-10-10", {}).get("005930") is None


# ═══════════════════════════════════════════════════════════════════════════
# B. _reconcile_corporate_actions — 3영업일 연속 CRITICAL 승격
# ═══════════════════════════════════════════════════════════════════════════


class _FakeStrategy:
    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id
        self.state = SimpleNamespace(positions={})
        self.on_scale_event = MagicMock()
        self.on_position_closed = MagicMock()


class _FakeRegistry:
    def __init__(self, strategies: dict[str, _FakeStrategy]):
        self._strategies = strategies

    def all(self):
        return list(self._strategies.values())

    def get(self, strategy_id):
        return self._strategies.get(strategy_id)


def _holding(ticker: str, *, avg_price: float, quantity: int) -> StockHolding:
    return StockHolding(
        ticker=ticker, name=f"종목{ticker}", quantity=quantity, sellable_quantity=quantity,
        avg_price=avg_price, purchase_amount=int(avg_price * quantity),
        current_price=int(avg_price), eval_amount=int(avg_price * quantity),
        eval_profit_loss=0, eval_profit_rate=0.0,
    )


async def _run_unexplained(scheduler, holdings, today, yesterday):
    with (
        patch("src.api.corporate_actions.fetch_face_value_change", new=AsyncMock(return_value=[])),
        patch("src.api.corporate_actions.fetch_capital_decrease", new=AsyncMock(return_value=[])),
        patch("src.api.corporate_actions.fetch_merger_split", new=AsyncMock(return_value=[])),
        patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(return_value=[])),
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch("src.engine.scanner.ticker_names", {}),
    ):
        await boot_manager._reconcile_corporate_actions(scheduler, holdings, today, yesterday)


@pytest.mark.asyncio
async def test_b1_escalates_to_critical_on_third_consecutive_day(caplog):
    """직전 2영업일 + 오늘 모두 unexplained 면 CRITICAL."""
    strat = _FakeStrategy("kojiro")
    strat.state.positions["444444"] = Position(
        ticker="444444", buy_price=10_000, quantity=5, order_no="O6",
        strategy_id="kojiro", buy_date=date(2026, 10, 9),
    )
    registry = _FakeRegistry({"kojiro": strat})
    scheduler = SimpleNamespace(registry=registry)
    holdings = [_holding("444444", avg_price=10_000, quantity=3)]
    today = date(2026, 10, 12)  # 월요일 — 직전 영업일 10-09(금), 10-08(목)

    with (
        patch(
            "src.engine.trading_calendar.previous_trading_day",
            new=AsyncMock(side_effect=[date(2026, 10, 9), date(2026, 10, 8)]),
        ),
        patch(
            "src.db.system_logs.search_logs",
            new=AsyncMock(return_value={
                "logs": [{"message": "[holding_qty_unexplained] ticker=444444 tracked=5 kis=3"}],
            }),
        ),
    ):
        with caplog.at_level("INFO", logger=_BOOT_LOGGER):
            await _run_unexplained(scheduler, holdings, today, date(2026, 10, 9))

    assert any(
        r.levelname == "CRITICAL" and "holding_qty_unexplained" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_b2_stays_error_when_only_one_prior_day_matches(caplog):
    """직전 1영업일만 일치하면 승격하지 않는다(ERROR 유지)."""
    strat = _FakeStrategy("kojiro")
    strat.state.positions["444444"] = Position(
        ticker="444444", buy_price=10_000, quantity=5, order_no="O6",
        strategy_id="kojiro", buy_date=date(2026, 10, 9),
    )
    registry = _FakeRegistry({"kojiro": strat})
    scheduler = SimpleNamespace(registry=registry)
    holdings = [_holding("444444", avg_price=10_000, quantity=3)]
    today = date(2026, 10, 12)

    def _fake_search(q, *, start=None, end=None, limit=200):
        if start and start.startswith("2026-10-09"):
            return {"logs": [{"message": "[holding_qty_unexplained] ticker=444444 tracked=5 kis=3"}]}
        return {"logs": []}

    with (
        patch(
            "src.engine.trading_calendar.previous_trading_day",
            new=AsyncMock(side_effect=[date(2026, 10, 9), date(2026, 10, 8)]),
        ),
        patch("src.db.system_logs.search_logs", new=AsyncMock(side_effect=_fake_search)),
    ):
        with caplog.at_level("INFO", logger=_BOOT_LOGGER):
            await _run_unexplained(scheduler, holdings, today, date(2026, 10, 9))

    assert any(
        r.levelname == "ERROR" and "holding_qty_unexplained" in r.message
        for r in caplog.records
    )
    assert not any(r.levelname == "CRITICAL" for r in caplog.records)


@pytest.mark.asyncio
async def test_b3_db_query_failure_keeps_error_does_not_raise(caplog):
    """DB 조회 실패도 ERROR 유지(승격 안 함, 예외 전파 안 함)."""
    strat = _FakeStrategy("kojiro")
    strat.state.positions["444444"] = Position(
        ticker="444444", buy_price=10_000, quantity=5, order_no="O6",
        strategy_id="kojiro", buy_date=date(2026, 10, 9),
    )
    registry = _FakeRegistry({"kojiro": strat})
    scheduler = SimpleNamespace(registry=registry)
    holdings = [_holding("444444", avg_price=10_000, quantity=3)]
    today = date(2026, 10, 12)

    with (
        patch(
            "src.engine.trading_calendar.previous_trading_day",
            new=AsyncMock(side_effect=[date(2026, 10, 9), date(2026, 10, 8)]),
        ),
        patch(
            "src.db.system_logs.search_logs",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ),
    ):
        with caplog.at_level("INFO", logger=_BOOT_LOGGER):
            await _run_unexplained(scheduler, holdings, today, date(2026, 10, 9))

    assert any(
        r.levelname == "ERROR" and "holding_qty_unexplained" in r.message
        for r in caplog.records
    )
    assert not any(r.levelname == "CRITICAL" for r in caplog.records)


@pytest.mark.asyncio
async def test_b4_calendar_unknown_keeps_error():
    """영업일을 모르면(trading_calendar None) 승격하지 않는다."""
    assert await car.should_escalate_unexplained("005930", today=date(2026, 10, 12)) is False


# ═══════════════════════════════════════════════════════════════════════════
# C. 빠진 통합 테스트 — 회귀표 C4 · C19 · C20
# ═══════════════════════════════════════════════════════════════════════════


def _account_summary() -> AccountSummary:
    return AccountSummary(
        deposit=0, stock_eval_amount=0, total_eval_amount=1_000_000, net_asset=1_000_000,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )


@pytest.mark.asyncio
async def test_c4_merge_to_zero_deletes_position_and_calls_on_position_closed():
    """C4 — 3주를 10:1 병합해 보유가 0주(KIS 잔고에서 사라짐) → 1차 삭제 경로 +
    `on_position_closed` 로 스탬프 정리. (`_reconcile_corporate_actions` 는 `kis`
    가 None 인 종목을 보지 않으므로, 소멸은 부팅 1차 복구의 "KIS 미보유" 분기다.)
    """
    strat = _FakeStrategy("kojiro")
    registry = SimpleNamespace(
        all=lambda: [strat],
        get=lambda sid: strat if sid == "kojiro" else None,
        is_ticker_held_by_any=lambda t: False,
        enabled=lambda: [],
        allocate_funds=lambda amount: None,
    )
    scheduler = SimpleNamespace(registry=registry)

    with (
        patch("src.engine.boot_manager.token_manager") as tm,
        patch(
            "src.engine.boot_manager.get_balance",
            new=AsyncMock(return_value=([], _account_summary())),
        ),
        patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(return_value=[])),
        patch("src.engine.boot_manager.write_log", new=AsyncMock()),
        patch("src.db.stock_master.count_active", new=AsyncMock(return_value=2768)),
        patch(
            "src.db.positions.load_all",
            new=AsyncMock(return_value=[{
                # 병합 전 3주 보유 — 10:1 병합 뒤 KIS 수량 0(= 보유 자체가 소멸)
                "ticker": "666666", "strategy_id": "kojiro", "buy_price": 10_000,
                "quantity": 3, "order_no": "O8", "buy_date": date(2026, 10, 9),
            }]),
        ),
        patch("src.db.positions.delete_position", new=AsyncMock()) as delete_mock,
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch("src.db.trade_history.get_recent_buy_strategy", new=AsyncMock(return_value=None)),
        patch("src.db.trade_history.mark_pending_buys_completed", new=AsyncMock()),
        patch(
            "src.db.trade_history.get_today_buys_ticker_strategy",
            new=AsyncMock(return_value=[]),
        ),
        patch("src.engine.boot_manager._reconcile_corporate_actions", new=AsyncMock()),
    ):
        tm.get_token = AsyncMock()
        scheduler._preissue_all_tokens = AsyncMock()
        scheduler._load_strategy_config = AsyncMock()
        scheduler._refresh_market_regime_and_persist = AsyncMock()
        scheduler._resolve_cash_usage_ratio = AsyncMock(return_value=1.0)
        scheduler._sync_orders_to_db = AsyncMock()
        scheduler._eager_refresh_stock_master_for_held_positions = AsyncMock()
        scheduler.order_engine = MagicMock()
        scheduler.order_engine._pending_buy_orders = {}
        scheduler.order_engine._order_qty = {}
        scheduler.order_engine._order_strategy = {}
        scheduler.order_engine._order_ticker = {}
        scheduler._pending_next_day_clear = set()

        await boot_manager.boot(scheduler)

    delete_mock.assert_awaited_once_with("666666")
    strat.on_position_closed.assert_called_once_with("666666")


@pytest.mark.asyncio
async def test_c19_budget_residual_unchanged_after_scale():
    """C19 — 반영 전후 Σ매수금액(buy_price × qty) 이 그대로다(예산 잔여 불변)."""
    strat = _FakeStrategy("kojiro")
    pos = Position(
        ticker="001390", buy_price=10_000, quantity=1, order_no="O1",
        strategy_id="kojiro", buy_date=date(2026, 10, 9), high_since_buy=12_000,
    )
    strat.state.positions["001390"] = pos
    registry = _FakeRegistry({"kojiro": strat})
    scheduler = SimpleNamespace(registry=registry)

    before_notional = pos.buy_price * pos.quantity

    holdings = [_holding("001390", avg_price=1_000, quantity=10)]
    rev_rows = [{"inter_bf_face_amt": "000005000", "inter_af_face_amt": "000000500"}]

    with (
        patch("src.api.corporate_actions.fetch_face_value_change", new=AsyncMock(return_value=rev_rows)),
        patch("src.api.corporate_actions.fetch_capital_decrease", new=AsyncMock(return_value=[])),
        patch("src.api.corporate_actions.fetch_merger_split", new=AsyncMock(return_value=[])),
        patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(return_value=[])),
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch("src.engine.scanner.ticker_names", {}),
    ):
        await boot_manager._reconcile_corporate_actions(
            scheduler, holdings, date(2026, 10, 10), date(2026, 10, 9),
        )

    after_notional = pos.buy_price * pos.quantity
    assert pos.quantity == 10
    assert pos.buy_price == 1_000
    assert after_notional == before_notional, (
        f"예산 잔여 불변 위반: before={before_notional} after={after_notional}"
    )


class _C20Strat(StrategyBase):
    def __init__(self) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id="kojiro", name="kojiro-dummy", enabled=True, weight=0.5,
                params={"exchange": "KRX"},
            )
        )
        self.state.total_investment = 10_000_000

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 0


@pytest.mark.asyncio
async def test_c20_sell_fill_pnl_uses_rescaled_buy_price(monkeypatch):
    """C20 — 반영(C1 분할) 뒤 SELL 체결의 손익이 환산된 매수가 기준으로 맞는다.

    `order_engine._handle_sell_fill` 은 고치지 않는다 — `handle_execution_notice`
    로 호출만 해서, cycle431 이 옮긴 `pos.buy_price` 를 그대로 쓰는지 본다.
    """
    import src.db.positions as positions_mod
    import src.engine.order_engine as _oe
    from src.engine import scanner
    from src.engine.order_engine import OrderEngine
    from src.engine.session import MarketBoard, session_tracker
    from src.config import settings

    ticker = "001390"
    monkeypatch.setattr(scanner, "ticker_names", {ticker: "테스트종목"}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prices", {ticker: {"current_price": 1_500}}, raising=False)
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))
    monkeypatch.setattr(settings, "kis_env", "vts")

    registry = StrategyRegistry()
    strat = _C20Strat()
    registry.register(strat)

    # C1 분할 전 — 1주 @10,000.
    pos = Position(
        ticker=ticker, buy_price=10_000, quantity=1, order_no="O1",
        strategy_id="kojiro", buy_date=date(2026, 10, 9), high_since_buy=10_000,
    )
    strat.state.positions[ticker] = pos

    scheduler = SimpleNamespace(registry=registry)
    holdings = [_holding(ticker, avg_price=1_000, quantity=10)]
    rev_rows = [{"inter_bf_face_amt": "000005000", "inter_af_face_amt": "000000500"}]

    with (
        patch("src.api.corporate_actions.fetch_face_value_change", new=AsyncMock(return_value=rev_rows)),
        patch("src.api.corporate_actions.fetch_capital_decrease", new=AsyncMock(return_value=[])),
        patch("src.api.corporate_actions.fetch_merger_split", new=AsyncMock(return_value=[])),
        patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(return_value=[])),
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch("src.engine.scanner.ticker_names", {ticker: "테스트종목"}),
    ):
        await boot_manager._reconcile_corporate_actions(
            scheduler, holdings, date(2026, 10, 10), date(2026, 10, 9),
        )

    # 반영 뒤 — 10주 @1,000 으로 옮겨졌다.
    assert pos.quantity == 10
    assert pos.buy_price == 1_000

    # 이제 10주 전량을 1,500 에 매도 체결시킨다.
    engine = OrderEngine(registry)
    engine._unsubscribe_if_no_other_strategy = AsyncMock(return_value=None)
    engine._order_qty["S1"] = 10
    engine._order_strategy["S1"] = "kojiro"
    engine._order_ticker[ticker] = ticker  # (미사용이어도 무해)

    calls: list = []

    async def fake_update(*args, **kwargs):
        calls.append((args, kwargs))
        return 1

    _save_sig = inspect.signature(positions_mod.save_position)

    async def fake_save(*args, **kwargs):
        return None

    async def fake_delete(ticker_, *a, **k):
        return None

    monkeypatch.setattr(_oe, "update_trade_status", fake_update)
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "_update_trade_status_by_order_no", AsyncMock(return_value=1))
    monkeypatch.setattr(_oe, "_lookup_strategy_from_trade_history", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(positions_mod, "save_position", fake_save)
    monkeypatch.setattr(positions_mod, "delete_position", fake_delete)
    import src.db.stock_master as _sm
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))

    try:
        await engine.handle_execution_notice(
            ticker=ticker, order_no="S1", side="SELL", price=1_500, quantity=10,
            ordered_qty_payload=10,
        )

        expected_pnl = (1_500 - 1_000) * 10  # 환산된(÷10) 매수가 기준
        assert strat.state.daily_realized_pnl == expected_pnl, (
            f"기대 손익 {expected_pnl}(환산 매수가 1,000 기준) ≠ 실제 "
            f"{strat.state.daily_realized_pnl}(옛 매수가 10,000 을 썼다면 "
            f"{(1_500 - 10_000) * 10} 가 됐을 것)"
        )
    finally:
        for task in list(engine._pending_cancel_tasks.values()):
            task.cancel()
        engine._pending_cancel_tasks.clear()
