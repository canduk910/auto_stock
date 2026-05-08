"""daily_log_reports CRUD."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from src.db.supabase import supabase

logger = logging.getLogger(__name__)


async def insert_log_report(
    *,
    target_date: date,
    summary: str,
    findings: list[dict],
    metrics: dict,
    model: str | None,
) -> dict | None:
    """일일 로그 분석 리포트를 INSERT한다.

    (target_date) UNIQUE — 동일 영업일 재실행 시 None 반환.
    """
    payload = {
        "target_date": target_date.isoformat(),
        "summary": summary,
        "findings": findings,
        "metrics": metrics,
        "model": model,
    }
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table("daily_log_reports").insert(payload).execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        msg = str(e)
        if "duplicate key" in msg or "23505" in msg:
            logger.info("daily_log_reports 중복 (이미 존재): %s", target_date)
            return None
        logger.exception("daily_log_reports INSERT 실패")
        raise


async def list_log_reports(days: int = 30) -> list[dict]:
    """최근 N일치 리포트를 신규순으로 조회한다."""
    result = await asyncio.to_thread(
        lambda: supabase.table("daily_log_reports")
        .select("*")
        .order("target_date", desc=True)
        .limit(days)
        .execute()
    )
    return result.data or []


async def get_log_report(target_date: date) -> dict | None:
    """단일 영업일 리포트를 조회한다."""
    result = await asyncio.to_thread(
        lambda: supabase.table("daily_log_reports")
        .select("*")
        .eq("target_date", target_date.isoformat())
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None
