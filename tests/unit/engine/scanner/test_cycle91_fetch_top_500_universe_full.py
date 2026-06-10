"""사이클 91 H-4 — `fetch_top_500_universe()` 통합 시나리오 500 ticker 완전 달성 (HIGH).

명세 (`_workspace/red/cycle91_volume_rank_pagination.md`):

- 사이클 89 운영 실측: KOSPI 30 + KOSDAQ 30 = 60 ticker 적재
- 사이클 91 시정 후 목표: KOSPI 250 + KOSDAQ 250 = 500 ticker

기대 동작 (Green):
- KOSPI 페이징 9 페이지 × 30 = 270 → top_n=250 cap
- KOSDAQ 페이징 9 페이지 × 30 = 270 → top_n=250 cap
- ETF 제외 통과 (보통주 prdt_type_cd="300" 만)
- 합집합 500 ticker 완전 달성

Red 상태 (사이클 91): 단일 호출 → 60 ticker 반환 → FAIL.
사이클 89 silent 결함 영구 차단.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 94 Q37=C + Q42=A — `fetch_top_500_universe` 가 단일 호출 (`FID_INPUT_ISCD='0000'`) "
        "+ stock_master.excg_dvsn_cd post-split 로 재설계됨. 사이클 91 시점 "
        "`FID_INPUT_ISCD='0001'/'0002'` 2회 호출 + `market_call_count['1'/'2']` 패턴 폐기. "
        "사이클 66 K-2 의미 전환 패턴."
    ),
)
@pytest.mark.asyncio
async def test_h4_fetch_top_500_universe_full_500_tickers():
    """H-4: `fetch_top_500_universe()` 통합 시나리오 KOSPI 250 + KOSDAQ 250 = 500.

    검증 매트릭스:
    - KOSPI mock: 9 페이지 × 30 = 270 가용 (페이지 1~8 tr_cont="M", 페이지 9 tr_cont="")
    - KOSDAQ mock: 9 페이지 × 30 = 270 가용 (동일 패턴)
    - 각 시장 top_n=250 cap 적용 → 250 + 250 = 500 ticker
    - ETF/리츠/SPAC 자동 제외 (prdt_type_cd="300" 만 통과)
    - 결과: 500건 (사이클 89 명세 100% 달성)

    Red 상태 (사이클 91): 단일 호출 → 30 + 30 = 60건 반환 → FAIL.

    영속 의무:
    - KOSPI/KOSDAQ 분리 호출 (mrkt_div_cls_code=1/2)
    - 사이클 89 ETF 제외 영역 영속
    - 사이클 48 BFB 거래대금 재정렬 답습
    """
    from src.engine.scanner import fetch_top_500_universe

    # KOSPI 9 페이지 × 30 = 270 가용 (top_n=250 cap 적용 예상)
    # 종목코드 "001000"~"001269" (KOSPI 식별)
    kospi_pages = []
    for p in range(9):
        kospi_pages.append({
            "rt_cd": "0",
            "output": [
                {"mksc_shrn_iscd": f"00{1000 + p * 30 + i:04d}",
                 "prdy_vol": 2_000_000 - p * 10_000 - i,
                 "stck_prpr": 50_000, "prdy_vrss": 1_000,
                 "prdt_type_cd": "300"}  # 보통주
                for i in range(30)
            ],
            "_response_headers": {"tr_cont": "M" if p < 8 else ""},
        })

    # KOSDAQ 9 페이지 × 30 = 270 가용
    # 종목코드 "030000"~"030269" (KOSDAQ 식별)
    kosdaq_pages = []
    for p in range(9):
        kosdaq_pages.append({
            "rt_cd": "0",
            "output": [
                {"mksc_shrn_iscd": f"03{p * 30 + i:04d}",
                 "prdy_vol": 1_000_000 - p * 5_000 - i,
                 "stck_prpr": 30_000, "prdy_vrss": 500,
                 "prdt_type_cd": "300"}  # 보통주
                for i in range(30)
            ],
            "_response_headers": {"tr_cont": "M" if p < 8 else ""},
        })

    market_call_count = {"1": 0, "2": 0}

    async def _fake_kis_get_quote(*args, **kwargs):
        # params 에서 market 추출 (FID_INPUT_ISCD)
        params = kwargs.get("params")
        if params is None and len(args) >= 3:
            params = args[2]
        # 디폴트 dict 일 수도, kwarg 일 수도 — graceful 추출
        if not isinstance(params, dict):
            params = {}
        input_iscd = params.get("FID_INPUT_ISCD", "")

        if input_iscd == "0001":  # KOSPI
            idx = market_call_count["1"]
            market_call_count["1"] += 1
            if idx >= len(kospi_pages):
                return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}
            return kospi_pages[idx]
        elif input_iscd == "0002":  # KOSDAQ
            idx = market_call_count["2"]
            market_call_count["2"] += 1
            if idx >= len(kosdaq_pages):
                return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}
            return kosdaq_pages[idx]
        return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        result = await fetch_top_500_universe()

    # 가드 1: 결과 = 500건 (사이클 89 명세 100% 달성)
    assert len(result) == 500, (
        f"\n사이클 91 H-4 위반 — 500 universe 완전 달성 결함:\n"
        f"  실제: {len(result)} ticker (사이클 89 명세 = 500 의무)\n"
        f"  사이클 89 silent 결함 영구 차단 의무\n"
        f"  운영 실측 (사용자 보고): KOSPI 30 + KOSDAQ 30 = 60\n"
        f"  Green 의무: KOSPI 250 + KOSDAQ 250 = 500"
    )

    # 가드 2: KOSPI/KOSDAQ 양쪽 모두 250건 가까이 포함
    kospi_tickers = [t for t in result if t.startswith("00")]
    kosdaq_tickers = [t for t in result if t.startswith("03")]
    assert len(kospi_tickers) == 250, (
        f"\n사이클 91 H-4 위반 — KOSPI 250 미달성:\n"
        f"  실제: {len(kospi_tickers)} (의무 = 250)\n"
        f"  Green 의무: KOSPI top_n=250 cap 정확 적용"
    )
    assert len(kosdaq_tickers) == 250, (
        f"\n사이클 91 H-4 위반 — KOSDAQ 250 미달성:\n"
        f"  실제: {len(kosdaq_tickers)} (의무 = 250)"
    )

    # 가드 3: KOSPI 페이징 호출 횟수 ≥ 9 (페이지당 30 × 9 = 270 ≥ 250 누적 후 종료)
    # 정확 횟수는 page 1~8 후 누적 240 < 250 → page 9 호출 후 270 ≥ 250 break = 9 회
    assert market_call_count["1"] >= 9, (
        f"\n사이클 91 H-4 위반 — KOSPI 페이징 호출 누락:\n"
        f"  실제: {market_call_count['1']} 회 (의무 ≥ 9 = top_n=250 도달까지)"
    )
    assert market_call_count["2"] >= 9, (
        f"\n사이클 91 H-4 위반 — KOSDAQ 페이징 호출 누락:\n"
        f"  실제: {market_call_count['2']} 회 (의무 ≥ 9)"
    )
