"""bull_flag_breakout `_scan_universe()` 정합성 회귀 가드.

2026-05-15 사이클(bull_flag_breakout 전략 추가) 시점부터 5/18까지 운영 환경에서
`prepare()` 매 호출이 `ImportError: cannot import name 'scan_volume_rank'` 로 실패하여
전략이 완전 비활성(매수 신호 0건, 보유 0건)되던 결함 회귀 가드.

사이클 48 (2026-05-27) — 유니버스 시간무관화. BFB 가 VB/LTV 와 동일하게
volume-rank(FHPST01710000) prdy_vol 기반으로 교체 (07:50 장 전 acml_vol=0 결함 시정).
본 테스트도 volume-rank mock 으로 갱신.

검증 포인트:
- `_scan_universe()` 가 import/호출 오류 없이 정상 완료
- volume-rank 응답 스키마 호환 (`mksc_shrn_iscd`/`hts_kor_isnm`/`stck_prpr`/`lstn_stcn`/`prdy_vol`/`prdy_vrss`)
- 시총·전일거래대금 컷 적용 (개별 호출 없이 응답 1건으로 산출)
- `_scan_stats["universe_candidates"]` / `["universe_filtered"]` 갱신
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit

_xfail_cycle108 = pytest.mark.xfail(
    strict=False,
    reason="사이클 108 stock_master 전환으로 BFB volume-rank 호출 패턴 폐기 — "
           "과거 계약 영속 보존 (사이클 97 K-2 패턴 답습)",
)


def _vrank_item(ticker: str, name: str = "샘플전자", price: int = 50_000,
                listed: int = 50_000_000, prdy_vol: int = 5_000_000,
                prdy_vrss: int = 0) -> dict[str, Any]:
    """volume-rank(FHPST01710000) `output` 단일 항목 모사 (시총·거래대금 컷 통과용).

    50,000 × 50,000,000 = 2.5조 시총 / 50,000 × 5,000,000 = 2,500억 전일거래대금.
    """
    return {
        "mksc_shrn_iscd": ticker,
        "hts_kor_isnm": name,
        "stck_prpr": str(price),
        "lstn_stcn": str(listed),
        "prdy_vol": str(prdy_vol),
        "prdy_vrss": str(prdy_vrss),
    }


def _patch_vrank(monkeypatch, output: list[dict[str, Any]]):
    """volume-rank kis_get 을 단일 응답으로 패치. blng 0/1/3 3회 호출 모두 동일 output."""
    calls = {"count": 0}

    async def _fake_kis_get(path, tr_id, params):
        calls["count"] += 1
        return {"output": output}

    import src.engine.strategies.bull_flag_breakout as bfb_mod
    from src.api import base as base_mod
    monkeypatch.setattr(bfb_mod, "kis_get", _fake_kis_get, raising=False)
    monkeypatch.setattr(base_mod, "kis_get", _fake_kis_get, raising=False)
    return calls


@pytest.fixture
def bfb(monkeypatch):
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {})
    return BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0)
    )


# ---------------------------------------------------------------------------
# 1) 정상 완료 회귀 가드 — `_scan_universe()` 가 오류 없이 후보 산출
# ---------------------------------------------------------------------------
@_xfail_cycle108
@pytest.mark.asyncio
async def test_scan_universe_completes_without_error(bfb, monkeypatch):
    """`_scan_universe()` 가 volume-rank 호출 + 시총·거래대금 컷 후 list 반환.

    5/15~5/18 운영 결함(ImportError → 전략 비활성) 회귀 가드 + 사이클 48 prdy 시간무관 정합.
    """
    _patch_vrank(monkeypatch, [
        _vrank_item("005930", "샘플전자"),
        _vrank_item("000660", "샘플하이닉스"),
    ])

    result = await bfb._scan_universe()

    assert isinstance(result, list)
    # 시총·전일거래대금 컷 통과
    assert "005930" in result
    assert "000660" in result


# ---------------------------------------------------------------------------
# 2) _scan_stats 갱신 — universe_candidates / universe_filtered 카운트
# ---------------------------------------------------------------------------
@_xfail_cycle108
@pytest.mark.asyncio
async def test_scan_universe_updates_scan_stats(bfb, monkeypatch):
    """`_scan_universe()` 가 _scan_stats 의 universe_candidates / universe_filtered 를 갱신."""
    _patch_vrank(monkeypatch, [_vrank_item("005930")])

    await bfb._scan_universe()

    # blng 0/1/3 합집합 dedupe → 동일 종목 1건
    assert bfb._scan_stats["universe_candidates"] == 1
    assert bfb._scan_stats["universe_filtered"] == 1
