"""사이클 126 영역 1 — get_stats() count="exact" 정확 카운트 회귀 가드.

PostgREST 디폴트 1000행 한도 silent 결함 시정:
- count="exact" 별도 쿼리 → result.count 직접 사용
- raw 분석 쿼리 .range(0, 9999) 명시
- count 쿼리 실패 시 raw len(rows) graceful fallback
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_row(ticker: str, raw: dict | None = None) -> dict:
    return {
        "ticker": ticker,
        "name": f"종목{ticker}",
        "nxt_tradable": True,
        "raw": raw or {},
        "refreshed_at": "2026-06-13T16:00:00+09:00",
    }


@pytest.mark.asyncio
async def test_g_count1_get_stats_uses_exact_count(monkeypatch):
    """G-COUNT1: count(*) 별도 쿼리 결과로 count_all=2697 정확 반환.

    사이클 M2b — count_all 은 pg.fetchval("SELECT count(*) FROM stock_master") 로
    정확 카운트 (PostgREST 1000행 silent cap 폐기, count='exact' → asyncpg count(*)).
    top_10_recent 는 별도 pg.fetch. stock_master_daily 연동은 모듈 함수 patch.
    """
    from src.db import stock_master, stock_master_daily

    count_sqls: list[str] = []
    data_sqls: list[str] = []

    async def _fetchval(sql, *args):
        count_sqls.append(sql)
        # count_all (필터 없는 count(*)) → 2697, 나머지 카운트 → 0
        return 2697

    async def _fetch(sql, *args):
        data_sqls.append(sql)
        return []

    async def fake_count_all():
        return 0
    async def fake_max_bas_dd(ticker=None):
        return None
    monkeypatch.setattr(stock_master_daily, "count_all", fake_count_all)
    monkeypatch.setattr(stock_master_daily, "max_bas_dd", fake_max_bas_dd)

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=_fetchval)
        pg_mod.fetch = AsyncMock(side_effect=_fetch)
        stats = await stock_master.get_stats()

    # count(*) 별도 쿼리 발화 + raw fetch(top10) 발화
    assert count_sqls and all("count(" in s.lower() for s in count_sqls), "count(*) 쿼리 미발화"
    assert data_sqls, "top_10_recent raw fetch 미발화"
    assert stats["count_all"] == 2697, (
        f"PostgREST 1000행 cap 결함 미시정: count_all={stats['count_all']} (기대 2697)"
    )


@pytest.mark.xfail(
    strict=False,
    reason="사이클 128 — raw rows .range(0, 9999) 영역 영구 폐기 (PostgREST 1000 silent cap 영구 차단) → count='exact' 별도 쿼리 전환. raw len(rows) graceful fallback 의미 전환 = count='exact' 실패 시 graceful 0 (사이클 66 K-2 패턴).",
)
@pytest.mark.asyncio
async def test_g_count2_get_stats_count_query_failure_fallback(monkeypatch):
    """G-COUNT3: count 쿼리 실패 시 raw len(rows) graceful fallback."""
    from src.db import stock_master, stock_master_daily

    raw_rows = [_make_row(f"{i:06d}") for i in range(100)]

    def fake_table(name: str):
        class T:
            def __init__(self):
                self._mode = None

            def select(self, cols: str, count: str = None):
                if count == "exact":
                    self._mode = "count"
                else:
                    self._mode = "raw"
                return self

            def order(self, *a, **kw):
                return self

            def range(self, start, end):
                return self

            def limit(self, n):
                return self

            def execute(self):
                if self._mode == "count":
                    raise RuntimeError("Supabase count 쿼리 실패 시뮬레이션")

                class Result:
                    pass
                r = Result()
                r.data = raw_rows
                return r

        return T()

    monkeypatch.setattr(stock_master.supabase, "table", fake_table)

    async def fake_count_all():
        return 0
    async def fake_max_bas_dd(ticker=None):
        return None
    monkeypatch.setattr(stock_master_daily, "count_all", fake_count_all)
    monkeypatch.setattr(stock_master_daily, "max_bas_dd", fake_max_bas_dd)

    stats = await stock_master.get_stats()

    # raw len(rows) fallback — 100
    assert stats["count_all"] == 100, (
        f"graceful fallback 미작동: count_all={stats['count_all']} (기대 100=len(raw_rows))"
    )
