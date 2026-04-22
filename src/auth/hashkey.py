"""KIS Hashkey 생성 모듈."""

import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


async def generate_hashkey(body: dict) -> str:
    """POST /uapi/hashkey 로 주문 요청 body의 hashkey를 생성한다."""
    url = f"{settings.kis_base_url}/uapi/hashkey"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "appkey": settings.kis_app_key,
        "appsecret": settings.kis_app_secret,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()

    return data["HASH"]
