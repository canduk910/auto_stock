"""system_logs CRUD."""

import logging

from src.db.supabase import supabase

logger = logging.getLogger(__name__)


async def write_log(log_level: str, message: str) -> None:
    """시스템 로그를 기록한다."""
    data = {
        "log_level": log_level,
        "message": message,
    }
    supabase.table("system_logs").insert(data).execute()


async def get_logs(limit: int = 100, log_level: str | None = None) -> list[dict]:
    """시스템 로그를 조회한다."""
    query = (
        supabase.table("system_logs")
        .select("*")
        .order("timestamp", desc=True)
        .limit(limit)
    )
    if log_level:
        query = query.eq("log_level", log_level)
    result = query.execute()
    return result.data
