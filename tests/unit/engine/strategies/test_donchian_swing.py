"""src/engine/strategies/donchian_swing.py 단위 테스트.

추세추종 멀티데이 전략. 검증 포인트:
- check_buy_signal: 09:05~09:30 시간 가드, 갭 +3% 스킵, 1회만 진입(_bought_today)
- check_exit_signal: (cycle405) −1R 손절(R = max(8%, 1.5×진입 ATR)) · 3R 뒤 본전 · 3R 뒤 10일 저가 채널
- check_force_clear: (cycle405) 20봉 +1R 미도달·250봉만 — 오늘 산 보유는 넣지 않는다
"""

from __future__ import annotations

from datetime import datetime

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def donchian():
    return DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="20일 신고가", weight=0.2)
    )


def _seed_candidate(strategy, ticker, *, prev_close=70000, donchian_high=72000, ema60=68000, atr=1500):
    strategy._candidates[ticker] = {
        "prev_close": prev_close,
        "donchian_high": donchian_high,
        "ema60": ema60,
        "atr": atr,
    }


# ---------------------------------------------------------------------------
# DEFAULT_PARAMS 검증
# ---------------------------------------------------------------------------
def test_default_params_thresholds():
    p = DonchianSwingStrategy.DEFAULT_PARAMS
    assert p["tradable_boards"] == ["main"]
    assert p["donchian_period"] == 20
    assert p["long_ma_period"] == 60
    assert p["volume_period"] == 20
    assert p["volume_multiplier"] == 1.5
    assert p["atr_period"] == 14
    assert p["atr_trail_mult"] == 2.0
    assert p["gap_skip_threshold"] == 3.0
    assert p["stop_loss_rate"] == -7.0


# ---------------------------------------------------------------------------
# check_buy_signal — 시간 가드
# ---------------------------------------------------------------------------
def test_buy_when_before_0905_then_none(donchian):
    _seed_candidate(donchian, "005930")
    with freeze_time("2026-05-08 09:04:00"):
        assert donchian.check_buy_signal("005930", 73000, 71000) == Signal.NONE


def test_buy_when_after_0930_then_none(donchian):
    _seed_candidate(donchian, "005930")
    with freeze_time("2026-05-08 09:31:00"):
        assert donchian.check_buy_signal("005930", 73000, 71000) == Signal.NONE


def test_buy_within_time_window_and_no_gap_then_buy(donchian):
    _seed_candidate(donchian, "005930", prev_close=70000)
    donchian.state.total_investment = 10_000_000   # cycle405 — 설계 랏 0 이면 신호 단계에서 거른다
    with freeze_time("2026-05-08 09:10:00"):
        # 시가 71400 → 갭 +2% (gap_skip 3% 미만), 진입 OK
        assert donchian.check_buy_signal("005930", 73000, 71400) == Signal.BUY
    assert "005930" in donchian._bought_today


def test_buy_when_gap_above_3pct_then_skip_and_marked(donchian):
    _seed_candidate(donchian, "005930", prev_close=70000)
    with freeze_time("2026-05-08 09:10:00"):
        # 시가 72200 → 갭 +3.14% > 3% → 스킵 + bought_today 등록(재시도 차단)
        assert donchian.check_buy_signal("005930", 73000, 72200) == Signal.NONE
    assert "005930" in donchian._bought_today


def test_buy_when_already_in_bought_today_then_none(donchian):
    _seed_candidate(donchian, "005930")
    donchian._bought_today.add("005930")
    with freeze_time("2026-05-08 09:10:00"):
        assert donchian.check_buy_signal("005930", 73000, 71000) == Signal.NONE


def test_buy_when_no_candidate_then_none(donchian):
    # _candidates 에 없는 종목
    with freeze_time("2026-05-08 09:10:00"):
        assert donchian.check_buy_signal("005930", 73000, 71000) == Signal.NONE


def test_buy_when_already_held_then_none(donchian):
    _seed_candidate(donchian, "005930")
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="donchian_swing",
    )
    with freeze_time("2026-05-08 09:10:00"):
        assert donchian.check_buy_signal("005930", 73000, 71000) == Signal.NONE


def test_buy_when_buy_disabled_then_none(donchian):
    _seed_candidate(donchian, "005930")
    donchian.state.buy_disabled = True
    with freeze_time("2026-05-08 09:10:00"):
        assert donchian.check_buy_signal("005930", 73000, 71000) == Signal.NONE


# ---------------------------------------------------------------------------
# check_exit_signal — 하드 손절 + ATR 트레일링
# ---------------------------------------------------------------------------
def test_exit_when_price_at_entry_minus_r_then_stop_loss(donchian):
    """cycle405 — 스탬프 없음 → R = 8% → 손절선 92,000 (옛 −7% 고정 손절 아님)."""
    _seed_candidate(donchian, "005930", atr=1500)
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="donchian_swing",
    )
    assert donchian.check_exit_signal("005930", 93000, 100000) == Signal.NONE
    assert donchian.check_exit_signal("005930", 92000, 100000) == Signal.STOP_LOSS


def test_exit_when_loss_within_r_then_none_no_chandelier(donchian):
    _seed_candidate(donchian, "005930", atr=1500)
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="donchian_swing",
        high_since_buy=100000,
    )
    # −6% — 손절선(92,000) 위. 옛 샹들리에(97,000)는 없어졌다 → NONE
    assert donchian.check_exit_signal("005930", 94000, 100000) == Signal.NONE


def test_exit_channel_only_after_3r(donchian):
    _seed_candidate(donchian, "005930", atr=1000)
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="donchian_swing",
        high_since_buy=110000,
    )
    donchian._channel_low["005930"] = 108000
    # 무장 전(고점 110,000 < E+3R 124,000) — 채널·샹들리에 모두 보지 않는다
    assert donchian.check_exit_signal("005930", 107500, 100000) == Signal.NONE
    donchian.state.positions["005930"].high_since_buy = 124000
    assert donchian.check_exit_signal("005930", 107500, 100000) == Signal.TRAILING_STOP


def test_exit_atr_trailing_when_above_chandelier_then_none(donchian):
    _seed_candidate(donchian, "005930", atr=1000)
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="donchian_swing",
        high_since_buy=110000,
    )
    # chandelier 108000. current 109000 > 108000 → NONE
    assert donchian.check_exit_signal("005930", 109000, 100000) == Signal.NONE


def test_exit_when_no_position_then_none(donchian):
    assert donchian.check_exit_signal("005930", 50000, 100000) == Signal.NONE


# ---------------------------------------------------------------------------
# check_force_clear — cycle405: 20봉·250봉 시간 청산만. 오늘 산 보유는 넣지 않는다
# ---------------------------------------------------------------------------
def test_force_clear_returns_empty_list_for_fresh_position(donchian):
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="donchian_swing",
    )
    assert donchian.check_force_clear() == []


# ---------------------------------------------------------------------------
# calc_buy_quantity
# ---------------------------------------------------------------------------
def test_calc_qty_when_amount_covers_qty(donchian):
    """cycle405 — R = max(8%·100,000, 1.5×1,500) = 8,000 → floor(10M×0.012/8,000) = 15 (명목 상한 15)."""
    donchian.state.total_investment = 10_000_000
    _seed_candidate(donchian, "005930", atr=1500)
    assert donchian.calc_buy_quantity(current_price=100_000, ticker="005930") == 15


def test_calc_qty_without_ticker_or_atr_then_zero(donchian):
    """cycle405 — ATR(N) 없이는 사지 않는다(스탬프 없는 랏 금지, 비중 낙하 없음)."""
    donchian.state.total_investment = 10_000_000
    assert donchian.calc_buy_quantity(current_price=100_000) == 0


def test_calc_qty_when_total_below_share_price_then_zero(donchian):
    donchian.state.total_investment = 30_000
    assert donchian.calc_buy_quantity(current_price=100_000) == 0
