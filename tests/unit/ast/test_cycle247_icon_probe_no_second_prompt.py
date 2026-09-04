"""cycle247 — 브라우저 아이콘 탐침이 Basic Auth 의 **두 번째 로그인 다이얼로그**가 되지 않음을 못박는다.

■ 발단 (2026-09-04, Safari 시크릿 창 실측)
cycle246(`withCredentials`) 배포 후에도 로그인이 두 번 떴다. nginx 접근 로그가 원인을
그대로 보여줬다 — 같은 초에 문서·JS·`/api/*` 는 전부 `user=ubuntu` 200 인데,
`/favicon.ico` `/favicon.svg` `/apple-touch-icon.png` `/apple-touch-icon-precomposed.png`
넷만 `user=-` 401 이었고 12초 뒤 같은 경로가 `ubuntu` 로 재요청됐다(= 재입력).
Safari 의 WebKit 네트워킹 프로세스는 아이콘을 페이지 자격 없이 따로 가져오고, 그 401 의
`WWW-Authenticate` 가 두 번째 다이얼로그가 된다. cycle246 은 Chrome 세션에서 관측된 XHR
무자격 경로만 닫은 것이었다.

■ 시정 계약
1. nginx 템플릿이 아이콘 경로 셋을 `return 204;` 로 **단락**한다 — `return` 은 rewrite
   단계라 access 단계의 `auth_basic` 에 도달하지 않는다(nginx:alpine 로컬 실측: 아이콘 204,
   `/`·`/assets/*`·`/api/` 는 그대로 401). `auth_basic off` 는 여전히 0건(D-1-b 불변).
2. 그 블록들엔 `return 204;` **외에 아무것도 없다** — proxy_pass/root/alias/try_files 가
   들어오면 무자격 콘텐츠 제공이 된다.
3. apple-touch 정규식 블록은 정적자산 정규식(`~* \\.(js|css|...)$`)보다 **앞**에 있다 —
   nginx 는 정규식 location 을 선언 순서로 매칭한다.
4. `index.html` 의 아이콘 `<link>` 는 서버 경로가 아니라 **data URI** 다 — 서버 경로면
   Basic Auth 아래에서 그 요청 자체가 두 번째 다이얼로그다.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE = _ROOT / "frontend" / "nginx.conf.template"
_INDEX = _ROOT / "frontend" / "index.html"

_ICON_LOCATIONS = (
    r"location\s*=\s*/favicon\.ico\s*\{",
    r"location\s*=\s*/favicon\.svg\s*\{",
    # iOS Safari 는 크기 지정 변형(`-120x120` 등)도 탐침한다 — 로컬 렌더 실측에서 그 변형이
    # 401 로 남아 정규식을 넓혔다.
    r"location\s*~\s*\^/apple-touch-icon\(-\[0-9\]\+x\[0-9\]\+\)\?\(-precomposed\)\?\\\.png\$\s*\{",
)
_STATIC_ASSET_REGEX_LOCATION = r"location\s*~\*\s*\\\.\(js\|css"


def _strip_comments(text: str) -> str:
    return "\n".join(ln.split("#", 1)[0] for ln in text.splitlines())


def _template() -> str:
    assert _TEMPLATE.is_file(), f"템플릿이 없다: {_TEMPLATE}"
    return _strip_comments(_TEMPLATE.read_text(encoding="utf-8"))


def _icon_blocks(text: str) -> list[tuple[str, str]]:
    """(패턴, 블록 본문) — 각 아이콘 location 의 `{ ... }` 안쪽 문자열."""
    out = []
    for pat in _ICON_LOCATIONS:
        m = re.search(pat, text)
        assert m, f"아이콘 단락 location 이 없다: {pat!r} — Safari 두 번째 로그인 다이얼로그 재발"
        depth, i, start = 1, m.end(), m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        assert depth == 0, f"블록이 닫히지 않았다: {pat!r}"
        out.append((pat, text[start : i - 1]))
    return out


def test_template_when_icon_probed_then_short_circuits_with_204():
    """G-247-1 — 아이콘 location 셋이 존재하고 각각 `return 204;` 를 담는다."""
    for pat, body in _icon_blocks(_template()):
        assert re.search(r"\breturn\s+204\s*;", body), (
            f"{pat!r} 블록에 `return 204;` 가 없다 — 그 경로가 access 단계(auth_basic)로 "
            "내려가 401 + WWW-Authenticate = 두 번째 로그인 다이얼로그"
        )


def test_template_when_icon_block_then_nothing_but_return():
    """G-247-2 — 아이콘 블록엔 `return 204;` 외의 지시자가 **0건**.

    `return` 이 auth 를 앞지르는 성질 때문에, 같은 블록에 콘텐츠 지시자를 두면
    그것이 곧 무자격 제공 경로가 된다. 특히 proxy_pass 는 `/api/` 밖에서도 백엔드에
    닿는 통로다.
    """
    for pat, body in _icon_blocks(_template()):
        directives = [d.strip() for d in body.split(";") if d.strip()]
        assert directives == ["return 204"], (
            f"{pat!r} 블록에 `return 204` 외 지시자가 있다: {directives!r}"
        )


def test_template_when_regex_locations_then_apple_touch_precedes_static_assets():
    """G-247-3 — apple-touch 정규식이 정적자산 정규식보다 앞에 선언돼 있다.

    뒤에 두면 `~* \\.(...|png|...)$` 가 먼저 매치돼 정적 파일 핸들러(access 단계 경유)
    로 떨어지고, 단락은 죽은 코드가 된다.
    """
    text = _template()
    apple = re.search(_ICON_LOCATIONS[2], text)
    static = re.search(_STATIC_ASSET_REGEX_LOCATION, text)
    assert apple and static, "정규식 location 둘 중 하나가 없다"
    assert apple.start() < static.start(), (
        "apple-touch 단락 블록이 정적자산 정규식 **뒤**에 있다 — nginx 는 정규식 location 을 "
        "선언 순서로 매칭하므로 단락이 도달 불가"
    )


def test_template_when_cycle247_applied_then_auth_basic_off_still_absent():
    """G-247-4 — 단락은 `auth_basic off` 로 구현하지 않았다(D-1-b 와 같은 축, 이중 봉인)."""
    assert not re.search(r"\bauth_basic\s+off\s*;", _template()), (
        "아이콘 단락을 `auth_basic off` 로 바꾸지 마라 — `return` 이 정확한 도구다(D-1-b)"
    )


def test_index_html_when_icon_linked_then_data_uri_not_server_path():
    """G-247-5 — `index.html` 의 `rel="icon"` 링크는 data URI 다.

    서버 경로(`/favicon.svg`)로 되돌리면 Basic Auth 아래에서 그 요청이 401 → Safari 두 번째
    다이얼로그. 템플릿의 `= /favicon.svg { return 204; }` 가 뒤를 받치지만, 그러면 아이콘이
    사라진다 — data URI 가 아이콘을 살리는 유일한 형태다.
    """
    html = _INDEX.read_text(encoding="utf-8")
    links = re.findall(r'<link\b[^>]*\brel="(?:shortcut )?icon"[^>]*>', html)
    assert links, "index.html 에 rel=\"icon\" 링크가 없다(브라우저가 /favicon.ico 를 탐침한다)"
    for link in links:
        m = re.search(r'\bhref="([^"]*)"', link)
        assert m and m.group(1).startswith("data:image/svg+xml"), (
            f"favicon 링크가 서버 경로다: {link[:120]!r} — Basic Auth 아래에서 두 번째 로그인 "
            "다이얼로그를 만든다(cycle247)"
        )
