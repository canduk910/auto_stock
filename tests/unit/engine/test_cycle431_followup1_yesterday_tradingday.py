"""cycle431 follow-up Fix1 — 「어제」= 직전 영업일(달력 어제 아님).

검토 지적: `boot_manager.boot()` 의 `yesterday = today - timedelta(days=1)` 를
`_reconcile_corporate_actions` 의 통보 유실 판정(사용자 결정 ②)에 그대로 쓰면
월요일·연휴 다음 날 아침은 주말·공휴일의 빈 주문내역을 봐서 금요일 매도체결
통보 유실을 영원히 설명하지 못한다. 고친 것 = 대사 경로에만
`trading_calendar.previous_trading_day(today)`(KIS 휴장일 역산, never-raise
→ 모르면 `None`)을 쓴다. `buy_dt` 기본값 등 다른 용도의 `yesterday` 는
무접촉(별도 가드 없음 — 기존 cycle431 회귀가 지킨다).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import boot_manager, corporate_action_reconcile as car
from src.engine.strategy_base import Position, StrategyState
from src.models.balance import AccountSummary, StockHolding

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_MONDAY = date(2026, 10, 12)  # 월요일
_FRIDAY = date(2026, 10, 9)  # 직전 영업일(금)
_SUNDAY = _MONDAY - timedelta(days=1)  # 달력 어제(일) — 틀린 값
_CHUSEOK_NEXT = date(2026, 9, 28)  # 연휴 다음 날(가정)
_CHUSEOK_PREV_BIZ = date(2026, 9, 18)  # 연휴 전 마지막 영업일(가정)


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

    def enabled(self):
        return []

    def allocate_funds(self, amount):
        return None


def _holding(ticker: str, *, avg_price: float, quantity: int) -> StockHolding:
    return StockHolding(
        ticker=ticker, name=f"종목{ticker}", quantity=quantity, sellable_quantity=quantity,
        avg_price=avg_price, purchase_amount=int(avg_price * quantity),
        current_price=int(avg_price), eval_amount=int(avg_price * quantity),
        eval_profit_loss=0, eval_profit_rate=0.0,
    )


def _account_summary() -> AccountSummary:
    return AccountSummary(
        deposit=0, stock_eval_amount=0, total_eval_amount=1_000_000, net_asset=1_000_000,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )


@pytest.fixture(autouse=True)
def _reset_state():
    car.reset_state_for_test()
    yield
    car.reset_state_for_test()


def _run_sync(coro):
    import asyncio
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# A — _reconcile_corporate_actions 자체: yesterday_trading_day=None → ②만 skip
# ---------------------------------------------------------------------------


async def _run_reconcile(scheduler, holdings, yesterday_trading_day, *, rev_rows=None, yesterday_orders=None):
    with (
        patch(
            "src.api.corporate_actions.fetch_face_value_change",
            new=AsyncMock(return_value=rev_rows or []),
        ),
        patch(
            "src.api.corporate_actions.fetch_capital_decrease",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "src.api.corporate_actions.fetch_merger_split",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "src.engine.boot_manager.get_daily_orders",
            new=AsyncMock(return_value=yesterday_orders or []),
        ) as orders_mock,
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch("src.engine.scanner.ticker_names", {}),
    ):
        await boot_manager._reconcile_corporate_actions(
            scheduler, holdings, _MONDAY, yesterday_trading_day,
        )
        return orders_mock


def test_a1_yesterday_none_skips_order_lookup_but_keeps_ratio_step(caplog):
    """A1 — yesterday_trading_day=None 이면 ②(주문내역 조회)는 skip, ①(비율)은 그대로."""
    strat = _FakeStrategy("kojiro")
    pos = Position(
        ticker="001390", buy_price=10_000, quantity=1, order_no="O1",
        strategy_id="kojiro", buy_date=_FRIDAY, high_since_buy=12_000,
    )
    strat.state.positions["001390"] = pos
    registry = _FakeRegistry({"kojiro": strat})
    scheduler = SimpleNamespace(registry=registry)

    holdings = [_holding("001390", avg_price=1_000, quantity=10)]
    rev_rows = [{"inter_bf_face_amt": "000005000", "inter_af_face_amt": "000000500"}]

    with caplog.at_level("WARNING", logger="src.engine.boot_manager"):
        orders_mock = _run_sync(
            _run_reconcile(scheduler, holdings, None, rev_rows=rev_rows),
        )

    orders_mock.assert_not_awaited()
    assert pos.quantity == 10  # ①(비율 반영)은 그대로 작동
    assert pos.buy_price == 1_000
    assert any("[corporate_action_yesterday_unknown]" in r.message for r in caplog.records)


def test_a2_yesterday_known_date_still_runs_order_lookup():
    """A2 — yesterday_trading_day 가 날짜면(기존 회귀) ②는 그대로 조회한다."""
    strat = _FakeStrategy("momentum")
    pos = Position(
        ticker="333333", buy_price=10_000, quantity=10, order_no="O5",
        strategy_id="momentum", buy_date=_FRIDAY, high_since_buy=10_500,
    )
    strat.state.positions["333333"] = pos
    registry = _FakeRegistry({"momentum": strat})
    scheduler = SimpleNamespace(registry=registry)

    holdings = [_holding("333333", avg_price=10_000, quantity=12)]
    yesterday_orders = [{"pdno": "333333", "sll_buy_dvsn_cd": "02", "tot_ccld_qty": "2"}]

    orders_mock = _run_sync(
        _run_reconcile(scheduler, holdings, _FRIDAY, yesterday_orders=yesterday_orders),
    )

    orders_mock.assert_awaited_once()
    assert orders_mock.await_args.kwargs["target_date"] == _FRIDAY.strftime("%Y%m%d")
    assert pos.quantity == 12  # sync_qty_only 반영 성공


# ---------------------------------------------------------------------------
# B — boot() 호출부 와이어링: trading_calendar.previous_trading_day 를 쓴다
# ---------------------------------------------------------------------------


def _run_boot_capture_reconcile_arg(previous_trading_day_value):
    """boot() 를 실행하고 `_reconcile_corporate_actions` 에 넘어간 4번째(어제) 인자를 캡처한다."""
    strat = _FakeStrategy("kojiro")
    registry = _FakeRegistry({"kojiro": strat})
    scheduler = SimpleNamespace(registry=registry)
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

    captured: dict = {}

    async def _capture(_scheduler, _holdings, _today, yesterday_trading_day):
        captured["yesterday"] = yesterday_trading_day

    with (
        patch("src.engine.boot_manager._reconcile_corporate_actions", new=_capture),
        patch(
            "src.engine.boot_manager.token_manager",
            new=SimpleNamespace(get_token=AsyncMock()),
        ),
        patch(
            "src.engine.boot_manager.get_balance",
            new=AsyncMock(return_value=([], _account_summary())),
        ),
        patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(return_value=[])),
        patch("src.engine.boot_manager.write_log", new=AsyncMock()),
        patch("src.db.stock_master.count_active", new=AsyncMock(return_value=2768)),
        patch("src.db.positions.load_all", new=AsyncMock(return_value=[])),
        patch("src.db.positions.delete_position", new=AsyncMock()),
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch("src.db.trade_history.get_recent_buy_strategy", new=AsyncMock(return_value=None)),
        patch("src.db.trade_history.mark_pending_buys_completed", new=AsyncMock()),
        patch(
            "src.db.trade_history.get_today_buys_ticker_strategy", new=AsyncMock(return_value=[]),
        ),
        patch(
            "src.engine.trading_calendar.previous_trading_day",
            new=AsyncMock(return_value=previous_trading_day_value),
        ),
    ):
        _run_sync(boot_manager.boot(scheduler))

    return captured.get("yesterday")


def test_b1_monday_resolves_to_friday_not_calendar_sunday():
    """B1 — 월요일 07:45 기동 → 대사 경로의 「어제」는 금요일(직전 영업일)이어야 한다.

    실제 호출 시각의 달력 어제(`today - 1일`)와 **절대 같을 수 없는** 먼 과거
    sentinel 값을 `previous_trading_day` 리턴으로 주입한다 — 우연히 날짜가
    맞아떨어져 구코드에서도 통과하는 거짓 양성을 차단한다(실측: 2026-10-09
    실행분이 달력 어제와 같아서 걸렸던 1차 버전의 결함).
    """
    real_today = datetime.now(_KST).date()
    calendar_yesterday = real_today - timedelta(days=1)
    sentinel = real_today - timedelta(days=40)  # 「금요일」 역할의 먼 과거 sentinel
    assert sentinel != calendar_yesterday

    got = _run_boot_capture_reconcile_arg(sentinel)
    assert got == sentinel
    assert got != calendar_yesterday


def test_b2_day_after_chuseok_backtracks_multiple_days():
    """B2 — 추석 연휴 다음 날 아침 → 연휴 전 마지막 영업일까지 역산된 값을 그대로 쓴다."""
    real_today = datetime.now(_KST).date()
    calendar_yesterday = real_today - timedelta(days=1)
    sentinel = real_today - timedelta(days=41)  # B1 과 다른 sentinel(다중 역산 흔적)
    assert sentinel != calendar_yesterday

    got = _run_boot_capture_reconcile_arg(sentinel)
    assert got == sentinel


def test_b3_lookup_failure_degrades_to_none_not_calendar_yesterday():
    """B3 — `previous_trading_day` 조회 실패(예외 흡수 후 None) → 대사 경로에 `None` 이 간다.

    `None` 을 달력 어제로 대체하지 않는다(그러면 B1 문제가 조용히 되살아난다).
    """
    got = _run_boot_capture_reconcile_arg(None)
    assert got is None
