"""cycle425 — boot_manager 「주인 모를 주문·보유 = momentum」 폴백 고정 테스트.

리팩토링 카드 #11 1단계(`_workspace/refactor/2026-10-09_review.md` 173행~) 전,
지금 코드의 입력→출력을 고정한다. 리터럴 `"momentum"` 폴백 6자리가 `boot_manager.py`
세 경로에 흩어져 같은 규칙("출처를 모르는 주문·보유는 momentum 이 받는다")을 반복한다:

1. DB positions 복구 (line ~305) — `registry.get(strategy_id) or registry.get("momentum")`
2. KIS 잔고 보완 복구 (line ~347) — 기본값 `"momentum"` + trade_history 조회로 덮어쓰기
3. 미체결 매수 주문 복구 (line ~455-456) — `db_strategy_map.get(ticker, "momentum")` +
   `registry.get(strategy_id) or registry.get("momentum")`

이 테스트는 리팩토링 전후로 **바이트 동일**해야 한다(행위 0) — 커밋 순서:
이 파일(현행 고정) → 상수(`FALLBACK_OWNER_ID`)·헬퍼 도입 리팩토링. 리팩토링 커밋은
이 파일을 건드리지 않는다.
"""
from __future__ import annotations

from datetime import date, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import boot_manager
from src.engine.strategy_base import StrategyState
from src.models.balance import AccountSummary, StockHolding

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


class _FakeStrategy:
    """등록된 전략 더블 — `StrategyState` 실물 + 최소 `config` 스텁."""

    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id
        self.state = StrategyState(strategy_id=strategy_id)
        self.config = SimpleNamespace(params={}, weight=0.0, enabled=True)


class _FakeRegistry:
    """실제 `StrategyRegistry` 와 같은 계약 — 등록 안 된 id 는 `None`."""

    def __init__(self, strategies: dict[str, _FakeStrategy]):
        self._strategies = strategies

    def get(self, strategy_id):
        return self._strategies.get(strategy_id)

    def all(self):
        return list(self._strategies.values())

    def enabled(self):
        return []

    def is_ticker_held_by_any(self, ticker: str) -> bool:
        return any(ticker in s.state.positions for s in self._strategies.values())

    def allocate_funds(self, amount):  # noqa: D401 — 테스트 스텁, 부수효과 없음
        return None


def _make_scheduler(registry: _FakeRegistry) -> MagicMock:
    scheduler = MagicMock()
    scheduler.registry = registry
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
    return scheduler


def _holding(ticker: str, *, avg_price: float = 10_000.0, quantity: int = 1) -> StockHolding:
    return StockHolding(
        ticker=ticker,
        name=f"종목{ticker}",
        quantity=quantity,
        sellable_quantity=quantity,
        avg_price=avg_price,
        purchase_amount=int(avg_price * quantity),
        current_price=int(avg_price),
        eval_amount=int(avg_price * quantity),
        eval_profit_loss=0,
        eval_profit_rate=0.0,
    )


def _summary() -> AccountSummary:
    return AccountSummary(
        deposit=0,
        stock_eval_amount=0,
        total_eval_amount=1_000_000,
        net_asset=1_000_000,
        purchase_total=0,
        eval_total=0,
        profit_loss_total=0,
    )


async def _run_boot(
    scheduler: MagicMock,
    *,
    holdings: list[StockHolding],
    db_positions: list[dict],
    recent_buy_strategy_map: dict[str, str | None],
    all_orders: list[dict],
    today_buys_rows: list[dict],
) -> None:
    async def _get_recent_buy_strategy(ticker):
        return recent_buy_strategy_map.get(ticker)

    with (
        patch("src.engine.boot_manager.token_manager") as tm,
        patch(
            "src.engine.boot_manager.get_balance",
            new=AsyncMock(return_value=(holdings, _summary())),
        ),
        patch(
            "src.engine.boot_manager.get_daily_orders",
            new=AsyncMock(return_value=all_orders),
        ),
        patch("src.engine.boot_manager.write_log", new=AsyncMock()),
        patch("src.db.stock_master.count_active", new=AsyncMock(return_value=2768)),
        patch("src.db.positions.load_all", new=AsyncMock(return_value=db_positions)),
        patch("src.db.positions.delete_position", new=AsyncMock()),
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch(
            "src.db.trade_history.get_recent_buy_strategy",
            new=AsyncMock(side_effect=_get_recent_buy_strategy),
        ),
        patch("src.db.trade_history.mark_pending_buys_completed", new=AsyncMock()),
        patch(
            "src.db.trade_history.get_today_buys_ticker_strategy",
            new=AsyncMock(return_value=today_buys_rows),
        ),
    ):
        tm.get_token = AsyncMock()
        await boot_manager.boot(scheduler)


def _db_position_row(
    ticker: str,
    strategy_id: str,
    *,
    buy_price: int = 10_000,
    quantity: int = 1,
) -> dict:
    return {
        "ticker": ticker,
        "ticker_name": f"종목{ticker}",
        "strategy_id": strategy_id,
        "buy_price": buy_price,
        "quantity": quantity,
        "order_no": "",
        "buy_date": None,
        "high_since_buy": 0,
    }


# ---------------------------------------------------------------------------
# 1. DB positions 복구 — registry.get(strategy_id) or registry.get("momentum")
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_db_position_unknown_strategy_falls_back_to_momentum():
    """DB 에 적힌 strategy_id 가 등록되지 않았으면 momentum 이 그 포지션을 받는다."""
    registry = _FakeRegistry(
        {
            "momentum": _FakeStrategy("momentum"),
            "volatility_breakout": _FakeStrategy("volatility_breakout"),
        }
    )
    scheduler = _make_scheduler(registry)

    db_positions = [_db_position_row("111111", "donchian_swing")]  # 미등록 전략
    holdings = [_holding("111111")]

    await _run_boot(
        scheduler,
        holdings=holdings,
        db_positions=db_positions,
        recent_buy_strategy_map={},
        all_orders=[],
        today_buys_rows=[],
    )

    momentum = registry.get("momentum")
    assert "111111" in momentum.state.positions
    assert momentum.state.positions["111111"].strategy_id == "momentum"
    assert "111111" not in registry.get("volatility_breakout").state.positions


@pytest.mark.asyncio
async def test_db_position_known_strategy_does_not_fall_back():
    """DB 에 적힌 strategy_id 가 등록돼 있으면 momentum 이 아니라 그 전략이 받는다."""
    registry = _FakeRegistry(
        {
            "momentum": _FakeStrategy("momentum"),
            "volatility_breakout": _FakeStrategy("volatility_breakout"),
        }
    )
    scheduler = _make_scheduler(registry)

    db_positions = [_db_position_row("222222", "volatility_breakout")]
    holdings = [_holding("222222")]

    await _run_boot(
        scheduler,
        holdings=holdings,
        db_positions=db_positions,
        recent_buy_strategy_map={},
        all_orders=[],
        today_buys_rows=[],
    )

    vb = registry.get("volatility_breakout")
    momentum = registry.get("momentum")
    assert "222222" in vb.state.positions
    assert vb.state.positions["222222"].strategy_id == "volatility_breakout"
    assert "222222" not in momentum.state.positions


# ---------------------------------------------------------------------------
# 2. KIS 잔고 보완 복구 — 기본값 "momentum" + trade_history 조회로 덮어쓰기
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kis_supplement_unknown_owner_defaults_to_momentum():
    """DB·trade_history 모두 모르는 보유는 momentum 기본값을 그대로 받는다."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    holdings = [_holding("333333")]

    await _run_boot(
        scheduler,
        holdings=holdings,
        db_positions=[],
        recent_buy_strategy_map={},  # get_recent_buy_strategy → None (모름)
        all_orders=[],
        today_buys_rows=[],
    )

    momentum = registry.get("momentum")
    assert "333333" in momentum.state.positions
    assert momentum.state.positions["333333"].strategy_id == "momentum"


@pytest.mark.asyncio
async def test_kis_supplement_known_owner_overrides_momentum_default():
    """trade_history 가 전략을 알면 momentum 기본값이 그 전략으로 덮인다."""
    registry = _FakeRegistry(
        {
            "momentum": _FakeStrategy("momentum"),
            "volatility_breakout": _FakeStrategy("volatility_breakout"),
        }
    )
    scheduler = _make_scheduler(registry)

    holdings = [_holding("444444")]

    await _run_boot(
        scheduler,
        holdings=holdings,
        db_positions=[],
        recent_buy_strategy_map={"444444": "volatility_breakout"},
        all_orders=[],
        today_buys_rows=[],
    )

    vb = registry.get("volatility_breakout")
    momentum = registry.get("momentum")
    assert "444444" in vb.state.positions
    assert "444444" not in momentum.state.positions


# ---------------------------------------------------------------------------
# 3. 미체결 매수 주문 복구 — db_strategy_map.get(ticker, "momentum") +
#    registry.get(strategy_id) or registry.get("momentum")
# ---------------------------------------------------------------------------
def _unfilled_order(ticker: str, order_no: str, *, price: int, qty: int) -> dict:
    return {
        "sll_buy_dvsn_cd": "02",
        "rmn_qty": str(qty),
        "pdno": ticker,
        "ord_unpr": str(price),
        "ord_qty": str(qty),
        "odno": order_no,
    }


@pytest.mark.asyncio
async def test_unfilled_order_unknown_ticker_falls_back_to_momentum():
    """db_strategy_map 에 없는 종목의 미체결 매수는 momentum 의 pending 으로 등록된다."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    orders = [_unfilled_order("555555", "ORDER1", price=1_000, qty=10)]

    await _run_boot(
        scheduler,
        holdings=[],
        db_positions=[],
        recent_buy_strategy_map={},
        all_orders=orders,
        today_buys_rows=[],
    )

    momentum = registry.get("momentum")
    assert "555555" in momentum.state.pending_buys
    assert momentum.state.pending_buy_amounts["555555"] == 10_000
    assert scheduler.order_engine._order_strategy["ORDER1"] == "momentum"


@pytest.mark.asyncio
async def test_unfilled_order_known_ticker_does_not_fall_back():
    """db_strategy_map 에 있는 종목의 미체결 매수는 그 전략의 pending 으로 등록된다."""
    registry = _FakeRegistry(
        {
            "momentum": _FakeStrategy("momentum"),
            "volatility_breakout": _FakeStrategy("volatility_breakout"),
        }
    )
    scheduler = _make_scheduler(registry)

    orders = [_unfilled_order("666666", "ORDER2", price=2_000, qty=5)]
    # db_strategy_map 은 db_positions ∪ today_buys_rows 에서 만들어진다.
    today_buys_rows = [{"ticker": "666666", "strategy": "volatility_breakout"}]

    await _run_boot(
        scheduler,
        holdings=[],
        db_positions=[],
        recent_buy_strategy_map={},
        all_orders=orders,
        today_buys_rows=today_buys_rows,
    )

    vb = registry.get("volatility_breakout")
    momentum = registry.get("momentum")
    assert "666666" in vb.state.pending_buys
    assert vb.state.pending_buy_amounts["666666"] == 10_000
    assert "666666" not in momentum.state.pending_buys
    assert scheduler.order_engine._order_strategy["ORDER2"] == "volatility_breakout"
