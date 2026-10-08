"""cycle412 Red — 워커 HTTP(설계 관찰자안 5절 ③ 「URL」).

리포터 키는 GET 이면 경로를 가리지 않고 통과한다(`api_auth.py:262-264`). 경로 오타 하나면
KIS 를 부르는 GET(`/api/balance`·`/api/balance/buyable`·`/api/portfolio/risk`)을 15초마다 친다.

| # | 계약 |
|---|---|
| H1 | 허용 경로는 G0·G1 두 상수뿐 · jw/ 코드의 `"/api/…"` 문자열도 그 둘뿐 |
| H2 | 허용 밖 경로 → ValueError, 요청 0 |
| H3 | 리다이렉트를 따라가지 않는다(요청 1번 · 실패) |
| H4 | `X-API-Key` = 리포터 키 · 성공이면 `data` · 4xx/5xx/`success=false` → JournalFetchError |
"""
from __future__ import annotations

import ast
import asyncio

import httpx
import pytest

from jw_testkit import jw, jw_sources

pytestmark = pytest.mark.unit

G0 = "/api/trading/status?include=system,holdings,strategies"
G1 = "/api/balance/exit-lines"


def _client(handler, key="rk-test"):
    return jw("http").build_client(base_url="http://backend:8000", reporter_key=key,
                                   transport=httpx.MockTransport(handler))


def _run(coro):
    return asyncio.run(coro)


def test_h1_allowed_paths_are_exactly_g0_g1():
    cfg = jw("config")
    assert cfg.G0_PATH == G0 and cfg.G1_PATH == G1
    assert cfg.ALLOWED_PATHS == frozenset({G0, G1})
    assert cfg.BASE_URL == "http://backend:8000"


def test_h1b_no_other_api_literal_in_worker_code():
    srcs = jw_sources()
    assert srcs, "jw/ 가 없다"
    found = set()
    for rel, text in srcs.items():
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "/api/" in node.value:
                found.add(node.value)
    assert found == {G0, G1}, found


@pytest.mark.parametrize("path", ["/api/balance", "/api/balance/buyable", "/api/portfolio/risk",
                                  "/api/balance/exit-lines/", "/api/trading/status",
                                  "http://evil/api/balance/exit-lines"])
def test_h2_disallowed_path_raises_before_request(path):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={"success": True, "data": {}})

    async def go():
        async with _client(handler) as c:
            with pytest.raises(ValueError):
                await jw("http").fetch(c, path)

    _run(go())
    assert calls == []


def test_h3_redirect_is_not_followed():
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(307, headers={"location": "/api/balance"})

    async def go():
        async with _client(handler) as c:
            assert c.follow_redirects is False
            with pytest.raises(jw("http").JournalFetchError):
                await jw("http").fetch(c, G1)

    _run(go())
    assert calls == ["http://backend:8000/api/balance/exit-lines"]


def test_h4_success_returns_data_and_sends_reporter_key():
    seen = {}

    def handler(req):
        seen["key"] = req.headers.get("x-api-key")
        seen["url"] = str(req.url)
        seen["method"] = req.method
        return httpx.Response(200, json={"success": True, "data": {"running": True, "items": []},
                                         "message": ""})

    async def go():
        async with _client(handler, key="rk-123") as c:
            return await jw("http").fetch(c, G1)

    assert _run(go()) == {"running": True, "items": []}
    assert seen == {"key": "rk-123", "url": "http://backend:8000/api/balance/exit-lines", "method": "GET"}


@pytest.mark.parametrize("status,body", [(401, {"detail": "x"}), (500, {"detail": "x"}),
                                         (200, {"success": False, "data": None, "message": "실패"})])
def test_h4b_failures_raise_fetch_error(status, body):
    async def go():
        async with _client(lambda req: httpx.Response(status, json=body)) as c:
            with pytest.raises(jw("http").JournalFetchError):
                await jw("http").fetch(c, G0)

    _run(go())
