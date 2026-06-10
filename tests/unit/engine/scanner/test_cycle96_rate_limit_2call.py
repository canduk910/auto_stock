"""사이클 96 M-2 — KIS 호출 영역 = 2회 분리 호출 + 페이징 영역 (MEDIUM).

명세 (`_workspace/red/cycle96_resurrect_industry_code_with_pagination.md`):

- KIS 호출 총량 = 2회 분리 호출 (KOSPI + KOSDAQ) × 각 ~17 페이지 = ~34 호출
- 사이클 91 50ms sleep 영속 (Rate Limit 보호)
- 사이클 89 영역 복원 = 호출 수 증가 (사이클 94 1회 → 사이클 96 ~34회) 영역 영속

기대 동작 (Green, backend-dev 인계):
- `fetch_top_500_universe()` 호출 시 `_fetch_volume_rank` 2회 호출
- 각 호출이 페이징 누적 (max_pages=17 영속)

Red 상태 (사이클 96): 사이클 94 단일 호출 영속 → 1회 → FAIL.

영속 의무:
- 사이클 91 페이징 영역 영속
- 사이클 83 Rate Limit 50ms sleep 답습
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_m2_kis_call_count_two_calls():
    """M-2.a: `_fetch_volume_rank` 정확 2회 호출 (KOSPI + KOSDAQ).

    검증 매트릭스:
    - mock 빈 응답 (호출 영역만 검증)
    - 호출 카운트 = 2

    영속 의무: 사이클 89 영역 복원 의도 영속.
    """
    from src.engine.scanner import fetch_top_500_universe

    call_count = [0]

    async def _fake_fetch(market: str, top_n: int = 250, max_pages: int = 17):
        call_count[0] += 1
        return []

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch)):
        await fetch_top_500_universe()

    assert call_count[0] == 2, (
        f"\n사이클 96 M-2.a 위반 — `_fetch_volume_rank` 호출 수 결함:\n"
        f"  기대: 2회 (KOSPI + KOSDAQ 분리)\n"
        f"  실제: {call_count[0]}회\n"
        f"  사이클 89 영역 복원 의무"
    )


@pytest.mark.asyncio
async def test_m2_max_pages_17_passed_each_call():
    """M-2.b: 각 호출 max_pages=17 영속 (사이클 91 영역).

    검증 매트릭스:
    - 호출 인자 max_pages = 17 (각 호출)

    영속 의무: 사이클 91 페이징 영역 영속 + 각 호출 ~17 페이지 누적.
    """
    from src.engine.scanner import fetch_top_500_universe

    call_kwargs: list[dict] = []

    async def _fake_fetch(market: str, top_n: int = 250, max_pages: int = 17):
        call_kwargs.append({"market": market, "top_n": top_n, "max_pages": max_pages})
        return []

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch)):
        await fetch_top_500_universe()

    assert len(call_kwargs) == 2, (
        f"\n사이클 96 M-2.b 위반 — 호출 수 결함: {len(call_kwargs)}"
    )

    # max_pages 영역 영속 (사이클 91 답습)
    for call in call_kwargs:
        # 호출 시 max_pages 가 명시되지 않더라도 default=17 영속 영역
        # 호출 측 명시 영역 vs default 영속 영역 양쪽 호환
        assert call.get("max_pages", 17) == 17, (
            f"\n사이클 96 M-2.b 위반 — max_pages 영역 결함:\n"
            f"  call: {call}\n"
            f"  사이클 91 페이징 영역 영속 의무 (각 17 페이지)"
        )
