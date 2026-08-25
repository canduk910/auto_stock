"""사이클 23 P2-1 Red — BFB breakout_retention_minutes 유지시간 조건.

요구 행위:
1. 첫 돌파 감지 시 `_breakout_first_seen[ticker] = now`, 신호 NONE
2. retention=3분 후 freeze_time 으로 시간 진행, 현재가 >= flag_high → BUY 신호
3. retention 중 현재가 < flag_high → `_breakout_first_seen` pop, NONE
4. `_reset_daily_state()` 호출 시 `_breakout_first_seen` 비워짐
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _make_strat(retention_minutes: int = 3):
    strat = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.0)
    )
    strat.config.params["breakout_retention_minutes"] = retention_minutes
    return strat


def _seed_candidate(strat, ticker, flag_high=12_000):
    strat._candidates[ticker] = {
        "pole_start": 9_000,
        "pole_high": 11_500,
        "flag_high": flag_high,
        "flag_low": 11_000,
        "flag_avg_volume": 500_000,
        "pole_len": 5,
        "flag_len": 4,
        "atr14": 300,
        "prev_close": 11_800,
    }


# ---------------------------------------------------------------------------
# 케이스 1: 첫 돌파 감지 → NONE (대기 시작)
# BFB 시간 가드: datetime.now().time() (UTC) 기준 → 09:05~13:00 UTC 로 freeze
# ---------------------------------------------------------------------------
@freeze_time("2026-05-20 09:30:00")  # UTC 09:30 → 시간 가드 통과
def test_first_breakout_detected_returns_none(monkeypatch):
    """첫 돌파 감지 시 _breakout_first_seen 에 등록되고 NONE 반환."""
    strat = _make_strat(retention_minutes=3)
    ticker = "005930"
    _seed_candidate(strat, ticker, flag_high=12_000)

    # 거래량 mock
    # ⚠️ cycle227 Stage 0 유지 — 게이트 전환 사이클에서 tick_volume 주입으로 의미 전환 의무
    monkeypatch.setattr(
        "src.engine.scanner.ticker_prices",
        {ticker: {"acml_vol": "5000000"}},
    )

    # prev_price < flag_high (첫 돌파 조건)
    strat._prev_price[ticker] = 11_900

    sig = strat.check_buy_signal(ticker, 12_000, 11_500)
    assert sig == Signal.NONE
    assert ticker in strat._breakout_first_seen


# ---------------------------------------------------------------------------
# 케이스 2: retention 충족 후 BUY
# ---------------------------------------------------------------------------
def test_buy_signal_after_retention_period(monkeypatch):
    """첫 돌파 등록 후 retention 분 경과 + 현재가 >= flag_high → BUY."""
    strat = _make_strat(retention_minutes=3)
    ticker = "005930"
    _seed_candidate(strat, ticker, flag_high=12_000)

    # 거래량 mock (vol_threshold 계산: flag_avg_volume=500_000 × breakout_volume_mult=2 = 1_000_000)
    # ⚠️ cycle227 Stage 0 유지 — 게이트 전환 사이클에서 tick_volume 주입으로 의미 전환 의무
    monkeypatch.setattr(
        "src.engine.scanner.ticker_prices",
        {ticker: {"acml_vol": "5000000"}},
    )

    # 첫 돌파 3분 전 기록 (UTC 기준)
    first_seen = datetime(2026, 5, 20, 9, 30, 0, tzinfo=KST)
    strat._breakout_first_seen[ticker] = first_seen
    strat._prev_price[ticker] = 12_000  # already past flag_high

    # 3분 후 시점으로 freeze (UTC 09:33 → 시간 가드 통과)
    with freeze_time("2026-05-20 09:33:01"):
        sig = strat.check_buy_signal(ticker, 12_100, 11_500)

    assert sig == Signal.BUY


# ---------------------------------------------------------------------------
# 케이스 3: retention 중 가격 후퇴 → dict pop, NONE
# ---------------------------------------------------------------------------
@freeze_time("2026-05-20 09:31:00")  # UTC 09:31 → 시간 가드 통과
def test_retreat_during_retention_pops_dict(monkeypatch):
    """돌파 후 가격 후퇴 시 _breakout_first_seen pop 하고 NONE 반환."""
    strat = _make_strat(retention_minutes=3)
    ticker = "005930"
    _seed_candidate(strat, ticker, flag_high=12_000)

    # ⚠️ cycle227 Stage 0 유지 — 게이트 전환 사이클에서 tick_volume 주입으로 의미 전환 의무
    monkeypatch.setattr(
        "src.engine.scanner.ticker_prices",
        {ticker: {"acml_vol": "5000000"}},
    )

    first_seen = datetime(2026, 5, 20, 9, 30, 0, tzinfo=KST)
    strat._breakout_first_seen[ticker] = first_seen
    strat._prev_price[ticker] = 12_000  # already flagged

    # 현재가 flag_high 아래 후퇴
    sig = strat.check_buy_signal(ticker, 11_800, 11_500)

    assert sig == Signal.NONE
    assert ticker not in strat._breakout_first_seen


# ---------------------------------------------------------------------------
# 케이스 4: _reset_daily_state() 호출 시 _breakout_first_seen 비워짐
# ---------------------------------------------------------------------------
def test_reset_daily_state_clears_breakout_first_seen():
    """_reset_daily_state() 호출 후 _breakout_first_seen 이 비어 있어야 한다."""
    strat = _make_strat(retention_minutes=3)
    ticker = "005930"
    strat._breakout_first_seen[ticker] = datetime.now(KST)

    strat._reset_daily_state()

    assert len(strat._breakout_first_seen) == 0
