"""사이클 94 H-4 — 단일 호출 + KOSPI 250 + KOSDAQ 250 = 500 정합 (HIGH).

명세 (`_workspace/red/cycle94_fid_input_iscd_fix.md`):

- 사이클 89 의도 영속 = KOSPI 250 + KOSDAQ 250 합집합 500 ticker
- 사이클 94 단일 호출 (`"0000"`) + post-split 으로 동일 결과 영속
- top_n cap 영속 (각 시장 250 ceiling)

기대 동작 (Green, backend-dev 인계):
- `_fetch_volume_rank` 단일 호출 (mock 600 ticker = KOSPI 300 + KOSDAQ 300)
- post-split → KOSPI 300 / KOSDAQ 300
- 각 250 ceiling 적용 → kospi[:250] + kosdaq[:250] = 500
- 결과 = 정확 500 ticker

Red 상태 (사이클 94): production 사이클 89 2회 호출 (`"0001"`/`"0002"`) 영속 → 30 + 30 = 60 → FAIL.

영속 의무:
- 사이클 89 KOSPI 250 + KOSDAQ 250 의도 영속 (post-split 영역으로 영속)
- 단일 호출 = KIS API 호출 수 절반 감소
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 96 Q50=D — 사이클 89 영역 복원 (2회 호출). "
        "사이클 94 H-4 영역 (단일 호출 + post-split) 폐기 계약 = 사이클 96 영역 복원 후 2회 호출 영속 정상. "
        "KIS 운영 실측 '0000' = 단일 페이지 30 한도 + 페이징 미지원 silent 결함. "
        "사이클 66 K-2 의미 전환 패턴."
    ),
)
@pytest.mark.asyncio
async def test_h4_single_call_kospi_250_kosdaq_250_split():
    """H-4: 단일 호출 (600 ticker mock) → post-split → KOSPI 250 + KOSDAQ 250 = 500.

    검증 매트릭스:
    - mock _fetch_volume_rank(market="all") → 600 ticker (KOSPI 300 + KOSDAQ 300)
    - mock stock_master.get() → ticker 짝수 = KOSPI, 홀수 = KOSDAQ
    - 결과 = 정확 500 ticker (각 시장 250 ceiling 영속)

    Red 상태 (사이클 94): 사이클 89 영속 2회 호출 + 30건 한도 → 60 ticker → FAIL.

    Green (backend-dev):
    - _fetch_volume_rank 단일 호출 영역
    - post-split + kospi[:250] + kosdaq[:250] 영속
    - 결과 500 ticker

    영속 의무:
    - 사이클 89 의도 (500 ticker) 영속
    - 단일 호출 = 효율 + 사용자 보고 결함 시정
    """
    from src.engine.scanner import fetch_top_500_universe
    from src.models.stock import StockBasics

    # mock 600 ticker (KOSPI 300 + KOSDAQ 300, 각 시장 250 ceiling 영속 검증)
    mock_response = []
    for i in range(600):
        ticker = f"{i:06d}"
        mock_response.append({
            "mksc_shrn_iscd": ticker,
            "prdy_vol": 1_000_000 - i,  # 거래량 desc (정렬 영역 영속)
            "stck_prpr": 50_000,
            "prdy_vrss": 1_000,
            "prdt_type_cd": "300",
        })

    # mock stock_master.get(): 짝수 ticker = KOSPI("02"), 홀수 = KOSDAQ("03")
    # 양쪽 컬럼 (excg_dvsn_cd 옵션 A + market_id 옵션 B) 호환 mock
    def _make_sm_data(ticker: str) -> StockBasics:
        idx = int(ticker)
        if idx % 2 == 0:
            return StockBasics(
                ticker=ticker, name=f"종목{ticker}",
                excg_dvsn_cd="02",  # 옵션 A KOSPI
                raw={"market_id": "STK"},  # 옵션 B KOSPI
            )
        else:
            return StockBasics(
                ticker=ticker, name=f"종목{ticker}",
                excg_dvsn_cd="03",  # 옵션 A KOSDAQ
                raw={"market_id": "KSQ"},  # 옵션 B KOSDAQ
            )

    sm_data_map = {f"{i:06d}": _make_sm_data(f"{i:06d}") for i in range(600)}

    fetch_call_log: list[dict] = []

    async def _fake_fetch_volume_rank(market="all", top_n=500, max_pages=17):
        fetch_call_log.append({"market": market, "top_n": top_n})
        return mock_response

    async def _fake_sm_get(ticker: str):
        return sm_data_map.get(ticker)

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)), \
         patch("src.db.stock_master.get",
               new=AsyncMock(side_effect=_fake_sm_get)):
        result = await fetch_top_500_universe()

    # 가드 1: _fetch_volume_rank 단일 호출 (사이클 89 2회 호출 폐기)
    assert len(fetch_call_log) == 1, (
        f"\n사이클 94 H-4 위반 — `_fetch_volume_rank` 호출 수 결함:\n"
        f"  기대: 1 (단일 호출 영역)\n"
        f"  실제: {len(fetch_call_log)}\n"
        f"  사이클 89 2회 호출 영속 결함 영구 시정 의무"
    )

    # 가드 2: 결과 = 정확 500 ticker (각 시장 250 ceiling)
    assert len(result) == 500, (
        f"\n사이클 94 H-4 위반 — 결과 ticker 수 결함:\n"
        f"  기대: 500 (KOSPI 250 + KOSDAQ 250)\n"
        f"  실제: {len(result)}\n"
        f"  사이클 89 의도 (500 ticker) 영속 의무"
    )

    # 가드 3: KOSPI 250 (짝수 ticker) + KOSDAQ 250 (홀수 ticker) 균형 영역
    even_count = sum(1 for t in result if int(t) % 2 == 0)
    odd_count = sum(1 for t in result if int(t) % 2 == 1)

    assert even_count == 250, (
        f"\n사이클 94 H-4 위반 — KOSPI ceiling 결함:\n"
        f"  기대: 250 (KOSPI 짝수 ticker)\n"
        f"  실제: {even_count}\n"
        f"  Green 의무: kospi[:250] 영속"
    )
    assert odd_count == 250, (
        f"\n사이클 94 H-4 위반 — KOSDAQ ceiling 결함:\n"
        f"  기대: 250 (KOSDAQ 홀수 ticker)\n"
        f"  실제: {odd_count}\n"
        f"  Green 의무: kosdaq[:250] 영속"
    )
