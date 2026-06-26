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
    """시총 통과 종목이 있을 때 mcap_pass 카운터가 증가해야 한다.

    사이클 157 (2026-06-17) 의미 전환 영구 영속 — VCP `_scan_universe()` 영역이
    `list_by_filter(is_kospi200=True, is_kosdaq150=True, min_market_cap=...)` 호출 영구 영속.
    list_by_filter 가 이미 시총 필터링 → 결과 전체에 mcap_pass = len(rows) 영구 영속.
    """
    strat = _make_strat()
    strat.config.params["min_market_cap"] = 1  # 최소 시총 기준 (대부분 통과)
    strat.config.params["max_scan_stocks"] = 5

    # 사이클 157 — list_by_filter mock (사이클 153 donchian 패턴 답습)
    # 사이클 175 — VCP 가 return_stage_counts=True 사용 → (rows, stage) 튜플 반환
    async def fake_list_by_filter(**kwargs):
        rows = [
            {"ticker": "005930", "name": "삼성전자", "raw": {}},
            {"ticker": "000660", "name": "SK하이닉스", "raw": {}},
        ]
        if kwargs.get("return_stage_counts"):
            tickers = [r["ticker"] for r in rows]
            return rows, {"union_tickers": tickers, "mcap_tickers": tickers, "trade_tickers": tickers}
        return rows

    monkeypatch.setattr("src.db.stock_master.list_by_filter", fake_list_by_filter)

    # 가격 필터 비활성 mock
    from src.db.system_config import PriceFilter
    async def fake_get_price_filter():
        return PriceFilter(min_price=0, max_price=0)

    monkeypatch.setattr("src.db.system_config.get_price_filter", fake_get_price_filter)

    await strat._scan_universe()
    assert strat._scan_stats["mcap_pass"] >= 1
