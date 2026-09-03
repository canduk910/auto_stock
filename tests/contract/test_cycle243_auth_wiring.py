"""cycle243 Red (B) — 앱 배선 계약: 인증이 **최외곽**이고 전 라우트를 덮는다.

명세: `_workspace/red/cycle243_api_auth_spec.md` §3.B(B-1~B-5) · §0-⑤

## 왜 별도 그룹인가 (⑦-b 사각 봉합)

⑦ 의 conftest autouse 픽스처는 기존 201 케이스를 인증에 **눈멀게** 만든다. 픽스처만
두면 "미들웨어 등록 줄을 지웠는데 스위트가 전부 초록" 이 성립한다. 이 그룹이 그
사각을 닫는 유일한 가드다 — 그래서 전 케이스가 `@pytest.mark.real_api_auth` 로
픽스처를 옵트아웃한다.

## B-5 는 명세와 구현 방식이 다르다 (안전 사유 — 반드시 읽을 것)

명세 B-5 는 "78개 `/api` 경로를 헤더 없이 호출해 한 건도 200 이 아님" 이다. 그런데
**Red 상태(=인증 부재)에서 그 호출은 실제 핸들러를 실행한다** — `POST /api/trading/
manual-sell` 은 `place_order(side=SELL, price=0)` 로 이어지고, `POST /api/stock-master/
refresh-*` 는 KIS 20/s 한도를 매매 주문 경로와 공유한다. 즉 **테스트가 FAIL 하는 바로
그 상태에서 실주문·실 KIS 호출이 나갈 수 있다.** 회귀 가드가 사고를 만드는 형태는
채택할 수 없다(M-1 뮤테이션 실증 때도 같은 위험이 재현된다).

그래서 B-5 는 **라우트 목록은 실제 `src.main.app` 에서 전수 열거**하되(라우트 추가 시
자동 커버 성질 보존), 요청은 `ApiAuthMiddleware(sentinel)` 로 흘려 **핸들러를 한 번도
호출하지 않는다**. "미들웨어가 실제로 앱에 붙어 있는가" 는 B-1 이 담당한다 —
두 가드가 합쳐져 명세 B-5 의 의도를 온전히 덮는다.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.contract, pytest.mark.real_api_auth]

GOOD_KEY = "cycle243WIRINGKEYaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _mw():
    try:
        import src.middleware.api_auth as mod
    except Exception as exc:  # pragma: no cover - Red 경로
        pytest.fail(f"Red — src/middleware/api_auth.py 미구현: {exc!r}")
    return mod


def _set_key(monkeypatch: pytest.MonkeyPatch, key: str = GOOD_KEY) -> None:
    from src.config import settings

    for name, value in (("api_auth_key", key), ("api_allowed_origins", "")):
        if not hasattr(settings, name):
            pytest.fail(f"Red — settings.{name} 미구현 (src/config.py §2.2)")
        monkeypatch.setattr(settings, name, value)


# ---------------------------------------------------------------------------
# B-1 — 최외곽 등록
# ---------------------------------------------------------------------------
def test_middleware_when_registered_then_outermost():
    """B-1 — `user_middleware[0]` 가 인증. Starlette 는 `insert(0)` + `reversed()` 라
    **마지막에 add 한 것이 가장 바깥**이고 `user_middleware[0]` 가 그것이다.

    M-1(등록 삭제)·M-2(CORS 안쪽으로 이동)가 여기서 죽는다.
    """
    from src.main import app

    mod = _mw()
    assert app.user_middleware, "미들웨어가 하나도 없다"
    assert app.user_middleware[0].cls is mod.ApiAuthMiddleware, [
        m.cls.__name__ for m in app.user_middleware
    ]


# ---------------------------------------------------------------------------
# B-2 / B-3 — 인증이 DoS 증폭기가 되지 않는다
# ---------------------------------------------------------------------------
def test_anonymous_flood_when_rejected_then_metrics_dict_not_grown(monkeypatch):
    """B-2 — 익명 401 은 `_endpoint_metrics` 키를 만들지 않는다.

    `MetricsMiddleware` 는 **정규화 없는 raw path** 로 키잉하고 키 개수 상한이 없다
    (`main.py:48,57-59`). 인증을 metrics 안쪽에 두면 익명 `/api/<랜덤>` 폭주가 매매
    프로세스 안의 dict 를 무한 증식시키고 `GET /api/system/metrics` 가 그걸 되비춘다
    = 인증 계층이 DoS 증폭기가 된다. 이것이 최외곽 배치의 결정적 근거이고, 이 케이스가
    그 논거의 **행위 검증**이다(M-2).
    """
    import src.main as main_mod
    from src.main import app

    _set_key(monkeypatch)
    client = TestClient(app)
    before = len(main_mod._endpoint_metrics)

    for _ in range(30):
        resp = client.get(f"/api/probe-{uuid.uuid4().hex}")
        assert resp.status_code == 401, resp.status_code

    assert len(main_mod._endpoint_metrics) == before, (
        f"익명 요청이 metrics 키를 {len(main_mod._endpoint_metrics) - before}개 늘렸다"
    )


def test_authorized_request_when_passed_then_metrics_still_recorded(monkeypatch):
    """B-3 — 인증 통과 요청은 종전대로 계상된다(관측 회귀 방지)."""
    import src.main as main_mod
    from src.main import app

    _set_key(monkeypatch)
    main_mod._endpoint_metrics.pop("/api/trading/status", None)

    client = TestClient(app)
    resp = client.get("/api/trading/status", headers={"X-API-Key": GOOD_KEY})
    assert resp.status_code == 200
    assert "/api/trading/status" in main_mod._endpoint_metrics


# ---------------------------------------------------------------------------
# B-4 — CORS 잠금 (Phase 2-C)
# ---------------------------------------------------------------------------
def test_cors_when_configured_then_not_wildcard():
    """B-4 — `allow_origins=["*"]` + `allow_credentials=True` 조합 제거.

    starlette 0.46.2 는 `not allow_all_origins or allow_credentials` 로 preflight
    를 **모든 오리진에 허가**한다. Phase 1 이 이걸 악화시킨다 — 브라우저가 Basic 자격을
    캐시하고 nginx 의 X-API-Key 주입은 출처를 구분하지 못한다.
    """
    from src.main import app

    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "CORSMiddleware 등록이 사라졌다"
    origins = cors[0].kwargs.get("allow_origins")
    assert origins != ["*"], "CORS 와일드카드가 그대로다"
    assert "*" not in (origins or []), origins


# ---------------------------------------------------------------------------
# B-5 — 전 라우트 전수 (핸들러 미실행)
# ---------------------------------------------------------------------------
def _api_route_cases() -> list[tuple[str, str]]:
    from src.main import app

    cases: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods or not path.startswith("/api"):
            continue
        concrete = path
        while "{" in concrete and "}" in concrete:
            head, _, rest = concrete.partition("{")
            _, _, tail = rest.partition("}")
            concrete = f"{head}1{tail}"
        for method in sorted(m for m in methods if m not in ("HEAD",)):
            cases.append((method, concrete))
    return sorted(set(cases))


async def test_every_api_route_when_no_header_then_rejected_before_handler(monkeypatch):
    """B-5 — 실제 앱의 모든 `/api` 라우트가 헤더 없이 거부된다.

    핸들러는 한 번도 실행하지 않는다(파일 docstring 의 안전 사유 참조).
    """
    mod = _mw()
    _set_key(monkeypatch)

    reached: list[tuple[str, str]] = []

    async def _sentinel(scope, receive, send):
        reached.append((scope["method"], scope["path"]))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    app = mod.ApiAuthMiddleware(_sentinel)
    cases = _api_route_cases()
    assert len(cases) >= 70, f"라우트 열거가 깨졌다 — {len(cases)}건"

    allowed: list[tuple[str, str]] = []
    for method, path in cases:
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": [(b"host", b"testserver")],
                "client": ("203.0.113.9", 51234),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )
        status = next(
            (m["status"] for m in sent if m.get("type") == "http.response.start"), None
        )
        if status != 401:
            allowed.append((method, path))

    assert not allowed, f"인증 없이 통과한 라우트 {len(allowed)}건: {allowed[:10]}"
    assert not reached, f"핸들러(sentinel)에 도달한 요청 {len(reached)}건"
