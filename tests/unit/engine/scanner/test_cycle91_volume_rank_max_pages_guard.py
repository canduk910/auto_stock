"""사이클 91 H-3 — max_pages=15 무한 루프 차단 가드 (HIGH).

명세 (`_workspace/red/cycle91_volume_rank_pagination.md`):

- KIS API 결함 또는 잘못된 응답 시 `tr_cont == "M"` 무한 반복 가능
- max_pages=15 → KIS LMS chain 차단 영구 가드
- KIS 표준 한도 영역 + 안전 마진 (KOSPI ~2,500 종목 / 30건/페이지 = 약 80 페이지 이상 가능하나
  실제 운영 영역은 top_n 가드로 조기 종료)

기대 동작 (Green):
- mock 무한 페이징 (tr_cont 항상 "M" + output 각 5건)
- top_n=250 미만 누적 (15 페이지 × 5 = 75 ≤ 250) → max_pages 도달
- 15 회 호출 후 중단
- 결과: 75건 반환

Red 상태 (사이클 91): 단일 호출 → 5건 반환 → FAIL (또는 max_pages 가드 없으면 무한 루프).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h3_volume_rank_max_pages_infinite_loop_guard():
    """H-3: max_pages=15 무한 루프 차단 가드.

    검증 매트릭스:
    - mock 무한 응답: tr_cont 항상 "M" + 각 5건
    - top_n=250 미만 누적 (15 × 5 = 75 ≤ 250)
    - max_pages=15 도달 후 break (KIS LMS chain 차단)
    - 결과: 75건 반환 (15 페이지 × 5)
    - 호출 횟수 = 15 (max_pages 정확 도달)

    영속 의무:
    - KIS LMS chain 차단 (사이클 17 OPSP0002 답습)
    - 무한 루프 영구 가드
    """
    from src.engine.scanner import _fetch_volume_rank

    call_count = {"value": 0}

    async def _fake_kis_get_quote(*args, **kwargs):
        page_idx = call_count["value"]
        call_count["value"] += 1
        # 무한 페이징 시나리오 — tr_cont 항상 "M" + 각 5건 (top_n=250 미달)
        return {
            "rt_cd": "0",
            "output": [
                {"mksc_shrn_iscd": f"{page_idx * 5 + i:06d}",
                 "prdy_vol": 1_000_000,
                 "stck_prpr": 50_000, "prdy_vrss": 1_000,
                 "prdt_type_cd": "300"}
                for i in range(5)
            ],
            "_response_headers": {"tr_cont": "M"},  # 항상 "M" — 무한 페이징
        }

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        # max_pages=15 디폴트 의무 (production 시그너처 영속)
        result = await _fetch_volume_rank(market="1", top_n=250)

    # 가드 1: 호출 횟수 = 15 (max_pages 정확 도달)
    assert call_count["value"] == 15, (
        f"\n사이클 91 H-3 위반 — max_pages 가드 결함:\n"
        f"  실제 호출: {call_count['value']} 회 (의무 = 15)\n"
        f"  Green 의무: max_pages=15 디폴트 + range(max_pages) 루프\n"
        f"  KIS LMS chain 차단 (무한 루프 영구 가드)"
    )

    # 가드 2: 결과 = 75건 (15 × 5)
    assert len(result) == 75, (
        f"\n사이클 91 H-3 위반 — 누적 결함:\n"
        f"  실제: {len(result)} (의무 = 75 = 15 × 5)\n"
        f"  Green 의무: 모든 페이지 output 누적"
    )
