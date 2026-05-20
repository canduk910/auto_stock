"""사이클 23 P2-4 Red — donchian 박스 수축 보조 필터.

요구 행위:
1. 박스 변동성 3% (≤5%) → box_contraction_pass 증가 (통과)
2. 박스 변동성 7% (>5%) → skip (통과 안 함)
3. box_contraction_pass 카운터 정확히 증가
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _make_strat(box_period: int = 10, max_box_vol: float = 5.0):
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.0)
    )
    strat.config.params["box_contraction_period"] = box_period
    strat.config.params["max_box_volatility_pct"] = max_box_vol
    return strat


def _make_candles(n=70, base_price=10_000, vol_pct=0.03, high_breakout=True):
    """n일치 가짜 일봉 생성.

    vol_pct: (high - low) / close 비율 — 박스 변동성 제어.
    최신순(idx=0이 가장 최근).

    high_breakout=True: candles[0] (가장 최근일, 전일) 의 종가가
    candles[1:21] 최고가 max 를 초과하도록 설정 → donchian 필터 통과.
    """
    from datetime import date, timedelta as td
    today = datetime(2026, 5, 20).date()
    candles = []
    for i in range(n):
        d = today - td(days=i + 1)
        if high_breakout and i == 0:
            # 가장 최근일: donchian 돌파 신고가 (나머지보다 10% 높게)
            close = int(base_price * 1.10)
            high = int(close * (1 + vol_pct / 2))
            low = int(close * (1 - vol_pct / 2))
        else:
            close = base_price
            high = int(close * (1 + vol_pct / 2))
            low = int(close * (1 - vol_pct / 2))
        candles.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_hgpr": str(high),
            "stck_lwpr": str(low),
            "stck_oprc": str(close),
            "acml_vol": "1000000",
        })
    return candles


def test_empty_scan_stats_has_box_contraction_pass():
    """_empty_scan_stats() 에 box_contraction_pass 키가 기본 0이어야 한다."""
    from src.engine.strategies.donchian_swing import _empty_scan_stats
    stats = _empty_scan_stats()
    assert "box_contraction_pass" in stats
    assert stats["box_contraction_pass"] == 0


def _make_donchian_passing_candles(n=70, base_price=10_000, vol_pct=0.03):
    """donchian prepare() 의 1~4 필터를 모두 통과하는 일봉 데이터 생성.

    donchian prepare() 필터:
    1) donchian: closes[0] > max(highs[1:donchian_period+1])
    2) EMA 우상향: ema_today > ema_yesterday AND closes[0] > ema_today
    3) 거래량: today_turnover > avg_turnover × volume_mult(1.5)
    4) ATR: positive

    최신순(idx=0 = 가장 최근) 반환.
    """
    from datetime import date, timedelta as td

    today = datetime(2026, 5, 20).date()
    candles = []

    for i in range(n):
        d = today - td(days=i + 1)
        if i == 0:
            # 가장 최근일(전일): 20일 신고가 초과 → donchian 통과
            # 나머지(1~69)는 base_price, 이 날은 base_price × 1.25
            close = int(base_price * 1.25)
            # 거래량도 높게 → 거래량 필터 통과
            acml_vol = "3000000"
        else:
            # 오래된 날수록 약간 낮게 → EMA 우상향 보장
            close = int(base_price * (1 + 0.001 * (n - i)))
            acml_vol = "1000000"
        high = int(close * (1 + vol_pct / 2))
        low = int(close * (1 - vol_pct / 2))
        candles.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_hgpr": str(high),
            "stck_lwpr": str(low),
            "stck_oprc": str(close),
            "acml_vol": acml_vol,
        })
    return candles


@pytest.mark.asyncio
async def test_box_contraction_pass_increments_when_low_volatility(monkeypatch):
    """박스 변동성 3% (< 5%) → box_contraction_pass 증가."""
    strat = _make_strat(box_period=10, max_box_vol=5.0)

    tickers = ["005930"]
    candles_low_vol = _make_donchian_passing_candles(n=70, base_price=10_000, vol_pct=0.03)

    # _scan_universe mock
    async def fake_scan_universe():
        strat._scan_stats["universe_candidates"] = 1
        strat._scan_stats["universe_filtered"] = 1
        return tickers

    monkeypatch.setattr(strat, "_scan_universe", fake_scan_universe)

    # fetch_daily_candles mock
    async def fake_fetch(ticker, days):
        return candles_low_vol

    monkeypatch.setattr(
        "src.api.condition.fetch_daily_candles", fake_fetch
    )

    # ticker_prev_close mock
    import src.engine.scanner as scanner_mod
    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {})

    # write_log mock
    monkeypatch.setattr(
        "src.db.system_logs.write_log", AsyncMock()
    )

    await strat.prepare()
    assert strat._scan_stats["box_contraction_pass"] >= 1


@pytest.mark.asyncio
async def test_box_contraction_skip_when_high_volatility(monkeypatch):
    """박스 변동성 7% (> 5%) → skip, box_contraction_pass 증가 안 함."""
    strat = _make_strat(box_period=10, max_box_vol=5.0)

    tickers = ["005930"]
    # 높은 변동성이지만 donchian/EMA/거래량/ATR 필터는 통과하도록 구성
    candles_high_vol = _make_donchian_passing_candles(n=70, base_price=10_000, vol_pct=0.07)

    async def fake_scan_universe():
        strat._scan_stats["universe_candidates"] = 1
        strat._scan_stats["universe_filtered"] = 1
        return tickers

    monkeypatch.setattr(strat, "_scan_universe", fake_scan_universe)

    async def fake_fetch(ticker, days):
        return candles_high_vol

    monkeypatch.setattr("src.api.condition.fetch_daily_candles", fake_fetch)

    import src.engine.scanner as scanner_mod
    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {})

    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())

    await strat.prepare()
    # 고변동성이라 box_contraction_pass = 0, final_prepared = 0
    assert strat._scan_stats["box_contraction_pass"] == 0
    assert strat._scan_stats["final_prepared"] == 0
