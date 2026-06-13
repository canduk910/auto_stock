"""사이클 126 영역 1 — get_stats() count="exact" 정확 카운트 회귀 가드.

PostgREST 디폴트 1000행 한도 silent 결함 시정:
- count="exact" 별도 쿼리 → result.count 직접 사용
- raw 분석 쿼리 .range(0, 9999) 명시
- count 쿼리 실패 시 raw len(rows) graceful fallback
"""
from __future__ import annotations

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
    """G-COUNT1: count="exact" 쿼리 결과로 count_all=2697 정확 반환."""
    from src.db import stock_master, stock_master_daily

    # raw 쿼리는 100행만 반환 (PostgREST 한도 시뮬레이션)
    raw_rows = [_make_row(f"{i:06d}") for i in range(100)]

    captured = {"count_called": False, "raw_called": False}

    def fake_table(name: str):
        class T:
            def __init__(self):
                self._mode = None

            def select(self, cols: str, count: str = None):
                if count == "exact":
                    captured["count_called"] = True
                    self._mode = "count"
                else:
                    captured["raw_called"] = True
                    self._mode = "raw"
                return self

            def order(self, *a, **kw):
                return self

            def range(self, start, end):
                return self

            def limit(self, n):
                return self

            def execute(self):
                class Result:
                    pass
                r = Result()
                if self._mode == "count":
                    r.count = 2697
                    r.data = []
                else:
                    r.data = raw_rows
                return r

        return T()

    monkeypatch.setattr(stock_master.supabase, "table", fake_table)

    # stock_master_daily 모킹 (graceful path)
    async def fake_count_all():
        return 0
    async def fake_max_bas_dd(ticker=None):
        return None
    monkeypatch.setattr(stock_master_daily, "count_all", fake_count_all)
    monkeypatch.setattr(stock_master_daily, "max_bas_dd", fake_max_bas_dd)

    stats = await stock_master.get_stats()

    assert captured["count_called"] is True, "count='exact' 쿼리 미발화"
    assert captured["raw_called"] is True, "raw 분석 쿼리 미발화"
    assert stats["count_all"] == 2697, (
        f"PostgREST 1000행 cap 결함 미시정: count_all={stats['count_all']} (기대 2697)"
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
