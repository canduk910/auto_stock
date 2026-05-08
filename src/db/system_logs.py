"""system_logs CRUD."""

import asyncio
import logging

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


async def get_logs(limit: int = 100, log_level: str | None = None) -> list[dict]:
    """시스템 로그를 조회한다."""
    def _query():
        q = (
            supabase.table("system_logs")
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
        )
        if log_level:
            q = q.eq("log_level", log_level)
        return q.execute()

    result = await asyncio.to_thread(_query)
    return result.data
