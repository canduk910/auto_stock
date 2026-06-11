"""사이클 23 P1-2 Red — BFB `min_trade_amount_failed` scan_stats 카운터.

요구 행위:
1. `_empty_scan_stats()` 에 `min_trade_amount_failed` 키 기본 0
2. `_scan_universe` 에서 거래대금 미달 시 카운터 증가
3. 시총 미달은 `min_trade_amount_failed` 에 영향 없음 (분리 검증)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

_xfail_cycle108 = pytest.mark.xfail(
    strict=False,
    reason="사이클 108 stock_master 전환으로 BFB volume-rank 호출 패턴 폐기 — "
           "과거 계약 영속 보존 (사이클 97 K-2 패턴 답습)",
)


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


# 사이클 48 (2026-05-27) — BFB 유니버스가 volume-rank(FHPST01710000) prdy_vol 기반으로
# 시간무관화. mock 도 kis_get 으로 갱신 (기존 _fetch_fluctuation_rank/fetch_stock_detail 폐기).
def _patch_kis_get(monkeypatch, output):
    async def _fake_kis_get(path, tr_id, params):
        return {"output": output}
    import src.engine.strategies.bull_flag_breakout as bfb_mod
    from src.api import base as base_mod
    monkeypatch.setattr(bfb_mod, "kis_get", _fake_kis_get, raising=False)
    monkeypatch.setattr(base_mod, "kis_get", _fake_kis_get, raising=False)


@_xfail_cycle108
@pytest.mark.asyncio
async def test_min_trade_amount_failed_increments_on_trade_amount_fail(monkeypatch):
    """거래대금 미달 종목에서 min_trade_amount_failed 카운터가 증가해야 한다."""
    strat = _make_strat()
    strat.config.params["min_market_cap"] = 0  # 시총 통과 보장
    strat.config.params["min_trade_amount"] = 999_999_999_999_999  # 극단적 거래대금 기준

    # volume-rank mock — 시총만 충분, 전일 거래대금은 미달
    _patch_kis_get(monkeypatch, [{
        "mksc_shrn_iscd": "005930",
        "hts_kor_isnm": "삼성전자",
        "stck_prpr": "10000",
        "lstn_stcn": "10000000",  # mcap=1000억 (시총 통과)
        "prdy_vol": "100",        # prdy_trade_amt=100×10000=1,000,000 (미달)
        "prdy_vrss": "0",
    }])

    await strat._scan_universe()
    assert strat._scan_stats["min_trade_amount_failed"] >= 1


@_xfail_cycle108
@pytest.mark.asyncio
async def test_mcap_fail_does_not_increment_min_trade_amount_failed(monkeypatch):
    """시총 미달 종목은 min_trade_amount_failed 에 영향 없어야 한다."""
    strat = _make_strat()
    strat.config.params["min_market_cap"] = 999_999_999_999_999  # 극단적 시총 기준
    strat.config.params["min_trade_amount"] = 0  # 거래대금 통과

    _patch_kis_get(monkeypatch, [{
        "mksc_shrn_iscd": "005930",
        "hts_kor_isnm": "삼성전자",
        "stck_prpr": "100",
        "lstn_stcn": "100",  # mcap=10,000 (시총 미달)
        "prdy_vol": "1000000",
        "prdy_vrss": "0",
    }])

    await strat._scan_universe()
    assert strat._scan_stats["min_trade_amount_failed"] == 0
