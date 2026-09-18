"""cycle303 — macro_lite 이식 1단계의 격리 가드 (텍스트 + YAML 파싱, 행위 무접촉).

macro_lite 컨테이너는 매매 이미지와 완전히 분리돼야 한다(`_workspace/cycle303_macro_integration_spec.md`).
이 파일은 그 분리가 실제로 지켜지는지 여섯 조건으로 잠근다:

1. nginx **두 템플릿 모두**에 `/api/macro` 프록시가 있다(한쪽만이면 RED — 대시보드가 TLS
   유무에 따라 macro 화면만 다르게 동작하는 결함을 막는다).
2. 그 프록시는 리터럴이 아니라 변수+resolver 형식이다(macro 다운 시 nginx 기동 자체가
   죽는 사고를 막는다, 팀 명세 §4) + `auth_basic off` 가 어디에도 없다(D-1-b 불변).
3. `docker-compose.prod.yml` 의 `macro` 서비스는 본체에 있고 `ports:`/`env_file` 이 없다
   (호스트 포트 게시 = nginx Basic Auth 우회, `env_file: .env` = 비밀 33개 유출).
4. 루트 `requirements.txt` 에 `numpy`/`yfinance` 가 없다(매매 이미지 오염 방지 — `pandas`
   는 이미 루트에 있으므로 가드 대상에서 제외한다).
5. `src/` 전체에 `macro_lite` import 가 0건이다(매매 코드가 macro 패키지를 참조하지 않는다).
6. `macro/macro_lite/` 는 원 프로젝트(stock-manager) 모듈을 import 하지 않는다(README
   「원 프로젝트 모듈 의존이 없음을 확인하려면」 절의 grep 조건을 테스트로 고정).
7. `pyproject.toml` 의 `testpaths` 가 `["tests"]` 라서 `macro/tests/`(vendor, 자체 pytest.ini
   보유)가 우리 스위트에 섞이지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[3]
_NGINX_TEMPLATES = [
    _ROOT / "frontend" / "nginx.conf.template",
    _ROOT / "frontend" / "nginx.tls.conf.template",
]
_COMPOSE_PROD = _ROOT / "docker-compose.prod.yml"
_ROOT_REQUIREMENTS = _ROOT / "requirements.txt"
_SRC_DIR = _ROOT / "src"
_MACRO_LITE_DIR = _ROOT / "macro" / "macro_lite"
_PYPROJECT = _ROOT / "pyproject.toml"


def _read(p: Path) -> str:
    assert p.is_file(), f"없다: {p}"
    return p.read_text(encoding="utf-8")


# ── 1·2. nginx 두 템플릿 모두 /api/macro 프록시 + 변수형 proxy_pass + auth_basic off 부재 ──

def test_nginx_when_both_templates_then_macro_location_present_in_each():
    for tpl in _NGINX_TEMPLATES:
        text = _read(tpl)
        assert "location /api/macro/" in text, f"{tpl.name} 에 macro 프록시 location 이 없다"


def test_nginx_when_macro_location_then_uses_resolver_variable_form_not_literal():
    """🔴 `proxy_pass http://macro:8000;` 리터럴이면 macro 다운 시 nginx 기동이 죽는다
    (팀 명세 §4). 변수 + resolver + `$request_uri` 형식이어야 한다."""
    for tpl in _NGINX_TEMPLATES:
        text = _read(tpl)
        # macro location 블록만 추출(다음 `location` 등장 전까지).
        m = re.search(r"location /api/macro/ \{(.*?)\n    \}", text, re.S)
        assert m, f"{tpl.name} 에서 macro location 블록을 못 찾았다"
        block = m.group(1)
        assert "resolver 127.0.0.11" in block, f"{tpl.name}: resolver 없음\n{block}"
        assert re.search(r"set\s+\$macro_upstream\s+http://macro:8000;", block), (
            f"{tpl.name}: 변수 upstream 정의가 없다\n{block}"
        )
        assert "proxy_pass $macro_upstream$request_uri;" in block, (
            f"{tpl.name}: proxy_pass 가 변수+$request_uri 형식이 아니다\n{block}"
        )
        # 리터럴 형식이 코드로 재등장하지 않는다(주석은 예외 — 리터럴 예시를 설명하는 문장은 허용).
        code_lines = [ln for ln in block.splitlines() if not ln.lstrip().startswith("#")]
        code = "\n".join(code_lines)
        assert "proxy_pass http://macro:8000;" not in code, (
            f"{tpl.name}: macro location 안에 리터럴 proxy_pass 가 남아 있다"
        )


def _strip_comments(text: str) -> str:
    """cycle243 `test_cycle243_deploy_assets.py::_strip_comments` 와 동일 규약 — `#` 뒤를
    버린다. 설명 주석이 금지 구문을 문자 그대로 인용하는 경우(이 파일 자신 포함)를
    오탐 처리하지 않기 위해서다."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def test_nginx_when_any_template_then_no_auth_basic_off_anywhere():
    """D-1-b 불변 — macro location 추가가 이 금기를 재도입하지 않았는지 재확인
    (`test_cycle243_deploy_assets.py::test_template_when_present_then_no_auth_basic_off_anywhere`
    와 같은 계약을 두 템플릿 모두에 대해 반복 — TLS 템플릿은 그 가드의 대상 밖이다)."""
    for tpl in _NGINX_TEMPLATES:
        text = _strip_comments(_read(tpl))
        assert not re.search(r"auth_basic\s+off\s*;", text), f"{tpl.name} 에 auth_basic off 가 있다"


def test_nginx_when_macro_location_then_auth_basic_explicit_two_lines():
    for tpl in _NGINX_TEMPLATES:
        text = _read(tpl)
        m = re.search(r"location /api/macro/ \{(.*?)\n    \}", text, re.S)
        assert m, tpl.name
        block = m.group(1)
        assert 'auth_basic           "auto_stock";' in block, f"{tpl.name}: auth_basic 명시 없음"
        assert "auth_basic_user_file /etc/nginx/secrets/.htpasswd;" in block, (
            f"{tpl.name}: auth_basic_user_file 명시 없음"
        )


# ── 3. docker-compose.prod.yml — macro 서비스 본체 + ports/env_file 부재 (YAML 파싱) ──

def _load_compose(path: Path) -> dict:
    text = _read(path)
    # `${VAR}`/`${VAR:-default}` 보간 구문은 YAML 파서가 그대로 문자열로 받아들이므로
    # 파싱 자체엔 문제가 없다(compose 는 런타임에 보간한다) — 치환 없이 그대로 로드한다.
    return yaml.safe_load(text)


def test_compose_prod_when_loaded_then_macro_service_in_body_no_ports_no_env_file():
    d = _load_compose(_COMPOSE_PROD)
    services = d.get("services", {})
    assert "macro" in services, "docker-compose.prod.yml 본체에 macro 서비스가 없다"
    macro = services["macro"]
    assert "ports" not in macro, f"macro 서비스에 ports: 가 있다 — 호스트 게시는 Basic Auth 우회다: {macro}"
    assert "env_file" not in macro, f"macro 서비스에 env_file 이 있다 — 비밀 33개가 유입된다: {macro}"
    # 팀 명세 §3 — build.context 는 독립 디렉터리 `./macro` 여야 매매 리포가 이미지에 실리지 않는다.
    assert macro.get("build", {}).get("context") == "./macro", macro.get("build")


def test_compose_prod_when_loaded_then_frontend_depends_on_macro():
    d = _load_compose(_COMPOSE_PROD)
    frontend = d["services"]["frontend"]
    assert "macro" in frontend.get("depends_on", []), frontend.get("depends_on")


def test_compose_dev_when_loaded_then_macro_service_present():
    d = _load_compose(_ROOT / "docker-compose.yml")
    services = d.get("services", {})
    assert "macro" in services, "docker-compose.yml(dev) 에 macro 서비스가 없다"
    # dev 는 호스트 npm run dev 경로를 위해 루프백 포트를 여는 것이 계약(prod 와 다르다).
    ports = services["macro"].get("ports", [])
    assert any("127.0.0.1:8010:8000" in p for p in ports), ports
    assert "env_file" not in services["macro"], services["macro"]


# ── 4. 루트 requirements.txt — numpy/yfinance 부재 (pandas 는 이미 있어 대상 제외) ──

def test_root_requirements_when_read_then_no_numpy_or_yfinance():
    text = _read(_ROOT_REQUIREMENTS).lower()
    assert "numpy" not in text, "루트 requirements.txt 에 numpy 가 있다 — 매매 이미지 오염"
    assert "yfinance" not in text, "루트 requirements.txt 에 yfinance 가 있다 — 매매 이미지 오염"
    # pandas 는 이미 루트에 있다(가드 대상 제외 확인용 — 이 단언이 깨지면 스펙 전제가 바뀐 것).
    assert "pandas" in text, "pandas 가 루트에서 사라졌다 — 이 가드의 전제(pandas 는 이미 있다)가 깨졌다"


# ── 5. src/ 에 macro_lite import 0건 ──

def test_src_dir_when_scanned_then_zero_macro_lite_imports():
    hits: list[str] = []
    for py in _SRC_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if re.search(r"^\s*(from|import)\s+macro_lite\b", text, re.M):
            hits.append(str(py.relative_to(_ROOT)))
    assert hits == [], f"src/ 가 macro_lite 를 import 한다: {hits}"


# ── 6. macro/macro_lite/ 가 원 프로젝트 모듈을 import 하지 않는다 (README grep 조건) ──

def test_macro_lite_when_scanned_then_zero_original_project_imports():
    """README 「원 프로젝트 모듈 의존이 없음을 확인하려면」 절의 grep 조건(0건)을 고정한다:
    `from stock`/`from services`/`from config`/`from db`/`import stock`/`import services`/
    `import config`/`import db` 가 macro_lite/ 어디에도 없어야 한다."""
    pattern = re.compile(
        r"^\s*(from\s+(stock|services|config|db)\b|import\s+(stock|services|config|db)\b)"
    )
    hits: list[str] = []
    for py in _MACRO_LITE_DIR.rglob("*.py"):
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.match(line):
                hits.append(f"{py.relative_to(_ROOT)}:{lineno}: {line.strip()}")
    assert hits == [], f"macro/macro_lite/ 가 원 프로젝트 모듈을 import 한다: {hits}"


# ── 7. pyproject.toml testpaths == ["tests"] (macro/tests/ 가 우리 스위트에 안 섞인다) ──

def test_pyproject_when_read_then_testpaths_is_tests_only():
    import tomllib

    d = tomllib.loads(_read(_PYPROJECT))
    testpaths = d["tool"]["pytest"]["ini_options"]["testpaths"]
    assert testpaths == ["tests"], (
        f"pyproject.toml testpaths={testpaths!r} — macro/tests/ 가 섞일 수 있다"
    )


def test_macro_dir_when_present_then_has_own_pytest_ini_not_relying_on_root():
    macro_pytest_ini = _ROOT / "macro" / "pytest.ini"
    assert macro_pytest_ini.is_file(), "macro/pytest.ini 가 없다 — 단독 실행 경로가 없다"
    text = _read(macro_pytest_ini)
    assert re.search(r"^testpaths\s*=\s*tests\s*$", text, re.M), text
