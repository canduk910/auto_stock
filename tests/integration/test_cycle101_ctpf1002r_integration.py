"""사이클 101 G-CTPF1 — `_full_universe_load_once` chain integration (HIGH).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**chain**:
1. market_cap (FHPST01740000) KOSPI + KOSDAQ 페이징 누적
2. 각 ticker → search_stock_info (CTPF1002R) 67 컬럼
3. stock_master upsert (사이클 84 history trigger 영속)

검증 매트릭스:
- G-CTPF1-A: `_full_universe_load_once` 함수 영속 (Red = 부재)
- G-CTPF1-B: market_cap → CTPF1002R → upsert chain 동작 (mock 통합)
- G-CTPF1-C: 반환 dict 영역 (total/kospi/kosdaq/securities/etf/fetched/skipped_ttl/failed/elapsed_ms)

Red 상태: 신규 함수 부재.
Green (backend-dev): `_full_universe_load_once` 구현 + chain 영속.

영속 의무:
- 사이클 32 R4 universe guard (보유/익일청산 절대 보호) - G-PERSIST2 별도
- 사이클 84 history trigger - G-PERSIST3 별도
- 사이클 88 G-REJECT graceful - G-PERSIST4 별도
- 매매 hot path 영향 0 (scanner 단계 영역)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_g_ctpf1_a_full_universe_load_once_exists() -> None:
    """G-CTPF1-A: `_full_universe_load_once` 함수 영속 (HIGH).

    Red 상태: 신규 함수 부재 → AttributeError.
    Green (backend-dev): src/engine/scanner.py 에 함수 정의 의무.
    """
    from src.engine import scanner

    assert hasattr(scanner, "_full_universe_load_once"), (
        "\n사이클 101 G-CTPF1-A Red 상태 — `_full_universe_load_once` 부재.\n"
        "  Green (backend-dev): src/engine/scanner.py 에 함수 영속 의무.\n"
        "  chain: market_cap → CTPF1002R → stock_master upsert"
    )


@pytest.mark.asyncio
async def test_g_ctpf1_b_market_cap_to_ctpf1002r_chain() -> None:
    """G-CTPF1-B: market_cap → CTPF1002R → upsert chain (HIGH).

    검증 매트릭스 (mock 통합):
    - market_cap KOSPI 응답 (2 ticker) + KOSDAQ 응답 (2 ticker) = 총 4 ticker
    - 각 ticker → CTPF1002R 호출 → 67 컬럼 응답
    - stock_master upsert 호출 4회 의무 (모두 stale 가정)

    Red 상태: 함수 부재 또는 chain 미연결 → upsert 0회.
    Green (backend-dev): chain 동작 의무.
    """
    from src.engine import scanner

    if not hasattr(scanner, "_full_universe_load_once"):
        pytest.fail(
            "사이클 101 G-CTPF1-B Red — `_full_universe_load_once` 부재 (G-CTPF1-A 영속).\n"
            "  Green: scanner.py 신규 함수 의무"
        )

    # mock 0: market_cap page (KOSPI 2 + KOSDAQ 2)
    if not hasattr(scanner, "_fetch_market_cap_page"):
        pytest.fail(
            "G-CTPF1-B Red — `_fetch_market_cap_page` 부재 (G-MC1-A 영속).\n"
            "  Green: 페이징 함수 신규 정의 의무"
        )

    async def fake_market_cap_page(market, max_pages=100):
        if market == "kospi":
            return [
                {"mksc_shrn_iscd": "005930"},
                {"mksc_shrn_iscd": "000660"},
            ]
        if market == "kosdaq":
            return [
                {"mksc_shrn_iscd": "086520"},
                {"mksc_shrn_iscd": "035720"},
            ]
        return []

    # mock 1: inquire_stock_basics (CTPF1002R 67 컬럼 응답)
    async def fake_inquire_basics(ticker):
        # 단순 mock — 67 컬럼 중 일부만 반환 (실제 응답 형식)
        from src.api.condition import StockBasics

        return StockBasics(
            ticker=ticker,
            name=f"종목_{ticker}",
            raw={
                "pdno": ticker,
                "bfdy_clpr": "10000",  # 사이클 81 정본 키 영속
                "prdt_type_cd": "300",
                "excg_dvsn_cd": "02" if ticker.startswith("0") else "03",
                "cptt_trad_tr_psbl_yn": "Y",
                "nxt_tr_stop_yn": "N",
            },
        )

    # mock 2: stock_master.is_stale (모두 stale 가정)
    async def fake_is_stale(ticker, max_age_hours=24):
        return True

    # mock 3: stock_master.upsert_one (호출 count tracking)
    upsert_calls = []

    async def fake_upsert(basics):
        upsert_calls.append(basics)

    with patch(
        "src.engine.scanner._fetch_market_cap_page",
        new=AsyncMock(side_effect=fake_market_cap_page),
    ), patch(
        "src.api.condition.inquire_stock_basics",
        new=AsyncMock(side_effect=fake_inquire_basics),
    ), patch(
        "src.db.stock_master.is_stale",
        new=AsyncMock(side_effect=fake_is_stale),
    ), patch(
        "src.db.stock_master.upsert_one",
        new=AsyncMock(side_effect=fake_upsert),
    ):
        result = await scanner._full_universe_load_once()

    assert len(upsert_calls) >= 4, (
        f"\n사이클 101 G-CTPF1-B 위반 — CTPF1002R upsert chain 미연결:\n"
        f"  기대: 4 ticker 모두 upsert 호출 (≥4)\n"
        f"  실제 upsert 호출: {len(upsert_calls)}회\n"
        f"  Red 결함 가설: market_cap → CTPF1002R → upsert chain 누락\n"
        f"  Green (backend-dev): chain 정합 영속"
    )


@pytest.mark.asyncio
async def test_g_ctpf1_c_returns_summary_dict() -> None:
    """G-CTPF1-C: 반환 dict 영역 영속 (HIGH).

    검증 매트릭스 (사이클 101 운영 가시화 의무):
    - 반환 dict 키: total / kospi / kosdaq / securities / etf / fetched /
      skipped_ttl / failed / elapsed_ms (사이클 74/89 collector 답습)

    Red 상태: 반환 dict 부재 또는 키 누락 → 운영 가시화 무력.
    Green (backend-dev): summary dict 영속.
    """
    from src.engine import scanner

    if not hasattr(scanner, "_full_universe_load_once"):
        pytest.fail("G-CTPF1-C Red — `_full_universe_load_once` 부재")

    async def empty_market_cap(market, max_pages=100):
        return []

    with patch(
        "src.engine.scanner._fetch_market_cap_page",
        new=AsyncMock(side_effect=empty_market_cap),
    ):
        result = await scanner._full_universe_load_once()

    assert isinstance(result, dict), (
        f"\n사이클 101 G-CTPF1-C 위반 — 반환 타입 dict 아님:\n"
        f"  실제: {type(result)}\n"
        f"  Green: summary dict 반환 영속"
    )

    required_keys = {
        "total", "kospi", "kosdaq", "securities", "etf",
        "fetched", "skipped_ttl", "failed", "elapsed_ms",
    }
    missing = required_keys - set(result.keys())
    assert not missing, (
        f"\n사이클 101 G-CTPF1-C 위반 — summary dict 키 누락:\n"
        f"  기대 키: {sorted(required_keys)}\n"
        f"  누락 키: {sorted(missing)}\n"
        f"  Red 결함 가설: collector 패턴 (사이클 74/89 답습) 미적용\n"
        f"  Green (backend-dev): summary dict 9 키 영속 의무"
    )
