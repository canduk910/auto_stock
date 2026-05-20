"""사이클 23 P1-2 Red — BFB `min_trade_amount_failed` scan_stats 카운터.

요구 행위:
1. `_empty_scan_stats()` 에 `min_trade_amount_failed` 키 기본 0
2. `_scan_universe` 에서 거래대금 미달 시 카운터 증가
3. 시총 미달은 `min_trade_amount_failed` 에 영향 없음 (분리 검증)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _make_strat():
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig
    return BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.0)
    )


def test_empty_scan_stats_has_min_trade_amount_failed_key():
    """_empty_scan_stats() 에 min_trade_amount_failed 키가 기본 0이어야 한다."""
    from src.engine.strategies.bull_flag_breakout import _empty_scan_stats
    stats = _empty_scan_stats()
    assert "min_trade_amount_failed" in stats
    assert stats["min_trade_amount_failed"] == 0


@pytest.mark.asyncio
async def test_min_trade_amount_failed_increments_on_trade_amount_fail(monkeypatch):
    """거래대금 미달 종목에서 min_trade_amount_failed 카운터가 증가해야 한다."""
    strat = _make_strat()
    strat.config.params["min_market_cap"] = 0  # 시총 통과 보장
    strat.config.params["min_trade_amount"] = 999_999_999_999_999  # 극단적 거래대금 기준

    # fetch_stock_detail mock — 시총만 충분, 거래대금은 미달
    async def fake_detail(ticker):
        return {
            "stck_prpr": "10000",
            "lstn_stcn": "10000000",  # mcap=1000억 (시총 통과)
            "prdy_vol": "100",       # trade_amt=100×10000=1,000,000 (미달)
            "hts_kor_isnm": "테스트",
        }

    async def fake_rank():
        return [{"mksc_shrn_iscd": "005930", "hts_kor_isnm": "삼성전자"}]

    import src.engine.strategies.bull_flag_breakout as bfb_mod
    monkeypatch.setattr(
        "src.api.condition._fetch_fluctuation_rank", fake_rank
    )
    monkeypatch.setattr(
        "src.api.condition.fetch_stock_detail", fake_detail
    )

    await strat._scan_universe()
    assert strat._scan_stats["min_trade_amount_failed"] >= 1


@pytest.mark.asyncio
async def test_mcap_fail_does_not_increment_min_trade_amount_failed(monkeypatch):
    """시총 미달 종목은 min_trade_amount_failed 에 영향 없어야 한다."""
    strat = _make_strat()
    strat.config.params["min_market_cap"] = 999_999_999_999_999  # 극단적 시총 기준
    strat.config.params["min_trade_amount"] = 0  # 거래대금 통과

    async def fake_detail(ticker):
        return {
            "stck_prpr": "100",
            "lstn_stcn": "100",  # mcap=10,000 (시총 미달)
            "prdy_vol": "1000000",
            "hts_kor_isnm": "테스트",
        }

    async def fake_rank():
        return [{"mksc_shrn_iscd": "005930", "hts_kor_isnm": "삼성전자"}]

    monkeypatch.setattr("src.api.condition._fetch_fluctuation_rank", fake_rank)
    monkeypatch.setattr("src.api.condition.fetch_stock_detail", fake_detail)

    await strat._scan_universe()
    assert strat._scan_stats["min_trade_amount_failed"] == 0
