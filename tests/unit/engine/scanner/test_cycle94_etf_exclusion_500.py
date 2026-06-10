"""사이클 94 M-2 — ETF/리츠/SPAC 제외 영속 (사이클 89 답습) (MEDIUM).

명세 (`_workspace/red/cycle94_fid_input_iscd_fix.md` §4 M-2):

- 사이클 89 `_universe_filter_securities_only` 헬퍼 영역 영속
- 단일 호출 영역에서도 ETF/리츠/SPAC 자동 제외 영속
- `prdt_type_cd != "300"` 차단

기대 동작 (Green, backend-dev 인계):
- mock 응답: 보통주 + ETF + 리츠 혼합 → 보통주만 결과 포함
- 사이클 89 헬퍼 호출 영속

Red 상태 (사이클 94): production 사이클 89 영속 — 호출 영속이나 사이클 94 시정 후
단일 호출 영역으로 변경 시 헬퍼 호출 누락 위험 → FAIL.

영속 의무:
- 사이클 89 헬퍼 영속 (Q42=A 호출 chain 보존)
- 6 전략 부적합 종목 차단 (영역 영속)
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 96 Q50=D — 사이클 94 단일 호출 경로 (`market='all'`) 폐기 계약. "
        "사이클 96 영역 복원 = 2회 분리 호출 (KIS API 파라미터 FID_TRGT_EXLS_CLS_CODE 서버 필터). "
        "`_universe_filter_securities_only` 호출 위치 변경 — mock 경로 폐기. 사이클 66 K-2 의미 전환 패턴."
    ),
)
@pytest.mark.asyncio
async def test_m2_etf_reits_excluded_in_single_call_path():
    """M-2: 단일 호출 영역에서도 ETF/리츠 제외 영속 (사이클 89 헬퍼 호출 영속).

    검증 매트릭스:
    - mock 응답: 보통주 3 + ETF 2 + 리츠 1 = 6건
    - 결과 영역: 보통주 3건만 포함 (ETF/리츠 제외)

    Red 상태 (사이클 94): production 사이클 89 영속 — 단일 호출 영역 미적용 → 6건 모두 포함 위험.

    Green (backend-dev): 단일 호출 영역에서도 `_universe_filter_securities_only` 호출 영속 → PASS.

    영속 의무: 사이클 89 헬퍼 호출 chain 영속.
    """
    from src.engine.scanner import fetch_top_500_universe
    from src.models.stock import StockBasics

    # mock 응답: 보통주 3 + ETF 2 + 리츠 1 혼합
    mock_response = [
        # 보통주 3건
        {"mksc_shrn_iscd": "005930", "prdy_vol": 1_000_000, "stck_prpr": 70_000,
         "prdy_vrss": 500, "prdt_type_cd": "300"},  # 삼성전자
        {"mksc_shrn_iscd": "035720", "prdy_vol": 800_000, "stck_prpr": 50_000,
         "prdy_vrss": 300, "prdt_type_cd": "300"},  # 카카오
        {"mksc_shrn_iscd": "035420", "prdy_vol": 600_000, "stck_prpr": 200_000,
         "prdy_vrss": 1_000, "prdt_type_cd": "300"},  # 네이버
        # ETF 2건 (제외 대상)
        {"mksc_shrn_iscd": "069500", "prdy_vol": 500_000, "stck_prpr": 30_000,
         "prdy_vrss": 200, "prdt_type_cd": "301"},  # KODEX 200
        {"mksc_shrn_iscd": "102110", "prdy_vol": 400_000, "stck_prpr": 35_000,
         "prdy_vrss": 100, "prdt_type_cd": "301"},  # TIGER 200
        # 리츠 1건 (제외 대상)
        {"mksc_shrn_iscd": "330590", "prdy_vol": 300_000, "stck_prpr": 5_000,
         "prdy_vrss": 50, "prdt_type_cd": "302"},  # 롯데리츠
    ]

    # stock_master mock - 보통주만 KOSPI 분류, ETF/리츠는 어차피 필터 제외되므로 무관
    sm_data_map = {
        "005930": StockBasics(ticker="005930", name="삼성전자", excg_dvsn_cd="02",
                              raw={"market_id": "STK"}),
        "035720": StockBasics(ticker="035720", name="카카오", excg_dvsn_cd="02",
                              raw={"market_id": "STK"}),
        "035420": StockBasics(ticker="035420", name="NAVER", excg_dvsn_cd="02",
                              raw={"market_id": "STK"}),
    }

    async def _fake_fetch_volume_rank(market="all", top_n=500, max_pages=17):
        return mock_response

    async def _fake_sm_get(ticker: str):
        return sm_data_map.get(ticker)

    with patch("src.engine.scanner._fetch_volume_rank",
               new=AsyncMock(side_effect=_fake_fetch_volume_rank)), \
         patch("src.db.stock_master.get",
               new=AsyncMock(side_effect=_fake_sm_get)):
        result = await fetch_top_500_universe()

    # 가드 1: ETF/리츠 ticker 영역 부재 (사이클 89 영속)
    forbidden = {"069500", "102110", "330590"}
    leaked = forbidden & set(result)
    assert leaked == set(), (
        f"\n사이클 94 M-2 위반 — ETF/리츠 영역 결함:\n"
        f"  금지 ticker: {forbidden}\n"
        f"  결과 영역 유출: {leaked}\n"
        f"  영속 의무: 사이클 89 `_universe_filter_securities_only` 호출 영속\n"
        f"  Green 의무: 단일 호출 영역에서도 헬퍼 호출 영속"
    )

    # 가드 2: 보통주 3건 영역 영속
    expected = {"005930", "035720", "035420"}
    present = expected & set(result)
    assert present == expected, (
        f"\n사이클 94 M-2 위반 — 보통주 누락:\n"
        f"  기대: {expected}\n"
        f"  실제: {present}\n"
        f"  보통주는 영속 영역"
    )
