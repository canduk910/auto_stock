"""사이클 M3b (Red) — src/main.py seam 2곳 asyncpg 전환 (호출부 diff 0 유일 예외).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — main seam).

⚠️ **로깅 척추 — 극도 주의**. main.py 는 매매 안전성 8영역 밖이나 seam 2곳만 변경.

## seam ① — `_DbLogHandler` (동기 handler → async INSERT)
asyncpg 는 async → 동기 `logging.Handler.emit` 에서 직접 await 불가.
**전환 설계 (계획 권고)**: emit 을 **큐 producer**(sync, non-blocking `queue.put_nowait`) +
lifespan 에 **async consumer task**(큐 drain → `pg.execute` INSERT). ThreadPoolExecutor 폐기.

**절대 보존 불변식**:
- 사이클72 500ms TTL dedupe 캐시 (`_DEDUPE_TTL_SECS=0.5`, `_dedupe_cache`) — emit producer 단계
  에서 dedupe (중복 큐 적재 차단).
- 사이클65 H2-bis KST `now_kst_iso()` 강제 — consumer 가 INSERT 시 KST timestamp.
- 사이클190 never-raise — emit producer 가 큐 full/예외 시 재귀 로그 금지(logger.* 미발화).
- src.* 필터 (record.name.startswith("src.")) 보존.

## seam ② — lifespan auto_start
`from src.db.supabase import supabase as _sb` 인라인 조회 → `system_config.get_auto_start() -> bool`
**신규 헬퍼로 추출**(system_config 는 M2a 에서 pg 전환됨) → seam 제거.

Red 유효성:
- `_DbLogHandler` 는 아직 ThreadPoolExecutor(`_LOG_DB_EXECUTOR.submit`) 경로 → 큐 producer 미구현 → FAIL.
- `system_config.get_auto_start` 헬퍼 미존재 → FAIL.
- lifespan 이 여전히 supabase 인라인 조회 → seam 제거 단언 FAIL.
"""

from __future__ import annotations

import ast
import inspect
import logging
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]


def _make_record(message: str, name: str = "src.engine.scheduler", level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1,
        msg=message, args=None, exc_info=None,
    )


# ===========================================================================
# seam ① — _DbLogHandler 큐 producer (sync, non-blocking) + dedupe + never-raise
# ===========================================================================
def _get_handler_queue(handler):
    """전환 후 handler 가 큐를 노출하는 접근자 — `_log_queue` 인스턴스/모듈 변수 또는 producer."""
    import src.main as main_mod

    # 우선순위: 모듈 전역 큐 (`_LOG_QUEUE`) → handler 인스턴스 큐 (`_log_queue`)
    for name in ("_LOG_QUEUE", "_log_queue"):
        q = getattr(main_mod, name, None)
        if q is not None:
            return q
        q = getattr(handler, name, None)
        if q is not None:
            return q
    return None


def test_db_log_handler_uses_queue_not_thread_executor():
    """⚠️ 전환 설계 — emit 은 큐 producer (put_nowait), ThreadPoolExecutor 폐기.

    Green: emit 이 `_LOG_QUEUE.put_nowait(...)` (또는 인스턴스 큐) 로 적재 → 큐 크기 증가.
    Red: `_LOG_DB_EXECUTOR.submit` 경로 → 큐 부재 → FAIL.
    """
    import src.main as main_mod

    # ThreadPoolExecutor 폐기 불변식 — `_LOG_DB_EXECUTOR` 심볼 제거 (또는 미사용)
    assert not hasattr(main_mod, "_LOG_DB_EXECUTOR"), (
        "ThreadPoolExecutor(`_LOG_DB_EXECUTOR`) 폐기 의무 (asyncpg 큐 전환)."
    )

    handler = main_mod._DbLogHandler()
    q = _get_handler_queue(handler)
    assert q is not None, (
        "전환 후 emit 큐(`_LOG_QUEUE` 또는 handler `_log_queue`) 미존재 — "
        "큐 producer/consumer 구조 미구현."
    )
    assert hasattr(q, "put_nowait"), "큐는 put_nowait 지원 (non-blocking producer) 의무."


def test_emit_enqueues_message_non_blocking():
    """emit → 큐에 (level, message) 적재 (non-blocking put_nowait). src.* 필터 통과."""
    import src.main as main_mod

    handler = main_mod._DbLogHandler()
    q = _get_handler_queue(handler)
    assert q is not None, "큐 미존재 (Red — 큐 producer 미구현)."

    # 큐를 명시 비움 (모듈 전역일 수 있어 격리)
    while not q.empty():
        q.get_nowait()

    handler.emit(_make_record("[test] 매수 신호 감지"))
    assert not q.empty(), "emit 이 큐에 적재하지 않음 (producer 미구현)."


def test_emit_non_src_logger_skipped():
    """record.name 이 src.* 아니면 skip (기존 필터 보존)."""
    import src.main as main_mod

    handler = main_mod._DbLogHandler()
    q = _get_handler_queue(handler)
    assert q is not None
    while not q.empty():
        q.get_nowait()

    handler.emit(_make_record("외부 로그", name="uvicorn.access"))
    assert q.empty(), "src.* 아닌 로거는 큐 적재 금지 (필터 보존)."


def test_emit_dedupe_500ms_within_window():
    """⚠️ 사이클72 dedupe — 동일 메시지 100ms 내 2회 emit → 큐 1건만 (producer 단계 dedupe)."""
    import src.main as main_mod

    handler = main_mod._DbLogHandler()
    q = _get_handler_queue(handler)
    assert q is not None, "큐 미존재 (Red)."
    while not q.empty():
        q.get_nowait()

    rec = _make_record("[ws_heartbeat] label=main window=300s")
    # monotonic 0.0 → 0.1 (100ms) — dedupe 윈도우(500ms) 안
    monotonic_values = iter([0.0, 0.0, 0.1, 0.1, 0.1, 0.1])
    with patch("time.monotonic", side_effect=lambda: next(monotonic_values, 0.1)):
        handler.emit(rec)
        handler.emit(rec)

    count = 0
    while not q.empty():
        q.get_nowait()
        count += 1
    assert count == 1, (
        f"동일 메시지 100ms 내 2회 emit → 큐 {count}건 (기대 1 — 500ms TTL dedupe)."
    )


def test_emit_dedupe_ttl_constant_preserved():
    """`_DEDUPE_TTL_SECS = 0.5` 상수 보존 (사이클72)."""
    import src.main as main_mod

    assert hasattr(main_mod, "_DEDUPE_TTL_SECS"), "_DEDUPE_TTL_SECS 상수 미정의."
    assert main_mod._DEDUPE_TTL_SECS == 0.5, (
        f"_DEDUPE_TTL_SECS={main_mod._DEDUPE_TTL_SECS}, 기대 0.5 (500ms)"
    )
    handler = main_mod._DbLogHandler()
    assert hasattr(handler, "_dedupe_cache"), "_dedupe_cache 인스턴스 변수 미존재 (사이클72)."


def test_emit_dedupe_after_ttl_enqueues_twice():
    """동일 메시지 600ms 후 emit → TTL 경과 → 큐 2건 (dedupe 해제)."""
    import src.main as main_mod

    handler = main_mod._DbLogHandler()
    q = _get_handler_queue(handler)
    assert q is not None
    while not q.empty():
        q.get_nowait()

    rec = _make_record("[stale_watcher] subscribed=30 stale=2")
    monotonic_values = iter([0.0, 0.0, 0.6, 0.6, 0.6, 0.6])
    with patch("time.monotonic", side_effect=lambda: next(monotonic_values, 0.6)):
        handler.emit(rec)
        handler.emit(rec)

    count = 0
    while not q.empty():
        q.get_nowait()
        count += 1
    assert count == 2, f"600ms 후 emit → 큐 {count}건 (기대 2 — TTL 경과)."


def test_emit_different_messages_both_enqueue():
    """다른 메시지 100ms 내 emit → 둘 다 큐 적재 (메시지별 dedupe 정확)."""
    import src.main as main_mod

    handler = main_mod._DbLogHandler()
    q = _get_handler_queue(handler)
    assert q is not None
    while not q.empty():
        q.get_nowait()

    rec1 = _make_record("[detail] session=main fresh=20")
    rec2 = _make_record("[detail] session=ISA fresh=11")
    monotonic_values = iter([0.0, 0.0, 0.05, 0.05, 0.05, 0.05])
    with patch("time.monotonic", side_effect=lambda: next(monotonic_values, 0.05)):
        handler.emit(rec1)
        handler.emit(rec2)

    count = 0
    while not q.empty():
        q.get_nowait()
        count += 1
    assert count == 2, f"다른 메시지 100ms 내 emit → 큐 {count}건 (기대 2)."


def test_emit_never_raises_on_queue_full(caplog):
    """⚠️ 사이클190 never-raise — 큐 full(put_nowait QueueFull) 시 emit 이 예외 미전파 + WARNING 이상 미발화."""
    import src.main as main_mod

    handler = main_mod._DbLogHandler()
    q = _get_handler_queue(handler)
    assert q is not None, "큐 미존재 (Red)."

    # put_nowait 를 QueueFull 로 강제 → emit 이 삼켜야 함
    import queue as _queue_mod

    def _raise_full(_item):
        raise _queue_mod.Full()

    with patch.object(q, "put_nowait", side_effect=_raise_full):
        with caplog.at_level(logging.DEBUG):
            # 예외 전파되면 여기서 raise → 실패
            handler.emit(_make_record("[test] full 케이스"))

    high_records = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and r.name.startswith("src.")
    ]
    assert not high_records, (
        f"큐 full 시 WARNING 이상 발화 금지 (재귀 위험): {[r.getMessage() for r in high_records]}"
    )


# ===========================================================================
# seam ① — async consumer: 큐 drain → pg.execute INSERT (KST timestamp)
# ===========================================================================
def _find_consumer_callable(main_mod):
    """전환 후 consumer 코루틴 — `_log_queue_consumer` / `_drain_log_queue` / `_log_consumer_loop` 후보."""
    for name in ("_log_queue_consumer", "_drain_log_queue", "_log_consumer_loop", "_consume_log_queue"):
        fn = getattr(main_mod, name, None)
        if fn is not None:
            return fn
    return None


def test_consumer_callable_exists():
    """async consumer 코루틴 존재 (큐 drain → pg.execute INSERT)."""
    import src.main as main_mod

    consumer = _find_consumer_callable(main_mod)
    assert consumer is not None, (
        "async consumer 코루틴 미존재 — 큐 drain → pg.execute INSERT 소비자 미구현."
    )
    assert inspect.iscoroutinefunction(consumer), "consumer 는 async 코루틴 의무."


@pytest.mark.asyncio
async def test_insert_log_helper_uses_pg_execute_kst():
    """⚠️ 사이클65 H2-bis — 로그 INSERT 헬퍼가 pg.execute + KST datetime timestamp.

    `_insert_log_to_db` (또는 consumer 내부 INSERT) 가 supabase 체인 폐기 + pg.execute
    "INSERT INTO system_logs" + timestamp = KST datetime (now_kst_iso 기반) 바인딩.

    Red 시점: `_insert_log_to_db` 가 동기 supabase 함수 → iscoroutinefunction False → FAIL.
    """
    import src.main as main_mod

    insert_fn = getattr(main_mod, "_insert_log_to_db", None)
    assert insert_fn is not None and inspect.iscoroutinefunction(insert_fn), (
        "_insert_log_to_db 는 async (pg.execute await) 의무 — 동기 supabase 폐기 "
        "(consumer 가 INSERT 를 인라인 처리하면 이 헬퍼 대신 consumer 케이스로 검증하도록 설계 조정)."
    )

    with patch.object(main_mod, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await insert_fn("INFO", "[src.engine] consumer 로그")

    pg_mod.execute.assert_awaited()
    sql = pg_mod.execute.await_args.args[0]
    assert "INSERT INTO system_logs" in sql, "INSERT INTO system_logs SQL 누락."
    args = pg_mod.execute.await_args.args[1:]
    dt_args = [a for a in args if isinstance(a, datetime)]
    assert dt_args, "timestamp datetime 바인딩 누락 (str 금지 — asyncpg TIMESTAMPTZ)."
    assert dt_args[0].utcoffset() == timedelta(hours=9), (
        f"KST(+09:00) 명시 의무 (사이클65 H2-bis): utcoffset={dt_args[0].utcoffset()}"
    )


@pytest.mark.asyncio
async def test_insert_log_helper_never_raises():
    """⚠️ 사이클190 — consumer INSERT 헬퍼가 pg.execute 예외 시 never-raise (무한 재귀 방지)."""
    import src.main as main_mod

    insert_fn = getattr(main_mod, "_insert_log_to_db", None)
    assert insert_fn is not None and inspect.iscoroutinefunction(insert_fn), (
        "_insert_log_to_db 는 async 의무 (never-raise 검증 대상)."
    )

    with patch.object(main_mod, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=Exception("connection lost"))
        # 예외 전파되면 실패
        await insert_fn("INFO", "[src.engine] 실패 로그")
    # 여기 도달 = never-raise 성립


# ===========================================================================
# seam ② — system_config.get_auto_start 헬퍼 신규 + lifespan seam 제거
# ===========================================================================
@pytest.mark.asyncio
async def test_system_config_get_auto_start_helper_exists():
    """⚠️ seam ② — system_config.get_auto_start() -> bool 신규 헬퍼 (pg 경유, M2a 기반)."""
    from src.db import system_config as sc

    assert hasattr(sc, "get_auto_start"), (
        "system_config.get_auto_start 헬퍼 미존재 (seam ② 추출 미구현)."
    )
    assert inspect.iscoroutinefunction(sc.get_auto_start), "get_auto_start 는 async 의무."


@pytest.mark.asyncio
async def test_get_auto_start_true_when_value_true():
    """get_auto_start → auto_start 키 value=True → True (기존 raw is True or == 'true' 계약 보존)."""
    from src.db import system_config as sc

    with patch.object(sc, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": True}}])
        out = await sc.get_auto_start()

    assert out is True, "value True → auto_start True."


@pytest.mark.asyncio
async def test_get_auto_start_true_when_value_string_true():
    """get_auto_start → value='true' 문자열도 True (과거 호환)."""
    from src.db import system_config as sc

    with patch.object(sc, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": "true"}])
        out = await sc.get_auto_start()

    assert out is True, "value 'true' 문자열 → True (과거 호환 계약)."


@pytest.mark.asyncio
async def test_get_auto_start_false_when_missing():
    """get_auto_start → 키 부재 → False (기존 `_auto.data else False` 계약 보존)."""
    from src.db import system_config as sc

    with patch.object(sc, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await sc.get_auto_start()

    assert out is False, "키 부재 → False (기본 미시작)."


@pytest.mark.asyncio
async def test_get_auto_start_graceful_on_exception():
    """get_auto_start → DB 예외 시 graceful (기존 lifespan except → .env 폴백 정합, False/예외 미전파)."""
    from src.db import system_config as sc

    with patch.object(sc, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("connection lost"))
        # 예외 전파되면 실패 (lifespan 이 헬퍼를 try/except 로 감싸도 헬퍼 자체 graceful 이 안전)
        out = await sc.get_auto_start()

    assert out is False, "DB 예외 → False graceful (lifespan 폴백 정합)."


def test_lifespan_no_supabase_inline_query():
    """⚠️ seam ② — lifespan 이 supabase 인라인 조회(`from src.db.supabase import supabase as _sb`) 제거.

    소스 AST 검사 — lifespan 함수 내 supabase 참조 부재 + get_auto_start 호출 존재.
    """
    src_path = _REPO / "src" / "main.py"
    tree = ast.parse(src_path.read_text(encoding="utf-8"))

    lifespan_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan":
            lifespan_fn = node
            break
    assert lifespan_fn is not None, "lifespan async 함수 부재."

    body_src = ast.unparse(lifespan_fn)
    # auto_start 결정 영역에서 supabase 직접 조회 제거 — `supabase.table("system_config")` 패턴 부재
    assert 'supabase.table("system_config")' not in body_src, (
        "lifespan 이 여전히 supabase 인라인 조회 — seam ② 제거 미완."
    )
    # get_auto_start 헬퍼 호출로 대체
    assert "get_auto_start" in body_src, (
        "lifespan 이 system_config.get_auto_start() 헬퍼를 호출해야 함 (seam ② 추출)."
    )


def test_lifespan_still_pool_and_token_logic_preserved():
    """seam 2곳 외 lifespan 로직 불변 — init_pool/close_pool/token_manager/전략설정 로드 보존."""
    src_path = _REPO / "src" / "main.py"
    body = src_path.read_text(encoding="utf-8")

    # M0 도입 pool lifecycle 보존
    assert "init_pool" in body and "close_pool" in body, "RDS pool lifecycle 불변 (M0)."
    # 토큰 발급/폐기 보존
    assert "token_manager.get_token" in body, "KIS 토큰 발급 로직 불변."
    assert "token_manager.revoke" in body, "토큰 폐기 로직 불변."
    # 전략 설정 초기 로드 보존
    assert "_load_strategy_config" in body, "전략 설정 초기 로드 불변."
    # run_daily 자동 매매 시작 보존
    assert "run_daily" in body, "AUTO_START run_daily 스케줄링 불변."
