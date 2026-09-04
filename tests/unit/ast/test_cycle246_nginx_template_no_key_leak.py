"""cycle246 — nginx 템플릿이 렌더 결과에 API 키를 흘리지 않음을 못박는다.

■ 발단 (2026-09-04 실측)
cycle243 배포 후 렌더된 `/etc/nginx/conf.d/default.conf` 에 `API_AUTH_KEY` 값이
**2회** 등장했다. 하나는 정당한 `proxy_set_header X-API-Key`, 다른 하나는 **설명
주석**이었다 — 템플릿 주석이 치환 구문을 문자 그대로 담고 있었고 envsubst 는
주석을 구분하지 않기 때문이다. 결과적으로 비밀이 설정 파일 본문에 평문으로
박혀 운영 중 설정 덤프(`docker exec ... cat`)로 그대로 새어 나왔다.

■ 이 가드가 지키는 계약
치환 구문(달러+중괄호)의 `API_AUTH_KEY` 참조는 템플릿 전체에서 **정확히 한 번**,
그리고 그 한 번은 반드시 `proxy_set_header X-API-Key` 줄이어야 한다.

⚠️ 이 파일은 검사 대상 문자열을 **문자 단위로 조립**한다. 소스에 치환 구문을 그대로
적으면 가드 자신이 위반 사례가 되기 때문이다(cycle243 D-15 가 명세 인용문을 위반으로
세어 커밋 직후 붉어진 것과 같은 부류).
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE = _ROOT / "frontend" / "nginx.conf.template"

# 치환 구문을 리터럴로 적지 않고 조립한다 (위 ⚠️ 참조).
_D = chr(36)                      # '$'
_SUBST = _D + "{API_AUTH_KEY}"    # 치환 구문
_BARE = _D + "API_AUTH_KEY"       # 중괄호 없는 형태도 envsubst 가 치환한다
_HEADER_LINE = "proxy_set_header X-API-Key"


def _lines() -> list[str]:
    assert _TEMPLATE.is_file(), f"템플릿이 없다: {_TEMPLATE}"
    return _TEMPLATE.read_text(encoding="utf-8").splitlines()


def test_template_when_scanned_then_subst_appears_exactly_once():
    """G-246-1 — 치환 구문은 템플릿 전체에서 정확히 1회."""
    hits = [(i + 1, ln) for i, ln in enumerate(_lines()) if _SUBST in ln]
    assert len(hits) == 1, (
        "nginx 템플릿의 치환 구문이 1회가 아니다 — 주석·설명문에 적으면 렌더 결과에 "
        f"키가 평문으로 박힌다(cycle246 발단): {hits}"
    )


def test_template_when_subst_used_then_only_on_proxy_header_line():
    """G-246-2 — 그 1회는 반드시 `proxy_set_header X-API-Key` 줄이다."""
    hits = [ln for ln in _lines() if _SUBST in ln]
    assert hits and _HEADER_LINE in hits[0], (
        f"치환 구문이 `{_HEADER_LINE}` 이 아닌 줄에 있다: {hits!r}"
    )


def test_template_when_scanned_then_no_braceless_substitution():
    """G-246-3 — 중괄호 없는 `$API_AUTH_KEY` 도 envsubst 가 치환하므로 금지.

    `${...}` 만 막으면 설명문에 중괄호 없는 형태를 적었을 때 같은 유출이 재발한다.
    """
    offenders = []
    for i, ln in enumerate(_lines(), 1):
        # `${API_AUTH_KEY}` 는 위 가드가 담당 — 여기서는 그 형태를 지운 뒤 검사한다.
        stripped = ln.replace(_SUBST, "")
        if _BARE in stripped:
            offenders.append((i, ln.strip()[:100]))
    assert not offenders, (
        f"중괄호 없는 치환 형태가 남아 있다(envsubst 가 동일하게 치환한다): {offenders}"
    )


def test_template_when_filter_declared_then_anchored_to_single_var():
    """G-246-4 — compose 의 `NGINX_ENVSUBST_FILTER` 가 앵커된 단일 변수여야 한다.

    앵커(`^`/`$`)가 없으면 엔트리포인트가 부분 일치로 평가해 `API_AUTH_KEY_OLD` 류까지
    치환 대상이 되고, 유출 표면이 넓어진다.
    """
    compose = (_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    m = re.search(r"NGINX_ENVSUBST_FILTER=(\S+)", compose)
    assert m, "docker-compose.prod.yml 에 NGINX_ENVSUBST_FILTER 가 없다"
    assert m.group(1) == "^API_AUTH_KEY" + _D, (
        f"FILTER 가 앵커된 단일 변수가 아니다: {m.group(1)!r}"
    )


def test_client_when_basic_auth_enabled_then_xhr_sends_credentials():
    """G-246-5 — axios 클라이언트가 `withCredentials: true` 를 유지한다.

    이게 없으면 문서는 인증되는데 SPA 의 XHR 이 무자격으로 나가 401 을 받고
    브라우저가 **두 번째 로그인 다이얼로그**를 띄운다(cycle246 발단, nginx 접근 로그
    실측: 같은 초의 `/api/*` 다수가 user 필드 `-`).
    """
    src = (_ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    # ⚠️ 주석을 먼저 걷어낸다. 같은 파일의 설명 주석이 `withCredentials: true` 를
    # 문자열로 담고 있어, 순진한 전체 검색은 **실제 설정을 주석 처리해도 통과**한다
    # (cycle246 뮤테이션 실증: `// withCredentials: true,` 로 바꿔도 초록).
    code_lines = [
        ln for ln in src.splitlines()
        if not ln.lstrip().startswith("//")
    ]
    code = "\n".join(code_lines)
    assert re.search(r"^\s*withCredentials:\s*true\s*,?\s*$", code, re.M), (
        "axios 클라이언트에 실효 `withCredentials: true` 설정이 없다(주석 제외) — "
        "Basic Auth 하에서 XHR 이 무자격으로 나가 로그인 다이얼로그가 두 번 뜬다"
    )
