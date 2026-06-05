"""사이클 62 (2026-06-05) Red — D 카테고리: 60s TTL 캐시 (2 케이스, MEDIUM 우선).

> **선행 명세**: `_workspace/red/cycle62_price_filter.md` (§D)
> **설계 카드**: §2.5 — `PRICE_FILTER_CACHE_TTL = 60.0` (사이클 56-E BUY_BLOCK_CACHE_TTL 답습)
> **선례**: `src/engine/market_regime.py` `BUY_BLOCK_CACHE_TTL` + `_get_buy_block_state` 캐시

요구 행위 (Red 단계 AttributeError 정답 — `_get_price_filter_cached` + 캐시 필드 미존재):

D-1: 60s 내 캐시 hit — DB `get_price_filter` 호출 0 (캐시 hit)
D-2: 60s 만료 또는 invalidate → DB 재조회 (캐시 miss)

위험 등급 MEDIUM 우선 케이스 — 60s 캐시 race.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_risk_manager():
    from src.engine.order_engine import OrderEngine
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    order_engine = MagicMock(spec=OrderEngine)
    rm = RiskManager(registry=registry, order_engine=order_engine)
    return rm


# ---------------------------------------------------------------------------
# D-1: 60s 내 캐시 hit (DB 호출 0)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_D1_cache_hit_within_60s_no_db_call():
    """D-1: 1초 간격 100회 호출 시 DB 호출 1건 (첫 호출만, 이후 60s 캐시).

    사이클 56-E `BUY_BLOCK_CACHE_TTL=60.0` 답습. 분당 ~1,800 DB 쿼리 → 1 (캐시 효과).
    """
    from src.db.system_config import PriceFilter

    rm = _make_risk_manager()
    pf = PriceFilter(min_price=5000, max_price=0, mode="HARD")
    db_get_mock = AsyncMock(return_value=pf)

    with patch("src.engine.risk.get_price_filter", db_get_mock):
        # 시작 시각 base
        base = 1_000_000.0
        # 1초 간격 60 회 호출 (60s 이내)
        with patch("time.monotonic", side_effect=[base + i for i in range(61)]):
            for _ in range(60):
                # Red: `_get_price_filter_cached` AttributeError
                result = await rm._get_price_filter_cached()
                assert result == pf

    # 캐시 hit — DB 호출 1건만
    assert db_get_mock.call_count == 1, (
        f"캐시 hit 결함 — 60s 내 60회 호출 시 DB 1건 (실제 {db_get_mock.call_count}건). "
        "사이클 56-E BUY_BLOCK_CACHE_TTL=60.0 답습 의무."
    )


# ---------------------------------------------------------------------------
# D-2: 60s 만료 후 캐시 miss + invalidate 즉시 반영
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_D2_cache_miss_after_ttl_expiry_and_invalidate():
    """D-2: (a) 60s 만료 후 캐시 miss → DB 재호출 / (b) invalidate 후 즉시 DB 재호출.

    Q5 자문 확정 — 즉시 반영 (5분 grace 추가 금지). Settings PUT 직후 운영자 토글이
    다음 매수 신호부터 즉시 반영.
    """
    from src.db.system_config import PriceFilter

    rm = _make_risk_manager()
    pf1 = PriceFilter(min_price=5000, max_price=0, mode="HARD")
    pf2 = PriceFilter(min_price=10_000, max_price=0, mode="HARD")
    pf3 = PriceFilter(min_price=0, max_price=0, mode="OFF")
    db_get_mock = AsyncMock(side_effect=[pf1, pf2, pf3])

    with patch("src.engine.risk.get_price_filter", db_get_mock):
        # (a) 60s 만료 시뮬레이션 — t=0 호출 → t=61 호출 (캐시 만료)
        with patch("time.monotonic", side_effect=[0.0, 61.0, 61.5]):
            r1 = await rm._get_price_filter_cached()  # t=0 — DB fetch (pf1)
            assert r1 == pf1
            r2 = await rm._get_price_filter_cached()  # t=61 — TTL 만료, DB fetch (pf2)
            assert r2 == pf2

        # (b) invalidate 즉시 → 다음 호출에서 DB 재호출
        # Red: `invalidate_price_filter_cache` AttributeError
        rm.invalidate_price_filter_cache()
        with patch("time.monotonic", return_value=61.7):
            r3 = await rm._get_price_filter_cached()  # invalidate 후 — DB fetch (pf3)
            assert r3 == pf3

    # 총 DB 호출 3건 (캐시 miss 3 번)
    assert db_get_mock.call_count == 3, (
        f"캐시 miss/invalidate 결함 — 만료 후 DB 재호출 + invalidate 후 재호출 = 3건 "
        f"(실제 {db_get_mock.call_count}건)"
    )
