"""cycle243 Red (A) — 백엔드 X-API-Key 인증 미들웨어 단위 계약.

명세: `_workspace/red/cycle243_api_auth_spec.md` §3.A(A-1~A-23) · 구현 계약 §2.3

## 고칠 결함 (한 문장)

`curl http://3.38.228.74/api/trading/status` 가 **200** 을 돌려준다 — 인터넷의 누구나
`POST /api/trading/manual-sell`(임의 종목·수량 시장가 매도) · `POST /api/trading/stop`
(13포지션 손절·트레일링 정지) · `PUT /api/strategies/{id}/params`(손절%·max_positions
임의 설정) 를 호출할 수 있고, 인증 코드는 코드베이스 전체에 **0건**이다.

## 이 파일이 봉인하는 seam (구현 계약 — 이름·형태가 다르면 FAIL 한다)

`src/middleware/api_auth.py`
  * `ApiAuthMiddleware(app)` — **순수 ASGI**. `BaseHTTPMiddleware` 금지(명세 §0-6:
    anyio portal hang 선례 2건 + stock_master BackgroundTasks 폴링).
  * `authorize(scope) -> str` — **모듈 레벨 함수**. `""` = 통과, 그 외 = 거부 사유.
    미들웨어 `__call__` 은 이 이름을 **한정하지 않은 전역**으로 호출한다. 메서드
    (`self._authorize`)로 만들면 ⑦ 의 conftest seam(기존 201 케이스 보호)이 성립하지
    않는다 — A-17 이 그 호출 형태를 행위로 잡고, D-12(phase2 AST)가 구조로 잡는다.
  * `log_startup_state() -> None` — 기동 1회 로그(A-22).

`src/config.py` — `api_auth_key: str = ""` · `api_allowed_origins: str = ""`.

## 설계 메모 (명세 문언과 다르게 구현한 곳 + 이유)

1. **A-4(헤더 대소문자)는 TestClient 로 검증할 수 없다.** httpx 0.28.1 `ASGITransport`
   가 `[(k.lower(), v) for ...]` 로 **미리 소문자화**해 scope 에 넣는다(실측) — 그
   위에서 대소문자 무관을 주장하면 공허하다. raw 헤더를 담은 scope 로 미들웨어를
   직접 구동한다.
2. **로그 cap(A-18)은 내부 이름(`_reject_counts`)을 찍지 않고 행위로 검증한다.**
   "서로 다른 150 경로 · 같은 사유" 가 3행만 남으면 cap 키가 `reason` 단독임이 증명
   되고, M-12(cap 키를 `(reason, path)` 로)는 자동으로 150행이 돼 잡힌다. 내부
   attribute 를 찍으면 이름만 바꿔도 가드가 죽는다.
3. **카운터 리셋도 내부 훅 대신 `freeze_time` 날짜 이동**으로 만든다(§2.3.9 자기 리셋).
   덕분에 로그를 보는 케이스마다 고유 날짜를 써서 `count=1` 발화를 보장한다 —
   그렇지 않으면 "키가 로그에 없다"(A-20) 같은 단언이 *로그가 아예 없어서* 통과하는
   공허한 초록이 된다.
   ⚠️ 프로즌 날짜는 **정의 순서대로 09-10 → 09-15 단조 증가**시켰다. 카운터 리셋을
   `!=` 가 아니라 `>` 로 구현해도 케이스가 서로를 오염시키지 않게 하려는 것이다
   (날짜를 되돌리면 `>` 구현에서 리셋이 안 걸려 이전 케이스의 카운트가 새어 든다).
   새 케이스를 끼워 넣을 때 이 단조성을 깨지 마라.
"""

from __future__ import annotations

import logging
import re

import pytest
from freezegun import freeze_time

pytestmark = [pytest.mark.unit, pytest.mark.real_api_auth]

# 44자 = `secrets.token_urlsafe(32)` 길이(§0-⑭ 권장 규격)
GOOD_KEY = "cycle243GOODKEYaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
BAD_KEY = "cycle243ATTACKERKEYbbbbbbbbbbbbbbbbbbbbbbbbbb"
API_PATH = "/api/trading/status"

REJECT_MARKER = "[api_auth_reject]"


# ---------------------------------------------------------------------------
# Red 헬퍼 — 미구현 상태를 "수집 에러" 가 아니라 케이스별 FAIL 로 보고한다
# ---------------------------------------------------------------------------
def _mw():
    try:
        import src.middleware.api_auth as mod
    except Exception as exc:  # pragma: no cover - Red 경로
        pytest.fail(f"Red — src/middleware/api_auth.py 미구현: {exc!r}")
    return mod


def _set_settings(monkeypatch: pytest.MonkeyPatch, **kwargs) -> None:
    from src.config import settings

    for name, value in kwargs.items():
        if not hasattr(settings, name):
            pytest.fail(f"Red — settings.{name} 미구현 (src/config.py §2.2)")
        monkeypatch.setattr(settings, name, value)


# ---------------------------------------------------------------------------
# 테스트용 하위 앱 (라우터·DB·KIS 무관 — 미들웨어만 검사한다)
# ---------------------------------------------------------------------------
_ECHO_BODY = b'{"echo": true}'


async def _echo_app(scope, receive, send):
    """어떤 http 경로에도 200 을 주는 하위 앱 + lifespan 처리."""
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": _ECHO_BODY})


def _client(monkeypatch, *, key: str = GOOD_KEY, allowed_origins: str = "", app=_echo_app):
    from starlette.testclient import TestClient

    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=key, api_allowed_origins=allowed_origins)
    return TestClient(mod.ApiAuthMiddleware(app))


def _scope(
    *,
    method: str = "GET",
    path: str = API_PATH,
    headers: list[tuple[bytes, bytes]] | None = None,
    type_: str = "http",
) -> dict:
    return {
        "type": type_,
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8", "surrogateescape"),
        "query_string": b"",
        "root_path": "",
        "headers": list(headers or []),
        "client": ("203.0.113.9", 51234),
        "server": ("testserver", 80),
    }


async def _drive(app, scope) -> list[dict]:
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return sent


def _status_of(sent: list[dict]) -> int | None:
    for message in sent:
        if message.get("type") == "http.response.start":
            return int(message["status"])
    return None


def _reject_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if REJECT_MARKER in r.getMessage()]


# ---------------------------------------------------------------------------
# A-1 ~ A-3 — 기본 판정
# ---------------------------------------------------------------------------
def test_correct_key_when_header_present_then_200(monkeypatch):
    """A-1 — 키 설정 + 올바른 `X-API-Key` → 200."""
    client = _client(monkeypatch)
    resp = client.get(API_PATH, headers={"X-API-Key": GOOD_KEY})
    assert resp.status_code == 200


def test_missing_header_when_key_configured_then_401_envelope(monkeypatch):
    """A-2 — 헤더 없음 → 401 ∧ ApiResponse 봉투 ∧ WWW-Authenticate 미부착(§2.3.7)."""
    client = _client(monkeypatch)
    resp = client.get(API_PATH)
    assert resp.status_code == 401
    body = resp.json()
    assert body.get("success") is False
    assert body.get("data") is None
    assert body.get("message") == "unauthorized"
    # 백엔드가 다이얼로그를 띄우면 Phase 1 basic auth 자격과 혼동된다.
    assert "www-authenticate" not in {k.lower() for k in resp.headers.keys()}


def test_wrong_key_when_header_present_then_401(monkeypatch):
    """A-3 — 틀린 키 → 401."""
    client = _client(monkeypatch)
    resp = client.get(API_PATH, headers={"X-API-Key": BAD_KEY})
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "raw_name", [b"X-API-Key", b"x-api-key", b"X-Api-Key", b"X-API-KEY"]
)
async def test_header_name_when_any_case_then_accepted(monkeypatch, raw_name):
    """A-4 — 헤더 이름 대소문자 무관.

    TestClient(httpx) 는 헤더를 미리 소문자화하므로 raw scope 로 직접 구동한다.
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)
    sent = await _drive(app, _scope(headers=[(raw_name, GOOD_KEY.encode())]))
    assert _status_of(sent) == 200


# ---------------------------------------------------------------------------
# A-5 / A-6 — fail-closed 핵심
# ---------------------------------------------------------------------------
def test_unset_key_when_no_header_then_401_fail_closed(monkeypatch):
    """A-5 — `API_AUTH_KEY` 미설정이면 **열리는 게 아니라 잠긴다**.

    fail-open 은 "키가 없으면 인증이 조용히 사라진다" = 이 사이클이 고치려는 결함의
    정확한 재현이다(명세 §0-④). 매매 엔진은 in-process 라 폭발 반경은 대시보드뿐.
    """
    client = _client(monkeypatch, key="")
    assert client.get(API_PATH).status_code == 401


@pytest.mark.parametrize("header_value", ["", " "])
def test_unset_key_when_empty_header_then_401(monkeypatch, header_value):
    """A-6 — `compare_digest("", "") is True` 함정 봉인.

    빈 키 선분기가 헤더 비교보다 **앞**에 없으면 미설정 상태에서 빈 헤더가 통과한다
    (§2.3.3). M-11(빈 키 선분기 삭제)이 여기서 죽는다.
    """
    client = _client(monkeypatch, key="")
    assert client.get(API_PATH, headers={"X-API-Key": header_value}).status_code == 401


# ---------------------------------------------------------------------------
# A-7 / A-8 / A-9 — 보호 범위 (deny-by-default, `/health` 만 예외)
# ---------------------------------------------------------------------------
def test_health_when_no_header_then_200(monkeypatch):
    """A-7 — `/health` 는 무인증 통과(유일 예외)."""
    client = _client(monkeypatch)
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
def test_fastapi_docs_when_no_header_then_401(monkeypatch, path):
    """A-8 — `/api` 접두사 스코프 기각(§0-⑤-c).

    `main.py` 가 `docs_url` 을 끄지 않아 78개 엔드포인트 스키마(manual-sell·weights
    요청 스키마 포함)가 열려 있다. M-5(`/api` 접두사 축소)·M-6(`/docs` 예외)가 여기서 죽는다.
    """
    client = _client(monkeypatch)
    assert client.request("GET", path).status_code == 401


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_api_paths_when_no_header_then_401_for_all_methods(monkeypatch, method):
    """A-9 — 상태변경 메서드 포함 전 메서드 401."""
    client = _client(monkeypatch)
    assert client.request(method, "/api/trading/manual-sell").status_code == 401


def test_options_when_no_header_then_401_and_with_key_then_200(monkeypatch):
    """A-10 — preflight 예외 없음(§0-⑤-b). M-7(OPTIONS 무조건 통과)이 여기서 죽는다."""
    client = _client(monkeypatch)
    assert client.request("OPTIONS", API_PATH).status_code == 401
    assert (
        client.request("OPTIONS", API_PATH, headers={"X-API-Key": GOOD_KEY}).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# A-11 — 비-http scope 통과 (빠뜨리면 앱이 기동조차 못 한다)
# ---------------------------------------------------------------------------
def test_lifespan_scope_when_wrapped_then_startup_succeeds(monkeypatch):
    """A-11-a — lifespan scope 통과. M-14(scope 게이트 제거)가 여기서 죽는다."""
    from starlette.testclient import TestClient

    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    with TestClient(mod.ApiAuthMiddleware(_echo_app)) as client:
        assert client.get("/health").status_code == 200


async def test_websocket_scope_when_no_header_then_passthrough(monkeypatch):
    """A-11-b — websocket scope 는 인증 판정 없이 하위 앱으로 넘어간다."""
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")

    reached: list[str] = []

    async def _inner(scope, receive, send):
        reached.append(scope["type"])

    app = mod.ApiAuthMiddleware(_inner)
    await _drive(app, _scope(type_="websocket", path="/ws"))
    assert reached == ["websocket"]


# ---------------------------------------------------------------------------
# A-12 ~ A-16 — Origin(CSRF) 검사 (§0-⑫)
# ---------------------------------------------------------------------------
def test_post_when_origin_absent_then_200(monkeypatch):
    """A-12 — Origin 부재는 **허용**. curl·ssh 비상 매도 경로를 절대 깨지 않는다.

    M-10(부재를 거부로)이 여기서 죽는다.
    """
    client = _client(monkeypatch)
    resp = client.post(API_PATH, headers={"X-API-Key": GOOD_KEY}, json={})
    assert resp.status_code == 200


def test_post_when_origin_matches_host_then_200(monkeypatch):
    """A-13 — same-origin(자기 설정형) 허용. prod 는 설정 0으로 동작한다."""
    client = _client(monkeypatch)
    resp = client.post(
        API_PATH,
        headers={"X-API-Key": GOOD_KEY, "Origin": "http://testserver"},
        json={},
    )
    assert resp.status_code == 200


async def test_post_when_cross_origin_then_401_and_logged(monkeypatch, caplog):
    """A-14 — 교차 출처 상태변경 거부 + `reason=cross_origin`.

    CORS 는 simple request 를 **막지 못한다**(응답 읽기만 차단, 요청은 이미 실행).
    `POST /api/trading/stop` 은 본문이 없어 simple request 로 성립하므로 브라우저에
    캐시된 Basic 자격 + nginx 의 무차별 X-API-Key 주입으로 **실행된다**.
    M-8(Origin 검사 제거)이 여기서 죽는다.
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)
    scope = _scope(
        method="POST",
        path="/api/trading/stop",
        headers=[
            (b"x-api-key", GOOD_KEY.encode()),
            (b"host", b"testserver"),
            (b"origin", b"http://evil.example"),
        ],
    )
    with freeze_time("2026-09-10 03:00:00"), caplog.at_level(logging.DEBUG):
        sent = await _drive(app, scope)

    assert _status_of(sent) == 401
    lines = _reject_lines(caplog)
    assert lines, "거부 로그가 한 행도 없다 — 관측 결손"
    assert any("reason=cross_origin" in line for line in lines), lines


def test_get_when_cross_origin_then_200(monkeypatch):
    """A-15 — Origin 검사는 **상태변경 메서드 한정**.

    GET 에 적용하면 대시보드 폴링(18곳·최단 3초)이 통째로 죽는다.
    M-9(GET 에도 적용)가 여기서 죽는다.
    """
    client = _client(monkeypatch)
    resp = client.get(
        API_PATH, headers={"X-API-Key": GOOD_KEY, "Origin": "http://evil.example"}
    )
    assert resp.status_code == 200


def test_post_when_origin_in_allowlist_then_200(monkeypatch):
    """A-16 — `API_ALLOWED_ORIGINS` CSV 등재 오리진 허용(dev vite `changeOrigin`)."""
    client = _client(
        monkeypatch, allowed_origins="http://localhost:3000,http://localhost:5173"
    )
    resp = client.post(
        API_PATH,
        headers={"X-API-Key": GOOD_KEY, "Origin": "http://localhost:3000"},
        json={},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# A-17 — 예외 흡수 (fail-closed) + `authorize` 전역 호출 seam 실증
# ---------------------------------------------------------------------------
def test_authorize_when_raises_then_401(monkeypatch):
    """A-17 — 판정 중 어떤 예외가 나도 401.

    부수 효과로 **`authorize` 를 모듈 전역 이름으로 호출한다**는 계약을 행위로 실증
    한다(메서드로 감추면 이 주입이 먹지 않아 500/200 이 된다 = M-21 조기 검출).
    """
    from starlette.testclient import TestClient

    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")

    def _boom(scope):
        raise RuntimeError("판정 폭발")

    monkeypatch.setattr(mod, "authorize", _boom)
    client = TestClient(mod.ApiAuthMiddleware(_echo_app))
    resp = client.get(API_PATH, headers={"X-API-Key": GOOD_KEY})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# A-18 ~ A-21 — 거부 로그 cap · 로그 인젝션 · 비밀 유출 · 자기 리셋
# ---------------------------------------------------------------------------
async def test_reject_log_when_150_distinct_paths_then_capped_by_reason(
    monkeypatch, caplog
):
    """A-18 — cap 키는 `reason` 단독. 경로를 키에 넣으면 무제한 메모리 증가 벡터다.

    150회 거부(전부 서로 다른 경로, 같은 사유) → `count ∈ {1,10,100}` 3행만.
    M-12(cap 키를 `(reason, path)` 로)면 150행이 되어 FAIL.
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)

    with freeze_time("2026-09-11 03:00:00"), caplog.at_level(logging.DEBUG):
        for i in range(150):
            sent = await _drive(app, _scope(path=f"/api/probe-{i}"))
            assert _status_of(sent) == 401

    lines = _reject_lines(caplog)
    counts = [int(m.group(1)) for line in lines for m in [re.search(r"count=(\d+)", line)] if m]
    assert counts == [1, 10, 100], f"기대 3행(1·10·100), 실제 {len(lines)}행 counts={counts}"


async def test_reject_log_when_path_has_newline_then_sanitized(monkeypatch, caplog):
    """A-19 — 로그 인젝션 차단: 개행 제거 + 80자 절단.

    인터넷 노출면이라 경로는 공격자 입력이다. 개행이 살아 있으면 위조 로그 행을
    `system_logs` 에 심을 수 있다(`_DbLogHandler` 가 INFO 이상을 그대로 나른다).
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)

    hostile = "/api/\n[fake_marker] injected\r" + ("A" * 200)
    with freeze_time("2026-09-12 03:00:00"), caplog.at_level(logging.DEBUG):
        sent = await _drive(app, _scope(path=hostile))
    assert _status_of(sent) == 401

    lines = _reject_lines(caplog)
    assert lines, "거부 로그가 한 행도 없다 — 단언이 공허해진다"
    for line in lines:
        assert "\n" not in line and "\r" not in line, repr(line)
        assert "A" * 81 not in line, "path 80자 절단 미적용"


async def test_reject_log_when_secrets_present_then_never_leaked(monkeypatch, caplog):
    """A-20 — 설정 키·수신 헤더 값은 로그·응답 어디에도 남지 않는다(§2.3.6).

    M-13(거부 로그에 수신 헤더 값 포함)이 여기서 죽는다.
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)

    with freeze_time("2026-09-13 03:00:00"), caplog.at_level(logging.DEBUG):
        sent = await _drive(
            app,
            _scope(headers=[(b"x-api-key", BAD_KEY.encode())]),
        )
    assert _status_of(sent) == 401

    lines = _reject_lines(caplog)
    assert lines, "거부 로그가 한 행도 없다 — 단언이 공허해진다"
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert GOOD_KEY not in blob, "설정 키가 로그에 유출됐다"
    assert BAD_KEY not in blob, "수신 헤더 값이 로그에 유출됐다"

    body = b"".join(m.get("body", b"") for m in sent if m.get("type") == "http.response.body")
    assert GOOD_KEY.encode() not in body and BAD_KEY.encode() not in body


async def test_reject_counter_when_day_rolls_over_then_self_resets(monkeypatch, caplog):
    """A-21 — 날짜 키 자기 리셋.

    `DailyEmitCap` 은 스스로 롤오버하지 않고 외부 `reset_daily()` 호출자에 의존하는데
    미들웨어엔 그 훅이 없다(§0-⑧). 리셋이 없으면 이튿날 거부가 영영 무음이 된다.
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)

    with caplog.at_level(logging.DEBUG):
        with freeze_time("2026-09-14 03:00:00"):
            for i in range(15):
                await _drive(app, _scope(path=f"/api/day1-{i}"))
        day1 = len(_reject_lines(caplog))
        assert day1 == 2, f"1일차 기대 2행(1·10), 실제 {day1}"

        caplog.clear()
        with freeze_time("2026-09-15 03:00:00"):
            await _drive(app, _scope(path="/api/day2-0"))

    lines = _reject_lines(caplog)
    assert lines, "이튿날 첫 거부가 무음 — 카운터가 리셋되지 않았다"
    assert "count=1" in lines[0], lines


async def test_reject_log_when_observer_raises_then_auth_path_intact(monkeypatch, caplog):
    """A-24 — 관측기의 자기 실패가 (a) 인증 경로를 깨지 않고 (b) 영구 침묵도 아니다.

    이 리포가 두 번 데인 구조다. cycle226 L-2 = 로그용 `int()` 가 `try` **밖**이라
    던지면 뒤의 청산 분기가 통째로 유실됐다. cycle226 D-3 / cycle233 F4 = cap 등록이
    로그 **앞**이라 로그가 던지면 그 키가 종일 봉인됐다(관측기 자기실패가 관측 대상을
    지운다). 여기서는 거부 응답(401)이 로깅 성패와 **무관**해야 하고, 한 번 실패한 뒤에도
    다음 임계 행이 정상 발화해야 한다.
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)

    assert hasattr(mod, "logger"), "모듈 레벨 `logger` 부재 (리포 공통 관례)"
    real_warning = mod.logger.warning
    calls = {"n": 0}

    def _flaky_warning(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("관측기 폭발")
        return real_warning(*args, **kwargs)

    monkeypatch.setattr(mod.logger, "warning", _flaky_warning)

    with freeze_time("2026-09-16 03:00:00"), caplog.at_level(logging.DEBUG):
        first = await _drive(app, _scope(path="/api/observer-0"))
        assert _status_of(first) == 401, "관측기 예외가 인증 응답을 삼켰다"
        for i in range(1, 15):
            sent = await _drive(app, _scope(path=f"/api/observer-{i}"))
            assert _status_of(sent) == 401

    assert calls["n"] >= 2, "첫 실패 이후 관측이 영구 침묵했다"
    assert any("count=10" in line for line in _reject_lines(caplog)), _reject_lines(caplog)


async def test_reject_reason_when_logged_then_within_fixed_four(monkeypatch, caplog):
    """A-25 — 거부 사유는 4종 고정(`no_key_configured`·`missing_header`·`bad_key`·
    `cross_origin`)이고 상황별로 **구분**된다.

    사유는 cap 키이자 운영자의 유일한 진단 채널이다(응답은 401 단일 — 미설정 상태를
    503 으로 구분하면 공격자에게 "이 박스는 키가 없다"를 알려준다, §0-④-b).
    """
    from src.config import settings

    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)

    with freeze_time("2026-09-17 03:00:00"), caplog.at_level(logging.DEBUG):
        await _drive(app, _scope(path="/api/r-missing"))
        await _drive(
            app,
            _scope(path="/api/r-bad", headers=[(b"x-api-key", BAD_KEY.encode())]),
        )
        monkeypatch.setattr(settings, "api_auth_key", "")
        await _drive(app, _scope(path="/api/r-nokey"))

    lines = _reject_lines(caplog)
    reasons = {m.group(1) for line in lines for m in [re.search(r"reason=(\w+)", line)] if m}
    assert {"missing_header", "bad_key", "no_key_configured"} <= reasons, reasons
    assert reasons <= {
        "no_key_configured",
        "missing_header",
        "bad_key",
        "cross_origin",
    }, f"고정 4종 밖 사유: {reasons}"


# ---------------------------------------------------------------------------
# A-22 / A-23 — 기동 로그 · 요청 시점 설정 참조
# ---------------------------------------------------------------------------
def test_startup_log_when_key_missing_then_critical(monkeypatch, caplog):
    """A-22-a — 키 부재 = CRITICAL + 변수명 명시(값 미포함).

    fail-closed 의 유일한 진단 채널이다. 키 없는 개발자가 401 을 자가 진단하는 경로.
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key="", api_allowed_origins="")
    with caplog.at_level(logging.DEBUG):
        mod.log_startup_state()

    critical = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
    assert critical, "키 부재인데 CRITICAL 이 없다"
    blob = "\n".join(r.getMessage() for r in critical)
    assert "[api_auth_key_missing]" in blob
    assert "API_AUTH_KEY" in blob


def test_startup_log_when_key_weak_then_warning_without_value(monkeypatch, caplog):
    """A-22-b — `len < 24` 는 WARNING, 값은 절대 출력하지 않는다."""
    mod = _mw()
    weak = "shortkey123"
    _set_settings(monkeypatch, api_auth_key=weak, api_allowed_origins="")
    with caplog.at_level(logging.DEBUG):
        mod.log_startup_state()

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "[api_auth_key_weak]" in blob
    assert weak not in blob, "약한 키 경고에 키 값이 실렸다"
    assert any(
        r.levelno == logging.WARNING and "[api_auth_key_weak]" in r.getMessage()
        for r in caplog.records
    )


def test_startup_log_when_key_ok_then_info_without_value(monkeypatch, caplog):
    """A-22-c — 정상 키 = INFO `[api_auth_config] enabled=true key_len=44 …`."""
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    with caplog.at_level(logging.DEBUG):
        mod.log_startup_state()

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "[api_auth_config]" in blob
    assert "enabled=true" in blob
    assert f"key_len={len(GOOD_KEY)}" in blob
    assert GOOD_KEY not in blob
    assert "[api_auth_key_missing]" not in blob


def test_key_when_rotated_at_runtime_then_read_per_request(monkeypatch):
    """A-23 — 키는 **요청 시점**에 읽는다. `__init__` 캡처면 M-15 로 죽는다.

    `settings` 는 import 시점 싱글톤이라(`config.py:95`) 캡처형 구현은 테스트 seam 도
    운영 진단도 동시에 막는다.
    """
    from starlette.testclient import TestClient
    from src.config import settings

    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    client = TestClient(mod.ApiAuthMiddleware(_echo_app))
    assert client.get(API_PATH, headers={"X-API-Key": GOOD_KEY}).status_code == 200

    rotated = "cycle243ROTATEDKEYcccccccccccccccccccccccccc"
    monkeypatch.setattr(settings, "api_auth_key", rotated)
    assert client.get(API_PATH, headers={"X-API-Key": GOOD_KEY}).status_code == 401
    assert client.get(API_PATH, headers={"X-API-Key": rotated}).status_code == 200


# ---------------------------------------------------------------------------
# A-25 ~ A-28 — 적대적 검증 후속 (cycle243 라운드 1 시정)
# ---------------------------------------------------------------------------
async def test_allowed_origins_when_wildcard_then_cross_origin_still_rejected(
    monkeypatch, caplog
):
    """A-25 — `API_ALLOWED_ORIGINS=*` 한 줄로 CSRF 문이 열리지 않는다.

    종전 `parse_allowed_origins` 는 `*` 를 그대로 목록에 담았다. 그러면 (a) 이 모듈의
    Origin 검사가 어떤 오리진이든 통과시키고 (b) `src/main.py` 의 CORS 가
    `allow_all_origins=True` 가 되어 결정 ⑪ 이 제거한 `["*"] + allow_credentials`
    조합이 **경고 한 줄 없이** 부활한다. 값 검증도 기동 경고도 회귀 가드도 없었다.

    설계: 조용히 받아들이지도, 조용히 버리지도 않는다 — 버리고 **시끄럽게** 알린다.
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="*")
    app = mod.ApiAuthMiddleware(_echo_app)

    with freeze_time("2026-09-18 03:00:00"), caplog.at_level(logging.DEBUG):
        sent = await _drive(
            app,
            _scope(
                method="POST",
                headers=[
                    (b"x-api-key", GOOD_KEY.encode()),
                    (b"origin", b"http://evil.example"),
                    (b"host", b"testserver"),
                ],
            ),
        )
        assert _status_of(sent) == 401, "와일드카드가 교차 출처 상태변경을 통과시켰다"
        assert any("cross_origin" in line for line in _reject_lines(caplog))

        caplog.clear()
        mod.log_startup_state()

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "[api_auth_wildcard_origin]" in blob, blob
    assert "allowed_origins=0" in blob, "무시한 뒤 개수에도 반영돼야 한다"


async def test_reject_log_when_behind_proxy_then_ip_from_forwarded_headers(
    monkeypatch, caplog
):
    """A-26 — `ip=` 는 nginx 가 넣어 주는 헤더에서 온다(+ `ip_src` 출처 태그).

    Phase 2 는 backend 를 `127.0.0.1:8000` 에 묶어 외부 요청이 전부 nginx 를 거치고,
    uvicorn 은 `--proxy-headers` 없이 뜬다 ⇒ `scope["client"]` 는 항상 nginx 컨테이너
    주소다. 그 상수를 공격자 IP 처럼 찍으면 포렌식 가치가 0을 넘어 **오독을 만든다**.
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)

    with freeze_time("2026-09-19 03:00:00"), caplog.at_level(logging.DEBUG):
        sent = await _drive(
            app,
            _scope(
                headers=[
                    (b"x-real-ip", b"198.51.100.7"),
                    (b"x-forwarded-for", b"1.2.3.4, 198.51.100.7"),
                ]
            ),
        )
    assert _status_of(sent) == 401

    lines = _reject_lines(caplog)
    assert lines, "거부 로그가 한 행도 없다 — 단언이 공허해진다"
    assert "ip=198.51.100.7" in lines[0], lines
    assert "ip_src=xri" in lines[0], lines
    # scope["client"](=프록시 주소)가 대신 찍히면 안 된다.
    assert "203.0.113.9" not in lines[0], lines


@pytest.mark.parametrize(
    "host,expected,note",
    [
        (b"127.0.0.1:8080", 200, "nginx `$http_host` — 원 포트 보존"),
        (b"127.0.0.1", 401, "nginx `$host` — 포트 탈락 ⇒ SSH 터널 접근 전면 차단"),
    ],
)
async def test_post_when_non_default_port_then_host_must_keep_port(
    monkeypatch, host, expected, note
):
    """A-27 — 80 이 아닌 포트로 붙었을 때의 상태변경 판정.

    이 케이스가 `frontend/nginx.conf.template` 의 `Host $http_host` 계약(D-2-b)의
    **행위 근거**다. `$host` 로 두면 SSH 터널(`ssh -L 8080:localhost:80`) 접근에서
    start/stop/manual-sell·비중 저장이 전부 `cross_origin` 401 이 되고, 그 실패는
    조용하다(UI 401 처리 부재, L10). 후속 F2(SG 80 을 운영자 IP 로 제한)를 채택하면
    터널이 표준 접근이 되므로 지금 못박는다.
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)

    sent = await _drive(
        app,
        _scope(
            method="POST",
            headers=[
                (b"x-api-key", GOOD_KEY.encode()),
                (b"origin", b"http://127.0.0.1:8080"),
                (b"host", host),
            ],
        ),
    )
    assert _status_of(sent) == expected, note


@pytest.mark.parametrize(
    "origin,host",
    [
        (b"http://backend:8000", b"backend:8000"),  # docker compose dev
        (b"http://localhost:8001", b"localhost:8001"),  # 로컬 `npm run dev`
    ],
)
async def test_dev_proxy_shape_when_origin_normalized_then_state_change_allowed(
    monkeypatch, origin, host
):
    """A-28 — dev 대시보드의 **상태변경**이 살아 있다(설정 0).

    vite `changeOrigin: true` 는 Host 만 target 으로 바꾸고 브라우저 Origin
    (`http://localhost:3000`)은 그대로 넘긴다 ⇒ 그대로 두면 시작·정지·비중 저장·
    파라미터 적용이 전부 401 이고, GET 폴링만 통과해 **화면은 멀쩡한데 버튼만 죽는다**.
    `frontend/vite.config.ts` 가 `Origin: apiTarget` 으로 정규화해 이 형태를 만든다
    (구조 축 = D-9-b).
    """
    mod = _mw()
    _set_settings(monkeypatch, api_auth_key=GOOD_KEY, api_allowed_origins="")
    app = mod.ApiAuthMiddleware(_echo_app)

    sent = await _drive(
        app,
        _scope(
            method="POST",
            headers=[
                (b"x-api-key", GOOD_KEY.encode()),
                (b"origin", origin),
                (b"host", host),
            ],
        ),
    )
    assert _status_of(sent) == 200, "dev 상태변경이 cross_origin 401 로 죽었다"
