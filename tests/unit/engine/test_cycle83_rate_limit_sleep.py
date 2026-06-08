"""사이클 83 G-TT2 — 50ms sleep Rate Limit 가드 검증.

명세 (`_workspace/red/cycle83_scan_pool_eager_refresh.md`):

Q3=B 사용자 결정: 24h TTL + 50ms sleep. eager refresh 가 ticker 간
`asyncio.sleep(0.05)` 50ms 간격 유지 → KIS Rate Limit 20/s 보호.

사이클 13-D `_eager_refresh_stock_master_for_held_positions` (sequential await)
패턴 답습 + 사이클 37 `_refresh_stale_ccnl_cache` (50ms sleep + cap 20) 답습.

기대 동작 (Green, 사이클 84):
- N ticker (N≥2) eager refresh 시 ticker 간 `asyncio.sleep(0.05)` 호출 ≥ (N-1) 회
- 30~50 ticker 시 호출 간격 누적 ≥ (N-1) × 50ms

Red 단계 (사이클 83):
- 신규 함수 미존재 → import fail → FAIL.

검증:
- asyncio.sleep mock — call_args 수집
- ticker 5종 eager refresh → asyncio.sleep(0.05) 호출 ≥ 4건 (ticker 간)

영속:
- 사이클 13-D sequential await 패턴
- 사이클 37 `_refresh_stale_ccnl_cache` 50ms sleep 답습
- KIS Rate Limit 20/s 보호 (50ms × 20 = 1초 = 20 호출/초)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_g_tt2_rate_limit_sleep_50ms_between_tickers():
    """G-TT2: ticker 간 `asyncio.sleep(0.05)` 50ms 호출 ≥ (N-1) 회.

    검증 매트릭스:
    - 5 ticker 입력 (모두 stale)
    - eager refresh 본체 1 회 실행
    - asyncio.sleep mock call_args 수집
    - 0.05 (50ms) 호출 ≥ 4회 (5-1 = 4 ticker 간 sleep)

    Red 상태 (사이클 83): 신규 함수 미존재 → ImportError → FAIL.

    Green (사이클 84): backend-dev 가 신규 함수 + sleep(0.05) 도입 → PASS.

    영속 의무:
    - 사이클 13-D `_eager_refresh_stock_master_for_held_positions` sequential
      await 패턴 답습
    - 사이클 37 `_refresh_stale_ccnl_cache` (`stale_diagnostics.py:228` 영역)
      `await asyncio.sleep(0.05)` 패턴 답습 — KIS 호출 간격 보호
    - 사이클 83 Q3=B 사용자 결정 (24h TTL + 50ms sleep)
    """
    # Red 사전조건
    try:
        from src.engine.scanner import _scan_pool_eager_refresh_loop  # noqa: F401
    except ImportError:
        pytest.fail(
            "\n사이클 83 G-TT2 Red 상태 — `_scan_pool_eager_refresh_loop` 미존재.\n"
            "  Green (사이클 84): backend-dev 가 신규 함수 도입 의무."
        )

    candidates = ["005930", "066570", "035720", "000660", "402340"]

    # 모두 stale
    async def _fake_is_stale(ticker: str, max_age_hours: int = 24) -> bool:
        return True

    async def _fake_inquire(ticker: str):
        return MagicMock(ticker=ticker, raw={"bfdy_clpr": 50000})

    async def _fake_upsert(basics):
        pass

    sleep_calls: list[float] = []

    real_sleep = __import__("asyncio").sleep

    async def _record_sleep(delay):
        sleep_calls.append(float(delay))
        # 실제 yield (이벤트 루프 진행)
        await real_sleep(0)

    with patch("src.db.stock_master.is_stale", new=AsyncMock(side_effect=_fake_is_stale)), \
         patch("src.api.condition.inquire_stock_basics", new=AsyncMock(side_effect=_fake_inquire)), \
         patch("src.db.stock_master.upsert_one", new=AsyncMock(side_effect=_fake_upsert)), \
         patch("src.engine.scanner.asyncio.sleep", new=_record_sleep):
        try:
            from src.engine.scanner import _scan_pool_eager_refresh_loop
            await _scan_pool_eager_refresh_loop(candidates)
        except (ImportError, AttributeError, TypeError) as e:
            pytest.fail(
                f"\n사이클 83 G-TT2 — `_scan_pool_eager_refresh_loop(candidates)` "
                f"호출 결함:\n  {type(e).__name__}: {e}\n"
                f"  Green: backend-dev 신규 함수 도입 의무."
            )

    # 본 가드: 50ms (0.05) sleep 호출 ≥ (N-1) = 4 회
    sleep_50ms_count = sum(1 for d in sleep_calls if abs(d - 0.05) < 1e-9)
    assert sleep_50ms_count >= len(candidates) - 1, (
        f"\n사이클 83 G-TT2 위반 — ticker 간 `asyncio.sleep(0.05)` 호출 누락:\n"
        f"  ticker 수: {len(candidates)} → 기대 sleep(0.05) ≥ {len(candidates) - 1}회\n"
        f"  실제 sleep(0.05) 호출: {sleep_50ms_count}회\n"
        f"  전체 sleep 호출 (모든 delay): {sleep_calls}\n\n"
        f"  Green: 사이클 13-D + 사이클 37 패턴 답습 — ticker iteration 내\n"
        f"  `await asyncio.sleep(0.05)` 추가 (KIS Rate Limit 20/s 보호).\n"
        f"  사이클 83 Q3=B 사용자 결정."
    )
