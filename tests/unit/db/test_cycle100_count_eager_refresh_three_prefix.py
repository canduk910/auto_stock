"""사이클 100 G-UI1 — `count_eager_refresh_today` 3 prefix OR 영역 정합 (HIGH).

명세 (`_workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md`):

**결함 (사이클 84 H-4 영속 + 사이클 89/95 누락)**:
- production `count_eager_refresh_today` = `ilike("message", "%[scan_pool_eager_refresh]%")` 단일 grep
- Supabase 7일 실측: 사이클 89 `[universe_eager_refresh]` 244건 + 사이클 95 `[stock_master_bulk_refresh]` 140건 + 사이클 83 `[scan_pool_eager_refresh]` 230건
- UI `StockMaster.tsx::scanPoolQuery.data?.eager_refresh_today` (L548) 표시 = 230 (실제 614 영역 중 ~62% 누락)

**사용자 결정 Q65=C-1**: 3 prefix `OR` 합산
- `[universe_eager_refresh]` (사이클 89, 244건 영속)
- `[scan_pool_eager_refresh]` (사이클 83, 230건 영속 — 기존 유지)
- `[stock_master_bulk_refresh]` (사이클 95, 140건 영속)

**Red 상태**: production 단일 grep → 검증 mock 호출 1 ≠ 기대 3 → FAIL.

**Green (backend-dev)**: 3 prefix OR 영역 시정 → 3 호출 + 합산 → PASS.

영속 의무:
- 사이클 38 명문화 영속 (scanner 단계 매수 진입 전용)
- 사이클 99 KIS 본질 한계 영구 영속 영역 호환
- 매매 안전성 영역 영향 0 (DB 카운트 영역 한정)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_g_ui1_count_eager_refresh_today_sums_three_prefix():
    """G-UI1: count_eager_refresh_today() 3 prefix OR 합산 (HIGH).

    검증 매트릭스 (사이클 100 영역 영구 영속):
    - mock 호출 결과 = prefix별 다른 카운트 (244 / 230 / 140 = 사이클 89/83/95 7일 실측 영역)
    - 결과 = 3 prefix 합산 = 614 (사용자 결정 Q65=C-1)
    - 호출 횟수 = 3 (3 prefix 각각 분리 쿼리 영역)
    - 호출 인자 영역 = `%[universe_eager_refresh]%` + `%[scan_pool_eager_refresh]%` + `%[stock_master_bulk_refresh]%` 모두 호출 영속

    Red 상태 (사이클 100): production 단일 grep → 호출 1회 + 결과 = scan_pool 단독 230 ≠ 614 → FAIL.

    Green (backend-dev): 3 prefix OR 시정 → 3 호출 + 합산 614 → PASS.

    영속 의무:
    - 사이클 84 H-4 호환 (scan_pool_eager_refresh 영역 영속 보존)
    - 사이클 99 영역 영구 영속 (60 ticker 영구 영속 호환)
    - 매매 안전성 영역 영향 0
    """
    from src.db import stock_master

    # prefix별 카운트 (7일 실측 영역 → 단일 일 카운트 시나리오로 축소)
    PREFIX_COUNTS = {
        "%[universe_eager_refresh]%": 24,      # 사이클 89, 244 7일 → 일 평균 24
        "%[scan_pool_eager_refresh]%": 23,     # 사이클 83, 230 7일 → 일 평균 23
        "%[stock_master_bulk_refresh]%": 14,   # 사이클 95, 140 7일 → 일 평균 14
    }
    EXPECTED_SUM = sum(PREFIX_COUNTS.values())  # 61 (사용자 결정 Q65=C-1 합산)

    # 사이클 M2b — pg.fetchval 경유. count_eager_refresh_today 는 3 prefix 각각
    #   pg.fetchval("SELECT count(*) FROM system_logs WHERE message ILIKE $1 ...", pattern, ...)
    # 를 발화 → args[1] 이 prefix 패턴. side_effect 로 패턴 캡처 + per-pattern count 반환.
    captured_patterns: list[str] = []

    async def _fetchval(sql, *args):
        pattern = args[0]  # $1 = ILIKE pattern
        captured_patterns.append(pattern)
        return PREFIX_COUNTS.get(pattern, 0)

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=_fetchval)
        result = await stock_master.count_eager_refresh_today()

    # 가드 1: 호출 횟수 = 3 (3 prefix 각각 분리 쿼리, 사용자 결정 Q65=C-1)
    assert len(captured_patterns) == 3, (
        f"\n사이클 100 G-UI1 위반 — 3 prefix 호출 영역 위반:\n"
        f"  기대 호출 횟수: 3 (사이클 89 universe + 사이클 83 scan_pool + 사이클 95 bulk_refresh)\n"
        f"  실제 호출 횟수: {len(captured_patterns)}\n"
        f"  실제 호출 패턴: {captured_patterns}\n"
        f"  Red 결함: production `count_eager_refresh_today` 단일 grep `[scan_pool_eager_refresh]` 영속\n"
        f"  Green (backend-dev): 3 prefix OR 영역 시정 의무 (사용자 결정 Q65=C-1)\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )

    # 가드 2: 3 prefix 영역 모두 호출 영속
    expected_prefixes = set(PREFIX_COUNTS.keys())
    captured_prefix_set = set(captured_patterns)
    assert captured_prefix_set == expected_prefixes, (
        f"\n사이클 100 G-UI1 위반 — 3 prefix 호출 인자 영역 위반:\n"
        f"  기대 prefix: {sorted(expected_prefixes)}\n"
        f"  실제 prefix: {sorted(captured_prefix_set)}\n"
        f"  누락 영역: {sorted(expected_prefixes - captured_prefix_set)}\n"
        f"  Red 결함: 사이클 89 [universe_eager_refresh] (244건 7일 영속) 또는 사이클 95 [stock_master_bulk_refresh] (140건 7일 영속) 누락\n"
        f"  Green (backend-dev): 3 prefix OR 영역 시정 의무"
    )

    # 가드 3: 결과 = 3 prefix 합산 (사용자 결정 Q65=C-1)
    assert result == EXPECTED_SUM, (
        f"\n사이클 100 G-UI1 위반 — 3 prefix 합산 영역 위반:\n"
        f"  기대 결과: {EXPECTED_SUM} (24 + 23 + 14)\n"
        f"  실제 결과: {result}\n"
        f"  Red 결함: production 단일 grep → scan_pool 단독 23 반환 (universe 24 + bulk 14 = 38 누락)\n"
        f"  Green (backend-dev): 3 prefix 합산 영역 시정 → {EXPECTED_SUM} 영속"
    )


@pytest.mark.asyncio
async def test_g_ui1_count_eager_refresh_today_zero_when_all_empty():
    """G-UI1-B: 3 prefix 모두 0건 → 합산 0 (graceful 영역).

    operating day 영역 = pre-9:00 영역 또는 영업일 외 영역 (사이클 89/83/95 emit 0건 영속).
    """
    from src.db import stock_master

    captured_patterns: list[str] = []

    async def _fetchval(sql, *args):
        captured_patterns.append(args[0])
        return 0

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=_fetchval)
        result = await stock_master.count_eager_refresh_today()

    assert len(captured_patterns) == 3, (
        "사이클 100 G-UI1-B 위반 — 3 prefix 호출 영역 영속 위반 (0건 케이스)"
    )
    assert result == 0, (
        f"사이클 100 G-UI1-B 위반 — 3 prefix 모두 0건 시 합산 0 위반: {result}"
    )
