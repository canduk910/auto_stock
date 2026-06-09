"""사이클 91 H-1 — KIS volume_rank 페이징 누적 검증 (HIGH).

명세 (`_workspace/red/cycle91_volume_rank_pagination.md`):

- KIS `volume_rank` (FHPST01710000) = 페이징 응답 의무
- 응답 헤더 `tr_cont == "M"` → 다음 페이지 존재 (Multi)
- 재호출 입력 `tr_cont = "N"` → 다음 페이지 누적 (Next)
- 사이클 89 silent 결함: 단일 호출 + slicing → 60 ticker 적재 (KOSPI 30 + KOSDAQ 30)
- 사이클 91 시정: 페이징 누적 의무

기대 동작 (Green, backend-dev 인계):
- 첫 호출 input tr_cont = ""
- 응답 헤더 tr_cont = "M" 시 두 번째 호출 input tr_cont = "N"
- 응답 헤더 tr_cont != "M" 시 종료
- 누적된 모든 페이지 ticker 반환

Red 상태 (사이클 91): production 코드 단일 호출만 → 첫 페이지 30 만 반환 → FAIL.

영속 의무:
- KIS 정본 페이징 패턴 (`open-trading-api/examples_llm/.../volume_rank.py`)
- 사이클 89 영역 영속 (KOSPI/KOSDAQ 분리 + ETF 제외 + 거래대금 정렬)
- 사이클 38 명문화 영속 (매수 진입 전용)
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h1_volume_rank_pagination_accumulates_across_pages():
    """H-1: `_fetch_volume_rank` 가 KIS `tr_cont == "M"` 응답 시 다음 페이지 호출 +
    누적된 모든 페이지 ticker 반환.

    검증 매트릭스:
    - mock 3 페이지 (각 30건 = 90 누적)
    - 페이지 1 응답: `tr_cont = "M"` → 다음 페이지 호출 의무
    - 페이지 2 응답: `tr_cont = "M"` → 다음 페이지 호출 의무
    - 페이지 3 응답: `tr_cont = ""` (또는 "D"/"E") → 종료
    - 결과: 90건 누적 (top_n=250 미만이므로 max_pages 도달 전 종료)

    Red 상태 (사이클 91): production 코드 단일 호출만 → 첫 페이지 30 만 반환 → FAIL.

    Green (backend-dev): 페이징 루프 도입 → PASS.

    영속 의무:
    - KIS 정본 페이징 패턴 (tr_cont "" → "M" → "N" → "M" → "N" → "")
    - 사이클 89 영역 영속 (KOSPI/KOSDAQ 분리 + ETF 제외 + 거래대금 정렬)
    """
    from src.engine.scanner import _fetch_volume_rank

    # mock 3 페이지 응답 (각 30건 = KIS 표준)
    page_responses = [
        {
            "rt_cd": "0",
            "output": [
                {"mksc_shrn_iscd": f"{i:06d}", "prdy_vol": 1_000_000 + i,
                 "stck_prpr": 50_000, "prdy_vrss": 1_000,
                 "prdt_type_cd": "300"}
                for i in range(30)
            ],
            "_response_headers": {"tr_cont": "M"},  # 페이지 1: 다음 페이지 존재
        },
        {
            "rt_cd": "0",
            "output": [
                {"mksc_shrn_iscd": f"{i + 30:06d}", "prdy_vol": 900_000 + i,
                 "stck_prpr": 50_000, "prdy_vrss": 1_000,
                 "prdt_type_cd": "300"}
                for i in range(30)
            ],
            "_response_headers": {"tr_cont": "M"},  # 페이지 2: 다음 페이지 존재
        },
        {
            "rt_cd": "0",
            "output": [
                {"mksc_shrn_iscd": f"{i + 60:06d}", "prdy_vol": 800_000 + i,
                 "stck_prpr": 50_000, "prdy_vrss": 1_000,
                 "prdt_type_cd": "300"}
                for i in range(30)
            ],
            "_response_headers": {"tr_cont": ""},  # 페이지 3: 마지막 페이지
        },
    ]

    call_log: list[str] = []

    async def _fake_kis_get_quote(*args, **kwargs):
        # 호출자 영역 검증: tr_cont 키워드 인자 추출
        tr_cont = kwargs.get("tr_cont", "MISSING_KWARG")
        call_log.append(tr_cont)
        page_idx = len(call_log) - 1
        if page_idx >= len(page_responses):
            return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}
        return page_responses[page_idx]

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        result = await _fetch_volume_rank(market="1", top_n=250)

    # 가드 1: 누적 카운트 = 90 (3 페이지 × 30)
    assert len(result) == 90, (
        f"\n사이클 91 H-1 위반 — 페이징 누적 결함:\n"
        f"  실제: {len(result)}건 (KIS 정본 = 3 페이지 90건 누적 의무)\n"
        f"  사이클 89 silent 결함: 단일 호출 + slicing → 30 만 반환\n"
        f"  KIS 정본: tr_cont == 'M' 시 다음 페이지 호출 의무"
    )

    # 가드 2: 호출 횟수 = 3 (페이징 누적 확정)
    assert len(call_log) == 3, (
        f"\n사이클 91 H-1 위반 — KIS 호출 횟수:\n"
        f"  실제: {len(call_log)} (페이징 3 회 의무)\n"
        f"  호출 로그: {call_log}\n"
        f"  KIS 정본: 첫 호출 tr_cont='' → 두 번째 tr_cont='N' → 세 번째 tr_cont='N'"
    )

    # 가드 3: tr_cont 입력 순서 정확 (KIS 정본 패턴)
    assert call_log[0] == "", (
        f"\n사이클 91 H-1 위반 — 첫 호출 tr_cont 입력 위반:\n"
        f"  실제: {call_log[0]!r} (KIS 정본 = '' 의무)\n"
        f"  KIS 정본: 첫 호출 = 빈 문자열"
    )
    assert call_log[1] == "N", (
        f"\n사이클 91 H-1 위반 — 두 번째 호출 tr_cont 입력 위반:\n"
        f"  실제: {call_log[1]!r} (KIS 정본 = 'N' 의무)\n"
        f"  KIS 정본: 다음 페이지 호출 = 'N' (Next)"
    )
    assert call_log[2] == "N", (
        f"\n사이클 91 H-1 위반 — 세 번째 호출 tr_cont 입력 위반:\n"
        f"  실제: {call_log[2]!r} (KIS 정본 = 'N' 의무)"
    )

    # 가드 4: 누적 순서 보존 (페이지 1 → 2 → 3 ticker 순서)
    tickers = [row["mksc_shrn_iscd"] for row in result]
    assert tickers[0] == "000000", (
        f"\n사이클 91 H-1 위반 — 페이지 1 첫 ticker 누락:\n"
        f"  실제: {tickers[:5]}..."
    )
    assert tickers[30] == "000030", (
        f"\n사이클 91 H-1 위반 — 페이지 2 첫 ticker 누락:\n"
        f"  실제: {tickers[28:35]}..."
    )
    assert tickers[60] == "000060", (
        f"\n사이클 91 H-1 위반 — 페이지 3 첫 ticker 누락:\n"
        f"  실제: {tickers[58:65]}..."
    )
