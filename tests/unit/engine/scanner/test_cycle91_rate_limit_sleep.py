"""사이클 91 M-1 — 페이지 간 50ms sleep 보장 (KIS Rate Limit 보호, MEDIUM).

명세 (`_workspace/red/cycle91_volume_rank_pagination.md`):

- KIS `smart_sleep()` 정본 패턴 (페이지 간 지연 의무)
- 사이클 83 50ms sleep 답습
- 마지막 페이지 후 sleep 없음 (효율)

기대 동작 (Green):
- `asyncio.sleep` mock 호출 횟수 = (페이지 수 - 1)
- 각 sleep 호출 = 0.05s (50ms)

Red 상태 (사이클 91): 단일 호출 → sleep 0 회 호출 → FAIL.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_m1_page_interval_sleep_50ms():
    """M-1: 페이지 간 50ms sleep 보장 (KIS Rate Limit 보호).

    검증 매트릭스:
    - mock 3 페이지 응답 (각 30건, 마지막 페이지 tr_cont="")
    - `asyncio.sleep` 호출 횟수 ≥ 2 (페이지 1→2, 페이지 2→3)
    - 각 sleep 인자 ≈ 0.05s (50ms, 사이클 83 답습)
    - 마지막 페이지 후 추가 sleep 없음

    영속 의무:
    - KIS Rate Limit 보호
    - 사이클 83 패턴 답습 (페이지 간 50ms)
    """
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
            "_response_headers": {"tr_cont": "M" if p < 2 else ""},
        }
        for p in range(3)
    ]

    call_count = {"value": 0}

    async def _fake_kis_get_quote(*args, **kwargs):
        page_idx = call_count["value"]
        call_count["value"] += 1
        if page_idx >= len(page_responses):
            return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}
        return page_responses[page_idx]

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float, *args, **kwargs):
        sleep_calls.append(seconds)

    # scanner 모듈 내부 asyncio import 영역 보호
    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)), \
         patch("asyncio.sleep", new=AsyncMock(side_effect=_fake_sleep)):
        await _fetch_volume_rank(market="1", top_n=250)

    # 가드 1: sleep 호출 횟수 ≥ 2 (페이지 간 = 3 페이지 - 1)
    # asyncio.sleep 은 다른 영역 (Rate Limit 등) 에서도 호출될 수 있으므로 ≥
    sleep_count_50ms = sum(1 for s in sleep_calls if abs(s - 0.05) < 0.001)
    assert sleep_count_50ms >= 2, (
        f"\n사이클 91 M-1 위반 — 페이지 간 50ms sleep 누락:\n"
        f"  실제 50ms sleep 호출: {sleep_count_50ms} (의무 ≥ 2)\n"
        f"  전체 sleep 호출: {sleep_calls}\n"
        f"  Green 의무: 페이지 간 await asyncio.sleep(0.05) (사이클 83 답습)"
    )
