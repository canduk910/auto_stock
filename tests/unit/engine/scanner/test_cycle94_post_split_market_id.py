"""사이클 94 H-3 — Q42=A post-split: `stock_master` 캐시 join (HIGH).

명세 (`_workspace/red/cycle94_fid_input_iscd_fix.md`):

- 사이클 94 단일 호출 (`"0000"`) → 응답 post-split 의무
- Q42=A 옵션: `stock_master.get(ticker)` 캐시 활용 (추가 KIS 호출 0)
- 분류 = KOSPI / KOSDAQ (excg_dvsn_cd 옵션 A "02"/"03" 또는 market_id 옵션 B "STK"/"KSQ")

기대 동작 (Green, backend-dev 인계):
- `fetch_top_500_universe()` 본체에서 ticker 별 `stock_master.get(ticker)` 호출
- 분류 헬퍼 `_classify_market(sm_data)` → "KOSPI" / "KOSDAQ" / None
- KOSPI 분류 ticker → kospi 리스트 / KOSDAQ → kosdaq / None → graceful skip
- 결과 = KOSPI 250 + KOSDAQ 250 = 500 영속

Red 상태 (사이클 94): production 코드 사이클 89 영역 `_fetch_volume_rank` 2회 호출
+ stock_master.get() 호출 0건 → FAIL.

영속 의무:
- Q42=A 캐시 활용 (추가 KIS 호출 0건 영속)
- 사이클 89 KOSPI/KOSDAQ 분리 의도 영속
- 사이클 88 G-REJECT 영속 (graceful 패턴 답습)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h3_post_split_uses_stock_master_cache():
    """H-3: `fetch_top_500_universe()` 가 post-split 시 `stock_master.get()` 호출 (Q42=A).

    검증 매트릭스:
    - mock `_fetch_volume_rank(market="all")` → 4 ticker 단일 응답
    - mock `stock_master.get(ticker)` 호출 → 2 KOSPI + 2 KOSDAQ 분류
    - `fetch_top_500_universe()` 호출 → KOSPI/KOSDAQ 분리 결과 검증

    Red 상태 (사이클 94): 사이클 89 영역 _fetch_volume_rank 2회 호출 + stock_master.get 호출 0 →
    FAIL (mock 호출 카운트 0).

    Green (backend-dev):
    - _fetch_volume_rank 단일 호출 (market="all")
    - 결과 ticker 각각 stock_master.get() 호출 → post-split
    - _classify_market 헬퍼 (옵션 A excg_dvsn_cd or 옵션 B market_id, 행위 무관)

    영속 의무:
    - Q42=A 캐시 활용 (추가 KIS 호출 0)
    - 사이클 88 G-REJECT 답습 (graceful 패턴)
    """
    from src.engine.scanner import fetch_top_500_universe
    from src.models.stock import StockBasics

    # mock 단일 호출 응답 (4 ticker)
    mock_response = [
        {"mksc_shrn_iscd": "005930", "prdy_vol": 1_000_000, "stck_prpr": 70_000,
         "prdy_vrss": 500, "prdt_type_cd": "300"},  # 삼성전자 KOSPI
        {"mksc_shrn_iscd": "035720", "prdy_vol": 800_000, "stck_prpr": 50_000,
         "prdy_vrss": 300, "prdt_type_cd": "300"},  # 카카오 KOSPI
        {"mksc_shrn_iscd": "035420", "prdy_vol": 600_000, "stck_prpr": 200_000,
         "prdy_vrss": 1000, "prdt_type_cd": "300"},  # 네이버 KOSPI (실제로 KOSPI 이나 mock 으로 KOSDAQ 표시 가능)
        {"mksc_shrn_iscd": "247540", "prdy_vol": 500_000, "stck_prpr": 300_000,
         "prdy_vrss": 2000, "prdt_type_cd": "300"},  # 에코프로비엠 KOSDAQ
    ]

    # mock stock_master.get(): 옵션 A (excg_dvsn_cd) / 옵션 B (market_id) 모두 호환
    # backend-dev 가 둘 중 어느 컬럼을 사용해도 통과하도록 양쪽 영역 mock 데이터 주입
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

    fetch_call_log: list[dict] = []
    sm_get_call_log: list[str] = []

    async def _fake_fetch_volume_rank(market="all", top_n=500, max_pages=17):
        fetch_call_log.append({"market": market, "top_n": top_n, "max_pages": max_pages})
        return mock_response

    async def _fake_sm_get(ticker: str):
        sm_get_call_log.append(ticker)
        return sm_data_map.get(ticker)

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)), \
         patch("src.db.stock_master.get",
               new=AsyncMock(side_effect=_fake_sm_get)):
        result = await fetch_top_500_universe()

    # 가드 1: _fetch_volume_rank 단일 호출 영역 (Q42=A 핵심 행위)
    assert len(fetch_call_log) == 1, (
        f"\n사이클 94 H-3 위반 — `_fetch_volume_rank` 호출 수 결함:\n"
        f"  기대: 1 (단일 호출 영역 = KIS API 호출 절반 감소)\n"
        f"  실제: {len(fetch_call_log)}\n"
        f"  호출 로그: {fetch_call_log}\n"
        f"  Green 의무: market='all' 단일 호출 영역"
    )

    # 가드 2: market="all" 호출 영속 (사이클 94 시그너처)
    assert fetch_call_log[0]["market"] == "all", (
        f"\n사이클 94 H-3 위반 — `market` 인자 결함:\n"
        f"  기대: 'all' (사이클 94 시그너처)\n"
        f"  실제: '{fetch_call_log[0]['market']}'\n"
        f"  사이클 89 영속 '1'/'2' 영역 폐기 의무"
    )

    # 가드 3: stock_master.get() 호출 영속 (Q42=A 캐시 활용 = 추가 KIS 호출 0)
    assert len(sm_get_call_log) >= 4, (
        f"\n사이클 94 H-3 위반 — `stock_master.get()` 호출 부재:\n"
        f"  기대: ≥ 4 (응답 4 ticker 모두 post-split 분류 영속)\n"
        f"  실제: {len(sm_get_call_log)}\n"
        f"  호출 ticker: {sm_get_call_log}\n"
        f"  Q42=A: stock_master 캐시 활용 (추가 KIS 호출 0건 영역)\n"
        f"  Green 의무: 응답 ticker 별 stock_master.get(ticker) 호출 + post-split"
    )

    # 가드 4: 결과 = ticker 리스트 (보통 KOSPI 3 + KOSDAQ 1 = 4 영역)
    assert isinstance(result, list), (
        f"\n사이클 94 H-3 위반 — 반환 타입 결함:\n"
        f"  기대: list[str]\n"
        f"  실제: {type(result).__name__}"
    )
    assert "005930" in result and "247540" in result, (
        f"\n사이클 94 H-3 위반 — KOSPI + KOSDAQ 분류 결함:\n"
        f"  기대: 005930 (KOSPI) + 247540 (KOSDAQ) 양쪽 포함\n"
        f"  실제 결과: {result}"
    )
