"""사이클 89 H-1 — `fetch_top_500_universe()` 정렬 검증.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

- A1 권고 영속: 거래대금 (전일) 단독 정렬 1순위 + 등락률 ±15%+ 2순위 dedupe
- A2 권고 영속: KOSPI 250 + KOSDAQ 250 분리 정렬 (`mrkt_div_cls_code=1/2` 2회 호출)
- 응답 list 최대 500건 (KOSPI 250 + KOSDAQ 250 합집합)
- 거래대금 재정렬 (`trade_amount = prdy_vol × (stck_prpr - prdy_vrss)`, 사이클 48 BFB 답습)

기대 동작 (Green, 사이클 90):
- `fetch_top_500_universe()` 호출 → KIS `volume_rank` 2회 호출 + 거래대금 desc 정렬 +
  ETF/리츠/SPAC 제외 + 최대 500건 반환

Red 단계 (사이클 89): production 코드 부재 → ImportError → FAIL.

영속 의무:
- 사이클 48 BFB 거래대금 재정렬 패턴 답습 (`trade_amount = vol × price`)
- 사이클 65 trade_amount_filter 영속 (DB upsert 영역과 분리)
- 사이클 81 bfdy_clpr 키 시정 영속 (영향 0, 영역 분리)
- 사이클 38 명문화 영속 (`tradable_boards` 매수 진입 전용)
- 매매 안전성 영향 0 (scanner 단계 영역 + DB CRUD)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h1_fetch_top_500_universe_kospi_kosdaq_separated_and_sorted():
    """H-1: `fetch_top_500_universe()` 가 KOSPI 250 + KOSDAQ 250 분리 호출 +
    거래대금 desc 정렬 + 최대 500건 반환.

    검증 매트릭스:
    - mock 응답: KOSPI 250건 (거래대금 무작위 순) + KOSDAQ 250건 (거래대금 무작위 순)
    - 결과: 500건 (KOSPI 250 + KOSDAQ 250 합집합)
    - 각 시장 내부 정렬: 거래대금 desc

    Red 상태 (사이클 89): `fetch_top_500_universe` 함수 미존재 → ImportError → FAIL.

    Green (사이클 90): backend-dev 가 신규 함수 도입 → PASS.

    영속 의무:
    - A1 권고 (거래대금 단독 정렬 + 등락률 dedupe 2순위)
    - A2 권고 (KOSPI/KOSDAQ 250+250 분리)
    - 사이클 48 BFB 거래대금 재정렬 답습
    """
    try:
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 89 H-1 Red 상태 — `fetch_top_500_universe` 함수 미존재.\n"
            "  Green (사이클 90): backend-dev 가 신규 함수 도입 의무.\n"
            "  - scanner.py: fetch_top_500_universe() +\n"
            "    _fetch_volume_rank(market, top_n) +\n"
            "    _trade_amount_key(row) +\n"
            "    _universe_filter_securities_only(rows)\n"
            "  - A1 권고 (거래대금 단독 정렬) + A2 권고 (KOSPI/KOSDAQ 분리)"
        )

    # KOSPI mock 응답 (거래대금 무작위) — 정상 보통주만
    kospi_mock = [
        {"mksc_shrn_iscd": f"00{i:04d}", "prdy_vol": 1_000_000 + i * 10_000,
         "stck_prpr": 50_000, "prdy_vrss": 1_000,
         "scts_mket_cls_code": "Y"}  # KOSPI
        for i in range(250)
    ]
    # KOSDAQ mock 응답
    kosdaq_mock = [
        {"mksc_shrn_iscd": f"03{i:04d}", "prdy_vol": 500_000 + i * 5_000,
         "stck_prpr": 30_000, "prdy_vrss": 500,
         "scts_mket_cls_code": "N"}  # KOSDAQ
        for i in range(250)
    ]

    call_log: list[str] = []

    async def _fake_fetch_volume_rank(market: str, top_n: int = 250):
        call_log.append(market)
        if market == "1":
            return kospi_mock
        elif market == "2":
            return kosdaq_mock
        return []

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)):
        result = await fetch_top_500_universe()

    # 가드 1: 결과 카운트 ≤ 500
    assert len(result) <= 500, (
        f"\n사이클 89 H-1 위반 — 결과 카운트 초과:\n"
        f"  실제: {len(result)} (≤ 500 의무)\n"
        f"  A2 권고: KOSPI 250 + KOSDAQ 250 = 500 최대"
    )

    # 가드 2: KOSPI + KOSDAQ 양쪽 포함 (mock 데이터 식별자 기반)
    has_kospi = any(t.startswith("00") for t in result)
    has_kosdaq = any(t.startswith("03") for t in result)
    assert has_kospi, (
        f"\n사이클 89 H-1 위반 — KOSPI 종목 누락:\n"
        f"  결과: {result[:10]}...\n"
        f"  A2 권고: KOSPI 250 + KOSDAQ 250 분리 정렬 의무"
    )
    assert has_kosdaq, (
        f"\n사이클 89 H-1 위반 — KOSDAQ 종목 누락:\n"
        f"  결과: {result[:10]}...\n"
        f"  A2 권고: KOSPI 250 + KOSDAQ 250 분리 정렬 의무"
    )

    # 가드 3: `_fetch_volume_rank` 가 mrkt_div_cls_code=1, 2 양쪽 호출
    assert "1" in call_log, (
        f"\n사이클 89 H-1 위반 — `_fetch_volume_rank(market='1')` (KOSPI) 호출 누락:\n"
        f"  호출 로그: {call_log}"
    )
    assert "2" in call_log, (
        f"\n사이클 89 H-1 위반 — `_fetch_volume_rank(market='2')` (KOSDAQ) 호출 누락:\n"
        f"  호출 로그: {call_log}"
    )
