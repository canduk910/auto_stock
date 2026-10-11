"""워커 → 백엔드 HTTP(cycle446). 허용 경로 둘만 호출한다(journal_worker/jw/http.py 와 같은 꼴)."""
from __future__ import annotations

import httpx

from lw.config import ALLOWED_PATHS


class FetchError(Exception):
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
        raise FetchError(str(exc)) from exc
    if resp.status_code >= 300:
        raise FetchError(f"status {resp.status_code}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise FetchError("invalid json") from exc
    if not isinstance(body, dict) or body.get("success") is not True:
        raise FetchError(f"success=false: {body}")
    return body.get("data")
