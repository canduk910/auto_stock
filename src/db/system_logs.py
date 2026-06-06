"""system_logs CRUD.

사이클 6 통합 (2026-05-20) — 검색(`search_logs`) + retention 자동 정리(`purge_old_logs`) 추가.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from src.db.supabase import supabase

logger = logging.getLogger(__name__)

# KST timezone
KST = timezone(timedelta(hours=9))

# Retention 정책 — 등급별 보관 기간 (사이클 6 통합)
INFO_RETENTION_DAYS = 2
HIGH_RETENTION_DAYS = 30
HIGH_LEVELS: tuple[str, ...] = ("WARNING", "ERROR", "CRITICAL")

# 1회 DELETE 안전 cap (단일 트랜잭션 폭주 차단)
MAX_PURGE_BATCH = 100_000

# 검색 limit clamp
SEARCH_DEFAULT_LIMIT = 200
SEARCH_MAX_LIMIT = 1000


async def write_log(log_level: str, message: str) -> None:
    """시스템 로그를 기록한다.

    supabase-py는 동기 client이므로 asyncio.to_thread()로 thread pool에 위임 →
    이벤트 루프 블로킹 차단 (on_tick 같은 핫패스에서 호출되어도 다른 await 처리 지연 없음).
    """
    data = {
        "log_level": log_level,
        "message": message,
        "timestamp": datetime.now(KST).isoformat(),  # 사이클 65 hotfix H2 — KST 강제 (사이클 53 패턴 답습)
    }
    await asyncio.to_thread(
        lambda: supabase.table("system_logs").insert(data).execute()
    )


async def safe_write_log(
    level: str,
    message: str,
    *,
    fallback_debug: str | None = None,
) -> None:
    """write_log 의 graceful skip 변형 — 실패 시 logger.debug 만 발화.

    사이클 56-E (2026-06-04): order_engine.py 동형 try/except 패턴 통합.
    write_log 실패 (Supabase 일시 장애, 네트워크 에러 등) 가 매매 흐름을 막지
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
        - supabase-py 의 ``count="exact"`` 옵션으로 ``total`` 을 함께 반환받는다.
        - ``total_pages = math.ceil(total / effective_size)``; total=0 면 0.
    """
    effective_size = size if size is not None else limit
    if effective_size < 1:
        effective_size = 1
    if page < 1:
        page = 1
    offset = (page - 1) * effective_size

    def _query():
        q = (
            supabase.table("system_logs")
            .select("*", count="exact")
            .order("timestamp", desc=True)
        )
        if log_level:
            q = q.eq("log_level", log_level)
        if from_date is not None:
            q = q.gte("timestamp", f"{from_date.isoformat()}T00:00:00+09:00")
        if to_date is not None:
            q = q.lte("timestamp", f"{to_date.isoformat()}T23:59:59.999999+09:00")
        q = q.range(offset, offset + effective_size - 1)
        return q.execute()

    result = await asyncio.to_thread(_query)
    items = list(getattr(result, "data", None) or [])
    total = getattr(result, "count", None)
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
        - supabase-py `ilike(col, pattern)` 사용 — 사용자 입력 그대로 패턴 임베드
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

    def _query():
        chain = (
            supabase.table("system_logs")
            .select("*", count="exact")
            .order("timestamp", desc=True)
            .ilike("message", pattern)
        )
        if level and level != "ALL":
            chain = chain.eq("log_level", level)
        if start is not None:
            chain = chain.gte("timestamp", start)
        if end is not None:
            chain = chain.lte("timestamp", end)
        chain = chain.limit(limit)
        return chain.execute()

    result = await asyncio.to_thread(_query)
    items = list(getattr(result, "data", None) or [])
    total = getattr(result, "count", None)
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

    def _delete():
        chain = supabase.table("system_logs").delete()
        # 등급 필터: 단일이면 eq, 다중이면 in_
        if isinstance(level_filter, str):
            chain = chain.eq("log_level", level_filter)
        else:
            chain = chain.in_("log_level", list(level_filter))
        chain = chain.lt("timestamp", cutoff_iso).limit(MAX_PURGE_BATCH)
        return chain.execute()

    result = await asyncio.to_thread(_delete)
    rows = getattr(result, "data", None) or []
    count = getattr(result, "count", None)
    if count is None:
        count = len(rows)
    return int(count)


async def purge_old_logs() -> dict[str, int]:
    """등급별 retention 정책 적용 — INFO 2일 / WARNING+ 30일.

    호출 시점:
    - settlement(20:10) 흐름의 ``_log_analysis_engine`` 직후, ``_reset_daily_state()`` *직전*
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
