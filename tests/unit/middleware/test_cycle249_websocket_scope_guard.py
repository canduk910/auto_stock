"""cycle249 위생 (1c) — WebSocket scope 우회를 **구조 가드**로 봉인.

## 왜 이 테스트가 필요한가

`ApiAuthMiddleware.__call__` 은 다음 한 줄로 non-HTTP ASGI scope 를 무판정 통과시킨다
(`src/middleware/api_auth.py`)::

    if scope.get("type") != "http":
        # lifespan·websocket 은 판정 없이 통과. 빠뜨리면 앱이 기동조차 못 한다.
        return await self.app(scope, receive, send)

`lifespan` 통과는 앱 기동에 필수라 정당하지만, 같은 분기가 **`websocket` scope 도
함께** 통과시킨다 — 즉 `@app.websocket(...)` 로 라우트 하나만 추가되면 그 경로는
`X-API-Key`/Origin 검사를 전혀 거치지 않고 열린다(cycle243 의 deny-by-default 계약
바깥). 이 사이클(cycle249) 은 그 사실을 **고치지 않는다**(명세 — 미들웨어 코드
변경 금지) — 대신 오늘 시점에 WebSocket 라우트가 0개임을 봉인해, 미래에 누군가
`@app.websocket(...)` 를 추가하는 순간 이 테스트가 **먼저** 붉어지게 한다. 그 실패가
"인증 처리를 추가하라"는 강제 신호가 된다(리뷰가 놓쳐도 CI 가 잡는다).

## 시세/체결통보 WebSocket 과 무관

`src/realtime/websocket.py` 의 KIS WebSocket 은 **우리 서버가 클라이언트로서** KIS
서버에 접속하는 아웃바운드 연결이지, FastAPI 가 라우트로 노출하는 인바운드
`WebSocketRoute` 가 아니다 — 이 가드가 보는 것은 오직 `src.main.app` 이 스스로
노출하는 ASGI 라우트 표면이다.
"""

from __future__ import annotations

import pytest
from starlette.routing import WebSocketRoute

pytestmark = pytest.mark.unit


def _iter_routes(routes):
    """중첩 `Mount`(있다면) 까지 재귀적으로 펼친다 — FastAPI `include_router` 는
    보통 라우트를 평탄화해 붙이지만, 향후 `Mount` 가 추가돼도 놓치지 않는다."""
    for route in routes:
        yield route
        nested = getattr(route, "routes", None)
        if nested:
            yield from _iter_routes(nested)


def test_app_routes_when_enumerated_then_zero_websocket_routes():
    """구조 가드 — `src.main.app` 에 `WebSocketRoute` 가 0개.

    `ApiAuthMiddleware` 는 `scope["type"] != "http"` 를 무판정 통과시키므로,
    WebSocket 라우트가 하나라도 등록되면 그 경로는 `X-API-Key`/Origin 검사
    바깥에 선다. 추가되는 순간 이 assert 가 붉어져 인증 처리(전용 검사 삽입 또는
    명시적 위험 인수)를 강제한다 — "조용히 열린 새 표면" 을 리뷰 누락에 맡기지 않는다.
    """
    from src.main import app

    ws_routes = [r for r in _iter_routes(app.routes) if isinstance(r, WebSocketRoute)]
    assert ws_routes == [], (
        f"WebSocketRoute 가 신규 등록됐다({[getattr(r, 'path', r) for r in ws_routes]}) — "
        "ApiAuthMiddleware 는 websocket scope 를 무판정 통과시킨다(cycle243 §설계). "
        "이 경로에 명시적 인증(예: 최초 메시지 토큰 검증)을 추가한 뒤에만 이 가드를 "
        "갱신하라."
    )
