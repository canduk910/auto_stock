"""사이클 6 통합 Red — `src/db/system_logs.py::purge_old_logs()` retention 정책.

배경:
- INFO 등급 로그는 운영자가 보통 당일~다음날까지만 검토. 30일 누적 시 system_logs 폭증.
- WARNING/ERROR/CRITICAL 은 30일 유지 (장기 사고 추적성).
- DB DELETE 안전 가드: WHERE 조건 누락 시 raise, 1회 cap 100,000 행.

요구 행위:
A. INFO 등급: `timestamp < (now_kst - 2 days)` DELETE
B. HIGH 등급 (WARNING/ERROR/CRITICAL): `timestamp < (now_kst - 30 days)` DELETE
C. 반환 dict: `{info_deleted, high_deleted, elapsed_ms}`
D. KST `+09:00` suffix 강제
E. 1회 cap 100,000 행 (range 또는 limit 적용)
F. WHERE cutoff None → RuntimeError (방어 코드)
G. INFO 영구 로그 `[log_retention]` prefix
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# Fake supabase delete chain
# ---------------------------------------------------------------------------


class _FakeDeleteQuery:
    def __init__(self, captured: dict[str, Any], group: str):
        self._captured = captured
        self._group = group

    def lt(self, col: str, val: Any):
        self._captured.setdefault("lt", {})[self._group] = (col, val)
        return self

    def eq(self, col: str, val: Any):
        self._captured.setdefault("eq", {}).setdefault(self._group, []).append((col, val))
        return self

    def in_(self, col: str, vals: list[Any]):
        self._captured.setdefault("in_", {})[self._group] = (col, list(vals))
        return self

    def limit(self, n: int):
        self._captured.setdefault("limit", {})[self._group] = n
        return self

    def execute(self):
        # delete-with-returning: supabase-py 는 `.execute()` 가 deleted rows 반환
        deleted = self._captured.get("_deleted", {}).get(self._group, 0)
        rows = [{"id": i} for i in range(deleted)]
        return type("R", (), {"data": rows, "count": deleted})()


class _FakeSelectQuery:
    """사이클 150 (2026-06-16) — `_purge_by_cutoff` 시정 = SELECT chain 영역 신규.

    사이클 6 결함 영역 시정 영구 영속 — supabase-py DELETE chain `.limit()` 미지원 →
    SELECT id LIMIT MAX_PURGE_BATCH + DELETE WHERE id IN (ids) 2-step 영역 영구 영속.
    """

    def __init__(self, captured: dict[str, Any], group: str):
        self._captured = captured
        self._group = group

    def eq(self, col: str, val: Any):
        # 사이클 150 영역 영속 — SELECT chain 영역으로 이전 후에도 사이클 6 영역 영속 영구 영속
        # captured["eq"] 영역 = INFO/HIGH 그룹 영구 영속 호환 보존 (사이클 66 K-2 의미 전환 영역)
        if col == "log_level" and val == "INFO":
            self._captured["_select_group"] = "info"
            self._group = "info"
        self._captured.setdefault("eq", {}).setdefault(self._group, []).append((col, val))
        return self

    def in_(self, col: str, vals: list[Any]):
        # 사이클 150 영역 영속 — HIGH 영역 영구 영속 = WARNING/ERROR/CRITICAL 영역 in_
        if col == "log_level":
            self._captured["_select_group"] = "high"
            self._group = "high"
        self._captured.setdefault("in_", {})[self._group] = (col, list(vals))
        return self

    def lt(self, col: str, val: Any):
        # 사이클 150 영역 영속 — SELECT chain 영역에서도 cutoff 캡처 (delete chain 정합)
        # 사이클 6 영속 영역 = lt 영역에서 group 영역 영구 영속 정합 보존
        group = self._captured.get("_select_group", self._group)
        self._captured.setdefault("lt", {})[group] = (col, val)
        return self

    def limit(self, n: int):
        group = self._captured.get("_select_group", self._group)
        self._captured.setdefault("limit", {})[group] = n
        return self

    def execute(self):
        group = self._captured.get("_select_group", self._group)
        # 사이클 150 영역 영속 — SELECT 결과 영역 = info_deleted / high_deleted 값
        deleted = self._captured.get("_deleted", {}).get(group, 0)
        rows = [{"id": i + 1} for i in range(deleted)]
        # 영속 영역 = 다음 DELETE chain 영역 영속 ids 전달 영역 영구 영속
        self._captured.setdefault("_select_ids", {})[group] = [r["id"] for r in rows]
        return type("R", (), {"data": rows, "count": deleted})()


class _FakeDeleteInQuery:
    """사이클 150 — DELETE WHERE id IN (ids) chain 영역 영구 영속."""

    def __init__(self, captured: dict[str, Any]):
        self._captured = captured

    def in_(self, col: str, vals: list[Any]):
        # 사이클 150 영역 = id 영역 영속 매핑
        # 호출 영역 영구 영속에서 _select_group 영속 영역 활용
        group = self._captured.get("_select_group", "info")
        self._captured.setdefault("delete_in_", {})[group] = (col, list(vals))
        return self

    def execute(self):
        group = self._captured.get("_select_group", "info")
        deleted = self._captured.get("_deleted", {}).get(group, 0)
        rows = [{"id": i + 1} for i in range(deleted)]
        return type("R", (), {"data": rows, "count": deleted})()


class _FakeTable:
    def __init__(self, captured: dict[str, Any]):
        self._captured = captured
        self._group: str | None = None

    def delete(self):
        # 사이클 150 영역 영속 — 사이클 6 시정 후 DELETE chain 영역 영구 영속 = id IN (ids) 단일
        # 그룹 매핑 영역 = SELECT chain 영역 영속에서 _select_group 영속 영역 결정
        idx = self._captured.setdefault("_delete_count", 0)
        self._captured["_delete_count"] = idx + 1
        return _FakeDeleteInQuery(self._captured)

    def select(self, *cols: str):
        # 사이클 150 영역 신규 — SELECT chain 영역 영구 영속
        idx = self._captured.setdefault("_select_count", 0)
        self._captured["_select_count"] = idx + 1
        # 첫 호출 = info / 두 번째 = high 영역 (사이클 6 영속 영역 영속)
        # 그룹 영역 영구 영속 = eq/in_ 영역에서 자동 결정 영구 영속
        group = "info" if idx == 0 else "high"
        self._captured["_select_group"] = group
        self._group = group
        return _FakeSelectQuery(self._captured, group)

    def insert(self, data):
        # 사이클 150 영역 — write_log 영역 graceful 영구 영속 흡수 영역
        # ([log_retention] INFO 1행 emit 영역 영구 영속 = mock 영역 흡수 무관)
        class _Inserted:
            def execute(self_inner):
                return type("R", (), {"data": [], "count": 0})()
        return _Inserted()


class _FakeSupabase:
    def __init__(self, captured: dict[str, Any]):
        self._captured = captured

    def table(self, name: str):
        self._captured.setdefault("tables", []).append(name)
        return _FakeTable(self._captured)


def _install(monkeypatch: pytest.MonkeyPatch, *, info_deleted: int = 0, high_deleted: int = 0):
    from src.db import system_logs

    captured: dict[str, Any] = {"_deleted": {"info": info_deleted, "high": high_deleted}}
    monkeypatch.setattr(system_logs, "supabase", _FakeSupabase(captured))
    return captured


# ---------------------------------------------------------------------------
# A. 반환 dict 구조 + 키 누락 없음
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_old_logs_returns_dict_with_required_keys(monkeypatch):
    from src.db.system_logs import purge_old_logs

    _install(monkeypatch, info_deleted=5, high_deleted=2)
    result = await purge_old_logs()

    assert isinstance(result, dict)
    assert set(result.keys()) >= {"info_deleted", "high_deleted", "elapsed_ms"}
    assert result["info_deleted"] == 5
    assert result["high_deleted"] == 2
    assert result["elapsed_ms"] >= 0


# ---------------------------------------------------------------------------
# B. INFO 등급 cutoff = 2일
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_info_uses_2_days_cutoff(monkeypatch):
    from src.db.system_logs import purge_old_logs

    captured = _install(monkeypatch)

    # 시간 고정
    fixed_now = datetime(2026, 5, 20, 20, 15, 0, tzinfo=KST)
    import src.db.system_logs as mod
    real_dt = mod.datetime

    class _FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            return fixed_now
    monkeypatch.setattr(mod, "datetime", _FakeDateTime)

    try:
        await purge_old_logs()
    finally:
        monkeypatch.setattr(mod, "datetime", real_dt)

    lt = captured.get("lt", {})
    assert "info" in lt, f"info delete 미호출: {captured}"
    col, val = lt["info"]
    assert col == "timestamp"
    # 2일 전: 2026-05-18T20:15:00+09:00
    assert val.startswith("2026-05-18T20:15"), f"got: {val}"
    assert val.endswith("+09:00"), f"got: {val}"


# ---------------------------------------------------------------------------
# C. HIGH 등급 cutoff = 30일 + 등급 필터 (WARNING/ERROR/CRITICAL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_high_uses_30_days_cutoff_with_level_filter(monkeypatch):
    from src.db.system_logs import purge_old_logs

    captured = _install(monkeypatch)

    fixed_now = datetime(2026, 5, 20, 20, 15, 0, tzinfo=KST)
    import src.db.system_logs as mod

    class _FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            return fixed_now
    monkeypatch.setattr(mod, "datetime", _FakeDateTime)

    await purge_old_logs()

    lt = captured.get("lt", {})
    assert "high" in lt, f"high delete 미호출: {captured}"
    col, val = lt["high"]
    assert col == "timestamp"
    # 30일 전: 2026-04-20T20:15:00+09:00
    assert val.startswith("2026-04-20T20:15"), f"got: {val}"
    assert val.endswith("+09:00"), f"got: {val}"

    # 등급 필터: in_("log_level", ["WARNING", "ERROR", "CRITICAL"]) 또는 eq 다중
    in_ = captured.get("in_", {})
    eq = captured.get("eq", {})
    if "high" in in_:
        col, vals = in_["high"]
        assert col == "log_level"
        assert set(vals) == {"WARNING", "ERROR", "CRITICAL"}
    else:
        # eq 다중 (구현 변형) - INFO 가드도 eq 사용한다면 high 가드도 eq
        high_eqs = eq.get("high", [])
        levels = {v for col, v in high_eqs if col == "log_level"}
        assert levels == {"WARNING", "ERROR", "CRITICAL"}, f"high level filter 누락: {eq}"


# ---------------------------------------------------------------------------
# D. INFO 등급 필터 (eq("log_level", "INFO"))
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_info_uses_level_filter(monkeypatch):
    from src.db.system_logs import purge_old_logs

    captured = _install(monkeypatch)
    await purge_old_logs()

    eq = captured.get("eq", {})
    info_eqs = eq.get("info", [])
    levels = {v for col, v in info_eqs if col == "log_level"}
    assert "INFO" in levels, f"INFO eq 누락: {eq}"


# ---------------------------------------------------------------------------
# E. 1회 cap 100,000 (limit 또는 range)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_applies_max_batch_cap(monkeypatch):
    from src.db.system_logs import purge_old_logs, MAX_PURGE_BATCH

    assert MAX_PURGE_BATCH == 100_000, f"MAX_PURGE_BATCH 상수 미정의 또는 다름: {MAX_PURGE_BATCH}"

    captured = _install(monkeypatch)
    await purge_old_logs()

    limit = captured.get("limit", {})
    # 두 그룹 모두 cap 적용
    assert limit.get("info") == 100_000, f"info limit 미적용: {limit}"
    assert limit.get("high") == 100_000, f"high limit 미적용: {limit}"


# ---------------------------------------------------------------------------
# F. cutoff None → RuntimeError (방어 코드)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_raises_when_cutoff_is_none(monkeypatch):
    """내부 헬퍼가 cutoff=None 받으면 RuntimeError raise.
    DELETE WHERE 조건 누락은 모든 행 삭제 위험 → 절대 차단.
    """
    from src.db.system_logs import _purge_by_cutoff

    _install(monkeypatch)
    with pytest.raises(RuntimeError, match="cutoff"):
        await _purge_by_cutoff(cutoff_iso=None, level_filter="INFO")


# ---------------------------------------------------------------------------
# G. INFO 영구 로그 `[log_retention]` prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_writes_retention_log_line(monkeypatch):
    from src.db import system_logs

    _install(monkeypatch, info_deleted=12, high_deleted=3)

    written: list[tuple[str, str]] = []

    async def fake_write_log(level: str, message: str):
        written.append((level, message))

    monkeypatch.setattr(system_logs, "write_log", fake_write_log)

    await system_logs.purge_old_logs()

    assert any(
        msg.startswith("[log_retention]") and "info_deleted=12" in msg and "high_deleted=3" in msg
        for _, msg in written
    ), f"[log_retention] 로그 미기록: {written}"
