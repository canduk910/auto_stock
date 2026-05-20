"""사이클 23 P2-3 Red — donchian 돌파폭 과열 상한 가드.

요구 행위:
1. 당일 고가가 돌파선 대비 max_breakout_extension_pct% 초과 → NONE
2. 당일 고가가 돌파선 대비 한계 미만 → BUY 정상 진입 가능
"""
from __future__ import annotations

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit


def _make_strat(max_ext: float = 3.0):
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.0)
    )
    strat.config.params["max_breakout_extension_pct"] = max_ext
    return strat


def _seed_candidate(strat, ticker, donchian_high=10_000, prev_close=9_800):
    strat._candidates[ticker] = {
        "prev_close": prev_close,
        "atr": 200,
        "ema60": 9_500,
        "donchian_high": donchian_high,
    }


# ---------------------------------------------------------------------------
# 케이스 1: 당일 고가가 돌파선 대비 3% 초과 → NONE
# donchian 시간 가드: datetime.now().time() (UTC) 기준 09:05~09:30 UTC 로 freeze
# ---------------------------------------------------------------------------
@freeze_time("2026-05-20 09:10:00")  # UTC 09:10 → 시간 가드 통과
def test_extension_cap_blocks_when_daily_high_exceeds_threshold(monkeypatch):
    """당일 고가 > donchian_high × (1 + max_ext%) → NONE."""
    strat = _make_strat(max_ext=3.0)
    ticker = "005930"
    _seed_candidate(strat, ticker, donchian_high=10_000, prev_close=9_800)

    # 당일 고가 = 10,400 → (10,400 - 10,000) / 10,000 * 100 = 4.0% > 3.0%
    monkeypatch.setattr(
        "src.engine.scanner.ticker_prices",
        {ticker: {"stck_hgpr": "10400", "high_price": "0"}},
    )

    # open_price와 current_price도 ticker_prices에 반영
    # (명세: max(stck_hgpr, high_price, current_price, open_price))
    sig = strat.check_buy_signal(ticker, 10_100, 10_050)
    assert sig == Signal.NONE


# ---------------------------------------------------------------------------
# 케이스 2: 당일 고가가 돌파선 대비 2% 초과 (3% 미만) → BUY 가능 (NONE이 아님)
# ---------------------------------------------------------------------------
@freeze_time("2026-05-20 09:10:00")  # UTC 09:10 → 시간 가드 통과
def test_extension_cap_allows_when_daily_high_below_threshold(monkeypatch):
    """당일 고가 ≤ donchian_high × (1 + max_ext%) → 가드 통과, BUY 가능."""
    strat = _make_strat(max_ext=3.0)
    ticker = "005930"
    _seed_candidate(strat, ticker, donchian_high=10_000, prev_close=9_800)

    # 당일 고가 = 10_200 → (10,200 - 10,000) / 10,000 * 100 = 2.0% < 3.0%
    monkeypatch.setattr(
        "src.engine.scanner.ticker_prices",
        {ticker: {"stck_hgpr": "10200", "high_price": "0"}},
    )

    # current_price >= donchian_high 이면서 시간 가드 통과 (09:05~09:30)
    # donchian 은 _prev_price 없음 — _bought_today 가드만 피하면 됨
    # 갭 스킵 확인: open_price 9,900 → gap_rate=(9900-9800)/9800 ≈ 1.0% < 3.0% 통과
    sig = strat.check_buy_signal(ticker, 10_050, 9_900)
    # 가드는 통과하므로 BUY 또는 NONE (다음 가드까지 도달)
    # 핵심: extension_cap 가드가 차단하지 않아야 함 (NONE 이 아닌 BUY 기대)
    assert sig == Signal.BUY
