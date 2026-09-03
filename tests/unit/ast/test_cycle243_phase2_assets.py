"""cycle243 Red (D/Phase 2) — 백엔드 인증 자산 정적·AST 가드.

명세: `_workspace/red/cycle243_api_auth_spec.md` §3.D(D-6, D-9~D-11) · §2.3 · §2.5

Phase 1 커밋(§6.1 P1-1)에 이 파일이 섞이면 아직 없는 Phase 2 자산 때문에 CI 가
빨간불이 되어 **장중 배포 가능한 Phase 1 이 막힌다**. 그래서 Phase 1 가드
(`test_cycle243_deploy_assets.py`)와 분리했다 — 이 파일은 §6.3 P2-2 커밋 소속이다.

## D-12 는 명세 목록에 없는 추가 가드다 (사유)

§2.3.1 의 "`authorize` 는 모듈 레벨 함수이고 전역 이름으로 호출한다" 는 **테스트
seam 의 생사가 걸린 구조 계약**인데, 명세의 Red 목록에서는 M-21 의 검출을 C-1(픽스처
무효화 → 201케이스 401)에만 맡긴다. 그 경로는 "다른 40개 파일이 무너지는" 간접
신호라 원인 귀인이 느리고, C-1 이 스킵/삭제되면 계약이 통째로 무방비가 된다.
구조를 직접 고정하는 가드를 하나 둔다(cycle224 의 "자기 가드 공허성" 교훈).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_MW = _ROOT / "src" / "middleware" / "api_auth.py"
_COMPOSE_PROD = _ROOT / "docker-compose.prod.yml"
_COMPOSE_DEV = _ROOT / "docker-compose.yml"
_VITE = _ROOT / "frontend" / "vite.config.ts"
_ENV_EXAMPLE = _ROOT / ".env.example"

KEY_FIELD = "api_auth_key"


def _read(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"Red — {path.relative_to(_ROOT)} 부재 (명세 §2.2/§2.5)")
    return path.read_text(encoding="utf-8")


def _mw_tree() -> ast.Module:
    return ast.parse(_read(_MW))


def _env_entries(service: dict) -> list[str]:
    env = service.get("environment") or []
    if isinstance(env, dict):
        return [f"{k}={v}" for k, v in env.items()]
    return [str(e) for e in env]


def _find_func(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ---------------------------------------------------------------------------
# D-6 — backend 포트 바인딩 (SG 오설정 2차 방어)
# ---------------------------------------------------------------------------
def test_compose_backend_when_phase2_then_bound_to_loopback():
    """D-6 — `127.0.0.1:8000:8000`.

    현재는 `0.0.0.0:8000` 게시라 **AWS 보안그룹이 유일한 방어막**이다. 이 한 줄이
    backend 컨테이너 재생성을 유발하므로 Phase 2 전용이다(①).
    """
    data = yaml.safe_load(_read(_COMPOSE_PROD))
    backend = (data.get("services") or {}).get("backend") or {}
    ports = [str(p) for p in (backend.get("ports") or [])]
    assert "127.0.0.1:8000:8000" in ports, ports


# ---------------------------------------------------------------------------
# D-9 — 개발 환경 (예외 없는 단일 경로)
# ---------------------------------------------------------------------------
def _strip_ts_comments(text: str) -> str:
    """TS 주석(`//`, `/* */`) 제거 — 주석이 가드를 충족시키는 공허성 차단.

    이 파일의 다른 가드들은 AST 로 코드만 보는데 D-9 만 원시 부분문자열이었다. 그
    결과 vite 설정의 **한글 주석 3줄**이 `X-API-Key`·`API_AUTH_KEY` 토큰을 포함해,
    실제 주입 코드를 지워도(뮤테이션 E-6) 초록이 유지됐다.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def test_dev_env_when_no_bypass_then_vite_injects_header():
    """D-9 — 개발 예외·개발용 기본키 **없이** dev 대시보드를 살리는 유일한 경로.

    커밋되는 개발용 기본키는 공격자가 프로덕션에 가장 먼저 시도할 값이고,
    `KIS_ENV != real` 류의 모드 분기 예외는 운영이 vts 로 도는 날 인증을 조용히
    없앤다(비활성화=경로 변경 독트린). 그래서 서버 측 vite proxy 가 헤더를 넣는다.

    검사는 **주석을 걷어낸 코드**에서 하고, 값이 `process.env.API_AUTH_KEY` 에서
    오는지까지 본다(빈 문자열 상수로 바꾸는 뮤테이션 W-5 차단).
    """
    code = _strip_ts_comments(_read(_VITE))
    assert "X-API-Key" in code, "vite proxy 에 X-API-Key 주입이 없다 — dev 전면 401"
    assert re.search(
        r"['\"]X-API-Key['\"]\s*:\s*process\.env\.API_AUTH_KEY", code
    ), f"X-API-Key 값이 process.env.API_AUTH_KEY 가 아니다:\n{code}"

    data = yaml.safe_load(_read(_COMPOSE_DEV))
    frontend = (data.get("services") or {}).get("frontend") or {}
    entries = _env_entries(frontend)
    assert any(e.startswith("API_AUTH_KEY=") for e in entries), entries


def test_dev_proxy_when_change_origin_then_origin_normalized_too():
    """D-9-b — vite proxy 가 `Origin` 도 upstream 으로 정규화한다.

    `changeOrigin: true` 는 **Host 만** 바꾸고 브라우저 `Origin: http://localhost:3000`
    은 그대로 넘긴다 ⇒ 백엔드 상태변경 Origin 검사가 `cross_origin` 401 을 낸다(실측).
    GET 폴링은 통과하므로 **대시보드는 정상으로 보이고 버튼만 말없이 죽는다**(UI 401
    처리 부재, L10). `Origin: apiTarget` 한 줄이 dev 를 설정 없이 살린다 —
    `API_ALLOWED_ORIGINS` 는 이 경로의 폴백이지 전제가 아니다.
    """
    code = _strip_ts_comments(_read(_VITE))
    assert re.search(r"\bOrigin\s*:\s*apiTarget\b", code), (
        f"vite proxy 가 Origin 을 정규화하지 않는다 — dev 상태변경 전면 401:\n{code}"
    )


# ---------------------------------------------------------------------------
# D-10 — 상수시간 비교
# ---------------------------------------------------------------------------
def test_middleware_when_comparing_key_then_constant_time_only():
    """D-10 — `secrets.compare_digest` 사용 ∧ 키를 `==`/`!=` 로 비교하는 노드 0건.

    M-4(`==` 로 교체)가 여기서 죽는다. `if not key:` 같은 **빈 값 선분기**는
    `UnaryOp` 라 여기 걸리지 않는다 — §2.3.3 이 요구하는 분기이므로 의도적이다.
    """
    tree = _mw_tree()

    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Attribute) and n.func.attr == "compare_digest")
            or (isinstance(n.func, ast.Name) and n.func.id == "compare_digest")
        )
    ]
    assert calls, "secrets.compare_digest 호출이 없다 — 타이밍 사이드채널"

    # settings.api_auth_key 에서 흘러나온 지역 이름을 수집(1단계 전이).
    key_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute):
            if node.value.attr == KEY_FIELD:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        key_names.add(target.id)

    def _is_key_expr(node: ast.AST) -> bool:
        if isinstance(node, ast.Attribute) and node.attr == KEY_FIELD:
            return True
        return isinstance(node, ast.Name) and node.id in key_names

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
            continue
        operands = [node.left, *node.comparators]
        if any(_is_key_expr(o) for o in operands):
            offenders.append(ast.dump(node))
    assert not offenders, f"키를 등가 비교하는 노드: {offenders}"


# ---------------------------------------------------------------------------
# D-11 — 개발용 기본키 커밋 차단
# ---------------------------------------------------------------------------
def _env_example_values(var: str) -> list[str]:
    text = _read(_ENV_EXAMPLE)
    lines = [l for l in text.splitlines() if re.match(rf"^{var}\s*=", l)]
    assert lines, f"{var} 플레이스홀더가 없다"
    return [line.split("=", 1)[1].split("#", 1)[0].strip() for line in lines]


def test_env_example_when_documented_then_auth_key_value_is_empty():
    """D-11 — `.env.example` 의 `API_AUTH_KEY` 값은 **비어 있다**. M-20 이 여기서 죽는다.

    커밋되는 개발용 기본키는 공격자가 프로덕션에 가장 먼저 시도할 값이다.
    """
    for value in _env_example_values("API_AUTH_KEY"):
        assert value == "", f"API_AUTH_KEY 에 값이 커밋돼 있다: {value!r}"


def test_env_example_when_documented_then_allowed_origins_never_wildcard():
    """D-11-b — `API_ALLOWED_ORIGINS` 는 존재하되 **`*` 가 아니다**.

    비밀이 아니므로 값 자체는 허용한다(dev 편의). 금지되는 것은 와일드카드 하나다 —
    그 한 값이 CORS 를 `allow_all_origins` 로 되돌려 결정 ⑪ 이 제거한
    `["*"] + allow_credentials` 조합을 부활시키고, 동시에 상태변경 Origin 검사(⑫)까지
    무력화한다. 런타임 방어는 `parse_allowed_origins` 가 별도로 한다(D-13).
    """
    for value in _env_example_values("API_ALLOWED_ORIGINS"):
        assert "*" not in value, f"와일드카드 오리진이 커밋돼 있다: {value!r}"


# ---------------------------------------------------------------------------
# D-13 / D-14 — 관측·설정 방어 (적대적 검증 후속)
# ---------------------------------------------------------------------------
def test_allowed_origins_when_wildcard_then_dropped():
    """D-13 — `parse_allowed_origins` 가 `*` 를 **버린다**(행위 축).

    `.env` 한 줄(`API_ALLOWED_ORIGINS=*`)로 CORS 와 CSRF 두 통제가 동시에 열리는
    경로를 남기지 않는다. 값 검증도 경고도 없이 통과하던 것이 결함이었다.
    """
    from src.middleware.api_auth import has_wildcard_origin, parse_allowed_origins

    assert parse_allowed_origins("*") == []
    assert parse_allowed_origins("http://a.example, *, http://b.example") == [
        "http://a.example",
        "http://b.example",
    ]
    assert has_wildcard_origin("*") is True
    assert has_wildcard_origin("http://a.example") is False


def test_client_ip_when_behind_proxy_then_reads_forwarded_headers():
    """D-14 — 거부 로그의 `ip=` 가 프록시 뒤에서 상수가 되지 않는다.

    Phase 2 는 backend 를 `127.0.0.1:8000` 에 묶으므로 외부 요청이 전부 nginx 를
    거치고, uvicorn 은 `--proxy-headers` 없이 뜬다 ⇒ `scope["client"]` 는 항상 nginx
    컨테이너 주소다. 그 값을 공격자 IP 처럼 찍는 것은 **잘못된 귀인**이고, 잘못된
    귀인은 없는 귀인보다 나쁘다. nginx 가 이미 넣어 주는 헤더를 읽는다.
    """
    from src.middleware.api_auth import _client_ip

    base = {"client": ("172.66.0.243", 5000), "headers": []}
    assert _client_ip(base) == ("172.66.0.243", "peer")

    xff = dict(base, headers=[(b"x-forwarded-for", b"1.2.3.4, 203.0.113.9")])
    assert _client_ip(xff) == ("203.0.113.9", "xff")  # 마지막 = 우리 nginx 가 append 한 실 peer

    xri = dict(xff, headers=[*xff["headers"], (b"x-real-ip", b"198.51.100.7")])
    assert _client_ip(xri) == ("198.51.100.7", "xri")

    assert _client_ip({"headers": []}) == ("-", "none")


# ---------------------------------------------------------------------------
# D-12 — 테스트 seam 구조 계약 (명세 추가분, 파일 docstring 사유 참조)
# ---------------------------------------------------------------------------
def test_authorize_when_defined_then_module_level_and_called_globally():
    """D-12 — `authorize` 는 모듈 레벨 함수이고 `__call__` 이 전역 이름으로 호출한다.

    메서드로 감추면 conftest 픽스처가 갈아끼울 대상이 사라지고, 그 순간 기존
    201케이스가 401 로 전멸한다(M-21). 프로덕션 코드에 `_TEST_BYPASS` 플래그를
    두지 않는 대가로 이 구조가 계약이 된다.
    """
    tree = _mw_tree()

    top_level = {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "authorize" in top_level, f"모듈 레벨 `authorize` 부재 (top-level={top_level})"

    cls = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ApiAuthMiddleware"),
        None,
    )
    assert cls is not None, "ApiAuthMiddleware 클래스 부재"
    methods = {
        n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_authorize" not in methods, "판정을 메서드로 감췄다 — 픽스처 seam 소멸"

    call = _find_func(cls, "__call__")
    assert call is not None, "`__call__` 부재 — 순수 ASGI 미들웨어가 아니다"
    bare_calls = [
        n
        for n in ast.walk(call)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "authorize"
    ]
    assert bare_calls, "`__call__` 이 전역 `authorize(...)` 를 호출하지 않는다"


def test_middleware_when_constructed_then_key_not_captured():
    """D-12-b — `__init__` 이 `settings.api_auth_key` 를 캡처하지 않는다(M-15 구조 축).

    A-23 이 행위로 잡고 여기서 구조로 못박는다 — `settings` 는 import 시점 싱글톤이라
    캡처형은 테스트 seam 도 운영 진단(키 회전)도 동시에 막는다.
    """
    tree = _mw_tree()
    cls = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ApiAuthMiddleware"),
        None,
    )
    assert cls is not None, "ApiAuthMiddleware 클래스 부재"
    init = _find_func(cls, "__init__")
    if init is None:
        return  # __init__ 생략 = 캡처 불가 = 계약 충족
    captured = [
        n for n in ast.walk(init) if isinstance(n, ast.Attribute) and n.attr == KEY_FIELD
    ]
    assert not captured, "__init__ 에서 키를 캡처했다 — 요청 시점 참조 계약 위반"


def test_middleware_when_pure_asgi_then_no_base_http_middleware():
    """D-12-c — `BaseHTTPMiddleware` 상속 금지(§0-6).

    이 리포는 anyio portal hang 으로 두 번 데였고(`test_cycle127_progress_routes.py` ·
    `test_pnl_summary.py` 가 TestClient 회피를 명시), stock_master 4개 refresh 라우트가
    `BackgroundTasks` fire-and-forget + 5초 폴링이다. 미들웨어를 하나 더 쌓으면 매
    요청 anyio task group + memory stream 이 추가된다.
    """
    text = _read(_MW)
    assert "BaseHTTPMiddleware" not in text, "순수 ASGI 계약 위반"
