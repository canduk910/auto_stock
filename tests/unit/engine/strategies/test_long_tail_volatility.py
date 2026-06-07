"""src/engine/strategies/long_tail_volatility.py 단위 테스트.

LTV 는 VB 진입 + 모멘텀 익일 청산을 합성한다. 검증 포인트:
- 매수 시 prdy_rate >= min_prdy_rate(5%) 필터가 추가
- check_exit_signal 의 2단계 모드 전환 (당일 손절 -3% → 상한가 도달 시 익일 모드)
- 익일 모드에서 손절 -5% / 갭<10% 즉시 / 갭>=10% 트레일링
- _next_day_clear_pending 동안 NEXT_DAY/TRAILING 억제 (손절은 유지)
- check_force_clear 는 상한가 모드 종목 제외
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_KST = timezone(timedelta(hours=9))


def _today_kst():
    """사이클 68 hotfix — CI UTC 자정 너머 KST 어긋남 차단 (production 일관)."""
    return datetime.now(_KST).date()

import pytest

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def ltv(monkeypatch):
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 70000})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="롱테일", weight=0.2)
    )


def _activate(board: str):
    session_tracker._active = frozenset({MarketBoard(board)})


def _seed_target(strategy, ticker, *, prev_range=2000, k=0.5):
    base = int(prev_range * k)
    strategy._targets[ticker] = {
        "k": k,
        "prev_range": prev_range,
        "target_offset_base": base,
        "target_offset": base,
        "target_price": 0,
        "open_price": 0,
        "boards": {},
    }
    strategy._open_confirmed[ticker] = {}


def _make_position(strategy, ticker="005930", buy_price=80000, *, next_day=False):
    pos = Position(
        ticker=ticker, buy_price=buy_price, quantity=1,
        order_no="O1", strategy_id=strategy.strategy_id,
        buy_date=(_today_kst() - timedelta(days=1)) if next_day else _today_kst(),
    )
    strategy.state.positions[ticker] = pos
    return pos


# ---------------------------------------------------------------------------
# 매수 — min_prdy_rate 필터
# ---------------------------------------------------------------------------
def test_buy_when_prdy_rate_below_min_then_none(ltv, monkeypatch):
    """전일대비 등락률이 min_prdy_rate(5%) 미만이면 BUY 안 함."""
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    _seed_target(ltv, "005930", prev_range=2000, k=0.5)
    ltv.config.params["k_value_krx_main"] = 1.0
    _activate("main")
    # 첫 틱 기록
    ltv.check_buy_signal("005930", 71000, 70000)
    # 두 번째 틱: 73000 (target=71000 돌파, but prdy_rate = +4.3% < 5%)
    assert ltv.check_buy_signal("005930", 73000, 70000) == Signal.NONE


def test_buy_when_breakout_and_prdy_rate_above_min_then_buy(ltv, monkeypatch):
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    _seed_target(ltv, "005930", prev_range=2000, k=0.5)  # base 1000, target = 81000
    ltv.config.params["k_value_krx_main"] = 1.0
    _activate("main")
    # 첫 틱: 80000 (target 81000 미달, prdy +14% > 5%) — 기록만
    assert ltv.check_buy_signal("005930", 80000, 80000) == Signal.NONE
    # 두 번째 틱: 81500 → 돌파 + prdy +16.4%
    assert ltv.check_buy_signal("005930", 81500, 80000) == Signal.BUY


# ---------------------------------------------------------------------------
# check_exit_signal — 당일 모드 (상한가 미도달)
# ---------------------------------------------------------------------------
def test_exit_intraday_stop_loss_at_minus_3(ltv):
    _make_position(ltv, buy_price=100000)
    # -3% 정확히 → STOP_LOSS
    assert ltv.check_exit_signal("005930", 97000, 100000) == Signal.STOP_LOSS


def test_exit_intraday_no_stop_loss_within_threshold(ltv):
    _make_position(ltv, buy_price=100000)
    assert ltv.check_exit_signal("005930", 97500, 100000) == Signal.NONE


def test_exit_intraday_when_prdy_above_29_then_mode_switches(ltv, monkeypatch):
    """상한가 도달 시 _limit_up_reached 등록 + 다음 호출은 익일 모드."""
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    _make_position(ltv, buy_price=80000)
    # 90400 → prdy +29.14% (limit_up_threshold=29)
    sig = ltv.check_exit_signal("005930", 90400, 80000)
    # 모드 전환만 일어나고 즉시 청산 신호는 없음
    assert sig == Signal.NONE
    assert "005930" in ltv._limit_up_reached


# ---------------------------------------------------------------------------
# check_exit_signal — 익일 모드 (상한가 도달 후 다음 영업일)
# ---------------------------------------------------------------------------
def test_exit_overnight_stop_loss_during_stabilize_pending(ltv):
    """pending=True 동안에는 overnight 손절(-5%)만 발동, NEXT_DAY_CLEAR/TRAILING 억제."""
    _make_position(ltv, buy_price=100000, next_day=True)
    ltv._limit_up_reached.add("005930")
    ltv._next_day_clear_pending = True
    # pending 중 -5% 도달 → STOP_LOSS
    assert ltv.check_exit_signal("005930", 95000, 100000) == Signal.STOP_LOSS


def test_exit_overnight_immediate_when_gap_below_10(ltv):
    _make_position(ltv, buy_price=100000, next_day=True)
    ltv._limit_up_reached.add("005930")
    # 갭 +5% < 10% → NEXT_DAY_CLEAR
    assert ltv.check_exit_signal("005930", 105000, 105000) == Signal.NEXT_DAY_CLEAR


def test_exit_overnight_trailing_when_gap_above_10_and_drop_below_minus_2(ltv):
    pos = _make_position(ltv, buy_price=100000, next_day=True)
    ltv._limit_up_reached.add("005930")
    # 첫 호출: 갭 +12%, 현재가 = 시가 → high_since_buy = 112000
    assert ltv.check_exit_signal("005930", 112000, 112000) == Signal.NONE
    assert pos.high_since_buy == 112000
    # 두 번째: 109700 → drop -2.05%
    assert ltv.check_exit_signal("005930", 109700, 112000) == Signal.TRAILING_STOP


def test_exit_overnight_pending_suppresses_clear_but_not_stop(ltv):
    _make_position(ltv, buy_price=100000, next_day=True)
    ltv._limit_up_reached.add("005930")
    ltv._next_day_clear_pending = True
    # 갭 +5% (정상이면 NEXT_DAY_CLEAR) → pending 으로 NONE
    assert ltv.check_exit_signal("005930", 105000, 105000) == Signal.NONE
    # 손절 -5% 는 pending 무시하고 발동
    assert ltv.check_exit_signal("005930", 95000, 105000) == Signal.STOP_LOSS


def test_exit_intraday_after_limit_up_uses_overnight_stop(ltv):
    """상한가 도달 후 같은 날(아직 next_day=False) 안에서는 overnight 손절(-5%) 적용."""
    _make_position(ltv, buy_price=100000)  # buy_date=today
    ltv._limit_up_reached.add("005930")
    # -3% (intraday 였다면 손절) 인데 상한가 모드라 overnight(-5) 기준 → 미발동
    assert ltv.check_exit_signal("005930", 97000, 100000) == Signal.NONE
    # -5% → 발동
    assert ltv.check_exit_signal("005930", 95000, 100000) == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# check_force_clear — 상한가 모드 종목 제외
# ---------------------------------------------------------------------------
def test_force_clear_excludes_limit_up_reached(ltv):
    _make_position(ltv, ticker="005930", buy_price=80000)
    _make_position(ltv, ticker="000660", buy_price=100000)
    ltv._limit_up_reached.add("005930")
    cleared = ltv.check_force_clear()
    assert "000660" in cleared
    assert "005930" not in cleared


# ---------------------------------------------------------------------------
# DEFAULT_PARAMS 검증
# ---------------------------------------------------------------------------
def test_default_params_thresholds():
    p = LongTailVolatilityStrategy.DEFAULT_PARAMS
    assert p["min_prdy_rate"] == 5.0
    assert p["intraday_stop_loss"] == -3.0
    assert p["overnight_stop_loss"] == -5.0
    assert p["limit_up_threshold"] == 29.0
    assert p["gap_up_threshold"] == 10.0
    assert p["trailing_stop_rate"] == -2.0
