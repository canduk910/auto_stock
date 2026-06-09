"""사이클 91 M-3 — `_response_headers` 키 없는 legacy mock 응답 호환 (MEDIUM).

명세 (`_workspace/red/cycle91_volume_rank_pagination.md`):

- 사이클 91 시정 후에도 기존 cycle89 mock (`_response_headers` 키 부재) 호환 의무
- `tr_cont` 헤더 없는 응답 = 단일 호출 + graceful 종료 (legacy)

기대 동작 (Green):
- mock 응답에 `_response_headers` 키 부재
- `data.get("_response_headers", {}).get("tr_cont", "")` → 빈 문자열 → 종료
- 첫 호출 결과만 반환 (호출 횟수 = 1)

Red 상태 (사이클 91): 사이클 89 mock 영역 변경 0 영속 가드. Green 후에도 legacy 호환.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_m3_no_response_headers_key_graceful_terminate():
    """M-3: `_response_headers` 키 없는 mock 응답 = 단일 호출 + graceful 종료.

    검증 매트릭스:
    - mock 응답: {"rt_cd": "0", "output": [30건]} — `_response_headers` 키 없음
    - 결과: 첫 호출 결과만 반환 (30건)
    - 호출 횟수 = 1 (다음 페이지 호출 안 함)

    영속 의무:
    - 사이클 89 mock 영역 호환 (기존 테스트 회귀 0)
    - graceful fallback (`data.get("_response_headers", {}).get("tr_cont", "")` 빈 문자열)
    """
    from src.engine.scanner import _fetch_volume_rank

    legacy_response = {
        "rt_cd": "0",
        "output": [
            {"mksc_shrn_iscd": f"{i:06d}",
             "prdy_vol": 1_000_000 + i, "stck_prpr": 50_000,
             "prdy_vrss": 1_000, "prdt_type_cd": "300"}
            for i in range(30)
        ],
        # 의도적 부재: "_response_headers" 키 없음 (legacy mock 패턴)
    }

    call_count = {"value": 0}

    async def _fake_kis_get_quote(*args, **kwargs):
        call_count["value"] += 1
        return legacy_response

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        result = await _fetch_volume_rank(market="1", top_n=250)

    # 가드 1: 호출 횟수 = 1 (legacy 응답은 단일 호출 후 종료)
    assert call_count["value"] == 1, (
        f"\n사이클 91 M-3 위반 — legacy 응답 무한 루프 결함:\n"
        f"  실제 호출: {call_count['value']} (의무 = 1)\n"
        f"  Green 의무: `_response_headers` 키 부재 시 graceful 종료\n"
        f"  패턴: data.get('_response_headers', {{}}).get('tr_cont', '') → '' → break"
    )

    # 가드 2: 결과 = 30건 (첫 호출 결과)
    assert len(result) == 30, (
        f"\n사이클 91 M-3 위반 — 첫 호출 결과 누락:\n"
        f"  실제: {len(result)} (의무 = 30)\n"
        f"  Green 의무: legacy 응답 호환 보존"
    )
