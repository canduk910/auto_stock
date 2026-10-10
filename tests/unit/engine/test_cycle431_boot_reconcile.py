"""cycle431 — `boot_manager._reconcile_corporate_actions` 조립 테스트.

07:45 부팅 1차 복구 직후 호출되는 자리의 행위를 고정한다. 판정 자체는
`corporate_action_reconcile.classify()`(순수, 별도 테스트)가 맡고, 여기서는
KIS 조회 결과를 받아 Position·DB·전략 스탬프에 **어떻게 적용**하는지와
`on_position_closed`(④) 를 검증한다.
"""
from __future__ import annotations

from datetime import date, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import boot_manager, corporate_action_reconcile as car
from src.engine.strategy_base import Position, StrategyState
from src.models.balance import AccountSummary, StockHolding

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_TODAY = date(2026, 10, 10)
_YESTERDAY = _TODAY - timedelta(days=1)


class _FakeStrategy:
    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id
        self.state = StrategyState(strategy_id=strategy_id)
        self.config = SimpleNamespace(params={}, weight=0.0, enabled=True)
        self.on_scale_event = MagicMock()
        self.on_position_closed = MagicMock()


class _FakeRegistry:
    def __init__(self, strategies: dict[str, _FakeStrategy]):
        self._strategies = strategies

    def all(self):
        return list(self._strategies.values())

    def get(self, strategy_id):
        return self._strategies.get(strategy_id)

    def allocate_funds(self, amount):  # noqa: D401 — 테스트 스텁, 부수효과 없음
        return None


def _holding(ticker: str, *, avg_price: float, quantity: int) -> StockHolding:
    return StockHolding(
        ticker=ticker, name=f"종목{ticker}", quantity=quantity, sellable_quantity=quantity,
        avg_price=avg_price, purchase_amount=int(avg_price * quantity),
        current_price=int(avg_price), eval_amount=int(avg_price * quantity),
        eval_profit_loss=0, eval_profit_rate=0.0,
    )


@pytest.fixture(autouse=True)
def _reset_state():
    car.reset_state_for_test()
    yield
    car.reset_state_for_test()


async def _run(scheduler, holdings, *, rev_rows=None, cap_rows=None, merger_rows=None, yesterday_orders=None):
    with (
        patch(
            "src.api.corporate_actions.fetch_face_value_change",
            new=AsyncMock(return_value=rev_rows or []),
        ),
        patch(
            "src.api.corporate_actions.fetch_capital_decrease",
            new=AsyncMock(return_value=cap_rows or []),
        ),
        patch(
            "src.api.corporate_actions.fetch_merger_split",
            new=AsyncMock(return_value=merger_rows or []),
        ),
        patch(
            "src.engine.boot_manager.get_daily_orders",
            new=AsyncMock(return_value=yesterday_orders or []),
        ),
        patch("src.db.positions.save_position", new=AsyncMock()) as save_mock,
        patch("src.engine.scanner.ticker_names", {}),
    ):
        await boot_manager._reconcile_corporate_actions(scheduler, holdings, _TODAY, _YESTERDAY)
        return save_mock


def test_c1_apply_scale_scales_position_and_marks_rescaled_today():
    """C1 — kojiro 1주 보유, 1:10 분할 → qty 10 · buy_price÷10 · high÷10 · 스탬프 반영."""
    strat = _FakeStrategy("kojiro")
    pos = Position(
        ticker="001390", buy_price=10_000, quantity=1, order_no="O1",
        strategy_id="kojiro", buy_date=_YESTERDAY, high_since_buy=12_000,
    )
    strat.state.positions["001390"] = pos
    registry = _FakeRegistry({"kojiro": strat})
    scheduler = SimpleNamespace(registry=registry)

    holdings = [_holding("001390", avg_price=1_000, quantity=10)]
    rev_rows = [{"inter_bf_face_amt": "000005000", "inter_af_face_amt": "000000500"}]

    save_mock = _run_sync(_run(scheduler, holdings, rev_rows=rev_rows))

    assert pos.quantity == 10
    assert pos.buy_price == 1_000
    assert pos.high_since_buy == pytest.approx(1_200.0)
    strat.on_scale_event.assert_called_once_with("001390", 10.0)
    assert car.is_rescaled_today("001390", today=_TODAY) is True
    save_mock.assert_awaited()


def test_c3_merge_applies_scale():
    """C3 — donchian 15주, 10:1 병합 → qty 1 · buy_price×10."""
    strat = _FakeStrategy("donchian_swing")
    pos = Position(
        ticker="011690", buy_price=1_000, quantity=15, order_no="O2",
        strategy_id="donchian_swing", buy_date=_YESTERDAY, high_since_buy=1_100,
    )
    strat.state.positions["011690"] = pos
    registry = _FakeRegistry({"donchian_swing": strat})
    scheduler = SimpleNamespace(registry=registry)

    holdings = [_holding("011690", avg_price=10_000, quantity=1)]
    rev_rows = [{"inter_bf_face_amt": "000000500", "inter_af_face_amt": "000005000"}]

    _run_sync(_run(scheduler, holdings, rev_rows=rev_rows))

    assert pos.quantity == 1
    assert pos.buy_price == 10_000
    strat.on_scale_event.assert_called_once_with("011690", pytest.approx(0.1))


def test_c5_bonus_issue_shape_without_face_value_change_is_unexplained_and_blocks_buy():
    """C5 — 수량×2·평균÷2 인데 액면가 그대로(무상증자 입고) → 반영 0 · 매수 차단 · 보유 유지."""
    strat = _FakeStrategy("vcp_breakout")
    pos = Position(
        ticker="100840", buy_price=10_000, quantity=10, order_no="O3",
        strategy_id="vcp_breakout", buy_date=_YESTERDAY,
    )
    strat.state.positions["100840"] = pos
    registry = _FakeRegistry({"vcp_breakout": strat})
    scheduler = SimpleNamespace(registry=registry)

    holdings = [_holding("100840", avg_price=5_000, quantity=20)]

    _run_sync(_run(scheduler, holdings))  # 예탁원 응답 없음(액면가 불변 상황 모사)

    assert pos.quantity == 10  # 보존 — 바뀌지 않는다
    assert car.is_buy_blocked_today("100840", today=_TODAY) is True
    strat.on_scale_event.assert_not_called()
    assert car.is_rescaled_today("100840", today=_TODAY) is False


def test_c8_merger_split_detected_blocks_buy_without_applying():
    strat = _FakeStrategy("kojiro")
    pos = Position(
        ticker="222222", buy_price=10_000, quantity=5, order_no="O4",
        strategy_id="kojiro", buy_date=_YESTERDAY,
    )
    strat.state.positions["222222"] = pos
    registry = _FakeRegistry({"kojiro": strat})
    scheduler = SimpleNamespace(registry=registry)

    holdings = [_holding("222222", avg_price=10_000, quantity=3)]
    merger_rows = [{"sht_cd": "222222", "cust_nm": "합병회사"}]

    _run_sync(_run(scheduler, holdings, merger_rows=merger_rows))

    assert pos.quantity == 5
    assert car.is_buy_blocked_today("222222", today=_TODAY) is True


def test_sync_qty_only_does_not_touch_buy_price_or_stamps():
    """통보 유실(사용자 결정 ②) — 수량만 KIS 값으로, 매입가·스탬프 무접촉."""
    strat = _FakeStrategy("momentum")
    pos = Position(
        ticker="333333", buy_price=10_000, quantity=10, order_no="O5",
        strategy_id="momentum", buy_date=_YESTERDAY, high_since_buy=10_500,
    )
    strat.state.positions["333333"] = pos
    registry = _FakeRegistry({"momentum": strat})
    scheduler = SimpleNamespace(registry=registry)

    holdings = [_holding("333333", avg_price=10_000, quantity=12)]
    yesterday_orders = [
        {"pdno": "333333", "sll_buy_dvsn_cd": "02", "tot_ccld_qty": "2"},
    ]

    _run_sync(_run(scheduler, holdings, yesterday_orders=yesterday_orders))

    assert pos.quantity == 12
    assert pos.buy_price == 10_000
    assert pos.high_since_buy == 10_500
    strat.on_scale_event.assert_not_called()
    assert car.is_rescaled_today("333333", today=_TODAY) is False


def test_kis_lookup_failures_are_graceful_and_fall_through_to_unexplained():
    strat = _FakeStrategy("kojiro")
    pos = Position(
        ticker="444444", buy_price=10_000, quantity=5, order_no="O6",
        strategy_id="kojiro", buy_date=_YESTERDAY,
    )
    strat.state.positions["444444"] = pos
    registry = _FakeRegistry({"kojiro": strat})
    scheduler = SimpleNamespace(registry=registry)

    holdings = [_holding("444444", avg_price=10_000, quantity=3)]

    with (
        patch(
            "src.api.corporate_actions.fetch_face_value_change",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "src.api.corporate_actions.fetch_capital_decrease",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "src.api.corporate_actions.fetch_merger_split",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "src.engine.boot_manager.get_daily_orders",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch("src.engine.scanner.ticker_names", {}),
    ):
        _run_sync(
            boot_manager._reconcile_corporate_actions(scheduler, holdings, _TODAY, _YESTERDAY)
        )

    assert pos.quantity == 5  # 보존
    assert car.is_buy_blocked_today("444444", today=_TODAY) is True


def test_on_position_closed_called_when_db_position_deleted_on_kis_miss():
    """④ — 부팅 「KIS 미보유 → DB 행 삭제」 경로에서 on_position_closed 를 부른다."""
    strat = _FakeStrategy("kojiro")
    registry = _FakeRegistry({"kojiro": strat})
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
                "ticker": "555555", "strategy_id": "kojiro", "buy_price": 10_000,
                "quantity": 1, "order_no": "O7", "buy_date": _YESTERDAY,
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
        patch(
            "src.engine.boot_manager._reconcile_corporate_actions", new=AsyncMock(),
        ),
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
        registry.is_ticker_held_by_any = lambda t: False
        registry.enabled = lambda: []

        _run_sync(boot_manager.boot(scheduler))

    delete_mock.assert_awaited_once_with("555555")
    strat.on_position_closed.assert_called_once_with("555555")


def _account_summary() -> AccountSummary:
    return AccountSummary(
        deposit=0, stock_eval_amount=0, total_eval_amount=1_000_000, net_asset=1_000_000,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )


def _run_sync(coro):
    import asyncio
    return asyncio.run(coro)
