"""사이클 6 Red — `src/db/system_logs.py::get_logs()` 기간 필터 + 페이징.

배경:
- 대시보드 하단 LogViewer 를 /logs 메뉴로 분리하면서 운영자가 과거 영업일 로그를
  년/월/일로 검색할 수 있도록 from_date/to_date + 페이징 응답으로 시그니처 확장.
- KST 강제: from_date/to_date 비교 시 `+09:00` 명시 (CLAUDE.md L5 컨벤션).

요구 행위:
A. `await get_logs()` 가 `{items, total, total_pages}` dict 를 반환한다.
B. `from_date=date(2026, 5, 17)` 명시 시 supabase 호출에 `>= "2026-05-17T00:00:00+09:00"` 적용.
C. `to_date=date(2026, 5, 17)` 명시 시 `<= "2026-05-17T23:59:59.999999+09:00"` 적용.
D. `page=2, size=10` 으로 `.range(10, 19)` 호출.
E. `total=23, size=10` → total_pages=3.
F. 기존 `await get_logs(limit=50)` 단독 호출 시에도 dict 응답 (size=50 흡수).
G. `log_level + from_date` 동시 적용 시 두 필터 모두 호출.
H. 빈 결과 → `{items: [], total: 0, total_pages: 0}`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

# 사이클 M3b (2026-07-16) — Supabase→RDS 이전. `get_logs` 가 supabase-py 체인(select/eq/
# gte/lte/order/range chain) → `pg.fetch`+`pg.fetchval` SQL 로 전환되어 본 파일의 Fake
# supabase 가 어떤 호출도 가로채지 못해 전량 FAIL. 페이징/KST 기간필터/dict 응답 실질
# 계약은 `tests/unit/db/test_cycleM3b_system_logs_pg.py::test_get_logs_*` 로 이관되어
# 회귀 가드 유지.
pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        reason="사이클M3b — get_logs supabase→pg 전환. 페이징/KST 필터 계약은 "
        "test_cycleM3b_system_logs_pg.py 로 이관",
        strict=False,
    ),
]


# ---------------------------------------------------------------------------
# Fake supabase chain — system_logs 전용
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, rows: list[dict], captured: dict[str, Any]):
        self._rows = rows
        self._captured = captured

    def eq(self, col: str, val: Any):
        self._captured.setdefault("eq", []).append((col, val))
        return self

    def gte(self, col: str, val: Any):
        self._captured["gte"] = (col, val)
        return self

    def lte(self, col: str, val: Any):
        self._captured["lte"] = (col, val)
        return self

    def order(self, col: str, desc: bool = False):
        self._captured["order"] = (col, desc)
        return self

    def limit(self, n: int):
        self._captured["limit"] = n
        return self

    def range(self, start: int, end: int):
        self._captured["range"] = (start, end)
        return self

    def execute(self):
        total = self._captured.get("_total", len(self._rows))
        rng = self._captured.get("range")
        if rng is not None:
            start, end = rng
            items = self._rows[start : end + 1]
        else:
            limit = self._captured.get("limit")
            items = self._rows[:limit] if limit else list(self._rows)
        # supabase-py 의 count="exact" 응답에는 .count 도 함께 포함된다.
        return type("R", (), {"data": items, "count": total})()


class _FakeTable:
    def __init__(self, rows: list[dict], captured: dict[str, Any]):
        self._rows = rows
        self._captured = captured

    def select(self, *_a, **kwargs):
        self._captured["select_kwargs"] = kwargs
        return _FakeQuery(self._rows, self._captured)


class _FakeSupabase:
    def __init__(self, rows: list[dict], captured: dict[str, Any]):
        self._rows = rows
        self._captured = captured

    def table(self, name: str):
        self._captured["table"] = name
        return _FakeTable(self._rows, self._captured)


def _install(monkeypatch: pytest.MonkeyPatch, rows: list[dict], total: int | None = None):
    from src.db import system_logs

    captured: dict[str, Any] = {}
    if total is not None:
        captured["_total"] = total
    monkeypatch.setattr(system_logs, "supabase", _FakeSupabase(rows, captured))
    return captured


# ---------------------------------------------------------------------------
# A. dict 반환 + 페이징 메타
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_default_returns_dict_with_pagination_meta(monkeypatch):
    from src.db.system_logs import get_logs

    _install(monkeypatch, rows=[
        {"id": 1, "timestamp": "2026-05-17T10:00:00+09:00", "log_level": "INFO", "message": "ok"},
    ], total=1)

    result = await get_logs()
    assert isinstance(result, dict)
    assert "items" in result
    assert "total" in result
    assert "total_pages" in result
    assert result["total"] == 1
    assert result["total_pages"] == 1
    assert len(result["items"]) == 1


# ---------------------------------------------------------------------------
# B/C. KST 기간 필터
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_from_date_uses_kst_timezone(monkeypatch):
    from src.db.system_logs import get_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await get_logs(from_date=date(2026, 5, 17))

    assert "gte" in captured, f"gte 필터가 호출되지 않음: {captured}"
    col, val = captured["gte"]
    assert col == "timestamp"
    assert val == "2026-05-17T00:00:00+09:00", f"got: {val}"


@pytest.mark.asyncio
async def test_get_logs_to_date_uses_kst_timezone(monkeypatch):
    from src.db.system_logs import get_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await get_logs(to_date=date(2026, 5, 17))

    assert "lte" in captured, f"lte 필터가 호출되지 않음: {captured}"
    col, val = captured["lte"]
    assert col == "timestamp"
    # 하루 끝: 23:59:59.999999+09:00
    assert val.startswith("2026-05-17T23:59:59"), f"got: {val}"
    assert val.endswith("+09:00"), f"got: {val}"


# ---------------------------------------------------------------------------
# D. 페이징 (page, size) → range
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_page_size_pagination(monkeypatch):
    from src.db.system_logs import get_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await get_logs(page=2, size=10)

    assert "range" in captured, f"range 가 호출되지 않음: {captured}"
    start, end = captured["range"]
    # page=2, size=10 → offset=10, end=19
    assert start == 10
    assert end == 19


# ---------------------------------------------------------------------------
# E. total_pages 계산
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_total_pages_ceil(monkeypatch):
    from src.db.system_logs import get_logs

    _install(monkeypatch, rows=[], total=23)
    result = await get_logs(page=1, size=10)
    assert result["total"] == 23
    # ceil(23 / 10) = 3
    assert result["total_pages"] == 3


# ---------------------------------------------------------------------------
# F. 하위 호환 — limit 단독 호출
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_legacy_limit_only_call_returns_dict(monkeypatch):
    """기존 `await get_logs(limit=50)` 호출도 dict 반환 + size 흡수."""
    from src.db.system_logs import get_logs

    _install(monkeypatch, rows=[
        {"id": i, "timestamp": "2026-05-17T10:00:00+09:00", "log_level": "INFO", "message": f"m{i}"}
        for i in range(50)
    ], total=50)

    result = await get_logs(limit=50)
    assert isinstance(result, dict)
    assert "items" in result
    assert len(result["items"]) == 50
    assert result["total"] == 50


# ---------------------------------------------------------------------------
# G. level + from_date 동시 적용
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_level_with_date_filter(monkeypatch):
    from src.db.system_logs import get_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await get_logs(log_level="ERROR", from_date=date(2026, 5, 17))

    # level eq 호출 확인
    eqs = captured.get("eq", [])
    level_eqs = [pair for pair in eqs if pair[0] == "log_level"]
    assert level_eqs and level_eqs[0][1] == "ERROR"
    # from_date gte 호출 확인
    assert captured["gte"][1] == "2026-05-17T00:00:00+09:00"


# ---------------------------------------------------------------------------
# H. 빈 결과
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_empty_result(monkeypatch):
    from src.db.system_logs import get_logs

    _install(monkeypatch, rows=[], total=0)
    result = await get_logs(from_date=date(2026, 5, 17), to_date=date(2026, 5, 17))

    assert result["items"] == []
    assert result["total"] == 0
    assert result["total_pages"] == 0
