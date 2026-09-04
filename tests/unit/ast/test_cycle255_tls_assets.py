"""cycle255 Red — HTTPS(TLS) 준비 자산의 정적 가드 (G-255-1 · 2 · 3 · 5).

명세: `_workspace/red/cycle255_tls_spec.md`(작업 명세 §1~§3) — cycle243 후속 F1.

■ 왜 정적 가드가 (거의) 유일한 자동 가드인가
cycle243 D 가드가 적어둔 이유(L4)가 그대로 유효하다 — vitest 는 jsdom+MSW, Playwright 는
vite dev server 라 **둘 다 nginx 를 경유하지 않는다**. 여기에 TLS 는 인증서가 있어야 기동
하므로 CI 에서 실기동조차 못 한다. 리포 안에서 회귀를 잡는 것은 이 파일의 텍스트/구조
가드 + `tests/unit/deploy/test_cycle255_compose_tls_overlay.py`(가짜 docker 행위 실증)뿐이고,
실 nginx 6변형은 tester 가 로컬 `nginx:alpine` 으로 수동 검증한다.

■ 이 사이클이 여는 구멍과 그것을 좁히는 계약
ACME HTTP-01 은 `/.well-known/acme-challenge/<token>` 이 **무자격 200** 이어야 한다.
`auth_basic off;` 는 D-1-b 가 금지하므로(한 줄로 Basic + 백엔드 X-API-Key 주입이 동시에
뚫린다) 대신 `satisfy any; allow all;` 을 쓴다. 이 지시어는 **그 location 하나**에만
존재해야 하고 블록 안 지시어는 정적 토큰 제공에 필요한 것만 허용한다 — `proxy_pass` 나
`alias` 가 한 줄 들어오는 순간 그게 곧 무자격 콘텐츠 제공 경로다(G-247-2 와 같은 논리).

■ 기존 가드와의 관계 (중복이 아니라 축이 다르다)
- D-1/D-1-b(cycle243), G-246-*(치환 유출), G-247-*(아이콘 단락)은 **HTTP 템플릿**만 본다.
  이 파일은 (a) 그 불변식이 ACME 블록 추가로 깨지지 않았는지 재확인하고 (b) 같은 불변식을
  **신규 TLS 템플릿**에도 강제한다. TLS 템플릿은 리포에 처음 생기는 파일이라 기존 가드가
  단 한 줄도 보지 않는다 — 그대로 두면 인증·키유출·아이콘 축이 전부 무방비인 사본이 생긴다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_HTTP_TEMPLATE = _ROOT / "frontend" / "nginx.conf.template"
_TLS_TEMPLATE = _ROOT / "frontend" / "nginx.tls.conf.template"
_COMPOSE_PROD = _ROOT / "docker-compose.prod.yml"
_COMPOSE_TLS = _ROOT / "docker-compose.tls.yml"
_TLS_SCRIPT = _ROOT / "tools" / "ops" / "tls_enable.sh"

DOMAIN = "auto.dkstock.cloud"
HTPASSWD_PATH = "/etc/nginx/secrets/.htpasswd"
ACME_WEBROOT = "/var/www/certbot"

#: cycle247 아이콘 단락 3줄 — **byte 단위로** 못박는다(명세 §3 "아이콘 3블록 동일").
#: 구조 검사는 G-247 이 이미 하므로 여기서는 "cycle255 가 이 줄들을 건드리지 않았다" 와
#: "TLS 템플릿이 같은 줄을 그대로 갖는다" 두 가지만 본다.
_ICON_LINES = (
    "    location = /favicon.ico { return 204; }",
    "    location = /favicon.svg { return 204; }",
    "    location ~ ^/apple-touch-icon(-[0-9]+x[0-9]+)?(-precomposed)?\\.png$ { return 204; }",
)

# 치환 구문은 리터럴로 적지 않고 조립한다 — 이 파일 자신이 위반 사례가 되지 않도록
# (cycle246 가드와 같은 이유).
_D = chr(36)
_SUBST_AUTH = _D + "{API_AUTH_KEY}"
_SUBST_REPORTER = _D + "{API_REPORTER_KEY}"
_BARE_AUTH = _D + "API_AUTH_KEY"
_BARE_REPORTER = _D + "API_REPORTER_KEY"
_VAR_PER_USER = _D + "api_key_for_user"

_AUTH_BASIC_REALM = r'\bauth_basic\s+"[^"]+"\s*;'
_AUTH_BASIC_OFF = r"\bauth_basic\s+off\s*;"
_ACME_LOCATION = r"location\s+\^~\s+/\.well-known/acme-challenge/\s*\{"
_STATIC_ASSET_LOCATION = r"location\s*~\*\s*\\\.\(js\|css"
_APPLE_TOUCH_LOCATION = (
    r"location\s*~\s*\^/apple-touch-icon\(-\[0-9\]\+x\[0-9\]\+\)\?\(-precomposed\)\?\\\.png\$\s*\{"
)


def _read(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"Red — {path.relative_to(_ROOT)} 부재 (명세 §2 범위)")
    return path.read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    return "\n".join(ln.split("#", 1)[0] for ln in text.splitlines())


def _depth_at(text: str, idx: int) -> int:
    """idx 위치의 중괄호 깊이. http 컨텍스트=0 · server 직속=1 · location 안=2."""
    return text.count("{", 0, idx) - text.count("}", 0, idx)


def _block_body(text: str, header_pattern: str) -> str | None:
    m = re.search(header_pattern, text)
    if not m:
        return None
    open_idx = text.index("{", m.start())
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i]
    return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _directives(body: str) -> list[str]:
    """`;` 로 끝나는 지시어 목록(중첩 블록 없음을 전제 — 있으면 그 자체가 위반)."""
    return [d.strip() for d in body.split(";") if d.strip()]


# ===========================================================================
# G-255-1 — HTTP 템플릿(`frontend/nginx.conf.template`)
# ===========================================================================
def test_http_template_when_acme_added_then_prefix_location_inside_server():
    """G-255-1a — ACME 챌린지 location 이 **server 직속**의 `^~` 접두 location 이다.

    `^~` 가 계약이다: 이게 없으면 정규식 location(정적자산 `~* \\.(js|css|…)$`)이 먼저
    평가될 수 있고, 토큰 파일명이 우연히 그 패턴에 걸리면 챌린지가 access 단계로 떨어져
    401 → 발급 실패. 반대로 `/api/` 안이나 http 컨텍스트에 두면 아예 동작하지 않는다.
    """
    text = _strip_comments(_read(_HTTP_TEMPLATE))
    m = re.search(_ACME_LOCATION, text)
    assert m, (
        "ACME 챌린지 location(`location ^~ /.well-known/acme-challenge/`)이 없다 — "
        "HTTP-01 발급이 Basic Auth 401 로 막힌다"
    )
    assert _depth_at(text, m.start()) == 1, (
        "ACME location 이 server 블록 직속이 아니다(http 컨텍스트 또는 다른 location 안)"
    )


def test_http_template_when_acme_block_then_only_static_serving_directives():
    """G-255-1b — ACME 블록 안 지시어 ⊆ {satisfy, allow, root, default_type} ∧ 필수 3종 존재.

    `auth_basic off` 없이 인증을 우회하는 유일한 합법 수단이 `satisfy any; allow all;` 인데,
    같은 블록에 `proxy_pass`/`alias`/`try_files` 가 들어오면 그 경로가 곧 **무자격 콘텐츠
    제공**이 된다(G-247-2 와 동일한 논리 — 여기서는 인증이 명시적으로 꺼져 있어 더 위험하다).
    """
    body = _block_body(_strip_comments(_read(_HTTP_TEMPLATE)), _ACME_LOCATION)
    assert body is not None, "ACME location 블록을 찾지 못했다"
    assert "{" not in body and "}" not in body, f"ACME 블록 안에 중첩 블록이 있다: {body!r}"

    directives = _directives(body)
    allowed = {"satisfy", "allow", "root", "default_type"}
    offenders = [d for d in directives if d.split()[0] not in allowed]
    assert not offenders, (
        f"ACME 블록에 허용되지 않은 지시어가 있다(무자격 콘텐츠 제공 경로): {offenders}"
    )
    norm = _norm(body)
    assert "satisfy any" in norm, "`satisfy any` 부재 — 챌린지가 401 이 되어 발급이 실패한다"
    assert "allow all" in norm, "`allow all` 부재 — satisfy any 가 만족시킬 조건이 없다"
    assert f"root {ACME_WEBROOT}" in norm, (
        f"webroot 가 {ACME_WEBROOT} 가 아니다 — certbot `-w` 인자·compose 마운트와 어긋난다"
    )


def test_http_template_when_scanned_then_satisfy_any_exactly_once():
    """G-255-1c — `satisfy` 는 템플릿 전체에서 **정확히 1회**, 그리고 ACME 블록 안이다.

    `satisfy any` 는 이 파일에서 인증 상속을 합법적으로 끊는 유일한 도구다. 두 번째가
    생기는 순간 그것이 `auth_basic off` 와 동등한 우회(D-1-b 가 텍스트로 금지한 바로 그
    구멍)가 되고, 텍스트 가드가 아니면 아무도 못 잡는다.
    """
    text = _strip_comments(_read(_HTTP_TEMPLATE))
    hits = [m.start() for m in re.finditer(r"\bsatisfy\b", text)]
    assert len(hits) == 1, f"`satisfy` 가 1회가 아니다(인증 우회가 늘어난다): {len(hits)}건"

    m = re.search(_ACME_LOCATION, text)
    assert m, "ACME location 부재"
    open_idx = text.index("{", m.start())
    close_idx = open_idx + len(_block_body(text, _ACME_LOCATION) or "") + 1
    assert open_idx < hits[0] < close_idx, "`satisfy` 가 ACME 블록 밖에 있다"


def test_http_template_when_cycle255_applied_then_auth_basic_contract_intact():
    """G-255-1d — D-1/D-1-b 불변: server 레벨 realm 존재 · `/api/` 명시 · `auth_basic off` 0건.

    ACME 블록 추가가 인증 축을 건드리지 않았음을 이 사이클의 파일에서도 재확인한다
    (cycle243 가드가 같은 것을 보지만, 회귀가 났을 때 **어느 사이클이 깼는지**를 이
    파일이 말해준다).
    """
    text = _strip_comments(_read(_HTTP_TEMPLATE))
    assert [m for m in re.finditer(_AUTH_BASIC_REALM, text) if _depth_at(text, m.start()) == 1], (
        "server 레벨 auth_basic realm 이 사라졌다"
    )
    api_block = _block_body(text, r"location\s+/api/\s*\{")
    assert api_block and re.search(_AUTH_BASIC_REALM, api_block), "/api/ auth_basic realm 부재"
    assert not re.findall(_AUTH_BASIC_OFF, text), "`auth_basic off;` 금지(D-1-b)"


def test_http_template_when_cycle255_applied_then_icon_lines_byte_identical():
    """G-255-1e — 아이콘 단락 3줄이 **byte 그대로**다(G-247 구조 가드 + byte 고정).

    ACME location 은 `^~` 접두라 정규식 location 평가 순서에 영향을 주지 않는다. 그래도
    같은 파일을 편집하는 사이클이 인접 줄을 스치는 사고는 흔하므로 byte 로 못박는다.
    """
    raw = _read(_HTTP_TEMPLATE)
    for line in _ICON_LINES:
        assert line in raw, f"아이콘 단락 줄이 바뀌었다(cycle247 회귀): {line!r}"


def test_http_template_when_cycle255_applied_then_key_substitution_still_only_in_map():
    """G-255-1f — 치환 구문(`${API_*_KEY}`)은 여전히 `map` 블록 안 2줄뿐이다(cycle246 축).

    envsubst 는 주석을 구분하지 않는다 — ACME 블록의 설명문에 치환 구문을 적으면 렌더된
    설정에 키가 평문으로 박힌다(cycle246 발단 그대로). 중괄호 없는 형태도 같이 막는다.
    """
    lines = _read(_HTTP_TEMPLATE).splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r"\s*map\s+\$remote_user\s+", ln)), None)
    assert start is not None, "`map $remote_user …` 블록이 사라졌다"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "}"), None)
    assert end is not None, "map 블록이 닫히지 않았다"

    for token, owner in ((_SUBST_AUTH, "default"), (_SUBST_REPORTER, "reporter")):
        hits = [(i, ln) for i, ln in enumerate(lines) if token in ln]
        assert len(hits) == 1, f"치환 구문이 1회가 아니다({owner}): {hits}"
        idx, line = hits[0]
        assert start <= idx <= end, f"치환 구문이 map 블록 밖에 있다: {line!r}"
        assert line.strip().startswith(owner), f"치환 구문이 `{owner}` 줄이 아니다: {line!r}"

    bare = []
    for i, ln in enumerate(lines, 1):
        stripped = ln.replace(_SUBST_AUTH, "").replace(_SUBST_REPORTER, "")
        if _BARE_AUTH in stripped or _BARE_REPORTER in stripped:
            bare.append((i, ln.strip()[:80]))
    assert not bare, f"중괄호 없는 치환 형태(envsubst 가 동일하게 치환한다): {bare}"


# ===========================================================================
# G-255-2 — TLS 템플릿(`frontend/nginx.tls.conf.template`, 신규)
# ===========================================================================
def test_tls_template_when_present_then_listens_443_for_domain():
    """G-255-2a — `listen 443 ssl;` + `server_name auto.dkstock.cloud;`.

    server_name 이 `_`(catch-all) 면 인증서 SNI 와 무관하게 아무 Host 나 받아 TLS 종단이
    도메인 계약과 어긋난다 — 인증서는 이 이름 하나로 발급된다.
    """
    text = _strip_comments(_read(_TLS_TEMPLATE))
    assert re.search(r"\blisten\s+443\s+ssl\b[^;]*;", text), "`listen 443 ssl;` 부재"
    assert re.search(rf"\bserver_name\s+{re.escape(DOMAIN)}\s*;", text), (
        f"`server_name {DOMAIN};` 부재"
    )


def test_tls_template_when_present_then_cert_paths_and_protocols():
    """G-255-2b — 인증서 경로는 certbot live 심볼릭 링크 · `ssl_protocols TLSv1.2 TLSv1.3`.

    live 경로를 쓰지 않으면(예: archive 실경로) 갱신 때 파일이 회전해 reload 후에도 옛
    인증서를 물고 있는다. TLSv1.0/1.1 은 켜지 않는다.
    """
    text = _strip_comments(_read(_TLS_TEMPLATE))
    norm = _norm(text)
    live = f"/etc/letsencrypt/live/{DOMAIN}"
    assert f"ssl_certificate {live}/fullchain.pem;" in norm, norm
    assert f"ssl_certificate_key {live}/privkey.pem;" in norm, norm
    m = re.search(r"ssl_protocols\s+([^;]+);", norm)
    assert m, "`ssl_protocols` 부재"
    assert set(m.group(1).split()) == {"TLSv1.2", "TLSv1.3"}, m.group(1)


def test_tls_template_when_stage1_then_no_hsts_header():
    """G-255-2c — 1단계에는 HSTS 를 넣지 않는다.

    HSTS 는 브라우저에 **되돌릴 수 없는** 상태를 심는다(max-age 동안 http 접근 자체가
    차단). 인증서 갱신·리다이렉트 정책이 1주 이상 안정된 뒤 2단계에서 붙인다 — 그때까지는
    `rm .tls_enabled` + frontend 재기동으로 80 만 남기는 원복 경로가 살아 있어야 한다.
    """
    text = _read(_TLS_TEMPLATE)
    assert "strict-transport-security" not in text.lower(), (
        "1단계 TLS 템플릿에 HSTS 가 있다 — 원복 경로(80 단독)를 브라우저가 거부하게 된다"
    )


def test_tls_template_when_present_then_auth_basic_at_server_and_api():
    """G-255-2d — Basic Auth 축이 TLS 사본에서도 동일하다(server 레벨 + `/api/` 명시).

    TLS 서버 블록은 리포에 처음 생기는 파일이라 cycle243 D-1 이 단 한 줄도 보지 않는다.
    여기서 빠지면 **443 만 무인증**인 상태가 되고, 80 은 정상이라 증상이 드러나지 않는다.
    """
    text = _strip_comments(_read(_TLS_TEMPLATE))
    assert [m for m in re.finditer(_AUTH_BASIC_REALM, text) if _depth_at(text, m.start()) == 1], (
        "TLS 서버 블록에 server 레벨 auth_basic realm 이 없다 — 443 이 무인증이 된다"
    )
    assert f"auth_basic_user_file {HTPASSWD_PATH}" in _norm(text), (
        f"TLS 템플릿의 user_file 이 {HTPASSWD_PATH} 가 아니다"
    )
    api_block = _block_body(text, r"location\s+/api/\s*\{")
    assert api_block is not None, "TLS 템플릿에 `location /api/` 가 없다"
    assert re.search(_AUTH_BASIC_REALM, api_block), "TLS `/api/` 에 auth_basic realm 부재"
    assert HTPASSWD_PATH in api_block, "TLS `/api/` 에 user_file 부재"
    assert not re.findall(_AUTH_BASIC_OFF, text), "`auth_basic off;` 금지(D-1-b, TLS 사본에도 적용)"


def test_tls_template_when_proxying_then_same_headers_as_http():
    """G-255-2e — `/api/` 프록시 헤더 4종이 HTTP 템플릿과 동일하다.

    특히 `X-API-Key $api_key_for_user`(백엔드 인증) 와 `Host $http_host`(포트 보존 —
    Origin 검사) 가 빠지면 443 경로만 전부 401 이 된다. `X-Forwarded-Proto $scheme` 은
    TLS 에서 비로소 `https` 가 되므로 값이 아니라 **변수**여야 한다(하드코딩 금지).
    """
    api_block = _block_body(_strip_comments(_read(_TLS_TEMPLATE)), r"location\s+/api/\s*\{")
    assert api_block is not None, "TLS `/api/` 블록 부재"
    norm = _norm(api_block)
    assert "proxy_pass http://backend:8000;" in norm, norm
    assert "proxy_set_header Host $http_host;" in norm, norm
    assert "proxy_set_header Host $host;" not in norm, "`$host` 는 포트를 떨어뜨린다(D-2-b)"
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in norm, norm
    assert f"proxy_set_header X-API-Key {_VAR_PER_USER};" in norm, norm


def test_tls_template_when_present_then_no_map_block():
    """G-255-2f — TLS 템플릿에 `map` 블록이 **없다**.

    `map` 은 http 컨텍스트 지시어다. 같은 변수를 두 번 정의해도 nginx 는 **정상 기동한다**
    (`nginx -t` 성공, duplicate/emerg 로그 0건 — nginx:alpine 실측). 대신 뒤에 include 되는
    `tls.conf`(> `default.conf`)의 map 이 조용히 이겨 **모든 사용자의 X-API-Key 가 빈 값**이
    되고 http/https/reporter 전부 backend 401 이 된다 — 관측으로 드러나지 않는 실패라 이
    텍스트 가드가 유일한 방어다. 사용자별 키 선택은 HTTP 템플릿의 map 하나를 공유한다.
    """
    lines = _strip_comments(_read(_TLS_TEMPLATE)).splitlines()
    offenders = [ln.strip() for ln in lines if re.match(r"\s*map\s+", ln)]
    assert not offenders, (
        f"TLS 템플릿에 map 블록이 있다 — nginx 가 duplicate map 으로 기동 거부한다: {offenders}"
    )


def test_tls_template_when_rendered_then_no_key_substitution_syntax():
    """G-255-2g — TLS 템플릿에 치환 구문이 **0건**이다(cycle246 축의 TLS 사본).

    이 파일도 `/etc/nginx/templates/*.template` 로 마운트돼 **같은 envsubst 를 통과한다**.
    설명문에 치환 구문을 적으면 렌더된 `/etc/nginx/conf.d/tls.conf` 주석에 키가 평문으로
    박힌다 — cycle246 이 고친 결함이 새 파일에서 그대로 재현되는 경로다.
    """
    raw = _read(_TLS_TEMPLATE)
    offenders = [
        (i, ln.strip()[:80])
        for i, ln in enumerate(raw.splitlines(), 1)
        if _SUBST_AUTH in ln or _SUBST_REPORTER in ln or _BARE_AUTH in ln or _BARE_REPORTER in ln
    ]
    assert not offenders, f"TLS 템플릿에 키 치환 구문이 있다(렌더 주석 유출): {offenders}"


def test_tls_template_when_present_then_icon_lines_and_spa_block():
    """G-255-2h — 아이콘 단락 3줄 byte 동일 + SPA fallback + `root /usr/share/nginx/html`.

    아이콘 단락이 빠지면 https 접속에서 Safari 두 번째 로그인 다이얼로그(cycle247)가
    되살아난다. 정적자산 정규식이 있다면 apple-touch 블록이 그보다 앞이어야 한다
    (nginx 는 정규식 location 을 **선언 순서**로 매칭 — G-247-3 과 같은 축).
    """
    raw = _read(_TLS_TEMPLATE)
    for line in _ICON_LINES:
        assert line in raw, f"TLS 템플릿에 아이콘 단락 줄이 없다(cycle247 회귀): {line!r}"

    text = _strip_comments(raw)
    assert "root /usr/share/nginx/html;" in _norm(text), "SPA 루트 경로 부재"
    spa = _block_body(text, r"location\s+/\s*\{")
    assert spa and "try_files" in spa, "SPA fallback(`location / { try_files … }`) 부재"

    apple = re.search(_APPLE_TOUCH_LOCATION, text)
    static = re.search(_STATIC_ASSET_LOCATION, text)
    assert apple, "apple-touch 아이콘 단락 location 부재"
    if static:
        assert apple.start() < static.start(), (
            "apple-touch 단락이 정적자산 정규식 뒤에 있다 — 단락이 도달 불가(G-247-3)"
        )


def test_tls_template_when_present_then_no_satisfy_directive():
    """G-255-2i — TLS 템플릿에 `satisfy` 는 0건이다.

    ACME 챌린지는 **80 에서만** 처리한다(갱신도 HTTP-01 그대로). 443 에 인증 우회 지시어를
    복사하면 그것은 발급과 무관한 순수 구멍이다 — "`satisfy any` 는 그 location 하나에만"
    이라는 명세 §0 제약의 다른 절반.
    """
    text = _strip_comments(_read(_TLS_TEMPLATE))
    assert not re.findall(r"\bsatisfy\b", text), "TLS 템플릿의 `satisfy` 는 발급과 무관한 인증 우회다"


# ===========================================================================
# G-255-3 — compose (오버레이 신규 + prod 최소 변경)
# ===========================================================================
def _services(path: Path) -> dict:
    data = yaml.safe_load(_read(path)) or {}
    services = data.get("services") or {}
    assert services, f"{path.name} 에 services 가 없다"
    return services


def test_compose_tls_overlay_when_present_then_frontend_only_no_backend_key():
    """G-255-3a — 오버레이는 `frontend` **하나만** 정의하고 키는 {ports, volumes} 뿐이다.

    오버레이에 backend 가 한 줄이라도 들어오면 그 서비스의 config 해시가 바뀌어
    **backend 컨테이너가 재생성**된다(cycle232 D6 — 장중 tick blind 손절 사각).
    `build`/`environment` 를 다시 적는 것도 같은 위험(merge 결과가 달라진다)이라 막는다.
    """
    services = _services(_COMPOSE_TLS)
    assert set(services) == {"frontend"}, (
        f"TLS 오버레이가 frontend 외 서비스를 건드린다(backend 재생성 위험): {sorted(services)}"
    )
    frontend = services["frontend"] or {}
    assert set(frontend) <= {"ports", "volumes"}, (
        f"오버레이 frontend 키는 ports/volumes 뿐이어야 한다: {sorted(frontend)}"
    )
    assert "ports" in frontend and "volumes" in frontend, sorted(frontend)
    assert "env_file" not in frontend, "오버레이에 env_file 금지(비밀이 nginx 컨테이너로 샌다)"


def test_compose_tls_overlay_when_present_then_443_and_three_readonly_mounts():
    """G-255-3b — 443 게시 + 세 마운트(전부 `:ro`).

    - TLS 템플릿 → `/etc/nginx/templates/tls.conf.template` (이미지에 굽지 않는다 —
      인증서가 없는 상태에서 이미지에 들어가면 nginx 가 기동 실패한다)
    - 호스트 `/etc/letsencrypt` (certbot 산출물)
    - 챌린지 webroot (HTTP 서버 블록이 읽는 경로와 동일해야 한다)
    셋 다 읽기전용이다 — nginx 가 인증서나 챌린지 파일을 쓸 이유가 없다.
    """
    frontend = _services(_COMPOSE_TLS)["frontend"]
    ports = [str(p) for p in (frontend.get("ports") or [])]
    assert "443:443" in ports, f"443 게시가 없다: {ports}"

    volumes = [str(v) for v in (frontend.get("volumes") or [])]
    expected = {
        "./frontend/nginx.tls.conf.template:/etc/nginx/templates/tls.conf.template:ro",
        "/etc/letsencrypt:/etc/letsencrypt:ro",
        f"./certbot-www:{ACME_WEBROOT}:ro",
    }
    assert set(volumes) == expected, f"오버레이 마운트 불일치: {sorted(volumes)}"


def test_compose_prod_when_cycle255_applied_then_frontend_gains_only_certbot_mount():
    """G-255-3c — prod 의 frontend 는 certbot webroot 마운트 **한 줄만** 늘고 나머지는 그대로.

    HTTP 서버 블록의 ACME location(`root /var/www/certbot`)이 파일을 실제로 읽으려면 기본
    compose 에도 같은 마운트가 있어야 한다(오버레이는 발급 **후**에야 켜지므로 기본 경로에
    없으면 첫 발급 자체가 불가능하다 — 닭·달걀).
    """
    frontend = _services(_COMPOSE_PROD)["frontend"]
    volumes = [str(v) for v in (frontend.get("volumes") or [])]
    assert volumes == [
        "./secrets:/etc/nginx/secrets:ro",
        f"./certbot-www:{ACME_WEBROOT}:ro",
    ], f"prod frontend 볼륨이 계약과 다르다: {volumes}"

    assert [str(p) for p in (frontend.get("ports") or [])] == ["80:80"], (
        "기본 compose 는 80 만 게시한다 — 443 은 오버레이 전용(인증서 없이 443 을 열면 기동 실패)"
    )
    assert "env_file" not in frontend, "frontend env_file 금지(cycle243 D-5)"
    assert set(frontend) == {"build", "ports", "volumes", "environment", "depends_on", "restart"}, (
        f"prod frontend 키 집합이 바뀌었다: {sorted(frontend)}"
    )


def test_compose_prod_when_cycle255_applied_then_backend_untouched_by_tls():
    """G-255-3d — prod 의 backend 블록에 TLS 흔적이 0건이다(재생성 방지).

    cycle243 D-5-b 가 backend 키/값 전부를 못박고 있으므로 여기서는 **이 사이클의 축**만
    본다: 443·인증서·챌린지 어느 것도 backend 로 새지 않았는가.
    """
    backend = _services(_COMPOSE_PROD).get("backend")
    assert backend, "backend 서비스가 사라졌다"
    blob = yaml.safe_dump(backend)
    for token in ("443", "letsencrypt", "certbot", "tls"):
        assert token not in blob.lower(), f"backend 블록에 TLS 흔적이 있다({token}): {blob}"


def test_compose_prod_when_cycle255_applied_then_no_tls_server_config_in_base():
    """G-255-3e — 기본 compose 에는 443·인증서 마운트가 없다.

    기본 경로가 인증서를 요구하면 인증서가 없는 상태(= 지금, 그리고 원복 후)에서 nginx 가
    기동하지 못해 **80 까지 죽는다**. TLS 는 반드시 오버레이로만 켜진다 — 그래야
    `rm .tls_enabled` 한 줄이 완전한 원복이다.
    """
    # 주석은 검사하지 않는다 — "443 은 오버레이 전용" 같은 설명문이 오히려 권장된다.
    # 보는 것은 **파싱된 구성**이다.
    blob = yaml.safe_dump(_services(_COMPOSE_PROD)).lower()
    assert "443" not in blob, "기본 compose 구성에 443 이 있다 — 인증서 부재 시 기동 실패 = 원복 불가"
    assert "letsencrypt" not in blob, "기본 compose 에 인증서 마운트가 있다(인증서 부재 시 기동 실패)"


# ===========================================================================
# G-255-5 — 발급·전환 스크립트(`tools/ops/tls_enable.sh`, 신규)
# ===========================================================================
def _script_src() -> str:
    return _read(_TLS_SCRIPT)


def _script_code() -> str:
    """주석 줄 제외 — 설명문의 단어는 검사 대상이 아니다(channel_probe 가드와 동일 관례)."""
    return "\n".join(ln for ln in _script_src().splitlines() if not ln.lstrip().startswith("#"))


def test_tls_script_when_present_then_bash_syntax_ok_and_strict_mode():
    """G-255-5a — `bash -n` 통과 + `set -euo pipefail`.

    이 스크립트는 EC2 에서 **운영 중 단 한 번** 돌고 중간 실패가 반쪽 상태(인증서는 있는데
    마커만 없음 / 마커는 있는데 컨테이너는 옛 설정)를 만든다. 중단 규약이 없으면 실패한
    사전 점검 뒤에도 계속 진행한다.
    """
    import subprocess

    assert _TLS_SCRIPT.exists(), f"Red — {_TLS_SCRIPT.relative_to(_ROOT)} 부재"
    proc = subprocess.run(["bash", "-n", str(_TLS_SCRIPT)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert re.search(r"^set -euo pipefail\s*$", _script_src(), re.M), "`set -euo pipefail` 부재"


def test_tls_script_when_run_then_dns_precheck_before_certbot():
    """G-255-5b — `dig +short auto.dkstock.cloud` 사전 점검이 certbot 호출 **앞**에 있다.

    A 레코드가 아직 없거나 다른 IP 를 가리키는 상태로 certbot 을 부르면 Let's Encrypt 의
    **실패 rate limit**(계정·도메인당)을 소모한다 — 하루에 몇 번 만에 그날 발급이 봉쇄되고,
    그 상태에서는 사용자가 A 레코드를 고쳐도 기다리는 것 외에 방법이 없다.
    """
    code = _script_code()
    dns = re.search(rf"dig\s+\+short\s+{re.escape(DOMAIN)}", code)
    assert dns, "`dig +short` DNS 사전 점검이 없다"
    assert "3.38.228.74" in code, "기대 IP(3.38.228.74) 대조가 없다 — 사전 점검이 공허하다"
    certbot = re.search(r"\bcertbot\b\s+certonly", code)
    assert certbot, "`certbot certonly` 호출이 없다"
    assert dns.start() < certbot.start(), "DNS 점검이 certbot 호출 뒤에 있다(rate limit 소모)"


def test_tls_script_when_issuing_then_webroot_matches_nginx_root():
    """G-255-5c — `--webroot -w …/certbot-www` 가 nginx `root /var/www/certbot` 과 짝이다.

    호스트 `./certbot-www` ↔ 컨테이너 `/var/www/certbot` 이 같은 디렉터리다. 한쪽만 바꾸면
    챌린지 파일을 certbot 이 쓰고 nginx 는 못 찾아 발급이 404 로 실패한다.
    `--standalone` 은 80 을 점유하려다 nginx 와 충돌하므로 금지한다.
    """
    code = _script_code()
    assert "--webroot" in code, "`--webroot` 방식이 아니다"
    assert "--standalone" not in code, (
        "`--standalone` 은 80 을 점유해 nginx 와 충돌한다(운영 중 사이트가 끊긴다)"
    )
    assert "certbot-www" in code, "호스트 webroot(`certbot-www`)가 스크립트에 없다"

    # `-w` 는 certbot **명령 안**에서만 찾는다 — 같은 스크립트의 `curl -w '%{http_code}'`
    # 같은 다른 플래그를 집으면 가드가 엉뚱한 문자열을 검사한다(프로토타입 실측).
    cmd = re.search(r"certbot\s+certonly((?:[^\n]|\\\n)*)", code)
    assert cmd, "`certbot certonly` 명령을 찾지 못했다"
    m = re.search(r"-w\s+(\S+)", cmd.group(1))
    assert m, f"certbot 명령에 `-w <webroot>` 인자가 없다: {cmd.group(1)[:120]!r}"
    arg = m.group(1).strip("\"'")
    if arg.startswith(_D):  # 변수로 받아도 좋다 — 다만 그 변수가 certbot-www 여야 한다
        var = arg.lstrip(_D).strip("{}")
        assign = re.search(rf"^\s*(?:export\s+)?{re.escape(var)}=([^\n]*)", code, re.M)
        assert assign and "certbot-www" in assign.group(1), (
            f"`-w {arg}` 의 대입이 certbot-www 를 가리키지 않는다: {assign.group(1) if assign else None}"
        )
    else:
        assert "certbot-www" in arg, f"`-w` 인자가 certbot-www 가 아니다: {arg!r}"
    assert arg.rstrip("/") != ACME_WEBROOT, (
        "certbot 은 **호스트**에서 돈다 — 컨테이너 경로(/var/www/certbot)를 `-w` 로 주면 "
        "호스트에 없는 디렉터리에 토큰을 쓰고 nginx 는 빈 webroot 를 읽어 404 로 실패한다"
    )


def test_tls_script_when_enabling_then_marker_written_after_successful_issue():
    """G-255-5d — `.tls_enabled` 마커 생성은 발급 **성공 뒤**다.

    마커가 먼저 생기면 다음 배포가 인증서 없는 상태로 443 오버레이를 올려 nginx 가 기동
    실패하고 **80 까지 내려간다**(오버레이 = 같은 컨테이너). 순서 하나가 전면 장애/정상을
    가른다.
    """
    code = _script_code()
    marker_writes = [m.start() for m in re.finditer(r"\.tls_enabled", code)]
    assert marker_writes, "`.tls_enabled` 마커를 만들지 않는다"
    create = re.search(r"(touch|>)\s*\S*\.tls_enabled", code)
    assert create, "마커 생성(touch 또는 리다이렉트) 구문이 없다"
    certbot = re.search(r"\bcertbot\b\s+certonly", code)
    assert certbot and certbot.start() < create.start(), (
        "마커 생성이 발급보다 앞이다 — 인증서 없는 443 기동 = frontend 전면 실패"
    )
    live = [m.start() for m in re.finditer(r"/etc/letsencrypt/live/\S*fullchain\.pem", code)]
    assert live, (
        "발급 산출물(fullchain.pem) 존재 확인이 없다 — certbot 종료 코드만 믿으면 dry-run·"
        "기존 인증서 재사용과 구별하지 못한다"
    )
    assert DOMAIN in code, f"도메인({DOMAIN}) 이 스크립트에 없다"
    assert min(live) < create.start(), "산출물 확인이 마커 생성 뒤다(순서가 뒤집히면 무의미)"


def _compose_up_lines() -> list[str]:
    """실행되는 `docker compose … up` 줄만 — `log`/`echo` 안내문은 명령이 아니다(안내문이 원복 up 을
    대신하면 F1 그 자체다)."""
    return [
        ln.strip()
        for ln in _script_code().splitlines()
        if "docker compose" in ln and " up " in ln
        and not re.match(r"\s*(log|echo)\b", ln)
    ]


def test_tls_script_when_switching_then_frontend_only_compose_up():
    """G-255-5e — 모든 `docker compose … up` 은 `--no-deps frontend`(backend 무접촉).

    전환은 장중에도 할 수 있어야 한다 — backend 를 건드리면 cycle232 D6(보유 중 재시작
    금지)에 걸려 전환 창이 하루 한 번으로 줄어든다. 전환 up 과 원복 up 이 모두 여기를 지난다.
    """
    ups = _compose_up_lines()
    assert ups, "`docker compose … up` 호출이 없다"
    for up in ups:
        assert "-f docker-compose.prod.yml" in up, f"base compose 가 빠진 up: {up}"
        assert re.search(r"--no-deps\s+frontend\b", up), f"backend 를 건드리는 up: {up}"
        assert "backend" not in up, up


def test_tls_script_when_switching_then_exactly_one_overlay_up_in_order():
    """G-255-5e-b — 전환 up 은 **정확히 1줄**이고 `-f prod -f tls` 순서다.

    compose 는 뒤에 오는 파일이 이긴다 — 오버레이가 base 앞에 오면 "base 위에 얹는다"는
    의도가 뒤집힌다. 전환 up 이 둘이면 어느 쪽이 실측 대상인지 사후 검증이 모호해진다.
    """
    switch = [u for u in _compose_up_lines() if "-f docker-compose.tls.yml" in u]
    assert len(switch) == 1, f"오버레이 up 은 정확히 1줄이어야 한다: {switch}"
    assert switch[0].index("-f docker-compose.prod.yml") < switch[0].index("-f docker-compose.tls.yml"), (
        "오버레이가 base 앞에 있다(뒤에 오는 파일이 이긴다)"
    )


def test_tls_script_when_switch_fails_then_base_only_rollback_up_exists():
    """G-255-5e-c — 원복 up(prod **단독**, 오버레이 없음)이 코드에 있다.

    F1 실측: 오버레이 `up -d` 가 non-zero 로 끝난 컨테이너는 created 로 멈춰 80 도 000 이고,
    크래시 루프는 exit 0 이라 안내문만으로는 80 이 돌아오지 않는다 — base 단독 up 이
    Recreate 해야 복구된다. 원복 up 에 오버레이가 붙으면 그건 원복이 아니라 재시도다.
    """
    rollback = [u for u in _compose_up_lines() if "-f docker-compose.tls.yml" not in u]
    assert rollback, "prod 단독 원복 up 이 없다(오버레이 up 실패 시 80 이 내려간 채 남는다)"
    for up in rollback:
        assert re.findall(r"-f\s+(\S+)", up) == ["docker-compose.prod.yml"], (
            f"원복 up 의 -f 는 prod 하나뿐이어야 한다: {up}"
        )
        assert "--build" not in up, f"원복 up 은 빌드 없는 up 이다(이미지는 그대로): {up}"


def test_tls_script_when_switched_then_health_verified_before_success():
    """G-255-5e-d — 5/6 뒤 사후 검증(80 401 ∧ 443 401 ∧ State=running)이 코드에 있고 전환 up 뒤다.

    `docker compose up -d` 는 컨테이너가 크래시 루프여도 exit 0 이다(compose v5.1 실측 —
    nginx `[emerg]` 로 restarting 이어도 0). 종료 코드만 믿으면 '완료' 를 찍고 마커를 남겨
    다음 자동 배포가 같은 오버레이를 재현한다. 세 축을 **같은 이터레이션**에서 본다.
    """
    code = _script_code()
    switch = re.search(r"docker compose -f docker-compose\.prod\.yml -f docker-compose\.tls\.yml up ", code)
    assert switch, "전환 up 부재"
    http = re.search(r"curl[^\n]*http://127\.0\.0\.1/api/health", code)
    https = re.search(rf"curl[^\n]*--resolve\s+{re.escape(DOMAIN)}:443:127\.0\.0\.1[^\n]*https://{re.escape(DOMAIN)}/api/health", code)
    state = re.search(r"docker compose[^\n]*\bps\b[^\n]*frontend", code)
    for name, m in (("80 health", http), ("443 health", https), ("State 조회", state)):
        assert m, f"사후 검증 {name} 이 없다"
        assert m.start() > switch.end(), f"사후 검증 {name} 이 전환 up 앞에 있다"
    assert '"State":"running"' in code, "State=running 판정이 없다(restarting 을 성공으로 본다)"
    assert re.search(r'"401"[^\n]*"401"', code) or code.count('"401"') >= 2, "401 기대값 대조가 없다"
    assert re.search(r"\bsleep\s+1\b", code), "폴링(sleep 1) 이 없다 — 첫 요청 한 번으로 판정하면 기동 중 오탐이 난다"


def test_tls_script_when_failed_then_documents_rollback():
    """G-255-5f — 원복 절차(`rm .tls_enabled` + frontend 재기동)가 스크립트 안에 적혀 있다.

    전환 실패 시 운영자가 읽을 문서가 이 파일 하나다(EC2 에는 리포 문서를 열 여유가 없다).
    80 은 계속 살아 있다는 사실까지 명시돼야 조급한 2차 조치를 막는다.
    """
    src = _script_src()
    assert re.search(r"rm\s+(-f\s+)?\S*\.tls_enabled", src), "원복 절차(`rm .tls_enabled`)가 없다"
    assert "80" in src, "원복 후 80 이 유지된다는 안내가 없다"


def test_tls_script_when_renewing_then_reload_hook_present():
    """G-255-5g — 갱신 훅이 nginx **reload** 다(재기동 아님).

    `certbot renew` 는 파일만 바꾸고 nginx 는 시작 시점의 인증서를 물고 있다 — reload 가
    없으면 90일 뒤 조용히 만료된다(무증상 → 전면 접속 불가). `restart`/`up` 은 재생성이라
    같은 컨테이너의 80 까지 잠시 끊는다.
    """
    code = _script_code()
    assert re.search(r"certbot\s+renew", code), "`certbot renew` 갱신 절차가 없다"
    assert "nginx -s reload" in code, "갱신 훅에 `nginx -s reload` 가 없다(90일 뒤 조용한 만료)"


def test_tls_script_when_issuing_then_deploy_hook_persisted_and_no_crontab():
    """G-255-5g-b — reload 훅은 `certonly --deploy-hook` 으로 renewal conf 에 영속되고, crontab 안내는 없다.

    F4: 종전 안내(ubuntu `crontab -e` + 상대경로 compose)는 그대로는 동작하지 않았다 —
    ① ubuntu 는 /etc/letsencrypt 쓰기 불가 ② cron cwd 에서 상대경로 `-f` 는 'no configuration
    file' ③ snap timer 는 훅 없이 갱신해 디스크 인증서만 바뀌고 nginx 는 옛 인증서를 문다.
    `--deploy-hook` 은 certbot 이 renewal conf 에 저장하므로 어느 갱신 경로든 reload 가 붙는다.
    훅 문자열은 cwd·PATH·TTY 에 의존하지 않아야 한다(절대경로 `--project-directory`, `exec -T`).
    """
    code = _script_code()
    cmd = re.search(r"certbot\s+certonly((?:[^\n]|\\\n)*)", code)
    assert cmd, "`certbot certonly` 명령을 찾지 못했다"
    assert "--deploy-hook" in cmd.group(1), "certonly 에 `--deploy-hook` 이 없다(갱신 시 reload 미실행 → 만료)"
    hook = re.search(r"^\s*RELOAD_HOOK=([^\n]*)$", code, re.M)
    assert hook, "훅 문자열 변수(RELOAD_HOOK) 대입이 없다"
    hook_val = hook.group(1)
    assert "--project-directory" in hook_val, "훅에 `--project-directory` 가 없다(cron/timer cwd 는 `/` 다)"
    assert "exec -T frontend nginx -s reload" in hook_val, "훅이 `exec -T frontend nginx -s reload` 가 아니다"
    assert hook_val.count("docker-compose.tls.yml") == 1 and hook_val.count("docker-compose.prod.yml") == 1, hook_val
    assert re.search(r"certbot\s+renew\s+--dry-run", code), "갱신 경로 자체 검증(`certbot renew --dry-run`)이 없다"
    # 설명문에서 crontab 을 *언급* 하는 것은 허용한다(왜 안 두는지 적어야 한다). 금지는 **지시** 형태 —
    # `crontab -e` 안내와 cron 스케줄 줄(`17 3 * * 1,4 certbot renew …`)이다.
    src = _script_src()
    assert not re.search(r"(?<!sudo )crontab\s+-e", src), (
        "ubuntu `crontab -e` 안내가 남아 있다 — 그대로는 동작하지 않는 절차다(F4)"
    )
    assert not re.search(r"^[^\n]*\S+\s+\S+\s+\*\s+\*\s+\S+\s+certbot\s+renew", src, re.M), (
        "cron 스케줄 줄로 certbot renew 를 안내한다 — 훅은 renewal conf 영속이 정본이다(F4)"
    )


def test_tls_script_when_probing_then_webroot_prepared_with_sudo_install():
    """G-255-5i — probe 디렉터리는 `sudo install -d … -o $(id -u)` 로 만들고, 그 뒤에 probe 를 쓴다.

    F2 실측(ubuntu:24.04): `./certbot-www` 는 prod compose 의 bind mount 가 root:root 755 로
    먼저 만들어 두므로 ubuntu 의 `mkdir -p ./certbot-www/.well-known/…` 는 EACCES 로 죽는다
    (`.token_cache` root 소유 사고와 동일 계열). certbot 은 sudo 라 무관하고, 죽는 것은 ubuntu 가
    쓰는 probe 뿐이다 — 그래서 소유자를 ubuntu 로 맞춘 디렉터리를 sudo 로 만든다.
    """
    code = _script_code()
    prep = re.search(r"^\s*sudo\s+install\s+-d\b[^\n]*$", code, re.M)
    assert prep, "`sudo install -d` 로 probe 디렉터리를 만들지 않는다(root 소유 certbot-www 에서 EACCES)"
    line = prep.group(0)
    assert re.search(r"-o\s+\"?\$\(id -u\)", line), f"`-o $(id -u)` 소유자 지정이 없다: {line}"
    assert "acme-challenge" in line, f"대상이 acme-challenge 디렉터리가 아니다: {line}"
    probe = re.search(r"^[^\n#]*>\s*[^\n]*acme-challenge/probe", code, re.M)
    assert probe, "probe 파일 쓰기가 없다"
    assert prep.start() < probe.start(), "probe 쓰기가 디렉터리 준비보다 앞이다"
    bare = re.findall(r"^\s*mkdir\s+-p\s+[^\n]*certbot-www", code, re.M)
    assert not bare, f"sudo 없는 `mkdir -p …certbot-www` 가 남아 있다(EACCES 재현): {bare}"


def test_tls_script_when_scanned_then_no_secret_literals():
    """G-255-5h — 스크립트에 비밀값 리터럴이 없다.

    이 파일은 git 에 커밋된다. htpasswd 비밀번호·API 키·개인키가 들어가면 리포 전체가
    오염되고, private 전환(cycle243 발단)으로 되돌릴 수 없다.
    """
    src = _script_src()
    assert not re.search(r"BEGIN [A-Z ]*PRIVATE KEY", src), "개인키가 스크립트에 있다"
    assert not re.search(r"htpasswd\b[^\n]*\s-\w*b\w*\s", src), (
        "`htpasswd -b` 는 비밀번호를 인자로 받는다(셸 히스토리·리포 유출)"
    )
    offenders = re.findall(
        r"^\s*(?:export\s+)?(?:API_\w*KEY|PASSWORD|PASSWD|SECRET)\s*=\s*[\"']?[A-Za-z0-9_\-]{8,}",
        src,
        re.M,
    )
    assert not offenders, f"비밀값 리터럴로 보이는 대입이 있다: {offenders}"
