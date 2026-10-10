"""cycle431 — 그날 재도출 눈금 가드(C8·C9). 사용자 결정 2026-10-10(안1).

"반영한 종목은 그날 하루 재도출 결과를 버린다" — `corporate_action_reconcile
.is_rescaled_today(ticker)` 가 참이면 kojiro `recompute_held_atr` · donchian
`_rederive_breakout_high`/`recompute_held_atr` · 공유 `_rederive_entry_atr`/
`_apply_high_since_buy_from_candles` 가 그 종목을 통째로 건너뛴다(스탬프는
07:45 부팅이 방금 옮긴 값 그대로 유지).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import corporate_action_reconcile as car
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import Position, StrategyConfig
from tests.unit.engine.strategies.test_kojiro_high_since_buy_recovery import (
    _Recorder,
    _hold as _kojiro_hold,
    _kis_candle,
    _kojiro,
    _today,
)

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


@pytest.fixture(autouse=True)
def _reset_state():
    car.reset_state_for_test()
    yield
    car.reset_state_for_test()


# ---------------------------------------------------------------------------
# C8 — kojiro `recompute_held_atr`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c8_kojiro_recompute_skips_rescaled_ticker():
    s = _kojiro()
    pos = _kojiro_hold(s, ticker="001390", buy=1_000, high=1_200, days_ago=5)
    car.mark_rescaled_today("001390")

    old_scale_candles = [_kis_candle(_today() - timedelta(days=i), 50_000) for i in range(1, 90)]
    with _Recorder({"001390": old_scale_candles}) as rec:
        await s.recompute_held_atr()

    # 재도출이 전혀 시도되지 않는다 — candles fetch 조차 안 한다(그 종목 skip).
    assert "001390" not in rec.fetch_calls
    assert "001390" not in s._candidates
    assert pos.high_since_buy == 1_200  # 옛 눈금 고가(50,000)로 끌어올려지지 않았다
    rec.update_high.assert_not_called()


@pytest.mark.asyncio
async def test_kojiro_recompute_runs_normally_when_not_rescaled():
    """대조군 — 반영 안 된 종목은 평소처럼 재도출된다."""
    s = _kojiro()
    _kojiro_hold(s, ticker="002222", buy=1_000, high=1_000, days_ago=5)

    candles = [_kis_candle(_today() - timedelta(days=i), 1_100 + i) for i in range(1, 90)]
    with _Recorder({"002222": candles}) as rec:
        await s.recompute_held_atr()

    assert "002222" in rec.fetch_calls
    assert "002222" in s._candidates


# ---------------------------------------------------------------------------
# C9 — donchian `_rederive_breakout_high` / `_rederive_entry_atr`(공유 base)
# ---------------------------------------------------------------------------


def _donchian() -> DonchianSwingStrategy:
    return DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.5, params={}),
    )


def test_c9_donchian_rederive_breakout_high_skips_rescaled_ticker():
    s = _donchian()
    pos = Position(
        ticker="011690", buy_price=10_000, quantity=1, order_no="O1",
        strategy_id="donchian_swing", buy_date=_today() - timedelta(days=5),
    )
    car.mark_rescaled_today("011690")

    candles = [
        {"stck_bsop_date": (_today() - timedelta(days=i)).strftime("%Y%m%d"), "stck_hgpr": "500000"}
        for i in range(1, 40)
    ]
    s._rederive_breakout_high("011690", pos, candles, donchian_period=20)

    assert "011690" not in s._breakout_high  # 옛 눈금 고가로 무장되지 않았다


def test_rederive_entry_atr_skips_rescaled_ticker():
    s = _donchian()
    pos = Position(
        ticker="033333", buy_price=10_000, quantity=1, order_no="O2",
        strategy_id="donchian_swing", buy_date=_today() - timedelta(days=5),
    )
    car.mark_rescaled_today("033333")

    candles = [
        {
            "stck_bsop_date": (_today() - timedelta(days=i)).strftime("%Y%m%d"),
            "stck_hgpr": "500000", "stck_lwpr": "490000", "stck_clpr": "495000",
        }
        for i in range(10, 40)
    ]
    s._rederive_entry_atr("033333", pos, candles, atr_period=14)

    assert "033333" not in s._entry_atr


@pytest.mark.asyncio
async def test_apply_high_since_buy_from_candles_skips_rescaled_ticker():
    s = _donchian()
    pos = Position(
        ticker="044444", buy_price=1_000, quantity=1, order_no="O3",
        strategy_id="donchian_swing", buy_date=_today() - timedelta(days=5),
        high_since_buy=1_200,
    )
    car.mark_rescaled_today("044444")

    old_scale_candles = [
        {
            "stck_bsop_date": (_today() - timedelta(days=i)).strftime("%Y%m%d"),
            "stck_hgpr": "500000",
        }
        for i in range(1, 4)
    ]
    with patch("src.db.positions.update_high", new=AsyncMock()) as update_mock:
        await s._apply_high_since_buy_from_candles(pos, old_scale_candles, _today())

    assert pos.high_since_buy == 1_200  # 끌어올려지지 않았다
    update_mock.assert_not_called()
