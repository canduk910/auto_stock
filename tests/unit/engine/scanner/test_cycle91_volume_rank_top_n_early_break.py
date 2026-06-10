"""사이클 91 H-2 — top_n 초과 시 조기 종료 효율 가드 (HIGH).

명세 (`_workspace/red/cycle91_volume_rank_pagination.md`):

- top_n=250 초과 시 추가 페이지 호출 skip (효율 가드)
- KIS Rate Limit 보호 + 응답 시간 단축

기대 동작 (Green):
- mock 5 페이지 × 100건 = 500 가용
- top_n=250 → 3 페이지째 300 누적 후 break
- 4/5 페이지 미호출 (효율 가드)
- 결과: 250건 반환 (`accumulated[:top_n]`)

Red 상태 (사이클 91): production 단일 호출 → 100건 반환 → FAIL (또는 페이징은 있으나
top_n 가드 미적용 시 500건 반환).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 97 Q53=A — `_fetch_volume_rank` 영역 전수 폐기. "
        "KIS fluctuation API (`_fetch_fluctuation`) 영역 신규 도입으로 영역 전환. "
        "사이클 91 top_n early break 영역 = 사이클 97 H-2 (fluctuation 페이징 top_n 절단) 가드로 영역 흡수. "
        "사이클 66 K-2 의미 전환 패턴 영속."
    ),
)
@pytest.mark.asyncio
async def test_h2_volume_rank_top_n_early_break_efficiency():
    """H-2: top_n=250 초과 시 추가 페이지 호출 skip (효율).

    검증 매트릭스:
    - mock 5 페이지 × 100건 가용
    - top_n=250 → 3 페이지째 (100+100+100=300) 누적 후 break
    - 4/5 페이지 미호출
    - 결과: 250건 반환 (accumulated[:250])

    영속 의무:
    - KIS Rate Limit 보호 (불필요 페이지 호출 차단)
    - 응답 시간 단축
    """
    from src.engine.scanner import _fetch_volume_rank

    # mock 5 페이지 응답 (각 100건)
    page_responses = [
        {
            "rt_cd": "0",
            "output": [
                {"mksc_shrn_iscd": f"{p * 100 + i:06d}",
                 "prdy_vol": 1_000_000 - p * 1_000 - i,
                 "stck_prpr": 50_000, "prdy_vrss": 1_000,
                 "prdt_type_cd": "300"}
                for i in range(100)
            ],
            "_response_headers": {"tr_cont": "M" if p < 4 else ""},
        }
        for p in range(5)
    ]

    call_count = {"value": 0}

    async def _fake_kis_get_quote(*args, **kwargs):
        page_idx = call_count["value"]
        call_count["value"] += 1
        if page_idx >= len(page_responses):
            return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}
        return page_responses[page_idx]

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        result = await _fetch_volume_rank(market="1", top_n=250)

    # 가드 1: 결과 카운트 = top_n=250 (slicing)
    assert len(result) == 250, (
        f"\n사이클 91 H-2 위반 — top_n slicing 결함:\n"
        f"  실제: {len(result)} (의무 = 250)\n"
        f"  Green 의무: accumulated[:top_n] 영역"
    )

    # 가드 2: 호출 횟수 ≤ 3 (3 페이지째 300 ≥ 250 누적 후 break)
    # KIS 호출 = 100 + 100 + 100 = 300 ≥ 250 → 4 페이지째 호출 skip
    assert call_count["value"] <= 3, (
        f"\n사이클 91 H-2 위반 — 효율 가드 결함:\n"
        f"  실제 호출: {call_count['value']} 회 (의무 ≤ 3)\n"
        f"  Green 의무: len(accumulated) >= top_n 시 break\n"
        f"  Rate Limit 보호: 불필요 페이지 호출 차단 의무"
    )
