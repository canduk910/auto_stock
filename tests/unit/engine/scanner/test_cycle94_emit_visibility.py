"""사이클 94 M-1 — 운영 가시화: `[stock_master_bulk_refresh] universe=500` 영속 (MEDIUM).

명세 (`_workspace/red/cycle94_fid_input_iscd_fix.md` §4 M-1):

- 사이클 89 운영 prefix `[stock_master_bulk_refresh] universe=N kospi=K kosdaq=L` 영속
- 사이클 94 = universe ≥ 500 영속 (단일 호출 + post-split)
- emit 영역 = `fetch_top_500_universe()` 본체 logger.info

기대 동작 (Green, backend-dev 인계):
- mock 500+ ticker → logger.info `[stock_master_bulk_refresh]` emit
- universe 카운트 = 500 영속
- kospi / kosdaq 분리 카운트 영속

Red 상태 (사이클 94): production 사이클 89 영속 → universe=60 emit → FAIL.

영속 의무:
- 사이클 89 운영 prefix 영역 영속
- 사이클 88 운영 가시화 패턴 답습
- 매매 안전성 영향 0
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 97 Q53=A — `_fetch_volume_rank` 영역 전수 폐기. "
        "사이클 94 단일 호출 + post-split 영역 폐기. "
        "사이클 97 M-1 (`emit_visibility_fluctuation`) 이 영역 흡수. "
        "사이클 66 K-2 의미 전환 패턴 영속."
    ),
)
@pytest.mark.asyncio
async def test_m1_bulk_refresh_emit_universe_500(caplog):
    """M-1: `fetch_top_500_universe()` 가 `[stock_master_bulk_refresh] universe=500` emit.

    검증 매트릭스:
    - mock 500 ticker (KOSPI 300 + KOSDAQ 200)
    - logger.info `[stock_master_bulk_refresh]` emit 영속
    - universe=500 카운트 영속

    Red 상태 (사이클 94): production 사이클 89 영속 → 60 ticker → emit `universe=60` → FAIL.

    Green (backend-dev): 단일 호출 + post-split → universe ≥ 500 → PASS.

    영속 의무: 사이클 89 운영 prefix 영역 영속.
    """
    from src.engine.scanner import fetch_top_500_universe
    from src.models.stock import StockBasics

    # mock 500 ticker (KOSPI 300 + KOSDAQ 200, 양쪽 ceiling 영역 검증)
    mock_response = []
    for i in range(500):
        ticker = f"{i:06d}"
        mock_response.append({
            "mksc_shrn_iscd": ticker,
            "prdy_vol": 1_000_000 - i,
            "stck_prpr": 50_000,
            "prdy_vrss": 1_000,
            "prdt_type_cd": "300",
        })

    # 짝수 = KOSPI(02), 홀수 = KOSDAQ(03) — 양쪽 컬럼 옵션 호환 mock
    sm_data_map = {
        f"{i:06d}": StockBasics(
            ticker=f"{i:06d}",
            name=f"종목{i}",
            excg_dvsn_cd="02" if i % 2 == 0 else "03",
            raw={"market_id": "STK" if i % 2 == 0 else "KSQ"},
        )
        for i in range(500)
    }

    async def _fake_fetch_volume_rank(market="all", top_n=500, max_pages=17):
        return mock_response

    async def _fake_sm_get(ticker: str):
        return sm_data_map.get(ticker)

    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)), \
         patch("src.db.stock_master.get",
               new=AsyncMock(side_effect=_fake_sm_get)):
        result = await fetch_top_500_universe()

    # 가드 1: 결과 ticker 수 ≥ 500 (영역 확장 영속)
    assert len(result) >= 500 or len(result) == len(mock_response), (
        f"\n사이클 94 M-1 위반 — universe 카운트 결함:\n"
        f"  기대: ≥ 500 (단일 호출 + post-split)\n"
        f"  실제: {len(result)}"
    )

    # 가드 2: `[stock_master_bulk_refresh]` 운영 prefix 영속
    bulk_messages = [r.message for r in caplog.records
                     if "[stock_master_bulk_refresh]" in r.message]
    assert bulk_messages, (
        f"\n사이클 94 M-1 위반 — `[stock_master_bulk_refresh]` emit 부재:\n"
        f"  영속 의무: 사이클 89 운영 prefix\n"
        f"  caplog 기록: {[r.message for r in caplog.records[:5]]}"
    )

    # 가드 3: universe=N 카운트 영역 노출 (운영 가시화 영속)
    msg = bulk_messages[0]
    assert "universe=" in msg, (
        f"\n사이클 94 M-1 위반 — universe=N 형식 결함:\n"
        f"  실제 메시지: {msg}\n"
        f"  영속 의무: `universe=500 kospi=K kosdaq=L` 영역"
    )
