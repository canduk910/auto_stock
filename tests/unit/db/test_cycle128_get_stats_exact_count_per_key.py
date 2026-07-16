"""사이클 128 P0-1 — get_stats() 4 카운트 silent cap 시정 회귀 가드.

근본 원인:
- 사이클 126 `count_all` 만 count="exact" 별도 쿼리로 시정
- 나머지 4 카운트 (bfdy_clpr_present / nxt_tradable_count / with_hts_avls / with_acml_tr_pbmn)
  는 `.range(0, 9999)` 후 Python-side sum
- Supabase PostgREST max-rows 한도 (기본 1000행) silent cap → 실제 1,000건만 fetch → 부분 집계

운영 실측 (사이클 126):
- count_all=2,697 (count="exact" 적용 후 정합)
- nxt_tradable=400 vs UI ~150 추정 (silent cap 결함)

본 사이클 128 시정 의무:
- 4 카운트 각각 PostgREST count="exact" + filter 별도 쿼리
- 사이클 126 count_all 시정 패턴 100% 답습
- 영속 가드: `.range(0, 9999)` silent cap 영역 영구 폐기 (AST G-1)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _stats_count_by_sql(sql: str) -> int:
    """사이클 M2b — get_stats 가 발화하는 count(*) SQL 텍스트로 5 카운트 구분.

    production SQL (raw->>'키' text path):
    - count_all: 필터 없는 SELECT count(*)
    - nxt_tradable_count: WHERE nxt_tradable = true
    - bfdy_clpr_present / with_hts_avls / with_acml_tr_pbmn: raw->>'키' 존재성
    """
    s = sql.lower()
    if "hts_avls" in s:
        return 2000
    if "acml_tr_pbmn" in s:
        return 2100
    if "bfdy_clpr" in s:
        return 2500
    if "nxt_tradable" in s:
        return 400
    # count_all (필터 없음)
    return 2697


@pytest.mark.asyncio
async def test_g_stats1_bfdy_clpr_present_exact_count():
    """G-STATS1: 4 카운트가 모두 별도 count(*) 쿼리로 정확 수행되어야 한다.

    사이클 128/M2b — Python-side sum (range 9999 cap) 영구 폐기 + DB-side count.
    asyncpg 전환으로 각 카운트는 pg.fetchval("SELECT count(*) ... WHERE ...").
    """
    from src.db import stock_master

    count_sqls: list[str] = []

    async def _fetchval(sql, *args):
        count_sqls.append(sql)
        return _stats_count_by_sql(sql)

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=_fetchval)
        pg_mod.fetch = AsyncMock(return_value=[
            {"ticker": f"0000{i:02d}", "name": f"종목{i}", "refreshed_at": "2026-06-13T10:00:00+09:00"}
            for i in range(10)
        ])
        with patch("src.db.stock_master_daily.count_all", new=AsyncMock(return_value=0)), \
                patch("src.db.stock_master_daily.max_bas_dd", new=AsyncMock(return_value=None)):
            result = await stock_master.get_stats()

    # 4 카운트가 모두 silent cap 폐기 후 count(*) 기반 정확 값 반환
    assert result["count_all"] == 2697, "count_all 사이클 126 영속"
    assert result["nxt_tradable_count"] == 400, "사이클 128 시정 — 4 카운트 정확 값"
    assert result["bfdy_clpr_present"] == 2500
    assert result["with_hts_avls"] == 2000
    assert result["with_acml_tr_pbmn"] == 2100

    # count(*) 쿼리 5개 이상 (count_all + 4 카운트)
    exact_calls = [s for s in count_sqls if "count(" in s.lower()]
    assert len(exact_calls) >= 5, (
        f"4 카운트 + count_all = 5+ count(*) 쿼리 의무 (사이클 128). 실제: {len(exact_calls)}"
    )


@pytest.mark.asyncio
async def test_g_stats2_range_9999_silent_cap_polished():
    """G-STATS2: get_stats 본체에 `.range(0, 9999)` Python-side cap 잔존 없음.

    AST 정적 가드 (소스 검사) — 4 카운트 silent cap 영역 영구 폐기 회귀 차단.
    """
    import ast
    from pathlib import Path

    src = Path("src/db/stock_master.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    range_9999_in_get_stats: list[int] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_stats":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    is_range_call = (
                        isinstance(func, ast.Attribute) and func.attr == "range"
                    )
                    if is_range_call and len(sub.args) >= 2:
                        # range(0, 9999) literal 패턴 검출
                        a, b = sub.args[0], sub.args[1]
                        if (
                            isinstance(a, ast.Constant) and a.value == 0
                            and isinstance(b, ast.Constant) and b.value == 9999
                        ):
                            range_9999_in_get_stats.append(sub.lineno)

    assert not range_9999_in_get_stats, (
        f"사이클 128 시정 — get_stats() 본체에 .range(0, 9999) 영구 폐기 의무. "
        f"잔존 라인: {range_9999_in_get_stats}"
    )


@pytest.mark.asyncio
async def test_g_stats3_top_10_recent_separate_small_fetch():
    """G-STATS3: top_10_recent 는 별도 작은 LIMIT 10 fetch 의무.

    사이클 128/M2b — 전체 raw fetch → top10 slicing 폐기. pg.fetch 로 LIMIT 10 별도 조회.
    """
    from src.db import stock_master

    fetch_sqls: list[str] = []

    async def _fetch(sql, *args):
        fetch_sqls.append(sql)
        return [
            {"ticker": f"00000{i}", "name": f"종목{i}", "refreshed_at": "2026-06-13T10:00:00+09:00"}
            for i in range(10)
        ]

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=2697)
        pg_mod.fetch = AsyncMock(side_effect=_fetch)
        with patch("src.db.stock_master_daily.count_all", new=AsyncMock(return_value=0)), \
                patch("src.db.stock_master_daily.max_bas_dd", new=AsyncMock(return_value=None)):
            result = await stock_master.get_stats()

    assert isinstance(result["top_10_recent"], list)
    assert len(result["top_10_recent"]) <= 10

    # top_10 별도 작은 fetch 검증: LIMIT 10 쿼리 1건 이상
    small_limit_calls = [s for s in fetch_sqls if "limit 10" in s.lower()]
    assert len(small_limit_calls) >= 1, (
        "top_10_recent 별도 작은 LIMIT 10 fetch 의무 (사이클 128)."
    )


@pytest.mark.asyncio
async def test_g_stats4_count_query_graceful_fallback():
    """G-STATS4: 카운트/조회 쿼리 실패 시 0/[] graceful 반환 (사이클 126 패턴 답습)."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=RuntimeError("pg 일시 장애"))
        pg_mod.fetch = AsyncMock(side_effect=RuntimeError("pg 일시 장애"))
        with patch("src.db.stock_master_daily.count_all", new=AsyncMock(return_value=0)), \
                patch("src.db.stock_master_daily.max_bas_dd", new=AsyncMock(return_value=None)):
            # 예외 전파 0건 — graceful 반환
            result = await stock_master.get_stats()

    # graceful = 0 / [] / None
    assert result["count_all"] == 0
    assert result["bfdy_clpr_present"] == 0
    assert result["nxt_tradable_count"] == 0
    assert result["with_hts_avls"] == 0
    assert result["with_acml_tr_pbmn"] == 0
    assert result["top_10_recent"] == []
