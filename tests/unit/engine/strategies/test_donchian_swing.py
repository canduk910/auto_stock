"""src/engine/strategies/donchian_swing.py 단위 테스트.

추세추종 멀티데이 전략. 검증 포인트:
- check_buy_signal: 09:05~09:30 시간 가드, 갭 +3% 스킵, 1회만 진입(_bought_today)
- check_exit_signal: 하드 손절 -7%, ATR×2 Chandelier 트레일링
- check_force_clear: 빈 리스트 (15:20 강제청산 없음 — 추세 끝까지 보유)
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
def test_exit_when_loss_breaches_minus_7_then_stop_loss(donchian):
    _seed_candidate(donchian, "005930", atr=1500)
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="donchian_swing",
    )
    # -7% 정확히 → STOP_LOSS
    assert donchian.check_exit_signal("005930", 93000, 100000) == Signal.STOP_LOSS


def test_exit_when_loss_within_threshold_then_none(donchian):
    _seed_candidate(donchian, "005930", atr=1500)
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="donchian_swing",
        high_since_buy=100000,
    )
    # -6% (loss_rate=-6 > stop_loss=-7) → 손절 미발동
    # ATR 트레일링: chandelier = 100000 - 1500*2 = 97000. current 94000 <= 97000 → TRAILING_STOP
    assert donchian.check_exit_signal("005930", 94000, 100000) == Signal.TRAILING_STOP


def test_exit_atr_trailing_when_drop_beyond_chandelier(donchian):
    _seed_candidate(donchian, "005930", atr=1000)
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="donchian_swing",
        high_since_buy=110000,  # 매수 후 고점 갱신됐다고 가정
    )
    # chandelier = 110000 - 1000*2 = 108000. current 107500 <= 108000 → TRAILING_STOP
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
# check_force_clear — 추세추종은 강제청산 없음
# ---------------------------------------------------------------------------
def test_force_clear_returns_empty_list_even_with_positions(donchian):
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="donchian_swing",
    )
    assert donchian.check_force_clear() == []


# ---------------------------------------------------------------------------
# calc_buy_quantity
# ---------------------------------------------------------------------------
def test_calc_qty_when_amount_covers_qty(donchian):
    donchian.state.total_investment = 10_000_000  # 20% = 2M
    assert donchian.calc_buy_quantity(current_price=100_000) == 20


def test_calc_qty_when_total_below_share_price_then_zero(donchian):
    donchian.state.total_investment = 30_000
    assert donchian.calc_buy_quantity(current_price=100_000) == 0
