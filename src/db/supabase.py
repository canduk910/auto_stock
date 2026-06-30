"""Supabase 클라이언트 초기화."""

from __future__ import annotations

import asyncio
import logging

import httpx
from supabase import create_client, Client

from src.config import settings

supabase: Client = create_client(settings.supabase_url, settings.supabase_key)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 사이클 187 (2026-06-30) — connection 계열 retry 래퍼
# 운영 배경: EC2 backend httpx.RemoteProtocolError "Server disconnected" 90건/24h
# (전부 read 경로 — 16:00 일봉 task 수백 종목 순회 시 httpx pool stale keep-alive
# 첫 요청에서 서버가 끊음). **멱등 SELECT 전용** — 쓰기 미적용 (멱등 우려).
# ---------------------------------------------------------------------------

_RETRY_EXCEPTIONS = (
    httpx.RemoteProtocolError,   # Server disconnected (확정 주원인)
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
)

_RETRY_BACKOFF_SECS = 0.2


async def execute_with_retry(build, *, retries: int = 1, op: str = ""):
    """동기 Supabase 쿼리(build())를 to_thread 위임 + connection 계열 예외 retries회 재시도.

    build = .execute() 포함 무인자 callable. **멱등 SELECT 전용** (쓰기 미적용).
    재시도 소진 시 마지막 예외 raise → 호출자 graceful except 보존.

    Args:
        build: () → Supabase APIResponse. `.execute()` 포함 무인자 callable.
        retries: 재시도 횟수 (기본 1 = 최대 2회 시도). retries=0 이면 재시도 없이 1회.
        op: 로그 식별자 (함수명 등). 빈 문자열이면 "?" 출력.

    연관 가드: G-187-A3 — write_log 호출 금지 (사이클 72 이중 INSERT 차단).
    logger.warning 단독 사용.
    """
    for attempt in range(retries + 1):
        try:
            return await asyncio.to_thread(build)
        except _RETRY_EXCEPTIONS as exc:
            if attempt >= retries:
                raise
            logger.warning(
                "[supabase_retry] op=%s attempt=%d/%d exc=%s 재시도",
                op or "?", attempt + 1, retries + 1, type(exc).__name__,
            )
            await asyncio.sleep(_RETRY_BACKOFF_SECS)
