"""사이클 M3b (Red) — src/db/system_logs.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — 분석·관찰 + main seam).

⚠️ **로깅 척추 — 극도 주의**. system_logs 는 관찰성 척추이자 매매 프로세스 안전망.
전환은 supabase-py 체인(+asyncio.to_thread) → `pg.*` 이나, **다음 3대 불변식을 절대 보존**:
1. **never-raise** (사이클190): write_log INSERT 실패 시 어떤 예외도 호출자에 전파 금지 →
   `logger.debug("[write_log_failed]")` 단독 (WARNING 이상 금지 = `_DbLogHandler` 재귀 차단).
2. **KST timestamp** (사이클65 H2): INSERT payload `timestamp` = KST `+09:00` (asyncpg 는
   TIMESTAMPTZ 를 datetime 으로 바인딩 → `datetime.fromisoformat(now_kst_iso())`).
3. **purge 루프 배치** (사이클175): SELECT id LIMIT 1000 → DELETE WHERE id = ANY 을 drained
   까지 루프 + 안전 cap 3중. **cutoff_iso=None → RuntimeError 절대 보존**.

함수 계약 (시그니처·반환형·graceful 폴백) 100% 보존 → 호출부(scheduler/routes/72곳) diff 0.

이 파일 = system_logs.py 자체 pg 전환 단위 계약 (mock `pg.*`).
`_DbLogHandler` / lifespan seam 은 `tests/unit/main/test_cycleM3b_main_seam_pg.py` 참조.

Red 유효성: production 미변경(supabase 체인) → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

import ast
import inspect
import logging
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _neutralize_supabase(monkeypatch):
    """현행 supabase(asyncio.to_thread) 경로 중립화 — Red 단계 실 DNS hang/노이즈 차단.

    Red 시점 production 은 supabase 를 호출 → 실 Supabase 로 나가 httpx ConnectError.
    to_thread 를 즉시 예외로 중립화 → 테스트가 *계약 단언* 으로 FAIL(의도 선명).
    Green 전환 후엔 무해(심볼 사라짐, raising=False).

    ⚠️ write_log never-raise 계약 테스트는 supabase 예외를 삼켜야 하므로, 이 중립화가
    write_log 를 태울 때 예외를 raise 하면 never-raise 가 무조건 PASS 로 오탐될 수 있다.
    → never-raise 테스트는 `pg.execute` 를 명시적으로 raise 시켜 검증(중립화와 독립).
    """
    from src.db import system_logs as _mod

    async def _fast_to_thread(fn, *a, **k):
        raise Exception("to_thread 중립화 (M3b Red)")

    monkeypatch.setattr(_mod, "supabase", None, raising=False)
    monkeypatch.setattr(_mod.asyncio, "to_thread", _fast_to_thread, raising=False)
    yield


# ---------------------------------------------------------------------------
# 헬퍼 — 발화 경로 SQL·인자 수집 (M3a 패턴 답습, Green 구현 자유도)
# ---------------------------------------------------------------------------
def _collect_sql(pg_mod) -> list[str]:
    from unittest.mock import AsyncMock

    sqls: list[str] = []
    for name in ("fetchrow", "execute", "fetch", "fetchval"):
        m = getattr(pg_mod, name, None)
        if isinstance(m, AsyncMock) and m.await_args is not None:
            sqls.append(m.await_args.args[0])
    return sqls


def _all_call_sqls(mock: AsyncMock) -> list[str]:
    """AsyncMock 의 전 호출(await_args_list)에서 첫 인자(SQL) 수집."""
    return [c.args[0] for c in mock.await_args_list if c.args]


def _all_call_args(mock: AsyncMock) -> list[tuple]:
    """AsyncMock 의 전 호출에서 바인딩 인자(args[1:]) 수집."""
    return [c.args[1:] for c in mock.await_args_list if c.args]


# ===========================================================================
# write_log — pg.execute INSERT + KST datetime 바인딩 + never-raise
# ===========================================================================
@pytest.mark.asyncio
async def test_write_log_uses_pg_execute_insert():
    """write_log → pg.execute("INSERT INTO system_logs ...") (supabase 체인 폐기)."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        result = await _mod.write_log("INFO", "테스트 로그 메시지")

    assert result is None, "write_log 반환은 항상 None (시그니처 불변)."
    pg_mod.execute.assert_awaited()
    sql = pg_mod.execute.await_args.args[0]
    assert "INSERT INTO system_logs" in sql, "INSERT INTO system_logs SQL 누락."
    assert "log_level" in sql and "message" in sql and "timestamp" in sql, (
        "log_level/message/timestamp 컬럼 바인딩 누락."
    )


@pytest.mark.asyncio
async def test_write_log_binds_level_and_message():
    """write_log → log_level/message 바인딩 값 보존."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await _mod.write_log("WARNING", "특정 메시지 XYZ")

    args = pg_mod.execute.await_args.args[1:]
    assert "WARNING" in args, "log_level 바인딩 누락."
    assert "특정 메시지 XYZ" in args, "message 바인딩 누락."


@pytest.mark.asyncio
async def test_write_log_timestamp_is_kst_datetime():
    """⚠️ 사이클65 H2 — timestamp 는 KST datetime 바인딩 (asyncpg TIMESTAMPTZ = datetime, str 금지).

    supabase 시절 payload["timestamp"] 는 `datetime.now(KST).isoformat()` str 이었으나,
    asyncpg TIMESTAMPTZ 컬럼은 datetime 을 바인딩해야 한다(M1 패턴 2). KST(+09:00) 명시
    보존 — datetime.fromisoformat(now_kst_iso()) → tzinfo utcoffset == 9h.
    """
    from datetime import timedelta, timezone

    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await _mod.write_log("INFO", "KST 검증 메시지")

    args = pg_mod.execute.await_args.args[1:]
    dt_args = [a for a in args if isinstance(a, datetime)]
    assert dt_args, "timestamp datetime 바인딩 누락 (str 금지 — asyncpg TIMESTAMPTZ)."
    ts = dt_args[0]
    assert ts.tzinfo is not None, "timestamp 는 tz-aware 여야 함 (KST 명시)."
    assert ts.utcoffset() == timedelta(hours=9), (
        f"KST(+09:00) 명시 의무 (사이클53 컨벤션): utcoffset={ts.utcoffset()}"
    )


@pytest.mark.asyncio
async def test_write_log_never_raises_on_pg_exception():
    """⚠️ 사이클190 never-raise — pg.execute 가 raise 해도 write_log 는 미전파(return None).

    운영 크래시 재현: INSERT 가 연결 예외/일반 예외 raise 해도 write_log 는 절대 전파 안 함.
    """
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=Exception("connection lost"))
        # 예외 전파되면 이 await 에서 raise → 테스트 실패
        result = await _mod.write_log("INFO", "실패 케이스")

    assert result is None, "write_log never-raise (사이클190) — 반환 None."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        ConnectionError("네트워크 오류"),
        RuntimeError("일반 런타임"),
        ValueError("직렬화 오류"),
        TimeoutError("타임아웃"),
    ],
)
async def test_write_log_never_raises_various_exceptions(exc):
    """다양한 예외 계열 미전파 (never-raise 보편 계약)."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=exc)
        result = await _mod.write_log("ERROR", "메시지")

    assert result is None


@pytest.mark.asyncio
async def test_write_log_failure_logs_debug_only_no_warning(caplog):
    """⚠️ 사이클190 재귀 차단 — 실패 시 logger.debug 만 발화 (WARNING 이상 금지)."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=Exception("boom"))
        with caplog.at_level(logging.DEBUG, logger="src.db.system_logs"):
            await _mod.write_log("INFO", "실패 로그")

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    high_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(debug_records) >= 1, "실패 시 logger.debug 최소 1회 발화 의무."
    assert not high_records, (
        f"WARNING 이상 발화 금지 (_DbLogHandler 재귀/무한 INSERT 위험): "
        f"{[r.getMessage() for r in high_records]}"
    )


# ===========================================================================
# safe_write_log — 사이클56-E graceful 변형 보존
# ===========================================================================
@pytest.mark.asyncio
async def test_safe_write_log_graceful_on_pg_exception(caplog):
    """safe_write_log → write_log(본체) → pg.execute 실패 end-to-end graceful (never-raise 이중 보호)."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=Exception("connection lost"))
        with caplog.at_level(logging.DEBUG, logger="src.db.system_logs"):
            await _mod.safe_write_log("INFO", "safe 통합 메시지")

    high_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not high_records, "safe_write_log 통합 경로도 WARNING 이상 발화 금지."


# ===========================================================================
# get_logs — SELECT + count="exact"→fetchval + KST 기간 필터 + 페이징
# ===========================================================================
@pytest.mark.asyncio
async def test_get_logs_uses_pg_fetch_and_fetchval_count():
    """get_logs → pg.fetch(items) + pg.fetchval(count) (count="exact"→별도 fetchval)."""
    from src.db import system_logs as _mod

    items = [{"id": 1, "log_level": "INFO", "message": "a", "timestamp": "2026-07-16T10:00:00+09:00"}]
    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=items)
        pg_mod.fetchval = AsyncMock(return_value=1)
        out = await _mod.get_logs(limit=10)

    assert out["items"] == items, "items 반환 계약."
    assert out["total"] == 1, "total 은 fetchval count 반환 계약."
    assert out["total_pages"] == 1
    pg_mod.fetch.assert_awaited()
    pg_mod.fetchval.assert_awaited()
    count_sql = pg_mod.fetchval.await_args.args[0].upper()
    assert "COUNT(" in count_sql and "SYSTEM_LOGS" in count_sql, (
        "count 는 별도 SELECT count(*) FROM system_logs 로 조회 (count=exact 대응)."
    )


@pytest.mark.asyncio
async def test_get_logs_orders_by_timestamp_desc_with_limit_offset():
    """get_logs → ORDER BY timestamp DESC + LIMIT/OFFSET 페이징 (range → LIMIT/OFFSET)."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchval = AsyncMock(return_value=0)
        await _mod.get_logs(limit=20, page=3, size=20)

    sql = pg_mod.fetch.await_args.args[0].upper()
    assert "ORDER BY" in sql and "DESC" in sql, "timestamp DESC 정렬 누락."
    assert "LIMIT" in sql and "OFFSET" in sql, "LIMIT/OFFSET 페이징 누락 (range 대체)."
    # offset = (page-1)*size = 40 바인딩 존재
    passed = pg_mod.fetch.await_args.args[1:]
    assert 40 in passed, f"offset=(page-1)*size=40 바인딩 누락: {passed}"


@pytest.mark.asyncio
async def test_get_logs_level_and_date_filters_bind_kst():
    """get_logs → log_level 필터 + from_date/to_date KST +09:00 경계 바인딩."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchval = AsyncMock(return_value=0)
        await _mod.get_logs(
            log_level="ERROR",
            from_date=date(2026, 7, 15),
            to_date=date(2026, 7, 16),
        )

    passed = list(pg_mod.fetch.await_args.args[1:])
    passed_str = [str(a) for a in passed]
    assert "ERROR" in passed, "log_level 필터 바인딩 누락."
    assert any("2026-07-15T00:00:00+09:00" in s for s in passed_str), (
        "from_date KST 00:00:00+09:00 경계 바인딩 누락 (TZ 없으면 KST 00~09시 누락)."
    )
    assert any("2026-07-16T23:59:59.999999+09:00" in s for s in passed_str), (
        "to_date KST 23:59:59.999999+09:00 경계 바인딩 누락."
    )
    # count 쿼리도 동일 필터 반영 (동봉 count 정합)
    count_passed_str = [str(a) for a in pg_mod.fetchval.await_args.args[1:]]
    assert "ERROR" in [str(a) for a in pg_mod.fetchval.await_args.args[1:]] or any(
        "ERROR" in s for s in count_passed_str
    ), "count 쿼리에도 log_level 필터 반영 의무 (total 정합)."


@pytest.mark.asyncio
async def test_get_logs_total_pages_ceil():
    """total_pages = ceil(total / size). total=25, size=10 → 3."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"id": i} for i in range(10)])
        pg_mod.fetchval = AsyncMock(return_value=25)
        out = await _mod.get_logs(limit=10, page=1, size=10)

    assert out["total"] == 25
    assert out["total_pages"] == 3, "ceil(25/10)=3 페이징 계산 계약 보존."


# ===========================================================================
# search_logs — ILIKE $1 + level ALL/None + start/end + clamp + 빈 q ValueError
# ===========================================================================
@pytest.mark.asyncio
async def test_search_logs_uses_ilike_pattern():
    """search_logs → message ILIKE $1 (`%q%`) — ilike("message", pattern) 대체."""
    from src.db import system_logs as _mod

    rows = [{"id": 1, "message": "매수 신호", "log_level": "INFO"}]
    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        pg_mod.fetchval = AsyncMock(return_value=1)
        out = await _mod.search_logs("매수")

    assert out["logs"] == rows, "logs 반환 계약."
    assert out["total"] == 1
    assert out["has_more"] is False
    sql = pg_mod.fetch.await_args.args[0].upper()
    assert "ILIKE" in sql, "message ILIKE 패턴 매칭 누락."
    passed = pg_mod.fetch.await_args.args[1:]
    assert any(isinstance(a, str) and "%매수%" in a for a in passed), (
        "ILIKE 패턴 `%q%` 바인딩 누락."
    )


@pytest.mark.asyncio
async def test_search_logs_empty_q_raises_value_error():
    """빈 q → ValueError (라우트 이중 안전망 계약 보존)."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchval = AsyncMock(return_value=0)
        with pytest.raises(ValueError):
            await _mod.search_logs("   ")


@pytest.mark.asyncio
async def test_search_logs_limit_clamp_max_1000():
    """limit > 1000 → 1000 clamp (LIMIT 바인딩 확인)."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchval = AsyncMock(return_value=0)
        await _mod.search_logs("x", limit=99999)

    passed = pg_mod.fetch.await_args.args[1:]
    assert 1000 in passed, f"limit clamp 1000 바인딩 누락: {passed}"


@pytest.mark.asyncio
async def test_search_logs_level_all_no_filter():
    """level='ALL' → log_level 무필터 (level 바인딩 없음)."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchval = AsyncMock(return_value=0)
        await _mod.search_logs("x", level="ALL")

    passed = pg_mod.fetch.await_args.args[1:]
    assert "ALL" not in passed, "level='ALL' 은 무필터 — 'ALL' 을 log_level 로 바인딩 금지."


@pytest.mark.asyncio
async def test_search_logs_level_and_range_bind():
    """level 지정 + start/end → log_level = $ + timestamp >= $ + timestamp <= $ 바인딩."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchval = AsyncMock(return_value=0)
        await _mod.search_logs(
            "x",
            level="ERROR",
            start="2026-07-15T00:00:00+09:00",
            end="2026-07-16T23:59:59+09:00",
        )

    passed = pg_mod.fetch.await_args.args[1:]
    assert "ERROR" in passed, "level 필터 바인딩 누락."
    assert "2026-07-15T00:00:00+09:00" in passed, "start gte 바인딩 누락."
    assert "2026-07-16T23:59:59+09:00" in passed, "end lte 바인딩 누락."


@pytest.mark.asyncio
async def test_search_logs_has_more_true_when_total_exceeds():
    """has_more = total > len(logs)."""
    from src.db import system_logs as _mod

    rows = [{"id": i} for i in range(200)]
    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        pg_mod.fetchval = AsyncMock(return_value=350)
        out = await _mod.search_logs("x", limit=200)

    assert out["has_more"] is True, "total(350) > len(logs)(200) → has_more True."


# ===========================================================================
# _purge_by_cutoff — 루프 배치 (SELECT id → DELETE = ANY) + cutoff None RuntimeError
# ===========================================================================
@pytest.mark.asyncio
async def test_purge_cutoff_none_raises_runtime_error():
    """⚠️ 사이클175 절대 보존 — cutoff_iso=None → RuntimeError (WHERE 누락 사고 차단)."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.execute = AsyncMock(return_value="DELETE 0")
        with pytest.raises(RuntimeError, match="cutoff"):
            await _mod._purge_by_cutoff(cutoff_iso=None, level_filter="INFO")


@pytest.mark.asyncio
async def test_purge_loop_drains_all_above_batch():
    """⚠️ 사이클175 루프 배치 — 2500 행(> batch 1000) 전량 삭제 (drained 루프).

    pg.fetch(SELECT id LIMIT 1000) 가 1000/1000/500 로 반환 → pg.execute(DELETE = ANY) 3회.
    """
    import math

    from src.db import system_logs as _mod

    batch = _mod.PURGE_SELECT_BATCH
    remaining = {"n": 2500}

    async def _fetch_ids(sql, *args):
        take = min(batch, remaining["n"])
        remaining["n"] -= take
        return [{"id": i} for i in range(take)]

    delete_calls = {"n": 0}
    delete_id_counts: list[int] = []

    async def _execute(sql, *args):
        # DELETE ... WHERE id = ANY($1) — args[0] 은 id 리스트
        delete_calls["n"] += 1
        ids = args[0] if args else []
        delete_id_counts.append(len(ids))
        return f"DELETE {len(ids)}"

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=_fetch_ids)
        pg_mod.execute = AsyncMock(side_effect=_execute)
        deleted = await _mod._purge_by_cutoff(
            cutoff_iso="2026-07-14T20:15:00+09:00", level_filter="INFO"
        )

    assert deleted == 2500, f"전량 삭제 실패: {deleted}"
    expected_iters = math.ceil(2500 / batch)
    assert delete_calls["n"] == expected_iters, (
        f"DELETE 호출 횟수 불일치: {delete_calls['n']} != {expected_iters}"
    )
    assert delete_id_counts[:-1] == [batch] * (expected_iters - 1), (
        f"중간 배치 크기 != batch: {delete_id_counts}"
    )


@pytest.mark.asyncio
async def test_purge_delete_uses_id_any_not_limit():
    """⚠️ 사이클6 영구 차단 — DELETE 는 id = ANY 리스트 방식 (DELETE .limit 미사용).

    asyncpg 전환 후 DELETE 는 `WHERE id = ANY($1::bigint[])` — 사이클6 supabase DELETE
    chain .limit AttributeError 결함이 SQL 로는 재현 불가하나, id 리스트 기반 삭제 계약 보존.
    """
    from src.db import system_logs as _mod

    remaining = {"n": 5}
    captured_delete_args: list = []

    async def _fetch_ids(sql, *args):
        take = min(_mod.PURGE_SELECT_BATCH, remaining["n"])
        remaining["n"] -= take
        return [{"id": 100 + i} for i in range(take)]

    async def _execute(sql, *args):
        captured_delete_args.append((sql, args))
        return "DELETE 5"

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=_fetch_ids)
        pg_mod.execute = AsyncMock(side_effect=_execute)
        await _mod._purge_by_cutoff(
            cutoff_iso="2026-07-14T20:15:00+09:00", level_filter="INFO"
        )

    assert captured_delete_args, "DELETE 미발화."
    sql, args = captured_delete_args[0]
    assert "DELETE FROM system_logs" in sql, "DELETE FROM system_logs SQL 누락."
    assert "ANY" in sql.upper(), "DELETE ... WHERE id = ANY($) 패턴 누락 (id 리스트 삭제)."
    assert isinstance(args[0], list) and args[0] == [100, 101, 102, 103, 104], (
        "DELETE id 리스트 바인딩 누락."
    )


@pytest.mark.asyncio
async def test_purge_empty_returns_zero_no_delete():
    """빈 결과 → 0 반환 + DELETE 0회 + SELECT 1회."""
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.execute = AsyncMock(return_value="DELETE 0")
        deleted = await _mod._purge_by_cutoff(
            cutoff_iso="2026-07-14T20:15:00+09:00", level_filter="INFO"
        )

    assert deleted == 0
    assert pg_mod.execute.await_count == 0, "빈 결과인데 DELETE 호출됨."
    assert pg_mod.fetch.await_count == 1, "빈 결과 확인 위해 SELECT 정확히 1회."


@pytest.mark.asyncio
async def test_purge_high_level_filter_uses_in_any():
    """level_filter 가 리스트(HIGH_LEVELS) → SELECT WHERE log_level = ANY($) 바인딩."""
    from src.db import system_logs as _mod

    captured_select: list = []

    async def _fetch_ids(sql, *args):
        captured_select.append((sql, args))
        return []  # 즉시 drained

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=_fetch_ids)
        pg_mod.execute = AsyncMock(return_value="DELETE 0")
        await _mod._purge_by_cutoff(
            cutoff_iso="2026-07-14T20:15:00+09:00",
            level_filter=list(_mod.HIGH_LEVELS),
        )

    assert captured_select, "SELECT 미발화."
    sql, args = captured_select[0]
    assert "log_level" in sql.lower(), "log_level 필터 누락."
    # HIGH_LEVELS 리스트가 ANY 로 바인딩
    joined_args = [a for a in args]
    assert any(
        isinstance(a, (list, tuple)) and set(a) == set(_mod.HIGH_LEVELS)
        for a in joined_args
    ), f"HIGH_LEVELS = ANY($) 바인딩 누락: {joined_args}"


@pytest.mark.asyncio
async def test_purge_cap_max_iterations_graceful(monkeypatch):
    """⚠️ 사이클175 CAP-1 — PURGE_MAX_ITERATIONS 도달 시 graceful 종료 + 부분삭제."""
    from src.db import system_logs as _mod

    batch = _mod.PURGE_SELECT_BATCH
    remaining = {"n": 10_000_000}  # 드레인 불가

    async def _fetch_ids(sql, *args):
        take = min(batch, remaining["n"])
        remaining["n"] -= take
        return [{"id": i} for i in range(take)]

    delete_calls = {"n": 0}

    async def _execute(sql, *args):
        delete_calls["n"] += 1
        ids = args[0] if args else []
        return f"DELETE {len(ids)}"

    monkeypatch.setattr(_mod, "PURGE_MAX_ITERATIONS", 5)
    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=_fetch_ids)
        pg_mod.execute = AsyncMock(side_effect=_execute)
        deleted = await _mod._purge_by_cutoff(
            cutoff_iso="2026-07-14T20:15:00+09:00", level_filter="INFO"
        )

    assert deleted == 5 * batch, f"max iterations 부분삭제 != 5*batch: {deleted}"
    assert delete_calls["n"] == 5, f"루프 5회 초과/미달: {delete_calls['n']}"
    assert remaining["n"] > 0, "런어웨이 차단 의미 — 잔여 존재."


@pytest.mark.asyncio
async def test_purge_accum_cap_max_purge_batch(monkeypatch):
    """⚠️ 사이클175 ACCUM-1 — MAX_PURGE_BATCH(100_000) 누적 상한 cap 도달 시 종료."""
    from src.db import system_logs as _mod

    assert _mod.MAX_PURGE_BATCH == 100_000, "MAX_PURGE_BATCH 상수 변경 금지."
    batch = _mod.PURGE_SELECT_BATCH
    remaining = {"n": 10_000_000}

    async def _fetch_ids(sql, *args):
        take = min(batch, remaining["n"])
        remaining["n"] -= take
        return [{"id": i} for i in range(take)]

    async def _execute(sql, *args):
        ids = args[0] if args else []
        return f"DELETE {len(ids)}"

    monkeypatch.setattr(_mod, "PURGE_MAX_ITERATIONS", 1_000_000)
    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=_fetch_ids)
        pg_mod.execute = AsyncMock(side_effect=_execute)
        deleted = await _mod._purge_by_cutoff(
            cutoff_iso="2026-07-14T20:15:00+09:00", level_filter="INFO"
        )

    assert deleted == _mod.MAX_PURGE_BATCH, f"누적 상한 cap != MAX_PURGE_BATCH: {deleted}"


# ===========================================================================
# purge_old_logs — 반환 스키마 + retention 경계 + [log_retention] emit 보존
# ===========================================================================
@pytest.mark.asyncio
async def test_purge_old_logs_schema_and_emit(monkeypatch):
    """purge_old_logs → {info_deleted, high_deleted, elapsed_ms} + [log_retention] emit 보존."""
    from src.db import system_logs as _mod

    # info 2500, high 1500 을 두 그룹으로 반환하는 fetch 시뮬 (log_level 별 분리)
    state = {"info": 2500, "high": 1500}

    async def _fetch_ids(sql, *args):
        # SELECT id ... WHERE log_level = 'INFO' 또는 log_level = ANY(HIGH)
        # 바인딩 args 로 그룹 판정
        group = "info"
        for a in args:
            if a == "INFO":
                group = "info"
            elif isinstance(a, (list, tuple)) and set(a) == set(_mod.HIGH_LEVELS):
                group = "high"
        take = min(_mod.PURGE_SELECT_BATCH, state[group])
        state[group] -= take
        return [{"id": i} for i in range(take)]

    async def _execute(sql, *args):
        ids = args[0] if args else []
        return f"DELETE {len(ids)}"

    written: list[tuple[str, str]] = []

    async def fake_write_log(level: str, message: str):
        written.append((level, message))

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=_fetch_ids)
        pg_mod.execute = AsyncMock(side_effect=_execute)
        monkeypatch.setattr(_mod, "write_log", fake_write_log)
        result = await _mod.purge_old_logs()

    assert set(result.keys()) >= {"info_deleted", "high_deleted", "elapsed_ms"}
    assert result["info_deleted"] == 2500, f"info 1000 초과 값 미반환 (cap 잔존): {result}"
    assert result["high_deleted"] == 1500, f"high 값 불일치: {result}"
    assert result["elapsed_ms"] >= 0
    assert any(
        msg.startswith("[log_retention]")
        and "info_deleted=2500" in msg
        and "high_deleted=1500" in msg
        for _, msg in written
    ), f"[log_retention] emit 미보존: {written}"


@pytest.mark.asyncio
async def test_purge_old_logs_retention_days_constants():
    """retention 경계 상수 보존 — INFO 2일 / HIGH 30일."""
    from src.db import system_logs as _mod

    assert _mod.INFO_RETENTION_DAYS == 2, "INFO_RETENTION_DAYS 변경 금지."
    assert _mod.HIGH_RETENTION_DAYS == 30, "HIGH_RETENTION_DAYS 변경 금지."
    assert _mod.HIGH_LEVELS == ("WARNING", "ERROR", "CRITICAL"), "HIGH_LEVELS 변경 금지."


# ===========================================================================
# 계약 보존 불변식 — supabase 미참조 (pg 단독) + 상수 보존
# ===========================================================================
def test_system_logs_no_supabase_after_transition():
    """전환 후 system_logs.py 는 supabase 를 참조하지 않는다 (pg 단독).

    소스 AST 검사 — supabase import/코드 참조 부재 + src.db.pg import 존재.
    (autouse fixture 가 supabase 심볼을 생성하므로 런타임 hasattr 금지 → AST 로만 판정.)
    """
    from src.db import system_logs as _mod

    tree = ast.parse(inspect.getsource(_mod))
    offenders: list[str] = []
    imports_pg = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if alias.name == "src.db.pg":
                    imports_pg = True
                if base == "supabase" or alias.name == "supabase":
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod_base = (node.module or "").split(".")[0]
            if node.module == "src.db" and any(a.name == "pg" for a in node.names):
                imports_pg = True
            if mod_base == "supabase":
                offenders.append(f"from {node.module} import ...")
            for alias in node.names:
                if alias.name == "supabase":
                    offenders.append(f"from {node.module} import {alias.name}")
        elif isinstance(node, ast.Name) and node.id == "supabase":
            offenders.append(f"name {node.id}")

    assert not offenders, f"전환 후 supabase 코드 참조 잔존 금지 (pg 단독). 발견: {offenders}"
    assert imports_pg, "system_logs 가 src.db.pg 를 import 해야 함."


def test_purge_select_batch_constants_preserved():
    """PURGE_SELECT_BATCH=1000 / PURGE_MAX_ITERATIONS=2000 상수 보존 (사이클175)."""
    from src.db import system_logs as _mod

    assert _mod.PURGE_SELECT_BATCH == 1000, "PURGE_SELECT_BATCH 변경 금지 (배치 크기)."
    assert _mod.PURGE_MAX_ITERATIONS == 2000, "PURGE_MAX_ITERATIONS 변경 금지 (런어웨이 cap)."


def test_write_log_signature_preserved():
    """write_log(log_level, message) → None 시그니처 불변 (72곳 호출 계약)."""
    from src.db import system_logs as _mod

    params = list(inspect.signature(_mod.write_log).parameters)
    assert params == ["log_level", "message"], f"write_log 시그니처 변경 금지: {params}"


def test_search_and_get_logs_signature_preserved():
    """get_logs / search_logs / safe_write_log 시그니처 불변."""
    from src.db import system_logs as _mod

    get_params = inspect.signature(_mod.get_logs).parameters
    for name in ("limit", "log_level", "from_date", "to_date", "page", "size"):
        assert name in get_params, f"get_logs 인자 {name} 삭제 금지."

    search_params = inspect.signature(_mod.search_logs).parameters
    for name in ("q", "level", "start", "end", "limit"):
        assert name in search_params, f"search_logs 인자 {name} 삭제 금지."

    safe_params = inspect.signature(_mod.safe_write_log).parameters
    for name in ("level", "message", "fallback_debug"):
        assert name in safe_params, f"safe_write_log 인자 {name} 삭제 금지."
