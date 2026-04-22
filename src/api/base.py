"""KIS REST API 공통 호출 래퍼.

- 헤더 자동 구성 (authorization, appkey, appsecret, tr_id, custtype)
- Rate Limit: asyncio.Semaphore 초당 20건
- 에러 처리: rt_cd / msg_cd 기반
- 자동 재시도: 네트워크 오류 시 최대 3회 지수 백오프
- 토큰 만료 시 자동 갱신 후 재시도
"""

import asyncio
import logging
import time

import httpx

from src.auth.token import token_manager
from src.config import settings

logger = logging.getLogger(__name__)

# Rate Limit: 초당 최대 20건
_semaphore = asyncio.Semaphore(20)
_last_reset = time.monotonic()
_call_count = 0
_rate_lock = asyncio.Lock()

MAX_RETRIES = 3
BACKOFF_BASE = 0.5  # 초


class KisApiError(Exception):
    """KIS API 응답 에러 (rt_cd != "0")."""

    def __init__(self, rt_cd: str, msg_cd: str, msg1: str) -> None:
        self.rt_cd = rt_cd
        self.msg_cd = msg_cd
        self.msg1 = msg1
        super().__init__(f"KIS API Error [{msg_cd}]: {msg1}")


async def _rate_limit() -> None:
    """초당 20건 Rate Limit을 적용한다."""
    global _last_reset, _call_count
    async with _rate_lock:
        now = time.monotonic()
        if now - _last_reset >= 1.0:
            _last_reset = now
            _call_count = 0
        if _call_count >= 20:
            wait = 1.0 - (now - _last_reset)
            if wait > 0:
                await asyncio.sleep(wait)
            _last_reset = time.monotonic()
            _call_count = 0
        _call_count += 1


async def kis_get(
    path: str,
    tr_id: str,
    params: dict | None = None,
    *,
    hashkey: str = "",
) -> dict:
    """KIS REST GET 요청."""
    return await _request("GET", path, tr_id, params=params, hashkey=hashkey)


async def kis_post(
    path: str,
    tr_id: str,
    body: dict | None = None,
    *,
    hashkey: str = "",
) -> dict:
    """KIS REST POST 요청."""
    return await _request("POST", path, tr_id, body=body, hashkey=hashkey)


async def _request(
    method: str,
    path: str,
    tr_id: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    hashkey: str = "",
) -> dict:
    """공통 요청 래퍼. 재시도 + Rate Limit + 토큰 갱신."""
    url = f"{settings.kis_base_url}{path}"

    for attempt in range(1, MAX_RETRIES + 1):
        await _rate_limit()
        async with _semaphore:
            token = await token_manager.get_token()
            headers = token_manager.build_headers(tr_id, hashkey=hashkey)
            try:
                async with httpx.AsyncClient() as client:
                    if method == "GET":
                        resp = await client.get(
                            url, headers=headers, params=params, timeout=10
                        )
                    else:
                        resp = await client.post(
                            url, headers=headers, json=body, timeout=10
                        )
                    resp.raise_for_status()
                    data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "HTTP %s (attempt %d/%d): %s",
                    e.response.status_code,
                    attempt,
                    MAX_RETRIES,
                    path,
                )
                if attempt == MAX_RETRIES:
                    raise
                await asyncio.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
                continue
            except httpx.RequestError as e:
                logger.warning(
                    "네트워크 오류 (attempt %d/%d): %s — %s",
                    attempt,
                    MAX_RETRIES,
                    path,
                    e,
                )
                if attempt == MAX_RETRIES:
                    raise
                await asyncio.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
                continue

        # KIS 응답 코드 확인
        rt_cd = data.get("rt_cd", "")
        if rt_cd == "0":
            return data

        msg_cd = data.get("msg_cd", "")
        msg1 = data.get("msg1", "")

        # 토큰 만료 에러 시 갱신 후 재시도
        if "token" in msg1.lower() or "만료" in msg1:
            logger.info("토큰 만료 감지, 재발급 시도")
            await token_manager.issue()
            if attempt < MAX_RETRIES:
                continue

        logger.error("KIS API 에러: rt_cd=%s, msg_cd=%s, msg1=%s", rt_cd, msg_cd, msg1)
        raise KisApiError(rt_cd, msg_cd, msg1)

    # 여기까지 도달하면 안 됨
    raise RuntimeError("Unreachable: max retries exhausted")
