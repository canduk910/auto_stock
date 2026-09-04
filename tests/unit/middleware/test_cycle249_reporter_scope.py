"""cycle249 Red (B) — 리포터 스코프 키(`API_REPORTER_KEY`) 판정 계약.

명세: `_workspace/red/cycle249_reporter_scope_spec.md` §B · §H(미들웨어)

## 왜 이 스코프가 필요한가 (지우기 전에 읽을 것)

매일 20:20 KST 클라우드 루틴이 백엔드에서 **당일 로그 번들을 GET** 해 분석한 뒤
`POST /api/log-reports/{date}/external` 로 결과를 돌려준다. 그 번들 안에는 KIS 거부
메시지·전략 로그 등 **외부에서 흘러든 문자열**이 섞여 있다. 즉 루틴은 prompt injection
표면이고, 그 루틴이 쥔 자격이 `POST /api/trading/manual-sell`(임의 종목·수량 시장가
매도)·`POST /api/trading/stop`·`PUT /api/strategies/{id}/params` 에 닿으면 **로그 한 줄이
매매 조작으로 승격**된다. 그래서 리포터 자격은 구조적으로 GET/HEAD + 리포트 POST
**단 한 경로**로 잘라 둔다.

## 스코프가 "키를 보내는 쪽"이 아니라 "Basic 사용자"에서 나오는 이유

cycle243 이후 nginx `location /api/` 는 `proxy_set_header X-API-Key …` 로 백엔드 키를
**치환 주입**한다 — `proxy_set_header` 는 클라이언트가 보낸 동명 헤더를 덮으므로
"루틴이 스코프 키를 보낸다" 는 설계는 애초에 성립하지 않는다(운영 키로 덮인다).
그래서 스코프는 nginx `map $remote_user` 가 Basic 사용자 `reporter` 에게만 다른 키를
주입하는 방식으로 만들고, **백엔드는 도착한 키 값으로 역할을 판정**한다. 이 파일은
그 백엔드 측 판정만 검증한다(nginx 렌더 축은 cycle249 AST 가드 + 실 nginx 검증).

## 봉인하는 seam (이름·형태가 다르면 FAIL)

`src/middleware/api_auth.py`
  * `REASON_REPORTER_SCOPE == "reporter_scope"` · `REASONS` 5종
  * `REPORTER_READ_METHODS` — GET/HEAD (POST 편입 금지)
  * `REPORTER_WRITE_PATH_RE` — 리포트 POST 1경로, 앵커된 정확 일치
  * `authorize(scope) -> str` 모듈 레벨 함수(cycle243 계약 유지 — conftest seam)
  * `log_startup_state()` 의 `[api_auth_config]` 에 `reporter_enabled=`
`src/config.py` — `api_reporter_key: str = ""`(기본 빈 값 = 리포터 역할 **비활성**)

## 재사용 (복붙 금지)

cycle243 미들웨어 단위 테스트의 리그(`_scope`/`_drive`/`_echo_app`/`_set_settings`)를
그대로 쓴다. 저쪽이 raw ASGI scope 로 구동하는 이유(httpx 가 헤더를 미리 소문자화해
대소문자 계약을 공허하게 만든다 · TestClient 우회)가 여기서도 그대로 유효하다.

⚠️ 프로즌 날짜는 **정의 순서대로 단조 증가**시킨다(cycle243 설계 메모 3 과 동일 이유 —
거부 카운터를 `!=` 가 아니라 `>` 로 구현해도 케이스가 서로를 오염시키지 않게 한다).
"""

from __future__ import annotations

import logging
import re

import pytest
from freezegun import freeze_time

# cycle243 리그 재사용 — 복붙 금지.
from tests.unit.middleware.test_cycle243_api_auth import (
    BAD_KEY,
    GOOD_KEY as OPERATOR_KEY,
    REJECT_MARKER,
    _drive,
    _echo_app,
    _mw,
    _reject_lines,
    _scope,
    _set_settings,
    _status_of,
)

pytestmark = [pytest.mark.unit, pytest.mark.real_api_auth]

# 44자 = `secrets.token_urlsafe(32)` 규격. 운영 키와 **다른** 값이어야 판정을 검증한다.
REPORTER_KEY = "cycle249REPORTERKEYcccccccccccccccccccccccc"

#: 리포터에게 허용된 **유일한 쓰기** 경로.
EXTERNAL_PATH = "/api/log-reports/2026-09-04/external"
#: 리포터가 읽어야 하는 입력 번들.
BUNDLE_PATH = "/api/log-reports/bundle"
#: 리포터가 절대 도달하면 안 되는 상태변경 경로(이 스코프가 존재하는 이유).
MANUAL_SELL_PATH = "/api/trading/manual-sell"

FORBIDDEN_STATUS = 403
UNAUTHORIZED_STATUS = 401


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _app(
    monkeypatch,
    *,
    api_auth_key: str = OPERATOR_KEY,
    api_reporter_key: str = REPORTER_KEY,
    api_allowed_origins: str = "",
):
    """미들웨어 + echo 하위 앱. 설정은 요청 시점 참조(cycle243 §2.3.5)라 매번 갈아끼운다."""
    mod = _mw()
    _set_settings(
        monkeypatch,
        api_auth_key=api_auth_key,
        api_reporter_key=api_reporter_key,
        api_allowed_origins=api_allowed_origins,
    )
    return mod.ApiAuthMiddleware(_echo_app)


def _hdr(key: str, extra: list[tuple[bytes, bytes]] | None = None):
    return [(b"x-api-key", key.encode())] + list(extra or [])


def _body_of(sent: list[dict]) -> bytes:
    return b"".join(
        m.get("body") or b"" for m in sent if m.get("type") == "http.response.body"
    )


# ---------------------------------------------------------------------------
# R-1 ~ R-3 — 읽기 허용
# ---------------------------------------------------------------------------
async def test_reporter_key_when_get_then_200(monkeypatch):
    """R-1 — 리포터 키 + GET → 통과.

    루틴은 번들을 GET 으로 읽는다. 읽기가 막히면 이관 자체가 성립하지 않는다.
    """
    app = _app(monkeypatch)
    sent = await _drive(app, _scope(method="GET", path=BUNDLE_PATH, headers=_hdr(REPORTER_KEY)))
    assert _status_of(sent) == 200


async def test_reporter_key_when_head_then_200(monkeypatch):
    """R-2 — HEAD 도 읽기다(부작용 없는 메서드).

    HEAD 를 막으면 헬스 체크·존재 확인이 403 이 되는데, 그건 방어가 아니라 잡음이다.
    """
    app = _app(monkeypatch)
    sent = await _drive(app, _scope(method="HEAD", path=BUNDLE_PATH, headers=_hdr(REPORTER_KEY)))
    assert _status_of(sent) == 200


@pytest.mark.parametrize(
    "path",
    ["/docs", "/openapi.json", "/api/trading/status", "/api/log-reports/2026-09-04"],
)
async def test_reporter_key_when_read_any_path_then_200(monkeypatch, path):
    """R-3 — 읽기는 **경로 무관** 통과(`/docs` 포함).

    명세의 명시적 결정이다: 리포터는 읽기 전면 허용이고, 스코프의 목적은 *쓰기* 를
    한 경로로 자르는 것이다. 읽기까지 경로 화이트리스트로 좁히면 번들 스키마가 바뀔
    때마다 인증 계층을 손대야 하고(변경 표면 확대), 읽기 자체는 매매를 못 바꾼다.
    """
    app = _app(monkeypatch)
    sent = await _drive(app, _scope(method="GET", path=path, headers=_hdr(REPORTER_KEY)))
    assert _status_of(sent) == 200


# ---------------------------------------------------------------------------
# R-4 ~ R-6 — 유일한 쓰기 경로
# ---------------------------------------------------------------------------
async def test_reporter_key_when_post_external_exact_then_200(monkeypatch):
    """R-4 — 정확 경로 POST 만 통과. 이 경로가 리포터의 **유일한 쓰기**다."""
    app = _app(monkeypatch)
    sent = await _drive(
        app, _scope(method="POST", path=EXTERNAL_PATH, headers=_hdr(REPORTER_KEY))
    )
    assert _status_of(sent) == 200


async def test_reporter_key_when_post_external_same_origin_then_200(monkeypatch):
    """R-5 — Origin 이 Host 와 같으면 통과(기존 `_origin_allowed` 재사용 확인).

    리포터 쓰기도 상태변경이므로 CSRF 검사를 **면제하지 않는다**. 다만 판정 함수는
    cycle243 것을 그대로 쓴다 — 두 벌이 되면 한쪽만 고쳐지는 비대칭이 생긴다.
    """
    app = _app(monkeypatch)
    sent = await _drive(
        app,
        _scope(
            method="POST",
            path=EXTERNAL_PATH,
            headers=_hdr(
                REPORTER_KEY,
                [(b"host", b"trading.example"), (b"origin", b"http://trading.example")],
            ),
        ),
    )
    assert _status_of(sent) == 200


async def test_reporter_key_when_post_external_cross_origin_then_401(monkeypatch):
    """R-6 — 교차 출처 쓰기는 **401 `cross_origin`**(403 아님).

    사유 귀인을 섞지 않는다: 스코프는 맞았고 출처가 틀린 것이므로 기존 사유를 쓴다.
    브라우저에 캐시된 Basic 자격 + nginx 의 키 주입으로 실행되는 simple request 를
    막는 축이라 리포터에도 그대로 적용된다.
    """
    app = _app(monkeypatch)
    sent = await _drive(
        app,
        _scope(
            method="POST",
            path=EXTERNAL_PATH,
            headers=_hdr(
                REPORTER_KEY,
                [(b"host", b"trading.example"), (b"origin", b"http://evil.example")],
            ),
        ),
    )
    assert _status_of(sent) == UNAUTHORIZED_STATUS


# ---------------------------------------------------------------------------
# R-7 ~ R-9 — 쓰기 차단 (이 스코프의 존재 이유)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [
        MANUAL_SELL_PATH,
        "/api/trading/stop",
        "/api/trading/start",
        "/api/log-reports/run",
        "/api/log-reports",
        "/api/strategy-funnel/snapshot",
    ],
)
async def test_reporter_key_when_post_other_path_then_403(monkeypatch, path):
    """R-7 — 다른 POST 는 전부 403.

    `/api/log-reports/run` 이 여기 있는 것이 핵심이다 — **같은 라우터** 안에 있어도
    스코프는 prefix 가 아니라 정확 경로다. prefix 로 열면 수동 트리거(OpenAI 호출 +
    INSERT)가 리포터 자격으로 실행된다.
    """
    app = _app(monkeypatch)
    sent = await _drive(app, _scope(method="POST", path=path, headers=_hdr(REPORTER_KEY)))
    assert _status_of(sent) == FORBIDDEN_STATUS, f"{path} 가 리포터 자격으로 통과했다"


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "OPTIONS"])
async def test_reporter_key_when_non_read_method_then_403(monkeypatch, method):
    """R-8 — 쓰기 경로가 맞아도 **메서드가 POST 가 아니면** 403.

    `PUT /api/strategies/{id}/params`(손절%·max_positions 임의 설정)가 이 가드가 막는
    구체적 표면이다. OPTIONS 는 읽기처럼 보이지만 화이트리스트에 없다 — 명세는
    READ 집합을 GET/HEAD 2종으로 **닫아** 두는 쪽을 택했다.
    """
    app = _app(monkeypatch)
    sent = await _drive(
        app, _scope(method=method, path=EXTERNAL_PATH, headers=_hdr(REPORTER_KEY))
    )
    assert _status_of(sent) == FORBIDDEN_STATUS


@pytest.mark.parametrize(
    "path",
    [
        "/api/log-reports/2026-09-04/external/",      # 후행 슬래시
        "/api/log-reports/2026-09-04/externalx",       # 접미 오염
        "/api/log-reports/2026-09-04/external/extra",  # 하위 경로
        "/api/log-reports/20260904/external",          # 날짜 형식 불일치
        "/api/log-reports/2026-9-4/external",          # 자릿수 불일치
        "/api/LOG-REPORTS/2026-09-04/EXTERNAL",        # 대문자
        "/API/log-reports/2026-09-04/external",        # 접두 대문자
        "//api/log-reports/2026-09-04/external",       # 이중 슬래시
        "/api/log-reports/../trading/manual-sell",     # 경로 traversal 형태
        "/api/log-reports/2026-09-04/external%2F..",   # 인코딩 잔재
        "/x/api/log-reports/2026-09-04/external",      # 접두 삽입
    ],
)
async def test_reporter_key_when_path_variant_then_403(monkeypatch, path):
    """R-9 — 경로 변형은 전부 403(앵커된 정확 일치).

    `$` 앵커가 빠지면 `…/external/../trading/manual-sell` 류가 통과하고, `^` 가 빠지면
    접두 삽입이 통과한다. 뮤테이션 "앵커 제거" 가 여기서 죽는다.
    """
    app = _app(monkeypatch)
    sent = await _drive(app, _scope(method="POST", path=path, headers=_hdr(REPORTER_KEY)))
    assert _status_of(sent) == FORBIDDEN_STATUS, f"경로 변형이 통과했다: {path}"


async def test_reporter_key_when_method_override_header_then_still_403(monkeypatch):
    """R-10 — `X-HTTP-Method-Override` 로 스코프를 우회할 수 없다.

    판정은 ASGI `scope["method"]` 만 본다. 헤더 기반 오버라이드를 해석하는 계층이
    뒤에 있어도 **인증은 원 메서드로 판정**하는 것이 계약이다(GET 으로 위장한 DELETE).
    """
    app = _app(monkeypatch)
    sent = await _drive(
        app,
        _scope(
            method="DELETE",
            path=EXTERNAL_PATH,
            headers=_hdr(REPORTER_KEY, [(b"x-http-method-override", b"GET")]),
        ),
    )
    assert _status_of(sent) == FORBIDDEN_STATUS


# ---------------------------------------------------------------------------
# R-11 ~ R-13 — fail-closed 경계
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("header_value", ["", " ", REPORTER_KEY])
async def test_empty_reporter_key_when_any_header_then_no_reporter_pass(
    monkeypatch, header_value
):
    """R-11 — 리포터 키가 빈 문자열이면 **어떤 헤더로도 리포터가 되지 않는다**.

    `compare_digest("", "")` 는 True 다 — 빈 리포터 키 선분기가 비교보다 앞에 없으면
    "리포터 키 미설정" 상태에서 빈 헤더를 보낸 쪽이 리포터로 승격된다(cycle243 A-6 과
    동형 함정). 기본값이 빈 문자열이므로 이건 **운영 기본 상태**의 안전성이다.
    """
    app = _app(monkeypatch, api_reporter_key="")
    sent = await _drive(
        app,
        _scope(method="GET", path=BUNDLE_PATH, headers=[(b"x-api-key", header_value.encode())]),
    )
    assert _status_of(sent) == UNAUTHORIZED_STATUS


async def test_unset_operator_key_when_reporter_key_matches_then_401_no_key(
    monkeypatch, caplog
):
    """R-12 — 운영 키가 비면 리포터 키가 맞아도 **401 `no_key_configured`**.

    "리포터 키만 설정된 상태로 아무것도 열리지 않는다" — fail-closed 의 우선순위가
    스코프보다 앞이다. 이 순서가 뒤집히면 `API_AUTH_KEY` 를 지우는 것만으로 리포터
    표면이 유일한 입구가 되는 조용한 구성 사고가 가능해진다.
    """
    app = _app(monkeypatch, api_auth_key="", api_reporter_key=REPORTER_KEY)

    with freeze_time("2026-10-01 03:00:00"), caplog.at_level(logging.DEBUG):
        sent = await _drive(
            app, _scope(method="GET", path=BUNDLE_PATH, headers=_hdr(REPORTER_KEY))
        )

    assert _status_of(sent) == UNAUTHORIZED_STATUS
    lines = _reject_lines(caplog)
    assert any("reason=no_key_configured" in line for line in lines), lines


async def test_same_key_for_both_roles_when_used_then_operator_wins(monkeypatch):
    """R-13 — 운영 키와 리포터 키가 같은 값이면 **운영자로 판정**(선행 분기).

    설정 사고(같은 값 복붙)로 운영자가 갑자기 403 을 받는 일이 없어야 한다. 판정
    순서가 "운영자 먼저" 인 것의 관측 가능한 귀결이다 — 뮤테이션 "리포터 분기를 앞으로"
    가 여기서 죽는다(운영자의 `POST manual-sell` 이 403 이 된다).
    """
    app = _app(monkeypatch, api_auth_key=OPERATOR_KEY, api_reporter_key=OPERATOR_KEY)
    sent = await _drive(
        app, _scope(method="POST", path=MANUAL_SELL_PATH, headers=_hdr(OPERATOR_KEY))
    )
    assert _status_of(sent) == 200


async def test_operator_key_when_post_any_path_then_unaffected(monkeypatch):
    """R-14 — 운영 키의 행위는 **byte 동일**(회귀 가드).

    스코프 도입이 운영자 경로를 좁히면 그건 기능 추가가 아니라 사고다.
    """
    app = _app(monkeypatch)
    for method, path in (
        ("POST", MANUAL_SELL_PATH),
        ("PUT", "/api/strategies/momentum/params"),
        ("DELETE", "/api/anything"),
        ("GET", "/api/trading/status"),
    ):
        sent = await _drive(app, _scope(method=method, path=path, headers=_hdr(OPERATOR_KEY)))
        assert _status_of(sent) == 200, f"운영자 {method} {path} 가 막혔다"


async def test_unknown_key_when_reporter_configured_then_401_bad_key(monkeypatch, caplog):
    """R-15 — 둘 다 불일치는 종전대로 401 `bad_key`(403 으로 새지 않는다).

    403 은 "키는 맞았고 권한이 없다" 는 뜻이라 공격자에게 **유효 키 보유**를 알려 준다.
    모르는 키에까지 403 을 주면 그 신호가 오염된다.
    """
    app = _app(monkeypatch)

    with freeze_time("2026-10-02 03:00:00"), caplog.at_level(logging.DEBUG):
        sent = await _drive(
            app, _scope(method="POST", path=MANUAL_SELL_PATH, headers=_hdr(BAD_KEY))
        )

    assert _status_of(sent) == UNAUTHORIZED_STATUS
    assert any("reason=bad_key" in line for line in _reject_lines(caplog)), _reject_lines(caplog)


async def test_health_when_reporter_configured_then_unauthenticated(monkeypatch):
    """R-16 — `/health` 는 스코프 도입과 무관하게 무인증 통과."""
    app = _app(monkeypatch)
    sent = await _drive(app, _scope(method="GET", path="/health", headers=[]))
    assert _status_of(sent) == 200


# ---------------------------------------------------------------------------
# R-17 ~ R-19 — 응답 형태 · 관측
# ---------------------------------------------------------------------------
async def test_reporter_scope_reject_when_responded_then_403_envelope(monkeypatch):
    """R-17 — 403 바디는 ApiResponse 봉투 + `message="forbidden"`.

    프론트가 `data.data` 를 뽑는 계약(사이클 84)을 인증 거부에서도 깨지 않는다.
    `WWW-Authenticate` 는 붙이지 않는다 — 붙이면 브라우저가 Basic 자격을 다시 묻는다.
    """
    app = _app(monkeypatch)
    sent = await _drive(
        app, _scope(method="POST", path=MANUAL_SELL_PATH, headers=_hdr(REPORTER_KEY))
    )

    assert _status_of(sent) == FORBIDDEN_STATUS
    import json

    body = json.loads(_body_of(sent).decode("utf-8"))
    assert body == {"success": False, "data": None, "message": "forbidden"}, body

    start = next(m for m in sent if m.get("type") == "http.response.start")
    names = {name.lower() for name, _ in start.get("headers") or ()}
    assert b"www-authenticate" not in names


async def test_unauthorized_body_when_reason_not_scope_then_unchanged(monkeypatch):
    """R-18 — 401 바디는 cycle243 그대로(`message="unauthorized"`).

    새 사유가 기존 봉투를 바꾸면 프론트·운영 스크립트가 조용히 갈라진다.
    """
    app = _app(monkeypatch)
    sent = await _drive(app, _scope(method="GET", path=BUNDLE_PATH, headers=_hdr(BAD_KEY)))

    assert _status_of(sent) == UNAUTHORIZED_STATUS
    import json

    assert json.loads(_body_of(sent).decode("utf-8")) == {
        "success": False,
        "data": None,
        "message": "unauthorized",
    }


async def test_reporter_scope_when_rejected_then_logged_without_key_value(
    monkeypatch, caplog
):
    """R-19 — `[api_auth_reject] reason=reporter_scope` 가 같은 cap 규약으로 기록되고,
    **키 값은 어디에도 실리지 않는다**(cycle243 §2.3.6 불변).

    사유가 로그에 없으면 "루틴이 왜 막혔는지" 를 운영자가 알 방법이 없고, 키가 로그에
    실리면 `system_logs` 를 통해 비밀이 DB 로 새어 나간다(`_DbLogHandler` 가 INFO 이상을
    그대로 나른다).
    """
    app = _app(monkeypatch)

    with freeze_time("2026-10-03 03:00:00"), caplog.at_level(logging.DEBUG):
        sent = await _drive(
            app, _scope(method="POST", path=MANUAL_SELL_PATH, headers=_hdr(REPORTER_KEY))
        )

    assert _status_of(sent) == FORBIDDEN_STATUS
    lines = _reject_lines(caplog)
    assert lines, f"{REJECT_MARKER} 거부 로그가 없다"
    assert any("reason=reporter_scope" in line for line in lines), lines
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert REPORTER_KEY not in joined, "리포터 키 값이 로그에 실렸다"
    assert OPERATOR_KEY not in joined, "운영 키 값이 로그에 실렸다"


async def test_reporter_scope_reason_when_capped_then_bounded(monkeypatch, caplog):
    """R-20 — 새 사유도 **사유 단독** cap 키를 쓴다(경로를 키에 넣지 않는다).

    경로를 cap 키에 넣으면 인터넷 노출면에서 `/api/aaa`,`/api/aab`… 로 메모리가 무한
    증식한다(cycle243 §2.3.9). 서로 다른 60 경로 · 같은 사유 → `EMIT_AT` 지점만 발화.
    """
    app = _app(monkeypatch)

    with freeze_time("2026-10-04 03:00:00"), caplog.at_level(logging.DEBUG):
        for i in range(60):
            sent = await _drive(
                app, _scope(method="POST", path=f"/api/scope-{i}", headers=_hdr(REPORTER_KEY))
            )
            assert _status_of(sent) == FORBIDDEN_STATUS

    lines = [ln for ln in _reject_lines(caplog) if "reason=reporter_scope" in ln]
    assert 0 < len(lines) <= 5, f"cap 키가 사유 단독이 아니다(행수 {len(lines)}): {lines[:3]}"


async def test_reject_reason_set_when_scope_added_then_five(monkeypatch, caplog):
    """R-21 — 사유 집합은 **5종 고정**이고 `reporter_scope` 가 그중 하나다.

    사유 집합이 열리면 cap 키가 무제한으로 늘어난다(`_log_reject` 의 `REASONS` 폴백이
    그 구조적 방어다).
    """
    mod = _mw()
    reasons = getattr(mod, "REASONS", None)
    assert reasons is not None, "Red — REASONS 미구현"
    assert set(reasons) == {
        "no_key_configured",
        "missing_header",
        "bad_key",
        "cross_origin",
        "reporter_scope",
    }, reasons
    assert len(tuple(reasons)) == 5, reasons
    assert getattr(mod, "REASON_REPORTER_SCOPE", None) == "reporter_scope"


async def test_reporter_read_methods_when_declared_then_get_head_only(monkeypatch):
    """R-22 — `REPORTER_READ_METHODS` 는 GET/HEAD 2종 정확 일치.

    POST 를 여기에 넣는 뮤테이션이 스코프 전체를 무력화한다(모든 POST 통과).
    """
    mod = _mw()
    methods = getattr(mod, "REPORTER_READ_METHODS", None)
    assert methods is not None, "Red — REPORTER_READ_METHODS 미구현"
    assert set(methods) == {"GET", "HEAD"}, methods


# ---------------------------------------------------------------------------
# R-23 — 기동 로그
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("reporter_key", "expected"), [(REPORTER_KEY, "true"), ("", "false")]
)
def test_startup_log_when_reporter_configured_then_flag_only(
    monkeypatch, caplog, reporter_key, expected
):
    """R-23 — `[api_auth_config]` 에 `reporter_enabled=<bool>` — **값·길이는 출력 금지**.

    운영자가 "루틴이 401 인데 키가 들어갔나" 를 자가 진단하는 유일한 채널이다. 값이나
    길이를 찍으면 그 자체가 유출 표면이 된다(cycle246: 렌더된 nginx 주석에 키가 박혀
    설정 덤프로 샜다).
    """
    mod = _mw()
    _set_settings(
        monkeypatch,
        api_auth_key=OPERATOR_KEY,
        api_reporter_key=reporter_key,
        api_allowed_origins="",
    )

    with caplog.at_level(logging.DEBUG):
        mod.log_startup_state()

    config_lines = [r.getMessage() for r in caplog.records if "[api_auth_config]" in r.getMessage()]
    assert config_lines, "[api_auth_config] 기동 로그가 없다"
    line = config_lines[-1]
    assert re.search(rf"reporter_enabled={expected}\b", line), line
    if reporter_key:
        assert reporter_key not in line, "기동 로그에 리포터 키 값이 실렸다"
        assert f"reporter_key_len={len(reporter_key)}" not in line, (
            "길이 출력도 금지 — 활성 여부만 노출한다"
        )


# ---------------------------------------------------------------------------
# R-24 ~ R-25 — 운영키==리포터키 충돌 (적대 검증 auth-bypass, MEDIUM 시정)
# ---------------------------------------------------------------------------
def test_startup_log_when_keys_collide_then_critical_marker_without_value(
    monkeypatch, caplog
):
    """R-24 — 운영 키와 리포터 키가 같은 값이면 기동 시 CRITICAL 마커.

    R-13(`test_same_key_for_both_roles_when_used_then_operator_wins`)이 그 상태에서도
    운영자를 지켜주지만, 그 순서 뒤집기는 정확히 **리포터 스코프가 존재하지 않는다**는
    뜻이다(모든 리포터 요청이 운영자로 판정돼 전권을 갖는다). 그런데 기존
    `[api_auth_config]` 는 `reporter_enabled=true` 한 줄뿐이라 이 충돌이 응답 코드로도
    로그로도 드러나지 않았다(모든 요청이 200) — cycle249 적대 검증 auth-bypass 렌즈
    확증. 값·길이는 여전히 비공개(존재 여부만 CRITICAL 로 알린다).
    """
    mod = _mw()
    _set_settings(
        monkeypatch,
        api_auth_key=OPERATOR_KEY,
        api_reporter_key=OPERATOR_KEY,
        api_allowed_origins="",
    )

    with caplog.at_level(logging.DEBUG):
        mod.log_startup_state()

    collision_records = [
        r for r in caplog.records if "[api_auth_reporter_key_collision]" in r.getMessage()
    ]
    assert collision_records, "충돌 시 `[api_auth_reporter_key_collision]` CRITICAL 이 없다"
    assert all(r.levelno == logging.CRITICAL for r in collision_records), collision_records

    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert OPERATOR_KEY not in joined, "충돌 로그에 키 값이 실렸다"

    config_lines = [r.getMessage() for r in caplog.records if "[api_auth_config]" in r.getMessage()]
    assert config_lines, "[api_auth_config] 기동 로그가 없다"
    assert re.search(r"reporter_distinct=false\b", config_lines[-1]), config_lines[-1]


def test_startup_log_when_keys_distinct_then_no_collision_marker(monkeypatch, caplog):
    """R-25 — 서로 다른 키면 충돌 마커가 발화하지 않고 `reporter_distinct=true`.

    회귀 가드 — R-24 가 도입한 비교가 정상 구성(서로 다른 두 키)까지 시끄럽게
    만들면 그 자체가 새로운 소음이다.
    """
    mod = _mw()
    _set_settings(
        monkeypatch,
        api_auth_key=OPERATOR_KEY,
        api_reporter_key=REPORTER_KEY,
        api_allowed_origins="",
    )

    with caplog.at_level(logging.DEBUG):
        mod.log_startup_state()

    assert not any(
        "[api_auth_reporter_key_collision]" in r.getMessage() for r in caplog.records
    ), "서로 다른 키인데 충돌 마커가 발화했다"

    config_lines = [r.getMessage() for r in caplog.records if "[api_auth_config]" in r.getMessage()]
    assert config_lines, "[api_auth_config] 기동 로그가 없다"
    assert re.search(r"reporter_distinct=true\b", config_lines[-1]), config_lines[-1]


def test_startup_log_when_reporter_disabled_then_distinct_true_no_collision(
    monkeypatch, caplog
):
    """R-25b — 리포터 키가 빈 문자열(비활성)이면 충돌 여지가 없다 — `distinct=true`.

    `key and reporter_key` 가드가 없으면 빈 리포터 키가 `compare_digest` 에 그대로
    들어가는데, 운영 키가 비어 있지 않은 한 그 비교는 항상 False 라 실질 위험은
    없지만, **가드 자체가 사라지는 뮤테이션**을 이 케이스가 잡는다(운영 키가 우연히
    빈 문자열인 상태는 `no_key_configured` 로 이미 별도 처리된다).
    """
    mod = _mw()
    _set_settings(
        monkeypatch,
        api_auth_key=OPERATOR_KEY,
        api_reporter_key="",
        api_allowed_origins="",
    )

    with caplog.at_level(logging.DEBUG):
        mod.log_startup_state()

    assert not any(
        "[api_auth_reporter_key_collision]" in r.getMessage() for r in caplog.records
    ), "리포터 비활성인데 충돌 마커가 발화했다"

    config_lines = [r.getMessage() for r in caplog.records if "[api_auth_config]" in r.getMessage()]
    assert config_lines
    assert re.search(r"reporter_distinct=true\b", config_lines[-1]), config_lines[-1]
    assert re.search(r"reporter_enabled=false\b", config_lines[-1]), config_lines[-1]


# ---------------------------------------------------------------------------
# R-26 ~ R-28 — 리포터 키 약한 값 경고 (M14 뮤테이션 렌즈 escape 봉인)
# ---------------------------------------------------------------------------
#: `MIN_KEY_LEN=24` 미만 — 운영 키 대칭 테스트(`test_cycle243_api_auth.py
#: ::test_startup_log_when_key_weak_then_warning_without_value`)의 리포터 미러.
WEAK_REPORTER_KEY = "short-rep-key"  # 13자


def test_startup_log_when_reporter_key_weak_then_warning_without_value(
    monkeypatch, caplog
):
    """R-26 (M14 봉인) — 리포터 키가 24자 미만이면 `[api_auth_reporter_key_weak]` WARNING.

    운영 키 쪽(`[api_auth_key_weak]`)은 cycle243 이 이미 지키지만, 리포터 키는 노출
    표면이 더 넓다(20:20 KST 클라우드 루틴이 매일 왕복시킨다 — `log_startup_state`
    본문 주석 참조). 이 관측이 없어도 인증 판정 자체는 무영향(관측 전용 결손)이라
    행위 테스트로는 안 잡히고, 여기서만 잡힌다.
    """
    mod = _mw()
    _set_settings(
        monkeypatch,
        api_auth_key=OPERATOR_KEY,
        api_reporter_key=WEAK_REPORTER_KEY,
        api_allowed_origins="",
    )

    with caplog.at_level(logging.DEBUG):
        mod.log_startup_state()

    weak_records = [
        r
        for r in caplog.records
        if "[api_auth_reporter_key_weak]" in r.getMessage()
    ]
    assert weak_records, "리포터 키가 짧은데 [api_auth_reporter_key_weak] 가 없다"
    assert any(r.levelno == logging.WARNING for r in weak_records), weak_records
    assert any(
        f"key_len={len(WEAK_REPORTER_KEY)}" in r.getMessage() for r in weak_records
    ), weak_records

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert WEAK_REPORTER_KEY not in blob, "약한 리포터 키 경고에 키 값이 실렸다"


def test_startup_log_when_reporter_key_long_then_no_weak_marker(monkeypatch, caplog):
    """R-27 — 리포터 키가 `MIN_KEY_LEN` 이상이면 약한 키 마커가 발화하지 않는다.

    회귀 가드 — R-26 이 도입한 검사가 정상 길이 구성까지 시끄럽게 만들면 안 된다.
    """
    mod = _mw()
    _set_settings(
        monkeypatch,
        api_auth_key=OPERATOR_KEY,
        api_reporter_key=REPORTER_KEY,  # 44자, MIN_KEY_LEN(24) 이상
        api_allowed_origins="",
    )

    with caplog.at_level(logging.DEBUG):
        mod.log_startup_state()

    assert not any(
        "[api_auth_reporter_key_weak]" in r.getMessage() for r in caplog.records
    ), "리포터 키가 충분히 긴데 약한 키 마커가 발화했다"


def test_startup_log_when_reporter_key_empty_then_no_weak_marker(monkeypatch, caplog):
    """R-28 — 리포터 키가 빈 문자열(비활성)이면 약한 키 마커가 발화하지 않는다.

    비활성은 약한 키가 아니다 — `reporter_key and len(reporter_key) < MIN_KEY_LEN`
    가드의 `and` 가 사라지면 빈 문자열(`len==0 < 24`)도 WARNING 을 낸다.
    """
    mod = _mw()
    _set_settings(
        monkeypatch,
        api_auth_key=OPERATOR_KEY,
        api_reporter_key="",
        api_allowed_origins="",
    )

    with caplog.at_level(logging.DEBUG):
        mod.log_startup_state()

    assert not any(
        "[api_auth_reporter_key_weak]" in r.getMessage() for r in caplog.records
    ), "리포터 키 비활성인데 약한 키 마커가 발화했다"
