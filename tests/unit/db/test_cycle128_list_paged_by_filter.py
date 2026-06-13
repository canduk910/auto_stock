"""사이클 128 P1-2 — list_paged_by_filter() 신규 메서드 회귀 가드.

신규 메서드 명세:
- 시그너처: list_paged_by_filter(*, market, min_market_cap, min_trade_amount, name_substr, limit, offset)
- 반환: {"items": list[dict], "total": int, "limit": int, "offset": int}
- 정렬: refreshed_at DESC 영속 (기존 list_all 답습)
- 필터: 모두 optional. 빈 필터 = 전체 (list_all 동등) 회귀 가드 의무 (T-1)
- market: "KOSPI" | "KOSDAQ" | None
- min_market_cap: int (원 단위) | 0 (무필터)
- min_trade_amount: int (원 단위) | 0 (무필터)
- name_substr: str | None (대소문자 무시 substring)

영속 의무:
- 사이클 84 GET 영역 영속
- 사이클 108 list_by_filter (scanner 전용) 와 분리 — UI list 신규 별개 함수
- 사이클 126 count="exact" 답습 (total 정확)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_supabase_chain(rows: list[dict], total_count: int):
    """Fake Supabase 쿼리 체인 — 마지막 execute 가 rows 또는 count 반환."""
    seen_filters: dict = {"eq": [], "ilike": [], "gte": [], "select_kwargs": {}}

    class FakeQuery:
        def __init__(self):
            self.is_count_query = False

        def select(self, cols, count=None):
            if count == "exact":
                self.is_count_query = True
            seen_filters["select_kwargs"] = {"cols": cols, "count": count}
            return self

        def eq(self, col, val):
            seen_filters["eq"].append((col, val))
            return self

        def ilike(self, col, pat):
            seen_filters["ilike"].append((col, pat))
            return self

        def gte(self, col, val):
            seen_filters["gte"].append((col, val))
            return self

        def order(self, *args, **kwargs):
            seen_filters["order"] = (args, kwargs)
            return self

        def range(self, a, b):
            seen_filters["range"] = (a, b)
            return self

        def limit(self, n):
            seen_filters["limit"] = n
            return self

        def execute(self):
            resp = MagicMock()
            if self.is_count_query:
                resp.count = total_count
                resp.data = []
            else:
                resp.data = rows
                resp.count = None
            return resp

    return FakeQuery(), seen_filters


@pytest.mark.asyncio
async def test_g_list1_empty_filter_equals_list_all():
    """G-LIST1: 빈 필터 = list_all 동등 (T-1 영속).

    필터 4개 모두 default 시 list_all 과 동일 결과셋 반환 의무.
    """
    from src.db import stock_master

    sample_rows = [
        {"ticker": f"00000{i}", "name": f"종목{i}", "refreshed_at": "2026-06-13T10:00:00+09:00"}
        for i in range(10)
    ]

    query_factory_calls = []

    def _factory(name):
        q, _ = _make_supabase_chain(sample_rows, total_count=2697)
        query_factory_calls.append(q)
        return q

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table.side_effect = _factory
        result = await stock_master.list_paged_by_filter(
            limit=100, offset=0
        )

    assert "items" in result
    assert "total" in result
    assert "limit" in result
    assert "offset" in result
    assert result["limit"] == 100
    assert result["offset"] == 0
    assert result["total"] == 2697
    assert result["items"] == sample_rows


@pytest.mark.asyncio
async def test_g_list2_market_kospi_filter_applies_excg_dvsn_eq():
    """G-LIST2: market="KOSPI" 시 excg_dvsn_cd="02" eq 필터 적용."""
    from src.db import stock_master

    seen = {"eq": [], "ilike": [], "gte": [], "limit": None, "range": None, "order": None}

    class FakeQuery:
        def __init__(self):
            self.is_count = False

        def select(self, cols, count=None):
            if count == "exact":
                self.is_count = True
            return self

        def eq(self, col, val):
            seen["eq"].append((col, val))
            return self

        def ilike(self, col, pat):
            seen["ilike"].append((col, pat))
            return self

        def gte(self, col, val):
            seen["gte"].append((col, val))
            return self

        def order(self, *args, **kwargs):
            seen["order"] = (args, kwargs)
            return self

        def range(self, a, b):
            seen["range"] = (a, b)
            return self

        def limit(self, n):
            seen["limit"] = n
            return self

        def execute(self):
            resp = MagicMock()
            if self.is_count:
                resp.count = 800
                resp.data = []
            else:
                resp.data = [{"ticker": "005930", "excg_dvsn_cd": "02"}]
                resp.count = None
            return resp

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table.side_effect = lambda n: FakeQuery()
        result = await stock_master.list_paged_by_filter(
            market="KOSPI", limit=50, offset=0
        )

    eq_set = set(seen["eq"])
    assert ("excg_dvsn_cd", "02") in eq_set, (
        f"KOSPI → excg_dvsn_cd='02' eq 필터 의무. 실제 eq: {seen['eq']}"
    )
    assert result["total"] == 800


@pytest.mark.asyncio
async def test_g_list3_market_kosdaq_filter_applies_excg_dvsn_eq():
    """G-LIST3: market="KOSDAQ" 시 excg_dvsn_cd="03" eq 필터 적용."""
    from src.db import stock_master

    seen = {"eq": []}

    class FakeQuery:
        def __init__(self):
            self.is_count = False

        def select(self, cols, count=None):
            if count == "exact":
                self.is_count = True
            return self

        def eq(self, col, val):
            seen["eq"].append((col, val))
            return self

        def ilike(self, *a, **k):
            return self

        def gte(self, *a, **k):
            return self

        def order(self, *args, **kwargs):
            return self

        def range(self, *args, **kwargs):
            return self

        def limit(self, n):
            return self

        def execute(self):
            resp = MagicMock()
            if self.is_count:
                resp.count = 1500
                resp.data = []
            else:
                resp.data = []
                resp.count = None
            return resp

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table.side_effect = lambda n: FakeQuery()
        await stock_master.list_paged_by_filter(market="KOSDAQ", limit=50, offset=0)

    assert ("excg_dvsn_cd", "03") in set(seen["eq"])


@pytest.mark.asyncio
async def test_g_list4_name_substr_ilike_applies():
    """G-LIST4: name_substr 지정 시 ilike("name", "%삼성%") 필터 적용."""
    from src.db import stock_master

    seen = {"ilike": []}

    class FakeQuery:
        def __init__(self):
            self.is_count = False

        def select(self, cols, count=None):
            if count == "exact":
                self.is_count = True
            return self

        def eq(self, *a, **k):
            return self

        def ilike(self, col, pat):
            seen["ilike"].append((col, pat))
            return self

        def gte(self, *a, **k):
            return self

        def order(self, *args, **kwargs):
            return self

        def range(self, *args, **kwargs):
            return self

        def limit(self, n):
            return self

        def execute(self):
            resp = MagicMock()
            if self.is_count:
                resp.count = 12
                resp.data = []
            else:
                resp.data = [{"ticker": "005930", "name": "삼성전자"}]
                resp.count = None
            return resp

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table.side_effect = lambda n: FakeQuery()
        result = await stock_master.list_paged_by_filter(name_substr="삼성", limit=50, offset=0)

    assert any(
        col == "name" and "삼성" in pat and pat.startswith("%") and pat.endswith("%")
        for col, pat in seen["ilike"]
    ), f"name_substr → ilike('name', '%삼성%') 의무. 실제: {seen['ilike']}"
    assert result["total"] == 12


@pytest.mark.asyncio
async def test_g_list5_offset_and_total_propagate():
    """G-LIST5: offset / limit / total 정합 — 응답에 포함되어야 한다."""
    from src.db import stock_master

    seen = {}

    class FakeQuery:
        def __init__(self):
            self.is_count = False

        def select(self, cols, count=None):
            if count == "exact":
                self.is_count = True
            return self

        def eq(self, *a, **k):
            return self

        def ilike(self, *a, **k):
            return self

        def gte(self, *a, **k):
            return self

        def order(self, *args, **kwargs):
            return self

        def range(self, a, b):
            seen["range"] = (a, b)
            return self

        def limit(self, n):
            return self

        def execute(self):
            resp = MagicMock()
            if self.is_count:
                resp.count = 500
                resp.data = []
            else:
                resp.data = [{"ticker": f"00000{i}"} for i in range(50)]
                resp.count = None
            return resp

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table.side_effect = lambda n: FakeQuery()
        result = await stock_master.list_paged_by_filter(limit=50, offset=100)

    assert result["limit"] == 50
    assert result["offset"] == 100
    assert result["total"] == 500
    # range(offset, offset+limit-1) = (100, 149)
    assert seen.get("range") == (100, 149)


@pytest.mark.asyncio
async def test_g_list6_min_market_cap_filter_applies():
    """G-LIST6: min_market_cap > 0 시 JSONB raw->>hts_avls 비교 필터 적용.

    raw.hts_avls 단위는 백만원 → min_market_cap (원) / 1_000_000 환산 후 비교.
    예: min_market_cap=1_000_000_000_000 (1조 원) → hts_avls >= 1_000_000 (백만원).
    """
    from src.db import stock_master

    seen = {"gte": [], "filter": []}

    class FakeQuery:
        def __init__(self):
            self.is_count = False

        def select(self, cols, count=None):
            if count == "exact":
                self.is_count = True
            return self

        def eq(self, *a, **k):
            return self

        def ilike(self, *a, **k):
            return self

        def gte(self, col, val):
            seen["gte"].append((col, val))
            return self

        def filter(self, col, op, val):
            seen["filter"].append((col, op, val))
            return self

        def order(self, *args, **kwargs):
            return self

        def range(self, *args, **kwargs):
            return self

        def limit(self, n):
            return self

        def execute(self):
            resp = MagicMock()
            if self.is_count:
                resp.count = 50
                resp.data = []
            else:
                resp.data = []
                resp.count = None
            return resp

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table.side_effect = lambda n: FakeQuery()
        # 1 조 원 (=백만원 단위 100만)
        await stock_master.list_paged_by_filter(
            min_market_cap=1_000_000_000_000, limit=50, offset=0
        )

    # gte 또는 filter 어느 한 쪽으로라도 hts_avls 영역 필터 적용 의무
    all_filter_calls = [
        (col, val) for col, val in seen["gte"]
    ] + [
        (col, val) for col, _op, val in seen["filter"] if "avls" in str(col).lower()
    ]
    hts_filter_applied = any("avls" in str(col).lower() for col, _ in all_filter_calls)
    assert hts_filter_applied, (
        f"min_market_cap → hts_avls 영역 필터 의무 (raw->>hts_avls 또는 raw->hts_avls). "
        f"실제 gte: {seen['gte']} / filter: {seen['filter']}"
    )


@pytest.mark.asyncio
async def test_g_list7_min_trade_amount_filter_applies():
    """G-LIST7: min_trade_amount > 0 시 JSONB raw->>acml_tr_pbmn 비교 필터."""
    from src.db import stock_master

    seen = {"gte": [], "filter": []}

    class FakeQuery:
        def __init__(self):
            self.is_count = False

        def select(self, cols, count=None):
            if count == "exact":
                self.is_count = True
            return self

        def eq(self, *a, **k):
            return self

        def ilike(self, *a, **k):
            return self

        def gte(self, col, val):
            seen["gte"].append((col, val))
            return self

        def filter(self, col, op, val):
            seen["filter"].append((col, op, val))
            return self

        def order(self, *args, **kwargs):
            return self

        def range(self, *args, **kwargs):
            return self

        def limit(self, n):
            return self

        def execute(self):
            resp = MagicMock()
            if self.is_count:
                resp.count = 30
                resp.data = []
            else:
                resp.data = []
                resp.count = None
            return resp

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table.side_effect = lambda n: FakeQuery()
        await stock_master.list_paged_by_filter(min_trade_amount=10_000_000_000, limit=50, offset=0)

    all_calls = [(c, v) for c, v in seen["gte"]] + [(c, v) for c, _, v in seen["filter"]]
    pbmn_applied = any("acml_tr_pbmn" in str(c) for c, _ in all_calls)
    assert pbmn_applied, (
        f"min_trade_amount → acml_tr_pbmn 영역 필터 의무. "
        f"실제 gte: {seen['gte']} / filter: {seen['filter']}"
    )
