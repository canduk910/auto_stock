"""사이클 175 Red — `_purge_by_cutoff` PostgREST row-cap silent 결함 항구 시정 (루프 배치).

배경 (메인 세션 진단 확정):
- 사이클 150 시정으로 `_purge_by_cutoff` 가 2-step 구조 (SELECT id LIMIT N → DELETE in_(ids)).
- 상수 `MAX_PURGE_BATCH = 100_000` 이나 Supabase PostgREST `db-max-rows=1000` 기본 cap 이
  SELECT 를 1000행으로 silent 절단 → 1회 호출당 최대 1000행만 삭제.
- `purge_old_logs()` 하루 1회(20:10 settlement) 호출 → INFO 30K+/일 생성 vs 1000/일 삭제 → 적체.
- 운영 증거: `[log_retention] info_deleted=1000 high_deleted=1000` 매일 정확히 1000.

사용자 승인 시정 = 루프 배치 (no-migration):
- `_purge_by_cutoff` 가 SELECT(id, limit=batch) + DELETE in_(ids) 를 drained 까지 루프.
- 안전 max iterations 가드 (런어웨이 차단) → 도달 시 graceful 종료 + 부분삭제 누적 반환.
- migration/RPC/PostgREST 설정 변경 금지. DELETE chain `.limit()` 미사용 보존 (사이클 6 결함 영구 차단).
- 반환 = 전 iteration 누적 삭제 수.

요구 행위 (G-175):
- LOOP-1 (HIGH): N > batch 시 전량 삭제 (루프 ceil(N/batch) 회)
- LOOP-2 (HIGH): DELETE in_ 호출 횟수 = ceil(rows/batch)
- CAP-1 (HIGH): max iterations 도달 시 graceful 종료 + 부분삭제 반환 (런어웨이 차단)
- EMPTY-1: 빈 결과 → 0 반환 + DELETE 0회
- NONE-1 (HIGH): cutoff_iso=None → RuntimeError 보존 (방어 코드 회귀 0)
- ACCUM-1: 누적 상한 cap 도달 시 종료
- AST-1 (HIGH): SELECT.limit + DELETE.in_ 2-step 구조 보존 + DELETE.limit 미사용 + 루프 존재
- RETURN-1: purge_old_logs 반환 스키마 + [log_retention] emit 보존 (1000 초과 값 정상)
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

# 사이클 M3b (2026-07-16) — Supabase→RDS 이전, `_purge_by_cutoff` 가 supabase-py 체인
# (select/eq/in_/lt/limit chain fake) → `pg.fetch`/`pg.execute` SQL 로 전환됨에 따라
# 본 파일의 Fake supabase 구조(_LoopSelectQuery 등)가 어떤 호출도 가로채지 못해 전량
# FAIL. 루프 배치(SELECT LIMIT 1000 → DELETE id=ANY drained) 실질 계약은
# `tests/unit/db/test_cycleM3b_system_logs_pg.py::test_purge_loop_drains_all_above_batch`
# / `test_purge_delete_uses_id_any_not_limit` / `test_purge_cap_max_iterations_graceful`
# / `test_purge_accum_cap_max_purge_batch` / `test_purge_cutoff_none_raises_runtime_error`
# / `test_purge_old_logs_schema_and_emit` 로 이관되어 회귀 가드 유지.
pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        reason="사이클M3b — _purge_by_cutoff supabase→pg 전환. 루프 배치 계약은 "
        "test_cycleM3b_system_logs_pg.py 로 이관",
        strict=False,
    ),
]

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 루프 지원 Fake supabase — 그룹별 ids 풀을 drained 까지 반환
# ---------------------------------------------------------------------------


class _LoopState:
    """단일 purge_old_logs 호출에서 info/high 두 그룹의 SELECT/DELETE 루프 상태."""

    def __init__(self, *, info_total: int, high_total: int, select_batch: int):
        # 남은 삭제 대상 행 수 (각 SELECT 가 최대 select_batch 만큼 반환)
        self.remaining = {"info": info_total, "high": high_total}
        self.select_batch = select_batch
        self.select_calls = {"info": 0, "high": 0}
        self.delete_calls = {"info": 0, "high": 0}
        self.delete_id_counts: dict[str, list[int]] = {"info": [], "high": []}
        self.limit_seen: dict[str, list[int]] = {"info": [], "high": []}
        self.lt_seen: dict[str, tuple[str, Any]] = {}
        self.tables: list[str] = []
        # 마지막 SELECT 가 반환한 ids (다음 DELETE in_ 에 전달될 것)
        self._last_select_ids: list[int] = []
        self._current_group = "info"


class _LoopSelectQuery:
    def __init__(self, state: _LoopState):
        self._state = state
        self._group = "info"

    def eq(self, col: str, val: Any):
        if col == "log_level" and val == "INFO":
            self._group = "info"
            self._state._current_group = "info"
        return self

    def in_(self, col: str, vals: list[Any]):
        if col == "log_level":
            self._group = "high"
            self._state._current_group = "high"
        return self

    def lt(self, col: str, val: Any):
        self._state.lt_seen[self._group] = (col, val)
        return self

    def limit(self, n: int):
        self._state.limit_seen.setdefault(self._group, []).append(n)
        self._limit = n
        return self

    def execute(self):
        group = self._group
        self._state.select_calls[group] += 1
        batch = getattr(self, "_limit", self._state.select_batch)
        # PostgREST row-cap 시뮬레이션: 요청 batch 와 무관하게 effective cap 1000.
        # 단 본 Fake 는 select_batch (구현이 정직하게 1000 요청) 를 effective 로 사용.
        effective = min(batch, self._state.select_batch)
        take = min(effective, self._state.remaining[group])
        ids = list(range(1, take + 1))
        self._state.remaining[group] -= take
        self._state._last_select_ids = ids
        return type("R", (), {"data": [{"id": i} for i in ids], "count": take})()


class _LoopDeleteQuery:
    def __init__(self, state: _LoopState):
        self._state = state
        self._ids: list[int] = []

    def in_(self, col: str, vals: list[Any]):
        self._ids = list(vals)
        return self

    def limit(self, n: int):
        # 사이클 6 결함 영역 — DELETE chain .limit() 호출되면 안 됨.
        raise AssertionError(
            "DELETE chain .limit() 미사용 보존 위반 (사이클 6 AttributeError 결함 영구 차단)"
        )

    def execute(self):
        group = self._state._current_group
        self._state.delete_calls[group] += 1
        self._state.delete_id_counts[group].append(len(self._ids))
        rows = [{"id": i} for i in self._ids]
        return type("R", (), {"data": rows, "count": len(self._ids)})()


class _LoopTable:
    def __init__(self, state: _LoopState):
        self._state = state

    def select(self, *cols: str):
        return _LoopSelectQuery(self._state)

    def delete(self):
        return _LoopDeleteQuery(self._state)

    def insert(self, data):
        class _Inserted:
            def execute(self_inner):
                return type("R", (), {"data": [], "count": 0})()

        return _Inserted()


class _LoopSupabase:
    def __init__(self, state: _LoopState):
        self._state = state

    def table(self, name: str):
        self._state.tables.append(name)
        return _LoopTable(self._state)


def _install_loop(
    monkeypatch: pytest.MonkeyPatch,
    *,
    info_total: int = 0,
    high_total: int = 0,
    select_batch: int | None = None,
) -> _LoopState:
    from src.db import system_logs

    if select_batch is None:
        # 구현이 노출하는 per-iteration SELECT 배치 크기 (없으면 1000 가정)
        select_batch = getattr(system_logs, "PURGE_SELECT_BATCH", 1000)

    state = _LoopState(
        info_total=info_total, high_total=high_total, select_batch=select_batch
    )
    monkeypatch.setattr(system_logs, "supabase", _LoopSupabase(state))
    return state


# ---------------------------------------------------------------------------
# G-175-LOOP-1 (HIGH) — N > batch 전량 삭제 (루프)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop1_purges_all_rows_above_batch_size(monkeypatch):
    """cutoff 통과 행 2500 (> batch 1000) → 전량 삭제 (단일 그룹)."""
    from src.db.system_logs import _purge_by_cutoff

    state = _install_loop(monkeypatch, info_total=2500)
    batch = state.select_batch

    deleted = await _purge_by_cutoff(cutoff_iso="2026-05-18T20:15:00+09:00", level_filter="INFO")

    assert deleted == 2500, f"전량 삭제 실패: {deleted} (remaining={state.remaining})"
    assert state.remaining["info"] == 0, "잔여 행 존재 — 루프 미완료"
    # 2500 / batch → ceil
    import math

    expected_iters = math.ceil(2500 / batch)
    assert state.delete_calls["info"] == expected_iters, (
        f"DELETE 호출 횟수 불일치: {state.delete_calls['info']} != {expected_iters}"
    )


# ---------------------------------------------------------------------------
# G-175-LOOP-2 (HIGH) — DELETE in_ 호출 횟수 = ceil(rows/batch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop2_delete_call_count_equals_ceil(monkeypatch):
    """rows=2001 → batch 1000 기준 3회 DELETE (1000+1000+1)."""
    import math

    from src.db.system_logs import _purge_by_cutoff

    state = _install_loop(monkeypatch, info_total=2001)
    batch = state.select_batch

    deleted = await _purge_by_cutoff(cutoff_iso="2026-05-18T20:15:00+09:00", level_filter="INFO")

    assert deleted == 2001
    expected = math.ceil(2001 / batch)
    assert state.delete_calls["info"] == expected, (
        f"{state.delete_calls['info']} != {expected}"
    )
    # 각 DELETE 의 ids 길이 = batch, batch, ..., 잔여
    counts = state.delete_id_counts["info"]
    assert counts[:-1] == [batch] * (expected - 1), f"중간 배치 크기 != batch: {counts}"
    assert counts[-1] == 2001 - batch * (expected - 1), f"마지막 배치 잔여 != : {counts}"


# ---------------------------------------------------------------------------
# G-175-CAP-1 (HIGH) — max iterations 도달 시 graceful 종료 + 부분삭제 반환
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cap1_max_iterations_graceful_partial(monkeypatch):
    """무한히 많은 행 + 작은 PURGE_MAX_ITERATIONS patch → 런어웨이 차단 + 부분삭제."""
    from src.db import system_logs

    # 매우 큰 행 수 (드레인 불가) — max iterations 가 먼저 끊어야 함
    state = _install_loop(monkeypatch, info_total=10_000_000)
    batch = state.select_batch

    # 안전 가드 상수 존재 의무 + 작은 값으로 patch (런어웨이 검증)
    assert hasattr(system_logs, "PURGE_MAX_ITERATIONS"), (
        "PURGE_MAX_ITERATIONS 런어웨이 안전 상수 미정의"
    )
    monkeypatch.setattr(system_logs, "PURGE_MAX_ITERATIONS", 5)

    deleted = await system_logs._purge_by_cutoff(
        cutoff_iso="2026-05-18T20:15:00+09:00", level_filter="INFO"
    )

    # 5 iteration × batch 만큼만 삭제 후 graceful 종료 (예외 0)
    assert deleted == 5 * batch, f"max iterations 부분삭제 != 5*batch: {deleted}"
    assert state.delete_calls["info"] == 5, f"루프 5회 초과/미달: {state.delete_calls['info']}"
    assert state.remaining["info"] > 0, "여전히 잔여 존재해야 함 (런어웨이 차단 의미)"


# ---------------------------------------------------------------------------
# G-175-EMPTY-1 — 빈 결과 → 0 반환 + DELETE 0회
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty1_no_rows_returns_zero_no_delete(monkeypatch):
    from src.db.system_logs import _purge_by_cutoff

    state = _install_loop(monkeypatch, info_total=0)

    deleted = await _purge_by_cutoff(cutoff_iso="2026-05-18T20:15:00+09:00", level_filter="INFO")

    assert deleted == 0
    assert state.delete_calls["info"] == 0, "빈 결과인데 DELETE 호출됨"
    assert state.select_calls["info"] == 1, "빈 결과 확인 위해 SELECT 정확히 1회"


# ---------------------------------------------------------------------------
# G-175-NONE-1 (HIGH) — cutoff_iso=None → RuntimeError 보존
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_none1_cutoff_none_raises_runtime_error(monkeypatch):
    """방어 코드 회귀 0 — WHERE cutoff 누락 시 모든 행 삭제 위험 절대 차단."""
    from src.db.system_logs import _purge_by_cutoff

    _install_loop(monkeypatch)
    with pytest.raises(RuntimeError, match="cutoff"):
        await _purge_by_cutoff(cutoff_iso=None, level_filter="INFO")


# ---------------------------------------------------------------------------
# G-175-ACCUM-1 — 누적 상한 cap (MAX_PURGE_BATCH) 도달 시 종료
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accum1_cumulative_cap_terminates(monkeypatch):
    """MAX_PURGE_BATCH 누적 상한 cap 도달 시 종료 (단일 호출 폭주 안전)."""
    from src.db import system_logs

    # MAX_PURGE_BATCH 보존 의무 (기존 E 케이스 + CLAUDE.md 명세)
    assert system_logs.MAX_PURGE_BATCH == 100_000, (
        f"MAX_PURGE_BATCH 상수 변경 금지: {system_logs.MAX_PURGE_BATCH}"
    )

    state = _install_loop(monkeypatch, info_total=10_000_000)
    batch = state.select_batch

    # PURGE_MAX_ITERATIONS 는 충분히 크게 (누적 상한이 먼저 끊어야 함)
    monkeypatch.setattr(system_logs, "PURGE_MAX_ITERATIONS", 1_000_000)

    deleted = await system_logs._purge_by_cutoff(
        cutoff_iso="2026-05-18T20:15:00+09:00", level_filter="INFO"
    )

    # 누적 상한 = MAX_PURGE_BATCH (100_000). batch 1000 → 100 iteration 후 종료.
    assert deleted == system_logs.MAX_PURGE_BATCH, (
        f"누적 상한 cap != MAX_PURGE_BATCH: {deleted}"
    )
    assert state.delete_calls["info"] == system_logs.MAX_PURGE_BATCH // batch, (
        f"누적 상한 도달 iteration 수 불일치: {state.delete_calls['info']}"
    )


# ---------------------------------------------------------------------------
# G-175-RETURN-1 — purge_old_logs 반환 스키마 + emit 보존 (1000 초과 값 정상)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_return1_purge_old_logs_schema_and_emit(monkeypatch):
    """purge_old_logs 반환 dict + [log_retention] emit 보존, info_deleted=2500 (1000 초과)."""
    from src.db import system_logs

    _install_loop(monkeypatch, info_total=2500, high_total=1500)

    written: list[tuple[str, str]] = []

    async def fake_write_log(level: str, message: str):
        written.append((level, message))

    monkeypatch.setattr(system_logs, "write_log", fake_write_log)

    result = await system_logs.purge_old_logs()

    assert set(result.keys()) >= {"info_deleted", "high_deleted", "elapsed_ms"}
    assert result["info_deleted"] == 2500, f"1000 초과 값 미반환 (cap 잔존): {result}"
    assert result["high_deleted"] == 1500, f"high 1000 초과 값 미반환: {result}"
    assert result["elapsed_ms"] >= 0

    assert any(
        msg.startswith("[log_retention]")
        and "info_deleted=2500" in msg
        and "high_deleted=1500" in msg
        for _, msg in written
    ), f"[log_retention] emit 미보존/cap 잔존: {written}"


# ---------------------------------------------------------------------------
# G-175-AST-1 (HIGH) — 2-step 구조 + DELETE.limit 미사용 + 루프 존재
# ---------------------------------------------------------------------------


def _get_purge_source() -> str:
    from src.db import system_logs

    return inspect.getsource(system_logs._purge_by_cutoff)


def test_ast1_two_step_loop_structure_preserved():
    """`_purge_by_cutoff` = SELECT.limit + DELETE.in_ 2-step + 루프 존재 + DELETE.limit 미사용."""
    src = _get_purge_source()
    tree = ast.parse(src)

    func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_purge_by_cutoff":
            func = node
            break
    assert func is not None, "_purge_by_cutoff async 함수 부재"

    # (1) 루프 존재 (drained 까지 반복)
    has_loop = any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(func))
    assert has_loop, "drained 루프 (for/while) 부재 — 단발 호출 잔존"

    # (2) SELECT chain .select(...) 존재
    method_calls: list[str] = []
    for n in ast.walk(func):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            method_calls.append(n.func.attr)
    assert "select" in method_calls, "select chain 부재"
    assert "delete" in method_calls, "delete chain 부재"
    assert "in_" in method_calls, "DELETE in_(ids) 2-step 부재"
    assert "limit" in method_calls, "SELECT limit 부재"

    # (3) DELETE chain .limit() 미사용 보존 — `delete()....limit(` 패턴 0건
    #     소스 문자열 정적 검사 (사이클 6 AttributeError 결함 영구 차단)
    # delete().in_(...) 또는 delete().limit(...) 형태에서 delete 직후 limit 금지.
    # 간단 가드: 소스에 'delete().limit' / 'delete()\n.limit' 류 인접 패턴 없음.
    compact = src.replace(" ", "").replace("\n", "")
    assert "delete().limit(" not in compact, (
        "DELETE chain .limit() 잔존 — 사이클 6 결함 재도입 (PostgREST 미지원)"
    )


def test_ast1b_max_purge_batch_constant_preserved():
    """MAX_PURGE_BATCH 상수 보존 (기존 E 케이스 + CLAUDE.md 명세 회귀 0)."""
    from src.db import system_logs

    assert hasattr(system_logs, "MAX_PURGE_BATCH")
    assert system_logs.MAX_PURGE_BATCH == 100_000


def test_ast1c_purge_select_batch_is_honest_1000():
    """PURGE_SELECT_BATCH = 1000 (정직 — PostgREST effective cap 과 정합)."""
    from src.db import system_logs

    assert hasattr(system_logs, "PURGE_SELECT_BATCH"), (
        "PURGE_SELECT_BATCH 신규 상수 미정의 (per-iteration SELECT 배치)"
    )
    # PostgREST db-max-rows=1000 effective cap 이므로 1000 이 정직.
    assert system_logs.PURGE_SELECT_BATCH == 1000, (
        f"PURGE_SELECT_BATCH != 1000 (PostgREST cap 정합): {system_logs.PURGE_SELECT_BATCH}"
    )
