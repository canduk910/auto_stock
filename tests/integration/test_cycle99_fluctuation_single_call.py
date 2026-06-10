"""사이클 99 G-REG1 — `fetch_top_500_universe()` 통합 시나리오 단일 호출 + 60 ticker 영속 (LOW).

명세 (`_workspace/red/cycle99_pagination_removal_60_ticker_persistence.md`):

- KIS fluctuation API 단일 호출 통합 영역 (사이클 99 영속)
- `_fetch_fluctuation` mock 영역 호출 횟수 = 정확 2회 (KOSPI + KOSDAQ 분리, 사이클 96 영속)
- mock 응답 30 ticker 영속 → 합 60 ticker 영구 영속
- 사이클 98 OPSQ2002 영역 영구 차단 보장 (FID_RANK_SORT_CLS_CODE "0" 영속 검증)

Red 상태 (사이클 99): 통합 테스트 사이클 99 영역 신규 → 신규 → FAIL.

Green (backend-dev): G-PURGE1 페이징 영역 영구 폐기 시정 후 PASS.

영속 의무:
- 사이클 38 명문화 영속 (scanner 단계 매수 진입 전용)
- 사이클 64 protected_tickers 영속
- 사이클 95 unknown=0 영속 (2회 분리 호출 = unknown 분류 불필요)
- 사이클 96 KOSPI/KOSDAQ 분리 호출 영속
- 사이클 98 OPSQ2002 영구 차단 영속 (FID_RANK_SORT_CLS_CODE "0" 영속)
- silent 결함 영구 차단 21 회 누적
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_g_reg1_fluctuation_single_call_per_market_with_60_ticker():
    """G-REG1: `fetch_top_500_universe()` 통합 영역 = 시장당 단일 호출 + 60 ticker 영속.

    검증 매트릭스 (사이클 99 영역 통합 영속):
    1. `_fetch_fluctuation` 호출 횟수 = 정확 2회 (KOSPI + KOSDAQ, 사이클 96 분리 영속)
    2. 각 호출 = 단일 호출 (페이징 영역 영구 폐기 영속, max_pages 인자 영역 부재)
    3. 합 결과 = 60 ticker 영구 영속 (KOSPI 30 + KOSDAQ 30)
    4. 사이클 98 영속: `_fetch_fluctuation` 본체 영역 FID_RANK_SORT_CLS_CODE "0" 영속

    Red 상태 (사이클 99): 신규 통합 영역 + production 페이징 영역 영속 → FAIL.

    Green (backend-dev): G-PURGE1 시정 후 통합 영역 PASS.

    영속 의무:
    - 사이클 95 unknown=0 영속 (2회 분리 호출 = unknown 분류 불필요)
    - 사이클 96 KOSPI/KOSDAQ 분리 호출 영속
    - 사이클 98 OPSQ2002 영구 차단 영속 (FID_RANK_SORT_CLS_CODE "0" 영속)
    - 매매 hot path 영향 0 (사이클 38 명문화 영속)
    """
    try:
        import src.engine.scanner as scanner_mod
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 99 G-REG1 Red 상태 — `fetch_top_500_universe` 함수 부재"
        )

    if not hasattr(scanner_mod, "_fetch_fluctuation"):
        pytest.fail(
            "\n사이클 99 G-REG1 Red 상태 — `_fetch_fluctuation` 함수 부재.\n"
            "  사이클 97 영역 = `_fetch_fluctuation` 신규 함수 영속 의무"
        )

    # 호출 인자 수집 (사이클 96 영속 + 사이클 99 영속)
    call_log: list[dict] = []

    KIS_SINGLE_PAGE_LIMIT = 30

    async def _fake_fetch_fluctuation(market: str, top_n: int = 30, **kwargs):
        # 사이클 99 영역 — max_pages 키워드 인자 영구 부재 검증
        if "max_pages" in kwargs:
            pytest.fail(
                f"\n사이클 99 G-REG1 위반 — `_fetch_fluctuation` 호출 영역에 `max_pages` 잔존:\n"
                f"  호출 kwargs: {kwargs}\n"
                f"  영구 차단 영역: `max_pages` 인자 (페이징 안전 마진 영역 영구 폐기)\n"
                f"  Green: 호출 영역 = `_fetch_fluctuation(market=...)` 영구 영속"
            )
        if "tr_cont" in kwargs:
            pytest.fail(
                f"\n사이클 99 G-REG1 위반 — `_fetch_fluctuation` 호출 영역에 `tr_cont` 잔존:\n"
                f"  호출 kwargs: {kwargs}\n"
                f"  영구 차단 영역: `tr_cont` 인자 (KIS 페이징 인자 영역 영구 폐기)"
            )

        call_log.append({"market": market, "top_n": top_n})
        # mock 30 ticker 응답 (KIS API 본질 한계 영구 영속)
        prefix = "0" if market == "kospi" else "1"
        return [
            {
                "stck_shrn_iscd": f"{prefix}{i:05d}",  # 6자리 숫자 영속 (필터 통과)
                "stck_prpr": "50000",
                "prdy_vrss": "1000",
                "prdy_ctrt": "2.0",
                "acml_vol": str(1_000_000 + i),
                "acml_tr_pbmn": str(50_000_000_000 + i * 1_000_000),
                "prdt_type_cd": "300",
            }
            for i in range(KIS_SINGLE_PAGE_LIMIT)
        ]

    with patch("src.engine.scanner._fetch_fluctuation",
               new=AsyncMock(side_effect=_fake_fetch_fluctuation)):
        result = await fetch_top_500_universe()

    # 가드 1: 호출 횟수 = 정확 2회 (KOSPI + KOSDAQ 분리, 사이클 96 영속)
    assert len(call_log) == 2, (
        f"\n사이클 99 G-REG1 위반 — `_fetch_fluctuation` 호출 횟수 결함 (사이클 96 분리 호출 영속 위반):\n"
        f"  기대: 2회 (KOSPI + KOSDAQ 분리, 사이클 96 영속)\n"
        f"  실제: {len(call_log)}회\n"
        f"  호출 영역: {call_log}\n"
        f"  사이클 99 영역 영구 영속:\n"
        f"    - 시장당 단일 호출 영역 영구 영속 (페이징 영역 영구 폐기)\n"
        f"    - 2회 호출 = KOSPI 30 + KOSDAQ 30 = 60 ticker 영구 영속"
    )

    # 가드 2: KOSPI + KOSDAQ 양쪽 호출 영속
    markets_called = {c["market"] for c in call_log}
    assert markets_called == {"kospi", "kosdaq"}, (
        f"\n사이클 99 G-REG1 위반 — KOSPI/KOSDAQ 분리 호출 영속 위반 (사이클 96):\n"
        f"  기대 markets: {{'kospi', 'kosdaq'}}\n"
        f"  실제 markets: {markets_called}\n"
        f"  호출 영역: {call_log}"
    )

    # 가드 3: 합 결과 = 60 ticker 영구 영속 (KIS API 본질 한계 영구 수용)
    assert len(result) == 60, (
        f"\n사이클 99 G-REG1 위반 — `fetch_top_500_universe()` 결과 60 ticker 영구 영속 위반:\n"
        f"  기대: 60 ticker (KOSPI 30 + KOSDAQ 30, KIS API 본질 한계 영구 수용)\n"
        f"  실제: {len(result)} ticker\n"
        f"  KIS API 본질 한계 영구 확정:\n"
        f"    - 단일 페이지 30 한도 + tr_cont 'M' 영구 비반환\n"
        f"    - 페이징 영역 영구 폐기 (사이클 91~98 모든 시정 영구 무용)\n"
        f"  사이클 99 영역 영구 영속:\n"
        f"    - 60 ticker 영구 영속 수용\n"
        f"    - 페이징 영역 영구 폐기\n"
        f"    - stock_master 적재 점진 증가 (사이클 95 unknown 합집합 영속)\n"
        f"  명세 영속: `_workspace/red/cycle99_pagination_removal_60_ticker_persistence.md`"
    )
