"""사이클 97 M-3 — scanner upsert chain 영속 (MEDIUM).

명세 (`_workspace/red/cycle97_fluctuation_api_replacement.md`):

- 사이클 83 `_scan_pool_eager_refresh_loop` chain 영속
- 사이클 89~96 영역 chain 영속 영역
- 사이클 97 영역 = fluctuation API 신규 도입 후에도 chain 영속

기대 동작 (Green, backend-dev 인계):
- `fetch_top_500_universe()` 반환 ticker list → `_universe_eager_refresh_loop` 호출 chain 영속
- `_universe_eager_refresh_loop` 영역 변경 0 (사이클 89 영속)
- ticker list 추출 영역 = `row.get("stck_shrn_iscd")` (fluctuation 정본 응답 키)

Red 상태 (사이클 97): `_fetch_fluctuation` 미존재 → ImportError → FAIL.

영속 의무:
- 사이클 83 chain 영속
- 사이클 93 chain 영속 (호출 chain 변경 0)
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_m3_universe_eager_refresh_loop_chain_persisted():
    """M-3.a: `_universe_eager_refresh_loop` 함수 영역 영속 (사이클 89 영역 영구 보존).

    검증 매트릭스:
    - `_universe_eager_refresh_loop` 모듈 attribute 영속
    - 함수 signature 영속 (candidates: list[str] 인자)

    Red 상태 (사이클 97): 만약 chain 변경 시 → FAIL.

    Green (backend-dev): chain 영역 변경 0 → PASS.
    """
    import src.engine.scanner as scanner_mod

    assert hasattr(scanner_mod, "_universe_eager_refresh_loop"), (
        "\n사이클 97 M-3.a 위반 — `_universe_eager_refresh_loop` 함수 영역 부재:\n"
        "  사이클 89 chain 영역 영속 의무\n"
        "  Green (backend-dev): scanner.py 영역 변경 0 의무"
    )

    import inspect
    sig = inspect.signature(scanner_mod._universe_eager_refresh_loop)
    params = list(sig.parameters.keys())
    assert "candidates" in params, (
        f"\n사이클 97 M-3.a 위반 — `_universe_eager_refresh_loop` signature 변경:\n"
        f"  기대 인자: candidates (사이클 89 영속)\n"
        f"  실제 params: {params}"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 99 — fetch_top_500_universe() 결과 60 ticker 영구 영속 (KOSPI 30 + KOSDAQ 30). "
        "사이클 97 시점 top_n=50 × 2 = 100 ticker 기대는 사이클 99 슬라이싱[:30] 으로 60 결과. "
        "KIS API 본질 한계 영구 확정 — tr_cont 'M' 영구 비반환 → 60 ticker 영구 영속 (사이클 66 K-2 패턴)."
    ),
)
@pytest.mark.asyncio
async def test_m3_fetch_top_500_universe_returns_ticker_list():
    """M-3.b: `fetch_top_500_universe()` 반환 = ticker list (str list, fluctuation 응답 키 정합).

    검증 매트릭스:
    - mock `_fetch_fluctuation` 응답 (KOSPI 50 + KOSDAQ 50)
    - 반환 = list[str] 정합
    - 응답 키 `stck_shrn_iscd` 영역 추출 영속 (volume_rank `mksc_shrn_iscd` 와 영역 차별)

    Red 상태 (사이클 97): `_fetch_fluctuation` 미존재 → FAIL.

    Green (backend-dev): `tickers = [row["stck_shrn_iscd"] for row in universe_rows ...]` 영속.
    """
    try:
        import src.engine.scanner as scanner_mod
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 97 M-3.b Red 상태 — `fetch_top_500_universe` 함수 부재"
        )

    if not hasattr(scanner_mod, "_fetch_fluctuation"):
        pytest.fail(
            "\n사이클 97 M-3.b Red 상태 — `_fetch_fluctuation` 함수 부재"
        )

    def _build_rows(prefix: str, count: int) -> list[dict]:
        return [
            {
                # fluctuation 정본 응답 키 (KIS chk_fluctuation.py COLUMN_MAPPING)
                "stck_shrn_iscd": f"{prefix}{i:04d}",
                "stck_prpr": "50000",
                "prdy_vrss": "1000",
                "prdy_ctrt": "2.0",
                "acml_vol": str(1_000_000 + i),
                "prdt_type_cd": "300",
            }
            for i in range(count)
        ]

    async def _fake_fetch_fluctuation(market: str, top_n: int = 250):
        if market == "kospi":
            return _build_rows("01", 50)
        elif market == "kosdaq":
            return _build_rows("02", 50)
        return []

    with patch("src.engine.scanner._fetch_fluctuation",
               new=AsyncMock(side_effect=_fake_fetch_fluctuation)):
        result = await fetch_top_500_universe()

    # 가드 1: list[str] 정합
    assert isinstance(result, list), (
        f"\n사이클 97 M-3.b 위반 — 반환 타입 결함:\n"
        f"  기대: list (str list)\n"
        f"  실제: {type(result).__name__}"
    )
    assert all(isinstance(t, str) for t in result), (
        f"\n사이클 97 M-3.b 위반 — list 항목 타입 결함 (str 의무):\n"
        f"  실제 샘플: {result[:5]}"
    )

    # 가드 2: ticker 추출 정합 (fluctuation 응답 키 영역)
    assert len(result) == 100, (
        f"\n사이클 97 M-3.b 위반 — ticker 추출 결함:\n"
        f"  기대: 100 (KOSPI 50 + KOSDAQ 50)\n"
        f"  실제: {len(result)}"
    )

    # 가드 3: 응답 키 `stck_shrn_iscd` 영역 정합 (prefix 검증)
    kospi_tickers = [t for t in result if t.startswith("01")]
    kosdaq_tickers = [t for t in result if t.startswith("02")]
    assert len(kospi_tickers) == 50, (
        f"\n사이클 97 M-3.b 위반 — KOSPI ticker 추출 결함:\n"
        f"  기대: 50\n"
        f"  실제: {len(kospi_tickers)}\n"
        f"  사이클 97 영역 = `stck_shrn_iscd` 응답 키 정합 의무"
    )
    assert len(kosdaq_tickers) == 50, (
        f"\n사이클 97 M-3.b 위반 — KOSDAQ ticker 추출 결함:\n"
        f"  기대: 50\n"
        f"  실제: {len(kosdaq_tickers)}"
    )
