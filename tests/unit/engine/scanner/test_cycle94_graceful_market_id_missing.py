"""사이클 94 M-3 — graceful: stock_master 부재 종목 자연 skip (사이클 88 G-REJECT 답습) (MEDIUM).

명세 (`_workspace/red/cycle94_fid_input_iscd_fix.md` §4 M-3):

- Q42=A post-split = stock_master.get() 호출 + 분류 불가 시 graceful 영속
- stock_master 캐시 miss = 분류 불가 → KOSPI/KOSDAQ 양쪽 누락 (보수적 skip)
- 사이클 88 G-REJECT 답습 (graceful 패턴 영속)
- 사이클 32 R4 universe guard 답습 (영구 블랙리스트 금지)

기대 동작 (Green, backend-dev 인계):
- mock 응답 ticker 일부 (50%) stock_master miss → graceful skip
- 분류된 ticker 만 결과 포함 (KOSPI/KOSDAQ 영역)
- 예외 발생 없음

Red 상태 (사이클 94): production 사이클 89 영속 — stock_master.get() 호출 0건 →
graceful 영역 부재 → FAIL (단순 ImportError 또는 호출 카운트 결함).

영속 의무:
- 사이클 88 G-REJECT 패턴 답습
- 사이클 32 R4 universe guard 답습 (영구 블랙리스트 금지)
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_m3_graceful_missing_market_id_skips_ticker():
    """M-3: stock_master miss 시 graceful skip 영역 영속 (사이클 88 G-REJECT 답습).

    검증 매트릭스:
    - mock 응답 6 ticker
    - mock stock_master.get(): 3 ticker → KOSPI / 3 ticker → None (miss)
    - 결과 = KOSPI 3 ticker 만 포함 (miss 3 ticker 자연 skip)
    - 예외 발생 없음 (graceful 영속)

    Red 상태 (사이클 94): production 사이클 89 영속 → stock_master.get() 호출 0건 →
    분류 영역 부재 → 모든 ticker 포함 (graceful 영역 미적용) → FAIL.

    Green (backend-dev): graceful skip 영속 (예외 흡수 + None 처리) → PASS.

    영속 의무: 사이클 88 G-REJECT 답습 (graceful 영역 영속).
    """
    from src.engine.scanner import fetch_top_500_universe
    from src.models.stock import StockBasics

    # mock 6 ticker (모두 보통주)
    mock_response = [
        {"mksc_shrn_iscd": f"00000{i}", "prdy_vol": 1_000_000 - i, "stck_prpr": 50_000,
         "prdy_vrss": 500, "prdt_type_cd": "300"}
        for i in range(1, 7)
    ]

    # stock_master: 3 ticker → KOSPI, 3 ticker → None (miss)
    sm_data_map = {
        "000001": StockBasics(ticker="000001", name="종목1", excg_dvsn_cd="02",
                              raw={"market_id": "STK"}),
        "000002": StockBasics(ticker="000002", name="종목2", excg_dvsn_cd="02",
                              raw={"market_id": "STK"}),
        "000003": StockBasics(ticker="000003", name="종목3", excg_dvsn_cd="02",
                              raw={"market_id": "STK"}),
        # "000004", "000005", "000006" = miss (None 반환)
    }

    async def _fake_fetch_volume_rank(market="all", top_n=500, max_pages=17):
        return mock_response

    async def _fake_sm_get(ticker: str):
        return sm_data_map.get(ticker)  # miss = None

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)), \
         patch("src.db.stock_master.get",
               new=AsyncMock(side_effect=_fake_sm_get)):
        # graceful 영속 = 예외 발생 없음
        result = await fetch_top_500_universe()

    # 가드 1: 결과 영역 = 분류 가능 ticker 만 포함 (miss 자연 skip)
    # graceful 영역 = miss ticker (000004, 000005, 000006) 자연 제외 영속
    miss_tickers = {"000004", "000005", "000006"}
    leaked_miss = miss_tickers & set(result)

    # 가드 1-a: miss ticker 가 graceful 영역에서 자연 제외됨 (Q42=A 영속)
    assert leaked_miss == set(), (
        f"\n사이클 94 M-3 위반 — miss ticker graceful 영역 결함:\n"
        f"  miss ticker (분류 불가): {miss_tickers}\n"
        f"  결과 영역 유출: {leaked_miss}\n"
        f"  Q42=A 영속: stock_master miss = 분류 불가 = 보수적 skip\n"
        f"  사이클 88 G-REJECT 답습 의무"
    )

    # 가드 2: 분류 가능 ticker 영역 (000001~000003 KOSPI) 영속 포함
    classified = {"000001", "000002", "000003"}
    present_classified = classified & set(result)
    assert present_classified == classified, (
        f"\n사이클 94 M-3 위반 — 분류 가능 ticker 누락:\n"
        f"  기대 (KOSPI 분류): {classified}\n"
        f"  실제: {present_classified}\n"
        f"  graceful 영역은 miss skip 만 영속 (분류 가능 ticker 영속)"
    )

    # 가드 3: 예외 발생 없음 (graceful 영속) - 본 시점까지 도달 = 예외 없음
    assert isinstance(result, list), (
        f"\n사이클 94 M-3 위반 — 반환 타입 결함 (graceful 영역 예외 위험):\n"
        f"  기대: list[str]\n"
        f"  실제: {type(result).__name__}"
    )
