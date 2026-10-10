"""cycle432 — 매도 조회 함수의 「주문내역 100건 꽉 참」(`page_full`) 판정 제거.

사용자 승인 2026-10-10 「100건 꽉 참 판정은 연속처리 넣었으니 제거하자」.

cycle430 이 `get_daily_orders`(TTTC0081R) 를 연속조회로 바꿔 쪽수 상한이
없어졌다(이어지지 않으면 `DailyOrdersPaginationStuckError`). 그 전제(단일
쪽만 읽는다)로 쓰여 있던 `order_engine._sell_orders_snapshot` 의
「len(rows) >= 환경별 page_size → `page_full`」 판정은 지금은 거짓 양성이다
— 한 종목 주문이 실전 100건·모의 15건 이상이어도 실제로는 잘리지 않았다.

행위 변경은 하나뿐이다 — 「한 종목 주문 ≥100건 → 지금까지는 불신, 이제는
정상 판정」. 그 외는 byte 단위로 같아야 한다(`timeout`·`error`·`bad_row`
3 사유와 「조회 불신 = 동결/보류」 동작은 그대로).
"""
from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit

_TICKER = "005930"


def _row(odno: str, qty, *, pdno: str = _TICKER) -> dict:
    return {
        "odno": odno, "pdno": pdno, "sll_buy_dvsn_cd": "01",
        "tot_ccld_qty": qty if isinstance(qty, str) else str(qty),
    }


# ---------------------------------------------------------------------------
# 1. page_full 제거 — 100건 초과 종목도 `ok` 로 간다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_120_orders_is_ok_not_page_full(monkeypatch):
    """한 종목 주문 120건(실전 page=100 초과) → `ok` + 정확한 fills."""
    import src.api.balance as bal
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_registry import StrategyRegistry

    rows = [_row(f"{i:010d}", 1) for i in range(120)]

    async def get_daily_orders(*a, **k):
        return rows

    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    eng = OrderEngine(StrategyRegistry())
    fills, reason, _pre = await eng._sell_orders_snapshot(_TICKER)

    assert reason == "ok", f"120건인데 reason={reason} (page_full 제거 전이면 page_full)"
    assert fills is not None and len(fills) == 120
    assert all(v == 1 for v in fills.values())


@pytest.mark.asyncio
async def test_15_orders_is_ok_not_page_full(monkeypatch):
    """옛 모의(page=15) 쪽 크기였던 15건도 `ok`(쪽 크기 상수 제거 확인)."""
    import src.api.balance as bal
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_registry import StrategyRegistry

    rows = [_row(f"{i:010d}", 1) for i in range(15)]

    async def get_daily_orders(*a, **k):
        return rows

    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    eng = OrderEngine(StrategyRegistry())
    fills, reason, _pre = await eng._sell_orders_snapshot(_TICKER)

    assert reason == "ok"
    assert fills is not None and len(fills) == 15


# ---------------------------------------------------------------------------
# 2. 연속조회 진행 멈춤 예외 → error (기존 bare except 가 흡수한다 — 코드
#    변경 없음, 회귀로 고정한다)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pagination_stuck_error_maps_to_error(monkeypatch):
    import src.api.balance as bal
    from src.api.balance import DailyOrdersPaginationStuckError
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_registry import StrategyRegistry

    async def get_daily_orders(*a, **k):
        raise DailyOrdersPaginationStuckError("pages=2 rows=100")

    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    eng = OrderEngine(StrategyRegistry())
    fills, reason, pre = await eng._sell_orders_snapshot(_TICKER)

    assert fills is None
    assert reason == "error"
    assert pre == frozenset()


# ---------------------------------------------------------------------------
# 3. timeout·bad_row 는 그대로다(회귀)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_timeout_still_maps_to_timeout(monkeypatch):
    import asyncio

    import src.api.balance as bal
    import src.engine.order_engine as _oe
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_registry import StrategyRegistry

    monkeypatch.setattr(_oe, "SELL_ORDERS_QUERY_TIMEOUT", 0.01, raising=False)

    async def get_daily_orders(*a, **k):
        await asyncio.sleep(0.5)
        return []

    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    eng = OrderEngine(StrategyRegistry())
    fills, reason, pre = await eng._sell_orders_snapshot(_TICKER)

    assert fills is None
    assert reason == "timeout"
    assert pre == frozenset()


@pytest.mark.asyncio
async def test_bad_row_still_maps_to_bad_row(monkeypatch):
    import src.api.balance as bal
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_registry import StrategyRegistry

    async def get_daily_orders(*a, **k):
        return [_row("0000031001", "")]  # 수량 공백 — 불량 행

    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    eng = OrderEngine(StrategyRegistry())
    fills, reason, pre = await eng._sell_orders_snapshot(_TICKER)

    assert fills is None
    assert reason == "bad_row"
    assert pre == frozenset()


# ---------------------------------------------------------------------------
# 4. 상수·시그니처 제거 확인
# ---------------------------------------------------------------------------
def test_page_constants_removed():
    import src.engine.order_engine as oe

    assert not hasattr(oe, "_DAILY_ORDERS_PAGE_REAL")
    assert not hasattr(oe, "_DAILY_ORDERS_PAGE_VTS")


def test_sell_fills_by_order_signature_has_no_page_param():
    from src.engine.order_engine import _sell_fills_by_order

    params = list(inspect.signature(_sell_fills_by_order).parameters)
    assert params == ["rows", "ticker"], params


def test_sell_fills_by_order_accepts_over_100_rows_directly():
    from src.engine.order_engine import _sell_fills_by_order

    rows = [_row(f"{i:010d}", 1) for i in range(150)]
    got = _sell_fills_by_order(rows, _TICKER)
    assert got is not None and len(got) == 150
