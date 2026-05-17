"""bull_flag_breakout `_scan_universe()` import 정합성 회귀 가드.

2026-05-15 사이클(bull_flag_breakout 전략 추가) 시점부터 5/18까지 운영 환경에서
`prepare()` 매 호출이 `ImportError: cannot import name 'scan_volume_rank'` 로 실패하여
전략이 완전 비활성(매수 신호 0건, 보유 0건)되던 결함 회귀 가드.

검증 포인트:
- `_scan_universe()` 가 `ImportError` 없이 정상 완료
- `_fetch_fluctuation_rank` (등락률 순위 API `FHPST01700000`) 응답 스키마와 호환
  (`mksc_shrn_iscd` 또는 `stck_shrn_iscd` 키, `hts_kor_isnm` 종목명)
- 시총·거래대금 컷 적용 — `fetch_stock_detail` 로 종목 보강
- `_scan_stats["universe_candidates"]` / `["universe_filtered"]` 갱신
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


def _rank_item(ticker: str, name: str = "샘플전자") -> dict[str, Any]:
    """등락률 순위(FHPST01700000) `output` 단일 항목 모사.

    실제 응답 키:
    - stck_shrn_iscd (단축종목코드, 6자리)
    - hts_kor_isnm (종목명)
    - stck_prpr (현재가), prdy_ctrt (전일대비율) 등
    """
    return {
        "stck_shrn_iscd": ticker,
        "hts_kor_isnm": name,
        "stck_prpr": "50000",
        "prdy_ctrt": "5.0",
    }


def _detail_response(price: int = 50_000, listed: int = 50_000_000,
                     prdy_vol: int = 5_000_000) -> dict[str, Any]:
    """fetch_stock_detail 응답 모사 (시총 · 전일거래량 컷 통과용)."""
    return {
        "stck_prpr": str(price),
        "lstn_stcn": str(listed),
        "prdy_vol": str(prdy_vol),
        "hts_kor_isnm": "샘플전자",
    }


@pytest.fixture
def bfb(monkeypatch):
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {})
    return BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0)
    )


# ---------------------------------------------------------------------------
# 1) ImportError 회귀 가드 — `_scan_universe()` 가 정상 import 후 완료
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_universe_imports_fluctuation_rank_without_error(bfb):
    """`_scan_universe()` 가 `_fetch_fluctuation_rank` 를 정상 import + 호출.

    5/15~5/18 운영 결함: `scan_volume_rank` 미존재 함수 import → ImportError →
    `prepare()` 전체 실패 → 전략 비활성. 본 케이스가 ImportError 자체를 차단.
    """
    rank_mock = AsyncMock(return_value=[_rank_item("005930"), _rank_item("000660", "샘플하이닉스")])
    detail_mock = AsyncMock(return_value=_detail_response())

    with patch("src.api.condition._fetch_fluctuation_rank", rank_mock), \
         patch("src.api.condition.fetch_stock_detail", detail_mock):
        result = await bfb._scan_universe()

    # ImportError 없이 list 반환
    assert isinstance(result, list)
    # 등락률 순위 API 1회 호출
    assert rank_mock.call_count == 1
    # 시총·거래대금 컷 통과한 종목들 (50,000 × 50,000,000 = 2.5조 시총, 50,000 × 5,000,000 = 2,500억 거래대금)
    assert "005930" in result
    assert "000660" in result


# ---------------------------------------------------------------------------
# 2) _scan_stats 갱신 — universe_candidates / universe_filtered 카운트
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_universe_updates_scan_stats(bfb):
    """`_scan_universe()` 가 _scan_stats 의 universe_candidates / universe_filtered 를 갱신."""
    rank_mock = AsyncMock(return_value=[_rank_item("005930")])
    detail_mock = AsyncMock(return_value=_detail_response())

    with patch("src.api.condition._fetch_fluctuation_rank", rank_mock), \
         patch("src.api.condition.fetch_stock_detail", detail_mock):
        await bfb._scan_universe()

    assert bfb._scan_stats["universe_candidates"] == 1
    assert bfb._scan_stats["universe_filtered"] == 1
