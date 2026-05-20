"""사이클 6 통합 Red — `src/db/system_logs.py::search_logs()` 키워드 검색.

배경:
- 운영자가 system_logs 에서 키워드(예: `OPSP0002`, `nxt_downgrade`)로 검색.
- ILIKE substring 매칭 (대소문자 무시).
- 등급 + 기간 + limit 동시 조건.

요구 행위:
A. `q="OPSP"` → `ilike("message", "%OPSP%")` 호출
B. `level="ERROR"` + `q` 동시 → `eq("log_level", "ERROR")` + `ilike` 모두 호출
C. `level="ALL"` (또는 None) → `eq` 호출 안 함
D. `start`/`end` → `gte`/`lte` 호출
E. `limit=200` (기본), `limit>1000` 거부 또는 1000 clamp
F. 반환 dict `{logs, total, has_more}` 형식
G. 빈 검색어 `q=""` → ValueError
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.unit


class _FakeQuery:
    def __init__(self, rows: list[dict], captured: dict[str, Any]):
        self._rows = rows
        self._captured = captured

    def eq(self, col: str, val: Any):
        self._captured.setdefault("eq", []).append((col, val))
        return self

    def ilike(self, col: str, pattern: str):
        self._captured["ilike"] = (col, pattern)
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

    def execute(self):
        limit = self._captured.get("limit", len(self._rows))
        total = self._captured.get("_total", len(self._rows))
        items = self._rows[:limit]
        return type("R", (), {"data": items, "count": total})()


class _FakeTable:
    def __init__(self, rows: list[dict], captured: dict[str, Any]):
        self._rows = rows
        self._captured = captured

    def select(self, *a, **kwargs):
        self._captured["select_kwargs"] = kwargs
        return _FakeQuery(self._rows, self._captured)


class _FakeSupabase:
    def __init__(self, rows: list[dict], captured: dict[str, Any]):
        self._rows = rows
        self._captured = captured

    def table(self, name: str):
        self._captured["table"] = name
        return _FakeTable(self._rows, self._captured)


def _install(monkeypatch, rows: list[dict], total: int | None = None):
    from src.db import system_logs

    captured: dict[str, Any] = {}
    if total is not None:
        captured["_total"] = total
    monkeypatch.setattr(system_logs, "supabase", _FakeSupabase(rows, captured))
    return captured


# ---------------------------------------------------------------------------
# A. ilike substring 매칭
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_logs_uses_ilike_for_q(monkeypatch):
    from src.db.system_logs import search_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await search_logs(q="OPSP")

    assert "ilike" in captured, f"ilike 미호출: {captured}"
    col, pattern = captured["ilike"]
    assert col == "message"
    assert pattern == "%OPSP%"


# ---------------------------------------------------------------------------
# B. level + q 동시 적용
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_logs_level_with_q(monkeypatch):
    from src.db.system_logs import search_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await search_logs(q="error_x", level="ERROR")

    eqs = captured.get("eq", [])
    levels = [v for col, v in eqs if col == "log_level"]
    assert "ERROR" in levels, f"level eq 누락: {captured}"
    assert "ilike" in captured, f"ilike 도 함께 호출: {captured}"


# ---------------------------------------------------------------------------
# C. level=ALL → eq 호출 안 함
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_logs_level_all_skips_eq(monkeypatch):
    from src.db.system_logs import search_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await search_logs(q="x", level="ALL")

    eqs = captured.get("eq", [])
    levels = [v for col, v in eqs if col == "log_level"]
    assert not levels, f"level=ALL 인데 eq 호출됨: {eqs}"


@pytest.mark.asyncio
async def test_search_logs_level_none_skips_eq(monkeypatch):
    from src.db.system_logs import search_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await search_logs(q="x", level=None)

    eqs = captured.get("eq", [])
    levels = [v for col, v in eqs if col == "log_level"]
    assert not levels


# ---------------------------------------------------------------------------
# D. start/end 시각 필터
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_logs_start_end_uses_gte_lte(monkeypatch):
    from src.db.system_logs import search_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await search_logs(
        q="x",
        start="2026-05-19T00:00:00+09:00",
        end="2026-05-20T23:59:59+09:00",
    )

    assert captured["gte"] == ("timestamp", "2026-05-19T00:00:00+09:00")
    assert captured["lte"] == ("timestamp", "2026-05-20T23:59:59+09:00")


# ---------------------------------------------------------------------------
# E. limit clamp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_logs_default_limit_is_200(monkeypatch):
    from src.db.system_logs import search_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await search_logs(q="x")

    assert captured.get("limit") == 200, f"기본 limit 200 아님: {captured}"


@pytest.mark.asyncio
async def test_search_logs_limit_max_clamped_to_1000(monkeypatch):
    from src.db.system_logs import search_logs

    captured = _install(monkeypatch, rows=[], total=0)
    await search_logs(q="x", limit=5000)

    assert captured.get("limit") == 1000, f"limit clamp 1000 미적용: {captured}"


# ---------------------------------------------------------------------------
# F. 반환 dict `{logs, total, has_more}`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_logs_returns_logs_total_has_more(monkeypatch):
    from src.db.system_logs import search_logs

    rows = [
        {"id": i, "timestamp": "2026-05-20T10:00:00+09:00", "log_level": "INFO", "message": f"m{i}"}
        for i in range(10)
    ]
    _install(monkeypatch, rows=rows, total=15)
    result = await search_logs(q="m", limit=10)

    assert isinstance(result, dict)
    assert set(result.keys()) >= {"logs", "total", "has_more"}
    assert len(result["logs"]) == 10
    assert result["total"] == 15
    # 15 > 10 → has_more=True
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_search_logs_has_more_false_when_all_returned(monkeypatch):
    from src.db.system_logs import search_logs

    rows = [
        {"id": i, "timestamp": "2026-05-20T10:00:00+09:00", "log_level": "INFO", "message": f"m{i}"}
        for i in range(5)
    ]
    _install(monkeypatch, rows=rows, total=5)
    result = await search_logs(q="m", limit=200)

    assert result["total"] == 5
    assert result["has_more"] is False


# ---------------------------------------------------------------------------
# G. 빈 검색어 → ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_logs_empty_q_raises(monkeypatch):
    from src.db.system_logs import search_logs

    _install(monkeypatch, rows=[], total=0)
    with pytest.raises(ValueError, match="q"):
        await search_logs(q="")


@pytest.mark.asyncio
async def test_search_logs_whitespace_q_raises(monkeypatch):
    from src.db.system_logs import search_logs

    _install(monkeypatch, rows=[], total=0)
    with pytest.raises(ValueError, match="q"):
        await search_logs(q="   ")
