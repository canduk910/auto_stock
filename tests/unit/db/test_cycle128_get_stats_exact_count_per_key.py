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

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _mk_count_response(count: int):
    """count="exact" + .limit(0) 응답 mock (data 빈 list + count int)."""
    resp = MagicMock()
    resp.count = count
    resp.data = []
    return resp


def _mk_data_response(rows: list[dict]):
    """raw 데이터 fetch 응답 mock."""
    resp = MagicMock()
    resp.data = rows
    resp.count = None
    return resp


@pytest.mark.asyncio
async def test_g_stats1_bfdy_clpr_present_exact_count():
    """G-STATS1: bfdy_clpr_present 카운트가 count="exact" 별도 쿼리로 수행되어야 한다.

    사이클 128 시정 — Python-side sum (range 9999 cap) 영구 폐기 + DB-side count.
    """
    from src.db import stock_master

    call_log: list[dict] = []

    class _NotProxy:
        """`.not_` 속성 접근 후 `.is_(...)` / `.neq(...)` 등을 부모 query 로 위임."""
        def __init__(self, parent):
            self._parent = parent

        def is_(self, col, val):
            self._parent.payload.setdefault("not_is_filters", []).append((col, val))
            return self._parent

        def neq(self, col, val):
            self._parent.payload.setdefault("not_neq_filters", []).append((col, val))
            return self._parent

    class FakeQuery:
        def __init__(self, label: str):
            self.label = label
            self.payload: dict = {"label": label}

        def select(self, cols, count=None):
            self.payload["select"] = cols
            self.payload["count"] = count
            return self

        def eq(self, col, val):
            self.payload.setdefault("eq", []).append((col, val))
            return self

        @property
        def not_(self):
            return _NotProxy(self)

        def is_(self, col, val):
            self.payload.setdefault("is_filters", []).append((col, val))
            return self

        def neq(self, col, val):
            self.payload.setdefault("neq", []).append((col, val))
            return self

        def limit(self, n):
            self.payload["limit"] = n
            return self

        def order(self, *args, **kwargs):
            self.payload["order"] = (args, kwargs)
            return self

        def range(self, a, b):
            self.payload["range"] = (a, b)
            return self

        def execute(self):
            call_log.append(self.payload)
            # 카운트 쿼리는 count=exact 동반 → count int 반환
            if self.payload.get("count") == "exact":
                # 키별 다른 count 반환 (not_is_filters / not_neq_filters 모두 탐색)
                not_keys = " ".join(
                    str(k) + " " + str(v)
                    for filters in (
                        self.payload.get("not_is_filters", []),
                        self.payload.get("not_neq_filters", []),
                        self.payload.get("neq", []),
                    )
                    for k, v in filters
                )
                if "hts_avls" in not_keys:
                    return _mk_count_response(2000)
                if "acml_tr_pbmn" in not_keys:
                    return _mk_count_response(2100)
                if "bfdy_clpr" in not_keys:
                    return _mk_count_response(2500)
                if any("nxt_tradable" == c for c, _ in self.payload.get("eq", []) or []):
                    return _mk_count_response(400)
                # count_all (필터 없음)
                return _mk_count_response(2697)
            # 일반 데이터 쿼리 (top_10 등)
            return _mk_data_response([
                {"ticker": f"0000{i:02d}", "name": f"종목{i}", "refreshed_at": "2026-06-13T10:00:00+09:00"}
                for i in range(10)
            ])

    fake_table = MagicMock()
    fake_table.side_effect = lambda name: FakeQuery(label=name)

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table = fake_table
        # stock_master_daily count_all / max_bas_dd graceful mock
        with patch("src.db.stock_master_daily.count_all", return_value=0):
            with patch("src.db.stock_master_daily.max_bas_dd", return_value=None):
                result = await stock_master.get_stats()

    # 4 카운트가 모두 silent cap 폐기 후 count="exact" 기반 정확 값 반환
    assert result["count_all"] == 2697, "count_all 사이클 126 영속"
    assert result["nxt_tradable_count"] == 400, "사이클 128 시정 — count='exact' 4 카운트 정확 값"
    assert result["bfdy_clpr_present"] == 2500
    assert result["with_hts_avls"] == 2000
    assert result["with_acml_tr_pbmn"] == 2100

    # count="exact" 쿼리 사용 검증 — 5개 이상 (count_all + 4 카운트)
    exact_calls = [c for c in call_log if c.get("count") == "exact"]
    assert len(exact_calls) >= 5, (
        f"4 카운트 + count_all = 5+ count='exact' 쿼리 의무 (사이클 128). 실제: {len(exact_calls)}"
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
    """G-STATS3: top_10_recent 는 별도 작은 limit(10) fetch 의무.

    사이클 128 — 전체 raw fetch → top10 slicing 패턴 폐기 (사이클 126 1000 cap 영역 영구 폐기).
    """
    from src.db import stock_master

    call_log: list[dict] = []

    class FakeQuery:
        def __init__(self):
            self.payload: dict = {}

        def select(self, cols, count=None):
            self.payload["select"] = cols
            self.payload["count"] = count
            return self

        def eq(self, col, val):
            self.payload.setdefault("eq", []).append((col, val))
            return self

        def not_(self):
            return self

        def is_(self, col, val):
            self.payload.setdefault("is_filters", []).append((col, val))
            return self

        def neq(self, col, val):
            self.payload.setdefault("neq", []).append((col, val))
            return self

        def limit(self, n):
            self.payload["limit"] = n
            return self

        def order(self, *args, **kwargs):
            self.payload["order"] = (args, kwargs)
            return self

        def range(self, a, b):
            self.payload["range"] = (a, b)
            return self

        def execute(self):
            call_log.append(dict(self.payload))
            if self.payload.get("count") == "exact":
                return _mk_count_response(2697)
            return _mk_data_response([
                {"ticker": f"00000{i}", "name": f"종목{i}", "refreshed_at": "2026-06-13T10:00:00+09:00"}
                for i in range(10)
            ])

    fake_table = MagicMock()
    fake_table.side_effect = lambda name: FakeQuery()

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table = fake_table
        with patch("src.db.stock_master_daily.count_all", return_value=0):
            with patch("src.db.stock_master_daily.max_bas_dd", return_value=None):
                result = await stock_master.get_stats()

    assert isinstance(result["top_10_recent"], list)
    assert len(result["top_10_recent"]) <= 10

    # top_10 작은 fetch 검증: limit=10 호출 1건 이상
    small_limit_calls = [c for c in call_log if c.get("limit") == 10]
    assert len(small_limit_calls) >= 1, (
        "top_10_recent 별도 작은 limit(10) fetch 의무 (사이클 128)."
    )


@pytest.mark.asyncio
async def test_g_stats4_count_query_graceful_fallback():
    """G-STATS4: count="exact" 쿼리 실패 시 0 graceful 반환 (사이클 126 패턴 답습)."""
    from src.db import stock_master

    class FailingQuery:
        def __init__(self):
            pass

        def select(self, *args, **kwargs):
            return self

        def eq(self, *args, **kwargs):
            return self

        def not_(self):
            return self

        def is_(self, *args, **kwargs):
            return self

        def neq(self, *args, **kwargs):
            return self

        def limit(self, n):
            return self

        def order(self, *args, **kwargs):
            return self

        def range(self, *args, **kwargs):
            return self

        def execute(self):
            raise RuntimeError("Supabase 일시 장애 시뮬레이션")

    fake_table = MagicMock()
    fake_table.side_effect = lambda name: FailingQuery()

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table = fake_table
        with patch("src.db.stock_master_daily.count_all", return_value=0):
            with patch("src.db.stock_master_daily.max_bas_dd", return_value=None):
                # 예외 전파 0건 — graceful 반환
                result = await stock_master.get_stats()

    # graceful = 0 / [] / None
    assert result["count_all"] == 0
    assert result["bfdy_clpr_present"] == 0
    assert result["nxt_tradable_count"] == 0
    assert result["with_hts_avls"] == 0
    assert result["with_acml_tr_pbmn"] == 0
    assert result["top_10_recent"] == []
