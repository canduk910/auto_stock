"""사이클 101 G-MC1 — market_cap (FHPST01740000) tr_cont "M" → "N" 페이징 누적 (HIGH).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**KIS 156 API 중 유일 페이징 지원 (사이클 100 Phase 1 영속)**:
- TR_ID `"FHPST01740000"` + URL `/uapi/domestic-stock/v1/ranking/market-cap`
- 정본 (chk_market_cap.py + market_cap.py main 호출 영역 L107~120): tr_cont "M" → 재귀 호출 + "N" 영속
- `_fetch_market_cap_page(market, max_pages=100)` 신규 함수 영역

검증 매트릭스 (사용자 결정 Q70=A + domain-expert A1/A3 영속):
- G-MC1-A: `_fetch_market_cap_page` 함수 영속 (Red = 함수 부재 → ImportError 또는 AttributeError)
- G-MC1-B: 다중 페이지 mock — tr_cont "M" 3회 + "N" 1회 → 30 × 3 + 30 = 120 ticker 누적
- G-MC1-C: max_pages 안전 한도 (무한 루프 차단, 사이클 91 답습)

Red 상태: 신규 함수 부재 → import 실패 또는 호출 시 0건.
Green (backend-dev): `_fetch_market_cap_page` 구현 + 페이징 누적.

영속 의무:
- 사이클 98 G-DOC1 (chk_market_cap.py main 정본 인용 의무 — 사이클 101 G-DOC1 별도 가드)
- 사이클 88 G-REJECT graceful (rt_cd != "0" → continue)
- 사이클 91 max_pages 무한 루프 차단 패턴 답습
- 매매 hot path 영향 0 (scanner 단계 영역 한정)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def test_g_mc1_a_function_exists() -> None:
    """G-MC1-A: `_fetch_market_cap_page` 함수 영속 (HIGH).

    Red 상태: 신규 함수 부재 → AttributeError 또는 ImportError.
    Green (backend-dev): src/engine/scanner.py 에 신규 함수 정의 의무.
    """
    from src.engine import scanner

    assert hasattr(scanner, "_fetch_market_cap_page"), (
        "\n사이클 101 G-MC1-A Red 상태 — `_fetch_market_cap_page` 함수 부재.\n"
        "  Green (backend-dev): src/engine/scanner.py 에 함수 영속 의무 (사이클 101).\n"
        "  KIS 정본: FHPST01740000 + /uapi/domestic-stock/v1/ranking/market-cap\n"
        "  명세 영속: _workspace/red/cycle101_market_cap_full_universe_load.md"
    )


@pytest.mark.asyncio
async def test_g_mc1_b_pagination_accumulates_multiple_pages() -> None:
    """G-MC1-B: tr_cont "M" 페이징 누적 (HIGH).

    검증 매트릭스:
    - mock kis_get_quote 응답을 4회 호출로 가정 (M/M/M/N)
    - 각 페이지 30 ticker → 120 ticker 누적 영속
    - tr_cont "N" 도달 시 페이징 종료 (정본 L107~120 영속)

    Red 상태: 함수 부재 또는 첫 페이지만 반환 → 30 또는 0 ticker.
    Green (backend-dev): tr_cont "M" → "N" 재귀 호출 영속.
    """
    from src.engine import scanner

    if not hasattr(scanner, "_fetch_market_cap_page"):
        pytest.fail(
            "사이클 101 G-MC1-B Red — `_fetch_market_cap_page` 부재 (G-MC1-A 영속).\n"
            "  Green: scanner.py 신규 함수 의무"
        )

    # mock: 4페이지 응답 (M/M/M/N)
    pages = []
    for page_idx in range(4):
        rows = [
            {"mksc_shrn_iscd": f"{page_idx * 30 + i:06d}"} for i in range(30)
        ]
        pages.append(rows)

    call_idx = {"i": 0}

    async def fake_kis_get_quote(url, tr_id, params=None, tr_cont="", **kwargs):
        idx = call_idx["i"]
        call_idx["i"] += 1
        # 마지막 4번째 응답 = "N", 그 이전 = "M"
        next_tr_cont = "N" if idx == 3 else "M"
        return {
            "rt_cd": "0",
            "msg_cd": "MCA00000",
            "msg1": "정상처리",
            "output": pages[idx],
            "tr_cont": next_tr_cont,
        }

    with patch(
        "src.api.base.kis_get_quote",
        new=AsyncMock(side_effect=fake_kis_get_quote),
    ):
        result = await scanner._fetch_market_cap_page(
            market="kospi", max_pages=100
        )

    assert isinstance(result, list), (
        "\n사이클 101 G-MC1-B 위반 — 반환 타입 list 아님.\n"
        f"  실제: {type(result)}\n"
        "  기대: list[dict]"
    )

    assert len(result) == 120, (
        f"\n사이클 101 G-MC1-B 위반 — 페이징 누적 실패:\n"
        f"  기대: 120 ticker (4페이지 × 30)\n"
        f"  실제: {len(result)} ticker\n"
        f"  Red 결함 가설: tr_cont 'M' 분기 미구현 또는 첫 페이지만 반환\n"
        f"  Green (backend-dev): KIS 정본 L107~120 답습 (M → 재귀 + N → 종료)"
    )


@pytest.mark.asyncio
async def test_g_mc1_c_max_pages_guards_infinite_loop() -> None:
    """G-MC1-C: max_pages 안전 한도 (무한 루프 차단, 사이클 91 답습) (HIGH).

    검증 매트릭스:
    - mock 가 영구 "M" 반환 (이론적 무한 페이징)
    - max_pages 도달 시 강제 종료 보장
    - 누적 ticker = max_pages × 30 (overflow 0)

    Red 상태: 함수 부재 또는 max_pages 가드 부재 → 무한 루프 가능.
    Green (backend-dev): max_pages 도달 시 break 영속.
    """
    from src.engine import scanner

    if not hasattr(scanner, "_fetch_market_cap_page"):
        pytest.fail(
            "사이클 101 G-MC1-C Red — `_fetch_market_cap_page` 부재 (G-MC1-A 영속).\n"
            "  Green: scanner.py 신규 함수 의무"
        )

    call_count = {"n": 0}

    async def fake_kis_get_quote(url, tr_id, params=None, tr_cont="", **kwargs):
        call_count["n"] += 1
        return {
            "rt_cd": "0",
            "msg_cd": "MCA00000",
            "msg1": "정상처리",
            "output": [
                {"mksc_shrn_iscd": f"{call_count['n']:06d}"}
            ],
            "tr_cont": "M",  # 영구 M (무한 페이징 가정)
        }

    with patch(
        "src.api.base.kis_get_quote",
        new=AsyncMock(side_effect=fake_kis_get_quote),
    ):
        # max_pages=5 강제 → 6번째 호출 차단 의무
        result = await scanner._fetch_market_cap_page(
            market="kospi", max_pages=5
        )

    assert call_count["n"] <= 5, (
        f"\n사이클 101 G-MC1-C 위반 — max_pages 한도 초과:\n"
        f"  max_pages=5 → 호출 횟수 ≤5 보장 의무\n"
        f"  실제 호출: {call_count['n']}회\n"
        f"  Red 결함 가설: max_pages 가드 부재 → 영구 'M' 응답 시 무한 루프\n"
        f"  Green (backend-dev): max_pages 도달 시 break (사이클 91 답습)"
    )
