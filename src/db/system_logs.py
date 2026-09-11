"""system_logs CRUD.

사이클 6 통합 (2026-05-20) — 검색(`search_logs`) + retention 자동 정리(`purge_old_logs`) 추가.

사이클 M3b (Supabase→RDS 이전, 마지막 db 모듈): supabase-py 체인(+asyncio.to_thread) →
`src.db.pg`(asyncpg) 전환. 관찰성 척추 + 매매 프로세스 안전망 — 3대 불변식 절대 보존:
1. **never-raise** (사이클190): write_log INSERT 실패 시 어떤 예외도 호출자에 전파하지 않는다.
2. **KST timestamp** (사이클65 H2): INSERT payload timestamp = KST(+09:00) datetime 바인딩.
3. **purge 루프 배치** (사이클175): SELECT id LIMIT 1000 → DELETE id=ANY() drained 까지 루프.

함수 시그니처·반환형·graceful 폴백 100% 보존 — 호출부(72곳) diff 0.
"""

from __future__ import annotations

import asyncio  # noqa: F401 — 하위 호환 (일부 테스트 fixture 가 _mod.asyncio 참조, 실사용 0)
import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import src.db.pg as pg
from src.db._kst import now_kst_iso

logger = logging.getLogger(__name__)

# KST timezone
KST = timezone(timedelta(hours=9))

# Retention 정책 — 등급별 보관 기간 (사이클 6 통합)
INFO_RETENTION_DAYS = 2
HIGH_RETENTION_DAYS = 30
HIGH_LEVELS: tuple[str, ...] = ("WARNING", "ERROR", "CRITICAL")

# 단일 purge 호출 누적 삭제 안전 cap (한 번의 settlement 폭주 차단)
MAX_PURGE_BATCH = 100_000

# 사이클 175 (2026-06-24) — PostgREST row-cap silent 결함 항구 시정 (루프 배치)
# per-iteration SELECT 배치 크기. asyncpg 전환 후에는 PostgREST cap 자체는 없으나,
# 동일한 배치+루프 구조를 보존 (단일 대량 DELETE 로 인한 락 경합/트랜잭션 비대 회피).
PURGE_SELECT_BATCH = 1000

# 루프 런어웨이 차단 (안전 max iterations). 2000 × 1000 = 2M 행 = 충분히 큼.
# 단일 호출 누적 상한 MAX_PURGE_BATCH(=100_000) 가 먼저 끊으므로 정상 운영에서 도달 불가.
PURGE_MAX_ITERATIONS = 2000

# 검색 limit clamp
SEARCH_DEFAULT_LIMIT = 200
SEARCH_MAX_LIMIT = 1000

# 사이클 M3b — timestamp 를 KST(+09:00) str 로 명시 캐스트 (trade_history.py::_TS_SELECT
# 패턴 답습). asyncpg pool 재사용 시 session timezone 이 서버 기본값(UTC)으로 리셋될 수
# 있어(M0 _init_conn docstring 경고), SELECT 단계에서 명시 변환해 KST 계약을 절연 보장.
_TS_SELECT = "to_char(timestamp, 'YYYY-MM-DD\"T\"HH24:MI:SS.US+09:00') AS timestamp"
_LOG_COLUMNS = f"id, log_level, message, {_TS_SELECT}"


async def write_log(log_level: str, message: str) -> None:
    """시스템 로그를 기록한다.

    관찰성 함수 — 어떤 예외도 호출자에 전파하지 않는다 (사이클 190, 2026-07-03).
    INSERT 실패 시 logger.debug 단독 발화 (WARNING 이상 금지 — _DbLogHandler 재귀 위험).
    배경: 2026-07-03 07:59 scheduler.py L677 bare await write_log 가 Supabase HTTP/2
    RemoteProtocolError 로 raise → 매매 프로세스 크래시. src/ 전체 72개 직접 호출 사이트
    무변경으로 단일 지점에서 영구 차단.

    사이클 M3b — asyncpg 전환. timestamp 는 KST datetime 바인딩 (str 금지, TIMESTAMPTZ 계약).
    """
    ts = datetime.fromisoformat(now_kst_iso())  # 사이클 65 hotfix H2 — KST 강제
    try:
        await pg.execute(
            "INSERT INTO system_logs (log_level, message, timestamp) VALUES ($1, $2, $3)",
            log_level,
            message,
            ts,
        )
    except Exception:
        logger.debug("[write_log_failed] level=%s msg=%.80s", log_level, message)


async def safe_write_log(
    level: str,
    message: str,
    *,
    fallback_debug: str | None = None,
) -> None:
    """write_log 의 graceful skip 변형 — 실패 시 logger.debug 만 발화.

    사이클 56-E (2026-06-04): order_engine.py 동형 try/except 패턴 통합.
    write_log 실패 (DB 일시 장애, 네트워크 에러 등) 가 매매 흐름을 막지
    않도록 graceful skip. logger.debug 는 stdout 에 흔적 보존.

    Args:
        level: 로그 레벨 (INFO / WARNING / ERROR / CRITICAL).
        message: 로그 메시지.
        fallback_debug: 예외 발생 시 logger.debug 에 전달할 메시지.
            None 이면 기본 메시지 "[safe_write_log] {message[:80]} 실패: level={level}" 사용.
    """
    try:
        await write_log(level, message)
    except Exception:
        if fallback_debug:
            logger.debug(fallback_debug, exc_info=True)
        else:
            logger.debug(
                "[safe_write_log] %s 실패: level=%s",
                message[:80],
                level,
                exc_info=True,
            )


async def get_logs(
    limit: int = 100,
    log_level: str | None = None,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = 1,
    size: int | None = None,
) -> dict:
    """시스템 로그를 조회한다.

    사이클 6 (2026-05-17) — 페이징 + KST 기간 필터.
    사이클 M3b — asyncpg 전환 (SELECT + count 는 pg.fetch + pg.fetchval 분리).

    Args:
        limit: 하위 호환용. ``size`` 가 None 이면 size 로 흡수된다.
        log_level: ``log_level`` 필터 (단일 값). None 이면 무필터.
        from_date: 시작일(KST). 명시 시 ``timestamp >= "{date}T00:00:00+09:00"``.
        to_date: 종료일(KST). 명시 시 ``timestamp <= "{date}T23:59:59.999999+09:00"``.
        page: 1-base 페이지 번호. 기본 1.
        size: 페이지 크기. None 이면 ``limit`` 값을 사용 (기존 호출 회귀 보존).

    Returns:
        ``{"items": list[dict], "total": int, "total_pages": int}``

    Note:
        - KST 컨벤션: 모든 비교 timestamp 는 ``+09:00`` suffix 명시.
        - `total` 은 별도 `SELECT count(*)` (동일 필터) 로 조회.
        - ``total_pages = math.ceil(total / effective_size)``; total=0 면 0.
    """
    effective_size = size if size is not None else limit
    if effective_size < 1:
        effective_size = 1
    if page < 1:
        page = 1
    offset = (page - 1) * effective_size

    conditions: list[str] = []
    args: list[Any] = []

    def _add(cond_tpl: str, value: Any) -> None:
        args.append(value)
        conditions.append(cond_tpl.format(n=len(args)))

    if log_level:
        _add("log_level = ${n}", log_level)
    if from_date is not None:
        # asyncpg 는 TIMESTAMPTZ 파라미터에 str 을 바인딩하면 프리페어 단계에서
        # DataError(암묵 변환 미지원). `::text::timestamptz` 2단 캐스트로 서버가
        # str → timestamptz 파싱을 전담하게 하여 str 바인딩 계약(단위테스트 isoformat
        # 부분일치)과 실 PG 왕복(TIMESTAMPTZ 비교) 을 동시 만족.
        _add("timestamp >= ${n}::text::timestamptz", f"{from_date.isoformat()}T00:00:00+09:00")
    if to_date is not None:
        _add("timestamp <= ${n}::text::timestamptz", f"{to_date.isoformat()}T23:59:59.999999+09:00")

    where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    select_args = list(args)
    select_sql = (
        f"SELECT {_LOG_COLUMNS} FROM system_logs"
        + where_sql
        + f" ORDER BY timestamp DESC LIMIT ${len(select_args) + 1} OFFSET ${len(select_args) + 2}"
    )
    select_args.extend([effective_size, offset])

    count_sql = "SELECT count(*) FROM system_logs" + where_sql

    items = await pg.fetch(select_sql, *select_args)
    total = await pg.fetchval(count_sql, *args)
    if total is None:
        total = len(items)
    total_pages = math.ceil(total / effective_size) if total else 0
    return {"items": items, "total": int(total), "total_pages": int(total_pages)}


# ---------------------------------------------------------------------------
# 사이클 6 통합 (2026-05-20) — 키워드 검색
# ---------------------------------------------------------------------------


async def search_logs(
    q: str,
    *,
    level: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = SEARCH_DEFAULT_LIMIT,
) -> dict[str, Any]:
    """system_logs 키워드 검색 (ILIKE substring 매칭).

    Args:
        q: 검색어 (필수, 빈 문자열 거부). `message` 컬럼 대상 ILIKE `%q%` 매칭.
        level: 등급 필터 (단일). `None` 또는 `"ALL"` 이면 무필터.
        start: ISO 8601 시각 (예: ``2026-05-19T00:00:00+09:00``). 명시 시 `timestamp >= start`.
        end: ISO 8601 시각. 명시 시 `timestamp <= end`.
        limit: 최대 행 수. 기본 200, 최대 1000 (초과 시 clamp).

    Returns:
        ``{"logs": list[dict], "total": int, "has_more": bool}``

    Raises:
        ValueError: `q` 가 빈 문자열 또는 공백만일 때.

    Note:
        - 대소문자 무시 substring 매칭 (`%q%`)
        - asyncpg `ILIKE $n` 사용 — 사용자 입력은 패턴 문자열로 바인딩 (SQL 인젝션 안전)
        - 라우트 측 `min_length=1` 가드와 이중 안전망
        - `has_more = total > len(logs)` — 추가 결과 존재 시 운영자에게 키워드 좁히기 안내
    """
    if not q or not q.strip():
        raise ValueError("q must be a non-empty string")

    if limit > SEARCH_MAX_LIMIT:
        limit = SEARCH_MAX_LIMIT
    if limit < 1:
        limit = 1

    pattern = f"%{q}%"

    conditions: list[str] = ["message ILIKE $1"]
    args: list[Any] = [pattern]

    if level and level != "ALL":
        args.append(level)
        conditions.append(f"log_level = ${len(args)}")
    if start is not None:
        args.append(start)
        # asyncpg TIMESTAMPTZ str 바인딩 DataError 회피 — `::text::timestamptz` 2단 캐스트.
        conditions.append(f"timestamp >= ${len(args)}::text::timestamptz")
    if end is not None:
        args.append(end)
        conditions.append(f"timestamp <= ${len(args)}::text::timestamptz")

    where_sql = f" WHERE {' AND '.join(conditions)}"

    select_args = list(args)
    select_sql = (
        f"SELECT {_LOG_COLUMNS} FROM system_logs"
        + where_sql
        + f" ORDER BY timestamp DESC LIMIT ${len(select_args) + 1}"
    )
    select_args.append(limit)

    count_sql = "SELECT count(*) FROM system_logs" + where_sql

    items = await pg.fetch(select_sql, *select_args)
    total = await pg.fetchval(count_sql, *args)
    if total is None:
        total = len(items)
    has_more = total > len(items)
    return {"logs": items, "total": int(total), "has_more": bool(has_more)}


# ---------------------------------------------------------------------------
# 사이클 6 통합 (2026-05-20) — Retention 자동 정리
# ---------------------------------------------------------------------------


async def _purge_by_cutoff(
    *,
    cutoff_iso: str | None,
    level_filter: str | list[str],
) -> int:
    """단일 그룹(INFO 또는 HIGH) 로그를 cutoff 이전 행만 DELETE.

    안전 가드:
    - cutoff_iso=None → RuntimeError (WHERE 조건 누락 차단)
    - 1회 cap = MAX_PURGE_BATCH (100,000)

    Args:
        cutoff_iso: KST ISO 8601 시각. `timestamp < cutoff_iso` 인 행 DELETE.
        level_filter: 단일 등급 문자열 또는 등급 리스트.

    Returns:
        삭제 행 수.
    """
    if cutoff_iso is None:
        raise RuntimeError("cutoff must not be None (WHERE 누락 차단)")

    # 사이클 150 → 사이클 175 → 사이클 M3b 영속 — 루프 배치 구조 보존.
    # asyncpg 전환 후 PostgREST 1000행 cap 자체는 사라졌으나, 단일 대량 DELETE 로
    # 인한 트랜잭션 비대/락 경합을 회피하기 위해 동일한 SELECT id LIMIT 1000 +
    # DELETE id = ANY() 를 drained 까지 루프하는 구조를 그대로 유지한다.
    #
    # ⚠️ asyncpg 는 TIMESTAMPTZ 바인딩에 str → datetime 암묵 변환을 지원하지 않는다
    # (M0 _init_conn docstring "최대 위험" 과 동형 계약). cutoff_iso 는 ISO 8601 str
    # 계약(테스트/purge_old_logs 호출자) 이므로 여기서 datetime 으로 변환해 바인딩한다.
    cutoff_dt = datetime.fromisoformat(cutoff_iso)

    level_is_list = not isinstance(level_filter, str)
    level_cond = "log_level = ANY($2::text[])" if level_is_list else "log_level = $2"
    level_arg = list(level_filter) if level_is_list else level_filter

    select_sql = (
        f"SELECT id FROM system_logs WHERE {level_cond} AND timestamp < $1 "
        f"LIMIT {PURGE_SELECT_BATCH}"
    )
    delete_sql = "DELETE FROM system_logs WHERE id = ANY($1::bigint[])"

    total_deleted = 0
    for _ in range(PURGE_MAX_ITERATIONS):
        select_rows = await pg.fetch(select_sql, cutoff_dt, level_arg)
        ids = [row["id"] for row in select_rows if "id" in row]

        if not ids:
            break  # drained — 더 이상 cutoff 통과 행 없음

        result = await pg.execute(delete_sql, ids)
        # asyncpg execute() 는 "DELETE N" 형식 상태 문자열 반환.
        count = None
        if isinstance(result, str) and result.upper().startswith("DELETE"):
            parts = result.split()
            if len(parts) >= 2 and parts[1].isdigit():
                count = int(parts[1])
        deleted = len(ids) if count is None or count <= 0 else count
        total_deleted += deleted

        if total_deleted >= MAX_PURGE_BATCH:
            break  # 단일 호출 누적 상한 cap (settlement 폭주 차단)
        if len(ids) < PURGE_SELECT_BATCH:
            break  # 마지막 페이지 (다음 SELECT 는 빈 결과 — 1회 호출 절약)

    return total_deleted


async def purge_old_logs() -> dict[str, int]:
    """등급별 retention 정책 적용 — INFO 2일 / WARNING+ 30일.

    호출 시점:
    - settlement(21:30 — cycle283 D3) 흐름의 ``_log_analysis_engine`` 직후, ``_reset_daily_state()`` *직전*
    - scheduler 가 try/except 로 graceful 처리 (실패 시 다음 사이클 재시도)

    Returns:
        ``{"info_deleted": int, "high_deleted": int, "elapsed_ms": int}``

    Side effects:
        - INFO 로그 1행 ``[log_retention] info_deleted=N high_deleted=M elapsed_ms=K``

    Note:
        - KST 기준 ``now`` → 2일/30일 전 cutoff
        - cutoff ISO 포맷 ``YYYY-MM-DDTHH:MM:SS.ffffff+09:00`` (microseconds 포함)
        - 1회 DELETE cap = MAX_PURGE_BATCH (=100,000). 잔여분은 다음 영업일 재처리
    """
    started = time.perf_counter()

    now_kst = datetime.now(KST)
    info_cutoff = (now_kst - timedelta(days=INFO_RETENTION_DAYS)).isoformat()
    high_cutoff = (now_kst - timedelta(days=HIGH_RETENTION_DAYS)).isoformat()

    info_deleted = await _purge_by_cutoff(
        cutoff_iso=info_cutoff,
        level_filter="INFO",
    )
    high_deleted = await _purge_by_cutoff(
        cutoff_iso=high_cutoff,
        level_filter=list(HIGH_LEVELS),
    )

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # INFO 1행 영구 로그 (fire-and-forget; write_log 실패는 호출자에 영향 없음)
    try:
        await write_log(
            "INFO",
            f"[log_retention] info_deleted={info_deleted} "
            f"high_deleted={high_deleted} elapsed_ms={elapsed_ms}",
        )
    except Exception:
        logger.exception("[log_retention] write_log 실패 (graceful)")

    return {
        "info_deleted": info_deleted,
        "high_deleted": high_deleted,
        "elapsed_ms": elapsed_ms,
    }
