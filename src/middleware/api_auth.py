"""cycle243 — API 인증 미들웨어 (`X-API-Key`, fail-closed).

명세: `_workspace/red/cycle243_api_auth_spec.md` §2.2~2.5 · 구현 계약 §2.3

## 고치는 결함

`curl http://<EC2>/api/trading/status` 가 **200** 을 돌려줬다 — 인터넷의 누구나
`POST /api/trading/manual-sell`(임의 종목·수량 시장가 매도) · `POST /api/trading/stop`
(보유 포지션의 손절·트레일링 정지) · `PUT /api/strategies/{id}/params`(손절%·
`max_positions` 임의 설정) 를 호출할 수 있었고, 인증 코드는 코드베이스 전체에 0건이었다.

## 설계 근거 (바꾸기 전에 읽을 것)

1. **순수 ASGI** — starlette 의 base-HTTP 미들웨어 계열(요청마다 anyio task group +
   memory stream 을 세우는 그 클래스) 금지(명세 §0-6). 이 리포는 anyio portal hang 으로
   두 번 데였고(`test_cycle127_progress_routes.py` · `test_pnl_summary.py` 가 TestClient
   회피를 명시), `stock_master` refresh 4종이 `BackgroundTasks` fire-and-forget + 5초
   폴링이다. 그 계열을 하나 더 쌓으면 매 요청 오버헤드가 추가된다. 순수 ASGI 는 거부
   요청에서 하위 앱을 아예 호출하지 않아 오버헤드도 0이다.
   (⚠️ 이 파일에 그 클래스 이름을 문자열로도 남기지 않는 것이 AST 가드 D-12-c 의 계약이다.)
2. **fail-closed** — `API_AUTH_KEY` 미설정/빈 문자열이면 **열리는 게 아니라 잠긴다**.
   매매 엔진은 in-process 라 API 가 잠겨도 매매 영향은 0(대시보드만 멈춘다)이고, 반대편
   fail-open 은 "키가 없으면 인증이 조용히 사라진다" = 이 사이클이 고치려는 결함의 정확한
   재현이다. 진단 채널은 기동 시 `[api_auth_key_missing]` CRITICAL 이다.
3. **deny-by-default** — `/health` 를 뺀 모든 경로를 보호한다. `/api` 접두사 스코프는
   `/docs`·`/redoc`·`/openapi.json`(엔드포인트 스키마 전량)을 덮지 못한다.
4. **`authorize` 는 모듈 레벨 함수**이고 `__call__` 이 **한정하지 않은 전역 이름**으로
   부른다. 기존 스위트 보호 픽스처(`tests/conftest.py::_neutralize_api_auth`)가 갈아끼우는
   유일한 seam 이다. 프로덕션 코드에 `_TEST_BYPASS` 류 플래그를 두지 않는 대가로 이
   구조가 계약이 된다(`tests/unit/ast/test_cycle243_phase2_assets.py::D-12`).
5. **키는 요청 시점에 읽는다** — `settings` 는 import 시점 싱글톤이라(`config.py`)
   `__init__` 캡처형은 테스트 seam 도 운영 진단(키 회전)도 동시에 막는다.
6. **키 값·수신 헤더 값은 로그·응답·예외 메시지 어디에도 넣지 않는다.** 길이만 찍는다.

## 알려진 한계

* **TLS 부재** — Basic Auth 자격과 `X-API-Key` 가 평문 HTTP 로 오간다(명세 L1, 후속 F1).
  이 미들웨어는 "익명 인터넷 전체 → 자격 보유자 + 경로 관찰자" 로 공격면을 줄일 뿐이다.
* **단일 공유 키** — 주체 식별·부분 권한·감사 추적이 없다(L2, 후속 F7).
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from starlette.responses import JSONResponse

from src.config import settings

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

#: 인증 헤더 이름(ASGI raw 헤더는 소문자로 비교한다 — HTTP 헤더 이름은 대소문자 무관).
HEADER_NAME = b"x-api-key"

#: 유일한 무인증 경로. 관례적 liveness 프로브이고 현재 어떤 프로브도 붙어 있지 않다.
EXEMPT_PATHS = frozenset({"/health"})

#: Origin(CSRF) 검사 대상. GET 에 적용하면 대시보드 폴링(18곳·최단 3초)이 통째로 죽는다.
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

REASON_NO_KEY = "no_key_configured"
REASON_MISSING_HEADER = "missing_header"
REASON_BAD_KEY = "bad_key"
REASON_CROSS_ORIGIN = "cross_origin"
#: cycle249 — 리포터 키가 허용 범위(GET/HEAD + 리포트 POST 1경로) 밖으로 나간 경우.
#: 유일하게 **403** 으로 응답한다(다른 사유는 전부 401 — "키는 맞았고 권한이 없다"는
#: 신호를 모르는 키에까지 주면 공격자에게 유효 키 보유를 알려준다).
REASON_REPORTER_SCOPE = "reporter_scope"
#: **5종 고정**(cycle243 4종 + cycle249 `reporter_scope`). cap 키이자 운영자의 유일한
#: 진단 채널이다(응답은 401/403 뿐 — 미설정 상태를 503 으로 구분하면 공격자에게
#: "이 박스는 키가 없다"를 알려준다). 집합을 여기서 닫아 두지 않으면 인터넷 노출면에서
#: `_log_reject` 의 cap 키가 무제한으로 늘어난다.
REASONS = (
    REASON_NO_KEY,
    REASON_MISSING_HEADER,
    REASON_BAD_KEY,
    REASON_CROSS_ORIGIN,
    REASON_REPORTER_SCOPE,
)

#: cycle249 — 리포터 키가 부작용 없이 통과하는 메서드(경로 무관). POST 를 넣는 순간
#: 스코프 전체가 무력화된다.
REPORTER_READ_METHODS = frozenset({"GET", "HEAD"})
#: cycle249 — 리포터의 **유일한 쓰기** 경로. 앵커(`^`/`\Z`) 필수 — 빠지면 접두 삽입이나
#: `…/external/../trading/manual-sell` 같은 접미 확장이 통과한다. **`$` 가 아니라 `\Z`**
#: 를 쓴다 — `$` 는 "문자열 끝" 뿐 아니라 "**끝의 개행 직전**"도 허용해(re 모듈 기본
#: 동작) `…/external\n` 처럼 인코딩된 위조 경로가 매치될 여지를 남긴다(적대 검증
#: 위생 시정, `authorize` 도 이 정규식을 `.fullmatch()` 로 쓴다). **`\d` 가 아니라
#: `[0-9]`** — `\d` 는 Python 기본으로 유니코드 십진 숫자(전각 숫자 U+FF10~FF19 등)
#: 까지 매치하는데, 그런 문자는 실제 라우트 매칭에 쓰이지도 않으면서 이 판정만
#: 통과시킬 수 있다. `|` 로 경로를 늘리는 변경은 "유일한 쓰기 경로" 라는 스코프의
#: 근거 자체를 무너뜨리므로 금지.
REPORTER_WRITE_PATH_RE = re.compile(
    r"^/api/log-reports/[0-9]{4}-[0-9]{2}-[0-9]{2}/external\Z"
)

#: `secrets.token_urlsafe(32)` = 43~44자. 이보다 짧으면 기동 시 WARNING.
MIN_KEY_LEN = 24

#: 로그에 실을 경로 최대 길이(로그 인젝션·폭 제한).
PATH_LOG_MAXLEN = 80

#: 거부 로그 발화 지점. "1행만" 보다 **공격 볼륨**을 보여주면서도 유계다(사유당 ≤5행/일).
EMIT_AT = frozenset({1, 10, 100, 1000, 10000})

_UNAUTHORIZED_BODY = {"success": False, "data": None, "message": "unauthorized"}
#: cycle249 — `reporter_scope` 사유 전용 403 바디. 401 봉투와 `message` 만 다르다
#: (프론트 `data.data` 계약은 그대로 유지).
_FORBIDDEN_BODY = {"success": False, "data": None, "message": "forbidden"}

# 거부 카운터 — 날짜 문자열 **자기 리셋**. `DailyEmitCap` 은 스스로 롤오버하지 않고 외부
# `reset_daily()` 호출자(스케줄러 일일 정산)에 의존하는데 미들웨어엔 그 훅이 없다.
# 키는 **사유 단독**이다. raw path 를 키에 넣으면 인터넷 노출면에서 `/api/aaa`,`/api/aab`…
# 로 무제한 메모리 증가 벡터가 된다.
_reject_state: dict[str, object] = {"day": "", "counts": {}}
# 판정 예외(버그 경로) 카운터 — 키 1개로 구조적으로 유계.
_internal_state: dict[str, object] = {"day": "", "count": 0}


# ---------------------------------------------------------------------------
# 순수 함수 헬퍼
# ---------------------------------------------------------------------------
def parse_allowed_origins(raw: str | None) -> list[str]:
    """`API_ALLOWED_ORIGINS` CSV → 정규화 목록. 기본(빈 값) = same-origin 전용.

    `src/main.py` 의 CORS `allow_origins` 와 이 모듈의 Origin 검사가 **같은 정의**를
    공유한다(두 곳이 갈라지면 "CORS 는 막는데 CSRF 는 통과" 같은 비대칭이 생긴다).

    ⚠️ **`*` 는 구조적으로 거부한다**(조용히 제거 + 기동 시 WARNING). 이 한 값이
    설정에 들어오면 `main.py` 의 CORS 가 `allow_all_origins=True` 가 되어 starlette 의
    `not allow_all_origins or allow_credentials` 경로로 **모든 오리진에 credentialed
    preflight 를 허가**한다 = 결정 ⑪ 이 제거한 바로 그 조합의 부활이고, 동시에 이
    모듈의 Origin 검사(⑫)까지 무력화된다. 환경변수 한 줄로 두 통제가 동시에 열리는
    경로를 남기지 않는다. 필요한 오리진은 **명시 열거**한다.
    """
    if not raw:
        return []
    items = [item.strip().rstrip("/") for item in str(raw).split(",") if item.strip()]
    return [item for item in items if item != "*"]


def has_wildcard_origin(raw: str | None) -> bool:
    """설정 원문에 `*` 항목이 있었는가(기동 경고용 — 판정에는 쓰지 않는다)."""
    if not raw:
        return False
    return any(item.strip().rstrip("/") == "*" for item in str(raw).split(","))


def _allowed_origin_set() -> set[str]:
    return {origin.lower() for origin in parse_allowed_origins(settings.api_allowed_origins)}


def _header(scope: dict, name: bytes) -> bytes | None:
    """raw ASGI 헤더 조회. 없으면 None(빈 값과 구분한다)."""
    for raw_name, raw_value in scope.get("headers") or ():
        if raw_name.lower() == name:
            return raw_value
    return None


def _header_text(scope: dict, name: bytes) -> str:
    raw = _header(scope, name)
    if raw is None:
        return ""
    try:
        return raw.decode("latin-1")
    except Exception:
        return ""


def _split_origin(origin: str) -> tuple[str, str]:
    """`http://host:port/…` → (scheme, host:port)."""
    scheme, sep, rest = origin.partition("://")
    if not sep:
        return "", origin.split("/", 1)[0]
    return scheme, rest.split("/", 1)[0]


def _strip_default_port(scheme: str, netloc: str) -> str:
    if scheme == "http" and netloc.endswith(":80"):
        return netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        return netloc[:-4]
    return netloc


def _origin_allowed(scope: dict) -> bool:
    """상태변경 요청의 출처 판정.

    CORS 는 **simple request 를 막지 못한다** — 응답 읽기만 차단할 뿐 요청은 이미 실행된다.
    `POST /api/trading/stop` 은 본문이 없어 `Content-Type: text/plain` simple request 로
    성립하므로, 브라우저에 캐시된 Basic 자격 + nginx 의 무차별 `X-API-Key` 주입으로
    **실행된다**. 표준 방어가 Origin 검사다.

    규칙: 부재 → 허용(curl·ssh 비상 매도 경로를 절대 깨지 않는다) / Host 일치 → 허용
    (자기 설정형이라 프로덕션은 설정 0으로 동작) / 허용 목록 등재 → 허용 / 그 외 → 거부.
    """
    origin_raw = _header_text(scope, b"origin").strip()
    if not origin_raw:
        return True  # 브라우저가 아닌 클라이언트(curl·스크립트) — 비상 경로 보존
    origin = origin_raw.rstrip("/").lower()
    if origin in _allowed_origin_set():
        return True
    scheme, netloc = _split_origin(origin)
    if not netloc or netloc == "null":
        return False
    host = _header_text(scope, b"host").strip().lower()
    if not host:
        return False
    return _strip_default_port(scheme, netloc) == _strip_default_port(scheme, host)


def authorize(scope: dict) -> str:
    """요청 1건의 인증 판정. `""` = 통과, 그 외 = 거부 사유(`REASONS` 5종).

    **모듈 레벨 함수인 것이 계약**이다(파일 docstring 4번). 메서드로 감추면 기존 스위트
    보호 픽스처가 갈아끼울 대상이 사라지고 수백 케이스가 401 로 전멸한다.

    판정 순서에 이유가 있다(cycle249 이 리포터 분기를 **운영자 판정 뒤**에 삽입했다 —
    두 키가 같은 값으로 설정되는 사고에서 운영자가 갑자기 403 을 받으면 안 된다):

    1. `/health` 예외 — 무인증 통과.
    2. **빈 운영 키 선분기가 헤더 비교보다 먼저**다. `compare_digest("", "")` 는 True 라,
       순서를 바꾸면 키 미설정 상태에서 빈 헤더를 보낸 쪽이 통과하는 구멍이 생긴다.
       리포터 키만 설정된 상태에서도 이 분기가 먼저 걸려 `no_key_configured` 로
       fail-closed 한다 — 리포터 표면이 유일한 입구가 되는 조용한 구성 사고 차단.
    3. 헤더 부재 → `missing_header`.
    4. **상수시간 비교**(`secrets.compare_digest`) — `==` 는 타이밍 사이드채널이다.
       운영 키가 일치하면 상태변경 Origin 검사 후 통과(기존 cycle243 경로, byte 동일).
    5. 운영 키가 불일치했을 때만 **리포터 키**를 본다. 리포터 키가 **비어 있지 않고**
       상수시간 일치하면: GET/HEAD 는 경로 무관 통과, `POST` + 정확한 리포트 경로는
       Origin 검사 후 통과, 그 외(다른 상태변경 메서드·다른 경로)는 `reporter_scope`
       (유일하게 403). 빈 리포터 키는 `and` 로 비교 자체를 건너뛴다(§2번과 동형 함정).
    6. 둘 다 불일치 → `bad_key`.
    """
    path = scope.get("path") or ""
    if path in EXEMPT_PATHS:
        return ""

    key = settings.api_auth_key  # 요청 시점 참조 (캡처 금지)
    if not key:
        return REASON_NO_KEY

    provided = _header(scope, HEADER_NAME)
    if provided is None:
        return REASON_MISSING_HEADER

    method = str(scope.get("method") or "").upper()

    if secrets.compare_digest(provided, key.encode("utf-8")):
        if method in STATE_CHANGING_METHODS and not _origin_allowed(scope):
            return REASON_CROSS_ORIGIN
        return ""

    # cycle249 — 리포터 스코프. 운영 키 불일치 뒤에만 평가한다(§4 참조).
    reporter_key = settings.api_reporter_key  # 요청 시점 참조 (캡처 금지)
    if reporter_key and secrets.compare_digest(provided, reporter_key.encode("utf-8")):
        if method in REPORTER_READ_METHODS:
            return ""
        if method == "POST" and REPORTER_WRITE_PATH_RE.fullmatch(path):
            if not _origin_allowed(scope):
                return REASON_CROSS_ORIGIN
            return ""
        return REASON_REPORTER_SCOPE

    return REASON_BAD_KEY


# ---------------------------------------------------------------------------
# 관측 (거부 로그 · 기동 로그) — 실패해도 인증 경로를 절대 건드리지 않는다
# ---------------------------------------------------------------------------
def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _sanitize(value: object, maxlen: int) -> str:
    """로그 인젝션 차단: 제어문자 제거 후 `maxlen` 절단.

    인터넷 노출면이라 경로는 공격자 입력이다. 개행이 살아 있으면 위조 로그 행을
    `system_logs` 에 심을 수 있다(`_DbLogHandler` 가 INFO 이상을 그대로 나른다).
    """
    text = "" if value is None else str(value)
    cleaned = "".join(ch for ch in text if ch.isprintable())
    return cleaned[:maxlen]


def _client_ip(scope: dict) -> tuple[str, str]:
    """(주소, 출처) — 출처는 `xri` · `xff` · `peer` · `none`.

    **`scope["client"]` 단독은 프로덕션에서 상수다.** Phase 2 는 backend 를
    `127.0.0.1:8000` 에 묶으므로 외부 요청이 전부 nginx(frontend 컨테이너)를 거치고,
    uvicorn 이 `--proxy-headers` 없이 뜨므로 백엔드가 보는 peer 는 항상 compose
    네트워크의 nginx 주소다. 그 값을 `ip=` 로 찍으면 **잘못된 귀인**이 되는데, 잘못된
    귀인은 없는 귀인보다 나쁘다(공격 IP 처럼 읽히는 상수).

    그래서 nginx 가 이미 넣어 주는 `X-Real-IP`(= `$remote_addr`) → `X-Forwarded-For`
    **마지막** 항목(= `$proxy_add_x_forwarded_for` 가 append 한 실 peer. 앞쪽 항목은
    클라이언트가 위조할 수 있다) → peer 순으로 폴백한다. `proxy_set_header` 는 동명
    헤더를 치환하므로 우리 nginx 를 거친 요청에서는 위조가 불가능하고, 거치지 않는
    경로(EC2 루프백 직결)는 로컬 접근뿐이다. **출처 태그를 함께 남겨** 어느 축을 믿고
    읽어야 하는지 로그만 보고 판별할 수 있게 한다.
    """
    real_ip = _header_text(scope, b"x-real-ip").strip()
    if real_ip:
        return _sanitize(real_ip, 45), "xri"  # IPv6 최대 45자

    forwarded = _header_text(scope, b"x-forwarded-for").strip()
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return _sanitize(hops[-1], 45), "xff"

    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        return _sanitize(client[0], 45), "peer"
    return "-", "none"


def _trace_auth_observer_failure(what: str) -> None:
    """관측기 자기 실패의 흔적. 무흔적 `pass` 는 도입 이전 무음과 구별할 수 없다."""
    try:
        logger.debug("[api_auth_observer_failed] %s", what, exc_info=True)
    except Exception:
        pass


def _log_reject(scope: dict, reason: str) -> None:
    """거부 관측. **인증 판정과 응답은 이 함수의 성패와 무관하다**(호출부 계약).

    cap 은 `count ∈ EMIT_AT` 지점만 발화한다. 카운터 자체는 매 거부마다 증가하므로
    한 번 로깅에 실패해도 다음 임계에서 정상 발화한다(영구 침묵 금지).
    """
    try:
        # 사유 집합을 **구조적으로** 5종에 고정 — 미래의 어떤 경로가 새 문자열을 만들어도
        # cap 키가 무제한으로 늘지 않는다.
        bucket = reason if reason in REASONS else REASON_BAD_KEY

        today = _today_kst()
        if _reject_state["day"] != today:
            _reject_state["day"] = today
            _reject_state["counts"] = {}
        counts: dict[str, int] = _reject_state["counts"]  # type: ignore[assignment]
        count = counts.get(bucket, 0) + 1
        counts[bucket] = count
        if count not in EMIT_AT:
            return

        ip, ip_src = _client_ip(scope)
        logger.warning(
            "[api_auth_reject] reason=%s method=%s path=%s ip=%s ip_src=%s count=%d",
            bucket,
            _sanitize(scope.get("method"), 16),
            _sanitize(scope.get("path"), PATH_LOG_MAXLEN),
            ip,
            ip_src,
            count,
        )
    except Exception:
        _trace_auth_observer_failure("reject_log")


def _log_internal_error(exc: BaseException | None) -> None:
    """판정 자체가 예외를 던진 경우(버그 경로)의 관측. 예외 **타입 이름만** 남긴다.

    메시지·트레이스에 값이 실려 나갈 여지를 만들지 않는다(§2.3.6).
    """
    try:
        today = _today_kst()
        if _internal_state["day"] != today:
            _internal_state["day"] = today
            _internal_state["count"] = 0
        count = int(_internal_state["count"]) + 1  # type: ignore[arg-type]
        _internal_state["count"] = count
        if count not in EMIT_AT:
            return
        logger.error(
            "[api_auth_internal_error] 판정 예외 — fail-closed 401 exc=%s count=%d",
            type(exc).__name__ if exc is not None else "?",
            count,
        )
    except Exception:
        _trace_auth_observer_failure("internal_error_log")


def log_startup_state() -> None:
    """기동 1회 상태 로그. fail-closed 의 **유일한 진단 채널**이다.

    키 없는 개발자가 전면 401 을 자가 진단하는 경로이기도 하다. 값은 절대 출력하지 않고
    길이만 찍는다.
    """
    key = settings.api_auth_key or ""
    if not key:
        logger.critical(
            "[api_auth_key_missing] API_AUTH_KEY 미설정 — /health 를 제외한 전 경로 401"
            "(fail-closed). .env 에 API_AUTH_KEY 를 설정하고 재시작하라 "
            "(생성: python3 -c \"import secrets;print(secrets.token_urlsafe(32))\")"
        )
    elif len(key) < MIN_KEY_LEN:
        logger.warning(
            "[api_auth_key_weak] key_len=%d — 32바이트 이상(token_urlsafe(32)) 권장",
            len(key),
        )
    if has_wildcard_origin(settings.api_allowed_origins):
        # 조용히 제거하고 끝내면 "설정했는데 왜 안 되지" 가 되고, 받아들이면 결정 ⑪ 이
        # 제거한 `["*"] + allow_credentials` 조합이 부활한다. 제거하되 시끄럽게 알린다.
        logger.warning(
            "[api_auth_wildcard_origin] API_ALLOWED_ORIGINS 의 `*` 항목을 **무시했다** — "
            "와일드카드는 CORS credentialed preflight 를 전 오리진에 열고 상태변경 "
            "Origin 검사(CSRF)까지 무력화한다. 허용할 오리진을 명시 열거하라"
        )
    reporter_key = settings.api_reporter_key or ""
    # cycle249 위생 시정 — 운영 키(위 elif)와 대칭인 약한 키 경고. 리포터 키는 운영
    # 키보다 노출 표면이 넓다(20:20 KST 클라우드 루틴이 매일 왕복시킨다) — 짧은 값은
    # 그 표면에서 먼저 브루트포스 대상이 된다. 값·길이 미출력 규약은 동일.
    if reporter_key and len(reporter_key) < MIN_KEY_LEN:
        logger.warning(
            "[api_auth_reporter_key_weak] key_len=%d — 32바이트 이상(token_urlsafe(32)) 권장",
            len(reporter_key),
        )
    # cycle249 적대 검증(auth-bypass, MEDIUM) — `authorize` 는 운영 키를 **선행** 비교
    # 하므로(§4) 두 키가 같은 값이면 운영자 분기가 항상 먼저 이겨 리포터 분기(§5)에
    # 도달하지 않는다 = 리포터 스코프가 **존재하지 않고** 그 키를 쥔 쪽이 전권을 가진다.
    # 모든 요청이 정상 200 이라 운영 관측(응답 코드·기존 `reporter_enabled=true` 한
    # 줄)으로는 절대 드러나지 않는다 — 그래서 기동 시점에 **한 번** 시끄럽게 비교한다.
    # 값·길이는 여전히 미출력(§2.3.6 불변) — 일치 여부(bool)만 CRITICAL 로 알린다.
    reporter_distinct = True
    if key and reporter_key:
        try:
            collides = secrets.compare_digest(key.encode("utf-8"), reporter_key.encode("utf-8"))
        except Exception:
            collides = False
        if collides:
            reporter_distinct = False
            logger.critical(
                "[api_auth_reporter_key_collision] API_REPORTER_KEY 가 API_AUTH_KEY 와 "
                "동일 — 리포터 스코프가 존재하지 않는다(값 미출력). 서로 다른 키를 "
                "설정하라(생성: python3 -c \"import secrets;print(secrets.token_urlsafe(32))\")"
            )
    logger.info(
        "[api_auth_config] enabled=%s key_len=%d allowed_origins=%d "
        "protected=all_except_health reporter_enabled=%s reporter_distinct=%s",
        "true" if key else "false",
        len(key),
        len(_allowed_origin_set()),
        # cycle249 — 활성 여부만 노출한다. 값·길이를 찍으면 그 자체가 유출 표면이다
        # (cycle246: 렌더된 nginx 주석에 키가 박혀 설정 덤프로 샜다).
        "true" if reporter_key else "false",
        # cycle249 적대 검증 시정 — 리포터 키가 운영 키와 구별되는지(충돌 없음)를
        # 별도 필드로 병기한다. 리포터 비활성(빈 키)이면 충돌 여지가 없어 true.
        "true" if reporter_distinct else "false",
    )


# ---------------------------------------------------------------------------
# 미들웨어
# ---------------------------------------------------------------------------
class ApiAuthMiddleware:
    """순수 ASGI 인증 관문. **최외곽**에 등록한다(`src/main.py`).

    최외곽이어야 하는 결정적 근거 = `MetricsMiddleware` 가 `_endpoint_metrics` 를
    **정규화 없는 raw path** 로 키잉하는데 키 개수 상한이 없다. 인증을 안쪽에 두면 익명
    `/api/<랜덤>` 폭주가 매매 프로세스 안의 dict 를 무한 증식시키고
    `GET /api/system/metrics` 가 그걸 되비춘다 = **인증 계층이 DoS 증폭기가 된다**.
    """

    def __init__(self, app):
        # 키를 캡처하지 않는다 — 요청 시점 `settings` 참조가 계약이다.
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            # lifespan·websocket 은 판정 없이 통과. 빠뜨리면 앱이 기동조차 못 한다.
            return await self.app(scope, receive, send)

        try:
            # 전역 이름 호출 = 테스트 seam(파일 docstring 4번). `self._authorize` 금지.
            reason = authorize(scope)
        except Exception as exc:  # noqa: BLE001 — 판정 불능은 **거부**로 흡수(fail-closed)
            # 새 사유를 만들지 않는다: 사유 집합이 열리면 cap 키가 무제한으로 늘어난다.
            reason = REASON_BAD_KEY
            _log_internal_error(exc)

        if not reason:
            return await self.app(scope, receive, send)

        _log_reject(scope, reason)  # 실패해도 아래 거부 응답은 그대로 나간다
        # `WWW-Authenticate` 를 붙이지 않는다 — 브라우저가 백엔드 다이얼로그를 띄우면
        # nginx Basic Auth(Phase 1) 자격과 혼동된다.
        # cycle249 — `reporter_scope` 만 403(키는 맞았고 권한이 없다). 나머지 4종은
        # 종전대로 401(모르는 키에까지 403 을 주면 공격자에게 유효 키 보유를 알려준다).
        if reason == REASON_REPORTER_SCOPE:
            response = JSONResponse(_FORBIDDEN_BODY, status_code=403)
        else:
            response = JSONResponse(_UNAUTHORIZED_BODY, status_code=401)
        await response(scope, receive, send)
