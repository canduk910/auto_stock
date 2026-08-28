"""src/engine/strategies/momentum.py 단위 테스트.

- 매수: 전일종가 +29% 돌파 순간 (이전 틱<29 AND 현재 틱>=29)
- 손절: 매수가 -7.5%
- 익일 청산: 갭<10% 즉시, 갭>=10% 트레일링 -2%
- _next_day_clear_pending=True 동안 NEXT_DAY_CLEAR/TRAILING 억제 (손절은 유지)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from freezegun import freeze_time

_KST = timezone(timedelta(hours=9))


def _today_kst():
    """사이클 68 hotfix — CI UTC 자정 너머 KST 어긋남 차단 (production 일관)."""
    return datetime.now(_KST).date()

import pytest

from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def momentum(monkeypatch):
    """scanner 전역 dict 를 격리한 모멘텀 전략 인스턴스."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 70000})
    # `t` 함수는 ticker → name 변환. 이미 ticker_names 가 있으므로 그대로 사용 가능.
    return MomentumStrategy(
        StrategyConfig(strategy_id="momentum", name="모멘텀", weight=0.5)
    )


# ---------------------------------------------------------------------------
# check_buy_signal — 매수 가드
# ---------------------------------------------------------------------------
def test_buy_when_prev_close_unknown_then_none(momentum, monkeypatch):
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    assert momentum.check_buy_signal("005930", 90000, 80000) == Signal.NONE


def test_buy_when_buy_disabled_then_none(momentum):
    momentum.state.buy_disabled = True
    # 어떤 조건이어도 NONE
    assert momentum.check_buy_signal("005930", 95000, 80000) == Signal.NONE


def test_buy_when_already_held_then_none(momentum):
    momentum.state.positions["005930"] = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="momentum",
    )
    assert momentum.check_buy_signal("005930", 95000, 80000) == Signal.NONE


def test_buy_when_pending_then_none(momentum):
    momentum.state.pending_buys.add("005930")
    assert momentum.check_buy_signal("005930", 95000, 80000) == Signal.NONE


def test_buy_when_sold_today_then_none(momentum):
    momentum.state.sold_today.add("005930")
    assert momentum.check_buy_signal("005930", 95000, 80000) == Signal.NONE


def test_buy_when_max_positions_reached_then_none(momentum):
    momentum.config.params["max_positions"] = 1
    momentum.state.positions["A"] = Position(
        ticker="A", buy_price=1, quantity=1, order_no="OA", strategy_id="momentum",
    )
    assert momentum.check_buy_signal("005930", 95000, 80000) == Signal.NONE


def test_buy_when_limit_up_above_30pct_then_excluded(momentum):
    # 전일 70000 → 92000 = +31.4% → 상한가(+30%) 초과로 제외
    assert momentum.check_buy_signal("005930", 92000, 80000) == Signal.NONE


# ---------------------------------------------------------------------------
# check_buy_signal — 돌파 순간 감지
# ---------------------------------------------------------------------------
def test_buy_first_tick_records_only_then_no_signal(momentum):
    # 70000 → 80000 = +14.3% (29% 미만이지만 첫 틱은 무조건 기록만)
    assert momentum.check_buy_signal("005930", 80000, 80000) == Signal.NONE
    # 두 번째 틱이어도 임계치 미돌파면 NONE
    assert momentum.check_buy_signal("005930", 85000, 80000) == Signal.NONE


# cycle229 적응 — 매수 컷(15:20 KST) 도입으로 무-freeze 실행이 벽시계 의존이 됨.
# 장중 KST(UTC 01:00 = KST 10:00) 로 동결해 결정성 확보(행위 불변).
@freeze_time("2026-05-08 01:00:00")
def test_buy_when_prev_below_threshold_and_current_above_then_buy(momentum):
    # 첫 틱: +27.14% 기록만 (임계 29% 미만, 부동소수 마진 충분)
    assert momentum.check_buy_signal("005930", 89000, 80000) == Signal.NONE
    # 두 번째 틱: +29.14% 돌파 → BUY
    assert momentum.check_buy_signal("005930", 90400, 80000) == Signal.BUY
    # buy_signals 기록도 검증
    assert len(momentum.state.buy_signals) == 1
    assert momentum.state.buy_signals[0]["ticker"] == "005930"


def test_buy_when_already_above_threshold_in_first_tick_then_no_signal(momentum):
    # 첫 틱이 이미 +30% 미만이지만 임계치 이상 → 기록만, BUY 발생하지 않음
    assert momentum.check_buy_signal("005930", 90400, 80000) == Signal.NONE


# cycle229 적응 — 매수 컷(15:20 KST) 도입으로 무-freeze 실행이 벽시계 의존이 됨.
# 장중 KST(UTC 01:00 = KST 10:00) 로 동결해 결정성 확보(행위 불변).
@freeze_time("2026-05-08 01:00:00")
def test_buy_signals_capped_at_20_entries(momentum):
    """buy_signals 리스트는 최신 20개만 유지."""
    # 첫 틱 기록 (임계 미달)
    momentum.check_buy_signal("005930", 89000, 80000)
    # 인공적으로 20개 채움
    momentum.state.buy_signals = [{"ticker": "DUMMY", "i": i} for i in range(20)]
    # 한 번 더 BUY → pop 발생, 길이 20 유지
    assert momentum.check_buy_signal("005930", 90400, 80000) == Signal.BUY
    assert len(momentum.state.buy_signals) == 20
    # 가장 오래된(i=0)은 제거되고 새 시그널이 마지막
    assert momentum.state.buy_signals[-1]["ticker"] == "005930"


# ---------------------------------------------------------------------------
# check_exit_signal — 손절
# ---------------------------------------------------------------------------
def test_exit_when_no_position_then_none(momentum):
    assert momentum.check_exit_signal("005930", 50000, 60000) == Signal.NONE


def test_exit_stop_loss_when_loss_breaches_minus_7_5(momentum):
    momentum.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="momentum",
    )
    # -7.5% 정확히 도달
    assert momentum.check_exit_signal("005930", 92500, 95000) == Signal.STOP_LOSS


def test_exit_no_stop_loss_when_loss_within_threshold(momentum):
    momentum.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="momentum",
    )
    # -7.4% 만 손실 → 손절 미발동
    assert momentum.check_exit_signal("005930", 92600, 95000) == Signal.NONE


# ---------------------------------------------------------------------------
# check_exit_signal — 익일 청산
# ---------------------------------------------------------------------------
def _make_next_day_position(strategy, ticker="005930", buy_price=100000):
    pos = Position(
        ticker=ticker, buy_price=buy_price, quantity=1,
        order_no="O1", strategy_id=strategy.strategy_id,
        buy_date=_today_kst() - timedelta(days=1),
    )
    strategy.state.positions[ticker] = pos
    return pos


def test_exit_next_day_immediate_when_gap_below_10_pct(momentum):
    _make_next_day_position(momentum)
    # 시가 105000 → 갭 +5% < 10% → 즉시 청산
    assert momentum.check_exit_signal("005930", 105000, 105000) == Signal.NEXT_DAY_CLEAR


def test_exit_next_day_trailing_stop_when_gap_above_10_and_drop_below_minus_2(momentum):
    pos = _make_next_day_position(momentum)
    # 첫 호출: 시가 +12% 갭, 현재가 = 시가 → high_since_buy 갱신, drop=0 → NONE
    assert momentum.check_exit_signal("005930", 112000, 112000) == Signal.NONE
    assert pos.high_since_buy == 112000
    # 두번째: 고점 112000 → 현재 109700 (-2.05%) → TRAILING_STOP
    assert momentum.check_exit_signal("005930", 109700, 112000) == Signal.TRAILING_STOP


def test_exit_next_day_clear_pending_suppresses_clear_but_not_stop_loss(momentum):
    _make_next_day_position(momentum)
    momentum._next_day_clear_pending = True
    # 갭 -5% (즉시청산 조건) 이지만 pending=True 라 NONE
    assert momentum.check_exit_signal("005930", 95000, 95000) == Signal.NONE
    # 그러나 손절 조건은 pending 무시하고 발동 — 매수가 100000, 92500 = -7.5%
    assert momentum.check_exit_signal("005930", 92500, 95000) == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# calc_buy_quantity — 비중/1주 fallback
# ---------------------------------------------------------------------------
def test_calc_qty_when_amount_covers_qty_then_returns_floor(momentum):
    momentum.state.total_investment = 10_000_000  # 25% = 2.5M
    qty = momentum.calc_buy_quantity(current_price=100_000)
    # 2_500_000 // 100_000 = 25
    assert qty == 25


def test_calc_qty_when_ratio_zero_but_total_covers_one_share_then_one(momentum):
    momentum.state.total_investment = 100_000  # ratio 25% = 25k → 100k 가격 → 0주
    qty = momentum.calc_buy_quantity(current_price=100_000)
    # ratio 기준 0 이지만 total_investment 가 1주 가격 이상 → 1주
    assert qty == 1


def test_calc_qty_when_total_below_share_price_then_zero(momentum):
    momentum.state.total_investment = 50_000
    assert momentum.calc_buy_quantity(current_price=100_000) == 0


def test_calc_qty_when_price_zero_then_zero(momentum):
    momentum.state.total_investment = 1_000_000
    assert momentum.calc_buy_quantity(current_price=0) == 0
