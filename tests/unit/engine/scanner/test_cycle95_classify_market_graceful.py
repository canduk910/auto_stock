"""사이클 95 H-3 — `_classify_market` graceful None 영속 + unknown 영역 분리 (HIGH).

명세 (`_workspace/red/cycle95_chicken_and_egg_fix_ui.md`):

- `_classify_market(sm_data)` (`src/engine/scanner.py:1413~1437`) 시그너처 변경 0
- None 반환 영속 (graceful — 분류 불가 영역)
- 사이클 95 시정 = **호출자** (`fetch_top_500_universe`) None 분기 처리 변경 (continue → unknown.append)

본 가드는 `_classify_market` 함수 본체 변경 0 영속을 검증 + 호출자 None 분기 → unknown 분리 검증.

영속 의무:
- 사이클 94 영역 3 (Q42=A) `_classify_market` 시그너처 절대 변경 금지
- "02" → KOSPI / "03" → KOSDAQ / 기타 → None 정합 영속
- KIS CTPF1002R 정본 영속
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_volume_rank_row(ticker: str) -> dict:
    return {
        "mksc_shrn_iscd": ticker,
        "prdy_vol": "1000000",
        "stck_prpr": "50000",
        "prdy_vrss": "1000",
    }


def _make_stock_basics(ticker: str, excg_dvsn_cd: str | None):
    """StockBasics mock with optional excg_dvsn_cd."""
    from src.models.stock import StockBasics

    return StockBasics(
        ticker=ticker,
        name=f"종목{ticker}",
        excg_dvsn_cd=excg_dvsn_cd or "",
        raw={"mksc_shrn_iscd": ticker},
    )


def test_h3_classify_market_none_for_absent_sm_data():
    """H-3.a: `_classify_market(None)` = None (graceful 영속)."""
    from src.engine.scanner import _classify_market

    result = _classify_market(None)
    assert result is None, (
        f"\n사이클 95 H-3.a 위반 — `_classify_market(None)` graceful 영속 결함:\n"
        f"  기대: None (graceful — 분류 불가)\n"
        f"  실제: {result}\n"
        f"  영속 의무: 사이클 94 영역 3 (Q42=A) 시그너처 절대 변경 금지"
    )


def test_h3_classify_market_kospi_kosdaq_unknown_partition():
    """H-3.b: "02"=KOSPI / "03"=KOSDAQ / 기타=None 정합 영속.

    검증 매트릭스 (KIS CTPF1002R 정본):
    - "02" → KOSPI
    - "03" → KOSDAQ
    - "01" → None (사이클 95 unknown 영역 진입 대상)
    - "" → None
    - 빈 sm_data → None
    """
    from src.engine.scanner import _classify_market

    assert _classify_market(_make_stock_basics("005930", "02")) == "KOSPI"
    assert _classify_market(_make_stock_basics("035720", "03")) == "KOSDAQ"
    assert _classify_market(_make_stock_basics("004250", "01")) is None  # ETF 등 → unknown
    assert _classify_market(_make_stock_basics("XX0000", "")) is None     # 빈 코드 → unknown
    assert _classify_market(None) is None                                  # 부재 → unknown


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 97 Q53=A — `_fetch_volume_rank` + post-split 영역 전수 폐기. "
        "사이클 95 unknown 합집합 영역 = 2회 분리 호출 (fluctuation API) 로 unknown=0 정상. "
        "사이클 97 M-1 unknown=0 영속 가드가 영역 흡수. "
        "사이클 66 K-2 의미 전환 패턴 영속."
    ),
)
@pytest.mark.asyncio
async def test_h3_classify_market_unknown_appends_in_fetch_top_500_universe():
    """H-3.c: `fetch_top_500_universe` 가 `_classify_market` None 결과를 unknown 영역으로 분리.

    검증 매트릭스:
    - volume_rank 응답: KOSPI 1 + KOSDAQ 1 + 비분류 ("01" ETF 등) 1 + 부재 1 = 4건
    - 사이클 95 시정 후: KOSPI 1 + KOSDAQ 1 + unknown 2 = universe 4
    - 비분류/부재 양쪽 모두 unknown 합집합 영역 진입

    Red (사이클 95): None continue → universe 2 → FAIL.

    Green: unknown 합집합 → universe 4 → PASS.
    """
    from src.engine import scanner

    tickers = ["005930", "035720", "004250", "999999"]
    raw_rows = [_make_volume_rank_row(t) for t in tickers]
    sm_map = {
        "005930": _make_stock_basics("005930", "02"),
        "035720": _make_stock_basics("035720", "03"),
        "004250": _make_stock_basics("004250", "01"),  # ETF 등 → unknown
        # 999999 = stock_master 부재 → unknown
    }

    async def fake_get(ticker: str):
        return sm_map.get(ticker)

    with patch.object(scanner, "_fetch_volume_rank", new=AsyncMock(return_value=raw_rows)), \
         patch("src.db.stock_master.get", side_effect=fake_get):
        universe = await scanner.fetch_top_500_universe()

    universe_set = set(universe)
    assert universe_set == set(tickers), (
        f"\n사이클 95 H-3.c 위반 — unknown 분리 결함:\n"
        f"  기대: KOSPI 1 + KOSDAQ 1 + unknown 2 (비분류 + 부재) = 4 ticker\n"
        f"  실제: {sorted(universe_set)}\n"
        f"  결함 인과: None continue → 비분류/부재 자연 skip\n"
        f"  시정: unknown 합집합 → KIS 호출 0건 증가 + chicken-and-egg 차단"
    )
