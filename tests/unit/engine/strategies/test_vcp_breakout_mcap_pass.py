"""사이클 23 P1-3 Red — VCP `mcap_pass` scan_stats 1단계 추가.

요구 행위:
1. `_empty_scan_stats()` 에 `mcap_pass` 키 기본 0
2. `_scan_universe` 에서 시총 통과 시 `mcap_pass` 카운터 증가
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _make_strat():
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig
    return VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.0)
    )


def test_empty_scan_stats_has_mcap_pass_key():
    """_empty_scan_stats() 에 mcap_pass 키가 기본 0이어야 한다."""
    from src.engine.strategies.vcp_breakout import _empty_scan_stats
    stats = _empty_scan_stats()
    assert "mcap_pass" in stats
    assert stats["mcap_pass"] == 0


@pytest.mark.asyncio
async def test_mcap_pass_increments_when_mcap_passes(monkeypatch):
    """시총 통과 종목이 있을 때 mcap_pass 카운터가 증가해야 한다."""
    strat = _make_strat()
    strat.config.params["min_market_cap"] = 1  # 최소 시총 기준 (대부분 통과)
    strat.config.params["max_scan_stocks"] = 5

    # KOSPI200/KOSDAQ150 고정 유니버스 중 일부만 fake
    monkeypatch.setattr(
        "src.engine.scanner.KOSPI_200_TICKERS", ["005930", "000660"]
    )
    monkeypatch.setattr(
        "src.engine.scanner.KOSDAQ_150_TICKERS", []
    )

    async def fake_detail(ticker):
        return {
            "stck_prpr": "80000",
            "lstn_stcn": "5969782550",  # 충분한 시총
            "hts_kor_isnm": "삼성전자",
        }

    monkeypatch.setattr("src.api.condition.fetch_stock_detail", fake_detail)

    await strat._scan_universe()
    assert strat._scan_stats["mcap_pass"] >= 1
