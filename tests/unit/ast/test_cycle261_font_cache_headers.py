"""cycle261 후속(적대 검토) — 자체 호스팅 Gmarket Sans TTF 가 no-store 로 서빙되던 결함.

■ 발단
`frontend/nginx.conf.template`(+ TLS 사본)의 정적자산 캐시 정규식
`~* \\.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$` 에 `ttf` 가 없어 `/fonts/*.ttf`
요청이 `location /`(try_files) 로 떨어지고 그 블록의
`Cache-Control: no-cache, no-store, must-revalidate` 를 받는다. nginx:alpine 실측 —
`Content-Type: application/octet-stream`(mime.types 에 ttf 없음) + no-store 라
전체 새로고침마다 Medium+Bold ≈ 4.9MB 를 재다운로드하고 `font-display: swap` 이라
매번 FOUT 이 보인다.

■ 시정 계약
`/fonts/` 전용 `location ^~ /fonts/ { ... }` 블록을 두 템플릿에 추가해 캐시 가능
`Cache-Control: public, max-age=...` 을 싣는다. `^~` 접두 location 은 정규식
location 의 선언 순서와 무관하게 매칭되므로(nginx 우선순위 규칙) 정적자산 정규식과의
상대 위치는 계약이 아니다 — 그래도 인접 배치로 가독성을 지킨다.

파일명 해시가 없는 정적 자산이라 `immutable`(cycle243 정적자산 규약)은 쓰지 않는다 —
폰트 파일 내용이 바뀌면(예: 오탈자 재발행) 브라우저가 무기한 캐시를 들고 있으면 안 된다.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_HTTP_TEMPLATE = _ROOT / "frontend" / "nginx.conf.template"
_TLS_TEMPLATE = _ROOT / "frontend" / "nginx.tls.conf.template"

_FONTS_LOCATION = r"location\s+\^~\s+/fonts/\s*\{"
_STATIC_ASSET_LOCATION = r"location\s*~\*\s*\\\.\(js\|css"


def _strip_comments(text: str) -> str:
    return "\n".join(ln.split("#", 1)[0] for ln in text.splitlines())


def _read(path: Path) -> str:
    assert path.is_file(), f"템플릿이 없다: {path}"
    return _strip_comments(path.read_text(encoding="utf-8"))


def _depth_at(text: str, idx: int) -> int:
    """idx 위치의 중괄호 중첩 깊이. server 직속 = 1, location 안 = 2."""
    return text.count("{", 0, idx) - text.count("}", 0, idx)


def _block_body(text: str, location_pattern: str) -> str | None:
    m = re.search(location_pattern, text)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[m.end() : i - 1]


def _fonts_location_body(text: str) -> str | None:
    return _block_body(text, _FONTS_LOCATION)


class _TestBothTemplates:
    """서브클래스가 TEMPLATE 을 지정 — HTTP·TLS 양쪽 동일 계약."""

    TEMPLATE: Path

    def test_fonts_location_exists_at_server_level(self) -> None:
        text = _read(self.TEMPLATE)
        m = re.search(_FONTS_LOCATION, text)
        assert m, (
            f"{self.TEMPLATE.name} 에 `location ^~ /fonts/ {{ ... }}` 블록이 없다 — "
            "TTF 가 여전히 SPA fallback(no-store) 으로 떨어진다"
        )
        assert _depth_at(text, m.start()) == 1, "fonts location 이 server 블록 직속이 아니다"

    def test_fonts_location_is_cacheable_public(self) -> None:
        text = _read(self.TEMPLATE)
        body = _fonts_location_body(text)
        assert body is not None, "fonts location 블록을 찾지 못했다"
        assert re.search(r"add_header\s+Cache-Control", body), (
            "fonts location 에 Cache-Control add_header 가 없다"
        )
        cache_control_values = re.findall(r'Cache-Control\s+"([^"]*)"', body)
        assert cache_control_values, "Cache-Control 헤더 값을 파싱하지 못했다"
        for value in cache_control_values:
            assert "no-store" not in value, f"fonts location 이 여전히 no-store: {value!r}"
            assert "public" in value, f"fonts location Cache-Control 에 public 이 없다: {value!r}"
        assert re.search(r"expires\s+\S", body), "fonts location 에 expires 지시어가 없다"
        assert re.search(r"default_type\s+font/ttf\s*;", body), (
            "fonts location 에 default_type font/ttf 가 없다 — nginx:alpine mime.types 에 "
            "ttf 가 없어 application/octet-stream 으로 나간다"
        )

    def test_fonts_location_has_no_dangerous_directives(self) -> None:
        """`proxy_pass`/`alias`/`try_files`/`auth_basic off` 가 들어오면 무자격 콘텐츠 제공이
        되거나(cycle247 D-1-b 계열 위험) 인증 상속을 끊는다 — 이 블록엔 캐시 헤더만 둔다."""
        text = _read(self.TEMPLATE)
        body = _fonts_location_body(text)
        assert body is not None
        for forbidden in ("proxy_pass", "alias ", "try_files", "auth_basic off"):
            assert forbidden not in body, f"fonts location 에 금지 지시어 존재: {forbidden!r}"

    def test_static_asset_regex_location_still_present(self) -> None:
        """기존 정적자산(js/css/png/...) 캐시 location 회귀 없음 — fonts 전용 location 추가가
        기존 계약을 대체한 게 아니라 병존한다."""
        text = _read(self.TEMPLATE)
        assert re.search(_STATIC_ASSET_LOCATION, text), "정적자산 정규식 location 이 사라졌다"


class TestHttpTemplate(_TestBothTemplates):
    TEMPLATE = _HTTP_TEMPLATE


class TestTlsTemplate(_TestBothTemplates):
    TEMPLATE = _TLS_TEMPLATE
