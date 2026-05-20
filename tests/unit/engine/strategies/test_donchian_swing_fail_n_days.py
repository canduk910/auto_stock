"""사이클 23 P2-2 Red — donchian breakout_fail_n_days 시간 기반 청산.

요구 행위:
1. N=5일 보유 + 현재가 < 돌파선 → STOP_LOSS
2. N=5일 미달 (3일) 보유 → NONE (시간 가드 진입 안 함)
3. `_breakout_high[ticker]` 등록 누락 (0) → graceful skip, 다른 청산 분기로 진행
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


def _make_strat(n_days: int = 5):
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.0)
    )
    strat.config.params["breakout_fail_n_days"] = n_days
    return strat


def _add_position(strat, ticker, buy_date, buy_price=10_000):
    from src.engine.strategy_base import Position
    pos = Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=10,
        order_no="ORD001",
        strategy_id="donchian_swing",
        buy_date=buy_date,
    )
    pos.high_since_buy = buy_price
    strat.state.positions[ticker] = pos
    # ATR 후보 등록 (ATR 트레일링 분기 제외 용)
    strat._candidates[ticker] = {
        "prev_close": buy_price,
        "atr": 0,  # 0이면 트레일링 SKIP
        "ema60": 9_000,
        "donchian_high": 11_000,
    }
    return pos


# ---------------------------------------------------------------------------
# 케이스 1: N=5일 보유 + 현재가 < 돌파선 → STOP_LOSS
# ---------------------------------------------------------------------------
@freeze_time("2026-05-25 10:00:00+09:00")
def test_fail_n_days_triggers_stop_loss_after_n_days():
    """N=5일 보유 + 현재가 < 돌파선 → STOP_LOSS."""
    strat = _make_strat(n_days=5)
    ticker = "005930"
    buy_date = date(2026, 5, 20)  # 5일 전
    pos = _add_position(strat, ticker, buy_date, buy_price=10_000)

    # 돌파선 = 11,000 등록
    strat._breakout_high[ticker] = 11_000
    # 현재가 < 돌파선 (10,500 < 11,000)
    # 하드 손절 -7% 미발동 (매수가 10,000 → 손절선 9,300 > 10,500)
    sig = strat.check_exit_signal(ticker, 10_500, 10_200)
    assert sig == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# 케이스 2: N=5일 미달 (3일) 보유 → NONE
# ---------------------------------------------------------------------------
@freeze_time("2026-05-23 10:00:00+09:00")
def test_fail_n_days_does_not_trigger_before_n_days():
    """N=5일 미달 3일 보유 → 시간 가드 미발동, NONE."""
    strat = _make_strat(n_days=5)
    ticker = "005930"
    buy_date = date(2026, 5, 20)  # 3일 전
    pos = _add_position(strat, ticker, buy_date, buy_price=10_000)

    strat._breakout_high[ticker] = 11_000
    # 현재가 < 돌파선이지만 보유 3일 < 5일
    sig = strat.check_exit_signal(ticker, 10_500, 10_200)
    assert sig == Signal.NONE


# ---------------------------------------------------------------------------
# 케이스 3: _breakout_high 미등록 (0) → graceful skip
# ---------------------------------------------------------------------------
@freeze_time("2026-05-25 10:00:00+09:00")
def test_fail_n_days_graceful_when_breakout_high_missing():
    """_breakout_high 미등록 시 graceful skip, 다른 청산 분기로 진행 → NONE."""
    strat = _make_strat(n_days=5)
    ticker = "005930"
    buy_date = date(2026, 5, 20)  # 5일 전
    pos = _add_position(strat, ticker, buy_date, buy_price=10_000)

    # _breakout_high 에 등록 안 함 (get 기본값 0)
    # 현재가 > 손절선, ATR=0 → NONE
    sig = strat.check_exit_signal(ticker, 10_500, 10_200)
    assert sig == Signal.NONE
