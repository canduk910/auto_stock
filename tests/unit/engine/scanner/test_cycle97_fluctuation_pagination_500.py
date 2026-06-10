"""사이클 97 H-2 — `_fetch_fluctuation` 페이징 누적 500 ticker 검증 (HIGH).

명세 (`_workspace/red/cycle97_fluctuation_api_replacement.md`):

- KIS fluctuation API 페이징 응답 의무 (정본 `tr_cont == "M"` 패턴)
- 사이클 89/91/94/96 단일 호출 silent 결함 영구 폐기
- 사이클 97 시정: 2회 분리 호출 (KOSPI + KOSDAQ) × 페이징 누적

기대 동작 (Green, backend-dev 인계):
- `fetch_top_500_universe()` 호출 → `_fetch_fluctuation(market="kospi")` + `_fetch_fluctuation(market="kosdaq")` 2회 분리 호출
- 각 호출 내부 페이징 누적 (tr_cont "" → "N" → "N" → "")
- 합 500 ticker 적재 (KOSPI 250 + KOSDAQ 250)

Red 상태 (사이클 97): `_fetch_fluctuation` 신규 함수 미존재 → ImportError → FAIL.

영속 의무:
- KIS 정본 페이징 패턴 영속 (사이클 91 답습)
- 사이클 89 분리 호출 영속 (사이클 96 영역 복원 영속)
- 응답 키 `stck_shrn_iscd` 영역 (volume_rank `mksc_shrn_iscd` 와 영역 차별)
- 매매 안전성 영향 0 (사이클 38 명문화 영속)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h2_fluctuation_pagination_accumulates_kospi():
    """H-2.a: `_fetch_fluctuation(market="kospi")` 페이징 누적 9 페이지 × 30 = 270 → top_n=250 절단.

    검증 매트릭스:
    - mock 9 페이지 (각 30건 = 270 누적)
    - 페이지 1~8: `tr_cont = "M"` → 다음 페이지 호출 의무
    - 페이지 9: `tr_cont = ""` → 종료 (top_n=250 도달 시 조기 종료 영역)
    - 결과: 250건 누적 (top_n 절단)

    Red 상태 (사이클 97): `_fetch_fluctuation` 신규 함수 미존재 → ImportError → FAIL.

    Green (backend-dev): 신규 함수 도입 + 페이징 루프 → PASS.
    """
    try:
        from src.engine.scanner import _fetch_fluctuation
    except ImportError:
        pytest.fail(
            "\n사이클 97 H-2.a Red 상태 — `_fetch_fluctuation` 함수 부재.\n"
            "  Green (backend-dev): scanner.py 신규 함수 도입 의무.\n"
            "    `async def _fetch_fluctuation(market, top_n=250, max_pages=17) -> list[dict]`"
        )

    # mock 9 페이지 응답 (top_n=250 초과 마진)
    def _build_page(start: int, has_next: bool) -> dict:
        return {
            "rt_cd": "0",
            "output": [
                {
                    "stck_shrn_iscd": f"{start + i:06d}",  # KIS fluctuation 정본 응답 키
                    "stck_prpr": "50000",
                    "prdy_vrss": "1000",
                    "prdy_ctrt": "2.0",
                    "acml_vol": str(1_000_000 + i),
                    "prdt_type_cd": "300",
                }
                for i in range(30)
            ],
            "_response_headers": {"tr_cont": "M" if has_next else ""},
        }

    page_responses = [_build_page(i * 30, has_next=(i < 8)) for i in range(9)]

    call_log: list[str] = []

    async def _fake_kis_get_quote(*args, **kwargs):
        tr_cont = kwargs.get("tr_cont", "MISSING_KWARG")
        call_log.append(tr_cont)
        page_idx = len(call_log) - 1
        if page_idx >= len(page_responses):
            return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}
        return page_responses[page_idx]

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        result = await _fetch_fluctuation(market="kospi", top_n=250)

    # 가드 1: top_n 절단 — 누적 270 → 250
    assert len(result) == 250, (
        f"\n사이클 97 H-2.a 위반 — top_n=250 절단 영역 결함:\n"
        f"  실제: {len(result)}건 (top_n=250 절단 의무)\n"
        f"  KIS 정본: fid_input_cnt_1 사용자 제어 + accumulated[:top_n]"
    )

    # 가드 2: tr_cont 입력 순서 (KIS 정본)
    assert call_log[0] == "", (
        f"\n사이클 97 H-2.a 위반 — 첫 호출 tr_cont 위반:\n"
        f"  실제: {call_log[0]!r} (KIS 정본 = '' 의무)"
    )
    if len(call_log) > 1:
        assert call_log[1] == "N", (
            f"\n사이클 97 H-2.a 위반 — 두 번째 호출 tr_cont 위반:\n"
            f"  실제: {call_log[1]!r} (KIS 정본 = 'N' 의무)"
        )


@pytest.mark.asyncio
async def test_h2_fetch_top_500_universe_two_market_call():
    """H-2.b: `fetch_top_500_universe()` 가 `_fetch_fluctuation` 2회 호출 (KOSPI + KOSDAQ).

    검증 매트릭스:
    - mock 으로 `_fetch_fluctuation` 호출 인자 수집
    - 호출 횟수 = 정확 2회
    - 호출 인자 `market` = {"kospi", "kosdaq"} 양쪽 포함

    Red 상태 (사이클 97): `_fetch_fluctuation` 미존재 → 신규 함수 patch 실패 → FAIL.

    Green (backend-dev): `fetch_top_500_universe` 본체 = `_fetch_fluctuation(market="kospi")` +
                         `_fetch_fluctuation(market="kosdaq")` 양쪽 호출 → PASS.

    영속 의무:
    - 사이클 89 분리 호출 (사이클 96 영역 복원 영속)
    - 코스닥 변동성 영역 보존 (6 전략 균형)
    """
    try:
        import src.engine.scanner as scanner_mod
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 97 H-2.b Red 상태 — `fetch_top_500_universe` 함수 부재"
        )

    if not hasattr(scanner_mod, "_fetch_fluctuation"):
        pytest.fail(
            "\n사이클 97 H-2.b Red 상태 — `_fetch_fluctuation` 함수 부재.\n"
            "  Green (backend-dev): scanner.py 신규 함수 도입 + fetch_top_500_universe 본체 전환 의무."
        )

    call_markets: list[str] = []

    async def _fake_fetch_fluctuation(market: str, top_n: int = 250):
        call_markets.append(market)
        return []

    with patch("src.engine.scanner._fetch_fluctuation",
               new=AsyncMock(side_effect=_fake_fetch_fluctuation)):
        await fetch_top_500_universe()

    # 가드 1: 호출 횟수 정확 2회
    assert len(call_markets) == 2, (
        f"\n사이클 97 H-2.b 위반 — `_fetch_fluctuation` 호출 횟수 결함:\n"
        f"  기대: 2회 (KOSPI + KOSDAQ)\n"
        f"  실제: {len(call_markets)}회\n"
        f"  호출 인자: {call_markets}\n"
        f"  사이클 96 영역 복원 영속"
    )

    # 가드 2: market=kospi 호출 포함
    assert "kospi" in call_markets, (
        f"\n사이클 97 H-2.b 위반 — KOSPI 호출 누락:\n"
        f"  호출 인자: {call_markets}"
    )

    # 가드 3: market=kosdaq 호출 포함
    assert "kosdaq" in call_markets, (
        f"\n사이클 97 H-2.b 위반 — KOSDAQ 호출 누락:\n"
        f"  호출 인자: {call_markets}"
    )
