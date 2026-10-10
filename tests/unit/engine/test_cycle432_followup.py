"""cycle432 — cycle428(F-422-1) 후속 LOW 2건.

(a) `selling_reconcile.reconcile_selling_unknown_one` — 180초 뒤 그 종목이
    이미 `order_engine._selling` 에 없으면(체결통보가 먼저 풀었음) 판정하지
    않는다. `result=already_released` 로 마커 1행만 남기고 반환한다. KIS
    조회도 하지 않는다. 지금까지는 이 경우 `not_accepted` 로 잘못 기록됐다
    (조회까지 한 뒤에).

(b) `order_engine.SELL_UNKNOWN_RECONCILE_DELAY_S` 와
    `selling_reconcile.SELLING_RECONCILE_MIN_AGE_S` 는 같은 객체다(leaf 정본
    하나, order_engine 은 alias). `scheduler.py` 의 같은 이름 상수는 이번
    사이클 승인 범위 밖이라 값만 같다(별도 리터럴).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

_T = "005930"
_SID = "kojiro"


def _recs(caplog, level: int, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno == level and r.getMessage().startswith(prefix)
    ]


# ---------------------------------------------------------------------------
# (a) already_released — 0 조회
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_already_released_skips_kis_query_entirely(monkeypatch, caplog):
    import src.api.balance as bal
    from src.engine.selling_reconcile import reconcile_selling_unknown_one

    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    get_balance = AsyncMock(side_effect=AssertionError("KIS 조회 — 호출되면 안 된다"))
    get_daily_orders = AsyncMock(side_effect=AssertionError("KIS 조회 — 호출되면 안 된다"))
    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    eng = SimpleNamespace(_selling=set(), _selling_since={})  # 이미 체결통보가 풀었다

    result = await reconcile_selling_unknown_one(eng, _T, _SID, min_age_s=180.0)

    assert result == "already_released"
    get_balance.assert_not_called()
    get_daily_orders.assert_not_called()
    rows = _recs(caplog, logging.WARNING, "[sell_send_unknown_resolved] ")
    assert rows == [
        f"[sell_send_unknown_resolved] ticker={_T} strategy={_SID} result=already_released"
    ]


@pytest.mark.asyncio
async def test_still_selling_goes_through_normal_lookup(monkeypatch, caplog):
    """대조 — `_selling` 에 아직 있으면 평소대로 조회한다(변경 없음)."""
    import src.api.balance as bal
    from src.engine.selling_reconcile import reconcile_selling_unknown_one

    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    get_balance = AsyncMock(return_value=([], SimpleNamespace(net_asset=0)))
    get_daily_orders = AsyncMock(return_value=[])
    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    eng = SimpleNamespace(_selling={_T}, _selling_since={})

    result = await reconcile_selling_unknown_one(eng, _T, _SID, min_age_s=180.0)

    assert result == "closed"  # 보유 0 → held_zero → closed
    get_balance.assert_awaited_once()
    get_daily_orders.assert_awaited_once()


# ---------------------------------------------------------------------------
# (b) 두 상수는 같은 객체다
# ---------------------------------------------------------------------------
def test_order_engine_delay_is_selling_reconcile_min_age_same_object():
    from src.engine import order_engine, selling_reconcile

    assert (
        order_engine.SELL_UNKNOWN_RECONCILE_DELAY_S
        is selling_reconcile.SELLING_RECONCILE_MIN_AGE_S
    ), "두 상수가 같은 객체가 아니다 — leaf 정본 하나로 묶이지 않았다"
    assert order_engine.SELL_UNKNOWN_RECONCILE_DELAY_S == 180.0
