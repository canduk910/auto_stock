"""사이클 89 H-4 — 500 ticker 적재 시 50ms sleep Rate Limit 가드.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

- 50ms sleep × 500 ticker = 25초 백그라운드 직렬 (사이클 83 패턴 답습)
- KIS Rate Limit 20/s 보호 (50ms × 20 = 1초 = 20 호출/초)
- 사이클 13-D `_eager_refresh_stock_master_for_held_positions` sequential await
  + 사이클 37 `_refresh_stale_ccnl_cache` (50ms sleep + cap 20) 패턴 답습
- 사이클 83 G-TT2 `test_cycle83_rate_limit_sleep.py` 직답습

기대 동작 (Green, 사이클 90):
- 500 ticker eager refresh 시 ticker 간 `asyncio.sleep(0.05)` 호출 ≥ 499 회
- 호출 간격 누적 25초 (모두 stale 가정)

Red 단계 (사이클 89): 신규 함수 `_universe_eager_refresh_loop` 미존재
→ ImportError → FAIL.

영속 의무:
- 사이클 83 Q3=B 사용자 결정 (24h TTL + 50ms sleep)
- 사이클 13-D sequential await 패턴
- KIS Rate Limit 20/s 보호 (Semaphore 영역 영속)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h4_rate_limit_50ms_between_500_tickers():
    """H-4: 500 ticker 적재 시 ticker 간 `asyncio.sleep(0.05)` 호출 ≥ 499회.

    검증 매트릭스:
    - 500 ticker 입력 (모두 stale)
    - `_universe_eager_refresh_loop` 1 회 실행
    - asyncio.sleep mock call_args 수집
    - 0.05 (50ms) 호출 ≥ 499회 (500-1 = 499 ticker 간 sleep)

    Red 상태 (사이클 89): `_universe_eager_refresh_loop` 미존재 → ImportError → FAIL.

    Green (사이클 90): backend-dev 가 신규 task body 도입 + sleep(0.05) 50ms → PASS.

    영속 의무:
    - 사이클 83 G-TT2 패턴 직답습 (50ms sleep)
    - 사이클 13-D sequential await
    - 사이클 37 `_refresh_stale_ccnl_cache` 50ms sleep 답습
    """
    # Red 사전조건
    try:
        from src.engine.scanner import _universe_eager_refresh_loop  # noqa: F401
    except ImportError:
        try:
            from src.engine.scheduler import _universe_eager_refresh_loop  # noqa: F401
        except ImportError:
            pytest.fail(
                "\n사이클 89 H-4 Red 상태 — `_universe_eager_refresh_loop` 미존재.\n"
                "  Green (사이클 90): backend-dev 가 신규 task body 도입 의무.\n"
                "  - scheduler.py 또는 scanner.py 에 `_universe_eager_refresh_loop()` +\n"
                "    내부에 ticker 간 `await asyncio.sleep(0.05)` 50ms 의무\n"
                "  - 사이클 83 G-TT2 패턴 답습"
            )

    # 500 ticker (모두 stale 가정)
    candidates = [f"{i:06d}" for i in range(500)]

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

    # production 함수 위치 시도 (scanner 또는 scheduler)
    try:
        from src.engine.scanner import _universe_eager_refresh_loop as _loop_fn
        sleep_patch_target = "src.engine.scanner.asyncio.sleep"
    except ImportError:
        from src.engine.scheduler import _universe_eager_refresh_loop as _loop_fn
        sleep_patch_target = "src.engine.scheduler.asyncio.sleep"

    with patch("src.db.stock_master.is_stale", new=AsyncMock(side_effect=_fake_is_stale)), \
         patch("src.api.condition.inquire_stock_basics", new=AsyncMock(side_effect=_fake_inquire)), \
         patch("src.db.stock_master.upsert_one", new=AsyncMock(side_effect=_fake_upsert)), \
         patch(sleep_patch_target, new=_record_sleep):
        try:
            await _loop_fn(candidates)
        except (ImportError, AttributeError, TypeError) as e:
            pytest.fail(
                f"\n사이클 89 H-4 — `_universe_eager_refresh_loop(candidates)` "
                f"호출 결함:\n  {type(e).__name__}: {e}\n"
                f"  Green: backend-dev 신규 함수 시그너처 의무."
            )

    # 본 가드: 50ms (0.05) sleep 호출 ≥ (N-1) = 499회
    sleep_50ms_count = sum(1 for d in sleep_calls if abs(d - 0.05) < 1e-9)
    assert sleep_50ms_count >= len(candidates) - 1, (
        f"\n사이클 89 H-4 위반 — ticker 간 `asyncio.sleep(0.05)` 호출 누락:\n"
        f"  ticker 수: {len(candidates)} → 기대 sleep(0.05) ≥ {len(candidates) - 1}회\n"
        f"  실제 sleep(0.05) 호출: {sleep_50ms_count}회\n"
        f"  전체 sleep 호출 (모든 delay 카운트): {len(sleep_calls)}회\n\n"
        f"  Green: 사이클 13-D + 사이클 37 + 사이클 83 패턴 답습 — ticker iteration 내\n"
        f"  `await asyncio.sleep(0.05)` 추가 (KIS Rate Limit 20/s 보호).\n"
        f"  사이클 89 시정 의무 (500 ticker × 50ms = 25초 백그라운드 직렬)."
    )
