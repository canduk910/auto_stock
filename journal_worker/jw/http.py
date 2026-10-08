"""워커 → 백엔드 HTTP(cycle412 계약 3.6절). 허용 경로 둘만 호출한다."""
from __future__ import annotations

import httpx

from jw.config import ALLOWED_PATHS


class JournalFetchError(Exception):
    pass


def build_client(*, base_url: str, reporter_key: str, transport=None) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, follow_redirects=False,
                              headers={"X-API-Key": reporter_key}, transport=transport)


async def fetch(client: httpx.AsyncClient, path: str) -> dict:
    if path not in ALLOWED_PATHS:
        raise ValueError(f"disallowed path: {path}")
    try:
        resp = await client.get(path)
    except httpx.HTTPError as exc:
        raise JournalFetchError(str(exc)) from exc
    if resp.status_code >= 300:
        raise JournalFetchError(f"status {resp.status_code}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise JournalFetchError("invalid json") from exc
    if not isinstance(body, dict) or body.get("success") is not True:
        raise JournalFetchError(f"success=false: {body}")
    return body.get("data")
