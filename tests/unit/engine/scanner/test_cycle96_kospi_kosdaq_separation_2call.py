"""사이클 96 H-4 — 2회 분리 호출 영속 (사이클 89 정본 정합) (HIGH).

명세 (`_workspace/red/cycle96_resurrect_industry_code_with_pagination.md`):

- 사이클 89 영역 복원 = KOSPI + KOSDAQ 2회 분리 호출 영역 영속
- 호출 인자 영역 = `market="kospi"` + `market="kosdaq"` 양쪽 포함
- 사이클 89 시점 `market="1"/"2"` 명명에서 의미 명확 영역으로 갱신

기대 동작 (Green, backend-dev 인계):
- `fetch_top_500_universe()` 호출 → `_fetch_volume_rank` 호출 2회
- 호출 인자 markets = {"kospi", "kosdaq"}

Red 상태 (사이클 96): production 사이클 94 단일 호출 (`market="all"`) 영속 → FAIL.

영속 의무:
- 사이클 89 A2 권고 (KOSPI/KOSDAQ 250+250 분리 의무)
- KOSPI 거래대금 vs KOSDAQ 거래대금 격차 영속 보존 (10배 차이 영역)
- 코스닥 변동성 영역 보존 (momentum 상한가/VCP 수렴/BFB 깃발 전략)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h4_two_call_kospi_kosdaq_separated():
    """H-4: `fetch_top_500_universe()` 가 `_fetch_volume_rank` 2회 호출 (KOSPI + KOSDAQ).

    검증 매트릭스:
    - `_fetch_volume_rank` mock 호출 수집
    - 호출 횟수 = 정확 2회
    - 호출 인자 `market` = {"kospi", "kosdaq"} 양쪽 포함

    Red 상태 (사이클 96): 사이클 94 단일 호출 영속 → 1회 → FAIL.

    Green (backend-dev): 영역 복원 → 2회 호출 → PASS.

    영속 의무:
    - 사이클 89 A2 권고 영역 복원
    - 코스닥 변동성 영역 보존 (6 전략 균형)
    """
    from src.engine.scanner import fetch_top_500_universe

    call_markets: list[str] = []

    async def _fake_fetch_volume_rank(market: str, top_n: int = 250, max_pages: int = 17):
        call_markets.append(market)
        return []

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)):
        await fetch_top_500_universe()

    # 가드 1: 호출 횟수 정확 2회
    assert len(call_markets) == 2, (
        f"\n사이클 96 H-4 위반 — `_fetch_volume_rank` 호출 횟수 결함:\n"
        f"  기대: 2회 (KOSPI + KOSDAQ)\n"
        f"  실제: {len(call_markets)}회\n"
        f"  호출 인자: {call_markets}\n"
        f"  사이클 89 A2 권고 영역 복원 의무"
    )

    # 가드 2: market="kospi" 호출 포함
    assert "kospi" in call_markets, (
        f"\n사이클 96 H-4 위반 — KOSPI (`market='kospi'`) 호출 누락:\n"
        f"  호출 인자: {call_markets}\n"
        f"  사이클 89 영역 복원 (`market='1'` → `market='kospi'` 명명 갱신)"
    )

    # 가드 3: market="kosdaq" 호출 포함
    assert "kosdaq" in call_markets, (
        f"\n사이클 96 H-4 위반 — KOSDAQ (`market='kosdaq'`) 호출 누락:\n"
        f"  호출 인자: {call_markets}\n"
        f"  사이클 89 영역 복원 (`market='2'` → `market='kosdaq'` 명명 갱신)"
    )


@pytest.mark.asyncio
async def test_h4_market_argument_names_kospi_kosdaq():
    """H-4.b: 호출 인자 = {"kospi", "kosdaq"} (사이클 96 명명 갱신).

    사이클 89 `"1"`/`"2"` 영역에서 의미 명확 `"kospi"`/`"kosdaq"` 영역으로 갱신.

    영속 의무: 영역 복원 시 사용자 가독성 영속.
    """
    from src.engine.scanner import fetch_top_500_universe

    call_markets: list[str] = []

    async def _fake_fetch_volume_rank(market: str, top_n: int = 250, max_pages: int = 17):
        call_markets.append(market)
        return []

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)):
        await fetch_top_500_universe()

    assert set(call_markets) == {"kospi", "kosdaq"}, (
        f"\n사이클 96 H-4.b 위반 — market 인자 명명 결함:\n"
        f"  기대: {{'kospi', 'kosdaq'}} (사이클 96 가독성 영역)\n"
        f"  실제: {set(call_markets)}\n"
        f"  사이클 89 영역 복원 + 명명 갱신"
    )
