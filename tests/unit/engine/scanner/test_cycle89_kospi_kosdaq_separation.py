"""사이클 89 H-3 — `mrkt_div_cls_code=1/2` 2회 호출 분리 검증.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

- A2 권고 영속: KOSPI 250 + KOSDAQ 250 분리 정렬
- KIS `volume_rank` (FHPST01710000) `mrkt_div_cls_code` 인자:
  - `0` = 전체 (비추 — KOSPI 편중 = 코스닥 변동성 보존 어려움)
  - `1` = KOSPI (250 건)
  - `2` = KOSDAQ (250 건)
- 2회 호출 의무 (각 250건)

기대 동작 (Green, 사이클 90):
- `fetch_top_500_universe()` 호출 → `_fetch_volume_rank(market="1")` 1회 +
  `_fetch_volume_rank(market="2")` 1회 호출 (총 2회)

Red 단계 (사이클 89): 신규 함수 미존재 → ImportError → FAIL.

영속 의무:
- A2 권고 (KOSPI/KOSDAQ 250+250 분리 의무)
- KOSPI 거래대금 상위 ~5,000억+ vs KOSDAQ 상위 ~500억+ = 10배 차이 (통합 시 코스닥 누락)
- 코스닥 변동성 영역 보존 (momentum 상한가/VCP 수렴/BFB 깃발 전략)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 94 Q37=C — `_fetch_volume_rank` 단일 호출 (`market='all'`, `FID_INPUT_ISCD='0000'`) "
        "로 변경됨. 사이클 89 시점 2회 호출 (`market='1'/'2'`) + 호출 횟수=2 + market 인자 {'1','2'} 계약 폐기. "
        "사이클 66 K-2 의미 전환 패턴."
    ),
)
@pytest.mark.asyncio
async def test_h3_kospi_kosdaq_separated_2_calls():
    """H-3: `fetch_top_500_universe()` 가 `_fetch_volume_rank` 2회 호출 (KOSPI + KOSDAQ).

    검증 매트릭스:
    - `_fetch_volume_rank` mock 호출 수집
    - 호출 횟수 = 정확 2회
    - 호출 인자 `market` = {"1", "2"} 양쪽 포함

    Red 상태 (사이클 89): `fetch_top_500_universe` 미존재 → ImportError → FAIL.

    Green (사이클 90): backend-dev 가 신규 함수 도입 + 2회 호출 → PASS.

    영속 의무:
    - A2 권고 (KOSPI/KOSDAQ 250+250 분리)
    - 코스닥 변동성 영역 보존 (6 전략 균형)
    """
    try:
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 89 H-3 Red 상태 — `fetch_top_500_universe` 함수 미존재.\n"
            "  Green (사이클 90): backend-dev 가 신규 함수 + 2회 호출 도입 의무.\n"
            "  - scanner.py: fetch_top_500_universe() 본체에\n"
            "    `await _fetch_volume_rank(market='1')` (KOSPI) +\n"
            "    `await _fetch_volume_rank(market='2')` (KOSDAQ) 양쪽 호출"
        )

    call_markets: list[str] = []

    async def _fake_fetch_volume_rank(market: str, top_n: int = 250):
        call_markets.append(market)
        # 빈 응답 (정렬/필터 영역은 H-1/H-2 가드)
        return []

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)):
        await fetch_top_500_universe()

    # 가드 1: 호출 횟수 정확 2회
    assert len(call_markets) == 2, (
        f"\n사이클 89 H-3 위반 — `_fetch_volume_rank` 호출 횟수 결함:\n"
        f"  기대: 2회 (KOSPI + KOSDAQ)\n"
        f"  실제: {len(call_markets)}회\n"
        f"  호출 인자: {call_markets}\n"
        f"  A2 권고: mrkt_div_cls_code=1 (KOSPI) + 2 (KOSDAQ) 분리 호출"
    )

    # 가드 2: market=1 (KOSPI) 호출 포함
    assert "1" in call_markets, (
        f"\n사이클 89 H-3 위반 — KOSPI (`market='1'`) 호출 누락:\n"
        f"  호출 인자: {call_markets}\n"
        f"  A2 권고: KOSPI 250 정렬 의무"
    )

    # 가드 3: market=2 (KOSDAQ) 호출 포함
    assert "2" in call_markets, (
        f"\n사이클 89 H-3 위반 — KOSDAQ (`market='2'`) 호출 누락:\n"
        f"  호출 인자: {call_markets}\n"
        f"  A2 권고: KOSDAQ 250 정렬 의무"
    )
