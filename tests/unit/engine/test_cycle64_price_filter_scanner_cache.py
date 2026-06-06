"""사이클 64 (2026-06-06) Red — D 카테고리: 60s TTL 캐시 + invalidate + Q7-1 KIS LMS 차단 (2 케이스).

> **선행 명세**: `_workspace/red/cycle64_price_filter_scanner.md` (§D)
> **설계 카드**: `_workspace/cycle64_price_filter_scanner_design_card.md` §2.3
> **자문 응답 Q7-1 (HIGH)**: AVOID 자동 unsubscribe (invalidate 캐시만 무효화)
> **선례**: 사이클 56-E `BUY_BLOCK_CACHE_TTL=60.0` + 사이클 62 D 패턴

요구 행위 (Red 단계 AttributeError / ImportError 정답):

- D-1: 60s 내 캐시 hit → DB 호출 1건 (TTL 캐시 동작)
- D-2: 60s 만료 후 캐시 miss + `invalidate_price_filter_cache_scanner()` 즉시 무효화 +
       **Q7-1 (HIGH)** invalidate 시 `kis_ws_pool.unsubscribe` 호출 0건

위험 등급:
- D-1 MEDIUM (캐시 정합성)
- D-2 HIGH (Q7-1 자동 unsubscribe 결함 → KIS LMS chain → 앱 정지 위험)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_pf(min_price=5000, max_price=0):
    from src.db.system_config import PriceFilter
    return PriceFilter(min_price=min_price, max_price=max_price)


# ---------------------------------------------------------------------------
# D-1: 60s 내 캐시 hit (DB 호출 1건)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_D1_cache_hit_within_60s_no_db_call():
    """D-1: 1초 간격 60회 호출 시 DB 호출 1건 (첫 호출만, 이후 60s 캐시).

    사이클 56-E `BUY_BLOCK_CACHE_TTL=60.0` 답습. 분당 1,800 DB 쿼리 → 1.
    """
    from src.engine import scanner

    pf = _make_pf()
    db_get_mock = AsyncMock(return_value=pf)

    # 캐시 사전 무효화 — 테스트 격리 (이전 케이스 잔재 제거)
    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()

    with patch("src.engine.scanner.get_price_filter", db_get_mock):
        base = 1_000_000.0
        # 1초 간격 60회 (60s 이내 — TTL 만료 *전*)
        # 첫 호출 + 59회 캐시 hit
        with patch("time.monotonic", side_effect=[base + i for i in range(61)]):
            for _ in range(60):
                # Red: `_get_price_filter_for_scanner` 미존재 → AttributeError 정답
                result = await scanner._get_price_filter_for_scanner()
                assert result == pf

    # 캐시 hit — DB 호출 1건만
    assert db_get_mock.call_count == 1, (
        f"캐시 hit 결함 — 60s 내 60회 호출 시 DB 1건 (실제 {db_get_mock.call_count}건). "
        "사이클 56-E BUY_BLOCK_CACHE_TTL=60.0 답습 의무."
    )


# ---------------------------------------------------------------------------
# D-2: 60s 만료 후 캐시 miss + invalidate 즉시 + Q7-1 unsubscribe 0건 (HIGH)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_D2_cache_invalidate_does_not_unsubscribe_q7_1():
    """D-2 (HIGH, Q7-1): (a) 60s 만료 후 캐시 miss / (b) invalidate 후 즉시 DB 재호출 /
    **(c) invalidate 시 `kis_ws_pool.unsubscribe` 호출 0건** (Q7-1 자문 — KIS LMS 차단).

    자문 §Q7-1 (HIGH): "invalidate_price_filter_cache 가 unsubscribe 발화 안 함 — 다음
    `_scan_loop` 5분 자연 delta unsubscribe 위임". 즉시 unsubscribe = KIS 등록/해제 race
    → 사이클 17 OPSP0002 폭주 (KIS 공지 "비정상 케이스 2 무한 등록/해제") 재발 위험.
    """
    from src.engine import scanner

    pf1 = _make_pf(min_price=5000)
    pf2 = _make_pf(min_price=10_000)
    pf3 = _make_pf(min_price=0, max_price=0)  # OFF (디폴트)
    db_get_mock = AsyncMock(side_effect=[pf1, pf2, pf3])

    # ws_pool unsubscribe mock — 호출 0 검증 (Q7-1 핵심)
    mock_pool = MagicMock()
    mock_pool.unsubscribe = MagicMock()

    # 캐시 사전 무효화 (테스트 격리)
    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()

    with patch("src.engine.scanner.get_price_filter", db_get_mock), \
         patch("src.engine.scanner.kis_ws_pool", mock_pool):

        # (a) 60s 만료 시뮬레이션 — t=0 → t=61 (캐시 만료 직후)
        with patch("time.monotonic", side_effect=[0.0, 61.0, 61.5]):
            r1 = await scanner._get_price_filter_for_scanner()  # t=0 fetch (pf1)
            assert r1 == pf1
            r2 = await scanner._get_price_filter_for_scanner()  # t=61 TTL 만료, fetch (pf2)
            assert r2 == pf2

        # (b) invalidate 즉시 → 다음 호출 DB 재호출
        # Red: `invalidate_price_filter_cache_scanner` 미존재 → AttributeError 정답
        scanner.invalidate_price_filter_cache_scanner()

        with patch("time.monotonic", return_value=61.7):
            r3 = await scanner._get_price_filter_for_scanner()  # invalidate 후 fetch (pf3)
            assert r3 == pf3

    # 총 DB 호출 3건 (캐시 miss 3 번)
    assert db_get_mock.call_count == 3, (
        f"캐시 miss/invalidate 결함 (실제 {db_get_mock.call_count}건)"
    )

    # === Q7-1 (HIGH) — invalidate 시 unsubscribe 0건 검증 ===
    mock_pool.unsubscribe.assert_not_called()
    # 추가 안전망 — 어떤 ws_pool 메서드도 호출 안 함 (캐시만 무효화)
    # MagicMock 의 method_calls 검증 — unsubscribe 류 호출 0
    unsub_calls = [c for c in mock_pool.method_calls
                   if "unsubscribe" in str(c).lower()]
    assert len(unsub_calls) == 0, (
        f"Q7-1 자문 위반 — invalidate 시 unsubscribe 호출 {len(unsub_calls)}건 발생 "
        f"(KIS LMS chain 위험, 사이클 17 OPSP0002 재발 위험)"
    )
