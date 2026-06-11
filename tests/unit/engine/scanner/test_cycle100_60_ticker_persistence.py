"""사이클 100 G-PERSIST1 — 사이클 99 60 ticker 영구 영속 (LOW, 변경 0).

명세 (`_workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md`):

**사이클 100 = 영역 변경 0 영속 확인 가드**:
- 사이클 99 G-PERSIST1 영속 (`tests/unit/engine/scanner/test_cycle99_60_ticker_persistence.py`) 영속
- `fetch_top_500_universe()` 결과 = 60 ticker 영구 영속 (KIS API 본질 한계 영구 수용)
- 사이클 100 = scanner.py 영역 변경 0 → 영속 가드 PASS 의무

**Phase 1 진단 영속 영역 (사이클 100 Phase 1)**:
- 영역 1 (UI prefix 정정) + 영역 2 (주문 발주 시장 분기) = scanner.py 영역 영향 0
- 사이클 99 영속 = KIS API 본질 한계 영구 수용 (KOSPI 30 + KOSDAQ 30 = 60 ticker)

검증 매트릭스:
- mock `_fetch_fluctuation(market="kospi")` = 30 ticker 반환
- mock `_fetch_fluctuation(market="kosdaq")` = 30 ticker 반환
- `fetch_top_500_universe()` 결과 = 60 ticker 영구 영속

**Red 상태**: 사이클 99 영속 = production 변경 0 → PASS (영속 확인 가드).

**Green**: 사이클 99 영속 = PASS.

영속 의무:
- 사이클 99 G-PERSIST1 영속 (60 ticker 영구 영속 수용)
- 사이클 99 G-DOC1 영속 (KIS API 본질 한계 영구 명문화)
- 사이클 100 영역 변경 0 → 두 영역 모두 영속 가드 PASS 의무
- 매매 안전성 영역 영향 0 (영속 가드만)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A+Q69=B — `fetch_top_500_universe` + `_fetch_fluctuation` 영구 폐기 "
        "(fluctuation API → market_cap FHPST01740000 + `_full_universe_load_once` 전환). "
        "사이클 100 시점 60 ticker 영구 영속 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
@pytest.mark.asyncio
async def test_g_persist1_fetch_top_500_universe_returns_60_ticker_persistence():
    """G-PERSIST1: `fetch_top_500_universe()` 결과 = 60 ticker 영구 영속 (LOW, 변경 0).

    검증 매트릭스 (사이클 99 + 사이클 100 영역 영구 영속):
    - mock `_fetch_fluctuation(market="kospi")` = 30 ticker 반환 (KIS API 단일 페이지 한도)
    - mock `_fetch_fluctuation(market="kosdaq")` = 30 ticker 반환 (KIS API 단일 페이지 한도)
    - `fetch_top_500_universe()` 결과 = 60 ticker 영구 영속 (KOSPI 30 + KOSDAQ 30)

    Red 상태 (사이클 100): 사이클 99 영속 = production 변경 0 → PASS (영속 확인 가드).

    Green: 사이클 99 영속 = PASS.

    영속 의무:
    - 사이클 99 G-PERSIST1 (60 ticker 영구 영속 수용)
    - 사이클 95 unknown 합집합 영역 영속
    - 사이클 93 chain 영속
    - 사이클 100 영역 변경 0 → 영속 가드 PASS 의무
    """
    try:
        import src.engine.scanner as scanner_mod
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 100 G-PERSIST1 Red 상태 — `fetch_top_500_universe` 함수 부재.\n"
            "  영속 의무: 사이클 99 G-PERSIST1 영속.\n"
            "  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
        )

    if not hasattr(scanner_mod, "_fetch_fluctuation"):
        pytest.fail(
            "\n사이클 100 G-PERSIST1 Red 상태 — `_fetch_fluctuation` 함수 부재.\n"
            "  영속 의무: 사이클 97 영역 = `_fetch_fluctuation` 신규 함수 영속.\n"
            "  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
        )

    # KIS API 단일 페이지 30 한도 영구 영속 (사이클 99)
    KIS_SINGLE_PAGE_LIMIT = 30

    def _build_kis_response_30_ticker(market_prefix: str) -> list[dict]:
        """KIS fluctuation API 단일 페이지 30 ticker 응답 영역 (사이클 99 영속)."""
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
        # 사이클 99 영속 — top_n=30 영구 영속 (KIS API 본질 한계)
        if market == "kospi":
            return _build_kis_response_30_ticker("0")
        elif market == "kosdaq":
            return _build_kis_response_30_ticker("1")
        return []

    with patch(
        "src.engine.scanner._fetch_fluctuation",
        new=AsyncMock(side_effect=_fake_fetch_fluctuation),
    ):
        result = await fetch_top_500_universe()

    # 가드: 결과 = 60 ticker 영구 영속 (사이클 99 + 사이클 100 영속)
    assert len(result) == 60, (
        f"\n사이클 100 G-PERSIST1 위반 — 60 ticker 영구 영속 위반:\n"
        f"  기대: 60 ticker (KOSPI 30 + KOSDAQ 30, KIS API 본질 한계 영구 수용)\n"
        f"  실제: {len(result)} ticker\n"
        f"  사이클 99 영속 매트릭스:\n"
        f"    - KIS API 단일 페이지 30 한도 + tr_cont 'M' 영구 비반환\n"
        f"    - 사이클 95 unknown 합집합 영역 영속\n"
        f"    - 사이클 93 chain 영속\n"
        f"  사이클 100 = scanner.py 영역 변경 0 영속 의무 — 사이클 99 영속 silent 삭제 영구 차단\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )
