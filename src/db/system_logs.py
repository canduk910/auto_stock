"""system_logs CRUD."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date

from src.db.supabase import supabase

logger = logging.getLogger(__name__)


async def write_log(log_level: str, message: str) -> None:
    """시스템 로그를 기록한다.

    supabase-py는 동기 client이므로 asyncio.to_thread()로 thread pool에 위임 →
    이벤트 루프 블로킹 차단 (on_tick 같은 핫패스에서 호출되어도 다른 await 처리 지연 없음).
    """
    data = {
        "log_level": log_level,
        "message": message,
    }
    await asyncio.to_thread(
        lambda: supabase.table("system_logs").insert(data).execute()
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
