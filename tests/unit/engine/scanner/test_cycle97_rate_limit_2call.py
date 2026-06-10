"""사이클 97 M-2 — Rate Limit 50ms sleep 영속 + 2회 분리 호출 영역 (MEDIUM).

명세 (`_workspace/red/cycle97_fluctuation_api_replacement.md`):

- 사이클 83 Rate Limit 50ms sleep 영속 (KIS Rate Limit 20/s)
- 사이클 89/96 2회 분리 호출 영속
- 사이클 97 영역 = fluctuation API 신규 도입 후에도 영속

기대 동작 (Green, backend-dev 인계):
- `_fetch_fluctuation` 내부 페이지 사이 `await asyncio.sleep(0.05)` 호출 영속
- 호출 횟수 = (페이지 수 - 1) (마지막 페이지 후 sleep 없음, 사이클 83 답습)

Red 상태 (사이클 97): `_fetch_fluctuation` 미존재 → ImportError → FAIL.

영속 의무:
- 사이클 83 Rate Limit 50ms 패턴 영속
- KIS Rate Limit 20/s 영구 정합
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 99 — 페이지 사이 sleep 영역 영구 폐기 (단일 호출 = sleep 불요). "
        "사이클 97 시점 Rate Limit sleep 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습). "
        "KIS API 페이징 미지원 영구 확정 → _asyncio.sleep(0.05) 페이징 영역 영구 폐기."
    ),
)
@pytest.mark.asyncio
async def test_m2_rate_limit_sleep_between_pages():
    """M-2.a: `_fetch_fluctuation` 페이지 사이 50ms sleep 영속.

    검증 매트릭스:
    - 3 페이지 mock (tr_cont M, M, "")
    - `asyncio.sleep` patch → 호출 인자 수집
    - sleep 호출 ≥ 2회 (페이지 1 → 2, 2 → 3 사이)
    - 모든 sleep 인자 = 0.05 (사이클 83 답습)

    Red 상태 (사이클 97): `_fetch_fluctuation` 미존재 → FAIL.
    """
    try:
        from src.engine.scanner import _fetch_fluctuation
    except ImportError:
        pytest.fail(
            "\n사이클 97 M-2.a Red 상태 — `_fetch_fluctuation` 함수 부재"
        )

    page_responses = [
        {
            "rt_cd": "0",
            "output": [{"stck_shrn_iscd": f"{i:06d}", "stck_prpr": "50000",
                        "prdy_vrss": "1000", "prdy_ctrt": "1.0",
                        "acml_vol": "1000000", "prdt_type_cd": "300"}
                       for i in range(30)],
            "_response_headers": {"tr_cont": "M"},
        },
        {
            "rt_cd": "0",
            "output": [{"stck_shrn_iscd": f"{i + 30:06d}", "stck_prpr": "50000",
                        "prdy_vrss": "1000", "prdy_ctrt": "1.0",
                        "acml_vol": "1000000", "prdt_type_cd": "300"}
                       for i in range(30)],
            "_response_headers": {"tr_cont": "M"},
        },
        {
            "rt_cd": "0",
            "output": [{"stck_shrn_iscd": f"{i + 60:06d}", "stck_prpr": "50000",
                        "prdy_vrss": "1000", "prdy_ctrt": "1.0",
                        "acml_vol": "1000000", "prdt_type_cd": "300"}
                       for i in range(30)],
            "_response_headers": {"tr_cont": ""},
        },
    ]

    call_idx = [0]

    async def _fake_kis_get_quote(*args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        if idx >= len(page_responses):
            return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}
        return page_responses[idx]

    sleep_calls: list[float] = []

    real_sleep = __import__("asyncio").sleep

    async def _capture_sleep(delay: float, *args, **kwargs):
        sleep_calls.append(delay)
        # 실제 sleep 은 매우 짧게 (테스트 속도 영속)
        await real_sleep(0)

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)), \
         patch("src.engine.scanner._asyncio.sleep", side_effect=_capture_sleep), \
         patch("asyncio.sleep", side_effect=_capture_sleep):
        # 사이클 97: max_pages 3 으로 제한 (top_n 도 충분히 크게 = top_n=500 → 90 누적)
        await _fetch_fluctuation(market="kospi", top_n=500, max_pages=3)

    # 가드: 50ms sleep 호출 ≥ 2회 (페이지 1→2, 2→3)
    fifty_ms_sleeps = [s for s in sleep_calls if s == 0.05]
    assert len(fifty_ms_sleeps) >= 2, (
        f"\n사이클 97 M-2.a 위반 — 50ms sleep 호출 누락:\n"
        f"  기대: ≥2회 (3 페이지 = 2 sleep)\n"
        f"  실제 50ms sleep: {len(fifty_ms_sleeps)}회\n"
        f"  전체 sleep 인자: {sleep_calls}\n"
        f"  사이클 83 Rate Limit 50ms 패턴 영속 의무"
    )


@pytest.mark.asyncio
async def test_m2_two_separated_market_calls():
    """M-2.b: `fetch_top_500_universe` 2회 분리 호출 영역 영속 (KOSPI + KOSDAQ).

    검증 매트릭스:
    - `_fetch_fluctuation` mock 호출 수집
    - 호출 횟수 = 정확 2회 (각각 market="kospi" / "kosdaq")
    - 호출 순서 영속 (KOSPI 먼저 → KOSDAQ)

    Red 상태 (사이클 97): `_fetch_fluctuation` 미존재 → FAIL.
    """
    try:
        import src.engine.scanner as scanner_mod
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 97 M-2.b Red 상태 — `fetch_top_500_universe` 함수 부재"
        )

    if not hasattr(scanner_mod, "_fetch_fluctuation"):
        pytest.fail(
            "\n사이클 97 M-2.b Red 상태 — `_fetch_fluctuation` 함수 부재"
        )

    call_log: list[str] = []

    async def _fake_fetch_fluctuation(market: str, top_n: int = 250):
        call_log.append(market)
        return []

    with patch("src.engine.scanner._fetch_fluctuation",
               new=AsyncMock(side_effect=_fake_fetch_fluctuation)):
        await fetch_top_500_universe()

    assert call_log == ["kospi", "kosdaq"], (
        f"\n사이클 97 M-2.b 위반 — 2회 분리 호출 영역 결함:\n"
        f"  기대: ['kospi', 'kosdaq'] (KIS API 영역 분리 순서)\n"
        f"  실제: {call_log}"
    )
