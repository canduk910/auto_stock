"""사이클 96 M-1 — `[stock_master_bulk_refresh]` emit 영역 정합 (MEDIUM).

명세 (`_workspace/red/cycle96_resurrect_industry_code_with_pagination.md`):

- `[stock_master_bulk_refresh] universe=N kospi=K kosdaq=L unknown=0 ...` 영속
- 사이클 95 unknown 키 영속 (영역 복원 결과 unknown=0 정상)
- 사이클 89 emit 영역 답습 (개장 전 1회 INFO)

기대 동작 (Green, backend-dev 인계):
- `fetch_top_500_universe()` 호출 시 `[stock_master_bulk_refresh]` 1행 emit
- 영역 = `universe=N kospi=K kosdaq=L unknown=0` 정합

Red 상태 (사이클 96): 사이클 94 영속 → universe ~30 + unknown 영역 ≠ 0 → FAIL.

영속 의무:
- 사이클 95 unknown 키 호환
- 사이클 89 emit 영역 답습
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 97 Q53=A — `_fetch_volume_rank` 영역 전수 폐기 + 응답 키 `mksc_shrn_iscd` → `stck_shrn_iscd` 영역 전환. "
            "KIS fluctuation API (`_fetch_fluctuation`) 영역 신규 도입으로 영역 전환. "
            "사이클 96 emit visibility 영역 = 사이클 97 M-1 가드로 영역 흡수. "
            "사이클 66 K-2 의미 전환 패턴 영속."
        ),
    ),
]


def _make_row(ticker: str) -> dict:
    return {
        "mksc_shrn_iscd": ticker,
        "prdy_vol": "1000000",
        "stck_prpr": "50000",
        "prdy_vrss": "1000",
        "prdt_type_cd": "300",
    }


@pytest.mark.asyncio
async def test_m1_emit_visibility_two_call_with_unknown_zero(caplog):
    """M-1.a: `[stock_master_bulk_refresh]` 1행 emit + `unknown=0` 영역 영속.

    검증 매트릭스:
    - mock KOSPI 100 + KOSDAQ 100 ticker
    - emit prefix 영속 = `[stock_master_bulk_refresh]`
    - emit 영역 = `universe=200 kospi=100 kosdaq=100 unknown=0`

    Red 상태 (사이클 96): 사이클 94 단일 호출 영속 → universe ≠ 200 → FAIL.

    Green (backend-dev): 2회 호출 + unknown=0 영속 → PASS.
    """
    from src.engine.scanner import fetch_top_500_universe

    kospi_rows = [_make_row(f"K{i:05d}") for i in range(100)]
    kosdaq_rows = [_make_row(f"D{i:05d}") for i in range(100)]

    async def _fake_fetch_volume_rank(market: str, top_n: int = 250, max_pages: int = 17):
        if market == "kospi":
            return kospi_rows
        elif market == "kosdaq":
            return kosdaq_rows
        return []

    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)):
        await fetch_top_500_universe()

    emit_messages = [
        record.getMessage() for record in caplog.records
        if "[stock_master_bulk_refresh]" in record.getMessage()
    ]

    assert len(emit_messages) >= 1, (
        f"\n사이클 96 M-1.a 위반 — `[stock_master_bulk_refresh]` emit 부재:\n"
        f"  caplog records: {[r.getMessage() for r in caplog.records]}\n"
        f"  사이클 89 emit 영역 답습 의무"
    )

    msg = emit_messages[0]

    # 가드 1: kospi=100 영역
    assert "kospi=100" in msg, (
        f"\n사이클 96 M-1.a 위반 — `kospi=100` 영역 부재:\n"
        f"  emit msg: {msg}\n"
        f"  사이클 89 영역 복원 효과"
    )

    # 가드 2: kosdaq=100 영역
    assert "kosdaq=100" in msg, (
        f"\n사이클 96 M-1.a 위반 — `kosdaq=100` 영역 부재:\n"
        f"  emit msg: {msg}"
    )

    # 가드 3: unknown=0 영역 (사이클 95 키 영속 + 사이클 96 영역 복원 결과)
    assert "unknown=0" in msg, (
        f"\n사이클 96 M-1.a 위반 — `unknown=0` 영역 부재:\n"
        f"  emit msg: {msg}\n"
        f"  사이클 95 키 영속 + 사이클 96 영역 복원 결과 (unknown=0 정상)"
    )
