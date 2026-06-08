"""사이클 83 G-TT1 — 24h TTL fresh skip 검증 (freezegun).

명세 (`_workspace/red/cycle83_scan_pool_eager_refresh.md`):

Q3=B 사용자 결정: 24h TTL + 50ms sleep. eager refresh 가 `stock_master.is_stale(
ticker, max_age_hours=24)` 검사 → fresh 면 KIS 호출 skip (Rate Limit + 비용 절감).

사이클 68 KST 답습 — `stock_master.is_stale()` 가 `_kst.now_kst()` 비교.

기대 동작 (Green, 사이클 84):
- 24h 이내 fresh ticker → `is_stale()` False → eager refresh skip (KIS 호출 0건)
- 24h 초과 stale ticker → `is_stale()` True → `inquire_stock_basics` + `upsert_one` 호출

Red 단계 (사이클 83):
- 신규 함수 `_scan_pool_eager_refresh_*` 미존재 → import fail or fixture skip 불가
- → FAIL (Red 의무)

검증:
- freezegun 2026-06-09 09:30 KST 고정
- stock_master mock: 일부 ticker fresh (last refreshed 2026-06-08 12:00) + 일부 stale
- eager refresh hook 호출 → fresh ticker 는 inquire_stock_basics 호출 0건 + stale 만 호출

영속:
- 사이클 68 KST 답습 (`_kst.now_kst()` 비교)
- 사이클 13-D `_eager_refresh_stock_master_for_held_positions` 패턴 답습
- 매매 안전성 영향 0 (캐시 갱신 영역)
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

_KST = timezone.__new__(timezone, __import__("datetime").timedelta(hours=9))


@pytest.mark.asyncio
async def test_g_tt1_24h_ttl_fresh_skip():
    """G-TT1: 24h TTL fresh ticker 는 eager refresh skip (KIS 호출 0건).

    검증 매트릭스:
    - freezegun 2026-06-09 09:30 KST
    - ticker 3종: A (fresh = 2026-06-08 12:00 갱신, 21.5h 경과) + B (stale =
      2026-06-07 09:00 갱신, 48.5h 경과) + C (미존재, stale)
    - eager refresh hook 호출 → `inquire_stock_basics` 호출 = {B, C} 만 (2회)
    - A 는 skip (0회)

    Red 상태 (사이클 83): 신규 모듈 `scan_pool_eager_refresh_*` 함수 미존재
    → ImportError → FAIL (Red 의무).

    Green (사이클 84): 신규 함수 + 24h TTL skip 로직 도입 → PASS.

    영속 의무:
    - 사이클 13-D `_eager_refresh_stock_master_for_held_positions` (L1833) 패턴
      답습 — `if not await stock_master.is_stale(ticker, max_age_hours=24):
      skipped += 1; continue`
    - 사이클 68 KST 답습 (`_kst.now_kst()` 비교)
    """
    # freezegun 대체: `is_stale` mock 결과로 fresh/stale 직접 주입
    # (시계 자체보다 stock_master 응답이 본질)

    # Red 사전조건: 신규 함수 import 시도
    try:
        from src.engine.scanner import (  # noqa: F401
            _collect_scan_pool_tickers_for_eager_refresh,
        )
    except ImportError:
        pytest.fail(
            "\n사이클 83 G-TT1 Red 상태 — `_collect_scan_pool_tickers_for_eager_refresh` "
            "함수 미존재.\n"
            "  Green (사이클 84): backend-dev 가 신규 함수 도입 의무.\n"
            "  - scanner.py: _collect_scan_pool_tickers_for_eager_refresh() +\n"
            "    _record_scan_pool_eager_refresh() +\n"
            "    _flush_scan_pool_eager_refresh_collector()\n"
            "  - scheduler.py: _scan_pool_eager_refresh_loop() task body"
        )

    # Green 시점 검증 (사이클 84 도입 후 활성화)
    candidates = ["005930", "066570", "402340"]  # A fresh / B stale / C 미존재

    async def _fake_is_stale(ticker: str, max_age_hours: int = 24) -> bool:
        # A (005930) = fresh (False), B (066570) + C (402340) = stale (True)
        return ticker != "005930"

    inquire_calls: list[str] = []

    async def _fake_inquire(ticker: str):
        inquire_calls.append(ticker)
        return MagicMock(ticker=ticker, raw={"bfdy_clpr": 70000})

    upsert_calls: list[str] = []

    async def _fake_upsert(basics):
        upsert_calls.append(basics.ticker)

    with patch("src.db.stock_master.is_stale", new=AsyncMock(side_effect=_fake_is_stale)), \
         patch("src.api.condition.inquire_stock_basics", new=AsyncMock(side_effect=_fake_inquire)), \
         patch("src.db.stock_master.upsert_one", new=AsyncMock(side_effect=_fake_upsert)):
        # Green 시점에 사용 가능: 신규 함수 호출
        try:
            from src.engine.scanner import _scan_pool_eager_refresh_loop
            # Green 시 단일 사이클 실행 헬퍼 — backend-dev 명명 따라 조정 가능
            await _scan_pool_eager_refresh_loop(candidates)
        except (ImportError, AttributeError, TypeError):
            pytest.fail(
                "\n사이클 83 G-TT1 — `_scan_pool_eager_refresh_loop(candidates)` "
                "호출 가능한 형태 미도입.\n"
                "  Green: backend-dev 가 신규 함수 또는 헬퍼 도입 의무."
            )

    # 본 가드 1: fresh (A) skip → inquire 호출 0회
    assert "005930" not in inquire_calls, (
        f"\n사이클 83 G-TT1 위반 — fresh ticker 005930 inquire_stock_basics 호출 발생:\n"
        f"  실제 호출 ticker: {inquire_calls}\n"
        f"  005930 = fresh (21.5h 경과) → 24h TTL 내 → skip 의무"
    )

    # 본 가드 2: stale (B, C) inquire 호출 발생
    expected_stale = {"066570", "402340"}
    actual_stale = set(inquire_calls)
    assert expected_stale.issubset(actual_stale), (
        f"\n사이클 83 G-TT1 위반 — stale ticker inquire_stock_basics 호출 누락:\n"
        f"  기대: {sorted(expected_stale)} 포함\n"
        f"  실제: {sorted(actual_stale)}\n"
        f"  Green: stale ticker 는 inquire 호출 의무"
    )
