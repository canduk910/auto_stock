"""사이클 94 H-2 — KIS volume_rank "0000" 페이징 500 ticker 누적 검증 (HIGH).

명세 (`_workspace/red/cycle94_fid_input_iscd_fix.md`):

- KIS 정본 (`FID_INPUT_ISCD = "0000"`) = 페이징 17+ 페이지 정상 작동
- 사이클 91 페이징 누적 코드 영역 영속 (tr_cont == "M" → "N" 누적)
- 사이클 94 시정 = 단일 호출 (`"0000"`) + 페이징 누적 → 500+ ticker

기대 동작 (Green, backend-dev 인계):
- `_fetch_volume_rank(market="all", top_n=500, max_pages=17)` 호출
- 17 페이지 mock 응답 (각 30건 = 510 누적)
- top_n=500 도달 시 조기 종료 또는 마지막 페이지 종료
- 결과 ≥ 500 ticker

Red 상태 (사이클 94): production 코드 `"0001"`/`"0002"` 호출 → KIS 30건 한도 →
30 ticker 만 반환 → FAIL.

영속 의무:
- KIS 정본 페이징 패턴 (사이클 91 영역 영속)
- max_pages=17 (사이클 91 max_pages=15 → 사이클 94 500 ticker 영역 확장)
- 50ms sleep Rate Limit 영속 (사이클 83 답습)
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h2_pagination_accumulates_500_tickers():
    """H-2: `_fetch_volume_rank(market="all", top_n=500)` 가 17 페이지 누적 500+ ticker 반환.

    검증 매트릭스:
    - mock 17 페이지 응답 (각 30건 = 510 누적)
    - 페이지 1~16: `tr_cont = "M"` (다음 페이지 존재)
    - 페이지 17: `tr_cont = ""` (마지막 페이지)
    - 결과 ≥ 500 ticker (top_n cap 영속)

    Red 상태 (사이클 94): production `_MARKET_INPUT_ISCD` 가 `"0001"`/`"0002"` 영속 →
    KIS 단일 페이지 30건 한도 (업종코드 페이징 미지원) → 30 ticker 만 반환 → FAIL.

    Green (backend-dev):
    - `_MARKET_INPUT_ISCD = {"all": "0000"}` 단일화 (H-1)
    - `_fetch_volume_rank(market="all", ...)` 시그너처 영속
    - KIS "0000" 영역 = 페이징 17+ 페이지 정상 → 500+ ticker 누적 → PASS

    영속 의무:
    - KIS MCP 정본 페이징 패턴 영속
    - 사이클 91 페이징 코드 영역 변경 0 (max_pages 만 확장 가능)
    """
    from src.engine.scanner import _fetch_volume_rank

    # 17 페이지 mock — 각 30건 = 510 누적
    page_responses = []
    for page_idx in range(17):
        tr_cont_response = "M" if page_idx < 16 else ""  # 마지막 페이지만 종료
        output = [
            {
                "mksc_shrn_iscd": f"{(page_idx * 30 + i):06d}",
                "prdy_vol": 1_000_000 - page_idx * 10_000 - i,
                "stck_prpr": 50_000,
                "prdy_vrss": 1_000,
                "prdt_type_cd": "300",
            }
            for i in range(30)
        ]
        page_responses.append({
            "rt_cd": "0",
            "output": output,
            "_response_headers": {"tr_cont": tr_cont_response},
        })

    call_log: list[dict] = []

    async def _fake_kis_get_quote(*args, **kwargs):
        tr_cont = kwargs.get("tr_cont", "")
        call_log.append({"tr_cont": tr_cont, "params": kwargs.get("params", {})})
        page_idx = len(call_log) - 1
        if page_idx >= len(page_responses):
            return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}
        return page_responses[page_idx]

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        result = await _fetch_volume_rank(market="all", top_n=500, max_pages=17)

    # 가드 1: 결과 ≥ 500 ticker (사이클 94 핵심 행위)
    assert len(result) >= 500, (
        f"\n사이클 94 H-2 위반 — 500 ticker 누적 실패:\n"
        f"  기대: ≥ 500 (KIS 정본 '0000' 영역 17+ 페이징)\n"
        f"  실제: {len(result)}\n"
        f"  호출 횟수: {len(call_log)}\n"
        f"  결함 인과:\n"
        f"    - sm사이클 89/91 silent: '0001'/'0002' 업종코드 = 30건 한도\n"
        f"    - 사이클 94 시정: '0000' 전체 영역 = 페이징 17+ 페이지 정상\n"
        f"  Green 의무: _MARKET_INPUT_ISCD 단일화 + _fetch_volume_rank(market='all')"
    )

    # 가드 2: 첫 호출 input tr_cont = "" + 모든 페이지 호출 (페이징 누적)
    assert call_log[0]["tr_cont"] == "", (
        f"\n사이클 94 H-2 위반 — 첫 호출 tr_cont 결함:\n"
        f"  기대: '' (KIS 표준 - 빈 문자열 = 첫 페이지)\n"
        f"  실제: '{call_log[0]['tr_cont']}'"
    )

    # 가드 3: 페이지 2 이후 input tr_cont = "N" (KIS Next)
    if len(call_log) > 1:
        assert call_log[1]["tr_cont"] == "N", (
            f"\n사이클 94 H-2 위반 — 페이지 2 tr_cont 결함:\n"
            f"  기대: 'N' (KIS 표준 - 다음 페이지)\n"
            f"  실제: '{call_log[1]['tr_cont']}'"
        )

    # 가드 4: FID_INPUT_ISCD = "0000" 사용 영속 (KIS 정본 영역)
    first_call_params = call_log[0]["params"]
    fid_input_iscd = first_call_params.get("FID_INPUT_ISCD", "")
    assert fid_input_iscd == "0000", (
        f"\n사이클 94 H-2 위반 — FID_INPUT_ISCD 결함:\n"
        f"  기대: '0000' (KIS 정본 전체 영역)\n"
        f"  실제: '{fid_input_iscd}'\n"
        f"  KIS MCP 정본 영속: '0000' = 전체 / '0001'·'0002' = 업종코드 (30건 한도)"
    )
