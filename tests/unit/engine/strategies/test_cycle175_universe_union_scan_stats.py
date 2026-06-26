"""사이클 175 — donchian/VCP scan_stats `universe_union`(합집합) 노출 회귀 가드.

대시보드 조건검색 현황(ScanMonitor)의 "코스피200+코스닥150 합집합" 단계가
조건검색 추적(DB funnel) step1(union_tickers)과 정합하도록 scan_stats 에
`universe_union`(시총/거래대금 컷 *전* 합집합) 노출. 기존 `universe_candidates`
(= list_by_filter 결과 = 필터 *후*) 와 분리.

근본: list_by_filter 가 시총/거래대금 컷을 내부 적용 → `len(rows)` 는 이미 필터 후.
ScanMonitor 가 이를 "합집합"으로 라벨 → mislabel. union 은 return_stage_counts 로만 노출.
"""
from __future__ import annotations

import pytest

from src.db.system_config import PriceFilter
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit

# 합집합(union) 5종목 → 시총/거래대금 컷 후 2종목(rows = list_by_filter 결과)
_FILTERED = [
    {"ticker": "005930", "name": "삼성전자", "raw": {}},
    {"ticker": "000660", "name": "SK하이닉스", "raw": {}},
]
_UNION = ["005930", "000660", "035420", "051910", "066570"]  # 5종목 합집합


async def _fake_list_by_filter(**kwargs):
    rows = [dict(r) for r in _FILTERED]
    if kwargs.get("return_stage_counts"):
        tickers = [r["ticker"] for r in rows]
        return rows, {
            "union_tickers": list(_UNION),   # 합집합 5
            "mcap_tickers": tickers,
            "trade_tickers": tickers,
        }
    return rows


async def _fake_price_filter():
    return PriceFilter(min_price=0, max_price=0)


def test_donchian_empty_scan_stats_has_universe_union():
    from src.engine.strategies.donchian_swing import _empty_scan_stats
    assert _empty_scan_stats().get("universe_union") == 0


def test_vcp_empty_scan_stats_has_universe_union():
    from src.engine.strategies.vcp_breakout import _empty_scan_stats
    assert _empty_scan_stats().get("universe_union") == 0


@pytest.mark.asyncio
async def test_donchian_universe_union_is_union_not_filtered(monkeypatch):
    """donchian — universe_union = 합집합(5) ≠ universe_candidates = 필터 후(2)."""
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="d", weight=0.0)
    )
    monkeypatch.setattr("src.db.stock_master.list_by_filter", _fake_list_by_filter)
    monkeypatch.setattr("src.db.system_config.get_price_filter", _fake_price_filter)

    await strat._scan_universe()

    assert strat._scan_stats["universe_union"] == 5, "합집합(union)이 노출돼야"
    assert strat._scan_stats["universe_candidates"] == 2, "필터 후는 그대로"
    assert strat._scan_stats["universe_union"] > strat._scan_stats["universe_candidates"]


@pytest.mark.asyncio
async def test_vcp_universe_union_is_union_not_filtered(monkeypatch):
    """VCP — return_stage_counts 추가로 universe_union = 합집합(5) 노출."""
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    strat = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="v", weight=0.0)
    )
    strat.config.params["min_market_cap"] = 1
    monkeypatch.setattr("src.db.stock_master.list_by_filter", _fake_list_by_filter)
    monkeypatch.setattr("src.db.system_config.get_price_filter", _fake_price_filter)

    await strat._scan_universe()

    assert strat._scan_stats["universe_union"] == 5
    assert strat._scan_stats["universe_candidates"] == 2
