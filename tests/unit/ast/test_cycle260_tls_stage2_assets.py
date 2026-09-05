"""cycle260 Red — TLS 2단계(http→https 301 · HSTS) 준비 자산의 정적 가드 (G-260-1 · G-260-2).

명세: `_workspace/specs/cycle260_tls_stage2_prep.md`. cycle255(1단계, 443 병행)의 후속으로
**스위치를 켜지 않은 채** 코드·절차만 들여온다. 가동은 09-07 20:20 자동 리포트가 https 로
성공한 것을 사람이 확인한 뒤 `tools/ops/tls_stage2_enable.sh` 가 한다.

■ 왜 정적 가드가 (거의) 유일한 자동 가드인가
cycle243 L4 · cycle255 서두가 적어둔 이유가 그대로다 — vitest 는 jsdom+MSW, Playwright 는
vite dev server 라 **둘 다 nginx 를 경유하지 않는다**. 게다가 2단계는 인증서 + 443 이 있어야
재현되므로 CI 에서 실기동조차 못 한다. 리포 안에서 회귀를 잡는 것은 이 파일의 텍스트/구조
가드 + `tests/unit/deploy/test_cycle260_*`(가짜 docker/curl 행위 실증)뿐이고, 실 nginx 렌더
2구성(스니펫 디렉터리 있음/없음)은 tester 가 로컬 `nginx:alpine` 으로 수동 검증한다.

■ 이 사이클의 스위치 = **마운트 존재**
두 템플릿에는 `include /etc/nginx/conf.d/stage2/<glob>.conf;` 한 줄(들)만 들어가고, 그
디렉터리는 `docker-compose.tls2.yml` 오버레이가 마운트할 때만 존재한다. 마커(`.tls_stage2`)가
없으면 디렉터리가 없고 nginx 의 와일드카드 include 는 아무것도 못 찾은 채 넘어가므로 렌더
결과가 1단계와 **행위 동일**이다. 그래서 이 파일이 지키는 것은 세 가지다:
  (a) 템플릿에는 **동작(301·HSTS) 리터럴이 0건**이고 include 한 줄만 있다 — 리터럴이 들어오면
      마커와 무관하게 항상 켜진 것이고, 그건 준비가 아니라 가동이다.
  (b) include 대상은 **와일드카드**이고 `conf.d` 의 **하위** 디렉터리다 — 리터럴 파일명이면
      디렉터리 부재 시 nginx 가 `[emerg]` 로 기동 실패해 80 까지 내려가고, `conf.d` 직속에
      두면 nginx 기본 `include /etc/nginx/conf.d/*.conf` 가 http 컨텍스트로 먼저 집어삼킨다.
  (c) 서버 레벨 glob 과 location 레벨 glob 이 **서로 다른 파일 집합**을 연다 — 겹치면 같은
      `add_header Strict-Transport-Security` 가 두 번 붙어 응답 헤더가
      `max-age=86400, max-age=86400` 이 되고, HSTS 는 값이 파싱되지 않아 **통째로 무시**된다
      (켰다고 믿는데 안 켜진, 관측으로 드러나지 않는 실패).

■ 기존 가드와의 관계 (중복이 아니라 축이 다르다)
D-1/D-1-b(cycle243) · G-246-*(치환 유출) · G-247-*(아이콘) · G-255-*(ACME·TLS 사본)은 이
사이클이 **같은 두 파일을 다시 편집**하기 때문에 재확인 대상이다. 여기서는 "cycle260 이
그 불변식을 깨지 않았는가" 만 본다 — 회귀가 났을 때 어느 사이클이 깼는지 이 파일이 말한다.

⚠️ 명세 §1 이 열어 둔 분기: 로컬 nginx 실측에서 "존재하지 않는 디렉터리의 와일드카드
include" 가 오류를 내면 Green 은 2-오버레이(`docker-compose.tls2.off.yml`) 대안을 택한다.
그 경우 G-260-2 의 오버레이 계약과 배포 스크립트 행위 계약을 함께 재협상해야 한다 —
이 파일은 명세의 **기본 설계**(단일 오버레이)를 잰다.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_HTTP_TEMPLATE = _ROOT / "frontend" / "nginx.conf.template"
_TLS_TEMPLATE = _ROOT / "frontend" / "nginx.tls.conf.template"
_SNIPPET_DIR = _ROOT / "tools" / "ops" / "tls_stage2"
_COMPOSE_PROD = _ROOT / "docker-compose.prod.yml"
_COMPOSE_TLS = _ROOT / "docker-compose.tls.yml"
_COMPOSE_TLS2 = _ROOT / "docker-compose.tls2.yml"
_GITIGNORE = _ROOT / ".gitignore"

DOMAIN = "auto.dkstock.cloud"
HTPASSWD_PATH = "/etc/nginx/secrets/.htpasswd"
ACME_WEBROOT = "/var/www/certbot"
#: 컨테이너 안의 스니펫 디렉터리 — `conf.d` **하위**여야 한다(직속이면 nginx 기본
#: `include /etc/nginx/conf.d/*.conf` 가 http 컨텍스트에서 먼저 읽어 server 블록 밖이 된다).
STAGE2_DIR = "/etc/nginx/conf.d/stage2"
#: 호스트 쪽 원본 — 오버레이가 이 경로를 RO 로 마운트한다.
STAGE2_HOST_MOUNT = f"./tools/ops/tls_stage2:{STAGE2_DIR}:ro"
#: 2단계 활성 마커(git 밖 호스트 파일). `.tls_enabled` 와 **함께** 있을 때만 유효하다.
STAGE2_MARKER = ".tls_stage2"
#: HSTS 는 1일로 시작한다 — 되돌릴 수 없는 상태를 브라우저에 심으므로 상향은 별도 결정이다.
HSTS_MAX_AGE = 86400

#: cycle247 아이콘 단락 3줄 — byte 로 못박는다(G-255-1e/2h 와 같은 축).
_ICON_LINES = (
    "    location = /favicon.ico { return 204; }",
    "    location = /favicon.svg { return 204; }",
    "    location ~ ^/apple-touch-icon(-[0-9]+x[0-9]+)?(-precomposed)?\\.png$ { return 204; }",
)

# 치환 구문은 리터럴로 적지 않고 조립한다 — 이 파일 자신이 위반 사례가 되지 않도록.
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
_SPA_LOCATION = r"location\s+/\s*\{"
_HSTS_NAME = "strict-transport-security"

#: stage2 include 한 줄 — 캡처 그룹 1 = include 인자(글롭 경로).
_STAGE2_INCLUDE = re.compile(
    r"^[ \t]*include[ \t]+(" + re.escape(STAGE2_DIR) + r"/[^;\s]+)[ \t]*;",
    re.M,
)


# ── 공통 헬퍼 (cycle255 가드와 동일 관례) ──────────────────────────────────

def _read(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"Red — {path.relative_to(_ROOT)} 부재 (명세 §범위)")
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
    return [d.strip() for d in body.split(";") if d.strip()]


def _stage2_includes(path: Path) -> list[tuple[int, str]]:
    """(파일 안 오프셋, include 인자) 목록 — 주석 제거본 기준."""
    text = _strip_comments(_read(path))
    return [(m.start(), m.group(1)) for m in _STAGE2_INCLUDE.finditer(text)]


def _snippet_files() -> list[Path]:
    """스니펫 디렉터리 **직속**의 `.conf` 파일들(하위 디렉터리는 보지 않는다)."""
    if not _SNIPPET_DIR.is_dir():
        pytest.fail(f"Red — {_SNIPPET_DIR.relative_to(_ROOT)}/ 디렉터리 부재 (명세 §범위)")
    return sorted(p for p in _SNIPPET_DIR.iterdir() if p.is_file() and p.suffix == ".conf")


def _matched(glob_path: str) -> list[Path]:
    """컨테이너 경로 글롭이 여는 **호스트** 파일 집합."""
    pattern = glob_path.rsplit("/", 1)[-1]
    return [p for p in _snippet_files() if fnmatch.fnmatch(p.name, pattern)]


def _one_include(path: Path, depth: int) -> str:
    hits = [(off, arg) for off, arg in _stage2_includes(path) if _depth_at(_strip_comments(_read(path)), off) == depth]
    assert len(hits) == 1, (
        f"{path.name} 의 depth={depth} stage2 include 가 1줄이 아니다: {hits}"
    )
    return hits[0][1]


# ===========================================================================
# G-260-1a — HTTP 템플릿(80): stage2 include 한 줄, 동작 리터럴 0건
# ===========================================================================
def test_http_template_when_stage2_then_exactly_one_include_at_server_level():
    """G-260-1a — stage2 include 가 **정확히 1줄**, server 직속, ACME location 보다 **앞**.

    server 레벨 `if ($uri !~ …) { return 301 …; }` 는 rewrite 단계라 location 선택보다 먼저
    돈다 — 그래서 include 를 어느 location 안에 넣으면 리다이렉트가 그 경로에서만 걸리고
    나머지는 평문으로 남는다. 파일 안 위치(ACME 앞)는 읽는 사람을 위한 규약이다: 챌린지
    예외가 어디서 오는지 그 다음 블록에서 바로 보인다.
    """
    text = _strip_comments(_read(_HTTP_TEMPLATE))
    hits = _stage2_includes(_HTTP_TEMPLATE)
    assert len(hits) == 1, f"HTTP 템플릿의 stage2 include 가 1줄이 아니다: {hits}"
    off, arg = hits[0]
    assert _depth_at(text, off) == 1, (
        "stage2 include 가 server 블록 직속이 아니다 — location 안이면 그 경로만 리다이렉트된다"
    )
    acme = re.search(_ACME_LOCATION, text)
    assert acme, "ACME 챌린지 location 이 사라졌다(G-255-1a 회귀)"
    assert off < acme.start(), "stage2 include 가 ACME location 뒤에 있다(명세 §테스트 G-260-1)"


def test_http_template_when_stage2_then_include_is_wildcard_under_subdirectory():
    """G-260-1b — include 대상은 **와일드카드**이고 `conf.d` 의 **하위** 디렉터리다.

    이 한 줄이 사이클 전체의 스위치다.
    - 리터럴 파일명(`…/stage2/http-redirect.conf`)이면 마운트가 없는 평시에 nginx 가
      `[emerg] open() failed` 로 **기동 실패**한다 — 같은 컨테이너의 80 까지 죽어 스위치가
      아니라 지뢰가 된다. 와일드카드 include 는 매치 0건을 오류로 보지 않는다.
    - `conf.d` **직속**에 두면 nginx 기본 `include /etc/nginx/conf.d/*.conf` 가 같은 파일을
      **http 컨텍스트**로 먼저 읽어 `add_header`/`if` 가 server 밖에서 파싱된다(기동 실패).
    """
    arg = _one_include(_HTTP_TEMPLATE, depth=1)
    assert arg.startswith(STAGE2_DIR + "/"), arg
    name = arg.rsplit("/", 1)[-1]
    assert "/" not in name, f"stage2 하위의 또 다른 디렉터리를 연다: {arg}"
    assert "*" in name, (
        f"include 인자가 와일드카드가 아니다({arg}) — 마운트 없는 평시에 nginx 가 기동 실패한다"
    )
    assert name.endswith(".conf"), arg


def test_http_template_when_stage2_then_no_redirect_literal_in_template():
    """G-260-1c — 템플릿 자체에는 `return 301`·`https://` 리다이렉트 리터럴이 **0건**이다.

    리터럴이 들어오면 마커·마운트와 무관하게 **항상 켜진 것**이다. 이 사이클의 계약은
    "리포에 들어와도 아무것도 켜지지 않는다" 이고, 그 진위는 이 단언 하나로 갈린다.
    (`return 204;` 아이콘 단락은 cycle247 자산이라 대상이 아니다.)
    """
    text = _strip_comments(_read(_HTTP_TEMPLATE))
    assert not re.findall(r"\breturn\s+30[12]\b", text), (
        "HTTP 템플릿에 리다이렉트 리터럴이 있다 — 마운트 없이도 켜진 상태다"
    )
    assert not re.findall(r"\brewrite\s+", text), "rewrite 지시어 금지(리다이렉트는 스니펫이 갖는다)"
    assert DOMAIN not in text, (
        f"HTTP 템플릿에 {DOMAIN} 리터럴이 있다 — 도메인 고정 리다이렉트는 스니펫 소관이다"
    )


def test_http_template_when_stage2_then_no_hsts_literal():
    """G-260-1d — HTTP(80) 템플릿에 HSTS 리터럴 0건.

    HSTS 는 평문 응답에 실으면 브라우저가 무시한다(RFC 6797 — http 응답의 HSTS 는 폐기).
    무의미할 뿐 아니라, 80 이 준비 상태에서 이미 무언가를 심고 있다는 착시를 만든다.
    """
    raw = _read(_HTTP_TEMPLATE)
    assert _HSTS_NAME not in raw.lower(), "HTTP 템플릿에 HSTS 가 있다(평문 응답의 HSTS 는 무시된다)"


def test_http_template_when_stage2_added_then_auth_and_acme_contract_intact():
    """G-260-1e — D-1/D-1-b·G-255-1 불변: auth_basic 축 · `satisfy` 정확 1회(ACME 블록 안).

    2단계가 편집하는 파일이 바로 그 불변식들이 사는 파일이다. `satisfy` 가 하나 늘면
    그것이 곧 `auth_basic off` 와 동등한 우회이고, 텍스트 가드가 아니면 아무도 못 잡는다.
    """
    text = _strip_comments(_read(_HTTP_TEMPLATE))
    assert [m for m in re.finditer(_AUTH_BASIC_REALM, text) if _depth_at(text, m.start()) == 1], (
        "server 레벨 auth_basic realm 이 사라졌다"
    )
    api_block = _block_body(text, r"location\s+/api/\s*\{")
    assert api_block and re.search(_AUTH_BASIC_REALM, api_block), "/api/ auth_basic realm 부재"
    assert not re.findall(_AUTH_BASIC_OFF, text), "`auth_basic off;` 금지(D-1-b)"

    hits = [m.start() for m in re.finditer(r"\bsatisfy\b", text)]
    assert len(hits) == 1, f"`satisfy` 가 1회가 아니다(인증 우회가 늘어난다): {len(hits)}건"
    body = _block_body(text, _ACME_LOCATION)
    assert body is not None, "ACME location 블록을 찾지 못했다"
    assert "satisfy any" in _norm(body) and "allow all" in _norm(body), body
    assert f"root {ACME_WEBROOT}" in _norm(body), body
    offenders = [d for d in _directives(body) if d.split()[0] not in {"satisfy", "allow", "root", "default_type"}]
    assert not offenders, f"ACME 블록에 허용되지 않은 지시어가 있다: {offenders}"


def test_http_template_when_stage2_added_then_icon_and_key_substitution_intact():
    """G-260-1f — 아이콘 3줄 byte 동일 + 치환 구문은 여전히 `map` 안 2줄뿐(G-247·G-246 축).

    envsubst 는 주석을 구분하지 않는다 — 2단계 설명문에 치환 구문을 적으면 렌더된 설정
    주석에 키가 평문으로 박힌다(cycle246 발단 그대로).
    """
    raw = _read(_HTTP_TEMPLATE)
    for line in _ICON_LINES:
        assert line in raw, f"아이콘 단락 줄이 바뀌었다(cycle247 회귀): {line!r}"

    lines = raw.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r"\s*map\s+\$remote_user\s+", ln)), None)
    assert start is not None, "`map $remote_user …` 블록이 사라졌다"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "}"), None)
    assert end is not None, "map 블록이 닫히지 않았다"
    for token, owner in ((_SUBST_AUTH, "default"), (_SUBST_REPORTER, "reporter")):
        hits = [(i, ln) for i, ln in enumerate(lines) if token in ln]
        assert len(hits) == 1, f"치환 구문이 1회가 아니다({owner}): {hits}"
        idx, line = hits[0]
        assert start <= idx <= end, f"치환 구문이 map 블록 밖에 있다: {line!r}"
    bare = [
        (i, ln.strip()[:80])
        for i, ln in enumerate(lines, 1)
        if _BARE_AUTH in ln.replace(_SUBST_AUTH, "") or _BARE_REPORTER in ln.replace(_SUBST_REPORTER, "")
    ]
    assert not bare, f"중괄호 없는 치환 형태: {bare}"


# ===========================================================================
# G-260-1g~k — TLS 템플릿(443): server 1 + location 2 include, HSTS 리터럴 0건
# ===========================================================================
def test_tls_template_when_stage2_then_one_server_include_and_two_location_includes():
    """G-260-1g — TLS 템플릿의 stage2 include 는 **정확히 3줄**: server 1 + location 2.

    nginx `add_header` 는 **상속이 아니라 대체**다 — 하위 location 이 자기 `add_header` 를
    하나라도 가지면 상위의 add_header 는 그 location 에서 **전부 사라진다**. 이 템플릿의
    `location /`(Cache-Control) 와 정적자산 location(Cache-Control) 이 정확히 그 경우라,
    server 레벨 HSTS 만으로는 **문서와 JS/CSS 응답에 HSTS 가 붙지 않는다**(= 실질적으로
    HSTS 가 안 켜진다). 그래서 두 location 안에도 같은 헤더를 넣어야 한다.
    server 레벨 것은 `/api/`(401)·아이콘(204)처럼 자체 add_header 가 없는 응답을 덮는다.
    """
    text = _strip_comments(_read(_TLS_TEMPLATE))
    hits = _stage2_includes(_TLS_TEMPLATE)
    assert len(hits) == 3, f"TLS 템플릿의 stage2 include 가 3줄이 아니다: {hits}"
    depths = sorted(_depth_at(text, off) for off, _ in hits)
    assert depths == [1, 2, 2], f"include 깊이 분포가 (server 1 + location 2) 가 아니다: {depths}"

    spa = _block_body(text, _SPA_LOCATION)
    static = _block_body(text, _STATIC_ASSET_LOCATION)
    assert spa is not None, "TLS 템플릿의 SPA fallback location 이 사라졌다"
    assert static is not None, "TLS 템플릿의 정적자산 location 이 사라졌다"
    for name, body in (("location /", spa), ("정적자산 location", static)):
        assert _STAGE2_INCLUDE.search(body), (
            f"{name} 안에 stage2 include 가 없다 — 그 응답에는 HSTS 가 붙지 않는다"
            "(add_header 는 상속이 아니라 대체)"
        )


def test_tls_template_when_stage2_then_location_includes_share_one_glob():
    """G-260-1h — 두 location 의 include 인자는 **같은 글롭 문자열**이다.

    서로 다르면 한쪽 응답만 HSTS 를 받는 구성이 조용히 생긴다(문서엔 붙고 JS 엔 안 붙는
    식). 같은 파일을 두 곳에서 여는 것이 의도다.
    """
    text = _strip_comments(_read(_TLS_TEMPLATE))
    loc_args = sorted({arg for off, arg in _stage2_includes(_TLS_TEMPLATE) if _depth_at(text, off) == 2})
    assert len(loc_args) == 1, f"location include 글롭이 하나가 아니다: {loc_args}"
    arg = loc_args[0]
    assert arg.startswith(STAGE2_DIR + "/") and "*" in arg.rsplit("/", 1)[-1], arg
    assert arg.endswith(".conf"), arg


def test_tls_template_when_stage2_then_server_and_location_globs_are_disjoint():
    """G-260-1i — server 글롭과 location 글롭이 **서로 다른 파일 집합**을 연다.

    ⚠️ 명세 §1 초안의 `tls-*.conf`(server) + `tls-loc-*.conf`(location) 조합은 이 계약을
    **위반**한다 — `tls-*` 가 `tls-loc-hsts.conf` 까지 매치해 server 레벨에서 같은
    `add_header` 가 두 번 붙는다. 그러면 응답 헤더가
    `Strict-Transport-Security: max-age=86400, max-age=86400` 이 되고, HSTS 값 파싱이
    실패해 브라우저가 **헤더를 통째로 무시**한다(켰다고 믿는데 안 켜진 상태 — 관측으로
    드러나지 않는다). Green 은 겹치지 않는 이름/글롭을 골라야 한다.
    """
    text = _strip_comments(_read(_TLS_TEMPLATE))
    inc = _stage2_includes(_TLS_TEMPLATE)
    srv = [arg for off, arg in inc if _depth_at(text, off) == 1]
    loc = [arg for off, arg in inc if _depth_at(text, off) == 2]
    assert srv and loc, (srv, loc)

    srv_files = {p.name for p in _matched(srv[0])}
    loc_files = {p.name for p in _matched(loc[0])}
    assert srv_files, f"server 글롭({srv[0]})이 여는 스니펫이 하나도 없다"
    assert loc_files, f"location 글롭({loc[0]})이 여는 스니펫이 하나도 없다"
    overlap = srv_files & loc_files
    assert not overlap, (
        f"server 글롭과 location 글롭이 같은 파일을 연다: {sorted(overlap)} — "
        "server 레벨에서 add_header 가 중복되어 HSTS 헤더가 무효값이 된다"
    )


def test_tls_template_when_stage2_then_no_hsts_or_redirect_literal():
    """G-260-1j — TLS 템플릿에도 HSTS·리다이렉트 리터럴이 0건이다(G-255-2c 유지).

    1단계 가드 G-255-2c 가 "HSTS 없음" 을 못박아 뒀다. 2단계에서도 그 단언은 **그대로
    참**이어야 한다 — 헤더는 마운트되는 스니펫에만 산다. 그래야 `rm .tls_stage2` +
    frontend 재기동이 완전한 원복이고, 1단계 가드를 고쳐 쓰지 않아도 된다.
    """
    raw = _read(_TLS_TEMPLATE)
    assert _HSTS_NAME not in raw.lower(), (
        "TLS 템플릿에 HSTS 리터럴이 있다 — 마커 없이도 켜진 상태이고 G-255-2c 를 깬다"
    )
    text = _strip_comments(raw)
    assert not re.findall(r"\breturn\s+30[12]\b", text), "TLS 템플릿에 리다이렉트 리터럴이 있다"


def test_tls_template_when_stage2_added_then_cycle255_invariants_intact():
    """G-260-1k — G-255-2 불변: 443/도메인 · 인증서 경로 · auth_basic · map 0 · satisfy 0 · 아이콘.

    TLS 템플릿을 다시 편집하는 사이클이므로 1단계 계약 전체를 이 파일에서도 재확인한다.
    특히 `map` 재정의는 nginx 가 **정상 기동**하면서 모든 사용자의 X-API-Key 를 빈 값으로
    만드는 무증상 실패라, 텍스트 가드가 유일한 방어다.
    """
    text = _strip_comments(_read(_TLS_TEMPLATE))
    assert re.search(r"\blisten\s+443\s+ssl\b[^;]*;", text), "`listen 443 ssl;` 부재"
    assert re.search(rf"\bserver_name\s+{re.escape(DOMAIN)}\s*;", text), f"`server_name {DOMAIN};` 부재"
    norm = _norm(text)
    live = f"/etc/letsencrypt/live/{DOMAIN}"
    assert f"ssl_certificate {live}/fullchain.pem;" in norm, norm
    assert f"ssl_certificate_key {live}/privkey.pem;" in norm, norm

    assert [m for m in re.finditer(_AUTH_BASIC_REALM, text) if _depth_at(text, m.start()) == 1], (
        "TLS server 레벨 auth_basic realm 부재 — 443 만 무인증이 된다"
    )
    assert f"auth_basic_user_file {HTPASSWD_PATH}" in norm, norm
    assert not re.findall(_AUTH_BASIC_OFF, text), "`auth_basic off;` 금지(D-1-b, TLS 사본에도 적용)"
    assert not re.findall(r"\bsatisfy\b", text), "TLS 템플릿의 `satisfy` 는 발급과 무관한 인증 우회다"
    assert not [ln for ln in text.splitlines() if re.match(r"\s*map\s+", ln)], (
        "TLS 템플릿에 map 블록이 있다 — 뒤 include 가 조용히 이겨 X-API-Key 가 빈 값이 된다"
    )

    api_block = _block_body(text, r"location\s+/api/\s*\{")
    assert api_block is not None, "TLS `/api/` 블록 부재"
    api_norm = _norm(api_block)
    assert "proxy_pass http://backend:8000;" in api_norm, api_norm
    assert "proxy_set_header Host $http_host;" in api_norm, api_norm
    assert f"proxy_set_header X-API-Key {_VAR_PER_USER};" in api_norm, api_norm

    raw = _read(_TLS_TEMPLATE)
    for line in _ICON_LINES:
        assert line in raw, f"TLS 템플릿의 아이콘 단락 줄이 바뀌었다: {line!r}"
    offenders = [
        (i, ln.strip()[:80])
        for i, ln in enumerate(raw.splitlines(), 1)
        if _SUBST_AUTH in ln or _SUBST_REPORTER in ln or _BARE_AUTH in ln or _BARE_REPORTER in ln
    ]
    assert not offenders, f"TLS 템플릿에 키 치환 구문이 있다(렌더 주석 유출): {offenders}"


# ===========================================================================
# G-260-1l~p — 스니펫 파일(`tools/ops/tls_stage2/*.conf`)
# ===========================================================================
def test_stage2_snippets_when_present_then_three_globs_partition_the_directory():
    """G-260-1l — 세 글롭이 스니펫 `.conf` 파일을 **정확히 분할**한다.

    - 어느 글롭에도 안 걸리는 파일 = 죽은 설정(운영자는 켰다고 믿는다).
    - 두 글롭에 걸리는 파일 = 같은 지시어가 80 과 443 양쪽/두 컨텍스트에 동시에 들어간다.
      HTTP 의 `if + return 301` 이 443 서버 블록에 들어가면 **https 가 자기 자신으로 무한
      리다이렉트**한다.
    """
    files = {p.name for p in _snippet_files()}
    assert files, f"{_SNIPPET_DIR.relative_to(_ROOT)}/ 에 .conf 스니펫이 없다"

    http_glob = _one_include(_HTTP_TEMPLATE, depth=1)
    text = _strip_comments(_read(_TLS_TEMPLATE))
    inc = _stage2_includes(_TLS_TEMPLATE)
    tls_srv = [a for off, a in inc if _depth_at(text, off) == 1]
    tls_loc = sorted({a for off, a in inc if _depth_at(text, off) == 2})
    assert tls_srv and len(tls_loc) == 1, (tls_srv, tls_loc)

    globs = {"http": http_glob, "tls-server": tls_srv[0], "tls-location": tls_loc[0]}
    matched: dict[str, set[str]] = {k: {p.name for p in _matched(v)} for k, v in globs.items()}
    for key, names in matched.items():
        assert names, f"글롭 {key}({globs[key]})이 여는 스니펫이 없다"

    counts = {name: sum(1 for names in matched.values() if name in names) for name in files}
    unmatched = sorted(n for n, c in counts.items() if c == 0)
    duplicated = sorted(n for n, c in counts.items() if c > 1)
    assert not unmatched, f"어느 글롭에도 안 걸리는 죽은 스니펫: {unmatched} (globs={globs})"
    assert not duplicated, f"두 글롭에 동시에 걸리는 스니펫: {duplicated} (globs={globs})"


def test_stage2_redirect_snippet_when_present_then_domain_pinned_301_excluding_acme():
    """G-260-1m — 80 스니펫: ACME 부정 조건 + `return 301 https://<도메인>$request_uri;`.

    두 가지가 계약이다.
    1. **도메인 고정** — `https://$host$request_uri` 로 쓰면 IP(3.38.228.74)로 들어온 요청이
       `https://3.38.228.74/` 로 가서 인증서 이름 불일치로 브라우저가 막는다. 인증서는
       이름 하나로 발급돼 있다.
    2. **ACME 예외** — `/.well-known/acme-challenge/` 가 301 이 되면 90일 뒤 갱신이 실패한다
       (챌린지는 http 로만 검증된다). 그리고 nginx 에서 `if` 가 안전하다고 보증되는 유일한
       용법이 `if` + `return` 이므로 블록 안에는 `return` 말고 아무것도 두지 않는다.
    """
    http_glob = _one_include(_HTTP_TEMPLATE, depth=1)
    files = _matched(http_glob)
    assert files, f"80 글롭({http_glob})이 여는 스니펫이 없다"
    text = _strip_comments("\n".join(p.read_text(encoding="utf-8") for p in files))
    norm = _norm(text)

    assert f"return 301 https://{DOMAIN}$request_uri;" in norm, (
        f"도메인 고정 301 이 없다(기대: `return 301 https://{DOMAIN}$request_uri;`): {norm!r}"
    )
    assert "https://$host" not in norm and "https://$http_host" not in norm, (
        "리다이렉트 대상이 변수다 — IP 접속이 인증서 이름 불일치로 막힌다"
    )
    ifs = re.findall(r"\bif\s*\(([^)]*)\)", text)
    assert len(ifs) == 1, f"`if` 는 정확히 1개여야 한다(nginx if is evil): {ifs}"
    cond = _norm(ifs[0])
    assert "acme-challenge" in cond, f"ACME 예외 조건이 없다 — 갱신이 301 로 깨진다: {cond!r}"
    assert "!~" in cond, f"ACME 조건이 **부정** 매치가 아니다: {cond!r}"

    body = _block_body(text, r"\bif\s*\([^)]*\)\s*\{")
    assert body is not None, "if 블록을 찾지 못했다"
    directives = _directives(body)
    assert directives and all(d.split()[0] == "return" for d in directives), (
        f"if 블록 안에 `return` 외 지시어가 있다(nginx 가 안전을 보증하지 않는 용법): {directives}"
    )


def test_stage2_hsts_snippets_when_present_then_one_day_max_age_always():
    """G-260-1n — 443 스니펫 2종: `max-age=86400` + `always`, includeSubDomains/preload 0건.

    - `always` 가 없으면 nginx 는 2xx/3xx 계열에만 헤더를 붙인다 — 이 사이트의 정상 응답은
      **무자격 401** 이라, `always` 를 빼면 로그인 전 브라우저가 HSTS 를 못 받는다.
    - `max-age` 는 **1일**로 시작한다. HSTS 는 브라우저에 되돌릴 수 없는 상태를 심는다 —
      180일로 시작하면 인증서 사고가 났을 때 80 으로 내려앉는 원복 경로가 반년간 막힌다.
    - `includeSubDomains` 는 `dkstock.cloud` 의 **다른 호스트까지** 강제 https 로 만든다
      (이 계정의 다른 서비스가 http 라면 그날로 접속 불가). `preload` 는 제출 시 사실상
      영구다 — 둘 다 이 단계에서 금지.
    """
    inc = _stage2_includes(_TLS_TEMPLATE)
    tls_globs = sorted({arg for _off, arg in inc})
    tls_files = {p.name: p.read_text(encoding="utf-8") for g in tls_globs for p in _matched(g)}
    assert len(tls_files) == 2, f"443 스니펫이 2개가 아니다(server 1 + location 1): {sorted(tls_files)}"

    for name, raw in sorted(tls_files.items()):
        body = _strip_comments(raw)
        norm = _norm(body)
        assert f'add_header Strict-Transport-Security "max-age={HSTS_MAX_AGE}" always;' in norm, (
            f"{name} 의 HSTS 지시어가 계약과 다르다: {norm!r}"
        )
        ages = re.findall(r"max-age=(\d+)", norm)
        assert ages == [str(HSTS_MAX_AGE)], f"{name} 의 max-age 가 1일(86400)이 아니다: {ages}"
        assert "includesubdomains" not in norm.lower(), f"{name}: includeSubDomains 금지"
        assert "preload" not in norm.lower(), f"{name}: preload 금지(사실상 영구)"
        directives = _directives(body)
        assert len(directives) == 1, f"{name} 에 지시어가 1개가 아니다: {directives}"


def test_stage2_snippets_when_present_then_no_context_changing_directives():
    """G-260-1o — 스니펫에는 컨텍스트를 바꾸거나 인증을 건드리는 지시어가 없다.

    이 파일들은 server/location **안으로 그대로 펼쳐진다**. `location`/`server` 가 들어오면
    중괄호가 어긋나 기동이 깨지고, `auth_basic`/`satisfy`/`allow` 가 들어오면 D-1-b 가 막아온
    인증 우회가 텍스트 가드 밖에서 생긴다. `proxy_pass`/`alias`/`root`/`try_files` 는 무자격
    콘텐츠 제공 경로다(G-247-2·G-255-1b 와 같은 논리).
    """
    banned = (
        "location", "server", "auth_basic", "auth_basic_user_file", "satisfy", "allow", "deny",
        "proxy_pass", "alias", "root", "try_files", "map", "include", "listen",
    )
    for p in _snippet_files():
        body = _strip_comments(p.read_text(encoding="utf-8"))
        for d in _directives(body):
            head = d.split()[0]
            assert head not in banned, f"{p.name} 에 금지 지시어: {d.strip()!r}"
        # 허용 구조는 "지시어들 + (최대 1개의 `if { … }` 블록)" 뿐이다 — 중첩 블록이 생기면
        # server/location 안으로 펼쳐질 때 무엇이 어느 컨텍스트에 들어가는지 읽을 수 없다.
        assert body.count("{") == body.count("}") <= 1, (
            f"{p.name} 에 중첩(또는 짝이 안 맞는) 블록이 있다: braces={body.count('{')}/{body.count('}')}"
        )


def test_stage2_snippets_when_present_then_no_envsubst_or_key_tokens():
    """G-260-1p — 스니펫에 치환 구문·키 이름이 0건이다.

    ⚠️ 이 파일들은 `/etc/nginx/templates/` 가 **아니라** `/etc/nginx/conf.d/stage2/` 로
    마운트되므로 **envsubst 를 통과하지 않는다**. 치환 구문을 적으면 치환되지 않고 그대로
    남아(`${API_AUTH_KEY}` 리터럴) 설정이 조용히 틀리거나 기동이 깨진다. 그리고 이 파일들은
    git 에 커밋되므로 키 이름조차 두지 않는다.
    """
    for p in _snippet_files():
        raw = p.read_text(encoding="utf-8")
        for token in (_SUBST_AUTH, _SUBST_REPORTER, _BARE_AUTH, _BARE_REPORTER, _VAR_PER_USER):
            assert token not in raw, f"{p.name} 에 치환/키 토큰이 있다: {token}"
        assert "$" not in raw or re.search(r"\$(uri|request_uri|scheme|host|http_host)\b", raw), (
            f"{p.name} 의 `$` 사용이 nginx 런타임 변수가 아니다"
        )


# ===========================================================================
# G-260-2 — 오버레이 · 기본 compose 무접촉 · .gitignore
# ===========================================================================
def _services(path: Path) -> dict:
    data = yaml.safe_load(_read(path)) or {}
    services = data.get("services") or {}
    assert services, f"{path.name} 에 services 가 없다"
    return services


def test_compose_tls2_overlay_when_present_then_frontend_only_single_readonly_mount():
    """G-260-2a — 2단계 오버레이는 `frontend` 하나 · 키는 `volumes` 뿐 · 마운트 1개(RO).

    `backend` 가 한 줄이라도 들어오면 그 서비스의 config 해시가 바뀌어 **backend 컨테이너가
    재생성**된다(cycle232 D6 — 장중 tick blind = 손절 사각). `ports`/`build`/`environment` 를
    다시 적는 것도 병합 결과를 예측 불가로 만들어 금지한다 — 443 게시는 1단계 오버레이
    (`docker-compose.tls.yml`)의 몫이고, 2단계는 **스니펫 디렉터리 하나만** 얹는다.
    """
    services = _services(_COMPOSE_TLS2)
    assert set(services) == {"frontend"}, (
        f"2단계 오버레이가 frontend 외 서비스를 건드린다(backend 재생성 위험): {sorted(services)}"
    )
    frontend = services["frontend"] or {}
    assert set(frontend) == {"volumes"}, (
        f"2단계 오버레이 frontend 키는 volumes 뿐이어야 한다: {sorted(frontend)}"
    )
    volumes = [str(v) for v in (frontend.get("volumes") or [])]
    assert volumes == [STAGE2_HOST_MOUNT], f"스니펫 마운트가 계약과 다르다: {volumes}"


def test_compose_tls2_overlay_when_present_then_no_tls_or_port_duplication():
    """G-260-2b — 2단계 오버레이에 443·인증서·`env_file` 흔적이 0건이다.

    1단계 오버레이가 이미 그것들을 얹는다. 여기서 다시 적으면 두 파일이 같은 키를 두고
    싸우고(compose 병합은 리스트를 합치므로 `443:443` 이 중복 게시된다), 무엇보다 "2단계는
    스니펫 마운트 하나" 라는 원복 단순성이 사라진다.
    """
    blob = yaml.safe_dump(_services(_COMPOSE_TLS2)).lower()
    for token in ("443", "letsencrypt", "certbot", "env_file", "8000"):
        assert token not in blob, f"2단계 오버레이에 {token} 흔적이 있다: {blob}"


def test_compose_tls_overlay_when_cycle260_applied_then_stage1_contract_unchanged():
    """G-260-2c — 1단계 오버레이(`docker-compose.tls.yml`)는 **한 줄도 늘지 않는다**(G-255-3b 핀).

    스니펫 마운트를 여기에 얹으면 `.tls_enabled` 만으로 2단계가 켜져 마커 게이트가 사라진다
    (= 준비가 곧 가동). 마운트를 늘릴 곳은 별도 오버레이뿐이다.
    """
    frontend = _services(_COMPOSE_TLS)["frontend"]
    assert set(frontend) <= {"ports", "volumes"}, sorted(frontend)
    assert [str(p) for p in (frontend.get("ports") or [])] == ["443:443"], frontend.get("ports")
    volumes = sorted(str(v) for v in (frontend.get("volumes") or []))
    assert volumes == sorted([
        "./frontend/nginx.tls.conf.template:/etc/nginx/templates/tls.conf.template:ro",
        "/etc/letsencrypt:/etc/letsencrypt:ro",
        f"./certbot-www:{ACME_WEBROOT}:ro",
    ]), f"1단계 오버레이 마운트가 늘었다(2단계는 별도 오버레이여야 한다): {volumes}"
    assert STAGE2_DIR not in yaml.safe_dump(frontend), "1단계 오버레이가 stage2 를 마운트한다"


def test_compose_prod_when_cycle260_applied_then_base_never_mounts_stage2():
    """G-260-2d — 기본 compose 는 stage2 를 마운트하지 않는다(무조건 켜짐 차단).

    기본 경로에 스니펫이 들어오면 마커·오버레이와 무관하게 **모든 배포가 2단계**가 된다.
    그러면 443 이 없는 상태(1단계 이전/원복 후)에서 80 이 https 로 무한 리다이렉트해 사이트가
    통째로 접속 불가가 된다 — 원복 수단이 남지 않는 방향의 사고다.
    """
    frontend = _services(_COMPOSE_PROD)["frontend"]
    volumes = [str(v) for v in (frontend.get("volumes") or [])]
    assert volumes == [
        "./secrets:/etc/nginx/secrets:ro",
        f"./certbot-www:{ACME_WEBROOT}:ro",
    ], f"prod frontend 볼륨이 계약과 다르다: {volumes}"
    assert [str(p) for p in (frontend.get("ports") or [])] == ["80:80"], frontend.get("ports")
    blob = yaml.safe_dump(_services(_COMPOSE_PROD))
    assert STAGE2_DIR not in blob and "tls_stage2" not in blob, "기본 compose 에 stage2 흔적이 있다"


def test_gitignore_when_cycle260_then_stage2_marker_is_ignored():
    """G-260-2e — `.tls_stage2` 가 `.gitignore` 에 있다(마커는 호스트 전용).

    마커가 커밋되면 리포를 클론한 **모든** 환경이 2단계로 켜지고, 원복(`rm`)이 다음 배포의
    `git pull` 로 되살아난다 — `.tls_enabled`(cycle255)·`.deployed_sha`(cycle248)와 같은 규약.
    """
    lines = [ln.strip() for ln in _read(_GITIGNORE).splitlines()]
    assert STAGE2_MARKER in lines, f"`.gitignore` 에 `{STAGE2_MARKER}` 줄이 없다"
    assert ".tls_enabled" in lines, "cycle255 마커 무시 규칙이 사라졌다"
