"""사이클 91 M-2 — 중간 페이지 KIS 실패 시 graceful 누적분 반환 (MEDIUM).

명세 (`_workspace/red/cycle91_volume_rank_pagination.md`):

- 사이클 89 graceful 패턴 영속 (`KisApiError` → 누적분 반환)
- 페이지 1+2 성공 + 페이지 3 실패 → 페이지 1+2 데이터 보존 반환

기대 동작 (Green):
- mock 페이지 1 성공 (30건) + 페이지 2 성공 (30건) + 페이지 3 `KisApiError` raise
- break + 누적 60건 반환
- 호출 횟수 = 3 (실패 페이지까지)

Red 상태 (사이클 91): 단일 호출 → 첫 페이지 30건 또는 0건 → FAIL (페이징 영역 미존재).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_m2_graceful_kis_error_mid_pagination():
    """M-2: 중간 페이지 KIS 실패 시 graceful 누적분 반환.

    검증 매트릭스:
    - mock 페이지 1 성공 (30건)
    - mock 페이지 2 성공 (30건)
    - mock 페이지 3 `KisApiError` raise
    - 결과: 60건 누적 반환 (페이지 1+2 데이터 보존)
    - 호출 횟수 = 3 (실패 페이지까지 시도)

    영속 의무:
    - 사이클 89 graceful 패턴 답습
    - try/except `KisApiError` 분기 영속
    """
    from src.api.base import KisApiError
    from src.engine.scanner import _fetch_volume_rank

    page_responses = [
        {
            "rt_cd": "0",
            "output": [
                {"mksc_shrn_iscd": f"{p * 30 + i:06d}",
                 "prdy_vol": 1_000_000, "stck_prpr": 50_000,
                 "prdy_vrss": 1_000, "prdt_type_cd": "300"}
                for i in range(30)
            ],
            "_response_headers": {"tr_cont": "M"},
        }
        for p in range(2)
    ]

    call_count = {"value": 0}

    async def _fake_kis_get_quote(*args, **kwargs):
        page_idx = call_count["value"]
        call_count["value"] += 1
        if page_idx < len(page_responses):
            return page_responses[page_idx]
        # 페이지 3: KisApiError raise
        raise KisApiError("1", "EGW00500", "KIS 일시 장애 (테스트)")

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        result = await _fetch_volume_rank(market="1", top_n=250)

    # 가드 1: 누적 결과 = 60 (페이지 1+2 보존)
    assert len(result) == 60, (
        f"\n사이클 91 M-2 위반 — graceful 누적분 반환 결함:\n"
        f"  실제: {len(result)} (의무 = 60 = 페이지 1+2 데이터 보존)\n"
        f"  Green 의무: except KisApiError → break + return accumulated"
    )

    # 가드 2: 호출 횟수 = 3 (실패 페이지까지 시도)
    assert call_count["value"] == 3, (
        f"\n사이클 91 M-2 위반 — 실패 페이지 시도 누락:\n"
        f"  실제 호출: {call_count['value']} (의무 = 3)\n"
        f"  Green 의무: 페이지 3 시도 후 KisApiError except → break"
    )
