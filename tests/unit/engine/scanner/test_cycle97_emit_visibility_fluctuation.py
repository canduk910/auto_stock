"""사이클 97 M-1 — `[stock_master_bulk_refresh]` emit 영속 (MEDIUM).

명세 (`_workspace/red/cycle97_fluctuation_api_replacement.md`):

- 사이클 96 emit 패턴 영속 (kospi + kosdaq + unknown=0)
- 사이클 97 영역 = fluctuation API 신규 도입 이후에도 emit 영역 영속

기대 동작 (Green, backend-dev 인계):
- `fetch_top_500_universe()` 호출 후 `[stock_master_bulk_refresh]` log emit 1회
- format: `universe=N kospi=K kosdaq=L unknown=0 securities=N etf_excluded=N elapsed_ms=N`
- caplog 기반 검증

Red 상태 (사이클 97): `_fetch_fluctuation` 신규 함수 미존재 → ImportError → FAIL.

영속 의무:
- 사이클 89 emit 패턴 영속 (사이클 96 영역 복원 영속)
- 사이클 95 unknown 합집합 graceful 영속 (unknown=0 = 사이클 96/97 영역 정상)
- 운영 가시화 영역 영속 (Grafana/Loki 모니터링)
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_m1_stock_master_bulk_refresh_emit_present(caplog: pytest.LogCaptureFixture):
    """M-1.a: `fetch_top_500_universe()` 가 `[stock_master_bulk_refresh]` emit 영속.

    검증 매트릭스:
    - `_fetch_fluctuation` mock (KOSPI 100 + KOSDAQ 100)
    - 호출 후 caplog 에 `[stock_master_bulk_refresh]` 1회
    - format 영역: `universe=200 kospi=100 kosdaq=100 unknown=0`

    Red 상태 (사이클 97): `_fetch_fluctuation` 미존재 → FAIL.

    Green (backend-dev): `fetch_top_500_universe` 본체 emit 영역 영속.
    """
    try:
        import src.engine.scanner as scanner_mod
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 97 M-1.a Red 상태 — `fetch_top_500_universe` 함수 부재"
        )

    if not hasattr(scanner_mod, "_fetch_fluctuation"):
        pytest.fail(
            "\n사이클 97 M-1.a Red 상태 — `_fetch_fluctuation` 함수 부재.\n"
            "  Green (backend-dev): scanner.py 신규 함수 도입 의무."
        )

    def _build_rows(prefix: str, count: int) -> list[dict]:
        return [
            {
                "stck_shrn_iscd": f"{prefix}{i:04d}",  # fluctuation 정본 응답 키
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
            return _build_rows("01", 100)
        elif market == "kosdaq":
            return _build_rows("02", 100)
        return []

    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    with patch("src.engine.scanner._fetch_fluctuation",
               new=AsyncMock(side_effect=_fake_fetch_fluctuation)):
        tickers = await fetch_top_500_universe()

    # 가드 1: emit 발생
    bulk_refresh_logs = [
        rec.message for rec in caplog.records
        if "[stock_master_bulk_refresh]" in rec.message
    ]
    assert len(bulk_refresh_logs) >= 1, (
        f"\n사이클 97 M-1.a 위반 — `[stock_master_bulk_refresh]` emit 부재:\n"
        f"  실제 records: {[r.message for r in caplog.records]}\n"
        f"  Green (backend-dev): fetch_top_500_universe 본체 emit 영역 영속 의무"
    )

    # 가드 2: format 영역 영속 (universe / kospi / kosdaq / unknown=0)
    msg = bulk_refresh_logs[0]
    for required_token in ["universe=", "kospi=", "kosdaq=", "unknown=0"]:
        assert required_token in msg, (
            f"\n사이클 97 M-1.a 위반 — emit format 영역 결함:\n"
            f"  누락 토큰: {required_token!r}\n"
            f"  실제 메시지: {msg}\n"
            f"  사이클 96 영역 영속 의무 (format: universe=N kospi=K kosdaq=L unknown=0)"
        )


@pytest.mark.asyncio
async def test_m1_unknown_zero_persistence():
    """M-1.b: 사이클 95 영속 영역 = unknown=0 (사이클 97 영역 = 2회 분리 호출 정상).

    검증 매트릭스:
    - mock fixture (각 100건) → unknown=0 영구 영속
    - 사이클 95 chicken-and-egg unknown 합집합 영역 = 분리 호출에서는 0 정상

    Red 상태 (사이클 97): `_fetch_fluctuation` 미존재 → FAIL.

    Green (backend-dev): unknown=0 hardcoded literal 영속.
    """
    try:
        import src.engine.scanner as scanner_mod
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 97 M-1.b Red 상태 — 함수 부재"
        )

    if not hasattr(scanner_mod, "_fetch_fluctuation"):
        pytest.fail(
            "\n사이클 97 M-1.b Red 상태 — `_fetch_fluctuation` 함수 부재"
        )

    captured_metric: list[dict] = []

    def _capture(metric: dict):
        captured_metric.append(metric)

    async def _fake_fetch_fluctuation(market: str, top_n: int = 250):
        return [
            {
                "stck_shrn_iscd": f"{market[0]}{i:05d}",
                "stck_prpr": "50000",
                "prdy_vrss": "1000",
                "prdy_ctrt": "2.0",
                "acml_vol": "1000000",
                "prdt_type_cd": "300",
            }
            for i in range(50)
        ]

    with patch("src.engine.scanner._fetch_fluctuation",
               new=AsyncMock(side_effect=_fake_fetch_fluctuation)), \
         patch("src.engine.stock_master_metrics.record_universe_refresh",
               side_effect=_capture):
        await fetch_top_500_universe()

    assert captured_metric, (
        "\n사이클 97 M-1.b 위반 — `record_universe_refresh` 호출 없음"
    )

    last_metric = captured_metric[-1]
    assert last_metric.get("unknown") == 0, (
        f"\n사이클 97 M-1.b 위반 — unknown 영역 결함:\n"
        f"  기대: 0 (사이클 95 영속 영역, 2회 분리 호출 = unknown=0 정상)\n"
        f"  실제: {last_metric.get('unknown')}\n"
        f"  사이클 97 영역 영속 의무 (KIS API 자체 분류 = 사이클 89/96 영역 복원)"
    )
