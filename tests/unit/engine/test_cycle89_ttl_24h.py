"""사이클 89 M-2 — 24h TTL fresh skip 검증 (사이클 83 답습).

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

- 24h TTL 영속 (사이클 83 Q3=B)
- `stock_master.is_stale(ticker, max_age_hours=24)` 검사 → fresh = skip
- 사이클 13-D `_eager_refresh_stock_master_for_held_positions` 패턴 답습

기대 동작 (Green, 사이클 90):
- 500 universe 중 24h 이내 fresh ticker → `is_stale()` False → KIS 호출 skip
- 24h 초과 stale ticker → `inquire_stock_basics` + `upsert_one` 호출
- 2 사이클째부터 일일 KIS 호출 추가 부담 = 0건 (24h TTL 자연 skip)

Red 단계 (사이클 89): 신규 함수 미존재 → ImportError → FAIL.

영속 의무:
- 사이클 68 KST 답습 (`_kst.now_kst()` 비교)
- 사이클 83 G-TT1 패턴 직답습 (24h TTL fresh skip)
- 사이클 13-D `_eager_refresh_stock_master_for_held_positions` 패턴 답습
- 매매 안전성 영향 0 (캐시 갱신 영역)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q69=B — `_universe_eager_refresh_loop` 영구 폐기 "
        "(scanner.py + scheduler.py 양쪽). "
        "사이클 89 시점 24h TTL fresh skip 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
@pytest.mark.asyncio
async def test_m2_24h_ttl_fresh_skip():
    """M-2: 24h TTL fresh ticker 는 eager refresh skip (KIS 호출 0건).

    검증 매트릭스:
    - ticker 3종: A (fresh, 21.5h 경과) + B (stale, 48.5h 경과) + C (미존재, stale)
    - eager refresh 호출 → `inquire_stock_basics` 호출 = {B, C} 만 (2회), A 는 0회

    Red 상태 (사이클 89): 신규 함수 미존재 → ImportError → FAIL.

    Green (사이클 90): backend-dev 가 신규 함수 + 24h TTL skip 로직 도입 → PASS.

    영속 의무:
    - 사이클 83 G-TT1 패턴 직답습
    - 사이클 13-D `if not await stock_master.is_stale(ticker, max_age_hours=24):
      skipped += 1; continue`
    - 사이클 68 KST 답습
    """
    # Red 사전조건: 신규 함수 import 시도
    try:
        from src.engine.scanner import _universe_eager_refresh_loop  # noqa: F401
    except ImportError:
        try:
            from src.engine.scheduler import _universe_eager_refresh_loop  # noqa: F401
        except ImportError:
            pytest.fail(
                "\n사이클 89 M-2 Red 상태 — `_universe_eager_refresh_loop` 미존재.\n"
                "  Green (사이클 90): backend-dev 가 신규 함수 도입 의무.\n"
                "  - scheduler.py 또는 scanner.py 에 `_universe_eager_refresh_loop()`\n"
                "  - 사이클 13-D + 사이클 83 G-TT1 패턴 답습"
            )

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

    # production 함수 위치 시도 (scanner 또는 scheduler)
    try:
        from src.engine.scanner import _universe_eager_refresh_loop as _loop_fn
    except ImportError:
        from src.engine.scheduler import _universe_eager_refresh_loop as _loop_fn

    with patch("src.db.stock_master.is_stale", new=AsyncMock(side_effect=_fake_is_stale)), \
         patch("src.api.condition.inquire_stock_basics", new=AsyncMock(side_effect=_fake_inquire)), \
         patch("src.db.stock_master.upsert_one", new=AsyncMock(side_effect=_fake_upsert)):
        try:
            await _loop_fn(candidates)
        except (ImportError, AttributeError, TypeError):
            pytest.fail(
                "\n사이클 89 M-2 — `_universe_eager_refresh_loop(candidates)` "
                "호출 가능한 형태 미도입.\n"
                "  Green: backend-dev 가 신규 함수 도입 의무."
            )

    # 본 가드 1: fresh (A) skip → inquire 호출 0회
    assert "005930" not in inquire_calls, (
        f"\n사이클 89 M-2 위반 — fresh ticker 005930 inquire_stock_basics 호출 발생:\n"
        f"  실제 호출 ticker: {inquire_calls}\n"
        f"  005930 = fresh (21.5h 경과) → 24h TTL 내 → skip 의무"
    )

    # 본 가드 2: stale (B, C) inquire 호출 발생
    expected_stale = {"066570", "402340"}
    actual_stale = set(inquire_calls)
    assert expected_stale.issubset(actual_stale), (
        f"\n사이클 89 M-2 위반 — stale ticker inquire_stock_basics 호출 누락:\n"
        f"  기대: {sorted(expected_stale)} 포함\n"
        f"  실제: {sorted(actual_stale)}\n"
        f"  Green: stale ticker 는 inquire 호출 의무"
    )
