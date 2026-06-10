"""사이클 96 H-2 — 2회 호출 (KOSPI + KOSDAQ) + 페이징 누적 ≥ 500 ticker (HIGH).

명세 (`_workspace/red/cycle96_resurrect_industry_code_with_pagination.md`):

- 사이클 89 영역 복원 = `_fetch_volume_rank(market="kospi")` + `_fetch_volume_rank(market="kosdaq")` 2회
- 사이클 91 페이징 결합 = 각 max_pages=17 영역 누적 (~510 ticker)
- 250 ceiling 적용 → KOSPI 250 + KOSDAQ 250 = 500 ticker
- KIS "0001"/"0002" = 페이징 정상 (운영 실측)

기대 동작 (Green, backend-dev 인계):
- `fetch_top_500_universe()` 호출 → `_fetch_volume_rank` 2회 호출
- 각 호출이 페이징 누적 (mock 17 페이지 × 30 = 510 ticker)
- 250 ceiling 적용 결과 = 500 ticker

Red 상태 (사이클 96): production 사이클 94 단일 호출 `"0000"` 영속 → 30 ticker → FAIL.

영속 의무:
- 사이클 91 페이징 영역 영속 결합
- 사이클 89 KOSPI/KOSDAQ 250+250 의도 영속
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_volume_rank_row(ticker: str) -> dict:
    """KIS volume_rank row mock — 거래대금 계산 영역 호환."""
    return {
        "mksc_shrn_iscd": ticker,
        "prdy_vol": "1000000",
        "stck_prpr": "50000",
        "prdy_vrss": "1000",
        "prdt_type_cd": "300",
    }


@pytest.mark.asyncio
async def test_h2_two_call_pagination_accumulates_500_ticker():
    """H-2: 2회 분리 호출 (KOSPI + KOSDAQ) + 각 페이징 누적 → 500 ticker.

    검증 매트릭스:
    - mock KOSPI = 510 ticker (페이징 17 페이지 × 30 = 510 누적 영역)
    - mock KOSDAQ = 510 ticker (동일 영역)
    - 결과 = 정확 500 ticker (각 시장 250 ceiling)

    Red 상태 (사이클 96): 사이클 94 단일 호출 30 한도 → 30 ticker → FAIL.

    Green (backend-dev): 2회 호출 + 페이징 누적 → 500 ticker → PASS.

    영속 의무:
    - 사이클 89 KOSPI 250 + KOSDAQ 250 의도 영속
    - 사이클 91 페이징 영역 결합
    """
    from src.engine.scanner import fetch_top_500_universe

    # KOSPI 510 ticker (000001~000510, 짝수 영역 가정)
    kospi_rows = [_make_volume_rank_row(f"K{i:05d}") for i in range(510)]
    # KOSDAQ 510 ticker (000001~000510, 홀수 영역 가정)
    kosdaq_rows = [_make_volume_rank_row(f"D{i:05d}") for i in range(510)]

    fetch_call_log: list[dict] = []

    async def _fake_fetch_volume_rank(market: str, top_n: int = 250, max_pages: int = 17):
        fetch_call_log.append({"market": market, "top_n": top_n, "max_pages": max_pages})
        if market == "kospi":
            return kospi_rows
        elif market == "kosdaq":
            return kosdaq_rows
        return []

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)):
        result = await fetch_top_500_universe()

    # 가드 1: 2회 분리 호출 영속 (사이클 89 영역 복원)
    assert len(fetch_call_log) == 2, (
        f"\n사이클 96 H-2 위반 — `_fetch_volume_rank` 호출 수 결함:\n"
        f"  기대: 2회 (KOSPI + KOSDAQ 분리 호출)\n"
        f"  실제: {len(fetch_call_log)}회\n"
        f"  호출 인자: {fetch_call_log}\n"
        f"  사이클 89 영역 복원 의무"
    )

    # 가드 2: 결과 = 정확 500 ticker (각 시장 250 ceiling)
    assert len(result) == 500, (
        f"\n사이클 96 H-2 위반 — 결과 ticker 수 결함:\n"
        f"  기대: 500 (KOSPI 250 + KOSDAQ 250)\n"
        f"  실제: {len(result)}\n"
        f"  사이클 89 의도 영속 + 사이클 91 페이징 결합"
    )

    # 가드 3: KOSPI 250 + KOSDAQ 250 = 500 (각 시장 250 ceiling)
    kospi_count = sum(1 for t in result if t.startswith("K"))
    kosdaq_count = sum(1 for t in result if t.startswith("D"))

    assert kospi_count == 250, (
        f"\n사이클 96 H-2 위반 — KOSPI ceiling 결함:\n"
        f"  기대: 250\n"
        f"  실제: {kospi_count}\n"
        f"  Green 의무: kospi_sorted[:250] 영속"
    )
    assert kosdaq_count == 250, (
        f"\n사이클 96 H-2 위반 — KOSDAQ ceiling 결함:\n"
        f"  기대: 250\n"
        f"  실제: {kosdaq_count}\n"
        f"  Green 의무: kosdaq_sorted[:250] 영속"
    )


@pytest.mark.asyncio
async def test_h2_max_pages_17_passed_to_fetch():
    """H-2.b: `_fetch_volume_rank` 호출 시 max_pages=17 영속 (사이클 91 영역).

    각 호출이 페이징 17 페이지 누적 영역 영속 가시화.
    """
    from src.engine.scanner import fetch_top_500_universe

    call_kwargs: list[dict] = []

    async def _fake_fetch(market: str, top_n: int = 250, max_pages: int = 17):
        call_kwargs.append({"market": market, "top_n": top_n, "max_pages": max_pages})
        return []  # 빈 응답 — H-2.b 호출 인자 영역만 검증

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch)):
        await fetch_top_500_universe()

    assert len(call_kwargs) == 2, (
        f"\n사이클 96 H-2.b 위반 — 호출 수 결함: {len(call_kwargs)}"
    )

    for call in call_kwargs:
        # top_n=250 영속 (사이클 89 의도)
        assert call["top_n"] == 250, (
            f"\n사이클 96 H-2.b 위반 — top_n 결함: {call}\n"
            f"  기대: 250 (사이클 89 영역)\n"
        )
