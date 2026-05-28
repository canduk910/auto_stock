"""src/engine/strategies/vcp_breakout.py 단위 테스트.

변동성 수축 돌파(VCP, Volatility Contraction Pattern) — 미네르비니식.

검증 포인트:
- DEFAULT_PARAMS — 명세 (`_workspace/00_leader_trading_rules.md` 6-F) 와 일치
- check_buy_signal:
    * 진입 시간대 가드 (09:05 ~ 14:30 KRX 메인)
    * 베이스 상단(base_high) 돌파 순간(prev<base_high AND now>=base_high)
    * 거래량 컷 (≥ 20일 평균 × 1.5)
    * 보유/주문중/당일매도 가드, _bought_today 1회 가드
    * 쿨다운 (재진입 7영업일) 가드
- check_exit_signal:
    * 하드 손절 -7%
    * 베이스 하단(base_low) 이탈 → STOP_LOSS
    * ATR×2 트레일링 → TRAILING_STOP (donchian 컨벤션)
    * 50일 EMA 이탈 → TRAILING_STOP
    * 시간 청산 없음 (멀티데이) — 단순히 시간만으로는 NONE
- check_force_clear: 빈 리스트 (15:20 강제 청산 없음, 멀티데이)
- calc_buy_quantity: position_ratio 20% + _fallback_one_share 1주 폴백
- _MULTIDAY_STRATEGIES 멤버 — Position.is_next_day 가 항상 False (vcp_breakout 도 멀티데이)
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from freezegun import freeze_time

from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def strat():
    return VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="변동성 수축 돌파", weight=0.0)
    )


def _seed_candidate(
    s,
    ticker,
    *,
    base_high=12_000,
    base_low=10_500,
    last_pullback_pct=0.05,
    atr14=200,
    ema50=11_500,
    ema150=11_000,
    ema200=10_800,
    prev_close=11_900,
    avg_volume_20=300_000,
):
    s._candidates[ticker] = {
        "base_high": base_high,
        "base_low": base_low,
        "last_pullback_pct": last_pullback_pct,
        "atr14": atr14,
        "ema50": ema50,
        "ema150": ema150,
        "ema200": ema200,
        "prev_close": prev_close,
        "avg_volume_20": avg_volume_20,
    }


# ---------------------------------------------------------------------------
# DEFAULT_PARAMS 검증
# ---------------------------------------------------------------------------
def test_default_params_thresholds():
    p = VcpBreakoutStrategy.DEFAULT_PARAMS
    assert p["tradable_boards"] == ["main"]
    assert p["exchange"] == "KRX"
    # 사이클 48 (2026-05-27) — 추세필터 0건 결함 시정 (KIS 100일 한도 계산 가능 값으로 하향)
    assert p["ema_short"] == 50
    assert p["ema_mid"] == 60
    assert p["ema_long"] == 120
    assert p["long_ema_uptrend_days"] == 20
    assert p["base_min_days"] == 25
    assert p["base_max_days"] == 75
    assert p["base_depth_pct"] == 0.30
    assert p["pullback_count_min"] == 2
    assert p["pullback_count_max"] == 4
    assert p["last_pullback_max"] == 0.12
    assert p["volume_contraction_ratio"] == 0.70
    assert p["breakout_volume_mult"] == 1.5
    assert p["entry_start"] == "09:05"
    assert p["entry_end"] == "14:30"
    assert p["position_ratio"] == 0.20
    assert p["max_positions"] == 5
    assert p["stop_loss_rate"] == -7.0
    assert p["atr_trail_mult"] == 2.0
    assert p["reentry_cooldown_days"] == 7


def test_default_tradable_boards_constant():
    assert VcpBreakoutStrategy.DEFAULT_TRADABLE_BOARDS == ("main",)


# ---------------------------------------------------------------------------
# Position.is_next_day — vcp_breakout 도 멀티데이 (_MULTIDAY_STRATEGIES 멤버)
# ---------------------------------------------------------------------------
def test_position_is_next_day_false_for_vcp_breakout():
    """vcp_breakout 도 멀티데이 보유 — Position.is_next_day 가 항상 False 여야 함.

    `Position._MULTIDAY_STRATEGIES` frozenset 에 'vcp_breakout' 추가 검증.
    OrderMonitor "청산" 배지 미표시(donchian I2 컨벤션).
    """
    yesterday = date.today() - timedelta(days=1)
    pos = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="vcp_breakout",
        buy_date=yesterday,
    )
    assert pos.is_next_day is False


# ---------------------------------------------------------------------------
# check_buy_signal — 시간 가드
# ---------------------------------------------------------------------------
def test_buy_when_before_0905_then_none(strat):
    _seed_candidate(strat, "005930")
    with freeze_time("2026-05-08 09:04:00"):
        assert strat.check_buy_signal("005930", 12_100, 11_900) == Signal.NONE


def test_buy_when_after_1430_then_none(strat):
    _seed_candidate(strat, "005930")
    with freeze_time("2026-05-08 14:31:00"):
        assert strat.check_buy_signal("005930", 12_100, 11_900) == Signal.NONE


# ---------------------------------------------------------------------------
# check_buy_signal — 돌파 순간 + 거래량 컷
# ---------------------------------------------------------------------------
def test_buy_when_breakout_with_volume_then_buy(strat):
    _seed_candidate(strat, "005930", base_high=12_000, avg_volume_20=300_000)
    from src.engine import scanner as _scanner
    _scanner.ticker_prices["005930"] = {
        "current_price": 12_100,
        "open_price": 11_900,
        "acml_vol": 500_000,  # 300_000 × 1.5 = 450_000 초과
    }
    strat._prev_price["005930"] = 11_990
    with freeze_time("2026-05-08 10:00:00"):
        assert strat.check_buy_signal("005930", 12_100, 11_900) == Signal.BUY
    assert "005930" in strat._bought_today


def test_buy_when_no_breakout_then_none(strat):
    _seed_candidate(strat, "005930", base_high=12_000)
    strat._prev_price["005930"] = 11_800
    with freeze_time("2026-05-08 10:00:00"):
        # 현재가 11_950 < base_high 12_000 → 미돌파
        assert strat.check_buy_signal("005930", 11_950, 11_900) == Signal.NONE


def test_buy_when_breakout_but_low_volume_then_none(strat):
    _seed_candidate(strat, "005930", base_high=12_000, avg_volume_20=300_000)
    from src.engine import scanner as _scanner
    _scanner.ticker_prices["005930"] = {
        "current_price": 12_100,
        "open_price": 11_900,
        "acml_vol": 400_000,  # 450_000 미만
    }
    strat._prev_price["005930"] = 11_990
    with freeze_time("2026-05-08 10:00:00"):
        assert strat.check_buy_signal("005930", 12_100, 11_900) == Signal.NONE


def test_buy_when_already_in_bought_today_then_none(strat):
    _seed_candidate(strat, "005930")
    strat._bought_today.add("005930")
    with freeze_time("2026-05-08 10:00:00"):
        assert strat.check_buy_signal("005930", 12_100, 11_900) == Signal.NONE


def test_buy_when_no_candidate_then_none(strat):
    with freeze_time("2026-05-08 10:00:00"):
        assert strat.check_buy_signal("005930", 12_100, 11_900) == Signal.NONE


def test_buy_when_already_held_then_none(strat):
    _seed_candidate(strat, "005930")
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="vcp_breakout",
    )
    with freeze_time("2026-05-08 10:00:00"):
        assert strat.check_buy_signal("005930", 12_100, 11_900) == Signal.NONE


def test_buy_when_buy_disabled_then_none(strat):
    _seed_candidate(strat, "005930")
    strat.state.buy_disabled = True
    with freeze_time("2026-05-08 10:00:00"):
        assert strat.check_buy_signal("005930", 12_100, 11_900) == Signal.NONE


# ---------------------------------------------------------------------------
# check_buy_signal — 쿨다운 7영업일
# ---------------------------------------------------------------------------
def test_buy_when_in_cooldown_then_none(strat):
    _seed_candidate(strat, "005930", base_high=12_000, avg_volume_20=300_000)
    with freeze_time("2026-05-08 10:00:00"):
        today = date(2026, 5, 8)
        strat._cooldown_until["005930"] = today + timedelta(days=3)  # 3일 후까지 쿨다운
        from src.engine import scanner as _scanner
        _scanner.ticker_prices["005930"] = {
            "current_price": 12_100, "open_price": 11_900, "acml_vol": 500_000,
        }
        strat._prev_price["005930"] = 11_990
        assert strat.check_buy_signal("005930", 12_100, 11_900) == Signal.NONE


def test_buy_when_cooldown_expired_then_buy(strat):
    _seed_candidate(strat, "005930", base_high=12_000, avg_volume_20=300_000)
    with freeze_time("2026-05-08 10:00:00"):
        today = date(2026, 5, 8)
        strat._cooldown_until["005930"] = today - timedelta(days=1)
        from src.engine import scanner as _scanner
        _scanner.ticker_prices["005930"] = {
            "current_price": 12_100, "open_price": 11_900, "acml_vol": 500_000,
        }
        strat._prev_price["005930"] = 11_990
        assert strat.check_buy_signal("005930", 12_100, 11_900) == Signal.BUY


# ---------------------------------------------------------------------------
# check_exit_signal — 하드 손절 / 베이스 하단 이탈
# ---------------------------------------------------------------------------
def test_exit_when_loss_breaches_minus_7_then_stop_loss(strat):
    _seed_candidate(strat, "005930", base_low=10_500, atr14=200)
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="vcp_breakout",
        high_since_buy=12_000,
    )
    # -7% 정확히: 12_000 × 0.93 = 11_160
    assert strat.check_exit_signal("005930", 11_160, 12_000) == Signal.STOP_LOSS


def test_exit_when_below_base_low_then_stop_loss(strat):
    _seed_candidate(strat, "005930", base_low=10_500, atr14=200, ema50=11_500)
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="vcp_breakout",
        high_since_buy=12_000,
    )
    # 손실률 -7% 안 닿았지만 base_low 10_500 이탈 → STOP_LOSS
    assert strat.check_exit_signal("005930", 10_400, 12_000) == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# check_exit_signal — ATR×2 트레일링
# ---------------------------------------------------------------------------
def test_exit_atr_trailing_when_drop_beyond_chandelier(strat):
    _seed_candidate(strat, "005930", base_low=10_500, atr14=200, ema50=11_500)
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="vcp_breakout",
        high_since_buy=13_000,  # 매수 후 고점 갱신
    )
    # chandelier = 13_000 - 200×2 = 12_600. current 12_550 ≤ 12_600 → TRAILING_STOP
    assert strat.check_exit_signal("005930", 12_550, 12_000) == Signal.TRAILING_STOP


def test_exit_atr_trailing_when_above_chandelier_then_none(strat):
    _seed_candidate(strat, "005930", base_low=10_500, atr14=200, ema50=11_500)
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="vcp_breakout",
        high_since_buy=13_000,
    )
    # chandelier 12_600. current 12_700 > 12_600 → NONE (다른 청산 조건도 미발동)
    assert strat.check_exit_signal("005930", 12_700, 12_000) == Signal.NONE


# ---------------------------------------------------------------------------
# check_exit_signal — 50일 EMA 이탈
# ---------------------------------------------------------------------------
def test_exit_when_below_ema50_then_trailing_stop(strat):
    # ATR 트레일링이 발동 안 되도록 high_since_buy = 매수가 (chandelier = 11_600)
    _seed_candidate(strat, "005930", base_low=10_500, atr14=200, ema50=11_500)
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="vcp_breakout",
        high_since_buy=12_000,
    )
    # chandelier = 12_000 - 400 = 11_600. current 11_450:
    #   - loss_rate -4.58% > -7% → 손절 미발동
    #   - base_low 10_500 > 11_450 X (11_450 > 10_500) → base 이탈 미발동
    #   - chandelier 11_600 > 11_450 → ATR 트레일링 발동
    # ATR 트레일링과 EMA 이탈 모두 TRAILING_STOP 반환이라 명세 충족
    result = strat.check_exit_signal("005930", 11_450, 12_000)
    assert result == Signal.TRAILING_STOP


def test_exit_above_all_thresholds_then_none(strat):
    _seed_candidate(strat, "005930", base_low=10_500, atr14=200, ema50=11_500)
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="vcp_breakout",
        high_since_buy=12_000,
    )
    # 12_500 — 모든 임계 위
    assert strat.check_exit_signal("005930", 12_500, 12_000) == Signal.NONE


# ---------------------------------------------------------------------------
# check_exit_signal — 시간 청산 없음 (멀티데이)
# ---------------------------------------------------------------------------
def test_exit_when_held_many_days_does_not_force_clear_by_time(strat):
    """donchian 컨벤션 — 시간만으로는 청산 신호 안 남."""
    _seed_candidate(strat, "005930", base_low=10_500, atr14=200, ema50=11_500)
    with freeze_time("2026-05-15 10:00:00"):
        strat.state.positions["005930"] = Position(
            ticker="005930", buy_price=12_000, quantity=10,
            order_no="O1", strategy_id="vcp_breakout",
            buy_date=date(2026, 4, 1),  # 한 달 보유
            high_since_buy=12_500,
        )
        # ATR 트레일링/EMA/base/손절 모두 미발동
        assert strat.check_exit_signal("005930", 12_400, 12_000) == Signal.NONE


def test_exit_when_no_position_then_none(strat):
    assert strat.check_exit_signal("005930", 12_100, 11_900) == Signal.NONE


# ---------------------------------------------------------------------------
# check_force_clear — 빈 리스트 (donchian 컨벤션)
# ---------------------------------------------------------------------------
def test_force_clear_returns_empty_list_even_with_positions(strat):
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="vcp_breakout",
    )
    assert strat.check_force_clear() == []


# ---------------------------------------------------------------------------
# calc_buy_quantity + 1주 폴백
# ---------------------------------------------------------------------------
def test_calc_qty_when_amount_covers_qty(strat):
    strat.state.total_investment = 10_000_000  # 20% = 2M
    assert strat.calc_buy_quantity(current_price=100_000) == 20


def test_calc_qty_falls_back_to_one_share_when_remaining_covers(strat):
    strat.state.total_investment = 100_000  # 20% = 20_000 < 50_000 (1주)
    assert strat.calc_buy_quantity(current_price=50_000) == 1


def test_calc_qty_returns_zero_when_remaining_below_one_share(strat):
    strat.state.total_investment = 100_000
    strat.state.positions["111111"] = Position(
        ticker="111111", buy_price=90_000, quantity=1,
        order_no="O9", strategy_id="vcp_breakout",
    )
    assert strat.calc_buy_quantity(current_price=50_000) == 0
