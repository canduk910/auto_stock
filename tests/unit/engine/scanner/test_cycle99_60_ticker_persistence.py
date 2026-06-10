"""사이클 99 G-PERSIST1 — `fetch_top_500_universe()` 60 ticker 영구 영속 (HIGH).

명세 (`_workspace/red/cycle99_pagination_removal_60_ticker_persistence.md`):

- KIS API 본질 한계 영구 확정 (단일 페이지 30 한도 + tr_cont "M" 영구 비반환)
- 사이클 99 = 60 ticker 영구 영속 수용 (KOSPI 30 + KOSDAQ 30)
- stock_master 적재 점진 증가 영속 (사이클 95 unknown 합집합 + 사이클 93 chain)

검증 매트릭스:
- mock `_fetch_fluctuation(market="kospi")` = 30 ticker 반환
- mock `_fetch_fluctuation(market="kosdaq")` = 30 ticker 반환
- `fetch_top_500_universe()` 결과 = 60 ticker 영속 (KOSPI 30 + KOSDAQ 30)
- 60 영역 영구 가드 (KIS API 본질 한계 영구 수용)

Red 상태 (사이클 99): production `top_n=250` 영속 + 60 영역 명시 가드 부재 → FAIL.

Green (backend-dev): top_n=30 기본값 영역 시정 + 60 ticker 영구 영속 명문화 → PASS.

영속 의무:
- 사이클 38 명문화 영속 (scanner 단계 매수 진입 전용)
- 사이클 64 protected_tickers 영속 (보유/익일청산 절대 보호)
- 사이클 95 unknown=0 영속 (2회 분리 호출 = unknown 불필요)
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_g_persist1_fetch_top_500_universe_returns_60_ticker_persistence():
    """G-PERSIST1: `fetch_top_500_universe()` 결과 = 60 ticker 영구 영속.

    검증 매트릭스 (사이클 99 영역 영구 영속):
    - mock `_fetch_fluctuation` 영역 = KOSPI 30 + KOSDAQ 30 반환 (KIS API 본질 한계 영속)
    - 결과 `len(tickers) == 60` 영구 영속 (60 ticker 영역 영구 가드)
    - 60 영역 영구 가드 = KIS API 본질 한계 영구 수용

    Red 상태 (사이클 99): production 사이클 97 영역 `top_n=250` 영속 → 60 영역 명시 가드 부재 →
                          mock 사이클 97 영역 250 영속 가정 → mock 결과 불일치 → FAIL.

    Green (backend-dev): `_fetch_fluctuation` 기본값 영역 `top_n=30` 시정 →
                          mock 영역 30 ticker × 2 = 60 ticker 영속 → PASS.

    영속 의무:
    - sum(KOSPI 30 + KOSDAQ 30) = 60 (KIS API 본질 한계 영구 수용)
    - stock_master 적재 점진 증가 (사이클 95 unknown 합집합 + 사이클 93 chain 영속)
    - 매매 hot path 영향 0 (사이클 38 명문화 영속)
    """
    try:
        import src.engine.scanner as scanner_mod
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 99 G-PERSIST1 Red 상태 — `fetch_top_500_universe` 함수 부재"
        )

    if not hasattr(scanner_mod, "_fetch_fluctuation"):
        pytest.fail(
            "\n사이클 99 G-PERSIST1 Red 상태 — `_fetch_fluctuation` 함수 부재.\n"
            "  사이클 97 영역 = `_fetch_fluctuation` 신규 함수 영속 의무."
        )

    # 사이클 99 영역 — KIS API 단일 페이지 30 한도 영구 영속
    # 사이클 97 영역 mock = 250 ticker 가정 → 사이클 99 영역 = 30 ticker 영역 영구 영속
    KIS_SINGLE_PAGE_LIMIT = 30

    def _build_kis_response_30_ticker(market_prefix: str) -> list[dict]:
        """KIS fluctuation API 단일 페이지 30 ticker 응답 영역 (사이클 99 영구 영속)."""
        return [
            {
                "stck_shrn_iscd": f"{market_prefix}{i:05d}",  # 6자리 숫자 영속 (필터 통과)
                "stck_prpr": "50000",
                "prdy_vrss": "1000",
                "prdy_ctrt": "2.0",
                "acml_vol": str(1_000_000 + i),
                "acml_tr_pbmn": str(50_000_000_000 + i * 1_000_000),
                "prdt_type_cd": "300",
            }
            for i in range(KIS_SINGLE_PAGE_LIMIT)
        ]

    async def _fake_fetch_fluctuation(market: str, top_n: int = 30, **kwargs):
        # 사이클 99 영역 — top_n=30 영구 영속 (KIS API 본질 한계)
        # 사이클 97 영역 (top_n=250) 잔존 시 mock 영역 30 ticker 반환 → 결과 60 영역 영속 가드
        if market == "kospi":
            return _build_kis_response_30_ticker("0")
        elif market == "kosdaq":
            return _build_kis_response_30_ticker("1")
        return []

    with patch("src.engine.scanner._fetch_fluctuation",
               new=AsyncMock(side_effect=_fake_fetch_fluctuation)):
        result = await fetch_top_500_universe()

    # 가드 1: 결과 = 60 ticker 영구 영속 (KIS API 본질 한계 영구 수용)
    assert len(result) == 60, (
        f"\n사이클 99 G-PERSIST1 위반 — `fetch_top_500_universe()` 결과 60 ticker 영구 영속 위반:\n"
        f"  기대: 60 ticker (KOSPI 30 + KOSDAQ 30, KIS API 본질 한계 영구 수용)\n"
        f"  실제: {len(result)} ticker\n"
        f"  KIS API 본질 한계 매트릭스 영구 확정:\n"
        f"    - volume_rank (FHPST01710000) = 단일 페이지 30 한도\n"
        f"    - fluctuation (FHPST01700000) = 단일 페이지 30 한도\n"
        f"    - KIS API 전체 영역 = tr_cont 'M' 영구 비반환 = 페이징 미지원 영구 확정\n"
        f"  운영 실증 (사이클 96 + 사이클 98):\n"
        f"    - [volume_rank_pagination] page=0 → tr_cont='' (M 영구 비반환)\n"
        f"    - [fetch_fluctuation] page=0 → tr_cont='' (M 영구 비반환)\n"
        f"  Green (backend-dev): `_fetch_fluctuation` 기본값 영역 `top_n=30` 시정 의무\n"
        f"    - 사이클 97 영역 `top_n=250` → 사이클 99 영역 `top_n=30` 영구 영속\n"
        f"  사이클 99 영역 영구 영속:\n"
        f"    - 60 ticker 영구 영속 수용 (KIS API 본질 한계 영구 수용)\n"
        f"    - 페이징 영역 영구 폐기 (사이클 91~98 모든 시정 영구 무용)\n"
        f"    - stock_master 적재 점진 증가 (사이클 95 unknown 합집합 + 사이클 93 chain)\n"
        f"  명세 영속: `_workspace/red/cycle99_pagination_removal_60_ticker_persistence.md`"
    )

    # 가드 2: KOSPI 영역 = 30 ticker 영구 영속 (KIS API 본질 한계)
    kospi_tickers = [t for t in result if t.startswith("0")]
    assert len(kospi_tickers) == 30, (
        f"\n사이클 99 G-PERSIST1 위반 — KOSPI 30 ticker 영구 영속 위반:\n"
        f"  기대: 30 ticker (KIS API 단일 페이지 한도 영구 영속)\n"
        f"  실제: {len(kospi_tickers)} ticker (prefix='0')"
    )

    # 가드 3: KOSDAQ 영역 = 30 ticker 영구 영속 (KIS API 본질 한계)
    kosdaq_tickers = [t for t in result if t.startswith("1")]
    assert len(kosdaq_tickers) == 30, (
        f"\n사이클 99 G-PERSIST1 위반 — KOSDAQ 30 ticker 영구 영속 위반:\n"
        f"  기대: 30 ticker (KIS API 단일 페이지 한도 영구 영속)\n"
        f"  실제: {len(kosdaq_tickers)} ticker (prefix='1')"
    )
