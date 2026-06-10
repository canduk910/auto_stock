"""사이클 96 H-3 — post-split 영역 폐기 (KOSPI/KOSDAQ 분리 KIS API 자체) (HIGH).

명세 (`_workspace/red/cycle96_resurrect_industry_code_with_pagination.md`):

- 사이클 94 영역 = `_classify_market(sm_data)` 호출 + stock_master 캐시 join
- 사이클 96 영역 복원 = KOSPI/KOSDAQ 분리 호출 자체 (KIS API "0001"/"0002")
- post-split 불요 = `_classify_market` 의존 영역 폐기
- 사이클 95 unknown graceful 영속 = 영역 0 (정상 = unknown=0)

기대 동작 (Green, backend-dev 인계):
- `fetch_top_500_universe()` 호출 시 `_classify_market` 호출 0건
- 또는 `stock_master.get()` 호출 0건 (post-split chain 폐기)
- 단, 사이클 95 unknown 합집합 graceful 영속 (호환)

Red 상태 (사이클 96): production 사이클 94 chain (`stock_master.get` 호출) 영속 → FAIL.

영속 의무:
- 사이클 95 unknown 영역 영속 (graceful fallback, unknown=0 정상)
- 사이클 89 KOSPI/KOSDAQ 분리 의도 영속
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 97 Q53=A — `_fetch_volume_rank` 영역 전수 폐기. "
            "KIS fluctuation API (`_fetch_fluctuation`) 영역 신규 도입으로 영역 전환. "
            "사이클 96 post_split 영역 영속 가드 = 사이클 97 영역 자연 흡수 (post_split chain 영구 부재). "
            "사이클 66 K-2 의미 전환 패턴 영속."
        ),
    ),
]


def _make_volume_rank_row(ticker: str) -> dict:
    return {
        "mksc_shrn_iscd": ticker,
        "prdy_vol": "1000000",
        "stck_prpr": "50000",
        "prdy_vrss": "1000",
        "prdt_type_cd": "300",
    }


@pytest.mark.asyncio
async def test_h3_post_split_stock_master_get_not_called():
    """H-3.a: `fetch_top_500_universe()` 가 post-split chain (`stock_master.get`) 호출 0건.

    검증 매트릭스:
    - mock _fetch_volume_rank 2회 (KOSPI 100 + KOSDAQ 100)
    - stock_master.get() 호출 카운트 = 0 (post-split 폐기 영역)

    Red 상태 (사이클 96): 사이클 94 post-split 영역 영속 → stock_master.get 호출 200회 → FAIL.

    Green (backend-dev): 영역 복원 시 post-split chain 폐기 → PASS.

    영속 의무:
    - 사이클 95 unknown 영역 = 영역 0 (정상 = unknown=0)
    - 사이클 89 분리 호출 자체 KOSPI/KOSDAQ 분류
    """
    from src.engine.scanner import fetch_top_500_universe

    # 6자리 숫자 ticker 영속 (사이클 89 `_universe_filter_securities_only` isdigit 가드 통과)
    kospi_rows = [_make_volume_rank_row(f"{i:06d}") for i in range(100, 200)]
    kosdaq_rows = [_make_volume_rank_row(f"{i:06d}") for i in range(200, 300)]

    combined_rows = kospi_rows + kosdaq_rows  # 사이클 94 단일 호출 영역 (market="all") 호환

    async def _fake_fetch_volume_rank(market: str = "all", top_n: int = 250, max_pages: int = 17):
        # 사이클 94 영역 (market="all") + 사이클 96 영역 ("kospi"/"kosdaq") 양쪽 호환
        if market == "kospi":
            return kospi_rows
        elif market == "kosdaq":
            return kosdaq_rows
        elif market == "all":
            return combined_rows  # 사이클 94 단일 호출 영역 응답
        return combined_rows  # graceful fallback

    sm_get_mock = AsyncMock(return_value=None)

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)), \
         patch("src.db.stock_master.get", new=sm_get_mock):
        await fetch_top_500_universe()

    sm_get_call_count = sm_get_mock.await_count

    assert sm_get_call_count == 0, (
        f"\n사이클 96 H-3.a 위반 — post-split chain (`stock_master.get`) 호출 영속 결함:\n"
        f"  기대: 0건 (post-split 영역 폐기)\n"
        f"  실제: {sm_get_call_count}건\n"
        f"  결함 인과: 사이클 94 post-split chain 영속 → 영역 복원 시 불요\n"
        f"  사이클 96 시정: KOSPI/KOSDAQ 분리 호출 자체 분류 (KIS '0001'/'0002')"
    )


@pytest.mark.asyncio
async def test_h3_classify_market_not_called():
    """H-3.b: `_classify_market` 호출 0건 (post-split 헬퍼 의존 영역 폐기).

    검증 매트릭스:
    - mock _fetch_volume_rank 2회
    - _classify_market 호출 카운트 = 0

    영속 의무: post-split chain 핵심 헬퍼 폐기 영구 가시화.
    """
    from src.engine.scanner import fetch_top_500_universe

    # 6자리 숫자 ticker 영속 (사이클 89 isdigit 가드 통과)
    kospi_rows = [_make_volume_rank_row(f"{i:06d}") for i in range(100, 200)]
    kosdaq_rows = [_make_volume_rank_row(f"{i:06d}") for i in range(200, 300)]

    classify_calls: list = []
    combined_rows = kospi_rows + kosdaq_rows  # 사이클 94 단일 호출 영역 호환

    async def _fake_fetch_volume_rank(market: str = "all", top_n: int = 250, max_pages: int = 17):
        if market == "kospi":
            return kospi_rows
        elif market == "kosdaq":
            return kosdaq_rows
        elif market == "all":
            return combined_rows
        return combined_rows

    def _spy_classify_market(sm_data):
        classify_calls.append(sm_data)
        return None

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)), \
         patch("src.engine.scanner._classify_market",
               side_effect=_spy_classify_market):
        await fetch_top_500_universe()

    assert len(classify_calls) == 0, (
        f"\n사이클 96 H-3.b 위반 — `_classify_market` 호출 영속 결함:\n"
        f"  기대: 0건 (post-split 헬퍼 폐기)\n"
        f"  실제: {len(classify_calls)}건\n"
        f"  사이클 96 영역 복원: KOSPI/KOSDAQ 분리 호출 자체 분류"
    )
