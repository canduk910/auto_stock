"""Phase G Red — 익일 청산 분기에 stock_master `nxt_tradable` 사전 판별 통합.

기존 `test_next_day_clear_nxt_eligibility.py` 는 WebSocket 시가 수신 여부만으로
NXT 거래가능성을 추론했다. 이제 KIS CTPF1002R 응답에서 파생된
`stock_master.nxt_tradable` 을 1순위로 사용한다.

요구 행위 (`scheduler._execute_next_day_clear`):

1. `stock_master.get(ticker).nxt_tradable=False` 면 NXT 시가 수신/안정화 *대기 없이*
   즉시 `_pending_next_day_clear` 등록. (NXT 주문 시도 0)
2. `stock_master.get(ticker).nxt_tradable=True` + 시가 수신 → 기존 NXT 지정가 매도.
3. stock_master 캐시 miss → 기존 시가 수신 휴리스틱으로 fallback.

이 테스트는 (1) 만 검증한다 — (2)(3) 회귀는 기존 파일이 커버.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.engine.strategy_base import Position, Signal

pytestmark = pytest.mark.integration


def _seed_next_day_pos(strategy, ticker, buy_price=15000, qty=6):
    pos = Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=qty,
        order_no="ORIG-NEXT",
        strategy_id=strategy.strategy_id,
        buy_date=date.today() - timedelta(days=1),
        high_since_buy=buy_price,
    )
    strategy.state.positions[ticker] = pos
    return pos


@pytest.fixture
def stub_stock_master_get(monkeypatch: pytest.MonkeyPatch):
    """src.db.stock_master.get 을 nxt_tradable 분기로 stub."""

    def _setup(*, nxt_tradable: bool | None):
        from src.models.stock import StockBasics

        async def _get(ticker: str):
            if nxt_tradable is None:
                return None
            return StockBasics(
                ticker=ticker,
                name="",
                excg_dvsn_cd="02",
                nxt_tradable=nxt_tradable,
                krx_halted=False,
                admin_item=False,
                raw={},
            )

        import src.db.stock_master as _sm

        monkeypatch.setattr(_sm, "get", _get)
        # scheduler 가 lazy import 한 alias 도 패치
        import src.engine.scheduler as _sched_mod

        if hasattr(_sched_mod, "stock_master_get"):
            monkeypatch.setattr(_sched_mod, "stock_master_get", _get, raising=False)
        return _get

    return _setup


# ---------------------------------------------------------------------------
# 1) stock_master.nxt_tradable=False → 즉시 보류 (NXT 시가 수신 여부 무관)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_next_day_clear_pending_when_stock_master_says_not_nxt_tradable(
    scheduler_env,
    stub_stock_master_get,
):
    """stock_master 가 nxt_tradable=False 로 응답 → NXT 청산 시도 0건 + pending 등록.

    시가 수신과 *무관*: 시가가 들어와 있어도 stock_master 가 거부하면 보류해야 한다
    (사전 차단 의미가 있으려면 시가 휴리스틱보다 우선해야 함).
    """
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200", buy_price=15000)

    # NXT 시가가 어떻게든 들어와 있더라도 stock_master 가 우선
    from src.engine import scanner
    scanner.ticker_prices["012200"] = {"open_price": 15050, "current_price": 15050}

    stub_stock_master_get(nxt_tradable=False)

    await sched._execute_next_day_clear()

    # NXT 주문 시도 0 — 시가가 있어도 stock_master 가 차단
    assert scheduler_env.calls.execute_sell == [], (
        "stock_master 가 nxt_tradable=False 면 시가 수신 무관 즉시 보류"
    )
    assert "012200" in momentum.state.positions
    assert ("012200", "momentum") in sched._pending_next_day_clear


# ---------------------------------------------------------------------------
# 2) stock_master.nxt_tradable=True → 기존 분기 (회귀 가드)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_next_day_clear_uses_existing_path_when_stock_master_says_tradable(
    scheduler_env,
    stub_stock_master_get,
):
    """nxt_tradable=True + NXT 시가 수신 + 갭률 < threshold → NXT 지정가 매도 (기존 동작)."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200", buy_price=15000)

    from src.engine import scanner
    scanner.ticker_prices["012200"] = {"open_price": 15050, "current_price": 15050}

    stub_stock_master_get(nxt_tradable=True)

    await sched._execute_next_day_clear()

    sells = scheduler_env.calls.execute_sell
    assert len(sells) == 1
    assert sells[0]["ticker"] == "012200"
    # 갭률 미만 → 지정가 매도
    assert sells[0].get("limit_price", 0) > 0


# ---------------------------------------------------------------------------
# 3) stock_master cache miss → 기존 시가 휴리스틱 fallback (회귀 가드)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_next_day_clear_falls_back_when_stock_master_miss(
    scheduler_env,
    stub_stock_master_get,
):
    """캐시 miss + 시가 수신 → 기존 분기 동작."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200", buy_price=15000)

    from src.engine import scanner
    scanner.ticker_prices["012200"] = {"open_price": 15050, "current_price": 15050}

    stub_stock_master_get(nxt_tradable=None)

    await sched._execute_next_day_clear()

    sells = scheduler_env.calls.execute_sell
    assert len(sells) == 1
    assert sells[0]["ticker"] == "012200"
