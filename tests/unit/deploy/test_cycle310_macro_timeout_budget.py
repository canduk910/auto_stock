"""cycle310 — macro 컨테이너의 FRED 타임아웃이 nginx 읽기 예산 안에 드는가.

🔴 **이 가드가 `macro/tests/` 가 아니라 여기 있는 이유** — `macro/macro_lite/` 와
`macro/tests/` 는 stock-manager 에서 **무수정 vendor** 하는 영역이라, 우리 계약을 거기
넣으면 다음 재이식에서 조용히 덮인다(2026-09-18 실제로 한 번 덮였다). 「우리 nginx 가
60초에 끊는다」는 **우리 배포 구성의 사실**이므로 우리 테스트가 지킨다.

지키는 불변식 하나 — `credit-spread`·`macro-cycle` 은 FRED CSV 를 **시리즈 2개(HY·IG) ×
재시도 2회** 친다. 그 최악 소요가 nginx `location /api/macro/` 의 `proxy_read_timeout`
을 넘으면 화면이 **504** 를 받는다(2026-09-18 실측: 타임아웃 25초일 때 104초).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

#: CSV 호출 횟수 = 시리즈 2개(BAMLH0A0HYM2·BAMLC0A0CM) × 시도 2회(최초 + 재시도 1회).
#: `macro_lite/fetcher.py::_http_get_fred_csv` 의 `for attempt in (1, 2)` 가 근거다.
_CSV_ATTEMPTS = 2
_CSV_SERIES = 2

_COMPOSE_FILES = ("docker-compose.prod.yml", "docker-compose.yml")
_NGINX_TEMPLATES = ("frontend/nginx.conf.template", "frontend/nginx.tls.conf.template")


def _read(rel: str) -> str:
    p = ROOT / rel
    assert p.exists(), f"{rel} 이 없다"
    return p.read_text(encoding="utf-8")


def _macro_timeout(compose_text: str) -> float:
    m = re.search(r"MACRO_LITE_FRED_TIMEOUT\s*=\s*([0-9.]+)", compose_text)
    assert m, "compose 의 macro 서비스에 MACRO_LITE_FRED_TIMEOUT 이 없다"
    return float(m.group(1))


def _macro_proxy_read_timeout(nginx_text: str) -> float | None:
    """`location /api/macro/` 블록 안의 `proxy_read_timeout` 초 단위 값."""
    start = nginx_text.find("location /api/macro/")
    if start < 0:
        return None
    # 블록 끝까지 (다음 `location ` 또는 문서 끝)
    nxt = nginx_text.find("\n    location ", start + 1)
    block = nginx_text[start : nxt if nxt > 0 else len(nginx_text)]
    m = re.search(r"proxy_read_timeout\s+([0-9.]+)s", block)
    return float(m.group(1)) if m else None


@pytest.mark.parametrize("compose", _COMPOSE_FILES)
def test_macro_timeout_declared(compose: str) -> None:
    """두 compose 모두 같은 값을 선언한다 — 한쪽만 두면 로컬이 운영 경로를 재현 못 한다."""
    assert _macro_timeout(_read(compose)) > 0


def test_both_composes_agree() -> None:
    values = {c: _macro_timeout(_read(c)) for c in _COMPOSE_FILES}
    assert len(set(values.values())) == 1, f"compose 간 값이 갈렸다: {values}"


@pytest.mark.parametrize("tpl", _NGINX_TEMPLATES)
def test_csv_worst_case_fits_nginx_budget(tpl: str) -> None:
    """`timeout × 2회 × 2시리즈` 가 nginx `proxy_read_timeout` 보다 작아야 한다."""
    budget = _macro_proxy_read_timeout(_read(tpl))
    if budget is None:
        pytest.skip(f"{tpl} 에 `location /api/macro/` 또는 proxy_read_timeout 이 없다")

    timeout = _macro_timeout(_read("docker-compose.prod.yml"))
    worst = timeout * _CSV_ATTEMPTS * _CSV_SERIES
    assert worst < budget, (
        f"CSV 최악 {worst:g}초(= {timeout:g} × {_CSV_ATTEMPTS}회 × {_CSV_SERIES}시리즈) 가 "
        f"{tpl} 의 nginx 예산 {budget:g}초를 넘는다 — 하이일드·경기사이클이 504 가 된다"
    )


def test_guard_is_not_vacuous() -> None:
    """가드가 공허하지 않은지 — 값을 25로 되돌리면 실제로 붉어지는 관계인지 산수로 확인."""
    budget = _macro_proxy_read_timeout(_read("frontend/nginx.conf.template"))
    if budget is None:
        pytest.skip("nginx 템플릿에 macro 블록이 없다")
    # 원 패키지 기본값 25 를 쓰면 100초라 어떤 합리적 nginx 예산도 넘는다.
    assert 25 * _CSV_ATTEMPTS * _CSV_SERIES > budget, (
        "nginx 예산이 100초를 넘게 커졌다면 이 가드의 전제가 바뀐 것이다 — 주석을 갱신하라"
    )
