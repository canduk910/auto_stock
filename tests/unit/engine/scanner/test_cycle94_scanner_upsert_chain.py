"""사이클 94 M-4 — 사이클 93 `_scanner_upsert_loop` chain 영속 (MEDIUM).

명세 (`_workspace/red/cycle94_fid_input_iscd_fix.md` §4 M-4):

- 사이클 93 호출 chain 영속 (`fetch_top_500_universe` 결과 → `_universe_eager_refresh_loop`)
- 사이클 94 시정 후에도 chain 변경 0 (호출 영속)
- scheduler `_universe_eager_refresh_loop` self method → scanner module 함수 위임 영속

기대 동작 (Green, backend-dev 인계):
- scanner module `_universe_eager_refresh_loop(candidates)` 함수 영역 영속
- 사이클 94 단일 호출 + post-split 결과 ticker list 인자로 호출 영속

Red 상태 (사이클 94): production 사이클 91/93 영속 — chain 영속이나 사이클 94 시정 시
chain 누락 위험 → FAIL (`_universe_eager_refresh_loop` 모듈 함수 부재 시 ImportError).

영속 의무:
- 사이클 93 호출 chain 영속 (변경 0)
- 사이클 89 도입 영역 영속
- 매매 안전성 영향 0 (영역 분리)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def test_m4_scanner_module_universe_eager_refresh_loop_exists():
    """M-4.a: scanner module 의 `_universe_eager_refresh_loop` 모듈 함수 영역 영속.

    사이클 89 도입 + 사이클 93 chain 영속 의무.

    Red 상태 (사이클 94): 사이클 94 시정 중 모듈 함수 변경/제거 위험 영역 검출.

    Green: 영속 의무 영역 (변경 0).
    """
    from src.engine import scanner as scanner_mod

    assert hasattr(scanner_mod, "_universe_eager_refresh_loop"), (
        "\n사이클 94 M-4.a 위반 — `_universe_eager_refresh_loop` 모듈 함수 부재:\n"
        "  사이클 89 도입 + 사이클 93 chain 영속 의무\n"
        "  사이클 94 시정 시 변경 0 (호출 chain 영속)"
    )


def test_m4_scanner_module_fetch_top_500_universe_exists():
    """M-4.b: scanner module 의 `fetch_top_500_universe()` 함수 영역 영속.

    사이클 89 도입 + 사이클 94 단일 호출 + post-split 영속.
    """
    from src.engine import scanner as scanner_mod

    assert hasattr(scanner_mod, "fetch_top_500_universe"), (
        "\n사이클 94 M-4.b 위반 — `fetch_top_500_universe()` 함수 부재:\n"
        "  사이클 89 도입 + 사이클 94 단일 호출 영속 의무"
    )


@pytest.mark.asyncio
async def test_m4_fetch_500_results_compatible_with_universe_loop():
    """M-4.c: `fetch_top_500_universe()` 결과 ticker list 가 `_universe_eager_refresh_loop`
    인자로 정확히 호환 영속.

    검증 매트릭스:
    - mock `_fetch_volume_rank` + `stock_master.get` → 4 ticker 결과
    - mock `_universe_eager_refresh_loop` → 호출 시 받은 인자 검증
    - 호출 인자 = list[str] 영속 (chain 영속)

    Red 상태 (사이클 94): production 사이클 91 영속 → 60 ticker 결과 → chain 인자 결함 영역 없음.

    Green (사이클 94 시정 후): 500 ticker 결과 → chain 인자 = list[str] 영속.

    영속 의무: 사이클 93 chain 변경 0.
    """
    from src.engine import scanner as scanner_mod
    from src.models.stock import StockBasics

    mock_response = [
        {"mksc_shrn_iscd": "005930", "prdy_vol": 1_000_000, "stck_prpr": 70_000,
         "prdy_vrss": 500, "prdt_type_cd": "300"},
        {"mksc_shrn_iscd": "035720", "prdy_vol": 800_000, "stck_prpr": 50_000,
         "prdy_vrss": 300, "prdt_type_cd": "300"},
        {"mksc_shrn_iscd": "035420", "prdy_vol": 600_000, "stck_prpr": 200_000,
         "prdy_vrss": 1_000, "prdt_type_cd": "300"},
        {"mksc_shrn_iscd": "247540", "prdy_vol": 500_000, "stck_prpr": 300_000,
         "prdy_vrss": 2_000, "prdt_type_cd": "300"},
    ]

    sm_data_map = {
        "005930": StockBasics(ticker="005930", name="삼성전자", excg_dvsn_cd="02",
                              raw={"market_id": "STK"}),
        "035720": StockBasics(ticker="035720", name="카카오", excg_dvsn_cd="02",
                              raw={"market_id": "STK"}),
        "035420": StockBasics(ticker="035420", name="NAVER", excg_dvsn_cd="02",
                              raw={"market_id": "STK"}),
        "247540": StockBasics(ticker="247540", name="에코프로비엠", excg_dvsn_cd="03",
                              raw={"market_id": "KSQ"}),
    }

    async def _fake_fetch_volume_rank(market="all", top_n=500, max_pages=17):
        return mock_response

    async def _fake_sm_get(ticker: str):
        return sm_data_map.get(ticker)

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)), \
         patch("src.db.stock_master.get",
               new=AsyncMock(side_effect=_fake_sm_get)):
        result = await scanner_mod.fetch_top_500_universe()

    # chain 인자 호환 영속 — list[str] 영역
    assert isinstance(result, list), (
        f"\n사이클 94 M-4.c 위반 — chain 인자 타입 결함:\n"
        f"  기대: list[str] (사이클 93 chain 영속)\n"
        f"  실제: {type(result).__name__}"
    )
    if result:
        assert all(isinstance(t, str) for t in result), (
            f"\n사이클 94 M-4.c 위반 — chain 인자 element 타입 결함:\n"
            f"  기대: 모두 str (ticker 6자리)\n"
            f"  실제 첫 element: {type(result[0]).__name__}"
        )
